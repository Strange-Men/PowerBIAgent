"""Report artifact persistence contract, identity, and namespace invariants."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import Base, ReportArtifactModel
from backend.app.persistence.repositories.report_artifact import (
    InMemoryReportArtifactRepository,
    SQLiteReportArtifactRepository,
)
from backend.app.report.resources import ReportArtifact, ReportStorageError


_REPORT_ID = "rpt_" + "a" * 32


def _artifact(
    *,
    report_id: str = _REPORT_ID,
    source_mode: str = "mock",
    semantic_model_key: str = "test_model",
    schema_fingerprint: str = "a" * 64,
    content_hash: str | None = None,
    conversation_id: str | None = "conv-report",
    request_id: str | None = "req-report",
    verified_fact_set_ids: list[str] | None = None,
    query_result_ids: list[str] | None = None,
) -> ReportArtifact:
    html = "<!DOCTYPE html><html><body>Report</body></html>"
    view_reference = f"/api/reports/{report_id}"
    return ReportArtifact(
        report_id=report_id,
        template_key="sales_report",
        html=html,
        source_mode=source_mode,
        generated_at="2026-08-20T00:00:00+00:00",
        contract_version="1.0",
        semantic_model_key=semantic_model_key,
        schema_fingerprint=schema_fingerprint,
        verified_fact_set_ids=verified_fact_set_ids or ["fact-1"],
        query_result_ids=query_result_ids or ["query-1"],
        content_type="text/html; charset=utf-8",
        content_hash=content_hash or hashlib.sha256(html.encode("utf-8")).hexdigest(),
        created_at="2026-08-20T00:00:00+00:00",
        view_reference=view_reference,
        download_reference=f"{view_reference}/download",
        relative_path=f"{report_id}.html",
        conversation_id=conversation_id,
        request_id=request_id,
    )


@pytest_asyncio.fixture
async def sqlite_report_repo():
    db_path = Path(tempfile.mkdtemp()) / "report_invariants.db"
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    repository = SQLiteReportArtifactRepository(session_factory=session_factory)
    yield repository, session_factory
    await dispose_engine(engine)


async def _remove_payload_fields(session_factory, report_id: str, *fields: str) -> None:
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(ReportArtifactModel, report_id)
            assert row is not None
            payload = json.loads(row.payload_json)
            for field in fields:
                payload.pop(field, None)
            row.payload_json = json.dumps(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "report_id",
        "source_mode",
        "content_hash",
        "relative_path",
        "template_key",
        "semantic_model_key",
        "schema_fingerprint",
    ],
)
@pytest.mark.asyncio
async def test_missing_required_payload_field_fails_closed(
    sqlite_report_repo,
    missing_field: str,
):
    repository, session_factory = sqlite_report_repo
    artifact = _artifact()
    await repository.save(artifact)
    await _remove_payload_fields(session_factory, artifact.report_id, missing_field)

    with pytest.raises(ReportStorageError, match="persistence contract"):
        await repository.get(artifact.report_id)


@pytest.mark.parametrize("linkage_field", ["conversation_id", "request_id"])
@pytest.mark.asyncio
async def test_db_linkage_without_payload_linkage_fails_closed(
    sqlite_report_repo,
    linkage_field: str,
):
    repository, session_factory = sqlite_report_repo
    artifact = _artifact()
    await repository.save(artifact)
    await _remove_payload_fields(session_factory, artifact.report_id, linkage_field)

    with pytest.raises(ReportStorageError, match="persistence contract"):
        await repository.get(artifact.report_id)


@pytest.mark.asyncio
async def test_missing_modern_payload_fails_closed(sqlite_report_repo):
    repository, session_factory = sqlite_report_repo
    artifact = _artifact()
    await repository.save(artifact)

    async with session_factory() as session:
        async with session.begin():
            row = await session.get(ReportArtifactModel, artifact.report_id)
            assert row is not None
            row.payload_json = None

    with pytest.raises(ReportStorageError, match="persistence contract"):
        await repository.get(artifact.report_id)


def _collision_candidate(
    base: ReportArtifact,
    case: str,
) -> tuple[ReportArtifact, dict[str, str]]:
    data = base.model_dump(mode="json")
    save_kwargs: dict[str, str] = {}
    if case == "source_mode":
        data["source_mode"] = "real"
    elif case == "semantic_model_key":
        data["semantic_model_key"] = "other_model"
    elif case == "schema_fingerprint":
        data["schema_fingerprint"] = "b" * 64
    elif case == "content_hash":
        data["content_hash"] = "c" * 64
    elif case == "relative_path":
        save_kwargs["relative_path"] = "other.html"
    elif case == "conversation_id":
        save_kwargs["conversation_id"] = "other-conversation"
    elif case == "request_id":
        save_kwargs["request_id"] = "other-request"
    elif case == "provenance":
        data["verified_fact_set_ids"] = ["fact-2"]
        data["query_result_ids"] = ["query-2"]
    else:  # pragma: no cover - parameter list is fixed below
        raise AssertionError(case)
    return ReportArtifact.model_validate(data), save_kwargs


_COLLISION_CASES = [
    "source_mode",
    "semantic_model_key",
    "schema_fingerprint",
    "content_hash",
    "relative_path",
    "conversation_id",
    "request_id",
    "provenance",
]


@pytest.mark.asyncio
async def test_sqlite_identical_metadata_save_is_idempotent(sqlite_report_repo):
    repository, _ = sqlite_report_repo
    artifact = _artifact()

    await repository.save(artifact)
    await repository.save(artifact)

    assert await repository._count() == 1
    assert await repository.get(artifact.report_id) == artifact.model_copy(update={"html": ""})


@pytest.mark.parametrize("case", _COLLISION_CASES)
@pytest.mark.asyncio
async def test_sqlite_report_identity_collision_rejected(sqlite_report_repo, case: str):
    repository, _ = sqlite_report_repo
    artifact = _artifact()
    await repository.save(artifact)
    candidate, save_kwargs = _collision_candidate(artifact, case)

    with pytest.raises(ReportStorageError, match="identity_collision"):
        await repository.save(candidate, **save_kwargs)

    stored = await repository.get(artifact.report_id)
    assert stored.source_mode == artifact.source_mode
    assert stored.content_hash == artifact.content_hash
    assert stored.semantic_model_key == artifact.semantic_model_key
    assert stored.conversation_id == artifact.conversation_id
    assert stored.request_id == artifact.request_id


@pytest.mark.asyncio
async def test_inmemory_identical_metadata_save_is_idempotent():
    repository = InMemoryReportArtifactRepository()
    artifact = _artifact()

    await repository.save(artifact)
    await repository.save(artifact)

    assert await repository._count() == 1


@pytest.mark.parametrize("case", _COLLISION_CASES)
@pytest.mark.asyncio
async def test_inmemory_report_identity_collision_rejected(case: str):
    repository = InMemoryReportArtifactRepository()
    artifact = _artifact()
    await repository.save(artifact)
    candidate, save_kwargs = _collision_candidate(artifact, case)

    with pytest.raises(ReportStorageError, match="identity_collision"):
        await repository.save(candidate, **save_kwargs)


@pytest.mark.asyncio
async def test_report_history_namespace_is_source_mode_plus_conversation(
    sqlite_report_repo,
):
    repository, session_factory = sqlite_report_repo
    conversation_id = "shared-conversation"
    mock_artifact = _artifact(
        report_id="rpt_" + "d" * 32,
        source_mode="mock",
        conversation_id=conversation_id,
        request_id="req-mock",
    )
    real_artifact = _artifact(
        report_id="rpt_" + "e" * 32,
        source_mode="real",
        conversation_id=conversation_id,
        request_id="req-real",
    )
    await repository.save(mock_artifact)
    await repository.save(real_artifact)

    async with session_factory() as session:
        mock_rows = (
            await session.execute(
                select(ReportArtifactModel.report_id).where(
                    ReportArtifactModel.source_mode == "mock",
                    ReportArtifactModel.conversation_id == conversation_id,
                )
            )
        ).scalars().all()
        real_rows = (
            await session.execute(
                select(ReportArtifactModel.report_id).where(
                    ReportArtifactModel.source_mode == "real",
                    ReportArtifactModel.conversation_id == conversation_id,
                )
            )
        ).scalars().all()

    assert mock_rows == [mock_artifact.report_id]
    assert real_rows == [real_artifact.report_id]


def test_report_source_mode_is_closed_namespace():
    data = _artifact().model_dump(mode="json")
    data["source_mode"] = "unknown"

    with pytest.raises(ValidationError):
        ReportArtifact.model_validate(data)
