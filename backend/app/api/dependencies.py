"""API 依赖注入 — M0.4.1

M0.4.1 修复：
- 删除模块级全局 _mock_turn_service 和 set_mock_turn_service()
- Service 通过 request.app.state 读取（由 lifespan 初始化）
- 多个 app 实例互不覆盖
"""

from fastapi import Request

from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import Settings, get_settings


def get_mock_turn_service(request: Request) -> MockTurnService:
    """从当前 app.state 获取 MockTurnService

    在 lifespan 启动时由 create_app() 初始化到 app.state.mock_turn_service。
    不同 app 实例的 state 互不覆盖。
    """
    service = getattr(request.app.state, "mock_turn_service", None)
    if service is None:
        raise RuntimeError(
            "MockTurnService not initialized — ensure app lifespan has started"
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
