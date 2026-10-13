"""Authenticated Cloud metadata and model selection; no factual execution routes."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.auth.dependencies import require_principal
from backend.app.auth.models import AuthFailure
from backend.app.application.failure_contract import map_public_failure
from backend.app.application.cloud_workspace_service import CloudSelectionConflict
from backend.app.harness.errors import ToolExecutionError, ToolTimeoutError
from backend.app.powerbi.base import PowerBIAdapterError

CONTROL_PLANE_ROUTES = frozenset({
    ("GET", "/api/v1/cloud/catalog"), ("GET", "/api/v1/cloud/status"),
    ("POST", "/api/v1/cloud/selection"), ("GET", "/api/v1/cloud/llm-profiles"),
    ("GET", "/api/v1/cloud/report-templates"),
})
router = APIRouter(prefix="/api/v1/cloud")


async def workspace(request: Request):
    service = getattr(request.app.state, "cloud_workspace_service", None)
    if service is None: raise AuthFailure("AUTH_FORBIDDEN", 403)
    if request.query_params: raise HTTPException(422, "invalid_cloud_request")
    if request.method == "GET" and await request.body(): raise HTTPException(422, "invalid_cloud_request")
    return service, request.cookies.get(request.app.state.settings.auth_cookie_name)


async def safe_call(operation):
    try: return await operation
    except CloudSelectionConflict:
        raise HTTPException(409, "cloud_selection_changed") from None
    except (PowerBIAdapterError, ToolExecutionError, ToolTimeoutError) as error:
        cause = error.__context__ if isinstance(error, ToolExecutionError) else error
        if isinstance(cause, AuthFailure): raise cause
        code = getattr(cause, "error_type", "UPSTREAM_UNAVAILABLE")
        failure = map_public_failure(terminal_state="tool_failed", stage="tool_execution", error_type=code)
        raise HTTPException(503, {"failure": failure.model_dump(mode="json")}) from None


@router.get("/catalog")
async def catalog(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return await safe_call(service.catalog(sid, principal))


@router.get("/status")
async def status(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return service.status(sid, principal)


@router.post("/selection")
async def select(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 1024: raise HTTPException(422, "invalid_cloud_request")
        raw.extend(chunk)
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
    return await safe_call(service.select(sid, principal, body["key"], expected_generation=body["expected_generation"]))


@router.get("/llm-profiles")
async def llm_profiles(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    service.status(sid, principal)
    registry = request.app.state.cloud_llm_registry
    return registry.public_catalog(default_profile_key=request.app.state.settings.llm_default_profile,
                                   include_keys={"deepseek", "kimi-k2.6"})


@router.get("/report-templates")
async def templates(request: Request, principal=Depends(require_principal)):
    service, sid = await workspace(request)
    return await safe_call(service.templates(sid, principal))
