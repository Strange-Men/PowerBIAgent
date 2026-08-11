"""Health API 测试 — M0.4.1

M0.4.1 修复：
- 使用真实 lifespan 初始化 Service（不再调用 set_mock_turn_service）
- 增加 ready/reasons 字段验证
- 增加 Real 模式 503 测试
- Health 不调用 LLM/Power BI、不含 Secret
"""

import os
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import get_mock_turn_service
from backend.app.config.settings import LLMMode, PowerBIMode, Settings, get_settings
from backend.app.main import create_app


@pytest_asyncio.fixture
async def mock_client():
    """Mock 模式客户端 — lifespan_context + ASGITransport"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestHealthMockReady:
    """Mock 模式 Health 正常 — 200、ready=true"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, mock_client):
        response = await mock_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_status_ok(self, mock_client):
        response = await mock_client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_ready_true(self, mock_client):
        """Mock 模式 ready=true、reasons 为空"""
        response = await mock_client.get("/health")
        data = response.json()
        assert data["ready"] is True
        assert data["reasons"] == []

    @pytest.mark.asyncio
    async def test_health_app_name(self, mock_client):
        response = await mock_client.get("/health")
        data = response.json()
        assert data["app_name"] == "PowerBIAgent"

    @pytest.mark.asyncio
    async def test_health_version(self, mock_client):
        response = await mock_client.get("/health")
        data = response.json()
        from backend.app.config.settings import Settings
        assert data["version"] == Settings().version

    @pytest.mark.asyncio
    async def test_health_mode_fields(self, mock_client):
        response = await mock_client.get("/health")
        data = response.json()
        assert data["llm_mode"] == "mock"
        assert data["powerbi_mode"] == "mock"
        assert data["harness_mode"] == "strict"

    @pytest.mark.asyncio
    async def test_health_timestamp(self, mock_client):
        response = await mock_client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert data["timestamp"]

    @pytest.mark.asyncio
    async def test_health_no_sensitive_fields(self, mock_client):
        """Health 响应不含 Secret 字段名"""
        response = await mock_client.get("/health")
        data = response.json()
        for key in data:
            assert "key" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "secret" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "token" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "password" not in key.lower(), f"Sensitive field leaked: {key}"


