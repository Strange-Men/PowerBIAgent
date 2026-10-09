"""Microsoft protocol client; no OAuth/JWT crypto implemented by the app.

MSAL 1.38+ decodes ID claims without validating signature/lifetime. Therefore
PyJWT verifies RS256 signature, issuer, audience and required timestamps using
the configured tenant's Microsoft JWKS. MSAL owns state/nonce/PKCE and refresh.
"""
from dataclasses import dataclass
from typing import Protocol

import jwt
import msal

from backend.app.auth.models import AuthFailure, PrincipalContext
from backend.app.config.settings import Settings

POWERBI_RESOURCE = "https://analysis.windows.net/powerbi/api"
DELEGATED_SCOPES = tuple(f"{POWERBI_RESOURCE}/{name}" for name in (
    "Item.Read.All", "Item.Execute.All", "Dataset.Read.All",
))


@dataclass(repr=False)
class IdentityResult:
    claims: dict
    context: object


class IdentityClient(Protocol):
    def initiate(self) -> tuple[dict, object]: ...
    def complete(self, flow: dict, response: dict, context: object) -> IdentityResult: ...
    def delegated_token(self, context: object, principal: PrincipalContext, scopes: tuple[str, ...]) -> str: ...
    def destroy(self, context: object) -> None: ...


@dataclass(repr=False)
class MsalContext:
    client: msal.ConfidentialClientApplication
    cache: msal.SerializableTokenCache
    account_id: str | None = None


class MsalIdentityClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.authority = f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        self.issuer = f"{self.authority}/v2.0"
        self._jwks = jwt.PyJWKClient(f"{self.authority}/discovery/v2.0/keys", timeout=10)

    def initiate(self):
        cache = msal.SerializableTokenCache()
        client = msal.ConfidentialClientApplication(
            self.settings.entra_client_id,
            authority=self.authority,
            client_credential=self.settings.entra_client_secret.get_secret_value(),
            token_cache=cache, enable_pii_log=False, timeout=15,
        )
        context = MsalContext(client, cache)
        try:
            flow = client.initiate_auth_code_flow(
                scopes=list(DELEGATED_SCOPES), redirect_uri=self.settings.entra_redirect_uri,
                response_mode="query", prompt="select_account",
            )
            return flow, context
        except Exception:
            self.destroy(context)
            raise AuthFailure() from None

    def complete(self, flow, response, context):
        result = context.client.acquire_token_by_auth_code_flow(flow, response)
        if "access_token" not in result or "id_token" not in result:
            code = ("AUTH_CONSENT_REQUIRED" if result.get("error") in {
                "consent_required", "interaction_required"
            } or 65001 in result.get("error_codes", []) else "AUTH_REQUIRED")
            raise AuthFailure(code)
        token = result["id_token"]
        signing_key = self._jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, signing_key, algorithms=["RS256"],
            issuer=self.issuer, audience=self.settings.entra_client_id,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "nonce", "tid", "oid"]})
        accounts = [a for a in context.client.get_accounts()
                    if a.get("local_account_id") == claims.get("oid")
                    and a.get("realm") == claims.get("tid")]
        if len(accounts) != 1:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        context.account_id = accounts[0]["home_account_id"]
        return IdentityResult(claims, context)

    def delegated_token(self, context, principal, scopes):
        accounts = [a for a in context.client.get_accounts()
                    if a.get("home_account_id") == context.account_id
                    and a.get("local_account_id") == principal.principal_id
                    and a.get("realm") == principal.tenant_id]
        if len(accounts) != 1:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        result = context.client.acquire_token_silent_with_error(list(scopes), account=accounts[0])
        if not result or not result.get("access_token"):
            if result and result.get("error") in {"consent_required", "interaction_required"}:
                raise AuthFailure("AUTH_CONSENT_REQUIRED")
            raise AuthFailure("AUTH_EXPIRED")
        return result["access_token"]

    def destroy(self, context):
        if not isinstance(context, MsalContext):
            return
        for account in context.client.get_accounts():
            context.client.remove_account(account)
        # Purge all credentials, including pending/partially populated caches.
        context.cache.deserialize("{}")
        context.account_id = None
