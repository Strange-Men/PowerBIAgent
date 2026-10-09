"""Request-scoped principal from opaque server session only."""
from fastapi import Request

from backend.app.auth.models import AuthFailure, PrincipalContext
from backend.app.auth.service import AuthService


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise AuthFailure("AUTH_FORBIDDEN", 403)
    return service


def require_principal(request: Request) -> PrincipalContext:
    service = get_auth_service(request)
    return service.require_session(request.cookies.get(service.settings.auth_cookie_name)).principal


def get_optional_principal(request: Request) -> PrincipalContext | None:
    service = getattr(request.app.state, "auth_service", None)
    if not service:
        return None
    sid = request.cookies.get(service.settings.auth_cookie_name)
    if not sid:
        return None
    return service.require_session(sid).principal
