"""FastAPI dependency: immutable identity + fresh adapter + request teardown."""
from fastapi import Depends, Request

from backend.app.auth.dependencies import get_auth_service, require_principal
from backend.app.auth.models import AuthFailure


async def get_fabric_iq_adapter(request: Request, principal=Depends(require_principal)):
    auth = get_auth_service(request)
    factory = getattr(request.app.state, "fabric_iq_adapter_factory", None)
    if factory is None: raise AuthFailure("AUTH_FORBIDDEN", 403)
    adapter = factory.create(request.cookies.get(auth.settings.auth_cookie_name), principal)
    try:
        yield adapter
    finally:
        await adapter.aclose()
