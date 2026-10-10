"""Principal report service: authenticated metadata before every file access."""
import json
from functools import wraps

from sqlalchemy import select

from backend.app.persistence.models import ConversationDeleteIntentModel, ReportDeleteIntentModel
from backend.app.report.resources import LocalReportRepository, ReportNotFoundError


def _authenticated(method):
    @wraps(method)
    async def guarded(self, *args, **kwargs):
        self._validate_owner()
        result = await method(self, *args, **kwargs)
        self._validate_owner()
        return result
    return guarded


class PrincipalReportRepository(LocalReportRepository):
    def __init__(self, root, metadata, owner_id, validate):
        super().__init__(root, metadata)
        self._owner_id, self._validate_owner = owner_id, validate

    async def _resolve_artifact(self, report_id):
        self._validate_owner()
        # Persistent metadata always wins, even if this request previously
        # cached an artifact that another request has since deleted/revoked.
        artifact = await self._metadata_repo.get(report_id)
        self._validate_owner()
        return artifact

    @_authenticated
    async def delete_html_files(self, report_ids):
        # Metadata has already been deleted; durable owner-scoped intents are
        # the authorization witness for crash recovery, never a file path.
        async with self._metadata_repo._session_factory() as session:
            rows = (await session.execute(select(ConversationDeleteIntentModel).where(
                ConversationDeleteIntentModel.owner_id == self._owner_id))).scalars().all()
            allowed = set()
            for row in rows:
                ids = json.loads(row.report_ids_json)
                if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
                    raise ReportNotFoundError("report_not_found")
                allowed.update(ids)
            pending = (await session.execute(select(ReportDeleteIntentModel.report_id).where(
                ReportDeleteIntentModel.owner_id == self._owner_id))).scalars().all()
            allowed.update(pending)
        if not set(report_ids).issubset(allowed):
            raise ReportNotFoundError("report_not_found")
        await super().delete_html_files(report_ids)

    store = _authenticated(LocalReportRepository.store)
    get = _authenticated(LocalReportRepository.get)
    read_html = _authenticated(LocalReportRepository.read_html)
    delete = _authenticated(LocalReportRepository.delete)
    rename = _authenticated(LocalReportRepository.rename)
    archive = _authenticated(LocalReportRepository.archive)
    restore = _authenticated(LocalReportRepository.restore)
    export_acceptance_copy = _authenticated(LocalReportRepository.export_acceptance_copy)
