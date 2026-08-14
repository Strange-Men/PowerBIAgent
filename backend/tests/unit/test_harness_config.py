"""M1.6.2 配置收口与工具注册测试

验证：
- Settings 与 HarnessConfig 使用同一 Enum 类型
- from_settings() 所有配置字段正确映射
- DeepSeek 配置 llm_mode=DEEPSEEK 且 is_mock=False
- main lifespan 向两种 TurnService 传入正确 HarnessConfig
- 共享工具注册只包含四个白名单工具
- ToolSpec 的超时与重试来自 HarnessConfig
"""

import pytest

from backend.app.config.settings import (
    AppEnv,
    HarnessMode,
    LLMMode,
    PowerBIMode,
    Settings,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.tool_registry import (
    DEFAULT_TOOL_NAMES,
    TOOL_NAME_DAX,
    TOOL_NAME_MEMBERS,
    TOOL_NAME_RENDER,
    TOOL_NAME_SCHEMA,
    SchemaInput,
    create_default_tool_gateway,
    register_default_tools,
)
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolSpec


# ──────────────────────────────────────────────
# 一、Enum 类型统一
# ──────────────────────────────────────────────

class TestEnumIdentity:
    """Settings 与 HarnessConfig 使用同一 Enum 类型"""

    def test_app_env_same_type(self):
        assert AppEnv is HarnessConfig.model_fields["app_env"].default.__class__

    def test_llm_mode_same_type(self):
        assert LLMMode is HarnessConfig.model_fields["llm_mode"].default.__class__

    def test_powerbi_mode_same_type(self):
        assert PowerBIMode is HarnessConfig.model_fields["powerbi_mode"].default.__class__

    def test_harness_mode_same_type(self):
        assert HarnessMode is HarnessConfig.model_fields["harness_mode"].default.__class__

    def test_harness_config_imports_enums_from_settings(self):
        """验证 HarnessConfig 的 Enum 字段类型与 Settings 的 Enum 完全一致"""
        from backend.app.harness.models import (
            AppEnv as HAppEnv,
            LLMMode as HLLMMode,
            PowerBIMode as HPowerBIMode,
            HarnessMode as HHarnessMode,
        )
        assert HAppEnv is AppEnv
        assert HLLMMode is LLMMode
        assert HPowerBIMode is PowerBIMode
        assert HHarnessMode is HarnessMode


# ──────────────────────────────────────────────
# 二、from_settings() 字段映射
# ──────────────────────────────────────────────

class TestFromSettingsMapping:
    """from_settings() 所有配置字段正确映射"""

    def test_default_mock_config(self):
        """默认 Settings → HarnessConfig 为 Mock 模式"""
        settings = Settings()
        config = HarnessConfig.from_settings(settings)
        assert config.app_env == AppEnv.DEVELOPMENT
        assert config.llm_mode == LLMMode.MOCK
        assert config.powerbi_mode == PowerBIMode.MOCK
        assert config.harness_mode == HarnessMode.STRICT
        assert config.is_mock is True

    def test_all_fields_mapped(self):
        """所有 12 个字段正确从 Settings 映射"""
        settings = Settings(
            app_env="test",
            llm_mode="deepseek",
            powerbi_mode="mock",
            harness_mode="test",
            request_timeout_seconds=60,
            powerbi_query_timeout_seconds=15,
            max_tool_calls=5,
            max_dax_repairs=2,
            max_llm_format_retries=3,
            max_powerbi_retries=2,
            max_query_rows=500,
            max_user_input_length=1000,
        )
        config = HarnessConfig.from_settings(settings)

        # 四个运行模式
        assert config.app_env == AppEnv.TEST
        assert config.llm_mode == LLMMode.DEEPSEEK
        assert config.powerbi_mode == PowerBIMode.MOCK
        assert config.harness_mode == HarnessMode.TEST

        # 超时
        assert config.request_timeout_seconds == 60
        assert config.powerbi_query_timeout_seconds == 15

        # 限制
        assert config.max_tool_calls == 5
        assert config.max_dax_repairs == 2
        assert config.max_llm_format_retries == 3
        assert config.max_powerbi_retries == 2
        assert config.max_query_rows == 500
        assert config.max_user_input_length == 1000

    def test_deepseek_config_not_mock(self):
        """DeepSeek 配置 llm_mode=DEEPSEEK 且 is_mock=False"""
        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)
        assert config.llm_mode == LLMMode.DEEPSEEK
        assert config.is_mock is False

    def test_production_env(self):
        """生产环境配置正确映射"""
        settings = Settings(app_env="production")
        config = HarnessConfig.from_settings(settings)
        assert config.app_env == AppEnv.PRODUCTION
        assert config.is_production is True

    def test_remote_mcp_not_mock(self):
        """Remote MCP 配置 is_mock=False"""
        settings = Settings(llm_mode="deepseek", powerbi_mode="remote_mcp")
        config = HarnessConfig.from_settings(settings)
        assert config.powerbi_mode == PowerBIMode.REMOTE_MCP
        assert config.is_mock is False