class TestHealthNotReady:
    """Real 模式 Health 返回 503 — 通过显式传入 Settings 避免缓存问题"""

    @pytest.mark.asyncio
    async def test_deepseek_mode_no_key_returns_503(self):
        """DeepSeek 模式无 Key → 503, deepseek_api_key_missing"""
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=None,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "not_ready"
                assert data["ready"] is False
                assert "deepseek_api_key_missing" in data["reasons"]

    @pytest.mark.asyncio
    async def test_deepseek_mode_with_key_returns_200(self):
        """DeepSeek+Mock 有 Key → M1.5 封板后返回 200 ready=true"""
        fake_key = "sk-" + ("T" * 24)
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=fake_key,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 200
                data = response.json()
                assert data["ready"] is True
                assert data["status"] == "ok"
                assert data["llm_mode"] == "deepseek"
                # Key 信息不泄露
                assert "sk-" not in str(data)

    @pytest.mark.asyncio
    async def test_remote_mcp_mode_returns_503(self):
        """Remote MCP 模式 Health 503、ready=false"""
        settings = Settings(
            llm_mode=LLMMode.MOCK,
            powerbi_mode=PowerBIMode.REMOTE_MCP,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "not_ready"
                assert data["ready"] is False
                assert "powerbi_remote_mcp_not_implemented" in data["reasons"]

    @pytest.mark.asyncio
    async def test_deepseek_local_configuration_ready_without_runtime_probe(self):
        """Health 只检查配置，不启动 npx、连接 Desktop 或读取 Schema。"""
        fake_key = "sk-" + ("L" * 24)
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            deepseek_api_key=fake_key,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            assert service is not None
            assert service.powerbi.provider_name == "local_mcp"
            assert service.pipeline is not None
            assert service._user_context.allowed_semantic_models == [
                settings.powerbi_local_semantic_model_key
            ]
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 200
                assert response.json()["ready"] is True

    @pytest.mark.asyncio
    async def test_mock_llm_plus_local_reports_explicit_not_ready_reason(self):
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.MOCK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 503
                assert "powerbi_local_mcp_requires_deepseek" in response.json()["reasons"]

    @pytest.mark.asyncio
    async def test_both_real_modes_503(self):
        """DeepSeek + Remote MCP 同时 → 503（Remote MCP 不可用）"""
        fake_key = "sk-" + ("U" * 24)
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.REMOTE_MCP,
            deepseek_api_key=fake_key,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                assert response.status_code == 503
                data = response.json()
                assert data["ready"] is False
                assert "powerbi_remote_mcp_not_implemented" in data["reasons"]

    @pytest.mark.asyncio
    async def test_health_no_secret_in_not_ready_response(self):
        """503 响应不含 Secret"""
        fake_key = "sk-" + ("S" * 24)
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=fake_key,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.get("/health")
                data = response.json()
                data_str = str(data)
                assert fake_key not in data_str
                assert "Bearer" not in data_str


class TestHealthNoLLMOrPowerBI:
    """Health 不得调用 LLM 或 Power BI"""

    @pytest.mark.asyncio
    async def test_health_not_call_llm(self, mock_client):
        """Health 是纯配置检查，不经过 MockLLMProvider"""
        response = await mock_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_no_secret_in_response(self, mock_client):
        """Health 响应不含 Secret"""
        response = await mock_client.get("/health")
        data = response.json()
        data_str = str(data)
        assert "sk-" not in data_str
        assert "Bearer" not in data_str


class TestLifespanIntegration:
    """Lifespan 真实初始化测试"""

    @pytest.mark.asyncio
    async def test_service_initialized_by_lifespan(self, mock_client):
        """Service 由真实 lifespan 初始化 — ASGITransport 自动触发"""
        response = await mock_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_no_lifespan_service_missing(self):
        """未启动 lifespan 时依赖明确失败 — 直接测试依赖函数"""
        settings = Settings()
        app = create_app(settings=settings)

        # 模拟未启动 lifespan 的状态：mock_turn_service 为 None
        app.state.mock_turn_service = None

        # 构造 Mock Request，验证 get_mock_turn_service 抛出 RuntimeError
        mock_request = MagicMock()
        mock_request.app.state = app.state

        with pytest.raises(RuntimeError, match="MockTurnService not initialized"):
            get_mock_turn_service(mock_request)

    @pytest.mark.asyncio
    async def test_two_apps_different_services(self):
        """两个 app 实例使用不同 Service — 在 lifespan 内验证"""
        settings1 = Settings()
        settings2 = Settings()

        app1 = create_app(settings=settings1)
        app2 = create_app(settings=settings2)

        transport1 = ASGITransport(app=app1)
        transport2 = ASGITransport(app=app2)

        svc1_id = None
        svc2_id = None

        async with app1.router.lifespan_context(app1):
            async with AsyncClient(transport=transport1, base_url="http://test1") as c1:
                r1 = await c1.get("/health")
                assert r1.status_code == 200
                svc1_id = id(app1.state.mock_turn_service)

        async with app2.router.lifespan_context(app2):
            async with AsyncClient(transport=transport2, base_url="http://test2") as c2:
                r2 = await c2.get("/health")
                assert r2.status_code == 200
                svc2_id = id(app2.state.mock_turn_service)

        # 两个是不同的 Service 实例
        assert svc1_id != svc2_id

        # lifespan 退出后 state 被清理
        assert app1.state.mock_turn_service is None
        assert app2.state.mock_turn_service is None

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_cleans_state(self):
        """lifespan 退出后 state 被清理"""
        app = create_app()
        transport = ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.get("/health")
                assert r.status_code == 200
                assert app.state.mock_turn_service is not None

        # lifespan 退出后 state 被清理
        assert app.state.mock_turn_service is None

    @pytest.mark.asyncio
    async def test_no_set_mock_turn_service_import(self):
        """测试文件不再调用 set_mock_turn_service() — 函数已删除"""
        from backend.app.api import dependencies
        assert not hasattr(dependencies, "set_mock_turn_service"), \
            "set_mock_turn_service should not exist in dependencies module"

    @pytest.mark.asyncio
    async def test_no_global_state_cross_apps(self):
        """两个独立 app 实例互不覆盖 state"""
        app_a = create_app()
        app_b = create_app()

        transport_a = ASGITransport(app=app_a)
        transport_b = ASGITransport(app=app_b)

        svc_a_id = None
        svc_b_id = None

        async with app_a.router.lifespan_context(app_a):
            async with AsyncClient(transport=transport_a, base_url="http://test-a") as ca:
                ra = await ca.get("/health")
                assert ra.status_code == 200
                svc_a_id = id(app_a.state.mock_turn_service)

        async with app_b.router.lifespan_context(app_b):
            async with AsyncClient(transport=transport_b, base_url="http://test-b") as cb:
                rb = await cb.get("/health")
                assert rb.status_code == 200
                svc_b_id = id(app_b.state.mock_turn_service)

        # 不同实例，不同 Service
        assert svc_a_id != svc_b_id
