"""FastAPI 应用 — M4.4

启动命令：
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

M4 persistence wiring：
- 新增 persistence factory：Sqlite 时创建 SQLiteMemoryRepository + SQLiteSnapshotRepository
- Memory 时使用 InMemoryMemoryRepository + ResultSnapshotStore（默认）
- engine/repo 生命周期在 lifespan 中管理（create/dispose）

M1.5 更新：
- 根据 Settings 条件初始化 MockTurnService 或 DeepSeekTurnService
- 存储为 app.state.turn_service（通用名称）
- DeepSeek 无 Key、Local 配置不完整或 Remote MCP 模式不初始化 Service
- shutdown 关闭 DeepSeek httpx Client（如有）
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.app.api.routes import router
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.application.conversation_history_service import ConversationHistoryService
from backend.app.config.settings import (
    LLMMode,
    PersistenceBackend,
    PowerBIMode,
    Settings,
    get_settings,
)
from backend.app.harness.models import HarnessConfig
from backend.app.memory.repository import InMemoryMemoryRepository, MemoryRepository
from backend.app.memory.result_snapshot import ResultSnapshotStore, SnapshotRepository
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
from backend.app.persistence.repositories.conversation_history import (
    SQLiteConversationHistoryRepository,
)
from backend.app.persistence.repositories.report_artifact import (
    InMemoryReportArtifactRepository,
    ReportArtifactRepository,
    SQLiteReportArtifactRepository,
)
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.mock import MockReportRenderer
from backend.app.report.resources import LocalReportRepository


# ---------------------------------------------------------------------------
# Persistence factory
# ---------------------------------------------------------------------------


def _create_repos(
    settings: Settings,
) -> tuple[
    MemoryRepository,
    Optional[SnapshotRepository],
    Optional[ReportArtifactRepository],
    Optional[AsyncEngine],
    Optional[async_sessionmaker],
]:
    """Create memory + snapshot + report artifact repositories.

    Returns
    -------
    (memory_repo, snapshot_store, report_artifact_repo, engine, session_factory)
        *memory_repo* is always a ``MemoryRepository``.
        *snapshot_store* is a ``SnapshotRepository`` (or the default if memory backend).
        *report_artifact_repo* is a ``ReportArtifactRepository`` (or in-memory default).
        *engine* is an ``AsyncEngine`` (sqlite) or ``None``.
        *session_factory* is an ``async_sessionmaker`` (sqlite) or ``None``.
    """
    if settings.persistence_backend == PersistenceBackend.SQLITE:
        engine = create_engine(settings, echo=False)
        # configure_engine is async — handled in lifespan
        session_factory = create_session_factory(engine)
        memory_repo = SQLiteMemoryRepository(session_factory=session_factory)
        snapshot_store = SQLiteSnapshotRepository(session_factory=session_factory)
        report_artifact_repo = SQLiteReportArtifactRepository(
            session_factory=session_factory
        )
        return memory_repo, snapshot_store, report_artifact_repo, engine, session_factory
    else:
        return (
            InMemoryMemoryRepository(),
            None,
            InMemoryReportArtifactRepository(),
            None,
            None,
        )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    startup: 根据 Settings 条件初始化 TurnService
        - Mock+Mock: MockTurnService
        - DeepSeek+Mock (Key 已配置): DeepSeekTurnService
        - DeepSeek+Local (配置完整): 复用 DeepSeekTurnService + TurnPipeline
        - DeepSeek 配置不完整: turn_service=None → Health 503
        - Remote MCP: turn_service=None → Health 503

    shutdown: 清理资源（关闭 SQLite engine、DeepSeek httpx Client 等）
    """
    # Settings — 可由 create_app(settings=...) 注入，否则使用默认
    if not hasattr(app.state, "settings") or app.state.settings is None:
        app.state.settings = get_settings()

    settings: Settings = app.state.settings
    # M1.6.2: 统一从 Settings 构建一次 HarnessConfig，显式传给所有 TurnService
    harness_config = HarnessConfig.from_settings(settings)
    turn_service = None
    _deepseek_provider = None  # 用于 shutdown 关闭

    # 初始化持久化仓库 — must create before report_repository
    (
        memory_repo,
        snapshot_store,
        report_artifact_repo,
        _engine,
        _session_factory,
    ) = _create_repos(settings)
    app.state._persistence_engine = _engine  # 保存用于 shutdown

    # Configure engine if SQLite (async setup)
    if _engine is not None:
        await configure_engine(_engine)

    report_repository = LocalReportRepository(
        metadata_repo=report_artifact_repo,
    )
    app.state.report_repository = report_repository
    if _session_factory is not None:
        app.state.conversation_history_service = ConversationHistoryService(
            SQLiteConversationHistoryRepository(_session_factory),
            report_repository=report_repository,
        )
    else:
        app.state.conversation_history_service = None

    if settings.llm_mode == LLMMode.MOCK and settings.powerbi_mode == PowerBIMode.MOCK:
        # Mock + Mock: 原有 MockTurnService
        turn_service = MockTurnService(
            memory_repo=memory_repo,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
            report_repository=report_repository,
            config=harness_config,
            snapshot_store=snapshot_store,
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
                memory_repo=memory_repo,
                snapshot_store=snapshot_store,
                llm_provider=deepseek_provider,
                powerbi_adapter=powerbi_adapter,
                report_renderer=SalesReportRenderer(),
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

    # shutdown — dispose SQLite engine（如有）
    if _engine is not None:
        await dispose_engine(_engine)

    # 清理 app.state 引用，防止跨测试污染
    app.state.turn_service = None
    app.state.mock_turn_service = None
    app.state.report_repository = None
    app.state.conversation_history_service = None
    app.state.settings = None
    app.state._persistence_engine = None


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
