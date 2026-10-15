"""Native Cloud storage composition; authorization precedes opening storage."""
from backend.app.auth.models import AuthFailure
from backend.app.config.settings import PersistenceBackend


def require_native_workspace(workspace):
    from backend.app.application.cloud_workspace_service import CloudWorkspaceService
    if not isinstance(workspace, CloudWorkspaceService):
        raise AuthFailure('AUTH_FORBIDDEN', 403)


def require_cloud_business_data(workspace,sid,principal):
    """Independent server-owned grants precede Core, Provider and storage."""
    require_native_workspace(workspace)
    workspace.require_disclosure(sid,principal)
    workspace.require_persistence(sid,principal)
    adapter, selection = workspace.selected_context(sid, principal)
    from types import SimpleNamespace
    ws, model = adapter.bound_resource_identity(selection.selected_model_key)
    workspace.require_persistence(sid, principal, binding=SimpleNamespace(workspace_id=ws, model_id=model))


class DeferredCloudRepositories:
    """Compose existing owner repositories lazily, without creating/migrating DBs.

    Startup and denied requests never open business persistence. Explicit
    operator grants and owner/exact-resource leases guard permitted access.
    """
    def __init__(self, auth, workspace, settings):
        self._auth, self._workspace, self._settings = auth, workspace, settings
        self._engine = self._repositories = None

    async def for_session(self, auth, sid, principal):
        require_native_workspace(self._workspace)
        self._workspace.require_persistence(sid, principal)
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
