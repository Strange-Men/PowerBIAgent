"""Long-term local_state ownership and cleanup governance."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.persistence.artifact_governance import audit_artifacts
from backend.app.persistence.artifact_ownership import (
    ArtifactOwnershipError,
    ArtifactOwnershipRegistry,
    cleanup_owned_test_run,
    managed_test_run,
    probe_owned_sqlite_residuals,
)


@pytest.fixture
def governed_state(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    state = project / "local_state"
    for name in ("persistence", "reports", "runtime", "archive"):
        (state / name).mkdir(parents=True, exist_ok=True)
    database = state / "persistence" / "powerbiagent.db"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE report_artifacts (
                report_id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL
            );
            CREATE TABLE conversation_delete_intents (conversation_id TEXT);
            CREATE TABLE report_delete_intents (report_id TEXT);
            """
        )
    return project, state


def test_clean_owned_layout_passes(governed_state):
    project, state = governed_state
    assert audit_artifacts(
        project, local_state_root=state, inspect_source_tree=False
    ).passed


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (lambda state: (state / "stray.log").write_text("x"), "unauthorized_local_state_entry"),
        (lambda state: (state / "reports" / "orphan.html").write_text("x"), "orphan_report_html"),
    ],
)
def test_unauthorized_and_orphan_artifacts_fail(governed_state, setup, expected):
    project, state = governed_state
    setup(state)
    result = audit_artifacts(project, local_state_root=state, inspect_source_tree=False)
    assert any(item.startswith(expected) for item in result.violations)


def test_metadata_file_mismatch_and_cleanup_intent_fail(governed_state):
    project, state = governed_state
    report_id = "rpt_" + "a" * 32
    with sqlite3.connect(state / "persistence" / "powerbiagent.db") as conn:
        conn.execute(
            "INSERT INTO report_artifacts VALUES (?, ?)",
            (report_id, f"{report_id}.html"),
        )
        conn.execute("INSERT INTO report_delete_intents VALUES (?)", (report_id,))
    result = audit_artifacts(project, local_state_root=state, inspect_source_tree=False)
    assert f"report_file_missing:{report_id}" in result.violations
    assert "artifact_cleanup_pending:report_delete_intents:1" in result.violations


def test_active_test_ownership_and_cleanup_failure_fail(governed_state):
    project, state = governed_state
    (state / "runtime" / "artifact_ownership.json").write_text(
        json.dumps({
            "version": 1,
            "active": [{"owner_id": "pytest:test-one"}],
            "cleanup_failures": [{"owner_id": "pytest:test-two"}],
        }),
        encoding="utf-8",
    )
    result = audit_artifacts(project, local_state_root=state, inspect_source_tree=False)
    assert "test_artifact_residual:pytest:test-one" in result.violations
    assert "artifact_cleanup_failure:pytest:test-two" in result.violations


def test_version_two_registry_reports_each_owned_residual_kind(governed_state):
    project, state = governed_state
    registry = ArtifactOwnershipRegistry(
        state / "runtime" / "artifact_ownership.json"
    )
    ownership = registry.register_run(
        test_run_id="residual-kinds",
        test_namespace="m541-residuals",
        runtime_mode="real",
        source_mode="real",
    )
    ownership.add_conversation("conversation-owned")
    ownership.add_report(
        "report-owned", html_path=state / "reports" / "report-owned.html"
    )
    ownership.add_sqlite_path(state / "persistence" / "test-owned.db")

    result = audit_artifacts(
        project, local_state_root=state, inspect_source_tree=False
    )
    assert any(item.startswith("test_conversation_residual:") for item in result.violations)
    assert any(item.startswith("test_report_metadata_residual:") for item in result.violations)
    assert any(item.startswith("test_report_html_residual:") for item in result.violations)
    assert any(item.startswith("test_sqlite_namespace_residual:") for item in result.violations)


@pytest.mark.asyncio
async def test_owned_conversation_and_report_cleanup_completes_without_residual(
    governed_state,
):
    project, state = governed_state
    registry = ArtifactOwnershipRegistry(
        state / "runtime" / "artifact_ownership.json"
    )
    deleted_conversations: list[str] = []
    deleted_reports: list[str] = []

    async with managed_test_run(
        registry,
        test_run_id="browser-acceptance-1",
        test_namespace="m541-browser",
        runtime_mode="real",
        source_mode="real",
        delete_conversation=lambda resource_id: _record(
            deleted_conversations, resource_id
        ),
        delete_report=lambda resource_id: _record(deleted_reports, resource_id),
        residual_probe=lambda _run: _residuals([]),
    ) as ownership:
        ownership.add_conversation("test-conversation")
        ownership.add_report("test-report")

    assert deleted_conversations == ["test-conversation"]
    assert deleted_reports == ["test-report"]
    assert audit_artifacts(
        project, local_state_root=state, inspect_source_tree=False
    ).passed


