"""M4.2.2 — Path containment & metadata coherence hardening tests.

Path containment（6 tests）:
  1. sibling-prefix escape rejected（核心漏洞修复验证）
  2. nested directory（多层 relative_path）→ reject
  3. symlink escape（resolve 后 parent 不同）→ reject
  4. valid '<report_id>.html' PASS
  5. startswith vulnerability proven closed
  6. wrong filename rejected（继承 M4.2.1）

Metadata coherence（6 tests）:
  7. payload report_id != row.report_id → reject
  8. payload content_hash != row.content_hash → reject
  9. payload relative_path != row.relative_path → reject
  10. payload source_mode != row.source_mode → reject
  11. payload linkage mismatch → reject
  12. consistent metadata PASS

Legacy regression（1 test）:
  13. legacy HTML still rejected after M4.2.2 changes
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text as sa_text

from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import Base
from backend.app.persistence.repositories.report_artifact import (
    InMemoryReportArtifactRepository,
    SQLiteReportArtifactRepository,
)
from backend.app.report.resources import (
    LocalReportRepository,
    ReportArtifact,
    ReportNotFoundError,
    ReportStorageError,
)


# ===========================================================================
# Helpers
# ===========================================================================

_REPORT_ID_HEX = "rpt_" + "a" * 32  # hex-valid report_id for valid artifacts


def _create_artifact() -> ReportArtifact:
    """Create a minimal valid ReportArtifact for testing."""
    view_ref = f"/api/reports/{_REPORT_ID_HEX}"
    return ReportArtifact(
        report_id=_REPORT_ID_HEX,
        template_key="sales_report",
        html="<!DOCTYPE html><html><body>Test</body></html>",
        source_mode="mock",
        generated_at="2026-08-19T00:00:00",
        contract_version="1.0",
        semantic_model_key="test_model",
        schema_fingerprint="a" * 64,
        verified_fact_set_ids=["fact-1"],
        query_result_ids=["qr-1"],
        content_type="text/html; charset=utf-8",
        content_hash=hashlib.sha256(
            "<!DOCTYPE html><html><body>Test</body></html>".encode("utf-8")
        ).hexdigest(),
        created_at="2026-08-19T00:00:00",
        view_reference=view_ref,
        download_reference=f"{view_ref}/download",
    )


def _report_spec_for_artifact(artifact: ReportArtifact):
    """Create a minimal ReportSpec that matches the artifact's provenance fields."""
    from backend.app.schemas.data_contracts import ReportSpec

    return ReportSpec(
        title="Test Report",
        template_key=artifact.template_key,
        summary="Test summary",
        source_mode=artifact.source_mode,
        contract_version=artifact.contract_version,
        semantic_model_key=artifact.semantic_model_key,
        schema_fingerprint=artifact.schema_fingerprint,
        verified_fact_set_ids=artifact.verified_fact_set_ids,
        query_result_ids=artifact.query_result_ids,
    )


def _evil_artifact(
    relative_path: str,
    *,
    report_id: str | None = None,
) -> ReportArtifact:
    """Build an artifact with an arbitrary relative_path — report_id must be hex-valid.

    NOTE: report_id defaults to hex-valid a*32. Callers who want a DIFFERENT
    hex-valid ID should pass report_id explicitly.
    """
    rid = report_id or _REPORT_ID_HEX
    view_ref = f"/api/reports/{rid}"
    return ReportArtifact(
        report_id=rid,
        template_key="test",
        html="<!DOCTYPE html><html><body>Evil</body></html>",
        source_mode="mock",
        generated_at="2026-08-19T00:00:00",
        contract_version="",
        semantic_model_key="test",
        schema_fingerprint="b" * 64,
        verified_fact_set_ids=["fact-e"],
        query_result_ids=["qr-e"],
        content_type="text/html; charset=utf-8",
        content_hash=hashlib.sha256(
            "<!DOCTYPE html><html><body>Evil</body></html>".encode("utf-8")
        ).hexdigest(),
        created_at="2026-08-19T00:00:00",
        view_reference=view_ref,
        download_reference=f"{view_ref}/download",
        relative_path=relative_path,
    )


