"""API 依赖注入 — M1.5

M0.4.1 修复：
- 删除模块级全局 _mock_turn_service 和 set_mock_turn_service()
- Service 通过 request.app.state 读取（由 lifespan 初始化）
- 多个 app 实例互不覆盖

M1.5 更新：
- 新增 get_turn_service() 返回通用 TurnServiceProtocol
- get_mock_turn_service() 保留为向后兼容别名
"""

from fastapi import Request

from backend.app.application.mock_turn_service import MockTurnService
from backend.app.application.turn_service_protocol import TurnServiceProtocol
from backend.app.application.conversation_history_service import ConversationHistoryService
from backend.app.application.semantic_model_discovery_service import (
    SemanticModelDiscoveryService,
)
from backend.app.config.settings import Settings, get_settings
from backend.app.report.resources import ReportRepository


def get_turn_service(request: Request) -> TurnServiceProtocol:
    """从当前 app.state 获取 TurnService

    在 lifespan 启动时由 create_app() 根据 Settings 初始化到 app.state.turn_service。
    Mock+Mock 模式返回 MockTurnService，DeepSeek+Mock 模式返回 DeepSeekTurnService。
    不同 app 实例的 state 互不覆盖。
    """
    service = getattr(request.app.state, "turn_service", None)
    if service is None:
        raise RuntimeError(
            "TurnService not initialized — "
            "check Settings.llm_mode and Settings.powerbi_mode configuration"
        )
    return service


def get_mock_turn_service(request: Request) -> MockTurnService:
    """从当前 app.state 获取 MockTurnService（向后兼容别名）

    仅 Mock+Mock 模式可用。其他模式返回 None 并抛出 RuntimeError。
    """
    service = getattr(request.app.state, "mock_turn_service", None)
    if service is None:
        raise RuntimeError(
            "MockTurnService not initialized — "
            "current mode does not use Mock LLM"
        )
    return service


def get_settings_dep(request: Request) -> Settings:
    """从 app.state 读取 Settings — 使用 app 实例绑定的配置，不使用全局缓存

    这样测试可以通过 create_app(settings=...) 注入自定义 Settings，
    而不会被全局 get_settings() 缓存干扰。
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return get_settings()
    return settings


def get_report_repository(request: Request) -> ReportRepository:
    """Return the app-scoped repository that exclusively owns report artifacts."""
    repository = getattr(request.app.state, "report_repository", None)
    if repository is None:
        raise RuntimeError("ReportRepository not initialized")
    return repository


def get_conversation_history_service(request: Request) -> ConversationHistoryService:
    """Return the SQLite-backed M4.3 query service for this app instance."""
    service = getattr(request.app.state, "conversation_history_service", None)
    if service is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="conversation_history_requires_sqlite"
        )
    return service


def get_semantic_model_discovery_service(
    request: Request,
) -> SemanticModelDiscoveryService:
    """Return the app-scoped read-only Desktop model discovery service."""
    service = getattr(request.app.state, "semantic_model_discovery_service", None)
    if service is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={"error_type": "semantic_model_discovery_unavailable"},
        )
    return service
