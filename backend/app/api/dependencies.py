"""API 依赖注入 — M0.4"""

from typing import Optional

from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import Settings, get_settings


# 模块级共享 — 在 lifespan 中初始化
_mock_turn_service: Optional[MockTurnService] = None


def get_mock_turn_service() -> MockTurnService:
    """获取全局共享的 MockTurnService 实例

    在 lifespan 启动时由 create_app() 初始化。
    MockTurnService 自身无请求级可变状态（M0.4 修复后），可安全并发复用。
    """
    if _mock_turn_service is None:
        raise RuntimeError(
            "MockTurnService not initialized — ensure app lifespan has started"
        )
    return _mock_turn_service


def set_mock_turn_service(service: MockTurnService) -> None:
    """由 lifespan 初始化调用"""
    global _mock_turn_service
    _mock_turn_service = service


def get_settings_dep() -> Settings:
    """FastAPI Depends 用的 Settings 注入"""
    return get_settings()
