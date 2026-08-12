"""架构门禁 AST 检查单元测试 (CI-166-002)

验证：
1. 注释中 AgentRuntime 不触发失败
2. import backend.app.agent.runtime 必须失败
3. class AgentRuntime 必须失败
4. 可执行代码引用 AgentRuntime 必须失败
5. PydanticAI import 必须失败
"""

from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# 将 scripts 目录加入 sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_architecture_gate as gate


class TestArchitectureGateAST:
    """AST 检查器单元测试：直接测试 ArchitectureVisitor。"""

    def test_comment_agentruntime_does_not_fail(self) -> None:
        """注释中出现 AgentRuntime 不应触发失败。"""
        source = textwrap.dedent("""\
            # This module previously used AgentRuntime for agent orchestration.
            # MockAgentRuntime was the test double for AgentRuntime.
            # Both have been removed per ADR-005.

            def some_function():
                '''Docstring mentioning AgentRuntime for historical context.'''
                return "no AgentRuntime here"
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0, (
            f"注释中的 AgentRuntime 不应触发违规，但发现了: {visitor.violations}"
        )

    def test_import_agent_runtime_must_fail(self) -> None:
        """import backend.app.agent.runtime 必须触发失败。"""
        source = textwrap.dedent("""\
            import backend.app.agent.runtime
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "import backend.app.agent.runtime 必须触发架构违规"
        )
        assert any("已删除模块" in v for v in visitor.violations), (
            f"违规应提及已删除模块: {visitor.violations}"
        )

    def test_from_agent_runtime_import_must_fail(self) -> None:
        """from backend.app.agent.runtime import AgentRuntime 必须触发失败。"""
        source = textwrap.dedent("""\
            from backend.app.agent.runtime import AgentRuntime
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "from backend.app.agent.runtime import 必须触发架构违规"
        )

    def test_class_agentruntime_must_fail(self) -> None:
        """class AgentRuntime 定义必须触发失败。"""
        source = textwrap.dedent("""\
            class AgentRuntime:
                def execute(self):
                    pass
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "class AgentRuntime 定义必须触发架构违规"
        )

    def test_class_mock_agentruntime_must_fail(self) -> None:
        """class MockAgentRuntime 定义必须触发失败。"""
        source = textwrap.dedent("""\
            class MockAgentRuntime:
                pass
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "class MockAgentRuntime 定义必须触发架构违规"
        )

    def test_executable_name_agentruntime_must_fail(self) -> None:
        """可执行代码中 AgentRuntime 名称引用必须触发失败。"""
        source = textwrap.dedent("""\
            def create_agent():
                return AgentRuntime()
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "可执行代码中的 AgentRuntime 引用必须触发架构违规"
        )

    def test_import_pydantic_ai_must_fail(self) -> None:
        """import pydantic_ai 必须触发失败。"""
        source = textwrap.dedent("""\
            import pydantic_ai
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, "import pydantic_ai 必须触发架构违规"

    def test_from_pydantic_ai_import_agent_must_fail(self) -> None:
        """from pydantic_ai import Agent 必须触发失败。"""
        source = textwrap.dedent("""\
            from pydantic_ai import Agent
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) >= 1, (
            "from pydantic_ai import 必须触发架构违规"
        )

    def test_normal_code_passes(self) -> None:
        """正常 TurnPipeline 代码应通过检查。"""
        source = textwrap.dedent("""\
            from backend.app.agent.turn_pipeline import TurnPipeline
            from backend.app.agent.tool_gateway import ToolGateway

            class TurnService:
                def __init__(self, pipeline: TurnPipeline, gateway: ToolGateway):
                    self.pipeline = pipeline
                    self.gateway = gateway

                async def execute(self, request):
                    return await self.pipeline.execute(request)
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0, (
            f"正常 TurnPipeline 代码不应触发违规: {visitor.violations}"
        )

    def test_string_literal_agentruntime_passes(self) -> None:
        """字符串字面量中的 AgentRuntime 不应触发失败。"""
        source = textwrap.dedent("""\
            MIGRATION_NOTE = "Replaced AgentRuntime with TurnPipeline per ADR-005"
            REMOVED_CLASSES = ["AgentRuntime", "MockAgentRuntime"]

            def log_migration():
                print("AgentRuntime has been removed.")
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0, (
            f"字符串字面量中的 AgentRuntime 不应触发违规: {visitor.violations}"
        )

    def test_comment_with_pydantic_ai_passes(self) -> None:
        """注释中的 pydantic_ai 不应触发失败。"""
        source = textwrap.dedent("""\
            # Previously we used pydantic_ai as the agent framework.
            # This was removed in M1.6.3 per ADR-005.
            def do_work():
                pass
        """)
        tree = ast.parse(source, filename="test_file.py")
        visitor = gate.ArchitectureVisitor("test_file.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0, (
            f"注释中的 pydantic_ai 不应触发违规: {visitor.violations}"
        )

    @pytest.mark.parametrize("owner", [
        "application", "api", "answer", "query_plan", "dax",
    ])
    def test_business_owner_import_mcp_fails(self, owner: str) -> None:
        tree = ast.parse("from mcp import Client\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor(f"backend/app/{owner}/bad.py")
        visitor.visit(tree)
        assert any("MCP SDK import 越界" in item for item in visitor.violations)

    def test_powerbi_owner_import_mcp_passes(self) -> None:
        tree = ast.parse("from mcp import Client\n", filename="provider.py")
        visitor = gate.ArchitectureVisitor("backend/app/powerbi/provider.py")
        visitor.visit(tree)
        assert visitor.violations == []

    def test_raw_call_tool_outside_provider_fails(self) -> None:
        tree = ast.parse("client.call_tool('x')\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor("backend/app/api/bad.py")
        visitor.visit(tree)
        assert any("raw MCP call_tool" in item for item in visitor.violations)

    @pytest.mark.parametrize("class_name", [
        "RealTurnPipeline", "LocalTurnPipeline", "RemoteTurnPipeline",
        "PowerBITurnPipeline", "RealTurnService", "LocalTurnService",
    ])
    def test_parallel_production_control_plane_fails(self, class_name: str) -> None:
        tree = ast.parse(f"class {class_name}:\n    pass\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor("backend/app/application/bad.py")
        visitor.visit(tree)
        assert any("生产控制面" in item for item in visitor.violations)

    @pytest.mark.parametrize(
        "method", ["execute_dax", "get_semantic_model_schema"]
    )
    def test_application_direct_adapter_call_fails(self, method: str) -> None:
        tree = ast.parse(f"await adapter.{method}(request)\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor("backend/app/application/bad.py")
        visitor.visit(tree)
        assert any("绕过 ToolGateway" in item for item in visitor.violations)

    @pytest.mark.parametrize("module", [
        "backend.app.memory.repository",
        "backend.app.answer.deepseek_service",
        "backend.app.query_plan.deepseek_service",
        "backend.app.application.turn_pipeline",
    ])
    def test_provider_reverse_business_dependency_fails(self, module: str) -> None:
        tree = ast.parse(f"import {module}\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor("backend/app/powerbi/bad.py")
        visitor.visit(tree)
        assert any("反向依赖业务层" in item for item in visitor.violations)

    def test_langgraph_import_fails(self) -> None:
        tree = ast.parse("import langgraph\n", filename="bad.py")
        visitor = gate.ArchitectureVisitor("backend/app/application/bad.py")
        visitor.visit(tree)
        assert any("LangGraph" in item for item in visitor.violations)


class TestArchitectureGateFileCheck:
    """文件级检查测试：使用临时文件。"""

    def test_clean_file_passes(self) -> None:
        """干净的生产代码文件应通过检查。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(textwrap.dedent("""\
                '''TurnPipeline — deterministic execution pipeline.'''
                from backend.app.config.settings import Settings

                class TurnPipeline:
                    '''Replaced AgentRuntime with deterministic pipeline.'''
                    async def execute(self, request):
                        return await self._do_execute(request)
            """))
            tmp_path = Path(f.name)

        try:
            violations = gate.check_file(tmp_path)
            assert len(violations) == 0, (
                f"干净文件不应触发违规: {violations}"
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_file_with_agentruntime_class_fails(self) -> None:
        """包含 class AgentRuntime 的文件必须触发违规。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(textwrap.dedent("""\
                class AgentRuntime:
                    pass
            """))
            tmp_path = Path(f.name)

        try:
            violations = gate.check_file(tmp_path)
            assert len(violations) >= 1, (
                "包含 class AgentRuntime 的文件必须触发违规"
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_file_with_pydantic_ai_import_fails(self) -> None:
        """包含 pydantic_ai import 的文件必须触发违规。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("from pydantic_ai import Agent\n")
            tmp_path = Path(f.name)

        try:
            violations = gate.check_file(tmp_path)
            assert len(violations) >= 1, (
                "包含 pydantic_ai import 的文件必须触发违规"
            )
        finally:
            tmp_path.unlink(missing_ok=True)


class TestArchitectureGateMain:
    """主函数集成测试。"""

    def test_main_no_violations(self, monkeypatch) -> None:
        """测试 main 函数在无违规时返回 0。"""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            inner_app = tmp_path / "backend" / "app"
            inner_app.mkdir(parents=True)
            (inner_app / "__init__.py").write_text("")
            (inner_app / "clean_module.py").write_text(
                "def hello(): return 'world'\n"
            )

            # 临时替换 PRODUCTION_DIR
            monkeypatch.setattr(gate, "PRODUCTION_DIR", inner_app)
            result = gate.main()
            assert result == 0, f"无违规应返回 0，实际返回 {result}"

    def test_main_with_violations(self, monkeypatch) -> None:
        """测试 main 函数在有违规时返回 1。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            inner_app = tmp_path / "backend" / "app"
            inner_app.mkdir(parents=True)
            (inner_app / "__init__.py").write_text("")
            (inner_app / "bad_module.py").write_text(
                "class AgentRuntime:\n    pass\n"
            )

            monkeypatch.setattr(gate, "PRODUCTION_DIR", inner_app)
            result = gate.main()
            assert result == 1, f"有违规应返回 1，实际返回 {result}"

    def test_main_missing_dir(self, monkeypatch) -> None:
        """测试 main 函数在目录不存在时返回 2。"""
        monkeypatch.setattr(gate, "PRODUCTION_DIR", Path("/nonexistent/path"))
        result = gate.main()
        assert result == 2, f"目录不存在应返回 2，实际返回 {result}"