@pytest.mark.asyncio
async def test_cleanup_failure_is_durable_and_gate_fails(governed_state):
    project, state = governed_state
    registry = ArtifactOwnershipRegistry(
        state / "runtime" / "artifact_ownership.json"
    )
    ownership = registry.register_run(
        test_run_id="failed-cleanup",
        test_namespace="m541-failure",
        runtime_mode="real",
        source_mode="real",
    )
    ownership.add_report("residual-report")

    async def fail_delete(_resource_id: str) -> None:
        raise RuntimeError("formal delete failed")

    with pytest.raises(ArtifactOwnershipError, match="cleanup_incomplete"):
        await cleanup_owned_test_run(
            registry,
            "failed-cleanup",
            delete_conversation=lambda resource_id: _record([], resource_id),
            delete_report=fail_delete,
            residual_probe=lambda _run: _residuals(
                ["report_metadata:residual-report", "html:residual-report.html"]
            ),
        )

    result = audit_artifacts(
        project, local_state_root=state, inspect_source_tree=False
    )
    assert "test_report_metadata_residual:automation:failed-cleanup:residual-report" in (
        result.violations
    )
    assert "artifact_cleanup_failure:automation:failed-cleanup" in result.violations


@pytest.mark.asyncio
async def test_cleanup_never_touches_unregistered_user_resources(governed_state):
    _project, state = governed_state
    registry = ArtifactOwnershipRegistry(
        state / "runtime" / "artifact_ownership.json"
    )
    ownership = registry.register_run(
        test_run_id="safe-cleanup",
        test_namespace="m541-safe",
        runtime_mode="real",
        source_mode="real",
    )
    ownership.add_conversation("automation-conversation")
    user_resources = {"user-conversation", "user-report"}
    deleted: list[str] = []

    await cleanup_owned_test_run(
        registry,
        "safe-cleanup",
        delete_conversation=lambda resource_id: _record(deleted, resource_id),
        delete_report=lambda resource_id: _record(deleted, resource_id),
        residual_probe=lambda _run: _residuals([]),
    )

    assert deleted == ["automation-conversation"]
    assert user_resources.isdisjoint(deleted)


def test_sqlite_residual_probe_matches_only_registered_ids(tmp_path: Path):
    database = tmp_path / "owned-residuals.db"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE conversations (
                runtime_mode TEXT, conversation_id TEXT
            );
            CREATE TABLE report_artifacts (report_id TEXT);
            CREATE TABLE report_presentations (report_id TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO conversations VALUES ('real', ?)",
            [("automation-conversation",), ("user-conversation",)],
        )
        conn.executemany(
            "INSERT INTO report_artifacts VALUES (?)",
            [("automation-report",), ("user-report",)],
        )
        conn.execute(
            "INSERT INTO report_presentations VALUES ('automation-report')"
        )
    registry = ArtifactOwnershipRegistry(tmp_path / "ownership.json")
    ownership = registry.register_run(
        test_run_id="sqlite-probe",
        test_namespace="m541-sqlite",
        runtime_mode="real",
        source_mode="real",
    )
    ownership.add_conversation("automation-conversation")
    ownership.add_report("automation-report")

    residuals = probe_owned_sqlite_residuals(
        database, registry.get_active("sqlite-probe")
    )

    assert residuals == [
        "sqlite_namespace:conversations:automation-conversation",
        "sqlite_report:report_artifacts:automation-report",
        "sqlite_report:report_presentations:automation-report",
    ]
    assert all("user-" not in item for item in residuals)


@pytest.mark.parametrize("malformed_schema", [False, True])
def test_sqlite_probe_releases_connection_before_file_cleanup(tmp_path, monkeypatch, malformed_schema):
    database = tmp_path / "probe-lifecycle.db"
    connection = sqlite3.connect(database)
    try:
        columns = "conversation_id TEXT" if malformed_schema else "runtime_mode TEXT, conversation_id TEXT"
        connection.execute(f"CREATE TABLE conversations ({columns})")
        connection.commit()
    finally:
        connection.close()
    registry = ArtifactOwnershipRegistry(tmp_path / "probe-ownership.json")
    owner = registry.register_run(test_run_id="probe-close", test_namespace="probe-close",
        runtime_mode="real", source_mode="real")
    owner.add_conversation("owned-conversation")
    opened = []
    real_connect = sqlite3.connect

    def capture_connection(*args, **kwargs):
        result = real_connect(*args, **kwargs)
        opened.append(result)
        return result

    monkeypatch.setattr(sqlite3, "connect", capture_connection)
    try:
        if malformed_schema:
            with pytest.raises(sqlite3.OperationalError):
                probe_owned_sqlite_residuals(database, registry.get_active("probe-close"))
        else:
            assert probe_owned_sqlite_residuals(database, registry.get_active("probe-close")) == []
        assert len(opened) == 1
        # Keep a live reference so garbage collection cannot hide the leak.
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            opened[0].execute("SELECT 1")
        database.unlink()
    finally:
        for item in opened:
            item.close()
        registry.complete_run("probe-close")
        database.unlink(missing_ok=True)


async def _record(target: list[str], resource_id: str) -> None:
    target.append(resource_id)


async def _residuals(items: list[str]) -> list[str]:
    return items
