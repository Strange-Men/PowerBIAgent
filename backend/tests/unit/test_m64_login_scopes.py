"""Real MSAL authorization URL construction, with synthetic authority HTTP."""
from urllib.parse import parse_qs, urlsplit

from backend.app.auth.identity import CATALOG_SCOPES, DELEGATED_SCOPES
from backend.tests.unit.test_msal_identity import msal_flow  # noqa: F401


def test_cloud_login_adds_only_catalog_read_scope(msal_flow):
    identity,_,context,_ = msal_flow
    identity.settings = identity.settings.model_copy(update={"powerbi_mode":"fabric_iq"})
    flow,new_context = identity.initiate()
    scopes = set(parse_qs(urlsplit(flow["auth_uri"]).query)["scope"][0].split())
    assert scopes == set(DELEGATED_SCOPES + CATALOG_SCOPES) | {"openid","profile","offline_access"}
    identity.destroy(new_context)
    identity.destroy(context)
