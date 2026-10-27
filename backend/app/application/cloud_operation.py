"""Ephemeral operation proofs and bounded diagnostics, never a permission cache."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from uuid import uuid4
import logging
import json


@dataclass(repr=False)
class VerifiedCloudOperation:
    request_id: str = field(default_factory=lambda: uuid4().hex)
    exact_access: set = field(default_factory=set)
    schemas: dict = field(default_factory=dict)
    active: bool = True


_current = ContextVar('verified_cloud_operation', default=None)


def current_operation():
    value = _current.get()
    return value if value is not None and value.active else None


@contextmanager
def operation_scope():
    existing = current_operation()
    if existing is not None:
        yield existing
        return
    value = VerifiedCloudOperation()
    token = _current.set(value)
    try:
        yield value
    finally:
        value.active = False
        value.exact_access.clear()
        value.schemas.clear()
        _current.reset(token)


def cloud_operation(method):
    @wraps(method)
    async def scoped(*args, **kwargs):
        with operation_scope():
            return await method(*args, **kwargs)
    return scoped


def cloud_stage(stage, provider):
    """Annotate origins using constants; never capture arguments or exception text."""
    def decorate(method):
        @wraps(method)
        async def traced(*args, **kwargs):
            try:
                return await method(*args, **kwargs)
            except Exception as error:
                origin=error
                for _ in range(8):
                    if hasattr(origin,'cloud_stage') or origin.__context__ is None: break
                    origin=origin.__context__
                if hasattr(origin,'cloud_stage'):
                    error.cloud_stage,error.cloud_provider=origin.cloud_stage,origin.cloud_provider
                else:
                    error.cloud_stage,error.cloud_provider=stage,provider
                if stage=='resource_verify' and error.cloud_stage=='catalog_rest':
                    error.cloud_stage,error.cloud_provider=stage,provider
                raise
        return traced
    return decorate


def trace_failure(operation, error, failure, status):
    # Both enum sets and public codes are server-owned. No identity, URLs,
    # messages, schemas, rows, prompt, exception repr or credentials are logged.
    allowed = {'catalog','selection','chat','template','history','report','resource_mutation','presentation'}
    origin = error
    for _ in range(8):
        if hasattr(origin, 'cloud_stage') or origin.__context__ is None: break
        origin = origin.__context__
    stage = getattr(origin,'cloud_stage','internal')
    provider = getattr(origin,'cloud_provider','internal')
    if stage not in {'catalog_rest','resource_verify','iq_resolve','iq_schema','iq_execute','llm','persistence','presentation','internal'}: stage='internal'
    if provider not in {'microsoft_rest','fabric_iq','llm','persistence','presentation','internal'}: provider='internal'
    scope = current_operation()
    exception_class = _root_exception_class(error)
    diagnostic={
        'request_id': scope.request_id if scope else uuid4().hex,
        'operation': operation if operation in allowed else 'resource_mutation',
        'stage': stage, 'failure_code': failure.code.value,
        'retryable': failure.retryable, 'provider': provider,
        'exception_class': exception_class,
        'http_status_category': f'{status // 100}xx'}
    _record_turn_diagnostic(error, failure_code=failure.code.value)
    logging.getLogger('powerbiagent.cloud').warning('cloud_failure %s',json.dumps(diagnostic,separators=(',',':')),
        extra={'cloud_failure':diagnostic})


def _root_exception_class(error: BaseException) -> str:
    """Deepest non-HTTP exception class in the chain; class name only."""
    from starlette.exceptions import HTTPException as StarletteHTTPException
    origin = error
    for _ in range(8):
        if origin.__context__ is None:
            break
        origin = origin.__context__
    if isinstance(origin, StarletteHTTPException) and not isinstance(error, StarletteHTTPException):
        return type(error).__name__
    return type(origin).__name__


def _record_turn_diagnostic(error: BaseException, *, failure_code: str) -> None:
    """Attach the exception class to an active FIRST-WRONG-LAYER recorder."""
    from backend.app.core.turn_diagnostics import current_diagnostics
    recorder = current_diagnostics()
    if recorder is None:
        return
    try:
        recorder.fail(error)
        if failure_code and recorder.failure_code is None:
            recorder.failure_code = failure_code
    except Exception:
        pass
