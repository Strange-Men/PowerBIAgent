"""Read-only governance audit for local runtime and test artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


ALLOWED_LOCAL_STATE_DIRECTORIES = frozenset(
    {"persistence", "reports", "runtime", "archive"}
)
_REPORT_FILE = re.compile(r"^rpt_[0-9a-f]{32}\.html$")
_RUNTIME_SUFFIXES = frozenset({".db", ".sqlite", ".log", ".html", ".json", ".txt"})


@dataclass(frozen=True)
class ArtifactGovernanceResult:
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.violations


def audit_artifacts(
    project_root: Path,
    *,
    local_state_root: Path | None = None,
    inspect_source_tree: bool = True,
) -> ArtifactGovernanceResult:
    """Audit without deleting, moving, or repairing any artifact."""

    project_root = project_root.resolve()
    state_root = (local_state_root or project_root / "local_state").resolve()
    violations: list[str] = []
    if not state_root.exists():
        violations.append("local_state_missing")
        return ArtifactGovernanceResult(tuple(violations))

    for required in sorted(ALLOWED_LOCAL_STATE_DIRECTORIES):
        if not (state_root / required).is_dir():
            violations.append(f"local_state_directory_missing:{required}")
    for entry in state_root.iterdir():
        if entry.name not in ALLOWED_LOCAL_STATE_DIRECTORIES:
            violations.append(f"unauthorized_local_state_entry:{entry.name}")

    _audit_registry(state_root / "runtime" / "artifact_ownership.json", violations)
    _audit_database_and_reports(state_root, violations)
    if inspect_source_tree:
        _audit_source_tree(project_root, violations)
    return ArtifactGovernanceResult(tuple(sorted(set(violations))))


def _audit_registry(path: Path, violations: list[str]) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        violations.append("artifact_ownership_registry_invalid")
        return
    if not isinstance(payload, dict) or payload.get("version") != 1:
        violations.append("artifact_ownership_registry_invalid")
        return
    active = payload.get("active", [])
    failures = payload.get("cleanup_failures", [])
    if not isinstance(active, list) or not isinstance(failures, list):
        violations.append("artifact_ownership_registry_invalid")
        return
    for item in active:
        if not isinstance(item, dict) or not isinstance(item.get("owner_id"), str):
            violations.append("artifact_ownership_registry_invalid")
            continue
        violations.append(f"test_artifact_residual:{item['owner_id']}")
    for item in failures:
        owner_id = item.get("owner_id") if isinstance(item, dict) else None
        violations.append(f"artifact_cleanup_failure:{owner_id or 'unknown'}")


def _audit_database_and_reports(state_root: Path, violations: list[str]) -> None:
    database = state_root / "persistence" / "powerbiagent.db"
    reports_root = state_root / "reports"
    managed_files: set[str] = set()
    if database.exists():
        try:
            with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "report_artifacts" in tables:
                    rows = conn.execute(
                        "SELECT report_id, relative_path FROM report_artifacts"
                    ).fetchall()
                    for report_id, relative_path in rows:
                        expected = f"{report_id}.html"
                        if relative_path != expected or not _REPORT_FILE.fullmatch(expected):
                            violations.append(f"report_metadata_path_invalid:{report_id}")
                            continue
                        managed_files.add(expected)
                        if not (reports_root / expected).is_file():
                            violations.append(f"report_file_missing:{report_id}")
                for table in (
                    "conversation_delete_intents",
                    "report_delete_intents",
                ):
                    if table in tables:
                        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        if count:
                            violations.append(f"artifact_cleanup_pending:{table}:{count}")
        except (OSError, sqlite3.Error):
            violations.append("persistence_governance_read_failed")

    if reports_root.is_dir():
        for path in reports_root.iterdir():
            if path.is_file() and path.suffix.casefold() == ".html":
                if path.name not in managed_files:
                    violations.append(f"orphan_report_html:{path.name}")
            elif path.is_file():
                violations.append(f"unauthorized_report_artifact:{path.name}")
            elif path.is_dir():
                violations.append(f"unauthorized_report_directory:{path.name}")


def _audit_source_tree(project_root: Path, violations: list[str]) -> None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        violations.append("source_tree_artifact_scan_failed")
        return
    for raw in result.stdout.splitlines():
        relative = Path(raw.strip())
        if not relative.parts or relative.parts[0] == "local_state":
            continue
        if relative.suffix.casefold() in _RUNTIME_SUFFIXES:
            violations.append(f"runtime_artifact_in_source_tree:{relative.as_posix()}")
