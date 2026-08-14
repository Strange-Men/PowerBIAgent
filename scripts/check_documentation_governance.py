#!/usr/bin/env python3
"""Deterministic documentation topology and version governance gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_MARKDOWN_WHITELIST = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "PROJECT_CHARTER.md",
    "CHANGELOG.md",
}
REQUIRED_PATHS = (
    "docs/index.md",
    "docs/specs",
    "docs/milestones",
    "docs/archive",
    "docs/adr",
    "docs/08_development_roadmap.md",
    "docs/09_context_handoff.md",
    "docs/00_product_requirements_document.md",
)
MOVED_DOCS = (
    (
        "docs/10_frontend_visual_and_interaction_spec.md",
        "docs/specs/10_frontend_visual_and_interaction_spec.md",
    ),
    (
        "docs/11_structured_answer_contract.md",
        "docs/specs/11_structured_answer_contract.md",
    ),
    (
        "docs/12_m2_powerbi_mcp_integration_plan.md",
        "docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md",
    ),
)
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_SETTINGS_VERSION = re.compile(
    r'version\s*:\s*str\s*=\s*Field\(default="(M\d+\.\d+(?:\.\d+)?)"'
)
_EXCLUDED_MARKDOWN_PARTS = {".git", ".pytest_cache", "local_state", "node_modules"}


def iter_repository_markdown(root: Path):
    for markdown in root.rglob("*.md"):
        try:
            relative_parts = markdown.relative_to(root).parts
        except ValueError:
            continue
        if any(part in _EXCLUDED_MARKDOWN_PARTS for part in relative_parts):
            continue
        yield markdown


def check_root_markdown(root: Path) -> list[str]:
    found = {path.name for path in root.glob("*.md")}
    errors = [
        f"root_markdown_not_allowed:{name}"
        for name in sorted(found - ROOT_MARKDOWN_WHITELIST)
    ]
    errors.extend(
        f"root_markdown_missing:{name}"
        for name in sorted(ROOT_MARKDOWN_WHITELIST - found)
    )
    return errors


def check_required_topology(root: Path) -> list[str]:
    errors = [
        f"required_path_missing:{path}"
        for path in REQUIRED_PATHS
        if not (root / path).exists()
    ]
    if (root / "PRD.md").exists():
        errors.append("prd_duplicate_root:PRD.md")
    docs_root = root / "docs"
    if docs_root.is_dir():
        for path in docs_root.glob("*.md"):
            match = re.match(r"^(\d+)_", path.name)
            if match and int(match.group(1)) >= 13:
                errors.append(f"docs_root_numbered_extension_forbidden:{path.name}")
    for old, new in MOVED_DOCS:
        if (root / old).exists():
            errors.append(f"moved_doc_old_path_present:{old}")
        if not (root / new).is_file():
            errors.append(f"moved_doc_new_path_missing:{new}")
    return errors


def check_deleted_path_references(root: Path) -> list[str]:
    errors: list[str] = []
    old_paths = tuple(old for old, _ in MOVED_DOCS)
    for markdown in iter_repository_markdown(root):
        text = markdown.read_text(encoding="utf-8")
        relative = markdown.relative_to(root).as_posix()
        for old in old_paths:
            if old in text:
                errors.append(f"deleted_doc_reference:{relative}:{old}")
    return errors


def check_relative_markdown_links(root: Path) -> list[str]:
    errors: list[str] = []
    for markdown in iter_repository_markdown(root):
        text = markdown.read_text(encoding="utf-8")
        for raw_target in _MARKDOWN_LINK.findall(text):
            target = raw_target.strip()
            if target.startswith("<") and ">" in target:
                target = target[1:target.index(">")]
            else:
                target = target.split(maxsplit=1)[0]
            if (
                not target
                or target.startswith(("http://", "https://", "mailto:", "#", "/"))
                or re.match(r"^[A-Za-z]:[\\/]", target)
            ):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            resolved = (markdown.parent / target).resolve()
            if not resolved.exists():
                relative = markdown.relative_to(root).as_posix()
                errors.append(
                    f"relative_markdown_link_missing:{relative}:{raw_target}"
                )
    return errors


def current_version(root: Path) -> str | None:
    settings = root / "backend/app/config/settings.py"
    if not settings.is_file():
        return None
    match = _SETTINGS_VERSION.search(settings.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check_version_consistency(root: Path) -> list[str]:
    version = current_version(root)
    if version is None:
        return ["settings_version_not_found"]
    checks = {
        "AGENTS.md": lambda text: f"当前版本：**{version}" in text,
        "README.md": lambda text: f"当前版本：**{version}" in text,
        "CHANGELOG.md": lambda text: bool(
            re.search(r"^## \[" + re.escape(version) + r"\]", text, re.MULTILINE)
        ) and re.search(r"^## \[(M[^\]]+)\]", text, re.MULTILINE).group(1) == version,
        "docs/07_milestones_status_and_open_questions.md": lambda text: version in text[:300],
        "docs/08_development_roadmap.md": lambda text: version in text[:300],
        "docs/09_context_handoff.md": lambda text: version in text[:500],
    }
    errors: list[str] = []
    for relative, predicate in checks.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"version_document_missing:{relative}")
            continue
        try:
            matches = predicate(path.read_text(encoding="utf-8"))
        except (AttributeError, OSError):
            matches = False
        if not matches:
            errors.append(f"version_mismatch:{relative}:{version}")
    return errors


def run_checks(root: Path = REPO_ROOT) -> list[str]:
    return [
        *check_root_markdown(root),
        *check_required_topology(root),
        *check_deleted_path_references(root),
        *check_relative_markdown_links(root),
        *check_version_consistency(root),
    ]


def main() -> int:
    errors = run_checks()
    if errors:
        print(f"[FAIL] Documentation Governance（{len(errors)} 项）")
        for error in errors:
            print(f"  {error}")
        return 1
    print("[PASS] Documentation Governance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
