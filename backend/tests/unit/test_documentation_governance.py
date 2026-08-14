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
