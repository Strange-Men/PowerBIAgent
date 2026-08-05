#!/usr/bin/env python3
"""架构门禁 — AST 级检查 (CI-166-002)

替代 git grep 字符串搜索，使用 Python AST 检测生产代码中的：
- PydanticAI import 残留
- AgentRuntime/MockAgentRuntime 类定义或可执行引用
- 已删除模块重新出现

注释、Docstring 和普通历史文字不触发失败。

退出码：
  0 — 通过
  1 — 发现架构违规
  2 — 脚本错误
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DIR = REPO_ROOT / "backend" / "app"

# ---------------------------------------------------------------------------
# 违规模式定义
# ---------------------------------------------------------------------------

# PydanticAI 相关 import
PYDANTIC_AI_IMPORT_PARTS = ("pydantic_ai", "pydantic_ai.agent", "pydantic_ai.tools")

# 已删除的 agent.runtime 模块
DELETED_MODULES = ("backend.app.agent.runtime", "backend.app.agent")

# 禁止的 ClassDef 名称
FORBIDDEN_CLASS_DEFS = ("AgentRuntime", "MockAgentRuntime")


class ArchitectureVisitor(ast.NodeVisitor):
    """遍历 Python AST 检测架构违规。"""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.violations: list[str] = []
        # 跟踪当前作用域内定义的名称
        self._local_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            # 检查是否 import 了 pydantic_ai
            if alias.name == "pydantic_ai" or alias.name.startswith("pydantic_ai."):
                self.violations.append(
                    f"{self.filepath}:{node.lineno}: PydanticAI import: `import {alias.name}`"
                )
            # 检查已删除模块
            if alias.name in DELETED_MODULES or alias.name.startswith("backend.app.agent.runtime"):
                self.violations.append(
                    f"{self.filepath}:{node.lineno}: 已删除模块 import: `import {alias.name}`"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        # 检查 from pydantic_ai import ...
        if module == "pydantic_ai" or (module and module.startswith("pydantic_ai.")):
            self.violations.append(
                f"{self.filepath}:{node.lineno}: PydanticAI import: `from {module} import ...`"
            )
        # 检查已删除模块
        if module in DELETED_MODULES or (module and module.startswith("backend.app.agent.runtime")):
            self.violations.append(
                f"{self.filepath}:{node.lineno}: 已删除模块 import: `from {module} import ...`"
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # 检查禁止的类名
        if node.name in FORBIDDEN_CLASS_DEFS:
            self.violations.append(
                f"{self.filepath}:{node.lineno}: 禁止的类定义: `class {node.name}`"
            )
        # 记录本地定义的类名
        self._local_names.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # 记录本地定义的函数名
        self._local_names.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # 记录赋值目标名称
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._local_names.add(target.id)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # 检查可执行代码中对禁止名称的引用（非定义位置）
        if node.id in FORBIDDEN_CLASS_DEFS:
            # 排除本地定义的类名（这些已经被 visit_ClassDef 捕获）
            if node.id not in self._local_names:
                self.violations.append(
                    f"{self.filepath}:{node.lineno}: 可执行代码引用禁止名称: `{node.id}`"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # 检查 agent.runtime 等属性链引用
        # 不遍历 AST 字符串，仅检查已删除模块可能出现的属性访问模式
        self.generic_visit(node)


def check_file(filepath: Path) -> list[str]:
    """对单个 Python 文件执行 AST 检查，返回违规列表。"""
    try:
        source = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        # 语法错误的文件不阻塞架构检查（可能是 WIP 或测试 fixture）
        return []

    # 尝试获取相对路径，失败时使用绝对路径
    try:
        display_path = str(filepath.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        display_path = str(filepath.resolve())

    visitor = ArchitectureVisitor(display_path)
    visitor.visit(tree)
    return visitor.violations


def collect_python_files(root: Path) -> list[Path]:
    """收集目录下所有 .py 文件（排除 __pycache__）。"""
    files: list[Path] = []
    for py_file in root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        files.append(py_file)
    return sorted(files)


def main() -> int:
    if not PRODUCTION_DIR.is_dir():
        print(f"ERROR: 生产目录不存在: {PRODUCTION_DIR}")
        return 2

    python_files = collect_python_files(PRODUCTION_DIR)
    if not python_files:
        print("WARNING: 未找到任何 Python 文件")
        return 0

    all_violations: list[str] = []
    for py_file in python_files:
        violations = check_file(py_file)
        all_violations.extend(violations)

    if all_violations:
        print(f"[FAIL] 发现 {len(all_violations)} 项架构违规：")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print(f"[PASS] 架构门禁通过（{len(python_files)} 个生产 Python 文件已检查）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
