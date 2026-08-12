#!/usr/bin/env python3
"""PowerBIAgent production architecture gate (AST + ownership)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DIR = REPO_ROOT / "backend" / "app"

FORBIDDEN_IMPORT_ROOTS = ("pydantic_ai", "langgraph")
DELETED_MODULES = ("backend.app.agent.runtime", "backend.app.agent")
FORBIDDEN_CLASS_DEFS = {
    "AgentRuntime", "MockAgentRuntime", "RealTurnPipeline", "LocalTurnPipeline",
    "RemoteTurnPipeline", "PowerBITurnPipeline", "RealTurnService", "LocalTurnService",
}
PROVIDER_FORBIDDEN_DEPENDENCIES = (
    "backend.app.query_plan", "backend.app.answer", "backend.app.report",
    "backend.app.memory", "backend.app.application.turn_pipeline",
)
ADAPTER_METHODS = {"execute_dax", "get_semantic_model_schema"}


class ArchitectureVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath.replace("\\", "/")
        self.violations: list[str] = []
        self._local_names: set[str] = set()
        parts = Path(self.filepath).parts
        try:
            self.owner = parts[parts.index("app") + 1]
        except (ValueError, IndexError):
            self.owner = ""

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"{self.filepath}:{node.lineno}: {message}")

    def _check_import(self, node: ast.AST, module: str) -> None:
        if module == FORBIDDEN_IMPORT_ROOTS[0] or module.startswith("pydantic_ai."):
            self._add(node, f"PydanticAI import: `{module}`")
        if module == FORBIDDEN_IMPORT_ROOTS[1] or module.startswith("langgraph."):
            self._add(node, f"LangGraph import: `{module}`")
        if module in DELETED_MODULES or module.startswith("backend.app.agent.runtime"):
            self._add(node, f"已删除模块 import: `{module}`")
        if self.owner != "powerbi" and (
            module == "mcp" or module.startswith("mcp.")
        ):
            self._add(node, f"MCP SDK import 越界: `{module}`")
        if self.owner == "powerbi" and any(
            module == forbidden or module.startswith(forbidden + ".")
            for forbidden in PROVIDER_FORBIDDEN_DEPENDENCIES
        ):
            self._add(node, f"Power BI Provider 反向依赖业务层: `{module}`")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._check_import(node, node.module or "")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in FORBIDDEN_CLASS_DEFS:
            self._add(node, f"禁止的生产控制面类定义: `class {node.name}`")
        self._local_names.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._local_names.add(node.name)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._local_names.add(target.id)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"AgentRuntime", "MockAgentRuntime"} and node.id not in self._local_names:
            self._add(node, f"可执行代码引用禁止名称: `{node.id}`")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method == "call_tool" and self.owner != "powerbi":
                self._add(node, "raw MCP call_tool 只能位于 Power BI Provider 层")
            if self.owner == "application" and method in ADAPTER_METHODS:
                self._add(node, f"Application Service 绕过 ToolGateway: `{method}()`")
        self.generic_visit(node)


def check_file(filepath: Path, *, display_path: str | None = None) -> list[str]:
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (OSError, UnicodeDecodeError):
        return []
    except SyntaxError as exc:
        return [f"{filepath}:{exc.lineno or 0}: 生产 Python 语法错误"]
    if display_path is None:
        try:
            display_path = str(filepath.resolve().relative_to(REPO_ROOT.resolve()))
        except ValueError:
            display_path = str(filepath.resolve())
    visitor = ArchitectureVisitor(display_path)
    visitor.visit(tree)
    return visitor.violations


def collect_python_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def main() -> int:
    if not PRODUCTION_DIR.is_dir():
        print(f"ERROR: 生产目录不存在: {PRODUCTION_DIR}")
        return 2
    python_files = collect_python_files(PRODUCTION_DIR)
    violations = [item for path in python_files for item in check_file(path)]
    if violations:
        print(f"[FAIL] 发现 {len(violations)} 项架构违规：")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print(f"[PASS] Architecture Gate（{len(python_files)} 个生产 Python 文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
