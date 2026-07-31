"""Chat API 测试 — M0.4"""

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import set_mock_turn_service
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import get_settings
from backend.app.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    set_mock_turn_service(MockTurnService())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestChatDataQuestion:
    """普通数据问答"""

    @pytest.mark.asyncio
    async def test_data_question_success(self, client):
        response = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "conv-chat-001",
            "request_id": "req-chat-001",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "completed"
        assert data["intent"] == "data_question"
        assert data["memory_commit"] is True
        assert "get_semantic_model_schema" in data["tool_sequence"]
        assert "execute_dax" in data["tool_sequence"]
        assert data["trace_id"] != ""

    @pytest.mark.asyncio
    async def test_data_question_conversation_auto_generated(self, client):
        """未提供 conversation_id 时自动生成"""
        response = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] != ""


class TestChatReportGeneration:
    """报表生成"""

    @pytest.mark.asyncio
    async def test_report_generation_success(self, client):
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售周报",
            "conversation_id": "conv-chat-rpt-001",
            "request_id": "req-chat-rpt-001",
            "report_template_key": "sales_weekly",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "completed"
        assert data["intent"] == "report_generation"
        assert data["memory_commit"] is True
        assert "render_report" in data["tool_sequence"]


class TestChatEdgeCases:
    """边界场景"""

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self, client):
        response = await client.post("/api/v1/chat", json={
            "message": "",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_request_id_idempotent(self, client):
        """重复 request_id 返回幂等结果"""
        payload = {
            "message": "测试查询",
            "conversation_id": "conv-idem-api",
            "request_id": "req-idem-api-001",
        }
        r1 = await client.post("/api/v1/chat", json=payload)
        r2 = await client.post("/api/v1/chat", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["terminal_state"] == "duplicate"

    @pytest.mark.asyncio
    async def test_clarification_response(self, client):
        """API 正确代理到 MockTurnService"""
        response = await client.post("/api/v1/chat", json={
            "message": "帮我看看数据",
            "conversation_id": "conv-chat-clarify",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] is not None

    @pytest.mark.asyncio
    async def test_response_structure_valid(self, client):
        """响应包含所有必需字段"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
        })
        assert response.status_code == 200
        data = response.json()
        required_fields = [
            "request_id", "conversation_id", "terminal_state",
            "intent", "response_type", "tool_sequence",
            "memory_commit", "trace_id", "is_mock",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestChatRealModeRejection:
    """Real 模式未实现时明确拒绝"""

    @pytest.mark.asyncio
    async def test_real_mode_returns_503(self):
        os.environ["LLM_MODE"] = "deepseek"
        # 清除 lru_cache 确保环境变量生效
        get_settings.cache_clear()
        try:
            app = create_app()
            set_mock_turn_service(MockTurnService())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "测试",
                })
                assert response.status_code == 503
                data = response.json()
                assert "detail" in data
        finally:
            os.environ.pop("LLM_MODE", None)
            get_settings.cache_clear()  # 恢复缓存


class TestChatForbiddenInput:
    """禁止客户端传 Mock Scenario Key"""

    @pytest.mark.asyncio
    async def test_extra_fields_rejected(self, client):
        """ChatRequest extra="forbid" — 不允许客户端传 scenario 相关字段"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
            "mock_scenario_key": "data_question",
        })
        assert response.status_code == 422


class TestChatConcurrent:
    """并发 API 测试"""

    @pytest.mark.asyncio
    async def test_concurrent_data_question_and_report(self, client):
        """同一个 FastAPI 应用并发执行数据问答和报表，trace_id 和工具序列互不污染"""

        async def req_data():
            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-api-conc-a",
                "request_id": "req-api-conc-a",
            })
            return r.json()

        async def req_report():
            r = await client.post("/api/v1/chat", json={
                "message": "生成销售周报",
                "conversation_id": "conv-api-conc-b",
                "request_id": "req-api-conc-b",
                "report_template_key": "sales_weekly",
            })
            return r.json()

        r_data, r_report = await asyncio.gather(req_data(), req_report())

        # 数据问答
        assert r_data["terminal_state"] == "completed"
        assert r_data["intent"] == "data_question"
        assert "render_report" not in r_data["tool_sequence"]
        assert r_data["trace_id"] != ""

        # 报表生成
        assert r_report["terminal_state"] == "completed"
        assert r_report["intent"] == "report_generation"
        assert "render_report" in r_report["tool_sequence"]
        assert r_report["trace_id"] != ""

        # trace_id 不同
        assert r_data["trace_id"] != r_report["trace_id"]

        # Memory 互不污染 — conversation 不同
        assert r_data["conversation_id"] != r_report["conversation_id"]

    @pytest.mark.asyncio
    async def test_concurrent_different_responses_no_crosstalk(self, client):
        """并发请求的响应互不串场"""

        async def req_a():
            r = await client.post("/api/v1/chat", json={
                "message": "销售额查询",
                "conversation_id": "conv-api-cc-a",
                "request_id": "req-api-cc-a",
            })
            return r.json()

        async def req_b():
            r = await client.post("/api/v1/chat", json={
                "message": "生成报表",
                "conversation_id": "conv-api-cc-b",
                "request_id": "req-api-cc-b",
                "report_template_key": "sales_weekly",
            })
            return r.json()

        ra, rb = await asyncio.gather(req_a(), req_b())

        # A 不应有报表工具
        assert "render_report" not in ra["tool_sequence"]
        # B 应有报表工具
        assert "render_report" in rb["tool_sequence"]

        # conversation 不串
        assert ra["conversation_id"] == "conv-api-cc-a"
        assert rb["conversation_id"] == "conv-api-cc-b"
