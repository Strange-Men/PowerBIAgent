"""FastAPI 应用 — M0.4.1

启动命令：
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

M0.4.1 修复：
- 使用 app.state 管理 Service 实例（不再使用模块级全局变量）
- lifespan 初始化 app.state.settings 和 app.state.mock_turn_service
- create_app() 支持 settings 参数注入（测试可用）
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.api.routes import router
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import Settings, get_settings
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    startup: 在 app.state 上初始化共享且并发安全的 MockTurnService
    shutdown: 清理资源（当前无需特殊处理）
    """
    # Settings — 可由 create_app(settings=...) 注入，否则使用默认
    if not hasattr(app.state, "settings") or app.state.settings is None:
        app.state.settings = get_settings()

    # Mock 模式：创建共享的 MockTurnService
    # M0.4 修复后：Service/ToolGateway 无请求级共享状态，可安全复用
    app.state.mock_turn_service = MockTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_runtime=MockAgentRuntime(),
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
    )

    yield

    # shutdown — 清理 app.state 引用，防止跨测试污染
    app.state.mock_turn_service = None
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

    # M0.4.1: 在 lifespan 启动前预设 settings（lifespan 检查 hasattr）
    app.state.settings = settings

    app.include_router(router)

    return app


# 模块级 app 实例 — 供 uvicorn 引用
app = create_app()
