"""Same-origin BFF endpoints; never send Microsoft credentials to the browser."""
from secrets import token_urlsafe
import json
from time import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend.app.auth.boundary import failure_response
from backend.app.auth.dependencies import get_auth_service
from backend.app.auth.models import AuthFailure, SessionDTO
from backend.app.config.settings import IdentityMode

router = APIRouter(prefix="/auth")
FLOW_COOKIE = "pbiagent_flow"
NOTICE_COOKIE = "pbiagent_notice"


def cookie(response, name, value, settings, ttl):
    response.set_cookie(name, value, max_age=ttl, httponly=True,
                        secure=settings.auth_cookie_secure, samesite="lax", path="/")


def clear_cookie(response, name, settings):
    response.delete_cookie(name, httponly=True, secure=settings.auth_cookie_secure, samesite="lax", path="/")


@router.get("/login")
def login(request: Request, return_to: str = "/"):
    service = get_auth_service(request)
    try:
        key, uri = service.start(return_to, request.cookies.get(FLOW_COOKIE))
    except AuthFailure:
        raise
    except Exception:
        raise AuthFailure() from None
    response = RedirectResponse(uri, status_code=302)
    cookie(response, FLOW_COOKIE, key, service.settings, service.settings.auth_flow_ttl)
    clear_cookie(response, NOTICE_COOKIE, service.settings)
    return response


@router.get("/callback")
def callback(request: Request):
    service = get_auth_service(request)
    settings = service.settings
    # Never persist code, claims or upstream error descriptions in browser URL.
    try:
        params = request.query_params
        if any(len(params.getlist(k)) != 1 for k in params):
            service.logout(request.cookies.get(settings.auth_cookie_name), request.cookies.get(FLOW_COOKIE))
            raise AuthFailure()
        session, target = service.complete(request.cookies.get(FLOW_COOKIE), dict(params),
                                           request.cookies.get(settings.auth_cookie_name))
        response = RedirectResponse(target, status_code=302)
        cookie(response, settings.auth_cookie_name, session.session_id, settings, settings.auth_session_ttl)
    except Exception as error:
        response = RedirectResponse("/", status_code=302)
        clear_cookie(response, settings.auth_cookie_name, settings)
        code = error.code if isinstance(error, AuthFailure) else "AUTH_REQUIRED"
        key = token_urlsafe(32)
        service.set_notice(key, code)
        cookie(response, NOTICE_COOKIE, key, settings, settings.auth_flow_ttl)
    clear_cookie(response, FLOW_COOKIE, settings)
    return response


@router.get("/session")
def session(request: Request):
    settings = request.app.state.settings
    if settings.identity_mode == IdentityMode.LOCAL_DEV:
        return SessionDTO(identity_mode="LOCAL_DEV", authenticated=False, state="LOCAL_DEV")
    service = get_auth_service(request)
    notice = service.take_notice(request.cookies.get(NOTICE_COOKIE))
    if notice:
        response = failure_response(AuthFailure(notice))
        if notice == "AUTH_REQUIRED":
            response = JSONResponse({**json.loads(response.body), "state": "AUTH_ERROR"}, status_code=401)
        clear_cookie(response, NOTICE_COOKIE, settings)
        return response
    record = service.require_session(request.cookies.get(settings.auth_cookie_name))
    return SessionDTO(identity_mode="ENTRA_BFF", authenticated=True,
        display_name=record.principal.display_name, preferred_username=record.principal.preferred_username,
        state="SIGNED_IN", csrf_token=record.csrf_token, expires_in=max(1, int(record.expires_at - time())))


@router.post("/logout")
def logout(request: Request):
    service = get_auth_service(request)
    service.logout(request.cookies.get(service.settings.auth_cookie_name), request.cookies.get(FLOW_COOKIE))
    response = JSONResponse({"authenticated": False, "state": "SIGNED_OUT"})
    for name in (service.settings.auth_cookie_name, FLOW_COOKIE, NOTICE_COOKIE):
        clear_cookie(response, name, service.settings)
    return response
