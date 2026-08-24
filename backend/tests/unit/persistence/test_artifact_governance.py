"""Long-term local_state ownership and cleanup governance."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.persistence.artifact_governance import audit_artifacts


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
