"""Chat API 测试 — M0.4.1

M0.4.1 修复：
- 使用 ASGITransport 自动触发 lifespan（不再调用 set_mock_turn_service）
- 验证 answer 是真实 AnswerSpec.answer，不是 "1 rows" 摘要
- 验证 report 返回 report_id、template_key、HTML
- 验证 clarification/unsupported 真实可达
- 验证 API 路由不构造或暴露 Scenario Key
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.main import create_app


@pytest_asyncio.fixture
async def client():
    """Mock 模式客户端 — lifespan_context + ASGITransport"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestChatDataQuestion:
    """普通数据问答 — 返回真实 Answer"""

    @pytest.mark.asyncio
    async def test_data_question_returns_real_answer(self, client):
        """普通查询返回真实 answer，不能是 "1 rows" 摘要"""
        response = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "conv-chat-001",
            "request_id": "req-chat-001",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "completed"
        assert data["intent"] == "data_question"
        assert data["response_type"] == "answer"
        # M0.4.1: answer 是真实 AnswerSpec.answer
        assert data["answer"] is not None
        assert data["answer"] != ""
        assert "rows" not in (data["answer"] or "").lower(), \
            f"answer should be real text from AnswerSpec, got: {data['answer']}"
        assert data["memory_commit"] is True
        assert "get_semantic_model_schema" in data["tool_sequence"]
        assert "execute_dax" in data["tool_sequence"]
        assert data["trace_id"] != ""

    @pytest.mark.asyncio
    async def test_data_question_auto_generate_ids(self, client):
        """未提供 conversation_id 时自动生成"""
        response = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] != ""
        assert data["request_id"] != ""

    @pytest.mark.asyncio
    async def test_data_question_answer_not_null(self, client):
        """answer 字段存在且不为空"""
        response = await client.post("/api/v1/chat", json={
            "message": "查询销售额",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] is not None
        assert len(data["answer"]) > 0


class TestChatReportGeneration:
    """报表生成 — 返回真实 Report"""

    @pytest.mark.asyncio
    async def test_report_returns_structured_data(self, client):
        """报表返回 report_id、template_key 和 HTML"""
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
        assert data["response_type"] == "report"
        assert data["memory_commit"] is True
        assert "render_report" in data["tool_sequence"]

        # M0.4.1: report 是结构化对象
        assert data["report"] is not None, "report should not be null"
        report = data["report"]
        assert report["report_id"] != "", "report_id should not be empty"
        assert report["template_key"] == "sales_weekly"
        assert report["html"] != "", "html should not be empty"

    @pytest.mark.asyncio
    async def test_report_without_template_key(self, client):
        """无 report_template_key 但消息包含报表关键词 → report_generation"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售周报",
            "conversation_id": "conv-chat-rpt-002",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "report_generation"
        assert data["report"] is not None


class TestChatClarification:
    """clarification 真实可达"""

    @pytest.mark.asyncio
    async def test_vague_message_returns_clarification(self, client):
        """"帮我看看数据" 真实返回 clarification_required"""
        response = await client.post("/api/v1/chat", json={
            "message": "帮我看看数据",
            "conversation_id": "conv-chat-clarify",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "clarification_required"
        assert data["intent"] == "clarification"
        assert data["response_type"] == "clarification"
        # M0.4.1: 返回 clarification question
        assert data["clarification_question"] is not None
        assert len(data["clarification_question"]) > 0
        # 不创建 memory
        assert data["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_ambiguous_look_message_clarification(self, client):
        """"看看有什么数据" → clarification"""
        response = await client.post("/api/v1/chat", json={
            "message": "看看有什么数据",
            "conversation_id": "conv-chat-vague",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "clarification"
        assert data["terminal_state"] == "clarification_required"


class TestChatUnsupported:
    """unsupported 真实可达"""

    @pytest.mark.asyncio
    async def test_destructive_message_returns_unsupported(self, client):
        """"删除所有数据" 真实返回 unsupported"""
        response = await client.post("/api/v1/chat", json={
            "message": "删除所有数据",
            "conversation_id": "conv-chat-unsup",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "unsupported"
        assert data["intent"] == "unsupported"
        assert data["response_type"] == "unsupported"
        # M0.4.1: 返回 unsupported reason
        assert data["unsupported_reason"] is not None
        assert len(data["unsupported_reason"]) > 0
        # 不创建 memory
        assert data["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_modify_message_unsupported(self, client):
        """"修改数据" → unsupported"""
        response = await client.post("/api/v1/chat", json={
            "message": "修改数据",
            "conversation_id": "conv-chat-modify",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "unsupported"
        assert data["terminal_state"] == "unsupported"


class TestChatNoScenarioExposure:
    """API 路由不构造或暴露 Scenario Key"""

    @pytest.mark.asyncio
    async def test_scenario_key_field_rejected(self, client):
        """额外 Scenario 字段返回 422"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
            "scenario_key": "data_question",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_intent_key_field_rejected(self, client):
        """禁止客户端传 intent_key"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
            "intent_key": "data_question",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_mock_scenario_field_rejected(self, client):
        """禁止客户端传 mock_scenario_key"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
            "mock_scenario_key": "data_question",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_response_has_no_scenario_field(self, client):
        """响应不含 scenario_key"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试",
        })
        assert response.status_code == 200
        data = response.json()
        assert "scenario_key" not in data
        assert "scenario" not in data


class TestChatIdempotent:
    """幂等测试"""

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


class TestChatStructure:
    """响应结构完整性"""

    @pytest.mark.asyncio
    async def test_response_has_all_required_fields(self, client):
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
            "answer", "report",
            "clarification_question", "unsupported_reason",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestChatRealModeRejection:
    """Real 模式未实现时明确拒绝"""

    @pytest.mark.asyncio
    async def test_real_mode_chat_returns_503(self):
        """DeepSeek 模式 chat 返回 503"""
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "测试",
                })
                assert response.status_code == 503
                data = response.json()
                assert "detail" in data


class TestChatConcurrent:
    """并发 API 测试 — 不串场"""

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
        assert r_data["answer"] is not None

        # 报表生成
        assert r_report["terminal_state"] == "completed"
        assert r_report["intent"] == "report_generation"
        assert "render_report" in r_report["tool_sequence"]
        assert r_report["trace_id"] != ""
        assert r_report["report"] is not None

        # trace_id 不同
        assert r_data["trace_id"] != r_report["trace_id"]

        # Memory 互不污染
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

        assert "render_report" not in ra["tool_sequence"]
        assert "render_report" in rb["tool_sequence"]
        assert ra["conversation_id"] == "conv-api-cc-a"
        assert rb["conversation_id"] == "conv-api-cc-b"


class TestChatEmptyMessage:
    """空消息拒绝"""

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self, client):
        response = await client.post("/api/v1/chat", json={
            "message": "",
        })
        assert response.status_code == 422