# ---------------------------------------------------------------------------
# SQLite fixture (minimal — report-ops only)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_report_repo():
    """Create a fresh SQLiteReportArtifactRepository in a temp DB."""
    tmp = Path(tempfile.mkdtemp()) / "test_m422.db"
    db_path = str(tmp)
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await configure_engine(engine)

    session_factory = create_session_factory(engine)
    repo = SQLiteReportArtifactRepository(session_factory=session_factory)

    yield repo, session_factory, db_path

    await dispose_engine(engine)


# ===========================================================================
# PATH CONTAINMENT — M4.2.2
# ===========================================================================


class TestM422PathContainment:
    """M4.2.2: replace str.startswith with strict parent containment."""

    @pytest.mark.asyncio
    async def test_sibling_prefix_escape_rejected(self):
        """Sibling-prefix escape: root=/x/reports, file in /x/reports_evil/.

        The old str.startswith('/x/reports') would match '/x/reports_evil/'.
        M4.2.2 must reject this via strict parent comparison + single-filename rule.
        """
        root_dir = Path(tempfile.mkdtemp())
        reports_root = root_dir / "reports"
        reports_root.mkdir(parents=True, exist_ok=True)
        evil_sibling = root_dir / "reports_evil"
        evil_sibling.mkdir(parents=True, exist_ok=True)

        evil_id = "rpt_" + "e" * 32  # hex-valid
        evil_file = evil_sibling / f"{evil_id}.html"
        evil_file.write_text("<!DOCTYPE html><html><body>ESCAPED</body></html>", encoding="utf-8")

        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_root, metadata_repo=meta_repo)

        evil = _evil_artifact(
            f"../reports_evil/{evil_id}.html",
            report_id=evil_id,
        )
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_nested_directory_rejected(self):
        """relative_path with a directory separator → reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        evil = _evil_artifact(
            "subdir/rpt_f.html",
            report_id="rpt_" + "f" * 32,  # hex-valid
        )
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_symlink_escape_rejected(self):
        """Symlink whose real target parent differs from root → reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        outside = Path(tempfile.mkdtemp())
        escape_target = outside / "leaked.html"
        escape_target.write_text("<!DOCTYPE html><html><body>LEAKED</body></html>", encoding="utf-8")

        report_id = "rpt_" + "d" * 32  # hex-valid
        link_path = reports_dir / f"{report_id}.html"
        try:
            link_path.symlink_to(escape_target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)
        artifact = _evil_artifact(
            f"{report_id}.html",
            report_id=report_id,
        )
        await meta_repo.save(artifact)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(report_id)

    @pytest.mark.asyncio
    async def test_valid_path_still_passes(self):
        """Valid '<report_id>.html' must still pass."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        spec = _report_spec_for_artifact(_create_artifact())
        stored = await local_repo.store(spec, "<!DOCTYPE html><html><body>M422 Valid</body></html>")
        report_id = stored.report_id

        artifact_b, html_b = await local_repo.read_html(report_id)
        assert artifact_b.report_id == report_id
        assert "M422 Valid" in html_b

    @pytest.mark.asyncio
    async def test_startswith_vulnerability_proven_closed(self):
        """Sibling-prefix escape attack via reports_attack dir."""
        root_base = Path(tempfile.mkdtemp())
        safe_root = root_base / "reports"
        safe_root.mkdir(parents=True, exist_ok=True)
        attack_root = root_base / "reports_attack"
        attack_root.mkdir(parents=True, exist_ok=True)

        rid = "rpt_" + "f" * 32  # hex-valid
        attack_file = attack_root / f"{rid}.html"
        attack_file.write_text("<!DOCTYPE html><html><body>ATTACK</body></html>", encoding="utf-8")

        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=safe_root, metadata_repo=meta_repo)

        evil_artifact = _evil_artifact(
            f"../reports_attack/{rid}.html",
            report_id=rid,
        )
        await meta_repo.save(evil_artifact)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(rid)

    @pytest.mark.asyncio
    async def test_wrong_filename_still_rejected(self):
        """Filename not matching report_id must still be rejected."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        wrong = _evil_artifact(
            "wrong-report.html",
            report_id="rpt_" + "c" * 32,  # hex-valid
        )
        await meta_repo.save(wrong)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(wrong.report_id)

    @pytest.mark.asyncio
    async def test_absolute_path_still_rejected(self):
        """Absolute path must still be rejected after M4.2.2 changes."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        # Absolute paths are caught by os.path.isabs() before any other check.
        # On Windows any C:\... path is absolute, but paths starting with /
        # are also absolute on Windows in os.path.isabs().  Test both.
        if os.name == "nt":
            evil = _evil_artifact("C:\\Windows\\win.ini")
        else:
            evil = _evil_artifact("/etc/passwd")
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_traversal_path_rejected(self):
        """../ in relative_path → reject (even after normalize)."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        evil = _evil_artifact("../evil.html")
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)


