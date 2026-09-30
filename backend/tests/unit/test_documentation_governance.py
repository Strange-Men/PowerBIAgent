"""Documentation topology and version governance gate regressions."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_documentation_governance as gate


def test_current_repository_documentation_governance_passes():
    assert gate.run_checks() == []


def test_unexpected_root_markdown_is_rejected(tmp_path: Path):
    for name in gate.ROOT_MARKDOWN_WHITELIST:
        (tmp_path / name).write_text("ok", encoding="utf-8")
    (tmp_path / "PRD.md").write_text("duplicate", encoding="utf-8")

    errors = gate.check_root_markdown(tmp_path)

    assert "root_markdown_not_allowed:PRD.md" in errors


def test_docs_root_13_plus_is_rejected(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "13_new_status.md").write_text("forbidden", encoding="utf-8")

    errors = gate.check_required_topology(tmp_path)

    assert "docs_root_numbered_extension_forbidden:13_new_status.md" in errors


def test_deleted_moved_path_reference_is_rejected(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "See docs/12_m2_powerbi_mcp_integration_plan.md", encoding="utf-8"
    )

    errors = gate.check_deleted_path_references(tmp_path)

    assert errors == [
        "deleted_doc_reference:README.md:docs/12_m2_powerbi_mcp_integration_plan.md"
    ]


def _seal_repository(root: Path, marker: str):
    settings = root / "backend/app/config/settings.py"
    settings.parent.mkdir(parents=True)
    settings.write_text('version: str = Field(default="M5.10.9")', encoding="utf-8")
    for relative in gate.CURRENT_STATE_DOCUMENTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = "# CHANGELOG\n\n## [M5.10.9]\n" if relative == "CHANGELOG.md" else ""
        path.write_text(prefix + marker, encoding="utf-8")


def test_m5_seal_rejects_one_stale_current_state_document(tmp_path: Path):
    _seal_repository(tmp_path, "M5.10.9 RELEASE CANDIDATE\nM5 FINAL=false")
    (tmp_path / "CLAUDE.md").write_text(
        "M5.10.8 LOCAL TEST SEAL PASS\nM5 FINAL=false", encoding="utf-8"
    )

    assert "m5_seal_state_mismatch:CLAUDE.md" in gate.check_m5_seal_consistency(tmp_path)


def test_m5_seal_rejects_mixed_candidate_and_complete(tmp_path: Path):
    _seal_repository(tmp_path, "M5.10.9 RELEASE CANDIDATE\nM5 FINAL=false")
    (tmp_path / "README.md").write_text(
        "M5.10.9 COMPLETE\nM5 FINAL=true", encoding="utf-8"
    )

    assert "m5_seal_state_mismatch:README.md" in gate.check_m5_seal_consistency(tmp_path)


def test_m5_final_requires_all_frozen_and_ready_markers(tmp_path: Path):
    _seal_repository(tmp_path, "M5.10.9 COMPLETE\nM5 FINAL=true")

    assert "m5_final_boundary_missing:AGENTS.md" in gate.check_m5_seal_consistency(tmp_path)


def test_m5_seal_does_not_treat_changelog_history_as_current(tmp_path: Path):
    marker = (
        "M5.10.9 COMPLETE\nM5 FINAL=true\nM5 CORE ANALYSIS KERNEL FROZEN\n"
        "LOCAL MVP BASELINE FROZEN\nM6 PRODUCTIONIZATION READY"
    )
    _seal_repository(tmp_path, marker)
    with (tmp_path / "CHANGELOG.md").open("a", encoding="utf-8") as stream:
        stream.write("\n## [M5.10.8]\nM5 FINAL=false\nREMOTE CI PENDING\n")

    assert gate.check_m5_seal_consistency(tmp_path) == []
