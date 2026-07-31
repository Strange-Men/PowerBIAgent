"""FastAPI 应用 — M0.4 最小骨架

启动命令：
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

M0.4 仅接入 Mock 能力。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.api.dependencies import set_mock_turn_service
from backend.app.api.routes import router
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import get_settings
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    startup: 初始化共享且并发安全的 MockTurnService
    shutdown: 清理资源（当前无需特殊处理）
    """
    settings = get_settings()

    # Mock 模式：创建共享的 MockTurnService
    # M0.4 修复后：Service/ToolGateway 无请求级共享状态，可安全复用
    service = MockTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_runtime=MockAgentRuntime(),
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
    )
    set_mock_turn_service(service)

    yield

    # shutdown — 暂无清理需求（Memory 在内存中，进程退出即丢弃）


def create_app() -> FastAPI:
    """创建 FastAPI 应用 — 避免导入时执行外部网络调用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.include_router(router)

    return app


# 模块级 app 实例 — 供 uvicorn 引用
app = create_app()
