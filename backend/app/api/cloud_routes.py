"""Authenticated Cloud control plane and explicitly gated product routes."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.requests import ClientDisconnect

from backend.app.auth.dependencies import require_principal
from backend.app.auth.models import AuthFailure
from backend.app.application.failure_contract import map_public_failure
from backend.app.application.cloud_workspace_service import CloudSelectionConflict
from backend.app.harness.errors import ToolExecutionError, ToolTimeoutError
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.application.cloud_operation import cloud_operation, operation_scope, trace_failure
from backend.app.config.runtime_build import runtime_build_identity

CONTROL_PLANE_ROUTES = frozenset({
    ("GET", "/api/v1/cloud/catalog"), ("GET", "/api/v1/cloud/status"),
    ("POST", "/api/v1/cloud/selection"), ("GET", "/api/v1/cloud/llm-profiles"),
    ("POST", "/api/v1/cloud/selection/link"),
    ("GET", "/api/v1/cloud/report-templates"),
    ("GET", "/api/v1/cloud/catalog/workspaces"), ("GET", "/api/v1/cloud/catalog/resources"),
})
router = APIRouter(prefix="/api/v1/cloud")


def is_product_route(method,path):
    return (method=='POST' and re.fullmatch(r'/api/v1/cloud/presentations/[a-zA-Z0-9_-]{1,64}',path) is not None
        or (method,path) in {('POST','/api/v1/cloud/chat'),('POST','/api/v1/cloud/new-chat'),
        ('POST','/api/v1/cloud/restore'),('GET','/api/v1/cloud/history'),('GET','/api/v1/cloud/reports')}
        or method=='GET' and re.fullmatch(r'/api/v1/cloud/(?:history/[^/]{1,64}|reports/[^/]{1,64}(?:/download)?)',path) is not None
        or method=='DELETE' and re.fullmatch(r'/api/v1/cloud/(?:history|reports)/[a-zA-Z0-9_-]{1,64}',path) is not None
        or method=='POST' and re.fullmatch(r'/api/v1/cloud/(?:history|reports)/[a-zA-Z0-9_-]{1,64}/(?:rename|archive|unarchive)',path) is not None)


async def workspace(request: Request, *, allowed_query=()):
    service = getattr(request.app.state, "cloud_workspace_service", None)
    if service is None: raise AuthFailure("AUTH_FORBIDDEN", 403)
    if any(k not in allowed_query or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise HTTPException(422, "invalid_cloud_request")
    if request.method == "GET" and await bounded_body(request, 0): raise HTTPException(422, "invalid_cloud_request")
    return service, request.cookies.get(request.app.state.settings.auth_cookie_name)


@cloud_operation
async def safe_call(operation, context='catalog'):
    try:
        with operation_scope(): return await operation
    except CloudSelectionConflict:
        raise HTTPException(409, "cloud_selection_changed") from None
    except (PowerBIAdapterError, ToolExecutionError, ToolTimeoutError) as error:
        cause = (error.__context__ or error) if isinstance(error, ToolExecutionError) else error
        if isinstance(cause, AuthFailure): raise cause
        code = 'QUERY_TIMEOUT' if isinstance(error,ToolTimeoutError) else getattr(cause, "error_type", "INTERNAL_FAILURE")
        failure = map_public_failure(terminal_state="tool_failed", stage="tool_execution", error_type=code)
        detail = {"failure": failure.model_dump(mode="json")}
        if getattr(cause, 'denial_reason', None) == 'test_scope_missing':
            detail['denial_reason'] = 'test_scope_missing'
        status = 403 if code in {'RESOURCE_NOT_ACCESSIBLE','AUTH_FORBIDDEN'} else 503
        if getattr(cause, 'denial_reason', None) == 'test_scope_missing': status = 503
        trace_failure(context,error,failure,status)
        raise HTTPException(status, detail) from None


@router.get("/catalog")
async def catalog(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return await safe_call(service.catalog(sid, principal))


@router.get('/catalog/workspaces')
@router.get('/catalog/resources')
async def browse_catalog(request: Request, principal=Depends(require_principal)):
    resource = request.url.path.endswith('/resources')
    allowed = {'query', 'cursor'} | ({'workspace_key', 'kind'} if resource else set())
    service, sid = await workspace(request, allowed_query=allowed)
    query, cursor = request.query_params.get('query', ''), request.query_params.get('cursor')
    workspace_key = request.query_params.get('workspace_key')
    kind = request.query_params.get('kind', 'SemanticModel')
    if (len(query) > 100 or cursor is not None and not 1 <= len(cursor) <= 100
            or resource and (workspace_key is None or not 1 <= len(workspace_key) <= 100)
            or kind not in {'SemanticModel', 'Report'}):
        raise HTTPException(422, 'invalid_cloud_request')
    return await safe_call(service.browse(sid, principal, workspace_key=workspace_key,
        kind=kind, query=query, cursor=cursor))


@router.get("/status")
async def status(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return public_workspace_status(request, service.status(sid, principal))


def public_workspace_status(request, value):
    """Every selection/state response retains the independent storage gate."""
    result = value.model_dump(mode='json') if hasattr(value, 'model_dump') else dict(value)
    readiness = getattr(request.app.state, 'persistence_readiness', None)
    if readiness is not None:
        result.update(readiness.public())
    return result


@router.post("/selection")
async def select(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    raw = await bounded_body(request, 1024)
    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs): raise ValueError()
        return result
    try:
        body = json.loads(raw, object_pairs_hook=unique_object)
        if (not isinstance(body, dict) or set(body) != {"key", "expected_generation"}
                or not isinstance(body["key"], str) or not 1 <= len(body["key"]) <= 200
                or type(body["expected_generation"]) is not int
                or not 0 <= body["expected_generation"] <= 2**53 - 1):
            raise ValueError()
    except (ValueError, UnicodeError): raise HTTPException(422, "invalid_cloud_request") from None
    return public_workspace_status(request, await safe_call(service.select_with_templates(
        sid, principal, body["key"], expected_generation=body["expected_generation"]), context='selection'))


@router.get("/llm-profiles")
async def llm_profiles(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    service.status(sid, principal)
    registry = request.app.state.cloud_llm_registry
    from backend.app.memory.models import RuntimeDataMode
    synthetic = service.data_mode(sid,principal)==RuntimeDataMode.MOCK
    keys = {'mock'} if synthetic else {'deepseek','kimi-k2.6'}
    return registry.public_catalog(default_profile_key='mock' if synthetic else request.app.state.settings.llm_default_profile,
                                   include_keys=keys)


@router.get("/report-templates")
async def templates(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return await safe_call(service.templates(sid, principal), context='template')


async def product(request):
    if request.method=='GET' and await bounded_body(request,0): raise HTTPException(422,'invalid_cloud_request')
    service=getattr(request.app.state,'cloud_product_services',None)
    if service is None: raise AuthFailure('AUTH_FORBIDDEN',403)
    readiness = getattr(request.app.state, 'persistence_readiness', None)
    if readiness is not None and not readiness.ready:
        from backend.app.persistence.readiness import PersistenceNotReady
        raise typed_product_failure(PersistenceNotReady(readiness),readiness.reason,'persistence')
    return service,request.cookies.get(request.app.state.settings.auth_cookie_name)


async def bounded_body(request, limit):
    raw=bytearray()
    try:
        async for chunk in request.stream():
            if len(raw)+len(chunk)>limit: raise HTTPException(422,'invalid_cloud_request')
            raw.extend(chunk)
    except ClientDisconnect:
        raise HTTPException(400,'invalid_cloud_request') from None
    return raw


async def body_as(request,model):
    from pydantic import ValidationError
    raw=await bounded_body(request,12000)
    def unique(pairs):
        value=dict(pairs)
        if len(value)!=len(pairs): raise ValueError()
        return value
    try: return model.model_validate(json.loads(raw,object_pairs_hook=unique))
    except (ValueError,UnicodeError,ValidationError): raise HTTPException(422,'invalid_cloud_request') from None


from pydantic import BaseModel,ConfigDict,Field


class GenerationRequest(BaseModel):
    expected_generation: int=Field(ge=0,le=2**53-1,strict=True)
    model_config=ConfigDict(extra='forbid')


class RestoreRequest(GenerationRequest):
    conversation_id: str=Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')


class ResourceLinkRequest(GenerationRequest):
    url: str=Field(min_length=1,max_length=2048)


@router.post('/selection/link')
async def open_resource_link(request:Request,principal=Depends(require_principal)):
    service,sid=await workspace(request)
    body=await body_as(request,ResourceLinkRequest)
    try:
        return public_workspace_status(request, await safe_call(service.open_resource_link(
            sid,principal,body.url,expected_generation=body.expected_generation), context='selection'))
    except ValueError: raise HTTPException(422,'unsupported_cloud_resource_link') from None


class CloudChatRequest(GenerationRequest):
    message: str=Field(min_length=1,max_length=2000)
    request_id: str=Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    llm_profile_key: str|None=Field(default=None,max_length=64,pattern=r'^[a-z0-9][a-z0-9._-]*$')
    report_template_key: str|None=Field(default=None,max_length=64,pattern=r'^[a-z0-9][a-z0-9._-]*$')
    # Presentation context only.  The current request selects the language of a
    # newly generated answer/presentation; it never becomes a semantic,
    # execution or ownership input.
    locale: str|None=Field(default=None,max_length=32)


@cloud_operation
async def product_call(operation, context='chat'):
    from backend.app.persistence.readiness import PersistenceNotReady
    from backend.app.presentation.projection import PresentationUnavailableError
    from backend.app.conversation.models import ConversationNotFoundError,ConversationHistoryCorruptionError
    from backend.app.report.resources import ReportNotFoundError,ReportStorageError
    from backend.app.application.conversation_history_service import InvalidConversationCursorError,InvalidConversationQueryError
    from backend.app.llm.base import LLMProviderError
    from backend.app.memory.request_fingerprint import IdempotencyConflictError
    try: return await safe_call(operation,context)
    except IdempotencyConflictError: raise HTTPException(409,'request_id_conflict') from None
    except PersistenceNotReady as error:
        raise typed_product_failure(error,error.readiness.reason,'persistence',context) from None
    except PresentationUnavailableError: raise HTTPException(404,'presentation_recipe_unavailable') from None
    except (ConversationNotFoundError,ReportNotFoundError): raise HTTPException(404,'resource_not_found') from None
    except (InvalidConversationCursorError,InvalidConversationQueryError): raise HTTPException(422,'invalid_cloud_query') from None
    except (ConversationHistoryCorruptionError,ReportStorageError) as error:
        raise typed_product_failure(error,'PERSISTENCE_UNAVAILABLE','persistence',context) from None
    except LLMProviderError as error:
        raise typed_product_failure(error,'LLM_SERVICE_UNAVAILABLE','llm',context) from None
    except (AuthFailure,HTTPException): raise
    except Exception as error:
        from sqlalchemy.exc import SQLAlchemyError
        code = 'PERSISTENCE_UNAVAILABLE' if isinstance(error,SQLAlchemyError) else 'INTERNAL_FAILURE'
        raise typed_product_failure(error,code,'persistence' if code=='PERSISTENCE_UNAVAILABLE' else 'internal',context) from None


def typed_product_failure(error,code,stage,context='chat'):
    if not hasattr(error,'cloud_stage'):
        error.cloud_stage, error.cloud_provider = stage, stage
    failure=map_public_failure(terminal_state='failed',stage=stage,error_type=code)
    trace_failure(context,error,failure,503)
    return HTTPException(503,{'failure':failure.model_dump(mode='json')})


def public_product(value):
    """Project route references at the API edge; stored artifacts stay frozen."""
    from urllib.parse import quote
    if hasattr(value,'model_dump'): value=value.model_dump(mode='json')
    if isinstance(value,list): return [public_product(item) for item in value]
    if not isinstance(value,dict): return value
    result={key:public_product(item) for key,item in value.items()}
    if result.get('report_id') and 'view_reference' in result:
        if result.get('availability_status')=='deleted':
            result.update(view_reference='',download_reference='')
            return result
        path='/api/v1/cloud/reports/'+quote(result['report_id'],safe='')
        result.update(view_reference=path,download_reference=path+'/download')
    return result


@router.post('/chat')
async def chat(request:Request,principal=Depends(require_principal)):
    from backend.app.api.schemas import ChatResponse
    from backend.app.presentation.locale import presentation_locale
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.core.turn_diagnostics import (
        TurnDiagnosticRecorder, bind_diagnostics, emit_diagnostic)
    if request.query_params: raise HTTPException(422,'invalid_cloud_request')
    body=await body_as(request,CloudChatRequest)
    service,sid=await product(request)
    mode=service._mode(sid,principal)
    recorder=TurnDiagnosticRecorder(
        request_id=body.request_id,
        runtime_build_id=runtime_build_identity().build_id,
        operation='chat',
        provider='mock' if mode==RuntimeDataMode.MOCK else 'fabric_iq',
        synthetic=mode==RuntimeDataMode.MOCK)
    try:
        with bind_diagnostics(recorder):
            with presentation_locale(body.locale):
                result=await product_call(service.chat(sid,principal,**body.model_dump(exclude={'locale'})))
    except HTTPException as error:
        emit_diagnostic(recorder.finalize(
            terminal_state='failed', **_failure_summary(error.detail)))
        raise
    except BaseException as error:
        recorder.fail(error)
        emit_diagnostic(recorder.finalize(terminal_state='failed'))
        raise
    # Existing factual presentation contract; never expose raw execution traces.
    usage=result.get('usage')
    data={k:result[k] for k in ChatResponse.model_fields if k in result}
    data['source_mode']=mode.value
    data['is_mock']=data['source_mode']=='mock'
    data['usage']=usage.to_dict() if hasattr(usage,'to_dict') else usage
    data['llm_mode']='mock' if data['is_mock'] else request.app.state.settings.llm_mode.value
    data['powerbi_mode']='mock' if data['source_mode']=='mock' else 'fabric_iq'
    data['execution_audit']=None
    emit_diagnostic(recorder.finalize(
        terminal_state=result.get('terminal_state'),
        conversation_id=result.get('conversation_id'),
        **_failure_summary(result.get('failure'))))
    return public_product(ChatResponse.model_validate(data))


def _failure_summary(failure) -> dict:
    """Bounded failure identity from a public failure payload or HTTP detail."""
    if isinstance(failure, dict) and isinstance(failure.get('failure'), dict):
        failure=failure['failure']
    if hasattr(failure,'model_dump'): failure=failure.model_dump(mode='json')
    if not isinstance(failure, dict): return {'failure_code':None,'failure_stage':None}
    return {'failure_code':failure.get('code'),'failure_stage':failure.get('stage')}


class PresentationRequest(GenerationRequest):
    locale: str=Field(max_length=32)


@router.post('/presentations/{request_id}')
async def presentation(request_id:str,request:Request,principal=Depends(require_principal)):
    if request.query_params or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',request_id):
        raise HTTPException(422,'invalid_cloud_request')
    body=await body_as(request,PresentationRequest)
    service,sid=await product(request)
    return public_product(await product_call(service.project_presentation(sid,principal,request_id,body.locale,body.expected_generation), context='presentation'))


@router.post('/new-chat')
async def new_chat(request:Request,principal=Depends(require_principal)):
    body=await body_as(request,GenerationRequest)
    ws,sid=await workspace(request)
    return public_workspace_status(request, await safe_call(ws.new_chat(sid,principal,body.expected_generation), context='chat'))


@router.post('/restore')
async def restore(request:Request,principal=Depends(require_principal)):
    if request.query_params: raise HTTPException(422,'invalid_cloud_request')
    body=await body_as(request,RestoreRequest)
    service,sid=await product(request)
    return public_workspace_status(request, await product_call(service.restore(
        sid,principal,body.conversation_id,body.expected_generation), context='history'))


def page_query(request,*,managed=False,search=False):
    allowed={'limit','cursor'} | ({'status'} if managed else set()) | ({'q'} if search else set())
    if set(request.query_params)-allowed or len(request.query_params.multi_items())!=len(request.query_params):
        raise HTTPException(422,'invalid_cloud_query')
    limit=request.query_params.get('limit','20')
    if not limit.isascii() or not limit.isdecimal() or len(limit)>2 or not 1<=int(limit)<=50:
        raise HTTPException(422,'invalid_cloud_query')
    cursor=request.query_params.get('cursor')
    if cursor is not None and not 1<=len(cursor)<=2200: raise HTTPException(422,'invalid_cloud_query')
    result={'limit':int(limit),'cursor':cursor}
    if managed:
        status=request.query_params.get('status','active')
        if status not in {'active','archived'}: raise HTTPException(422,'invalid_cloud_query')
        result['status']=status
    if search and 'q' in request.query_params:
        query=request.query_params['q'].strip()
        if not query or len(query)>200 or result['status']!='active':
            raise HTTPException(422,'invalid_cloud_query')
        result['query']=query
    return result


@router.get('/history')
async def history(request:Request,principal=Depends(require_principal)):
    service,sid=await product(request)
    return public_product(await product_call(service.list_history(sid,principal,**page_query(request,managed=True,search=True)), context='history'))


@router.get('/history/{conversation_id}')
async def history_detail(conversation_id:str,request:Request,principal=Depends(require_principal)):
    service,sid=await product(request)
    return public_product(await product_call(service.read_history(sid,principal,conversation_id,**page_query(request)), context='history'))


@router.get('/reports')
async def reports(request:Request,principal=Depends(require_principal)):
    service,sid=await product(request)
    return public_product(await product_call(service.list_reports(sid,principal,**page_query(request,managed=True)), context='report'))


class RenameResourceRequest(GenerationRequest):
    title: str=Field(min_length=1,max_length=120)


@router.post('/{kind}/{resource_id}/{action}')
@router.delete('/{kind}/{resource_id}')
async def mutate_resource(kind:str,resource_id:str,request:Request,action:str='delete',principal=Depends(require_principal)):
    if (kind not in {'history','reports'} or action not in {'rename','archive','unarchive','delete'}
            or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',resource_id) or request.query_params):
        raise HTTPException(422,'invalid_cloud_request')
    body=await body_as(request,RenameResourceRequest if action=='rename' else GenerationRequest)
    if action=='rename' and kind=='history' and len(body.title)>80:
        raise HTTPException(422,'invalid_cloud_request')
    service,sid=await product(request)
    result = public_product(await product_call(service.mutate_resource(sid,principal,kind,resource_id,action,**body.model_dump()), context='resource_mutation'))
    if 'workspace_status' in result:
        result['workspace_status'] = public_workspace_status(request, result['workspace_status'])
    return result


async def report_response(request,principal,report_id,download):
    from fastapi.responses import HTMLResponse
    if (set(request.query_params)-{'locale'} or len(request.query_params.multi_items())!=len(request.query_params)):
        raise HTTPException(422,'invalid_cloud_request')
    service,sid=await product(request)
    if 'locale' in request.query_params:
        html=await product_call(service.localized_report(sid,principal,report_id,request.query_params['locale']), context='report')
    else:
        artifact,html=await product_call(service.read_report(sid,principal,report_id), context='report')
    headers={'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox",'Cache-Control':'no-store'}
    if download: headers['Content-Disposition']='attachment; filename="report.html"'
    return HTMLResponse(html,headers=headers)


@router.get('/reports/{report_id}')
async def report_view(report_id:str,request:Request,principal=Depends(require_principal)):
    return await report_response(request,principal,report_id,False)


@router.get('/reports/{report_id}/download')
async def report_download(report_id:str,request:Request,principal=Depends(require_principal)):
    return await report_response(request,principal,report_id,True)
