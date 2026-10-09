"""Bounded, process-local Auth stores; never SQLite/business persistence."""
from dataclasses import dataclass, field
from secrets import token_urlsafe
from threading import RLock
from time import time
from typing import Callable, Protocol

from backend.app.auth.models import AuthFailure, PrincipalContext


@dataclass(repr=False)
class AuthSession:
    session_id: str
    principal: PrincipalContext
    context: object
    expires_at: float
    csrf_token: str = field(default_factory=lambda: token_urlsafe(32))


class AuthSessionStore(Protocol):
    def create(self, principal: PrincipalContext, context: object, ttl: int) -> AuthSession: ...
    def lookup(self, session_id: str | None) -> tuple[AuthSession | None, bool]: ...
    def invalidate(self, session_id: str | None) -> None: ...
    def clear(self) -> None: ...


class AuthFlowStore(Protocol):
    def create(self, payload: dict, context: object, return_to: str, ttl: int) -> str: ...
    def consume(self, key: str | None) -> "AuthFlow | None": ...
    def discard(self, key: str | None) -> None: ...
    def clear(self) -> None: ...


class InMemoryAuthSessionStore:
    """Single-process development ONLY; destroy token state on expiry/logout."""
    def __init__(self, destroy: Callable, capacity: int = 1024):
        self._records: dict[str, AuthSession] = {}
        self._expired: dict[str, float] = {}
        self._lock = RLock()
        self._destroy = destroy
        self.capacity = capacity

    def _prune(self):
        now = time()
        for sid, record in list(self._records.items()):
            if record.expires_at <= now:
                self.invalidate(sid)
                self._expired[sid] = now + 600
        self._expired = {k: v for k, v in self._expired.items() if v > now}
        while len(self._expired) > self.capacity:
            self._expired.pop(next(iter(self._expired)))

    def create(self, principal, context, ttl):
        with self._lock:
            self._prune()
            if len(self._records) >= self.capacity:
                raise AuthFailure("AUTH_FORBIDDEN", 503)
            record = AuthSession(token_urlsafe(32), principal, context, time() + ttl)
            self._records[record.session_id] = record
            return record

    def peek(self, sid):
        with self._lock:
            return self._records.get(sid)

    def lookup(self, session_id):
        with self._lock:
            self._prune()
            return self._records.get(session_id), session_id in self._expired

    def prune(self):
        with self._lock:
            self._prune()

    def invalidate(self, session_id):
        with self._lock:
            record = self._records.pop(session_id, None)
            if record:
                self._destroy(record.context)
                record.principal = record.principal.model_copy(update={
                    "session_epoch": record.principal.session_epoch + 1,
                    "authorization_epoch": record.principal.authorization_epoch + 1,
                })
                record.context = None

    def clear(self):
        with self._lock:
            for sid in list(self._records):
                self.invalidate(sid)
            self._expired.clear()


@dataclass(repr=False)
class AuthFlow:
    payload: dict
    context: object
    return_to: str
    expires_at: float


class InMemoryAuthFlowStore:
    def __init__(self, destroy: Callable, capacity: int = 1024):
        self._records: dict[str, AuthFlow] = {}
        self._lock = RLock()
        self._destroy = destroy
        self.capacity = capacity

    def create(self, payload, context, return_to, ttl):
        with self._lock:
            for key, record in list(self._records.items()):
                if record.expires_at <= time():
                    self.discard(key)
            if len(self._records) >= self.capacity:
                raise AuthFailure("AUTH_FORBIDDEN", 503)
            key = token_urlsafe(32)
            self._records[key] = AuthFlow(payload, context, return_to, time() + ttl)
            return key

    def consume(self, key):
        with self._lock:
            return self._records.pop(key, None)

    def peek(self, key):
        with self._lock:
            return self._records.get(key)

    def discard(self, key):
        record = self.consume(key)
        if record:
            self._destroy(record.context)

    def clear(self):
        with self._lock:
            for key in list(self._records):
                self.discard(key)

    def prune(self):
        with self._lock:
            for key, record in list(self._records.items()):
                if record.expires_at <= time():
                    self.discard(key)
