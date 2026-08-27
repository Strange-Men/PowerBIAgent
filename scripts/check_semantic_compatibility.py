"""Permanent M5.7.1 semantic compatibility gate."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
KNOWN_CASES = ROOT / "harness" / "cases" / "known_answer_cases.yaml"
EXAMPLE_BASELINE = ROOT / "harness" / "baselines" / "example_known_answers.yaml"
SENSITIVE_FILES = (
    ROOT / "backend" / "app" / "intent" / "prompt.py",
    ROOT / "backend" / "app" / "query_plan" / "prompt.py",
    ROOT / "backend" / "app" / "query_plan" / "business_glossary.yaml",
    ROOT / "backend" / "app" / "config" / "settings.py",
)
SEMANTIC_AUTHORITY_FILES = (
    ROOT / "backend" / "app" / "query_plan" / "grounding.py",
    ROOT / "backend" / "app" / "query_plan" / "semantic_catalog.py",
    ROOT / "backend" / "app" / "query_plan" / "state_transition.py",
    ROOT / "backend" / "app" / "dax" / "builder.py",
    ROOT / "backend" / "app" / "facts" / "verified.py",
)


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s，。！？、,.!?；;：:'\"`]+", "", normalized)


def _walk_values(value: Any):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


def collect_static_violations() -> list[str]:
    """Check committed production inputs without reading local or secret state."""

    cases = yaml.safe_load(KNOWN_CASES.read_text(encoding="utf-8"))["cases"]
    baselines = yaml.safe_load(EXAMPLE_BASELINE.read_text(encoding="utf-8"))[
        "baselines"
    ]
    sensitive_text = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in SENSITIVE_FILES
    }
    frontend_text = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend" / "src").rglob("*")
        if path.is_file() and ".test." not in path.name
    }
    violations: list[str] = []

    for case in cases:
        normalized_question = _normalized_text(str(case["message"]))
        oracle_key = str(case["oracle_key"])
        for relative, content in sensitive_text.items():
            if normalized_question in _normalized_text(content):
                violations.append(
                    f"benchmark_question_leak:{relative}:{case['id']}"
                )
            if oracle_key in content:
                violations.append(f"oracle_key_leak:{relative}:{oracle_key}")

    distinctive_values = {
        format(float(value), ".10g")
        for value in _walk_values(baselines)
        if isinstance(value, float) and not float(value).is_integer()
    }
    for relative, content in {**sensitive_text, **frontend_text}.items():
        for value in distinctive_values:
            if re.search(rf"(?<![\d.]){re.escape(value)}(?![\d.])", content):
                violations.append(f"benchmark_value_leak:{relative}:{value}")

    for path in SEMANTIC_AUTHORITY_FILES:
        source = path.read_text(encoding="utf-8").casefold()
        relative = path.relative_to(ROOT).as_posix()
        if "backend.app.llm.deepseek" in source:
            violations.append(f"provider_specific_semantic_authority:{relative}")

    return sorted(set(violations))


def main() -> int:
    violations = collect_static_violations()
    if violations:
        print("Semantic Compatibility Gate: FAIL")
        for violation in violations:
            print(f"- {violation}")
        return 1

    env = os.environ.copy()
    env.update({
        "LLM_MODE": "mock",
        "POWERBI_MODE": "mock",
        "PERSISTENCE_BACKEND": "memory",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    command = [
        sys.executable,
        "-m",
        "pytest",
        "backend/tests/unit/test_semantic_compatibility.py",
        "backend/tests/unit/test_semantic_grounding.py",
        "backend/tests/unit/test_intent.py",
        "backend/tests/unit/test_deterministic_dax.py",
        "backend/tests/unit/test_known_answer_oracle.py",
        "backend/tests/api/test_chat.py",
        "backend/tests/integration/test_multi_turn_benchmark.py",
        "-q",
    ]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode:
        print("Semantic Compatibility Gate: FAIL")
        return result.returncode
    print("Semantic Compatibility Gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
