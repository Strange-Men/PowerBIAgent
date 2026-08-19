"""SQLiteReportArtifactRepository — persistent report metadata backed by SQLite.

Report metadata (not HTML) is stored in the ``report_artifacts`` table.
The actual HTML content stays on the filesystem at
``local_state/reports/<report_id>.html`` — only the metadata path points
to it.

Design notes
============
*   ``save()`` persists ReportArtifact metadata — HTML is written separately
    by the caller (``LocalReportRepository``).
*   ``get()`` reconstructs a ``ReportArtifact`` from the DB row.
*   ``exists()`` checks DB presence without deserializing the payload.
*   Mock / Real isolation: ``report_artifacts`` tracks ``source_mode`` in a
    dedicated column; namespace isolation is maintained by the application
    layer (mock vs real conversation IDs are already scoped per runtime mode).
*   No HTML blob is stored in the database — only the ``relative_path``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.persistence.models import ReportArtifactModel
from backend.app.persistence.serialization import domain_to_json, json_to_domain
from backend.app.report.resources import (
    ReportArtifact,
    ReportNotFoundError,
    ReportStorageError,
)


# ---------------------------------------------------------------------------
# Abstract report metadata repository
# ---------------------------------------------------------------------------


class ReportArtifactRepository:
    """Repository boundary for report metadata.

    The concrete implementation (SQLite, in-memory) is injected at wiring
    time.  ``LocalReportRepository`` depends on this for metadata
    persistence and recovery.
    """

    async def save(self, artifact: ReportArtifact) -> None:
        """Persist report metadata."""
        raise NotImplementedError

    async def get(self, report_id: str) -> ReportArtifact:
        """Retrieve report metadata by report_id.

        Raises:
            ReportNotFoundError: no metadata for this report_id.
            ReportStorageError: corrupt stored data.
        """
        raise NotImplementedError

    async def exists(self, report_id: str) -> bool:
        """Check whether metadata exists for this report_id."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------


def _artifact_to_model_values(
    artifact: ReportArtifact,
) -> dict:
    """Convert a ReportArtifact to column values for ReportArtifactModel.

    ``conversation_id`` and ``request_id`` are nullable columns available
    for future conversation-scoped report lookup (M4.3).  The domain model
    does not yet carry them — they are stored as ``None``.
    """
    return {
        "report_id": artifact.report_id,
        "conversation_id": None,
        "request_id": None,
        "template_key": artifact.template_key,
        "semantic_model_key": artifact.semantic_model_key,
        "schema_fingerprint": artifact.schema_fingerprint,
        "source_mode": artifact.source_mode,
        "content_hash": artifact.content_hash,
        "relative_path": f"local_state/reports/{artifact.report_id}.html",
        "payload_json": domain_to_json(artifact),
    }


def _model_to_artifact(row: ReportArtifactModel) -> ReportArtifact:
    """Reconstruct ReportArtifact from a row.

    Prefers the payload_json for full fidelity (includes fields like
    contract_version, verified_fact_set_ids, query_result_ids etc.).
    Falls back to reconstructing from columns if payload is missing.

    Raises:
        ReportStorageError: if the stored JSON is corrupt.
    """
    if row.payload_json:
        try:
            return json_to_domain(ReportArtifact, row.payload_json)
        except Exception as exc:
            raise ReportStorageError(
                f"Report metadata corrupt for {row.report_id}: {exc}"
            ) from exc
    # Fallback — minimal reconstruction from columns
    # (payload_json should always exist for modern artifacts)
    return ReportArtifact(
        report_id=row.report_id,
        template_key=row.template_key,
        html="",
        source_mode=row.source_mode,
        generated_at=row.created_at,
        content_type="text/html; charset=utf-8",
        content_hash=row.content_hash,
        created_at=row.created_at,
        view_reference=f"/api/reports/{row.report_id}",
        download_reference=f"/api/reports/{row.report_id}/download",
    )


class SQLiteReportArtifactRepository(ReportArtifactRepository):
    """Report metadata repository backed by SQLite.

    Uses the same session_factory as the other SQLite repositories.
    No separate engine or connection pool.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def save(self, artifact: ReportArtifact) -> None:
        """Insert or update report metadata in the report_artifacts table."""
        values = _artifact_to_model_values(artifact)
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(ReportArtifactModel).where(
                    ReportArtifactModel.report_id == artifact.report_id
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    # Update all mutable columns
                    existing.conversation_id = values["conversation_id"]
                    existing.request_id = values["request_id"]
                    existing.template_key = values["template_key"]
                    existing.semantic_model_key = values["semantic_model_key"]
                    existing.schema_fingerprint = values["schema_fingerprint"]
                    existing.source_mode = values["source_mode"]
                    existing.content_hash = values["content_hash"]
                    existing.relative_path = values["relative_path"]
                    existing.payload_json = values["payload_json"]
                else:
                    model = ReportArtifactModel(**values)
                    session.add(model)
                await session.flush()

    async def get(self, report_id: str) -> ReportArtifact:
        """Retrieve report metadata by report_id.

        Raises:
            ReportNotFoundError: no metadata found.
            ReportStorageError: corrupt payload in DB.
        """
        async with self._session_factory() as session:
            stmt = select(ReportArtifactModel).where(
                ReportArtifactModel.report_id == report_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                raise ReportNotFoundError("report_not_found")
            return _model_to_artifact(row)

    async def exists(self, report_id: str) -> bool:
        """Quick existence check via primary key lookup."""
        async with self._session_factory() as session:
            stmt = select(ReportArtifactModel.report_id).where(
                ReportArtifactModel.report_id == report_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Test introspection
    # ------------------------------------------------------------------

    async def _count(self) -> int:
        """Return total rows in report_artifacts (for test introspection)."""
        async with self._session_factory() as session:
            from sqlalchemy import func as sa_func, select as sa_select

            stmt = sa_select(sa_func.count(ReportArtifactModel.report_id))
            result = await session.execute(stmt)
            return result.scalar() or 0


# ---------------------------------------------------------------------------
# In-memory implementation (compatibility / memory backend)
# ---------------------------------------------------------------------------


class InMemoryReportArtifactRepository(ReportArtifactRepository):
    """In-memory report metadata store for memory-backend mode.

    Used when ``persistence_backend=memory`` — keeps existing behaviour
    while providing the same interface as the SQLite variant.
    """

    def __init__(self) -> None:
        self._items: dict[str, ReportArtifact] = {}

    async def save(self, artifact: ReportArtifact) -> None:
        self._items[artifact.report_id] = artifact

    async def get(self, report_id: str) -> ReportArtifact:
        artifact = self._items.get(report_id)
        if artifact is None:
            raise ReportNotFoundError("report_not_found")
        return artifact

    async def exists(self, report_id: str) -> bool:
        return report_id in self._items

    async def _count(self) -> int:
        return len(self._items)