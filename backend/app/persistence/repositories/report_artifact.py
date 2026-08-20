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

import asyncio
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.persistence.models import ReportArtifactModel
from backend.app.report.resources import (
    ReportArtifact,
    ReportArtifactMetadata,
    ReportNotFoundError,
    ReportStorageError,
    _build_metadata_json,
)


_REQUIRED_AUTHORITY_FIELDS = frozenset(
    {
        "report_id",
        "template_key",
        "semantic_model_key",
        "schema_fingerprint",
        "source_mode",
        "content_hash",
        "relative_path",
    }
)
_LINKAGE_FIELDS = ("conversation_id", "request_id")
_AUTHORITY_COLUMNS = (
    "report_id",
    "conversation_id",
    "request_id",
    "template_key",
    "semantic_model_key",
    "schema_fingerprint",
    "source_mode",
    "content_hash",
    "relative_path",
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

    async def save(
        self,
        artifact: ReportArtifact,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
        relative_path: str | None = None,
    ) -> None:
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
    *,
    conversation_id: str | None = None,
    request_id: str | None = None,
    relative_path: str | None = None,
) -> dict:
    """Convert a ReportArtifact to column values for ReportArtifactModel.

    M4.2.1: payload_json stores metadata-only ``ReportArtifactMetadata``
    (no HTML).  ``html`` is never written to the database.
    ``conversation_id`` and ``request_id`` are written as explicit columns
    and included in the metadata payload.
    """
    if conversation_id is None:
        conversation_id = artifact.conversation_id
    if request_id is None:
        request_id = artifact.request_id
    if relative_path is None:
        relative_path = f"{artifact.report_id}.html"
    payload_json = _build_metadata_json(
        artifact,
        relative_path,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    return {
        "report_id": artifact.report_id,
        "conversation_id": conversation_id,
        "request_id": request_id,
        "template_key": artifact.template_key,
        "semantic_model_key": artifact.semantic_model_key,
        "schema_fingerprint": artifact.schema_fingerprint,
        "source_mode": artifact.source_mode,
        "content_hash": artifact.content_hash,
        "relative_path": relative_path,
        "payload_json": payload_json,
    }


def _normalize_nullable_string(val: str | None) -> str | None:
    """Normalize legacy empty linkage columns to the nullable contract."""
    return val if val else None


def _validate_coherence(row: ReportArtifactModel, meta: dict) -> None:
    """Verify that DB columns and payload_json agree on critical fields.

    payload_json is the modern reconstruction authority.  Dedicated DB
    columns are immutable integrity witnesses: every authority field must be
    present in the payload and exactly match its column.  Nullable linkage
    may be absent only when its DB column is also null.

    Raises:
        ReportStorageError: on any mismatch.
    """
    missing = sorted(_REQUIRED_AUTHORITY_FIELDS.difference(meta))
    for field in _LINKAGE_FIELDS:
        row_value = _normalize_nullable_string(getattr(row, field))
        if row_value is not None and field not in meta:
            missing.append(field)
    if missing:
        raise ReportStorageError(
            f"Report metadata persistence contract missing fields for "
            f"{row.report_id}: {', '.join(sorted(set(missing)))}"
        )

    checks = [
        ("report_id", row.report_id, meta.get("report_id")),
        ("template_key", row.template_key, meta.get("template_key")),
        ("semantic_model_key", row.semantic_model_key, meta.get("semantic_model_key")),
        ("schema_fingerprint", row.schema_fingerprint, meta.get("schema_fingerprint")),
        ("source_mode", row.source_mode, meta.get("source_mode")),
        ("content_hash", row.content_hash, meta.get("content_hash")),
        ("relative_path", row.relative_path, meta.get("relative_path")),
        (
            "conversation_id",
            _normalize_nullable_string(row.conversation_id),
            meta.get("conversation_id"),
        ),
        (
            "request_id",
            _normalize_nullable_string(row.request_id),
            meta.get("request_id"),
        ),
    ]
    for field, row_val, payload_val in checks:
        if row_val != payload_val:
            raise ReportStorageError(
                f"Metadata coherence violation for {row.report_id}: "
                f"DB column {field}={row_val!r} != payload {field}={payload_val!r}"
            )


def _metadata_values_match(left: dict, right: dict) -> bool:
    """Return whether two complete metadata identities are semantically equal."""
    if any(left[field] != right[field] for field in _AUTHORITY_COLUMNS):
        return False
    try:
        return json.loads(left["payload_json"]) == json.loads(right["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return False


def _row_matches_values(row: ReportArtifactModel, values: dict) -> bool:
    """Compare a validated stored row with one candidate immutable identity."""
    _model_to_artifact(row)
    stored = {field: getattr(row, field) for field in _AUTHORITY_COLUMNS}
    stored["payload_json"] = row.payload_json
    return _metadata_values_match(stored, values)


def _model_to_artifact(row: ReportArtifactModel) -> ReportArtifact:
    """Reconstruct ReportArtifact from a row.

    The modern payload_json contract is required for full-fidelity recovery
    (contract version, provenance IDs, references, and timestamps).  Missing
    payload or required authority fields fails closed; no business-related
    defaults or column-derived recovery are allowed.

    M4.2.1: payload_json is metadata-only (ReportArtifactMetadata).
    Legacy payloads that contain ``html`` are rejected (fail-closed)
    to prevent the database from being treated as the HTML authority.

    M4.2.2: Before reconstruction the function validates that DB columns
    and payload_json agree on all critical fields.  Any mismatch raises
    ``ReportStorageError`` (fail-closed).

    Raises:
        ReportStorageError: corrupt stored data, legacy HTML, or coherence violation.
    """
    if not row.payload_json:
        raise ReportStorageError(
            f"Report metadata persistence contract missing payload for {row.report_id}"
        )
    try:
        meta_dict = json.loads(row.payload_json)
    except Exception as exc:
        raise ReportStorageError(
            f"Report metadata corrupt for {row.report_id}: {exc}"
        ) from exc
    if not isinstance(meta_dict, dict):
        raise ReportStorageError(
            f"Report metadata persistence contract invalid for {row.report_id}"
        )

    # M4.2.1: Reject legacy payloads that contain html
    if "html" in meta_dict and meta_dict.get("html"):
        raise ReportStorageError(
            f"Report metadata for {row.report_id} contains legacy HTML — "
            "database is not the HTML authority"
        )

    _validate_coherence(row, meta_dict)
    try:
        metadata = ReportArtifactMetadata.model_validate(meta_dict)
    except Exception as exc:
        raise ReportStorageError(
            f"Report metadata persistence contract invalid for {row.report_id}: {exc}"
        ) from exc

    try:
        return ReportArtifact(
            report_id=metadata.report_id,
            template_key=metadata.template_key,
            html="",
            source_mode=metadata.source_mode,
            generated_at=metadata.generated_at,
            contract_version=metadata.contract_version,
            semantic_model_key=metadata.semantic_model_key,
            schema_fingerprint=metadata.schema_fingerprint,
            verified_fact_set_ids=metadata.verified_fact_set_ids,
            query_result_ids=metadata.query_result_ids,
            content_type=metadata.content_type,
            content_hash=metadata.content_hash,
            created_at=metadata.created_at,
            view_reference=metadata.view_reference,
            download_reference=metadata.download_reference,
            relative_path=metadata.relative_path,
            conversation_id=metadata.conversation_id,
            request_id=metadata.request_id,
        )
    except Exception as exc:
        raise ReportStorageError(
            f"Report metadata reconstruction failed for {row.report_id}: {exc}"
        ) from exc


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

    async def save(
        self,
        artifact: ReportArtifact,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
        relative_path: str | None = None,
    ) -> None:
        """Insert immutable metadata or accept an identical idempotent save."""
        # M4.2.1: fall back to artifact fields if kwargs not provided
        if conversation_id is None and artifact.conversation_id:
            conversation_id = artifact.conversation_id
        if request_id is None and artifact.request_id:
            request_id = artifact.request_id
        values = _artifact_to_model_values(
            artifact,
            conversation_id=conversation_id,
            request_id=request_id,
            relative_path=relative_path,
        )
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(ReportArtifactModel).where(
                    ReportArtifactModel.report_id == artifact.report_id
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    if _row_matches_values(existing, values):
                        return
                    raise ReportStorageError("report_artifact_identity_collision")
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
        self._lock = asyncio.Lock()

    async def save(
        self,
        artifact: ReportArtifact,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
        relative_path: str | None = None,
    ) -> None:
        values = _artifact_to_model_values(
            artifact,
            conversation_id=conversation_id,
            request_id=request_id,
            relative_path=relative_path,
        )
        canonical = artifact.model_copy(
            update={
                "conversation_id": values["conversation_id"],
                "request_id": values["request_id"],
                "relative_path": values["relative_path"],
            }
        )
        async with self._lock:
            existing = self._items.get(artifact.report_id)
            if existing is not None:
                existing_values = _artifact_to_model_values(
                    existing,
                    conversation_id=existing.conversation_id,
                    request_id=existing.request_id,
                    relative_path=existing.relative_path,
                )
                if _metadata_values_match(existing_values, values):
                    return
                raise ReportStorageError("report_artifact_identity_collision")
            self._items[artifact.report_id] = canonical

    async def get(self, report_id: str) -> ReportArtifact:
        async with self._lock:
            artifact = self._items.get(report_id)
            if artifact is None:
                raise ReportNotFoundError("report_not_found")
            return artifact

    async def exists(self, report_id: str) -> bool:
        async with self._lock:
            return report_id in self._items

    async def _count(self) -> int:
        async with self._lock:
            return len(self._items)
