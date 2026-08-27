"""Static checks owned by the permanent Semantic Compatibility Gate."""

from pathlib import Path

import pytest

from scripts.check_semantic_compatibility import (
    EXCLUDED_PRODUCTION_DIRECTORIES,
    PRODUCTION_TEXT_SUFFIXES,
    collect_production_backend_files,
    collect_static_violations,
)


def test_no_benchmark_answer_or_provider_authority_leakage():
    assert collect_static_violations() == []


def test_complete_production_backend_text_boundary_is_scanned():
    files = collect_production_backend_files()

    assert files
    assert all(path.suffix.casefold() in PRODUCTION_TEXT_SUFFIXES for path in files)
    assert all("backend/app" in path.as_posix() for path in files)
    assert all(
        not set(part.casefold() for part in path.parts)
        & EXCLUDED_PRODUCTION_DIRECTORIES
        for path in files
    )
    assert any(path.name == "main.py" for path in files)
    assert any(path.name == "business_glossary.yaml" for path in files)


def _write_oracle_sources(root: Path) -> None:
    cases = root / "harness" / "cases" / "known_answer_cases.yaml"
    baseline = root / "harness" / "baselines" / "example_known_answers.yaml"
    cases.parent.mkdir(parents=True)
    baseline.parent.mkdir(parents=True)
    cases.write_text(
        "cases:\n"
        "  - id: sample\n"
        "    message: '总销售额是多少？'\n"
        "    oracle_key: total_sales\n",
        encoding="utf-8",
    )
    baseline.write_text(
        "baselines:\n"
        "  - oracle_key: total_sales\n"
        "    expected_value: 1000.25\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("relative_path", "content", "expected_code"),
    [
        (
            "backend/app/service.py",
            "PROMPT = '总销售额是多少？'\n",
            "benchmark_question_leak",
        ),
        (
            "backend/app/config.yaml",
            "fallback_value: 1000.2500\n",
            "benchmark_value_leak",
        ),
        (
            "backend/app/service.py",
            "oracle_key = 'total_sales'\n",
            "production_oracle_reference",
        ),
        (
            "backend/app/service.py",
            "from backend.app.harness.oracles.known_answer import KnownAnswerOracle\n",
            "production_oracle_dependency",
        ),
        (
            "backend/app/service.py",
            "ORACLE = 'harness/cases/known_answer_cases.yaml'\n",
            "production_oracle_reference",
        ),
    ],
)
def test_production_leakage_and_oracle_dependencies_fail_closed(
    tmp_path: Path,
    relative_path: str,
    content: str,
    expected_code: str,
):
    _write_oracle_sources(tmp_path)
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    violations = collect_static_violations(tmp_path)

    assert any(item.startswith(f"{expected_code}:") for item in violations)


def test_harness_tests_generated_cache_and_binary_are_excluded(tmp_path: Path):
    _write_oracle_sources(tmp_path)
    leaked = "PROMPT = '总销售额是多少？'\nVALUE = 1000.25\n"
    excluded_paths = (
        "backend/app/harness/cases/leak.py",
        "backend/app/tests/leak.py",
        "backend/app/docs/leak.yaml",
        "backend/app/generated/leak.json",
        "backend/app/cache/leak.toml",
        "backend/app/__pycache__/leak.py",
        "backend/app/artifacts/leak.json",
        "backend/app/leak.bin",
        "frontend/src/Widget.test.tsx",
    )
    for relative in excluded_paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(leaked, encoding="utf-8")
    production = tmp_path / "backend" / "app" / "service.py"
    production.write_text("SAFE = True\n", encoding="utf-8")

    assert collect_production_backend_files(tmp_path) == (production,)
    assert collect_static_violations(tmp_path) == []
