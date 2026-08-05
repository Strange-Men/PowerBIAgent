"""M1.2 集成测试 — Mock 隔离验证"""

from __future__ import annotations

from pydantic import SecretStr
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import Settings
from backend.app.main import create_app


@pytest_asyncio.fixture
async def mock_client():
    """Mock 模式客户端"""
    settings = Settings(llm_mode="mock", powerbi_mode="mock")
    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestHealthM12:

    @pytest.mark.asyncio
    async def test_health_mock_200(self):
        settings = Settings(llm_mode="mock", powerbi_mode="mock")
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ready"] is True
                assert data["version"] == "M1.6.4"

    @pytest.mark.asyncio
    async def test_health_deepseek_no_key_503(self):
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=None,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 503
                data = resp.json()
                assert data["ready"] is False
                # deepseek_api_key_missing
                reason_text = " ".join(data["reasons"])
                assert "api_key_missing" in reason_text

    @pytest.mark.asyncio
    async def test_health_deepseek_with_key_returns_200(self):
        """M1.5: DeepSeek+Mock 有 Key → Health 200 ready=true"""
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=SecretStr("sk-" + ("T" * 30)),
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ready"] is True
                assert data["llm_mode"] == "deepseek"


class TestChatM12:

    @pytest.mark.asyncio
    async def test_chat_mock_data_question(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "test-dq-m12-001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "data_question"
        assert data["is_mock"] is True

    @pytest.mark.asyncio
    async def test_chat_mock_report_generation(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "生成本周销售周报",
            "conversation_id": "test-rg-m12-001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "report_generation"

    @pytest.mark.asyncio
    async def test_chat_mock_clarification(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "帮我看看",
            "conversation_id": "test-cl-m12-001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "clarification"

    @pytest.mark.asyncio
    async def test_chat_mock_unsupported(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "删除Power BI数据",
            "conversation_id": "test-us-m12-001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "unsupported"

    @pytest.mark.asyncio
    async def test_chat_mock_answer(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "test-ans-m12-001",
        })
        data = resp.json()
        assert data["response_type"] == "answer"
        assert data["answer"] is not None

    @pytest.mark.asyncio
    async def test_chat_mock_report(self, mock_client):
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "生成本周销售周报",
            "conversation_id": "test-rep-m12-001",
        })
        data = resp.json()
        assert data["response_type"] == "report"
        assert data["report"] is not None
        assert data["report"]["html"] is not None

    @pytest.mark.asyncio
    async def test_chat_deepseek_no_fallback_to_mock(self):
        """M1.5: DeepSeek Chat 可用，不回退 Mock LLM"""
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=SecretStr("sk-" + ("T" * 30)),
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v1/chat", json={
                    "message": "本月销售额是多少？",
                })
                # M1.5: Chat 已启用，假 Key 不会返回 503 mode guard
                # 实际会尝试调用 DeepSeek API 并因假 Key 失败
                assert resp.status_code != 200  # 不应返回 Mock 成功
                data = resp.json()
                detail = data.get("detail", {})
                if isinstance(detail, dict):
                    assert detail.get("error_type") != "deepseek_pipeline_not_ready"


class TestReplayM12:

    @pytest.mark.asyncio
    async def test_request_id_replay_normal(self, mock_client):
        rid = "test-replay-m12-" + "001"
        resp1 = await mock_client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "request_id": rid,
            "conversation_id": "replay-conv-m12-001",
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["idempotent_replay"] is False

        resp2 = await mock_client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "request_id": rid,
            "conversation_id": "replay-conv-m12-001",
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["idempotent_replay"] is True

    @pytest.mark.asyncio
    async def test_request_id_conflict_409(self, mock_client):
        rid = "test-conflict-m12-" + "001"
        await mock_client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "request_id": rid,
            "conversation_id": "conflict-conv-m12-001",
        })
        resp = await mock_client.post("/api/v1/chat", json={
            "message": "不同的消息内容",
            "request_id": rid,
            "conversation_id": "conflict-conv-m12-001",
        })
        assert resp.status_code == 409


class TestMockScenarioResolverRegression:

    def test_resolver_data_question(self):
        from backend.app.application.mock_scenario_resolver import MockScenarioResolver
        resolution = MockScenarioResolver.resolve("本月销售额是多少？")
        assert resolution.scenario.intent_key == "data_question"

    def test_resolver_report_generation(self):
        from backend.app.application.mock_scenario_resolver import MockScenarioResolver
        resolution = MockScenarioResolver.resolve("生成本周销售周报")
        assert resolution.scenario.intent_key == "report_generation"

    def test_resolver_clarification(self):
        from backend.app.application.mock_scenario_resolver import MockScenarioResolver
        resolution = MockScenarioResolver.resolve("帮我看看")
        assert resolution.scenario.intent_key == "clarification"

    def test_resolver_unsupported(self):
        from backend.app.application.mock_scenario_resolver import MockScenarioResolver
        resolution = MockScenarioResolver.resolve("删除Power BI数据")
        assert resolution.scenario.intent_key == "unsupported"

    def test_resolver_report_with_template(self):
        from backend.app.application.mock_scenario_resolver import MockScenarioResolver
        resolution = MockScenarioResolver.resolve("查看报表", report_template_key="custom_template")
        assert resolution.scenario.intent_key == "report_generation"
        assert resolution.effective_report_template_key == "custom_template"