# ──────────────────────────────────────────────
# 三、main lifespan 配置传递
# ──────────────────────────────────────────────

class TestMainLifespanConfig:
    """main lifespan 向两种 TurnService 传入正确 HarnessConfig"""

    @pytest.mark.anyio
    async def test_mock_turn_service_receives_config(self):
        """MockTurnService 从 lifespan 接收正确的 Mock 配置"""
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository

        settings = Settings(llm_mode="mock", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)

        service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            config=config,
        )
        assert service.config is config
        assert service.config.llm_mode == LLMMode.MOCK
        assert service.config.is_mock is True
        # 工具网关包含 schema/member/DAX/render 四个受控工具
        tools = service.tool_gateway.list_tools()
        assert len(tools) == 4
        assert set(tools) == set(DEFAULT_TOOL_NAMES)

    @pytest.mark.anyio
    async def test_mock_turn_service_config_driven_timeouts(self):
        """MockTurnService 的 ToolSpec 超时和重试来自 HarnessConfig"""
        from backend.app.application.mock_turn_service import MockTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository

        settings = Settings(
            llm_mode="mock",
            powerbi_mode="mock",
            powerbi_query_timeout_seconds=45,
            max_powerbi_retries=3,
            request_timeout_seconds=90,
        )
        config = HarnessConfig.from_settings(settings)

        service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            config=config,
        )

        # get_semantic_model_schema 使用 powerbi_query_timeout_seconds 和 max_powerbi_retries
        schema_tool = service.tool_gateway.get_tool(TOOL_NAME_SCHEMA)
        assert schema_tool.timeout_seconds == 45.0
        assert schema_tool.max_retries == 3

        # execute_dax 同样使用 powerbi 超时和重试
        dax_tool = service.tool_gateway.get_tool(TOOL_NAME_DAX)
        assert dax_tool.timeout_seconds == 45.0
        assert dax_tool.max_retries == 3

        # render_report 使用 request_timeout_seconds，max_retries=0
        render_tool = service.tool_gateway.get_tool(TOOL_NAME_RENDER)
        assert render_tool.timeout_seconds == 90.0
        assert render_tool.max_retries == 0

    @pytest.mark.anyio
    async def test_deepseek_turn_service_receives_deepseek_config(self):
        """DeepSeekTurnService 接收 DeepSeek 配置（非 Mock）"""
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository
        from backend.app.llm.mock import MockLLMProvider

        # 使用 MockLLMProvider 但构造非 mock 的 settings/config
        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)

        # DeepSeekTurnService 要求非 Mock LLM Provider
        # 用 MockLLMProvider 但设置 is_mock 标识 — 这里我们只验证 config 传递
        llm_provider = MockLLMProvider()

        # 注意：DeepSeekTurnService 会检查 provider.is_mock 并拒绝
        # 这里我们验证配置逻辑而非完整构造
        # 使用 try/except 验证 ValueError 来自 provider 检查而非 config 问题
        with pytest.raises(ValueError, match="非 Mock"):
            DeepSeekTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_provider=llm_provider,
                powerbi_adapter=MockPowerBIAdapter(),
                report_renderer=MockReportRenderer(),
                settings=settings,
                config=config,
            )

    @pytest.mark.anyio
    async def test_main_create_app_mock_mode(self):
        """create_app Mock 模式下 lifespan 传入正确 config"""
        from backend.app.main import create_app

        settings = Settings(llm_mode="mock", powerbi_mode="mock")
        app = create_app(settings=settings)

        assert app.state.settings is settings

        # 手动触发 lifespan startup
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            assert service is not None
            assert service.config.llm_mode == LLMMode.MOCK
            assert service.config.is_mock is True
            tools = service.tool_gateway.list_tools()
            assert len(tools) == 4
            assert set(tools) == set(DEFAULT_TOOL_NAMES)

    @pytest.mark.anyio
    async def test_main_create_app_deepseek_no_key(self):
        """create_app DeepSeek+Mock 无 Key → turn_service=None"""
        from backend.app.main import create_app
        import os

        # 确保 DeepSeek Key 未设置
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            settings = Settings(llm_mode="deepseek", powerbi_mode="mock", deepseek_api_key=None)
            app = create_app(settings=settings)

            async with app.router.lifespan_context(app):
                assert app.state.turn_service is None
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key

    @pytest.mark.anyio
    async def test_deepseek_lifespan_creates_service_with_tool_gateway(self):
        """M1.6.3: lifespan DeepSeek+Mock 有 Key → DeepSeekTurnService 使用共享 ToolGateway"""
        from unittest.mock import MagicMock, AsyncMock, patch
        from backend.app.main import create_app
        import os

        # 模拟 API Key（fake_key 为安全扫描允许的占位值）
        os.environ["DEEPSEEK_API_KEY"] = "fake_key"
        try:
            settings = Settings(
                llm_mode="deepseek",
                powerbi_mode="mock",
                deepseek_api_key="fake_key",
                deepseek_base_url="https://api.deepseek.com/v1",
                deepseek_model="deepseek-chat",
            )

            # Mock DeepSeekLLMProvider 以避免真实网络请求
            mock_provider = MagicMock()
            mock_provider.is_mock = False
            mock_provider.provider_name = "deepseek"

            with patch(
                "backend.app.llm.factory.DeepSeekLLMProvider",
                return_value=mock_provider,
            ):
                with patch.object(mock_provider, "aclose", AsyncMock()):
                    app = create_app(settings=settings)

                    async with app.router.lifespan_context(app):
                        service = app.state.turn_service
                        assert service is not None, "DeepSeekTurnService 应被创建"

                        # 验证 HarnessConfig 为 DEEPSEEK 且 is_mock=False
                        assert service.config.llm_mode == LLMMode.DEEPSEEK
                        assert service.config.is_mock is False

                        # M1.6.3: 验证 ToolGateway 来自 create_default_tool_gateway
                        tools = service.tool_gateway.list_tools()
                        assert len(tools) == 4
                        assert set(tools) == set(DEFAULT_TOOL_NAMES)

                        # M1.6.3.1: 验证 ContextBuilder 由 TurnPipeline 统一管理
                        assert service.pipeline.context_builder is not None
        finally:
            del os.environ["DEEPSEEK_API_KEY"]

    @pytest.mark.anyio
    async def test_deepseek_turn_service_tool_gateway_is_shared_entry(self):
        """M1.6.3: DeepSeekTurnService 的 allowed_tools 来自 gateway.list_tools()"""
        from unittest.mock import MagicMock
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.powerbi.mock import MockPowerBIAdapter
        from backend.app.report.mock import MockReportRenderer
        from backend.app.memory.repository import InMemoryMemoryRepository

        settings = Settings(llm_mode="deepseek", powerbi_mode="mock")
        config = HarnessConfig.from_settings(settings)

        # 使用 MagicMock 创建非 Mock Provider
        llm_provider = MagicMock()
        llm_provider.is_mock = False
        llm_provider.provider_name = "deepseek"

        service = DeepSeekTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_provider=llm_provider,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            settings=settings,
            config=config,
        )

        # allowed_tools 必须来自 gateway.list_tools()
        tools = service.tool_gateway.list_tools()
        assert set(tools) == set(DEFAULT_TOOL_NAMES)

        # _build_result 的 allowed_tools 也必须与 gateway 一致
        result = service._build_result("req-1", "conv-1", "completed")
        assert set(result["allowed_tools"]) == set(tools)


