"""Native Cloud storage composition; authorization precedes opening storage."""
from backend.app.auth.models import AuthFailure
from backend.app.config.settings import PersistenceBackend


class DeferredCloudRepositories:
    """Compose existing owner repositories lazily, without creating/migrating DBs.

    Native execution is currently unavailable. Neither startup, blocked HTTP,
    nor direct service preparation may touch enterprise business persistence.
    Future readiness must first be proven by the workspace authority.
    """
    def __init__(self, auth, workspace, settings):
        self._auth, self._workspace, self._settings = auth, workspace, settings
        self._engine = self._repositories = None

    async def for_session(self, auth, sid, principal):
        self._workspace.require_business_access(sid, principal)
        if self._settings.persistence_backend != PersistenceBackend.SQLITE:
            raise AuthFailure('AUTH_FORBIDDEN',403)
        # No schema creation, migration, legacy assignment or default fallback.
        if self._repositories is None:
            from backend.app.persistence.database import create_engine, create_session_factory
            from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory
            self._engine = create_engine(self._settings, echo=False)
            self._repositories = PrincipalScopedRepositoryFactory(
                create_session_factory(self._engine), self._settings.report_artifacts_path)
        return await self._repositories.for_session(auth, sid, principal)

    async def aclose(self):
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = self._repositories = None
