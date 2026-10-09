"""Auth boundary; opaque sessions bind validated principal and private cache."""
from secrets import compare_digest
from threading import RLock
from time import time
from uuid import UUID

from backend.app.auth.identity import DELEGATED_SCOPES, IdentityClient
from backend.app.auth.models import AuthFailure, PrincipalContext
from backend.app.auth.stores import InMemoryAuthFlowStore, InMemoryAuthSessionStore
from backend.app.config.settings import Settings


class AuthService:
    def __init__(self, settings: Settings, identity: IdentityClient):
        self.settings = settings
        self.identity = identity
        self.sessions = InMemoryAuthSessionStore(identity.destroy, settings.auth_store_capacity)
        self.flows = InMemoryAuthFlowStore(identity.destroy, settings.auth_store_capacity)
        # Development serialization also makes logout/cache acquisition atomic.
        self._lock = RLock()
        self._epoch = 0
        self._notices = {}

    def set_notice(self, key, code):
        with self._lock:
            self._notices = {k: v for k, v in self._notices.items() if v[1] > time()}
            if len(self._notices) >= self.settings.auth_store_capacity:
                self._notices.pop(next(iter(self._notices)))
            self._notices[key] = (code, time() + self.settings.auth_flow_ttl)

    def take_notice(self, key):
        with self._lock:
            value = self._notices.pop(key, None)
            return value[0] if value and value[1] > time() else None

    def start(self, return_to: str, old_flow: str | None):
        if return_to != "/":
            raise AuthFailure("AUTH_FORBIDDEN", 400)
        with self._lock:
            self.flows.discard(old_flow)
            payload, context = self.identity.initiate()
            if not all(payload.get(k) for k in ("state", "nonce", "code_verifier", "auth_uri")):
                self.identity.destroy(context)
                raise AuthFailure()
            try:
                key = self.flows.create(payload, context, return_to, self.settings.auth_flow_ttl)
            except Exception:
                self.identity.destroy(context)
                raise
            return key, payload["auth_uri"]

    def complete(self, correlation: str | None, response: dict, old_session: str | None):
        with self._lock:
            flow = self.flows.consume(correlation)
            # Clear old identity even when a subsequent callback fails.
            self.sessions.invalidate(old_session)
            if not flow:
                raise AuthFailure()
            try:
                if flow.expires_at <= time() or not all(flow.payload.get(k) for k in ("state", "nonce", "code_verifier")):
                    raise AuthFailure()
                if not compare_digest(str(response.get("state", "")), flow.payload["state"]):
                    raise AuthFailure()
                result = self.identity.complete(flow.payload, response, flow.context)
                claims = result.claims
                expected_issuer = f"https://login.microsoftonline.com/{self.settings.entra_tenant_id}/v2.0"
                if (claims.get("tid") != self.settings.entra_tenant_id or claims.get("iss") != expected_issuer
                        or claims.get("aud") != self.settings.entra_client_id
                        or not claims.get("sub") or float(claims.get("exp", 0)) <= time()
                        or float(claims.get("nbf", 0)) > time()
                        or str(UUID(claims.get("oid", ""))) != claims.get("oid")):
                    raise AuthFailure("AUTH_FORBIDDEN", 403)
                self._epoch += 1
                def display(value):
                    return "".join(c for c in str(value or "") if c.isprintable())[:160]
                principal = PrincipalContext(tenant_id=claims["tid"], principal_id=claims["oid"],
                    subject=claims["sub"], issuer=claims["iss"],
                    display_name=display(claims.get("name")) or "Microsoft 用户",
                    preferred_username=display(claims.get("preferred_username")) or None,
                    session_epoch=self._epoch, authorization_epoch=self._epoch)
                session = self.sessions.create(principal, result.context, self.settings.auth_session_ttl)
                return session, flow.return_to
            except Exception:
                self.identity.destroy(flow.context)
                raise
            finally:
                flow.payload.clear()

    def require_session(self, sid):
        with self._lock:
            record, expired = self.sessions.lookup(sid)
            if not record:
                raise AuthFailure("AUTH_EXPIRED" if expired else "AUTH_REQUIRED")
            if record.principal.tenant_id != self.settings.entra_tenant_id:
                self.sessions.invalidate(sid)
                raise AuthFailure("AUTH_FORBIDDEN", 403)
            return record

    def csrf(self, sid, origin, token):
        record = self.require_session(sid)
        if origin != self.settings.auth_allowed_origin or not token or not compare_digest(token, record.csrf_token):
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return record

    def logout(self, sid, flow):
        with self._lock:
            self.sessions.invalidate(sid)
            self.flows.discard(flow)
            self._epoch += 1

    def get_delegated_token(self, sid, principal, scopes=DELEGATED_SCOPES):
        with self._lock:
            record = self.require_session(sid)
            if record.principal != principal or tuple(scopes) != DELEGATED_SCOPES:
                raise AuthFailure("AUTH_FORBIDDEN", 403)
            try:
                return self.identity.delegated_token(record.context, principal, DELEGATED_SCOPES)
            except AuthFailure:
                self.sessions.invalidate(sid)
                raise
            except Exception:
                self.sessions.invalidate(sid)
                raise AuthFailure("AUTH_EXPIRED") from None

    def close(self):
        with self._lock:
            self.flows.clear()
            self.sessions.clear()
            self._notices.clear()

    def prune(self):
        with self._lock:
            self.sessions.prune()
            self.flows.prune()
            self._notices = {k: v for k, v in self._notices.items() if v[1] > time()}
