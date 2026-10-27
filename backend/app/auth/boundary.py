"""Fail-closed stage gate and reusable unsafe-method CSRF policy."""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool

from backend.app.application.failure_contract import map_public_failure
from backend.app.auth.models import AuthFailure
from backend.app.config.settings import IdentityMode

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def failure_response(error: AuthFailure):
    failure = map_public_failure(terminal_state="auth_failed", stage="auth", error_type=error.code)
    if error.denial_reason:
        return JSONResponse(status_code=error.status, content={
            'failure': failure.model_dump(mode='json'), 'denial_reason': error.denial_reason,
        }, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    if error.status >= 500 or error.code == 'AUTH_FORBIDDEN':
        # A resource/coarse-route refusal does not prove identity invalidation.
        return JSONResponse(status_code=error.status, content={
            'failure': failure.model_dump(mode='json'),
        }, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    state = {"AUTH_REQUIRED": "SIGNED_OUT", "AUTH_EXPIRED": "SESSION_EXPIRED",
             "AUTH_FORBIDDEN": "AUTH_ERROR", "AUTH_CONSENT_REQUIRED": "CONSENT_REQUIRED"}[error.code]
    return JSONResponse(status_code=error.status, content={
        "identity_mode": "ENTRA_BFF", "authenticated": False,
        "state": state, "failure": failure.model_dump(mode="json"),
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class AuthBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = request.app.state.settings
        if settings.identity_mode != IdentityMode.ENTRA_BFF:
            response = await call_next(request)
            if request.url.path.startswith("/auth/"):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
            return response
        path = request.url.path
        service = request.app.state.auth_service
        try:
            # Applies to future protected routes too; callback is GET-only.
            if request.method in UNSAFE_METHODS:
                await run_in_threadpool(service.csrf, request.cookies.get(settings.auth_cookie_name),
                                        request.headers.get("origin"), request.headers.get("x-csrf-token"))
            if path == "/health":
                from backend.app.config.runtime_build import runtime_build_identity
                persistence = getattr(request.app.state, 'persistence_readiness', None)
                ready = persistence is None or persistence.ready
                payload = {"status": "ok" if ready else "not_ready", "identity_mode": "ENTRA_BFF",
                           "ready": ready, "configuration_ready": True,
                           "reasons": [] if ready else [persistence.reason.lower()],
                           **runtime_build_identity().public()}
                if persistence is not None:
                    payload.update(persistence.public())
                response = JSONResponse(payload, status_code=200 if ready else 503)
            elif path.startswith("/api/") or path in {"/api", "/docs", "/redoc", "/openapi.json"}:
                await run_in_threadpool(service.require_session, request.cookies.get(settings.auth_cookie_name))
                from backend.app.api.cloud_routes import CONTROL_PLANE_ROUTES, is_product_route
                if ((request.method, path) in CONTROL_PLANE_ROUTES
                        and getattr(request.app.state, "cloud_workspace_service", None) is not None):
                    response = await call_next(request)
                elif is_product_route(request.method,path) and getattr(request.app.state,'cloud_product_services',None) is not None:
                    response=await call_next(request)
                else:
                    raise AuthFailure("AUTH_FORBIDDEN", 403)
            else:
                response = await call_next(request)
                if path == "/auth/logout" and response.status_code == 200:
                    cloud = getattr(request.app.state, "cloud_workspace_service", None)
                    if cloud is not None: await cloud.prune()
        except AuthFailure as error:
            logging.getLogger(__name__).info('auth_boundary status=%d category=%s denial_reason=%s',
                error.status, error.code, error.denial_reason or 'none')
            response = failure_response(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


class AuthLogRedaction(logging.Filter):
    """Keep severity/category, drop protocol payloads and exception claims."""
    def filter(self, record):
        if record.name.startswith(("msal", "urllib3", "requests", "jwt")):
            record.msg = "Auth upstream event (sensitive details redacted)"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        elif record.name == "uvicorn.access":
            args = record.args
            if isinstance(args, tuple) and len(args) == 5:
                path = str(args[2]).split("?", 1)[0]
                if path.startswith('/api/'):
                    # Client-forged IDs and schema/member query strings must
                    # not become persistent access-log evidence.
                    path = '/api/[resource details redacted]'
                elif not path.startswith('/auth/'):
                    return True
                record.args = (args[0], args[1], path, args[3], args[4])
        return True


def install_auth_log_redaction():
    # Filter exact emitters as logger filters aren't inherited by children.
    for name in ("msal", "msal.application", "msal.authority", "msal.token_cache",
                 "msal.oauth2cli.oauth2", "msal.oauth2cli.oidc", "msal.oauth2cli.http",
                 "msal.telemetry", "msal.region", "urllib3.connectionpool", "requests", "jwt", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, AuthLogRedaction) for f in logger.filters):
            logger.addFilter(AuthLogRedaction())
