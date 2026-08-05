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
    if "tests" in rel.split(os.sep) or "__pycache__" in rel.split(os.sep) or rel.split(os.sep)[0] == "scripts":
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


class TestTurnPipelineUnifiedControlSurface:
    """M1.6.3.1 — 验证 TurnPipeline 真正统一通用控制面，两个 Service 不重复实现"""

    def test_mock_service_no_own_context_builder(self):
        """MockTurnService 不再持有自己的 ContextBuilder"""
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository

        svc = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
        # ContextBuilder 只在 TurnPipeline 中
        assert not hasattr(svc, "context_builder"), \
            "MockTurnService should not have its own context_builder"
        assert svc.pipeline.context_builder is not None, \
            "TurnPipeline must own the ContextBuilder"

    def test_deepseek_service_no_own_context_builder(self):
        """DeepSeekTurnService 不再持有自己的 ContextBuilder"""
        from unittest.mock import MagicMock
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository
        from backend.app.config.settings import Settings
        from backend.app.harness.models import HarnessConfig

        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)
        llm = MagicMock()
        llm.is_mock = False
        llm.provider_name = "deepseek"

        svc = DeepSeekTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_provider=llm,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            settings=settings,
            config=config,
        )
        assert not hasattr(svc, "context_builder"), \
            "DeepSeekTurnService should not have its own context_builder"
        assert svc.pipeline.context_builder is not None, \
            "TurnPipeline must own the ContextBuilder"

    @pytest.mark.anyio
    async def test_turn_pipeline_creates_context_before_callback(self):
        """验证 TurnPipeline.execute() 在调用 callback 前构建 context 并创建 controller"""
        from backend.app.application.turn_pipeline import TurnPipeline
        from backend.app.harness.models import HarnessConfig
        from backend.app.harness.runtime.turn_controller import TurnController
        from backend.app.memory.models import RuntimeDataMode
        from backend.app.memory.repository import InMemoryMemoryRepository

        config = HarnessConfig()
        repo = InMemoryMemoryRepository()
        pipeline = TurnPipeline(config=config, memory_repo=repo)

        received_controller = None
        received_context = None
        received_conv_id = None
        received_req_id = None

        async def capture_callback(**kwargs):
            nonlocal received_controller, received_context, received_conv_id, received_req_id
            received_controller = kwargs.get("controller")
            received_context = kwargs.get("context")
            received_conv_id = kwargs.get("effective_conv_id")
            received_req_id = kwargs.get("effective_req_id")
            return {
                "request_id": received_req_id,
                "conversation_id": received_conv_id,
                "terminal_state": "completed",
                "tool_sequence": [],
                "memory_commit": True,
                "is_mock": True,
                "allowed_tools": [],
            }

        await pipeline.execute(
            message="测试消息",
            conversation_id=None,
            request_id=None,
            semantic_model_key="test_model",
            report_template_key=None,
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            llm_provider_name="mock",
            powerbi_provider_name="mock_powerbi",
            do_execute=capture_callback,
        )

        assert received_controller is not None, \
            "TurnPipeline must create and pass TurnController to callback"
        assert isinstance(received_controller, TurnController), \
            "Must be a TurnController instance"
        assert received_context is not None, \
            "TurnPipeline must build and pass context dict to callback"
        assert isinstance(received_context, dict), \
            "Context must be a dict"

    def test_turn_pipeline_has_create_tool_context(self):
        """验证 TurnPipeline 提供统一的 ToolExecutionContext 工厂"""
        from backend.app.application.turn_pipeline import TurnPipeline
        from backend.app.harness.models import HarnessConfig
        from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
        from backend.app.memory.models import RuntimeDataMode
        from backend.app.memory.repository import InMemoryMemoryRepository
        from backend.app.intent.models import IntentType

        pipeline = TurnPipeline(
            config=HarnessConfig(),
            memory_repo=InMemoryMemoryRepository(),
        )
        ctx = pipeline.create_tool_context(
            trace_id="t1",
            request_id="r1",
            conversation_id="c1",
            runtime_mode=RuntimeDataMode.MOCK,
            intent=IntentType.DATA_QUESTION,
        )
        assert isinstance(ctx, ToolExecutionContext)
        assert ctx.trace_id == "t1"
        assert ctx.request_id == "r1"

    @pytest.mark.anyio
    async def test_turn_pipeline_has_mark_memory_failed(self):
        """验证 TurnPipeline 提供统一的 Memory 失败标记"""
        import uuid
        from backend.app.application.turn_pipeline import TurnPipeline
        from backend.app.harness.models import HarnessConfig
        from backend.app.memory.models import MemoryStatus, RuntimeDataMode
        from backend.app.memory.repository import InMemoryMemoryRepository

        repo = InMemoryMemoryRepository()
        pipeline = TurnPipeline(config=HarnessConfig(), memory_repo=repo)

        rid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        mode = RuntimeDataMode.MOCK

        await pipeline.create_pending_memory(
            conversation_id=cid,
            request_id=rid,
            semantic_model_key="test_model",
            report_template_key=None,
            intent_value="data_question",
            runtime_mode=mode,
            is_mock=True,
            llm_provider_name="mock",
            powerbi_provider_name="mock_powerbi",
            base_version=0,
        )
        await pipeline.mark_memory_failed(
            rid, mode, reason="test failure", stage="test_stage"
        )

        failed = await repo.get_by_request_id(rid, mode)
        assert failed is not None
        assert failed.state_status == MemoryStatus.FAILED

    def test_both_services_have_no_own_tool_context_creation(self):
        """两个 Service 的 ToolExecutionContext 都通过 TurnPipeline 创建"""
        import inspect
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService

        # 检查 MockTurnService._do_execute 源码中不包含 ToolExecutionContext 直接构造
        mock_source = inspect.getsource(MockTurnService._do_execute)
        assert "ToolExecutionContext(" not in mock_source.replace(
            "self.pipeline.create_tool_context(", ""
        ), "MockTurnService._do_execute should not directly construct ToolExecutionContext"

        # 检查 DeepSeekTurnService._do_execute 源码
        deepseek_source = inspect.getsource(DeepSeekTurnService._do_execute)
        assert "ToolExecutionContext(" not in deepseek_source.replace(
            "self.pipeline.create_tool_context(", ""
        ), "DeepSeekTurnService._do_execute should not directly construct ToolExecutionContext"

    @pytest.mark.anyio
    async def test_shared_turn_pipeline_has_commit_memory_safe(self):
        """验证 TurnPipeline 提供安全的 Memory 提交方法"""
        import uuid
        from backend.app.application.turn_pipeline import TurnPipeline
        from backend.app.harness.models import HarnessConfig
        from backend.app.harness.runtime.turn_controller import TurnController, TurnState
        from backend.app.harness.observability.trace_recorder import TraceRecorder
        from backend.app.memory.models import RuntimeDataMode
        from backend.app.memory.repository import InMemoryMemoryRepository

        config = HarnessConfig()
        repo = InMemoryMemoryRepository()
        pipeline = TurnPipeline(config=config, memory_repo=repo)
        trace = TraceRecorder(config)
        rid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        mode = RuntimeDataMode.MOCK

        memory = await pipeline.create_pending_memory(
            conversation_id=cid,
            request_id=rid,
            semantic_model_key="test_model",
            report_template_key=None,
            intent_value="data_question",
            runtime_mode=mode,
            is_mock=True,
            llm_provider_name="mock",
            powerbi_provider_name="mock_powerbi",
            base_version=0,
        )
        controller = TurnController(config, request_id=rid)
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()
        controller.transition(TurnState.PLAN_READY)
        controller.record_tool_execution_succeeded()
        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)
        controller.record_dax_valid()
        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)
        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)
        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)
        evidence = controller.build_commit_evidence()

        committed, error = await pipeline.commit_memory_safe(
            memory, evidence, controller,
            trace, "t1", rid, mode,
        )
        assert committed is not None, "Commit should succeed"
        assert error is None, f"Should not error, got: {error}"
        assert committed.memory_version == 1
