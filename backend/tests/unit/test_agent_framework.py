"""M1.6.3 — Agent 抽象清理回归测试

验证：
1. AgentRuntime 已删除（不可导入）
2. PydanticAI 不在生产代码引用中
3. TurnPipeline 共享骨架可被 Mock 和 DeepSeek 使用
"""

import pytest


class TestAgentRuntimeRemoved:
    """验证旧 AgentRuntime 抽象已完全删除"""

    def test_agent_runtime_cannot_be_imported(self):
        """AgentRuntime 无法从 backend.app.agent 导入"""
        with pytest.raises(ImportError):
            from backend.app.agent import AgentRuntime  # noqa: F401

    def test_agent_run_result_cannot_be_imported(self):
        """AgentRunResult 无法从 backend.app.agent 导入"""
        with pytest.raises(ImportError):
            from backend.app.agent import AgentRunResult  # noqa: F401

    def test_mock_agent_runtime_cannot_be_imported(self):
        """MockAgentRuntime 无法导入"""
        with pytest.raises(ImportError):
            from backend.app.agent.mock_runtime import MockAgentRuntime  # noqa: F401

    def test_agent_module_does_not_exist(self):
        """backend.app.agent 模块已不存在"""
        import importlib
        spec = importlib.util.find_spec("backend.app.agent")
        assert spec is None, "backend.app.agent module should not exist"


class TestPydanticAIRemoved:
    """验证 PydanticAI 依赖已移除"""

    def test_no_pydantic_ai_in_pyproject(self):
        """pyproject.toml 不包含 pydantic-ai 依赖"""
        import pathlib
        pyproject = (pathlib.Path(__file__).parent.parent.parent.parent /
                     "pyproject.toml").read_text(encoding="utf-8")
        assert "pydantic-ai" not in pyproject, \
            "pyproject.toml should not reference pydantic-ai"

    def test_no_pydantic_ai_production_import(self):
        """验证生产代码不 import pydantic_ai"""
        import subprocess
        import pathlib
        import sys

        repo_root = pathlib.Path(__file__).parent.parent.parent.parent
        # 搜索所有 Python 生产文件（非测试）
        result = subprocess.run(
            [sys.executable, "-c",
             """
import os, pathlib
root = pathlib.Path(r'%s')
for f in root.rglob("*.py"):
    rel = str(f.relative_to(root))
    if "tests" in rel.split(os.sep) or "__pycache__" in rel.split(os.sep):
        continue
    content = f.read_text(encoding="utf-8", errors="ignore")
    if "pydantic_ai" in content or "pydantic-ai" in content:
        print(rel)
""" % str(repo_root)],
            capture_output=True, text=True, timeout=30,
        )
        pydantic_refs = [l for l in result.stdout.strip().split("\n") if l]
        assert len(pydantic_refs) == 0, \
            f"Production files still reference pydantic_ai: {pydantic_refs}"


class TestTurnPipelineShared:
    """验证 TurnPipeline 共享骨架可用于 Mock 和 DeepSeek"""

    def test_turn_pipeline_importable(self):
        """TurnPipeline 可导入"""
        from backend.app.application.turn_pipeline import TurnPipeline
        assert TurnPipeline is not None

    def test_turn_pipeline_both_services_use_same_type(self):
        """Mock 和 DeepSeek 使用同一个 TurnPipeline 类型"""
        from backend.app.application.turn_pipeline import TurnPipeline
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository
        from backend.app.config.settings import Settings
        from backend.app.harness.models import HarnessConfig
        from unittest.mock import MagicMock

        # Mock service
        mock_svc = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
        assert isinstance(mock_svc.pipeline, TurnPipeline)

        # DeepSeek service（用 MagicMock 绕过 provider 检查）
        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)
        llm_provider = MagicMock()
        llm_provider.is_mock = False
        llm_provider.provider_name = "deepseek"

        deepseek_svc = DeepSeekTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_provider=llm_provider,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            settings=settings,
            config=config,
        )
        assert isinstance(deepseek_svc.pipeline, TurnPipeline)

    def test_both_services_tool_gateway_same_registry(self):
        """两个 Service 的工具都来自 create_default_tool_gateway 共享入口"""
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository
        from backend.app.config.settings import Settings
        from backend.app.harness.models import HarnessConfig
        from backend.app.harness.tool_registry import DEFAULT_TOOL_NAMES
        from unittest.mock import MagicMock

        mock_svc = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
        mock_tools = set(mock_svc.tool_gateway.list_tools())

        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)
        llm_provider = MagicMock()
        llm_provider.is_mock = False
        llm_provider.provider_name = "deepseek"

        deepseek_svc = DeepSeekTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_provider=llm_provider,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            settings=settings,
            config=config,
        )
        deepseek_tools = set(deepseek_svc.tool_gateway.list_tools())

        # 两者都必须包含相同的三个白名单工具
        assert mock_tools == set(DEFAULT_TOOL_NAMES)
        assert deepseek_tools == set(DEFAULT_TOOL_NAMES)
        assert mock_tools == deepseek_tools
