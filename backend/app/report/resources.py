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

from pydantic import ConfigDict, Field, model_validator

from backend.app.schemas.data_contracts import RenderedReport, ReportSpec


REPORT_CONTENT_TYPE = "text/html; charset=utf-8"
_REPORT_ID_PATTERN = re.compile(r"^rpt_[0-9a-f]{32}$")


class ReportResourceError(RuntimeError):
    pass


class ReportNotFoundError(ReportResourceError):
    pass


class ReportStorageError(ReportResourceError):
    pass


class ReportArtifact(RenderedReport):
    """Metadata and exact compatibility copy for one managed HTML artifact."""

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


class ReportRepository(ABC):
    """Repository-owned report IDs are the only route to stored artifacts."""

    @abstractmethod
    async def store(self, report: ReportSpec, html: str) -> ReportArtifact:
        ...

    @abstractmethod
    async def get(self, report_id: str) -> ReportArtifact:
        ...

    @abstractmethod
    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        ...


def _validate_report_id(report_id: str) -> None:
    if not _REPORT_ID_PATTERN.fullmatch(report_id):
        raise ReportNotFoundError("report_not_found")


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
    )


class InMemoryReportRepository(ReportRepository):
    """Compatibility repository for tests and explicitly in-memory services."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[ReportArtifact, bytes]] = {}
        self._lock = asyncio.Lock()

    async def store(self, report: ReportSpec, html: str) -> ReportArtifact:
        content = _validated_html_bytes(html)
        async with self._lock:
            report_id = self._new_id()
            artifact = _build_artifact(report, html, content, report_id)
            self._items[report_id] = (artifact, content)
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

    def _new_id(self) -> str:
        while True:
            report_id = f"rpt_{uuid.uuid4().hex}"
            if report_id not in self._items:
                return report_id


class LocalReportRepository(ReportRepository):
    """Atomic local artifact storage rooted at local_state/reports only."""

    def __init__(self, root: Path | str = Path("local_state") / "reports") -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, ReportArtifact] = {}
        self._lock = asyncio.Lock()

    @property
    def root(self) -> Path:
        return self._root

    async def store(self, report: ReportSpec, html: str) -> ReportArtifact:
        content = _validated_html_bytes(html)
        async with self._lock:
            report_id = self._new_id()
            artifact = _build_artifact(report, html, content, report_id)
            target = self._target(report_id)
            self._atomic_write(target, content)
            self._items[report_id] = artifact
            return artifact

    async def get(self, report_id: str) -> ReportArtifact:
        _validate_report_id(report_id)
        async with self._lock:
            artifact = self._items.get(report_id)
            if artifact is None:
                raise ReportNotFoundError("report_not_found")
            return artifact

    async def read_html(self, report_id: str) -> tuple[ReportArtifact, str]:
        _validate_report_id(report_id)
        async with self._lock:
            artifact = self._items.get(report_id)
            if artifact is None:
                raise ReportNotFoundError("report_not_found")
            target = self._target(report_id)
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
