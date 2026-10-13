"""Native composition must refuse before opening operator-owned storage."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.application.cloud_product_runtime import DeferredCloudRepositories
from backend.app.auth.models import AuthFailure
from backend.tests.api.test_auth_security import config


@pytest.mark.asyncio
async def test_deferred_repository_refuses_before_engine_or_owner_registration(monkeypatch):
    from backend.app.persistence import database
    engine = Mock(side_effect=AssertionError('business DB must not be opened'))
    monkeypatch.setattr(database,'create_engine',engine)
    def deny(*args): raise AuthFailure('AUTH_FORBIDDEN',403)
    repositories = DeferredCloudRepositories(object(),SimpleNamespace(require_business_access=deny),
        config(powerbi_mode='fabric_iq',persistence_backend='sqlite'))
    with pytest.raises(AuthFailure): await repositories.for_session(object(),'synthetic',object())
    assert repositories._engine is None and repositories._repositories is None
    engine.assert_not_called()
    await repositories.aclose()
