"""Permanent M5.7.1 semantic compatibility gate."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
KNOWN_CASES = ROOT / "harness" / "cases" / "known_answer_cases.yaml"
EXAMPLE_BASELINE = ROOT / "harness" / "baselines" / "example_known_answers.yaml"
PRODUCTION_TEXT_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".json", ".toml"})
EXCLUDED_PRODUCTION_DIRECTORIES = frozenset({
    "tests",
    "test",
    "harness",
    "docs",
    "generated",
    "cache",
    "caches",
    "__pycache__",
    ".pytest_cache",
    "artifact",
    "artifacts",
})
FRONTEND_TEXT_SUFFIXES = frozenset({
    ".css", ".html", ".js", ".json", ".jsx", ".ts", ".tsx",
})
FORBIDDEN_ORACLE_IMPORT_PREFIXES = (
    "backend.app.harness.cases",
    "backend.app.harness.oracles",
    "backend.tests",
    "harness.cases",
    "harness.oracles",
    "tests",
)
FORBIDDEN_ORACLE_REFERENCE_PATTERNS = (
    re.compile(r"\bknown[\s_-]?answer\b", re.IGNORECASE),
    re.compile(r"\boracle_key\b", re.IGNORECASE),
    re.compile(r"\bexpected[\s_-]?answer\b", re.IGNORECASE),
    re.compile(
        r"(?:backend[./\\]app[./\\])?harness[./\\]"
        r"(?:cases|baselines|oracles)(?:[./\\]|\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\bbackend[./\\]tests(?:[./\\]|\b)", re.IGNORECASE),
)
SEMANTIC_AUTHORITY_FILES = (
    ROOT / "backend" / "app" / "query_plan" / "model_semantic_context.py",
    ROOT / "backend" / "app" / "query_plan" / "model_override.py",
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


def collect_production_backend_files(root: Path = ROOT) -> tuple[Path, ...]:
    """Return all supported production backend text files, deterministically."""

    app_root = root / "backend" / "app"
    if not app_root.is_dir():
        return ()
    return tuple(sorted(
        path
        for path in app_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in PRODUCTION_TEXT_SUFFIXES
        and not any(
            part.casefold() in EXCLUDED_PRODUCTION_DIRECTORIES
            for part in path.relative_to(app_root).parts[:-1]
        )
    ))


def _collect_frontend_production_files(root: Path) -> tuple[Path, ...]:
    source_root = root / "frontend" / "src"
    if not source_root.is_dir():
        return ()
    return tuple(sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in FRONTEND_TEXT_SUFFIXES
        and ".test." not in path.name.casefold()
        and ".spec." not in path.name.casefold()
        and "__tests__" not in {
            part.casefold() for part in path.relative_to(source_root).parts[:-1]
        }
    ))


def _read_text_files(
    root: Path,
    paths: tuple[Path, ...],
    violations: list[str],
) -> dict[str, str]:
    text: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            text[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"production_text_not_utf8:{relative}")
    return text


def _distinctive_expected_values(baselines: Any) -> frozenset[Decimal]:
    values: set[Decimal] = set()
    for value in _walk_values(baselines):
        if not isinstance(value, float) or float(value).is_integer():
            continue
        values.add(Decimal(str(value)))
    return frozenset(values)


def _numeric_tokens(content: str):
    for match in re.finditer(
        r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\w.])",
        content,
    ):
        try:
            yield match.group(0), Decimal(match.group(0))
        except InvalidOperation:
            continue


def _is_forbidden_oracle_import(module: str) -> bool:
    normalized = module.casefold()
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_ORACLE_IMPORT_PREFIXES
    )


def _collect_python_dependency_violations(
    relative: str,
    content: str,
) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [f"production_python_parse_error:{relative}"]

    for node in ast.walk(tree):
        modules: tuple[str, ...] = ()
        if isinstance(node, ast.Import):
            modules = tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = (node.module,)
        for module in modules:
            if _is_forbidden_oracle_import(module):
                violations.append(
                    f"production_oracle_dependency:{relative}:{module}"
                )
    return violations


def collect_static_violations(root: Path = ROOT) -> list[str]:
    """Check committed production inputs without reading local or secret state."""

    known_cases = root / KNOWN_CASES.relative_to(ROOT)
    example_baseline = root / EXAMPLE_BASELINE.relative_to(ROOT)
    cases = yaml.safe_load(known_cases.read_text(encoding="utf-8"))["cases"]
    baselines = yaml.safe_load(example_baseline.read_text(encoding="utf-8"))[
        "baselines"
    ]
    violations: list[str] = []
    production_text = _read_text_files(
        root, collect_production_backend_files(root), violations
    )
    frontend_text = _read_text_files(
        root, _collect_frontend_production_files(root), violations
    )

    for case in cases:
        normalized_question = _normalized_text(str(case["message"]))
        for relative, content in production_text.items():
            if normalized_question in _normalized_text(content):
                violations.append(
                    f"benchmark_question_leak:{relative}:{case['id']}"
                )

    distinctive_values = _distinctive_expected_values(baselines)
    for relative, content in {**production_text, **frontend_text}.items():
        for literal, numeric_value in _numeric_tokens(content):
            if numeric_value in distinctive_values:
                violations.append(
                    f"benchmark_value_leak:{relative}:{literal}"
                )

    for relative, content in production_text.items():
        for pattern in FORBIDDEN_ORACLE_REFERENCE_PATTERNS:
            match = pattern.search(content)
            if match:
                violations.append(
                    f"production_oracle_reference:{relative}:{match.group(0)}"
                )
        if relative.endswith(".py"):
            violations.extend(
                _collect_python_dependency_violations(relative, content)
            )

    for path in SEMANTIC_AUTHORITY_FILES:
        scoped_path = root / path.relative_to(ROOT)
        if not scoped_path.is_file():
            continue
        source = scoped_path.read_text(encoding="utf-8").casefold()
        relative = scoped_path.relative_to(root).as_posix()
        if "backend.app.llm.deepseek" in source:
            violations.append(f"provider_specific_semantic_authority:{relative}")

    return sorted(set(violations))


def main() -> int:
    production_files = collect_production_backend_files()
    violations = collect_static_violations()
    if violations:
        print("Semantic Compatibility Gate: FAIL")
        print(f"Production backend files scanned: {len(production_files)}")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(f"Production backend files scanned: {len(production_files)}")

    env = os.environ.copy()
    env.update({
        "LLM_MODE": "mock",
        "POWERBI_MODE": "mock",
        "PERSISTENCE_BACKEND": "memory",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    test_paths = [
        "backend/tests/unit/test_cross_language_grounding.py",
        "backend/tests/api/test_cross_language_grounding.py",
        "backend/tests/unit/test_model_semantic_context.py",
        "backend/tests/api/test_model_semantic_context.py",
        "backend/tests/unit/test_question_routing.py",
        "backend/tests/unit/test_semantic_compatibility.py",
        "backend/tests/unit/test_semantic_grounding.py",
        "backend/tests/unit/test_intent.py",
        "backend/tests/unit/test_deterministic_dax.py",
        "backend/tests/unit/test_verified_facts.py",
        "backend/tests/unit/test_known_answer_oracle.py",
        "backend/tests/api/test_chat.py",
        "backend/tests/integration/test_multi_turn_benchmark.py",
    ]
    command = [
        sys.executable,
        "-m",
        "pytest",
        *(str(ROOT / path) for path in test_paths),
        "-q",
    ]
    env["PYTHONPATH"] = str(ROOT)
    # Run outside the repository so developer-local .env values cannot affect
    # this deterministic CI-equivalent gate.
    with tempfile.TemporaryDirectory(prefix="powerbiagent-semantic-") as run_dir:
        result = subprocess.run(command, cwd=run_dir, env=env, check=False)
    if result.returncode:
        print("Semantic Compatibility Gate: FAIL")
        return result.returncode
    print("Semantic Compatibility Gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
