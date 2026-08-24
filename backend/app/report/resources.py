"""M3 report artifact contract and repository implementations."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.persistence.serialization import domain_to_json
from backend.app.schemas.data_contracts import RenderedReport, ReportSpec

if TYPE_CHECKING:
    from backend.app.persistence.repositories.report_artifact import (
        ReportArtifactRepository,
    )


REPORT_CONTENT_TYPE = "text/html; charset=utf-8"
_REPORT_ID_PATTERN = re.compile(r"^rpt_[0-9a-f]{32}$")


class ReportResourceError(RuntimeError):
    pass


class ReportNotFoundError(ReportResourceError):
    pass


class ReportStorageError(ReportResourceError):
    pass


class ReportDeleteResult(BaseModel):
    report_id: str
    source_mode: Literal["mock", "real"]
    conversation_id: str | None = None
    request_id: str | None = None
    deleted: bool = True

    model_config = ConfigDict(frozen=True)


class ReportRenameRequest(BaseModel):
    display_title: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")

    @field_validator("display_title")
    @classmethod
    def validate_display_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("invalid_report_display_title")
        return normalized


class ReportRenameResult(BaseModel):
    report_id: str
    display_title: str
    availability_status: Literal["available"] = "available"

    model_config = ConfigDict(frozen=True)


class ReportArtifact(RenderedReport):
    """Metadata and exact compatibility copy for one managed HTML artifact."""

    source_mode: Literal["mock", "real"] = "mock"
    contract_version: str = ""
    semantic_model_key: str = ""
    schema_fingerprint: str = ""
    verified_fact_set_ids: list[str] = Field(default_factory=list)
    query_result_ids: list[str] = Field(default_factory=list)
    content_type: str = REPORT_CONTENT_TYPE
    content_hash: str = Field(..., min_length=64, max_length=64)
    created_at: datetime
    view_reference: str
    download_reference: str
    relative_path: str = ""
    conversation_id: str | None = None
    request_id: str | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_sales_artifact(self) -> "ReportArtifact":
        if not _REPORT_ID_PATTERN.fullmatch(self.report_id):
            raise ValueError("report_artifact_id_invalid")
        if self.content_type != REPORT_CONTENT_TYPE:
            raise ValueError("report_artifact_content_type_invalid")
        if self.template_key == "sales_report" and (
            not self.contract_version
            or not self.semantic_model_key
            or len(self.schema_fingerprint) != 64
            or not self.verified_fact_set_ids
            or not self.query_result_ids
            or len(self.verified_fact_set_ids)
            != len(set(self.verified_fact_set_ids))
            or len(self.query_result_ids) != len(set(self.query_result_ids))
            or len(self.verified_fact_set_ids) != len(self.query_result_ids)
        ):
            raise ValueError("sales_report_artifact_provenance_incomplete")
        expected_view = f"/api/reports/{self.report_id}"
        if (
            self.view_reference != expected_view
            or self.download_reference != f"{expected_view}/download"
        ):
            raise ValueError("report_artifact_reference_invalid")
        return self


# ---------------------------------------------------------------------------
# M4.2.1: Metadata-only DTO — payload_json stores only this, never HTML
# ---------------------------------------------------------------------------


class ReportArtifactMetadata(BaseModel):
    """Metadata-only serialization contract for report_artifacts.payload_json.

    Must NEVER contain ``html``.  HTML lives exclusively on the filesystem.
    """

    report_id: str
    template_key: str
    source_mode: Literal["mock", "real"]
    generated_at: str
    contract_version: str = ""
    semantic_model_key: str
    schema_fingerprint: str
    verified_fact_set_ids: list[str] = Field(default_factory=list)
    query_result_ids: list[str] = Field(default_factory=list)
    content_type: str = REPORT_CONTENT_TYPE
    content_hash: str
    created_at: str
    view_reference: str
    download_reference: str
    relative_path: str
    conversation_id: str | None = None
    request_id: str | None = None

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_domain(
        cls,
        artifact: ReportArtifact,
        relative_path: str,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> "ReportArtifactMetadata":
        """Build metadata from a full ReportArtifact + explicit fields."""
        return cls(
            report_id=artifact.report_id,
            template_key=artifact.template_key,
            source_mode=artifact.source_mode,
            generated_at=(
                artifact.generated_at.isoformat()
                if hasattr(artifact.generated_at, "isoformat")
                else str(artifact.generated_at)
            ),
            contract_version=artifact.contract_version,
            semantic_model_key=artifact.semantic_model_key,
            schema_fingerprint=artifact.schema_fingerprint,
            verified_fact_set_ids=list(artifact.verified_fact_set_ids),
            query_result_ids=list(artifact.query_result_ids),
            content_type=artifact.content_type,
            content_hash=artifact.content_hash,
            created_at=(
                artifact.created_at.isoformat()
                if hasattr(artifact.created_at, "isoformat")
                else str(artifact.created_at)
            ),
            view_reference=artifact.view_reference,
            download_reference=artifact.download_reference,
            relative_path=relative_path,
            conversation_id=conversation_id,
            request_id=request_id,
        )


class ReportRepository(ABC):
    """Repository-owned report IDs are the only route to stored artifacts."""

    @abstractmethod
    async def store(
        self,
        report: ReportSpec,
        html: str,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> ReportArtifact:
        ...

    @abstractmethod
    async def get(self, report_id: str) -> ReportArtifact:
        ...

    @abstractmethod
    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        ...

    @abstractmethod
    async def delete(self, report_id: str) -> ReportDeleteResult:
        """Delete one report resource; this is never an Agent tool."""
        ...

    @abstractmethod
    async def rename(self, report_id: str, display_title: str) -> ReportRenameResult:
        """Rename presentation metadata only; factual artifact bytes stay immutable."""
        ...

    async def delete_html_files(self, report_ids: list[str]) -> None:
        """Delete repository-owned HTML bytes after metadata cascade.

        Conversation deletion is an M4 persistence workflow.  Implementations
        must keep path ownership inside the report repository; callers never
        receive or unlink arbitrary filesystem paths.
        """
        raise NotImplementedError


def _validate_report_id(report_id: str) -> None:
    if not _REPORT_ID_PATTERN.fullmatch(report_id):
        raise ReportNotFoundError("report_not_found")


def _normalize_display_title(display_title: str) -> str:
    if not isinstance(display_title, str):
        raise ReportStorageError("invalid_report_display_title")
    normalized = display_title.strip()
    if not normalized or len(normalized) > 120:
        raise ReportStorageError("invalid_report_display_title")
    return normalized


def _validated_html_bytes(html: str) -> bytes:
    if not isinstance(html, str) or not html:
        raise ReportStorageError("report_html_empty")
    lowered = html.casefold()
    if (
        not html.startswith("<!DOCTYPE html>")
        or "</html>" not in lowered
        or "<script" in lowered
        or "javascript:" in lowered
        or "http://" in lowered
        or "https://" in lowered
        or "<link" in lowered
        or "<iframe" in lowered
        or "<object" in lowered
        or "<embed" in lowered
        or "@import" in lowered
        or "url(" in lowered
        or "src=" in lowered
    ):
        raise ReportStorageError("report_html_unsafe_or_incomplete")
    return html.encode("utf-8")


def _build_artifact(
    report: ReportSpec,
    html: str,
    content: bytes,
    report_id: str,
    *,
    conversation_id: str | None = None,
    request_id: str | None = None,
) -> ReportArtifact:
    created_at = datetime.now(timezone.utc)
    view_reference = f"/api/reports/{report_id}"
    return ReportArtifact(
        report_id=report_id,
        template_key=report.template_key,
        html=html,
        source_mode=report.source_mode,
        generated_at=created_at,
        contract_version=report.contract_version,
        semantic_model_key=report.semantic_model_key,
        schema_fingerprint=report.schema_fingerprint,
        verified_fact_set_ids=list(report.verified_fact_set_ids),
        query_result_ids=list(report.query_result_ids),
        content_type=REPORT_CONTENT_TYPE,
        content_hash=hashlib.sha256(content).hexdigest(),
        created_at=created_at,
        view_reference=view_reference,
        download_reference=f"{view_reference}/download",
        relative_path=f"{report_id}.html",
        conversation_id=conversation_id,
        request_id=request_id,
    )


def _build_metadata_json(
    artifact: ReportArtifact,
    relative_path: str,
    *,
    conversation_id: str | None = None,
    request_id: str | None = None,
) -> str:
    """Build the JSON string for payload_json — metadata ONLY, no HTML."""
    meta = ReportArtifactMetadata.from_domain(
        artifact,
        relative_path,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    return domain_to_json(meta)


class InMemoryReportRepository(ReportRepository):
    """Compatibility repository for tests and explicitly in-memory services."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[ReportArtifact, bytes]] = {}
        self._display_titles: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def store(
        self,
        report: ReportSpec,
        html: str,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> ReportArtifact:
        content = _validated_html_bytes(html)
        async with self._lock:
            report_id = self._new_id()
            artifact = _build_artifact(
                report, html, content, report_id,
                conversation_id=conversation_id,
                request_id=request_id,
            )
            self._items[report_id] = (artifact, content)
            self._display_titles[report_id] = _normalize_display_title(report.title)
            return artifact

    async def get(self, report_id: str) -> ReportArtifact:
        _validate_report_id(report_id)
        async with self._lock:
            item = self._items.get(report_id)
            if item is None:
                raise ReportNotFoundError("report_not_found")
            return item[0]

    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        _validate_report_id(report_id)
        async with self._lock:
            item = self._items.get(report_id)
            if item is None:
                raise ReportNotFoundError("report_not_found")
            artifact, content = item
            if hashlib.sha256(content).hexdigest() != artifact.content_hash:
                raise ReportStorageError("report_content_hash_mismatch")
            return artifact, content.decode("utf-8")

    async def delete_html_files(self, report_ids: list[str]) -> None:
        async with self._lock:
            for report_id in report_ids:
                _validate_report_id(report_id)
                self._items.pop(report_id, None)

    async def delete(self, report_id: str) -> ReportDeleteResult:
        _validate_report_id(report_id)
        async with self._lock:
            item = self._items.pop(report_id, None)
            if item is None:
                raise ReportNotFoundError("report_not_found")
            artifact = item[0]
            return ReportDeleteResult(
                report_id=artifact.report_id,
                source_mode=artifact.source_mode,
                conversation_id=artifact.conversation_id,
                request_id=artifact.request_id,
            )

    async def rename(self, report_id: str, display_title: str) -> ReportRenameResult:
        _validate_report_id(report_id)
        normalized = _normalize_display_title(display_title)
        async with self._lock:
            if report_id not in self._items:
                raise ReportNotFoundError("report_not_found")
            self._display_titles[report_id] = normalized
            return ReportRenameResult(report_id=report_id, display_title=normalized)

    def _new_id(self) -> str:
        while True:
            report_id = f"rpt_{uuid.uuid4().hex}"
            if report_id not in self._items:
                return report_id


class LocalReportRepository(ReportRepository):
    """Atomic local artifact storage rooted at local_state/reports only.

    M4.2: Report metadata is now persisted through a ``ReportArtifactRepository``
    (SQLite or in-memory).  The in-process ``_items`` dict is retained as a
    read-through cache — the metadata repository is the authority on restart.
    """

    def __init__(
        self,
        root: Path | str = Path("local_state") / "reports",
        metadata_repo: Optional[ReportArtifactRepository] = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._metadata_repo = metadata_repo
        self._items: dict[str, ReportArtifact] = {}
        self._lock = asyncio.Lock()

    @property
    def root(self) -> Path:
        return self._root

    async def _resolve_artifact(
        self, report_id: str
    ) -> ReportArtifact:
        """Resolve artifact metadata from cache or metadata repository.

        Falls back to the metadata repository (if configured) when the
        in-process cache does not have the entry.  On restart this is
        the recovery path.
        """
        artifact = self._items.get(report_id)
        if artifact is not None:
            return artifact
        if self._metadata_repo is not None:
            artifact = await self._metadata_repo.get(report_id)
            self._items[report_id] = artifact
            return artifact
        raise ReportNotFoundError("report_not_found")

    async def store(
        self,
        report: ReportSpec,
        html: str,
        *,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> ReportArtifact:
        content = _validated_html_bytes(html)
        async with self._lock:
            report_id = self._new_id()
            artifact = _build_artifact(
                report, html, content, report_id,
                conversation_id=conversation_id,
                request_id=request_id,
            )
            relative_path = f"{report_id}.html"
            target = (self._root / relative_path).resolve()

            # 1. Atomic filesystem write
            self._atomic_write(target, content)

            # 2. Persist metadata (best-effort — if this fails, clean up)
            if self._metadata_repo is not None:
                try:
                    await self._metadata_repo.save(
                        artifact,
                        conversation_id=conversation_id,
                        request_id=request_id,
                        relative_path=relative_path,
                        display_title=report.title,
                    )
                except Exception:
                    # Metadata persistence failed — clean up the temp HTML
                    # to avoid orphan artifacts.  Re-raise.
                    try:
                        target.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise

            self._items[report_id] = artifact
            return artifact

    async def get(self, report_id: str) -> ReportArtifact:
        _validate_report_id(report_id)
        async with self._lock:
            return await self._resolve_artifact(report_id)

    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        _validate_report_id(report_id)
        async with self._lock:
            artifact = await self._resolve_artifact(report_id)
            target = self._validate_path(artifact)
            try:
                content = target.read_bytes()
            except OSError as exc:
                raise ReportStorageError("report_artifact_unreadable") from exc
            if hashlib.sha256(content).hexdigest() != artifact.content_hash:
                raise ReportStorageError("report_content_hash_mismatch")
            try:
                html = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ReportStorageError("report_artifact_not_utf8") from exc
            return artifact, html

    async def delete_html_files(self, report_ids: list[str]) -> None:
        """Remove exact managed report files; missing files are idempotent."""
        async with self._lock:
            targets = [(report_id, self._target(report_id)) for report_id in report_ids]
            try:
                for report_id, target in targets:
                    target.unlink(missing_ok=True)
                    self._items.pop(report_id, None)
            except OSError as exc:
                raise ReportStorageError("report_artifact_delete_failed") from exc

    async def delete(self, report_id: str) -> ReportDeleteResult:
        """Durably unlink one exact managed report without deleting its conversation."""

        _validate_report_id(report_id)
        async with self._lock:
            if self._metadata_repo is not None:
                artifact = await self._metadata_repo.begin_delete(report_id)
            else:
                artifact = await self._resolve_artifact(report_id)
            target = self._target(report_id)
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                raise ReportStorageError("report_artifact_delete_failed") from exc
            self._items.pop(report_id, None)
            if self._metadata_repo is not None:
                await self._metadata_repo.complete_delete(report_id)
            return ReportDeleteResult(
                report_id=artifact.report_id,
                source_mode=artifact.source_mode,
                conversation_id=artifact.conversation_id,
                request_id=artifact.request_id,
            )

    async def rename(self, report_id: str, display_title: str) -> ReportRenameResult:
        """Update only the presentation title for one available report."""

        _validate_report_id(report_id)
        normalized = _normalize_display_title(display_title)
        async with self._lock:
            if self._metadata_repo is None:
                await self._resolve_artifact(report_id)
                return ReportRenameResult(
                    report_id=report_id, display_title=normalized
                )
            return await self._metadata_repo.rename(report_id, normalized)

    def _validate_path(self, artifact: ReportArtifact) -> Path:
        """Validate and resolve the relative_path as the recovery authority.

        Security rules (M4.2.2):
        1. relative_path must be a relative path (not absolute).
        2. ``..`` traversal and sibling-prefix escape are rejected by
           strict parent-directory containment: the resolved path must
           have *exactly* ``self._root`` as its parent.
        3. Symlinks within root are allowed; a resolved path whose real
           (symlink-resolved) parent differs from root is rejected.
        4. relative_path must be a single filename (no directory separators
           other than a possible leading ``./``).
        5. The filename must be exactly ``<report_id>.html``.
        6. The file must exist on disk.
        7. Hash mismatch is checked by the caller after read.

        Raises:
            ReportNotFoundError: path is invalid, traversal detected, or file missing.
            ReportStorageError: hash mismatch on read.
        """
        rp = artifact.relative_path or f"{artifact.report_id}.html"

        # 1. Reject absolute paths
        if os.path.isabs(rp):
            raise ReportNotFoundError("report_not_found")

        # 2. relative_path must be a single filename (no directory nesting)
        normalized = Path(rp).as_posix()
        # Strip optional leading ./
        if normalized.startswith("./"):
            normalized = normalized[2:]
        if "/" in normalized:
            raise ReportNotFoundError("report_not_found")

        # 3. Target filename must be exactly <report_id>.html
        expected_name = f"{artifact.report_id}.html"
        if normalized != expected_name:
            raise ReportNotFoundError("report_not_found")

        # 4. Build resolved path and verify strict parent containment.
        #    Unlike str.startswith, comparing Path.parent catches
        #    sibling-prefix escape: root=/x/reports, target=/x/reports_evil/x.html
        #    would have parent=/x/reports_evil which != /x/reports.
        root_resolved = self._root.resolve()
        try:
            target = (root_resolved / normalized).resolve()
        except (OSError, ValueError):
            raise ReportNotFoundError("report_not_found")

        if target.parent != root_resolved:
            raise ReportNotFoundError("report_not_found")

        # 5. Symlink escape check: if the target is a symlink, verify its
        #    real (ultimate) parent is also the report root.
        try:
            real = target.resolve(strict=False)
        except (OSError, ValueError):
            raise ReportNotFoundError("report_not_found")
        if target.is_symlink():
            if real.parent != root_resolved:
                raise ReportNotFoundError("report_not_found")

        # 6. File must exist
        if not target.exists():
            raise ReportNotFoundError("report_not_found")

        return target

    async def export_acceptance_copy(self, report_id: str) -> Path:
        """Export the exact managed bytes to the one fixed local acceptance name."""
        artifact, html = await self.read_html(report_id)
        content = html.encode("utf-8")
        if hashlib.sha256(content).hexdigest() != artifact.content_hash:
            raise ReportStorageError("report_content_hash_mismatch")
        async with self._lock:
            target = (self._root / "m3_sales_report.html").resolve()
            if target.parent != self._root:
                raise ReportStorageError("report_acceptance_path_invalid")
            self._atomic_write(target, content)
            return target

    def _target(self, report_id: str) -> Path:
        _validate_report_id(report_id)
        target = (self._root / f"{report_id}.html").resolve()
        if target.parent != self._root:
            raise ReportNotFoundError("report_not_found")
        return target

    def _new_id(self) -> str:
        """Generate a unique report_id.

        Checks the in-process cache and filesystem for collisions.
        The metadata repository PK is enforced at ``save()`` time via
        the DB primary key constraint.  UUIDv4 collision probability is
        astronomically low (~2^-122) — the retry loop is a safety net.
        """
        while True:
            report_id = f"rpt_{uuid.uuid4().hex}"
            if report_id not in self._items and not self._target(report_id).exists():
                return report_id

    def _atomic_write(self, target: Path, content: bytes) -> None:
        temp = self._root / f".{target.name}.{uuid.uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temp,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError as exc:
            raise ReportStorageError("report_atomic_store_failed") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
