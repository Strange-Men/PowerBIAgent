"""FastAPI 应用 — M3.1

启动命令：
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

M1.5 更新：
- 根据 Settings 条件初始化 MockTurnService 或 DeepSeekTurnService
- 存储为 app.state.turn_service（通用名称）
- DeepSeek 无 Key、Local 配置不完整或 Remote MCP 模式不初始化 Service
- shutdown 关闭 DeepSeek httpx Client（如有）
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import LLMMode, PowerBIMode, Settings, get_settings
from backend.app.harness.models import HarnessConfig
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.fixed import FixedSalesReportRenderer
from backend.app.report.mock import MockReportRenderer
from backend.app.report.resources import LocalReportRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    startup: 根据 Settings 条件初始化 TurnService
        - Mock+Mock: MockTurnService
        - DeepSeek+Mock (Key 已配置): DeepSeekTurnService
        - DeepSeek+Local (配置完整): 复用 DeepSeekTurnService + TurnPipeline
        - DeepSeek 配置不完整: turn_service=None → Health 503
        - Remote MCP: turn_service=None → Health 503

    shutdown: 清理资源（关闭 DeepSeek httpx Client 等）
    """
    # Settings — 可由 create_app(settings=...) 注入，否则使用默认
    if not hasattr(app.state, "settings") or app.state.settings is None:
        app.state.settings = get_settings()

    settings: Settings = app.state.settings
    # M1.6.2: 统一从 Settings 构建一次 HarnessConfig，显式传给所有 TurnService
    harness_config = HarnessConfig.from_settings(settings)
    turn_service = None
    _deepseek_provider = None  # 用于 shutdown 关闭
    report_repository = LocalReportRepository()
    app.state.report_repository = report_repository

    if settings.llm_mode == LLMMode.MOCK and settings.powerbi_mode == PowerBIMode.MOCK:
        # Mock + Mock: 原有 MockTurnService
        turn_service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            report_repository=report_repository,
            config=harness_config,
        )

    elif (
        settings.llm_mode == LLMMode.DEEPSEEK
        and settings.powerbi_mode in {PowerBIMode.MOCK, PowerBIMode.LOCAL_MCP}
    ):
        if not settings.is_real_ready:
            # DeepSeek 或 Local 配置不完整：不初始化 Service，Health 返回 503
            turn_service = None
        else:
            # DeepSeek + Mock / Local: 只替换 PowerBIAdapter Provider。
            from backend.app.application.deepseek_turn_service import (
                DeepSeekTurnService,
            )
            from backend.app.llm.factory import build_llm_registry

            registry = build_llm_registry(settings)
            deepseek_provider = registry.get("deepseek")
            _deepseek_provider = deepseek_provider

            powerbi_adapter: PowerBIAdapter
            if settings.powerbi_mode == PowerBIMode.LOCAL_MCP:
                powerbi_adapter = LocalMCPPowerBIAdapter(
                    executable=settings.powerbi_local_mcp_executable,
                    package=settings.powerbi_local_mcp_package,
                    semantic_model_key=settings.powerbi_local_semantic_model_key,
                    readonly=settings.powerbi_local_mcp_readonly,
                    timeout=float(settings.request_timeout_seconds),
                    max_retries=settings.max_powerbi_retries,
                )
            else:
                powerbi_adapter = MockPowerBIAdapter()

            turn_service = DeepSeekTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_provider=deepseek_provider,
                powerbi_adapter=powerbi_adapter,
                report_renderer=FixedSalesReportRenderer(),
                report_repository=report_repository,
                settings=settings,
                config=harness_config,
            )

    else:
        # Remote MCP 或其他不支持的模式
        turn_service = None

    app.state.turn_service = turn_service
    # 兼容旧代码：同时设置 mock_turn_service（测试用）
    if isinstance(turn_service, MockTurnService):
        app.state.mock_turn_service = turn_service
    else:
        app.state.mock_turn_service = None

    yield

    # shutdown — 关闭 DeepSeek httpx Client（如有）
    if _deepseek_provider is not None and hasattr(_deepseek_provider, "aclose"):
        try:
            await _deepseek_provider.aclose()
        except Exception:
            pass

    # 清理 app.state 引用，防止跨测试污染
    app.state.turn_service = None
    app.state.mock_turn_service = None
    app.state.report_repository = None
    app.state.settings = None


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """创建 FastAPI 应用 — 避免导入时执行外部网络调用

    Args:
        settings: 可选 Settings 实例（测试注入用）。None 时使用 get_settings()。
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # 在 lifespan 启动前预设 settings（lifespan 检查 hasattr）
    app.state.settings = settings

    app.include_router(router)

    return app


# 模块级 app 实例 — 供 uvicorn 引用
app = create_app()