# ===========================================================================
# METADATA COHERENCE — M4.2.2
# ===========================================================================

# All report_id values in coherence tests must be hex-valid [0-9a-f]{32}
# because _model_to_artifact() constructs a ReportArtifact which validates
# the report_id pattern.
_R1 = "rpt_a0000000000000000000000000000001"  # report_id mismatch test
_R2 = "rpt_a0000000000000000000000000000002"  # content_hash mismatch
_R3 = "rpt_a0000000000000000000000000000003"  # relative_path mismatch
_R4 = "rpt_a0000000000000000000000000000004"  # source_mode mismatch
_R5 = "rpt_a0000000000000000000000000000005"  # linkage mismatch
_R6 = "rpt_a0000000000000000000000000000006"  # legacy HTML


class TestM422MetadataCoherence:
    """M4.2.2: DB row / payload_json coherence validation."""

    @pytest.mark.asyncio
    async def test_payload_report_id_mismatch_rejected(self, sqlite_report_repo):
        """payload report_id != row.report_id → reject."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R1,  # same as row — but we inject a different
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "a" * 64,
                    "source_mode": "mock",
                    "content_hash": "a" * 64,
                    "relative_path": f"{_R1}.html",
                })
                # payload says _R1, row says _R2 — coherence violation
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                'mock', :ch, :rp, :pj)"""
                    ),
                    {
                        "rid": _R1,
                        "sf": "a" * 64,
                        "ch": "a" * 64,
                        "rp": f"{_R1}.html",
                        "pj": bad_payload,
                    },
                )
            await session.commit()

        # Payload report_id matches row.report_id in this case (both are _R1)
        # so no mismatch.  We need a test where they DIFFER.
        # Re-do with a direct mismatch: row has _R2, payload says _R1.
        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R1,  # payload says _R1
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "a" * 64,
                    "source_mode": "mock",
                    "content_hash": "a" * 64,
                    "relative_path": f"{_R1}.html",
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                'mock', :ch, :rp, :pj)"""
                    ),
                    {
                        "rid": _R2,  # row says _R2 — different!
                        "sf": "a" * 64,
                        "ch": "a" * 64,
                        "rp": f"{_R1}.html",
                        "pj": bad_payload,
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="coherence"):
            await repo.get(_R2)

    @pytest.mark.asyncio
    async def test_payload_content_hash_mismatch_rejected(self, sqlite_report_repo):
        """payload content_hash != row.content_hash → reject."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R2,
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "b" * 64,
                    "source_mode": "mock",
                    "content_hash": "b" * 64,  # payload says b*64
                    "relative_path": f"{_R2}.html",
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                'mock', :ch, :rp, :pj)"""
                    ),
                    {
                        "rid": _R2,
                        "sf": "b" * 64,
                        "ch": "a" * 64,  # DB says a*64
                        "rp": f"{_R2}.html",
                        "pj": bad_payload,
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="coherence"):
            await repo.get(_R2)

    @pytest.mark.asyncio
    async def test_payload_relative_path_mismatch_rejected(self, sqlite_report_repo):
        """payload relative_path != row.relative_path → reject."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R3,
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "c" * 64,
                    "source_mode": "mock",
                    "content_hash": "c" * 64,
                    "relative_path": "wrong_path.html",  # differs from DB column
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                'mock', :ch, :rp, :pj)"""
                    ),
                    {
                        "rid": _R3,
                        "sf": "c" * 64,
                        "ch": "c" * 64,
                        "rp": f"{_R3}.html",  # row says correct path
                        "pj": bad_payload,  # payload says wrong_path.html
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="coherence"):
            await repo.get(_R3)

    @pytest.mark.asyncio
    async def test_payload_source_mode_mismatch_rejected(self, sqlite_report_repo):
        """payload source_mode != row.source_mode → reject."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R4,
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "d" * 64,
                    "source_mode": "real",  # payload says real
                    "content_hash": "d" * 64,
                    "relative_path": f"{_R4}.html",
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                :sm, :ch, :rp, :pj)"""
                    ),
                    {
                        "rid": _R4,
                        "sf": "d" * 64,
                        "sm": "mock",  # DB says mock
                        "ch": "d" * 64,
                        "rp": f"{_R4}.html",
                        "pj": bad_payload,  # payload says real
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="coherence"):
            await repo.get(_R4)

    @pytest.mark.asyncio
    async def test_payload_linkage_mismatch_rejected(self, sqlite_report_repo):
        """payload conversation/request differs from DB column → reject."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                bad_payload = json.dumps({
                    "report_id": _R5,
                    "template_key": "sales_report",
                    "semantic_model_key": "test",
                    "schema_fingerprint": "e" * 64,
                    "source_mode": "mock",
                    "content_hash": "e" * 64,
                    "relative_path": f"{_R5}.html",
                    "conversation_id": "payload-conv",
                    "request_id": "payload-req",
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json,
                         conversation_id, request_id)
                        VALUES (:rid, 'sales_report', 'test', :sf,
                                'mock', :ch, :rp, :pj,
                                :conv, :req)"""
                    ),
                    {
                        "rid": _R5,
                        "sf": "e" * 64,
                        "ch": "e" * 64,
                        "rp": f"{_R5}.html",
                        "pj": bad_payload,
                        "conv": "row-conv",
                        "req": "row-req",
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="coherence"):
            await repo.get(_R5)

    @pytest.mark.asyncio
    async def test_legacy_html_still_rejected(self, sqlite_report_repo):
        """M4.2.1 legacy HTML check still works after M4.2.2 changes."""
        repo, sf, db_path = sqlite_report_repo

        async with sf() as session:
            async with session.begin():
                legacy_payload = json.dumps({
                    "report_id": _R6,
                    "template_key": "sales_report",
                    "html": "<!DOCTYPE html><html><body>LEGACY</body></html>",
                    "source_mode": "mock",
                    "content_hash": "f" * 64,
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', '', '', 'mock', :ch, 'legacy.html', :pj)"""
                    ),
                    {
                        "rid": _R6,
                        "ch": "f" * 64,
                        "pj": legacy_payload,
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="legacy HTML"):
            await repo.get(_R6)

    @pytest.mark.asyncio
    async def test_consistent_metadata_passes(self, sqlite_report_repo):
        """Valid consistent metadata must still pass."""
        repo, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()

        await repo.save(artifact)
        retrieved = await repo.get(artifact.report_id)

        assert retrieved.report_id == artifact.report_id
        assert retrieved.content_hash == artifact.content_hash
        assert retrieved.relative_path == f"{artifact.report_id}.html"
        assert retrieved.html == ""
