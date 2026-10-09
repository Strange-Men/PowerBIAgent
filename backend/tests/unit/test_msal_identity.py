"""Offline Microsoft-library protocol tests; synthetic signed ID tokens only."""
import base64
import json
import logging
from time import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import jwt
import msal
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.auth.boundary import install_auth_log_redaction
from backend.app.auth.identity import DELEGATED_SCOPES, MsalIdentityClient
from backend.app.auth.models import PrincipalContext
from backend.app.config.settings import Settings

TENANT, CLIENT, OID = (str(UUID(int=i)) for i in (1, 2, 3))
AUTHORITY = f"https://login.microsoftonline.com/{TENANT}"


class Reply:
    status_code = 200
    headers = {"Content-Type": "application/json"}
    def __init__(self, body):
        self.body = body
        self.text = json.dumps(body)
    def json(self):
        return self.body


class FakeMicrosoftHTTP:
    def __init__(self, signing_key):
        self.signing_key = signing_key
        self.changes = {}
        self.nonce = None
        self.post_data = None
    def get(self, url, **kwargs):
        assert url == f"{AUTHORITY}/v2.0/.well-known/openid-configuration"
        return Reply({"authorization_endpoint": f"{AUTHORITY}/oauth2/v2.0/authorize",
                      "token_endpoint": f"{AUTHORITY}/oauth2/v2.0/token",
                      "issuer": f"{AUTHORITY}/v2.0"})
    def post(self, url, data, **kwargs):
        assert url == f"{AUTHORITY}/oauth2/v2.0/token"
        self.post_data = data
        now = int(time())
        claims = {"iss":f"{AUTHORITY}/v2.0", "aud":CLIENT, "sub":"synthetic-sub",
                  "oid":OID, "tid":TENANT, "exp":now + 600, "iat":now, "nbf":now,
                  "nonce":self.nonce, "name":"Synthetic User"} | self.changes
        encoded = jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid":"synthetic-key"})
        client_info = base64.urlsafe_b64encode(json.dumps({"uid":OID,"utid":TENANT}).encode()).decode().rstrip("=")
        return Reply({"token_type":"Bearer", "access_token":"synthetic-private-access",
                      "refresh_token":"synthetic-private-refresh", "id_token":encoded,
                      "scope":" ".join(DELEGATED_SCOPES), "expires_in":600, "client_info":client_info})


@pytest.fixture
def msal_flow(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = FakeMicrosoftHTTP(key)
    real_constructor = msal.ConfidentialClientApplication
    monkeypatch.setattr(msal, "ConfidentialClientApplication", lambda *a, **kw:
        real_constructor(*a, **kw, instance_discovery=False, http_client=http))
    config = Settings(_env_file=None, identity_mode="ENTRA_BFF", entra_tenant_id=TENANT,
        entra_client_id=CLIENT, entra_client_secret="NOT_A_REAL_SECRET_MSAL", auth_cookie_secure=False)
    identity = MsalIdentityClient(config)
    monkeypatch.setattr(identity._jwks, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=key.public_key()))
    flow, context = identity.initiate()
    http.nonce = parse_qs(urlsplit(flow["auth_uri"]).query)["nonce"][0]
    return identity, flow, context, http


def test_microsoft_flow_pkce_nonce_and_private_cache(msal_flow, caplog):
    identity, flow, context, http = msal_flow
    install_auth_log_redaction()
    caplog.set_level(logging.DEBUG)
    params = parse_qs(urlsplit(flow["auth_uri"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert flow["code_verifier"] not in flow["auth_uri"]
    result = identity.complete(flow, {"state":flow["state"], "code":"synthetic-code"}, context)
    assert result.claims["oid"] == OID
    assert http.post_data["code_verifier"] == flow["code_verifier"]
    assert http.post_data["client_secret"] == "NOT_A_REAL_SECRET_MSAL"
    assert context.account_id
    principal = PrincipalContext(tenant_id=TENANT, principal_id=OID,
        subject=result.claims["sub"], issuer=result.claims["iss"], display_name="Synthetic User",
        preferred_username=None, session_epoch=1, authorization_epoch=1)
    completed_exchange = http.post_data
    assert identity.delegated_token(context, principal, DELEGATED_SCOPES) == "synthetic-private-access"
    assert http.post_data is completed_exchange  # cache hit, no refresh exchange needed
    _, separate_context = identity.initiate()
    assert separate_context.cache is not context.cache
    assert not separate_context.client.get_accounts()
    identity.destroy(separate_context)
    assert "synthetic-private-access" not in caplog.text
    assert "synthetic-private-refresh" not in caplog.text
    assert "NOT_A_REAL_SECRET_MSAL" not in caplog.text
    identity.destroy(context)
    assert not context.cache._cache


@pytest.mark.parametrize("change", [{"nonce":"wrong-nonce"}, {"aud":"wrong-audience"},
    {"iss":"https://evil.invalid"}, {"exp":0}, {"nbf":9999999999}])
def test_supported_libraries_deny_nonce_and_claim_attacks(msal_flow, change):
    identity, flow, context, http = msal_flow
    http.changes = change
    with pytest.raises(Exception):
        identity.complete(flow, {"state":flow["state"], "code":"synthetic-code"}, context)
    identity.destroy(context)


def test_supported_library_rejects_bad_signature(msal_flow):
    identity, flow, context, http = msal_flow
    http.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidSignatureError):
        identity.complete(flow, {"state":flow["state"], "code":"synthetic-code"}, context)
    identity.destroy(context)


def test_supported_library_rejects_wrong_state_before_token_exchange(msal_flow):
    identity, flow, context, http = msal_flow
    with pytest.raises(ValueError):
        identity.complete(flow, {"state":"wrong-state", "code":"synthetic-code"}, context)
    assert http.post_data is None
    identity.destroy(context)
