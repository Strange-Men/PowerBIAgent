"""Auth-derived repository composition. No identity enters the factual Core."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from secrets import token_bytes
from uuid import UUID

from sqlalchemy import event, inspect, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.app.auth.models import AuthFailure, PrincipalContext
from backend.app.persistence.models import LOCAL_OWNER_ID, OwnedRow, ResourceOwnerModel


@dataclass(frozen=True, repr=False)
class ResourceOwnerScope:
    tenant_id: str
    principal_id: str
    identity_mode: str
    authorization_epoch: int

    @classmethod
    def local(cls):
        return cls("local", "legacy", "LOCAL_DEV", 0)

    @classmethod
    def from_principal(cls, principal: PrincipalContext):
        # Caller must additionally validate this immutable projection against
        # AuthService.require_session. UUIDs/display claims are not credentials.
        if (principal.auth_source != "entra" or principal.authorization_epoch < 1
                or str(UUID(principal.tenant_id)) != principal.tenant_id
                or str(UUID(principal.principal_id)) != principal.principal_id):
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return cls(principal.tenant_id, principal.principal_id,
            "ENTRA_PRINCIPAL", principal.authorization_epoch)

    @property
    def owner_id(self):
        if self.identity_mode == "LOCAL_DEV":
            if (self.tenant_id, self.principal_id, self.authorization_epoch) != ("local", "legacy", 0):
                raise AuthFailure("AUTH_FORBIDDEN", 403)
            return LOCAL_OWNER_ID
        if self.identity_mode != "ENTRA_PRINCIPAL":
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        raw = json.dumps([self.tenant_id, self.principal_id], separators=(",", ":"))
        return "entra:" + sha256(raw.encode()).hexdigest()

    @property
    def transient_key(self):
        return f"{self.owner_id}:{self.authorization_epoch}"


def session_owner_id(session):
    return session.info.get("resource_owner_id", LOCAL_OWNER_ID)


def _validate_session(session):
    validate = session.info.get("resource_owner_validate")
    if validate:
        validate()


class _ScopedAsyncSession(AsyncSession):
    async def execute(self, *args, **kwargs):
        _validate_session(self)
        result = await super().execute(*args, **kwargs)
        _validate_session(self)
        return result


@event.listens_for(Session, "before_commit")
def _validate_commit(session):
    _validate_session(session)


@event.listens_for(Session, "before_flush")
def _guard_owned_writes(session, flush_context, instances):
    if "resource_owner_id" not in session.info:
        return
    _validate_session(session)
    owner_id = session_owner_id(session)
    for row in session.new | session.dirty | session.deleted:
        if isinstance(row, OwnedRow):
            if row in session.new and row.owner_id is None:
                row.owner_id = owner_id
            if row.owner_id != owner_id or (
                    row not in session.new and inspect(row).attrs.owner_id.history.has_changes()):
                raise AuthFailure("AUTH_FORBIDDEN", 403)


class _ScopedIdempotency:
    def __init__(self, tracker, scope, validate):
        self._tracker, self._scope, self._validate = tracker, scope, validate

    def _key(self, request_id):
        return json.dumps([self._scope.transient_key, request_id], separators=(",", ":"))

    async def claim(self, request_id, runtime_mode, fingerprint_hash):
        self._validate()
        result = await self._tracker.claim(self._key(request_id), runtime_mode, fingerprint_hash)
        try:
            self._validate()
        except AuthFailure:
            await self._tracker.abort(self._key(request_id), runtime_mode)
            raise
        return result

    async def complete(self, request_id, runtime_mode):
        # Cleanup must remain possible after logout/cancellation.
        await self._tracker.complete(self._key(request_id), runtime_mode)

    async def abort(self, request_id, runtime_mode):
        await self._tracker.abort(self._key(request_id), runtime_mode)


@dataclass(frozen=True)
class PrincipalRepositories:
    owner_scope: ResourceOwnerScope
    memory: object
    snapshots: object
    history: object
    report_metadata: object
    reports: object
    history_service: object


class PrincipalScopedRepositoryFactory:
    """App-owned factory; bundles are request/session scoped, never global users."""
    def __init__(self, session_factory, report_root):
        from backend.app.memory.result_snapshot import IdempotencyTracker
        self._sessions, self._root = session_factory, Path(report_root).resolve()
        self._in_flight = IdempotencyTracker()
        self._cursor_secret = token_bytes(32)

    async def for_session(self, auth, session_id, principal):
        def validate():
            if auth.require_session(session_id).principal != principal:
                raise AuthFailure("AUTH_FORBIDDEN", 403)
        validate()
        scope = ResourceOwnerScope.from_principal(principal)
        # Namespace registration never assigns legacy resources to a user.
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(insert(ResourceOwnerModel).values(
                    owner_id=scope.owner_id, identity_mode=scope.identity_mode,
                    tenant_id=scope.tenant_id, principal_id=scope.principal_id,
                ).on_conflict_do_nothing())
                row = (await session.execute(select(ResourceOwnerModel).where(
                    ResourceOwnerModel.owner_id == scope.owner_id))).scalar_one()
                if (row.identity_mode, row.tenant_id, row.principal_id) != (
                        scope.identity_mode, scope.tenant_id, scope.principal_id):
                    raise AuthFailure("AUTH_FORBIDDEN", 403)
                validate()
        sessions = async_sessionmaker(bind=self._sessions.kw["bind"],
            class_=_ScopedAsyncSession, expire_on_commit=False,
            info={"resource_owner_id": scope.owner_id, "resource_owner_validate": validate})
        from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
        from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
        from backend.app.persistence.repositories.conversation_history import SQLiteConversationHistoryRepository
        from backend.app.persistence.repositories.report_artifact import SQLiteReportArtifactRepository
        from backend.app.application.conversation_history_service import ConversationHistoryService
        from backend.app.persistence.scoped_reports import PrincipalReportRepository
        memory = SQLiteMemoryRepository(sessions, owner_id=scope.owner_id)
        snapshots = SQLiteSnapshotRepository(sessions, owner_id=scope.owner_id)
        snapshots._idempotency = _ScopedIdempotency(self._in_flight, scope, validate)
        history = SQLiteConversationHistoryRepository(sessions, owner_id=scope.owner_id)
        metadata = SQLiteReportArtifactRepository(sessions, owner_id=scope.owner_id)
        # Separate managed roots also protect crash cleanup and ID collisions.
        reports = PrincipalReportRepository(self._root / scope.owner_id.replace(":", "_"),
            metadata, scope.owner_id, validate)
        history_service = ConversationHistoryService(history, report_repository=reports,
            owner_scope_key=scope.transient_key, cursor_secret=self._cursor_secret)
        validate()
        return PrincipalRepositories(scope, memory, snapshots, history, metadata, reports, history_service)
