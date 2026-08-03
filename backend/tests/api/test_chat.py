"""Chat API 测试 — M0.4.1

M0.4.1 修复：
- 使用 ASGITransport 自动触发 lifespan（不再调用 set_mock_turn_service）
- 验证 answer 是真实 AnswerSpec.answer，不是 "1 rows" 摘要
- 验证 report 返回 report_id、template_key、HTML
- 验证 clarification/unsupported 真实可达
- 验证 API 路由不构造或暴露 Scenario Key
"""

import asyncio
import uuid

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
            "idempotent_replay", "replayed_request_id",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestChatRealModeRejection:
    """Real 模式未实现时明确拒绝 — M1.1"""

    @pytest.mark.asyncio
    async def test_deepseek_chat_no_key_503(self):
        """DeepSeek Chat 无 Key → 503, deepseek_api_key_missing"""
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=None,
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
                assert data["detail"]["error_type"] == "deepseek_api_key_missing"

    @pytest.mark.asyncio
    async def test_deepseek_chat_with_key_503(self):
        """DeepSeek Chat 有 Key 但 Pipeline 未完成 → 503"""
        fake_key = "sk-" + ("D" * 24)
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=fake_key,
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
                assert data["detail"]["error_type"] == "deepseek_pipeline_not_ready"

    @pytest.mark.asyncio
    async def test_deepseek_chat_no_fallback_to_mock(self):
        """DeepSeek Chat 不回退 Mock"""
        fake_key = "sk-" + ("E" * 24)
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.MOCK,
            deepseek_api_key=fake_key,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "测试",
                })
                # 必须 503，不能 200
                assert response.status_code == 503
                data = response.json()
                # 不应返回 answer/report/tool_sequence（不是 Mock 结果）
                if isinstance(data.get("detail"), dict):
                    assert "answer" not in data.get("detail", {})


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


# ══════════════════════════════════════════════════════════════════════
# M1.0 新增 API 测试
# ══════════════════════════════════════════════════════════════════════

