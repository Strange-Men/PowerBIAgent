"""Documentation topology and version governance gate regressions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


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


def _semantic_repository(root: Path):
    _seal_repository(root, (
        "M5.10.9 COMPLETE\nM5 FINAL=true\nM5 CORE ANALYSIS KERNEL FROZEN\n"
        "LOCAL MVP BASELINE FROZEN\nM6 PRODUCTIONIZATION READY\n"
    ))
    files = {
        "docs/00_product_requirements_document.md": (
            "当前 QueryShape：SCALAR ENTITY_LIST GROUPED RANKING MEMBER_SET "
            "FILTERED_AGGREGATION TREND BOUNDED_TREND\n"
            "当前模型目录：sales_report / sales_executive_report；model-aware。\n"
        ),
        "docs/01_product_scope_and_frontend_skeleton.md":
            "当前模型目录：sales_report / sales_executive_report；model-aware。\n",
        "docs/adr/README.md": (
            "### ADR-019 — Template Authority\n"
            "ReadingContext / immutable snapshot / SALES_QUERY_REQUIREMENTS\n"
        ),
        "docs/specs/10_frontend_visual_and_interaction_spec.md": (
            "| Eligibility | Policy |\n"
            "| domain-ineligible | not_returned |\n"
            "| domain-matched | capability_validation |\n"
        ),
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize("relative,stale", [
    ("AGENTS.md", "本轮不进入 M6 implementation。"),
    ("AGENTS.md", "当前只做治理、version 与 12px CSS polish，不做 M6 implementation。"),
    ("CLAUDE.md", "最终条件成立立即停止，不启动 M6。"),
    ("CLAUDE.md", "本轮不实现 Cloud/Entra/存储/migration/M6。"),
    ("CLAUDE.md", "M5.10.9_文档治理与最终封板候选 → M5.10.9_M5最终封板"),
    ("docs/09_context_handoff.md", "本轮结束后停止，不自动开始 M6。"),
    ("docs/09_context_handoff.md", "本轮禁止 Entra/Fabric IQ/PostgreSQL/Blob/Redis/migration/M6 implementation。"),
    ("docs/09_context_handoff.md", "当前阶段 — M5.10.9 — Documentation Governance & M5 Final Seal"),
])
def test_final_ready_rejects_construction_instructions(tmp_path: Path, relative, stale):
    _semantic_repository(tmp_path)
    with (tmp_path / relative).open("a", encoding="utf-8") as stream:
        stream.write(stale)
    assert f"semantic_stale_m5_instruction:{relative}" in gate.check_current_semantics(tmp_path)


@pytest.mark.parametrize("relative,stale", [
    ("docs/00_product_requirements_document.md", "当前 production catalog 只有 `sales_report`。"),
    ("docs/01_product_scope_and_frontend_skeleton.md", "当前唯一公开模板为 `sales_report / 简易模板`。"),
    ("docs/00_product_requirements_document.md", "当前仅 `sales_report / 简易模板`。"),
    ("docs/01_product_scope_and_frontend_skeleton.md", "Current catalog: only sales_report."),
    ("docs/01_product_scope_and_frontend_skeleton.md", "当前只有简易模板。"),
])
def test_current_contract_rejects_single_template_claim(tmp_path: Path, relative, stale):
    _semantic_repository(tmp_path)
    with (tmp_path / relative).open("a", encoding="utf-8") as stream:
        stream.write(stale)
    assert f"semantic_single_template_catalog:{relative}" in gate.check_current_semantics(tmp_path)


def test_adr_index_rejects_stale_professional_availability(tmp_path: Path):
    _semantic_repository(tmp_path)
    with (tmp_path / "docs/adr/README.md").open("a", encoding="utf-8") as stream:
        stream.write("专业销售模板保持 unavailable。")
    assert "semantic_adr019_availability:docs/adr/README.md" in gate.check_current_semantics(tmp_path)


@pytest.mark.parametrize("mutation", ["disabled", "incompatible", "missing", "missing_layer2"])
def test_frontend_domain_eligibility_contract_is_required(tmp_path: Path, mutation):
    _semantic_repository(tmp_path)
    path = tmp_path / "docs/specs/10_frontend_visual_and_interaction_spec.md"
    content = path.read_text(encoding="utf-8")
    if mutation == "missing":
        content = content.replace("domain-ineligible", "unknown")
    elif mutation == "missing_layer2":
        content = content.replace("capability_validation", "not_validated")
    else:
        content = content.replace("not_returned", mutation)
    path.write_text(content, encoding="utf-8")
    assert f"semantic_domain_eligibility:{path.relative_to(tmp_path).as_posix()}" in gate.check_current_semantics(tmp_path)


def test_current_prd_requires_all_eight_supported_query_shapes(tmp_path: Path):
    _semantic_repository(tmp_path)
    path = tmp_path / "docs/00_product_requirements_document.md"
    path.write_text(path.read_text(encoding="utf-8").replace("BOUNDED_TREND", ""), encoding="utf-8")
    assert "semantic_query_shapes:docs/00_product_requirements_document.md" in gate.check_current_semantics(tmp_path)


def test_current_semantics_accepts_approved_m6_and_preserves_history(tmp_path: Path):
    _semantic_repository(tmp_path)
    historical = (
        "\n## Historical — M5.10.9\n本轮不进入 M6 implementation。\n"
        "### Phase A\nM5 FINAL=false；当前 production catalog 只有 sales_report。\n"
        "专业销售模板保持 unavailable。\n"
        "## Future approved scope\nM6 implementation 需用户批准与官方 contract 验证。\n"
    )
    for relative in ("AGENTS.md", "CLAUDE.md", "docs/09_context_handoff.md",
                     "docs/00_product_requirements_document.md", "docs/01_product_scope_and_frontend_skeleton.md",
                     "docs/adr/README.md", "docs/specs/10_frontend_visual_and_interaction_spec.md"):
        with (tmp_path / relative).open("a", encoding="utf-8") as stream:
            stream.write(historical)
    for relative in ("docs/archive/old.md", "docs/milestones/m5/old.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(historical, encoding="utf-8")
    assert gate.check_current_semantics(tmp_path) == []


def test_construction_rule_after_historical_section_is_still_current(tmp_path: Path):
    _semantic_repository(tmp_path)
    with (tmp_path / "AGENTS.md").open("a", encoding="utf-8") as stream:
        stream.write("\n## Historical\n本轮不进入 M6 implementation。\n"
                     "## Current\n本轮不进入 M6 implementation。\n")
    assert "semantic_stale_m5_instruction:AGENTS.md" in gate.check_current_semantics(tmp_path)