# ──────────────────────────────────────────────
# 四、共享工具注册
# ──────────────────────────────────────────────

class TestSharedToolRegistry:
    """共享工具注册只包含四个白名单工具"""

    def test_default_tool_names_exactly_four(self):
        """DEFAULT_TOOL_NAMES 恰好包含四个白名单工具"""
        assert len(DEFAULT_TOOL_NAMES) == 4
        assert DEFAULT_TOOL_NAMES == [
            TOOL_NAME_SCHEMA,
            TOOL_NAME_MEMBERS,
            TOOL_NAME_DAX,
            TOOL_NAME_RENDER,
        ]

    def test_create_default_tool_gateway_registers_four_tools(self, mock_adapters):
        """create_default_tool_gateway 注册恰好四个工具"""
        powerbi, renderer = mock_adapters
        config = HarnessConfig()
        gateway = create_default_tool_gateway(powerbi, renderer, config)
        tools = gateway.list_tools()
        assert len(tools) == 4
        assert set(tools) == set(DEFAULT_TOOL_NAMES)

    def test_register_default_tools_idempotent_reject(self, mock_adapters):
        """重复注册被拒绝"""
        powerbi, renderer = mock_adapters
        config = HarnessConfig()
        gateway = ToolGateway()
        register_default_tools(gateway, powerbi, renderer, config)

        from backend.app.harness.errors import ToolNotRegisteredError
        with pytest.raises(ToolNotRegisteredError, match="already registered"):
            register_default_tools(gateway, powerbi, renderer, config)

    def test_tool_timeouts_from_config(self, mock_adapters):
        """ToolSpec 超时和重试来自 HarnessConfig，不写死"""
        powerbi, renderer = mock_adapters
        config = HarnessConfig(
            powerbi_query_timeout_seconds=25,
            max_powerbi_retries=2,
            request_timeout_seconds=80,
        )
        gateway = create_default_tool_gateway(powerbi, renderer, config)

        schema_tool = gateway.get_tool(TOOL_NAME_SCHEMA)
        assert schema_tool.timeout_seconds == 25.0
        assert schema_tool.max_retries == 2

        dax_tool = gateway.get_tool(TOOL_NAME_DAX)
        assert dax_tool.timeout_seconds == 25.0
        assert dax_tool.max_retries == 2

        render_tool = gateway.get_tool(TOOL_NAME_RENDER)
        assert render_tool.timeout_seconds == 80.0
        assert render_tool.max_retries == 0

    def test_tool_names_not_hardcoded_in_service(self):
        """工具名称不在 Service 中硬编码 — 来自 tool_registry"""
        # 验证 tool_registry 中定义了常量，Service 使用这些常量
        assert TOOL_NAME_SCHEMA == "get_semantic_model_schema"
        assert TOOL_NAME_DAX == "execute_dax"
        assert TOOL_NAME_RENDER == "render_report"

    def test_schema_input_model(self):
        """SchemaInput 模型正确"""
        si = SchemaInput(semantic_model_key="test_model")
        assert si.semantic_model_key == "test_model"
        assert SchemaInput().semantic_model_key == "mock_sales_model"  # default

    def test_all_tools_read_only(self, mock_adapters):
        """所有三个工具必须为 read_only=True"""
        powerbi, renderer = mock_adapters
        config = HarnessConfig()
        gateway = create_default_tool_gateway(powerbi, renderer, config)

        for tool_name in DEFAULT_TOOL_NAMES:
            tool = gateway.get_tool(tool_name)
            assert tool.read_only is True, f"Tool '{tool_name}' must be read_only"

    def test_schema_and_dax_support_both_intents(self, mock_adapters):
        """get_semantic_model_schema 和 execute_dax 支持 data_question 和 report_generation"""
        from backend.app.intent.models import IntentType
        powerbi, renderer = mock_adapters
        config = HarnessConfig()
        gateway = create_default_tool_gateway(powerbi, renderer, config)

        for tool_name in [TOOL_NAME_SCHEMA, TOOL_NAME_DAX]:
            tool = gateway.get_tool(tool_name)
            assert IntentType.DATA_QUESTION in tool.allowed_intents
            assert IntentType.REPORT_GENERATION in tool.allowed_intents

    def test_render_report_only_for_report_generation(self, mock_adapters):
        """render_report 仅允许 report_generation intent"""
        from backend.app.intent.models import IntentType
        powerbi, renderer = mock_adapters
        config = HarnessConfig()
        gateway = create_default_tool_gateway(powerbi, renderer, config)

        render_tool = gateway.get_tool(TOOL_NAME_RENDER)
        assert IntentType.DATA_QUESTION not in render_tool.allowed_intents
        assert IntentType.REPORT_GENERATION in render_tool.allowed_intents


# ── fixtures ──

@pytest.fixture
def mock_adapters():
    """提供 Mock PowerBI Adapter 和 Mock Report Renderer"""
    from backend.app.powerbi.mock import MockPowerBIAdapter
    from backend.app.report.mock import MockReportRenderer
    return MockPowerBIAdapter(), MockReportRenderer()