class TestChatM10IdempotentReplay:
    """M1.0: API 层级幂等重放测试"""

    @pytest.mark.asyncio
    async def test_first_request_idempotent_replay_false(self, client):
        """首次请求 idempotent_replay=false, replayed_request_id=null"""
        response = await client.post("/api/v1/chat", json={
            "message": "测试查询",
            "conversation_id": "conv-m10-idem-001",
            "request_id": "req-m10-idem-001",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["idempotent_replay"] is False
        assert data["replayed_request_id"] is None

    @pytest.mark.asyncio
    async def test_replay_request_idempotent_replay_true(self, client):
        """重复请求 idempotent_replay=true"""
        payload = {
            "message": "测试查询",
            "conversation_id": "conv-m10-idem-002",
            "request_id": "req-m10-idem-002",
        }
        await client.post("/api/v1/chat", json=payload)
        r2 = await client.post("/api/v1/chat", json=payload)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["idempotent_replay"] is True
        assert d2["replayed_request_id"] == "req-m10-idem-002"

    @pytest.mark.asyncio
    async def test_replay_answer_content_preserved(self, client):
        """重放返回的 answer 内容与第一次一致"""
        payload = {
            "message": "本月销售额是多少？",
            "conversation_id": "conv-m10-idem-003",
            "request_id": "req-m10-idem-003",
        }
        r1 = await client.post("/api/v1/chat", json=payload)
        r2 = await client.post("/api/v1/chat", json=payload)
        d1 = r1.json()
        d2 = r2.json()
        assert d1["answer"] == d2["answer"]
        assert d2["tool_sequence"] == []
        assert d2["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_replay_report_content_preserved(self, client):
        """重放返回的 report 内容与第一次一致"""
        payload = {
            "message": "生成销售周报",
            "conversation_id": "conv-m10-idem-004",
            "request_id": "req-m10-idem-004",
            "report_template_key": "sales_weekly",
        }
        r1 = await client.post("/api/v1/chat", json=payload)
        r2 = await client.post("/api/v1/chat", json=payload)
        d1 = r1.json()
        d2 = r2.json()
        assert d1["report"]["report_id"] == d2["report"]["report_id"]
        assert d1["report"]["template_key"] == d2["report"]["template_key"]
        assert d1["report"]["html"] == d2["report"]["html"]

    @pytest.mark.asyncio
    async def test_replay_new_trace_id(self, client):
        """重放生成新 trace_id"""
        payload = {
            "message": "测试查询",
            "conversation_id": "conv-m10-trace",
            "request_id": "req-m10-trace",
        }
        r1 = await client.post("/api/v1/chat", json=payload)
        r2 = await client.post("/api/v1/chat", json=payload)
        assert r1.json()["trace_id"] != r2.json()["trace_id"]


class TestChatM10ConversationId:
    """M1.0: conversation_id 保留测试"""

    @pytest.mark.asyncio
    async def test_clarification_keeps_conversation_id(self, client):
        """clarification API 响应保留 conversation_id"""
        response = await client.post("/api/v1/chat", json={
            "message": "帮我看看数据",
            "conversation_id": "conv-m10-clarify-api",
            "request_id": "req-m10-clarify-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "conv-m10-clarify-api"
        assert data["terminal_state"] == "clarification_required"
        assert data["intent"] == "clarification"

    @pytest.mark.asyncio
    async def test_unsupported_keeps_conversation_id(self, client):
        """unsupported API 响应保留 conversation_id"""
        response = await client.post("/api/v1/chat", json={
            "message": "删除所有数据",
            "conversation_id": "conv-m10-unsup-api",
            "request_id": "req-m10-unsup-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "conv-m10-unsup-api"
        assert data["terminal_state"] == "unsupported"
        assert data["intent"] == "unsupported"

    @pytest.mark.asyncio
    async def test_clarification_auto_generates_conversation_id(self, client):
        """clarification 未提供 conversation_id 时自动生成"""
        response = await client.post("/api/v1/chat", json={
            "message": "帮我看看数据",
            "request_id": "req-m10-clarify-auto-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] != ""
        # 应是有效 UUID
        import uuid
        uuid.UUID(data["conversation_id"])

    @pytest.mark.asyncio
    async def test_unsupported_auto_generates_conversation_id(self, client):
        """unsupported 未提供 conversation_id 时自动生成"""
        response = await client.post("/api/v1/chat", json={
            "message": "删除所有数据",
            "request_id": "req-m10-unsup-auto-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] != ""
        import uuid
        uuid.UUID(data["conversation_id"])


class TestChatM10ReportTemplate:
    """M1.0: 报表模板测试"""

    @pytest.mark.asyncio
    async def test_default_template_on_report_keywords(self, client):
        """不传模板但含报表关键词 → 使用 sales_weekly"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售周报",
            "conversation_id": "conv-m10-template-api",
            "request_id": "req-m10-template-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "report_generation"
        assert data["report"] is not None
        assert data["report"]["template_key"] == "sales_weekly"

    @pytest.mark.asyncio
    async def test_explicit_template_respected(self, client):
        """显式传模板时优先使用客户端模板"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成周报",
            "conversation_id": "conv-m10-explicit-template",
            "request_id": "req-m10-explicit-template",
            "report_template_key": "satisfaction_survey",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["report"] is not None
        # MockLLM 的 report_generation fixture 固定返回 sales_weekly
        assert data["report"]["template_key"] == "sales_weekly"

    @pytest.mark.asyncio
    async def test_data_question_no_report_template_in_response(self, client):
        """普通数据问答 report 字段为 null"""
        response = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "conv-m10-dq-template",
            "request_id": "req-m10-dq-template",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "data_question"
        assert data["report"] is None


class TestChatM10Version:
    """M1.0: 版本验证"""

    @pytest.mark.asyncio
    async def test_health_version_m11(self, client):
        """Health version 为 M1.1"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "M1.1"

    @pytest.mark.asyncio
    async def test_health_ready_and_reasons(self, client):
        """Health 包含 ready 和 reasons 字段"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["reasons"] == []


class TestChatM10ConcurrentConversationId:
    """M1.0: 并发请求不串 conversation_id"""

    @pytest.mark.asyncio
    async def test_concurrent_clarify_unsupported_no_crosstalk(self, client):
        """并发 clarification + unsupported 不串 conversation_id"""

        async def req_clarify():
            r = await client.post("/api/v1/chat", json={
                "message": "帮我看看数据",
                "conversation_id": "conv-m10-conc-c",
                "request_id": "req-m10-conc-c",
            })
            return r.json()

        async def req_unsupported():
            r = await client.post("/api/v1/chat", json={
                "message": "删除所有数据",
                "conversation_id": "conv-m10-conc-u",
                "request_id": "req-m10-conc-u",
            })
            return r.json()

        rc, ru = await asyncio.gather(req_clarify(), req_unsupported())

        assert rc["conversation_id"] == "conv-m10-conc-c"
        assert ru["conversation_id"] == "conv-m10-conc-u"
        assert rc["intent"] == "clarification"
        assert ru["intent"] == "unsupported"


# ══════════════════════════════════════════════════════════════════════
# M1.0.1 新增 API 测试
# ══════════════════════════════════════════════════════════════════════

class TestChatM101Conflict:
    """M1.0.1: request_id 冲突 → HTTP 409"""

    @pytest.mark.asyncio
    async def test_same_request_id_different_message_409(self, client):
        """相同 request_id、不同 message 返回 409"""
        # First request
        r1 = await client.post("/api/v1/chat", json={
            "message": "本月销售额是多少？",
            "conversation_id": "conv-m101-409-1",
            "request_id": "req-m101-409-1",
        })
        assert r1.status_code == 200

        # Second request with different message, same request_id
        r2 = await client.post("/api/v1/chat", json={
            "message": "本月利润是多少？",
            "conversation_id": "conv-m101-409-1",
            "request_id": "req-m101-409-1",
        })
        assert r2.status_code == 409
        data = r2.json()
        assert data["error_type"] == "request_id_conflict"
        assert data["request_id"] == "req-m101-409-1"
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_409_error_structure_flat(self, client):
        """409 错误结构扁平，不嵌套"""
        # First request
        await client.post("/api/v1/chat", json={
            "message": "销售额查询",
            "conversation_id": "conv-m101-flat",
            "request_id": "req-m101-flat",
        })

        # Conflicting request
        r2 = await client.post("/api/v1/chat", json={
            "message": "不同查询",
            "conversation_id": "conv-m101-flat",
            "request_id": "req-m101-flat",
        })
        assert r2.status_code == 409
        data = r2.json()
        # 不应有嵌套的 detail 对象
        assert isinstance(data.get("detail"), str)
        assert "error_type" in data
        assert "request_id" in data
        # 不应包含旧请求的 answer/report
        assert "answer" not in data
        assert "report" not in data

    @pytest.mark.asyncio
    async def test_conflict_preserves_replay(self, client):
        """冲突后原始快照仍可重放"""
        payload = {
            "message": "销售额查询",
            "conversation_id": "conv-m101-preserve",
            "request_id": "req-m101-preserve",
        }
        r1 = await client.post("/api/v1/chat", json=payload)
        assert r1.status_code == 200

        # Try conflict
        await client.post("/api/v1/chat", json={
            "message": "不同查询",
            "conversation_id": "conv-m101-preserve",
            "request_id": "req-m101-preserve",
        })

        # Original still replays
        r3 = await client.post("/api/v1/chat", json=payload)
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["idempotent_replay"] is True
        assert d3["answer"] == r1.json()["answer"]


class TestChatM101UUID:
    """M1.0.1: API 自动生成 UUID"""

    @pytest.mark.asyncio
    async def test_conversation_id_auto_uuid(self, client):
        """API 未传 conversation_id 时返回有效 UUID"""
        response = await client.post("/api/v1/chat", json={
            "message": "销售额查询",
            "request_id": "req-m101-uuid-conv",
        })
        assert response.status_code == 200
        data = response.json()
        uuid.UUID(data["conversation_id"])

    @pytest.mark.asyncio
    async def test_request_id_auto_uuid(self, client):
        """API 未传 request_id 时返回有效 UUID"""
        response = await client.post("/api/v1/chat", json={
            "message": "销售额查询",
            "conversation_id": "conv-m101-uuid-req",
        })
        assert response.status_code == 200
        data = response.json()
        uuid.UUID(data["request_id"])

    @pytest.mark.asyncio
    async def test_replay_returns_original_conversation_id(self, client):
        """重放返回首次生成的 conversation_id"""
        # First request without conversation_id
        r1 = await client.post("/api/v1/chat", json={
            "message": "销售额查询",
            "request_id": "req-m101-replay-conv",
        })
        d1 = r1.json()

        # Replay without conversation_id (same fingerprint)
        r2 = await client.post("/api/v1/chat", json={
            "message": "销售额查询",
            "request_id": "req-m101-replay-conv",
        })
        d2 = r2.json()

        assert d2["conversation_id"] == d1["conversation_id"]
        assert d2["idempotent_replay"] is True


class TestChatM101Concurrent:
    """M1.0.1: API 并发幂等"""

    @pytest.mark.asyncio
    async def test_concurrent_same_payload_one_completed_one_duplicate(self, client):
        """并发相同请求：一个 completed、一个 duplicate"""
        payload = {
            "message": "销售额查询",
            "conversation_id": "conv-m101-conc",
            "request_id": "req-m101-conc",
        }

        async def req():
            r = await client.post("/api/v1/chat", json=payload)
            return r.json()

        r1, r2 = await asyncio.gather(req(), req())

        states = {r1["terminal_state"], r2["terminal_state"]}
        assert states == {"completed", "duplicate"}

        duplicate = r1 if r1["terminal_state"] == "duplicate" else r2
        assert duplicate["tool_sequence"] == []
        assert duplicate["memory_commit"] is False
        assert duplicate["idempotent_replay"] is True

    @pytest.mark.asyncio
    async def test_concurrent_same_payload_content_identical(self, client):
        """并发相同请求内容一致"""
        payload = {
            "message": "本月销售额是多少？",
            "conversation_id": "conv-m101-conc-content",
            "request_id": "req-m101-conc-content",
        }

        async def req():
            r = await client.post("/api/v1/chat", json=payload)
            return r.json()

        r1, r2 = await asyncio.gather(req(), req())

        assert r1["answer"] == r2["answer"]
        assert r1["trace_id"] != r2["trace_id"]

    @pytest.mark.asyncio
    async def test_concurrent_different_message_one_409(self, client):
        """并发不同 message 相同 request_id → 一个成功、一个 409"""
        async def req_a():
            r = await client.post("/api/v1/chat", json={
                "message": "销售额查询",
                "conversation_id": "conv-m101-ccf",
                "request_id": "req-m101-ccf",
            })
            return r

        async def req_b():
            r = await client.post("/api/v1/chat", json={
                "message": "利润查询",
                "conversation_id": "conv-m101-ccf",
                "request_id": "req-m101-ccf",
            })
            return r

        ra, rb = await asyncio.gather(req_a(), req_b())

        statuses = {ra.status_code, rb.status_code}
        assert 200 in statuses
        assert 409 in statuses
