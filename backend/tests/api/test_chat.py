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
from pydantic import BaseModel

from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.intent.models import (
    IntentSpec,
    IntentType,
    TimeIntentDraft,
    TimeIntentKind,
    TurnRelation,
)
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.llm.profiles import LLMModelProfile, LLMProviderProtocol
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.main import create_app
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.query_plan.semantic_catalog import (
    SemanticCatalogBuilder,
    compute_schema_fingerprint,
)
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    ColumnMembersRequest,
    ColumnMembersResult,
    ColumnSchema,
    DAXRequest,
    MeasureSchema,
    PowerBIError,
    QueryPlan,
    QueryResult,
    RelationshipSchema,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
)


def _llm_test_profile(
    profile_key: str = "deepseek",
    model: str = "fake-deepseek",
) -> LLMModelProfile:
    return LLMModelProfile(
        profile_key=profile_key,
        display_name="DeepSeek" if profile_key == "deepseek" else "Kimi K2.6",
        provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        base_url="https://llm.invalid/v1",
        model=model,
        timeout_seconds=30,
    )


def _deepseek_test_profile() -> LLMModelProfile:
    return _llm_test_profile()


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

    def test_openapi_powerbi_mode_description_lists_current_modes(self):
        schema = create_app().openapi()
        description = schema["components"]["schemas"]["ChatResponse"][
            "properties"
        ]["powerbi_mode"]["description"]
        assert "mock" in description
        assert "local_mcp" in description
        assert "remote_mcp" in description
        assert "Deferred" in description

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
            "message": "生成销售报告",
            "conversation_id": "conv-chat-rpt-001",
            "request_id": "req-chat-rpt-001",
            "report_template_key": "sales_report",
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
        assert report["template_key"] == "sales_report"
        assert report["html"] != "", "html should not be empty"

    @pytest.mark.asyncio
    async def test_report_without_template_key(self, client):
        """报表请求未显式选模板时，必须在任何工具和 artifact 前早停。"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售周报",
            "conversation_id": "conv-chat-rpt-002",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "clarification_required"
        assert data["intent"] == "report_generation"
        assert data["response_type"] == "clarification"
        assert data["clarification_question"] == "生成报表前请选择有效的模板"
        assert data["report"] is None
        assert data["memory_commit"] is False
        assert data["tool_sequence"] == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_key", ["unknown_template", "sales_weekly"])
    async def test_report_with_invalid_or_stale_template_fails_closed(
        self, client, template_key
    ):
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售报告",
            "conversation_id": f"conv-chat-invalid-{template_key}",
            "request_id": f"req-chat-invalid-{template_key}",
            "report_template_key": template_key,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "clarification_required"
        assert data["response_type"] == "clarification"
        assert data["report"] is None
        assert data["memory_commit"] is False
        assert data["tool_sequence"] == []
        assert data["clarification_question"] == "生成报表前请选择有效的模板"

    @pytest.mark.asyncio
    async def test_normal_question_without_template_is_not_intercepted(self, client):
        response = await client.post("/api/v1/chat", json={
            "message": "查询销售额",
            "conversation_id": "conv-chat-no-template-data-question",
            "request_id": "req-chat-no-template-data-question",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "completed"
        assert data["intent"] == "data_question"
        assert data["response_type"] == "answer"
        assert data["memory_commit"] is True

    @pytest.mark.asyncio
    async def test_report_retry_succeeds_after_explicit_template_selection(self, client):
        conversation_id = "conv-chat-template-retry"
        first = await client.post("/api/v1/chat", json={
            "message": "生成销售报告",
            "conversation_id": conversation_id,
            "request_id": "req-chat-template-retry-missing",
        })
        retry = await client.post("/api/v1/chat", json={
            "message": "生成销售报告",
            "conversation_id": conversation_id,
            "request_id": "req-chat-template-retry-valid",
            "report_template_key": "sales_report",
        })
        assert first.json()["report"] is None
        assert retry.status_code == 200
        data = retry.json()
        assert data["terminal_state"] == "completed"
        assert data["report"]["template_key"] == "sales_report"
        assert data["tool_sequence"].count("render_report") == 1


class TestReportTemplateCatalog:
    @pytest.mark.asyncio
    async def test_catalog_exposes_only_backend_registered_available_templates(self, client):
        response = await client.get("/api/v1/report-templates")

        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {
                    "template_key": "sales_report",
                    "display_name": "简易模板",
                    "description": "适合快速查看关键指标、趋势与分类明细",
                    "availability": "available",
                }
            ]
        }

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
            assert data["detail"]["error_type"] == "llm_default_profile_not_configured"

    @pytest.mark.asyncio
    async def test_deepseek_chat_with_key_attempts_real(self):
        """DeepSeek+Mock 有 Key → M1.5 Chat 可用，尝试调用真实 API（会因假 Key 失败）"""
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
                # M1.5: Chat 已启用，假 Key 会导致鉴权/连接错误（非 503 mode guard）
                assert response.status_code in (502, 500)

    @pytest.mark.asyncio
    async def test_deepseek_chat_no_fallback_to_mock(self):
        """DeepSeek Chat 不回退 Mock LLM — 即使 API 调用失败也不返回 Mock 结果"""
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
                # M1.5: 不返回 Mock 模式的 200，必须是错误状态
                assert response.status_code != 200
                # 必须不是 503 mode guard
                data = response.json()
                if isinstance(data.get("detail"), dict):
                    assert data["detail"].get("error_type") != "deepseek_pipeline_not_ready"


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
                "report_template_key": "sales_report",
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
                "report_template_key": "sales_report",
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
            "report_template_key": "sales_report",
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
    async def test_report_keywords_never_select_an_implicit_template(self, client):
        """报表关键词不能隐式选择默认模板。"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成销售周报",
            "conversation_id": "conv-m10-template-api",
            "request_id": "req-m10-template-api",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "report_generation"
        assert data["terminal_state"] == "clarification_required"
        assert data["report"] is None
        assert data["tool_sequence"] == []

    @pytest.mark.asyncio
    async def test_unknown_explicit_template_is_rejected(self, client):
        """未知显式模板不能由 Mock fixture 改写为其他模板。"""
        response = await client.post("/api/v1/chat", json={
            "message": "生成周报",
            "conversation_id": "conv-m10-explicit-template",
            "request_id": "req-m10-explicit-template",
            "report_template_key": "satisfaction_survey",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_state"] == "clarification_required"
        assert data["report"] is None
        assert data["tool_sequence"] == []

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
        from backend.app.config.settings import Settings
        assert data["version"] == Settings().version

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


# ══════════════════════════════════════════════════════════════════
# M2.4 DeepSeek Provider Fake + Local Adapter Fake 正式组合
# ══════════════════════════════════════════════════════════════════


class _M24ScriptedDeepSeekProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        self.calls.append(request)
        if request.task == LLMTask.INTENT_RECOGNITION:
            structured = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.99,
                normalized_question="总销售额是多少？",
                detected_measures=["Total Sales"],
            )
        elif request.task == LLMTask.QUERY_PLAN:
            structured = QueryPlan(
                normalized_question="总销售额是多少？",
                semantic_model_key="local_desktop_model",
                measures=["Total Sales"],
            )
        elif request.task == LLMTask.DAX:
            structured = DAXRequest(
                semantic_model_key="local_desktop_model",
                dax='EVALUATE ROW("Total Sales", [Total Sales])',
            )
        elif request.task == LLMTask.ANSWER:
            structured = AnswerSpec(
                answer="总销售额为 100。",
                summary="总销售额为 100。",
                metrics={"Total Sales": 100},
                evidence={
                    "result_id": "qr-m24-real",
                    "semantic_model_key": "local_desktop_model",
                    "row_count": 1,
                    "source_mode": "real",
                    "metric_provenance": {
                        "Total Sales": {
                            "source_field": "[Total Sales]",
                            "aggregation": "direct",
                        }
                    },
                },
                semantic_model_key="local_desktop_model",
                source_mode="real",
            )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _UnsupportedRoutingProvider(_M24ScriptedDeepSeekProvider):
    def __init__(self) -> None:
        super().__init__()
        self.active = "normal"

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        self.calls.append(request)
        if request.task == LLMTask.INTENT_RECOGNITION:
            messages = {
                "normal": "总销售额是多少？",
                "unknown": "客户幸福指数是多少？",
                "comparison": "销售额同比去年如何？",
                "filter": "销售额中类别包含 Furniture",
                "non_data": "帮我写一首诗",
            }
            structured = IntentSpec(
                intent=IntentType.UNSUPPORTED,
                confidence=0.7,
                normalized_question=messages[self.active],
                unsupported_reason="scripted false-or-true unsupported",
            )
        elif request.task == LLMTask.QUERY_PLAN:
            if self.active == "unknown":
                structured = QueryPlan(
                    normalized_question="客户幸福指数是多少？",
                    semantic_model_key="local_desktop_model",
                )
            elif self.active == "filter":
                structured = QueryPlan(
                    normalized_question="销售额中类别包含 Furniture",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                    filters=[StructuredFilter(
                        field="Category",
                        operator="contains",
                        value="Furniture",
                    )],
                )
            else:
                structured = QueryPlan(
                    normalized_question=(
                        "销售额同比去年如何？"
                        if self.active == "comparison"
                        else "总销售额是多少？"
                    ),
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _M24FakeLocalPowerBIAdapter(PowerBIAdapter):
    def __init__(self, **_: object) -> None:
        self.schema_calls = 0
        self.dax_calls = 0

    @property
    def provider_name(self) -> str:
        return "local_mcp"

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        raise AssertionError("configuration health must not probe Local MCP")

    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        self.schema_calls += 1
        assert semantic_model_key == "local_desktop_model"
        return SemanticModelSchema(
            name="Local Desktop Model",
            key="local_desktop_model",
            tables=[TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Category", data_type="string"),
                    ColumnSchema(name="Product", data_type="string"),
                    ColumnSchema(name="OrderDate", data_type="datetime"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                ],
            )],
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        return QueryResult(
            result_id="qr-m24-real",
            semantic_model_key=request.semantic_model_key,
            columns=["[Total Sales]"],
            rows=[[100]],
            row_count=1,
            source_mode="real",
            request_id=request.request_id,
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        assert isinstance(raw, QueryResult)
        return raw

    async def normalize_error(self, raw: object) -> PowerBIError:
        if isinstance(raw, PowerBIError):
            return raw
        return PowerBIError(type="unknown", message="normalized")


class _M533MultiTurnProvider(_M24ScriptedDeepSeekProvider):
    def __init__(self) -> None:
        super().__init__()
        self.active = "current"
        self.model_key = "local_desktop_model"
        self.fail_intent_once = False
        self.fail_query_plan_once = False

    async def generate(self, request, output_type):
        self.calls.append(request)
        if request.task == LLMTask.SEMANTIC_SELECTION:
            from backend.app.query_plan.grounding import CandidateSelection

            assert self.active == "m55_unknown_member"
            return LLMResponse(content="{}", structured=CandidateSelection(outcome="UNRESOLVED"))
        if request.task == LLMTask.INTENT_RECOGNITION and self.fail_intent_once:
            self.fail_intent_once = False
            raise RuntimeError("injected intent outage")
        if request.task == LLMTask.QUERY_PLAN and self.fail_query_plan_once:
            self.fail_query_plan_once = False
            raise RuntimeError("injected query-plan outage")
        messages = {
            "current": "本月销售额是多少？",
            "absolute": "2025年5月销售额多少？",
            "last_may": "去年五月",
            "previous_month": "上个月",
            "recent_half": "最近半年",
            "top_region": "销售额最高的前3个区域是什么？",
            "south": "那只看华南呢？",
            "last_year": "改成去年。",
            "fresh_quantity": "总销量是多少？",
            "failed": "总销售额是多少？",
            "model_switch": "总销售额是多少？",
            "m55_south": "那南区呢",
            "m55_last_year": "换成去年",
            "m55_top_product": "前三个产品呢",
            "m55_unknown_member": "火星区销售额",
        }
        if request.task == LLMTask.INTENT_RECOGNITION:
            values = {
                "intent": IntentType.DATA_QUESTION,
                "confidence": 0.99,
                "normalized_question": messages[self.active],
            }
            if self.active in {
                "current", "absolute", "top_region", "failed", "model_switch",
                "m55_unknown_member",
            }:
                values["detected_measures"] = ["销售额"]
                values["turn_relation"] = TurnRelation.FRESH_QUESTION
            elif self.active == "fresh_quantity":
                values["detected_measures"] = ["销量"]
                values["turn_relation"] = TurnRelation.FRESH_QUESTION
            elif self.active in {"m55_south", "m55_top_product"}:
                values["turn_relation"] = TurnRelation.FOLLOW_UP
            else:
                values["turn_relation"] = (
                    TurnRelation.FOLLOW_UP
                    if self.active == "south" else TurnRelation.REPLACE
                )
            if self.active == "absolute":
                values["detected_time_range"] = "2025年5月"
                values["time_intent"] = TimeIntentDraft(
                    kind=TimeIntentKind.ABSOLUTE_MONTH,
                    expression="2025年5月",
                    year=2025,
                    month=5,
                )
            elif self.active in {
                "current", "last_may", "previous_month", "recent_half", "last_year"
            }:
                values["detected_time_range"] = messages[self.active]
            if self.active == "top_region":
                values["detected_dimensions"] = ["区域"]
            if self.active in {"south", "m55_south", "m55_unknown_member"}:
                values["detected_filters"] = [
                    {
                        "field": "区域",
                        "operator": "eq",
                        "value": (
                            "华南" if self.active == "south"
                            else "南区" if self.active == "m55_south"
                            else "火星区"
                        ),
                    }
                ]
            if self.active == "m55_top_product":
                values["detected_dimensions"] = ["产品"]
            structured = IntentSpec(**values)
        elif request.task == LLMTask.QUERY_PLAN:
            values = {
                "normalized_question": messages[self.active],
                "semantic_model_key": self.model_key,
            }
            if self.active in {
                "current", "absolute", "last_may", "previous_month",
                "recent_half", "top_region", "south", "last_year", "failed",
                "model_switch", "m55_south", "m55_last_year",
                "m55_top_product", "m55_unknown_member",
            }:
                values["measures"] = ["Total Sales"]
            else:
                values["measures"] = ["Total Quantity"]
            if self.active in {"top_region", "south", "last_year"}:
                values["dimensions"] = ["Region"]
                values["sort"] = "desc"
                values["top_n"] = 3
            if self.active == "m55_top_product":
                values["dimensions"] = ["Product"]
                values["sort"] = "desc"
                values["top_n"] = 3
            if self.active in {"south", "m55_south", "m55_unknown_member"}:
                values["filters"] = [
                    StructuredFilter(
                        field="Region",
                        value=(
                            "华南" if self.active == "south"
                            else "南区" if self.active == "m55_south"
                            else "火星区"
                        ),
                    )
                ]
            if self.active in {
                "current", "absolute", "last_may", "previous_month", "recent_half", "last_year"
            }:
                values["time_range"] = messages[self.active]
            structured = QueryPlan(**values)
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _M533MultiTurnAdapter(_M24FakeLocalPowerBIAdapter):
    fail_next = False

    async def get_semantic_model_schema(self, semantic_model_key: str):
        self.schema_calls += 1
        assert semantic_model_key in {
            "local_desktop_model", "local_desktop_model_alt"
        }
        return SemanticModelSchema(
            name="Local Desktop Model",
            key=semantic_model_key,
            tables=[TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Category", data_type="string"),
                    ColumnSchema(name="Product", data_type="string"),
                    ColumnSchema(name="OrderDate", data_type="datetime"),
                    ColumnSchema(name="Region", data_type="string"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                ],
            )],
        )

    async def get_column_members(self, request: ColumnMembersRequest):
        return ColumnMembersResult(
            semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,
            field_name=request.field_name,
            values=["华南", "华东", "华北"],
            source_mode="real",
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        if self.fail_next:
            self.fail_next = False
            return QueryResult(
                semantic_model_key=request.semantic_model_key,
                source_mode="real",
                request_id=request.request_id,
                error=PowerBIError(type="injected_failure", message="controlled"),
            )
        measure = (
            "Total Quantity" if "[Total Quantity]" in request.dax else "Total Sales"
        )
        if "SUMMARIZECOLUMNS(\n    'Sales'[Region]" in request.dax:
            return QueryResult(
                result_id=f"qr-{request.request_id}",
                semantic_model_key=request.semantic_model_key,
                columns=["Sales[Region]", f"[{measure}]"],
                rows=[["华南", 100], ["华东", 80], ["华北", 60]],
                row_count=3,
                source_mode="real",
                request_id=request.request_id,
            )
        if "SUMMARIZECOLUMNS(\n    'Sales'[Product]" in request.dax:
            return QueryResult(
                result_id=f"qr-{request.request_id}",
                semantic_model_key=request.semantic_model_key,
                columns=["Sales[Product]", f"[{measure}]"],
                rows=[["A", 100], ["B", 80], ["C", 60]],
                row_count=3,
                source_mode="real",
                request_id=request.request_id,
            )
        return QueryResult(
            result_id=f"qr-{request.request_id}",
            semantic_model_key=request.semantic_model_key,
            columns=[f"[{measure}]"],
            rows=[[100]],
            row_count=1,
            source_mode="real",
            request_id=request.request_id,
        )


class _M571RichTemporalAdapter(_M533MultiTurnAdapter):
    async def get_semantic_model_schema(self, semantic_model_key: str):
        self.schema_calls += 1
        assert semantic_model_key == "local_desktop_model"
        return SemanticModelSchema(
            name="Rich Local Model",
            key=semantic_model_key,
            tables=[
                TableSchema(
                    name="Sales",
                    columns=[
                        ColumnSchema(name="Category", data_type="string"),
                        ColumnSchema(name="Product", data_type="string"),
                        ColumnSchema(name="OrderDate", data_type="datetime"),
                        ColumnSchema(name="Region", data_type="string"),
                    ],
                    measures=[
                        MeasureSchema(name="Total Sales", data_type="decimal"),
                        MeasureSchema(name="Total Quantity", data_type="int64"),
                    ],
                ),
                TableSchema(
                    name="Date",
                    columns=[
                        ColumnSchema(name="Date", data_type="datetime"),
                        ColumnSchema(name="YearMonth", data_type="datetime"),
                    ],
                ),
            ],
            relationships=[RelationshipSchema(
                from_table="Sales",
                from_column="OrderDate",
                to_table="Date",
                to_column="Date",
                is_active=True,
            )],
        )


class _M571AmbiguousTemporalAdapter(_M533MultiTurnAdapter):
    async def get_semantic_model_schema(self, semantic_model_key: str):
        self.schema_calls += 1
        assert semantic_model_key == "local_desktop_model"
        return SemanticModelSchema(
            name="Ambiguous Local Model",
            key=semantic_model_key,
            tables=[TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Category", data_type="string"),
                    ColumnSchema(name="Product", data_type="string"),
                    ColumnSchema(name="OrderDate", data_type="datetime"),
                    ColumnSchema(name="ShipDate", data_type="datetime"),
                    ColumnSchema(name="Region", data_type="string"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                ],
            )],
        )


class _M56MonthlyTrendProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(self, request, output_type):
        if request.task == LLMTask.INTENT_RECOGNITION:
            structured = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.99,
                normalized_question="每个月销售额趋势",
                detected_measures=["销售额"],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif request.task == LLMTask.QUERY_PLAN:
            structured = QueryPlan(
                normalized_question="每个月销售额趋势",
                semantic_model_key="local_desktop_model",
                measures=["Total Sales"],
            )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _M56MonthlyTrendAdapter(_M24FakeLocalPowerBIAdapter):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.last_dax = ""

    async def get_semantic_model_schema(
        self, semantic_model_key: str
    ) -> SemanticModelSchema:
        self.schema_calls += 1
        assert semantic_model_key == "local_desktop_model"
        return SemanticModelSchema(
            name="Local Desktop Model",
            key=semantic_model_key,
            tables=[
                TableSchema(
                    name="Sales",
                    columns=[
                        ColumnSchema(name="Category", data_type="string"),
                        ColumnSchema(name="Product", data_type="string"),
                        ColumnSchema(name="OrderDate", data_type="datetime"),
                    ],
                    measures=[
                        MeasureSchema(name="Total Sales", data_type="decimal"),
                        MeasureSchema(name="Total Quantity", data_type="int64"),
                    ],
                ),
                TableSchema(
                    name="Date",
                    columns=[
                        ColumnSchema(name="Date", data_type="datetime"),
                        ColumnSchema(name="YearMonth", data_type="datetime"),
                    ],
                ),
            ],
            relationships=[
                RelationshipSchema(
                    from_table="Sales",
                    from_column="OrderDate",
                    to_table="Date",
                    to_column="Date",
                )
            ],
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        self.last_dax = request.dax
        assert "'Date'[YearMonth]" in request.dax
        return QueryResult(
            result_id=f"qr-{request.request_id}",
            semantic_model_key=request.semantic_model_key,
            columns=["Date[YearMonth]", "[Total Sales]"],
            rows=[
                ["2025-01-01T00:00:00", 100.0],
                ["2025-02-01T00:00:00", 140.0],
                ["2025-03-01T00:00:00", 90.0],
                ["2025-04-01T00:00:00", 110.0],
            ],
            row_count=4,
            source_mode="real",
            request_id=request.request_id,
        )


class _M24PreviewMissingRowsAdapter(_M24FakeLocalPowerBIAdapter):
    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        return QueryResult(
            semantic_model_key=request.semantic_model_key,
            source_mode="real",
            request_id=request.request_id,
            error=PowerBIError(
                type="preview_row_data_missing",
                message="Power BI Preview response did not include row data",
            ),
        )


class _M24ConnectionFailureAdapter(_M24FakeLocalPowerBIAdapter):
    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        self.schema_calls += 1
        raise PowerBIAdapterError(
            "Local MCP connection failed",
            provider="local_mcp",
            retryable=False,
            error_type="connection_error",
        )


class _M25BusinessGoldenProvider(LLMProvider):
    """Offline scripted provider for generalized Business Golden contracts."""

    def __init__(
        self,
        *,
        question: str,
        measure: str,
        dimension: str,
        sort: str | None,
        top_n: int | None,
    ) -> None:
        self.question = question
        self.measure = measure
        self.dimension = dimension
        self.sort = sort
        self.top_n = top_n
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        self.calls.append(request)
        if request.task == LLMTask.INTENT_RECOGNITION:
            structured = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.99,
                normalized_question=self.question,
                detected_measures=[self.measure],
                detected_dimensions=[self.dimension],
            )
        elif request.task == LLMTask.QUERY_PLAN:
            structured = QueryPlan(
                normalized_question=self.question,
                semantic_model_key="local_desktop_model",
                measures=[self.measure],
                dimensions=[self.dimension],
                sort=self.sort,
                top_n=self.top_n,
            )
        elif request.task == LLMTask.DAX:
            grouped = (
                f"SUMMARIZECOLUMNS('Sales'[{self.dimension}], "
                f"\"{self.measure}\", [{self.measure}])"
            )
            if self.top_n is None:
                dax = f"EVALUATE {grouped}"
            else:
                dax = (
                    f"EVALUATE TOPN({self.top_n}, {grouped}, "
                    f"[{self.measure}], DESC) ORDER BY [{self.measure}] DESC"
                )
            structured = DAXRequest(
                semantic_model_key="local_desktop_model",
                dax=dax,
            )
        elif request.task == LLMTask.ANSWER:
            structured = AnswerSpec(
                answer="查询完成。",
                summary="查询完成。",
                metrics={self.measure: 30},
                evidence={
                    "result_id": "qr-m25-business-golden",
                    "semantic_model_key": "local_desktop_model",
                    "row_count": 3,
                    "source_mode": "real",
                    "metric_provenance": {
                        self.measure: {
                            "source_field": f"[{self.measure}]",
                            "aggregation": "direct",
                        }
                    },
                },
                semantic_model_key="local_desktop_model",
                source_mode="real",
            )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _M25BusinessGoldenAdapter(_M24FakeLocalPowerBIAdapter):
    async def get_semantic_model_schema(
        self, semantic_model_key: str
    ) -> SemanticModelSchema:
        self.schema_calls += 1
        assert semantic_model_key == "local_desktop_model"
        return SemanticModelSchema(
            name="Local Desktop Model",
            key="local_desktop_model",
            tables=[TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Category", data_type="string"),
                    ColumnSchema(name="Product", data_type="string"),
                    ColumnSchema(name="OrderDate", data_type="datetime"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                ],
            )],
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        dimension = "Product" if "[Product]" in request.dax else "Category"
        measure = (
            "Total Quantity"
            if "[Total Quantity]" in request.dax
            else "Total Sales"
        )
        return QueryResult(
            result_id="qr-m25-business-golden",
            semantic_model_key=request.semantic_model_key,
            columns=[f"Sales[{dimension}]", f"[{measure}]"],
            rows=[["A", 30], ["B", 20], ["C", 10]],
            row_count=3,
            source_mode="real",
            request_id=request.request_id,
        )


def _patch_fake_runtime_glossary(monkeypatch):
    """Bind fake Local schemas to an explicit test-only glossary fingerprint."""
    import backend.app.application.deepseek_turn_service as turn_service_module

    aliases = {
        "Total Sales": ["销售额", "总销售额", "销售金额"],
        "Total Quantity": ["销量", "总数量", "销售数量", "件数", "多少件"],
        "Total Orders": ["订单数", "总订单数"],
        "Average Order Value": ["平均订单金额", "平均订单额"],
        "Category": ["类别", "品类"],
        "Product": ["产品", "商品"],
        "Region": ["区域", "地区"],
        "OrderDate": ["订单日期", "销售日期"],
        "Date": ["日期"],
        "YearMonth": ["月份", "月度"],
    }

    class _TestCatalogBuilder:
        def build(self, schema, *, glossary_scope_key=None):
            glossary = {
                "version": 1,
                "semantic_model_key": schema.key,
                "schema_fingerprint": compute_schema_fingerprint(schema),
                "measures": {},
                "fields": {},
            }
            for table in schema.tables:
                for measure in table.measures:
                    glossary["measures"][measure.name] = {
                        "table_name": table.name,
                        "object_type": "measure",
                        "aliases": aliases.get(measure.name, []),
                    }
                for column in table.columns:
                    metadata = {
                        "table_name": table.name,
                        "object_type": "field",
                        "aliases": aliases.get(column.name, []),
                    }
                    if (
                        table.name == "Date"
                        and column.name == "Date"
                        and any(
                            candidate.name == "YearMonth"
                            for candidate in table.columns
                        )
                    ):
                        metadata["temporal_role"] = "default"
                    if (
                        table.name == "Date"
                        and column.name == "YearMonth"
                        and any(
                            candidate.name == "Date"
                            for candidate in table.columns
                        )
                    ):
                        metadata["temporal_grouping"] = {
                            "grain": "month",
                            "date_field": "Date",
                            "date_table_name": "Date",
                        }
                    if column.name == "Region":
                        metadata["member_aliases"] = {
                            "华南": "华南",
                            "华南区": "华南",
                            "南区": "华南",
                        }
                        metadata["member_suffixes"] = ["区"]
                    if column.name == "Product":
                        metadata["member_aliases"] = {
                            "手机": "手机",
                            "笔记本": "笔记本",
                            "电脑": "电脑",
                        }
                    glossary["fields"][column.name] = metadata
            return SemanticCatalogBuilder().build_from_data(schema, glossary)

    monkeypatch.setattr(
        turn_service_module, "SemanticCatalogBuilder", _TestCatalogBuilder
    )


def _patch_m25_business_golden_composition(
    monkeypatch,
    provider: _M25BusinessGoldenProvider,
):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(
        main_module, "LocalMCPPowerBIAdapter", _M25BusinessGoldenAdapter
    )
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings)


def _patch_m24_local_composition(monkeypatch, adapter_type):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _M24ScriptedDeepSeekProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(main_module, "LocalMCPPowerBIAdapter", adapter_type)
    fake_key = "test-key-not-real"
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key=fake_key,
    )
    return main_module.create_app(settings=settings), provider


def _patch_unsupported_routing_composition(monkeypatch):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _UnsupportedRoutingProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(
        main_module, "LocalMCPPowerBIAdapter", _M24FakeLocalPowerBIAdapter
    )
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings), provider


def _patch_m533_multi_turn_composition(
    monkeypatch,
    adapter_type=_M533MultiTurnAdapter,
):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _M533MultiTurnProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(
        main_module, "LocalMCPPowerBIAdapter", adapter_type
    )
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings), provider


def _patch_m56_monthly_trend_composition(monkeypatch):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _M56MonthlyTrendProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    monkeypatch.setattr(
        main_module, "LocalMCPPowerBIAdapter", _M56MonthlyTrendAdapter
    )
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings)


class _PendingClarificationProvider(LLMProvider):
    """Script language stages while leaving semantic authority to Grounding."""

    def __init__(self) -> None:
        self.active = "e1"
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(
        self, request: LLMRequest, output_type: type[BaseModel]
    ) -> LLMResponse:
        self.calls.append(request)
        if request.task == LLMTask.INTENT_RECOGNITION:
            if self.active == "e1":
                structured = IntentSpec(
                    intent=IntentType.CLARIFICATION,
                    confidence=0.8,
                    normalized_question="哪个表现最好？",
                    needs_clarification=True,
                    clarification_question="请明确指标和维度。",
                )
            elif self.active == "e2":
                structured = IntentSpec(
                    intent=IntentType.DATA_QUESTION,
                    confidence=0.99,
                    normalized_question="按销售额",
                    detected_measures=["Total Sales"],
                )
            elif self.active == "e3":
                structured = IntentSpec(
                    intent=IntentType.DATA_QUESTION,
                    confidence=0.99,
                    normalized_question="按产品",
                    detected_measures=["Total Sales"],
                    detected_dimensions=["Product"],
                )
            elif self.active == "override":
                structured = IntentSpec(
                    intent=IntentType.DATA_QUESTION,
                    confidence=0.99,
                    normalized_question="改成按产品看销量",
                    detected_measures=["Total Quantity"],
                    detected_dimensions=["Product"],
                )
            elif self.active == "ambiguous":
                structured = IntentSpec(
                    intent=IntentType.DATA_QUESTION,
                    confidence=0.99,
                    normalized_question="按产品还是类别",
                    detected_measures=["Total Sales"],
                    detected_dimensions=["Product", "Category"],
                )
            elif self.active in {"abandon", "unrelated"}:
                structured = IntentSpec(
                    intent=IntentType.DATA_QUESTION,
                    confidence=0.99,
                    normalized_question=(
                        "重新开始，总销售额"
                        if self.active == "abandon"
                        else "总销售额是多少？"
                    ),
                    detected_measures=["Total Sales"],
                )
            else:
                raise AssertionError(f"unknown scripted turn: {self.active}")
        elif request.task == LLMTask.QUERY_PLAN:
            plans = {
                "e1": QueryPlan(
                    normalized_question="哪个表现最好？",
                    semantic_model_key="local_desktop_model",
                    sort="desc",
                    top_n=1,
                ),
                "e2": QueryPlan(
                    normalized_question="按销售额",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                ),
                # The repeated measure is only a weak draft echo.  The current
                # utterance explicitly contributes Product; pending owns Sales.
                "e3": QueryPlan(
                    normalized_question="按产品",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                    dimensions=["Product"],
                ),
                "override": QueryPlan(
                    normalized_question="改成按产品看销量",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Quantity"],
                    dimensions=["Product"],
                ),
                "ambiguous": QueryPlan(
                    normalized_question="按产品还是类别",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                    dimensions=["Product", "Category"],
                ),
                "abandon": QueryPlan(
                    normalized_question="重新开始，总销售额",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                ),
                "unrelated": QueryPlan(
                    normalized_question="总销售额是多少？",
                    semantic_model_key="local_desktop_model",
                    measures=["Total Sales"],
                ),
            }
            structured = plans[self.active]
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _PendingClarificationAdapter(_M24FakeLocalPowerBIAdapter):
    fail_next = False

    async def get_column_members(
        self, request: ColumnMembersRequest
    ) -> ColumnMembersResult:
        return ColumnMembersResult(
            semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,
            field_name=request.field_name,
            values=["A", "B"],
            source_mode="real",
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        if self.fail_next:
            self.fail_next = False
            return QueryResult(
                semantic_model_key=request.semantic_model_key,
                source_mode="real",
                request_id=request.request_id,
                error=PowerBIError(
                    type="controlled_failure",
                    message="focused pending clarification failure",
                ),
            )
        measure = (
            "Total Quantity" if "[Total Quantity]" in request.dax else "Total Sales"
        )
        if "'Sales'[Product]" in request.dax:
            return QueryResult(
                result_id="qr-pending-grouped",
                semantic_model_key=request.semantic_model_key,
                columns=["Sales[Product]", f"[{measure}]"],
                rows=[["A", 100]],
                row_count=1,
                source_mode="real",
                request_id=request.request_id,
            )
        return QueryResult(
            result_id="qr-pending-scalar",
            semantic_model_key=request.semantic_model_key,
            columns=[f"[{measure}]"],
            rows=[[100]],
            row_count=1,
            source_mode="real",
            request_id=request.request_id,
        )


def _patch_pending_clarification_composition(monkeypatch):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _PendingClarificationProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(
        main_module, "LocalMCPPowerBIAdapter", _PendingClarificationAdapter
    )
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings), provider


class TestPendingClarificationProductionPath:
    @staticmethod
    async def _post(client, conversation_id: str, request_id: str, message: str):
        return await client.post(
            "/api/v1/chat",
            json={
                "message": message,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "semantic_model_key": "local_desktop_model",
            },
        )

    @pytest.mark.asyncio
    async def test_partial_chain_executes_only_after_all_slots(self, monkeypatch):
        app, provider = _patch_pending_clarification_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "pending-chain-complete"
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                first = await self._post(client, conversation_id, "pending-e1", "哪个表现最好？")
                assert first.status_code == 200
                first_body = first.json()
                assert first_body["terminal_state"] == "clarification_required"
                assert first_body["memory_commit"] is False
                pending = await service.pipeline.get_pending_clarification(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert pending is not None
                chain_id = pending.chain_id
                assert pending.missing_slots == ["measure", "dimension"]
                assert await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                ) is None

                provider.active = "e2"
                second = await self._post(client, conversation_id, "pending-e2", "按销售额")
                assert second.status_code == 200
                assert second.json()["terminal_state"] == "clarification_required"
                pending = await service.pipeline.get_pending_clarification(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert pending is not None
                assert pending.chain_id == chain_id
                assert pending.measures == ["Total Sales"]
                assert pending.missing_slots == ["dimension"]
                assert await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                ) is None

                provider.active = "e3"
                third = await self._post(client, conversation_id, "pending-e3", "按产品")
                assert third.status_code == 200
                body = third.json()
                assert body["terminal_state"] == "completed"
                assert body["memory_commit"] is True
                assert body["execution_audit"]["canonical_query_plan"]["measures"] == ["Total Sales"]
                assert body["execution_audit"]["canonical_query_plan"]["dimensions"] == ["Product"]
                assert body["execution_audit"]["canonical_query_plan"]["top_n"] == 1
                assert body["execution_audit"]["llm_dax_call_count"] == 0
                assert await service.pipeline.get_pending_clarification(
                    conversation_id, RuntimeDataMode.REAL
                ) is None
                committed = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert committed is not None
                assert committed.request_id == "pending-e3"
                assert committed.memory_version == 1


    @pytest.mark.asyncio
    async def test_time_replace_fresh_follow_up_and_failed_turn_boundaries(
        self, monkeypatch
    ):
        app, provider = _patch_m533_multi_turn_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "m533-multi-turn"

        async def post(
            client,
            active,
            message,
            semantic_model_key="local_desktop_model",
        ):
            provider.active = active
            provider.model_key = semantic_model_key
            response = await client.post("/api/v1/chat", json={
                "message": message,
                "conversation_id": conversation_id,
                "request_id": f"m533-{active}",
                "semantic_model_key": semantic_model_key,
            })
            assert response.status_code == 200, response.text
            return response.json()

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for active, message, start, end in (
                    ("current", "本月销售额是多少？", "2026-08-01", "2026-08-31"),
                    ("absolute", "2025年5月销售额多少？", "2025-05-01", "2025-05-31"),
                    ("last_may", "去年五月", "2025-05-01", "2025-05-31"),
                    ("previous_month", "上个月", "2026-07-01", "2026-07-31"),
                    ("recent_half", "最近半年", "2026-03-01", "2026-08-31"),
                ):
                    body = await post(client, active, message)
                    assert body["terminal_state"] == "completed", body
                    committed = await service.pipeline.get_latest_committed_memory(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    assert committed is not None and committed.time_range is not None
                    assert committed.time_range.start_date.isoformat() == start
                    assert committed.time_range.end_date.isoformat() == end

                top = await post(
                    client,
                    "top_region",
                    "销售额最高的前3个区域是什么？",
                )
                assert top["terminal_state"] == "completed", top
                plan = top["execution_audit"]["canonical_query_plan"]
                assert plan["dimensions"] == ["Region"]
                assert plan["top_n"] == 3 and plan["sort"] == "desc"
                assert plan["time_range"] is None
                assert plan["filters"] == []

                follow = await post(client, "south", "那只看华南呢？")
                follow_plan = follow["execution_audit"]["canonical_query_plan"]
                assert follow_plan["dimensions"] == ["Region"]
                assert follow_plan["top_n"] == 3
                assert follow_plan["filters"][0]["value"] == "华南"

                replaced = await post(client, "last_year", "改成去年。")
                replace_plan = replaced["execution_audit"]["canonical_query_plan"]
                assert replace_plan["time_range"]["start_date"] == "2025-01-01"
                assert replace_plan["filters"][0]["value"] == "华南"

                fresh = await post(client, "fresh_quantity", "总销量是多少？")
                fresh_plan = fresh["execution_audit"]["canonical_query_plan"]
                assert fresh_plan["measures"] == ["Total Quantity"]
                assert fresh_plan["dimensions"] == []
                assert fresh_plan["filters"] == []
                assert fresh_plan["time_range"] is None
                assert fresh_plan["sort"] is None and fresh_plan["top_n"] is None
                committed_before_failure = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )

                service.powerbi.fail_next = True
                failed = await post(client, "failed", "总销售额是多少？")
                assert failed["terminal_state"] == "tool_failed"
                committed_after_failure = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert committed_before_failure is not None
                assert committed_after_failure is not None
                assert committed_after_failure.request_id == committed_before_failure.request_id
                assert (
                    committed_after_failure.memory_version
                    == committed_before_failure.memory_version
                )

                switched = await post(
                    client,
                    "model_switch",
                    "总销售额是多少？",
                    "local_desktop_model_alt",
                )
                switched_plan = switched["execution_audit"]["canonical_query_plan"]
                assert switched["terminal_state"] == "completed"
                assert switched_plan["semantic_model_key"] == "local_desktop_model_alt"
                assert switched_plan["dimensions"] == []
                assert switched_plan["filters"] == []
                assert switched_plan["time_range"] is None
                switched_memory = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert switched_memory is not None
                assert switched_memory.semantic_model_key == "local_desktop_model_alt"
    @pytest.mark.asyncio
    async def test_current_explicit_slot_overrides_pending(self, monkeypatch):
        app, provider = _patch_pending_clarification_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "pending-override"
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await self._post(client, conversation_id, "override-e1", "哪个表现最好？")
                provider.active = "e2"
                await self._post(client, conversation_id, "override-e2", "按销售额")
                provider.active = "override"
                result = await self._post(
                    client, conversation_id, "override-e3", "改成按产品看销量"
                )
                assert result.json()["terminal_state"] == "completed"
                committed = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert committed is not None
                assert committed.measures == ["Total Quantity"]
                assert committed.dimensions == ["Product"]

    @pytest.mark.asyncio
    async def test_ambiguous_or_failed_completion_never_commits(self, monkeypatch):
        app, provider = _patch_pending_clarification_composition(monkeypatch)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                ambiguous_id = "pending-ambiguous"
                await self._post(client, ambiguous_id, "ambiguous-e1", "哪个表现最好？")
                provider.active = "e2"
                await self._post(client, ambiguous_id, "ambiguous-e2", "按销售额")
                provider.active = "ambiguous"
                ambiguous = await self._post(
                    client, ambiguous_id, "ambiguous-e3", "按产品还是类别"
                )
                assert ambiguous.json()["terminal_state"] == "clarification_required", ambiguous.json()
                assert await service.pipeline.get_latest_committed_memory(
                    ambiguous_id, RuntimeDataMode.REAL
                ) is None

                failed_id = "pending-failed"
                provider.active = "e1"
                await self._post(client, failed_id, "failed-e1", "哪个表现最好？")
                provider.active = "e2"
                await self._post(client, failed_id, "failed-e2", "按销售额")
                provider.active = "e3"
                service.powerbi.fail_next = True
                failed = await self._post(client, failed_id, "failed-e3", "按产品")
                assert failed.json()["terminal_state"] == "tool_failed"
                assert await service.pipeline.get_latest_committed_memory(
                    failed_id, RuntimeDataMode.REAL
                ) is None

    @pytest.mark.asyncio
    async def test_explicit_abandonment_clears_old_pending(self, monkeypatch):
        app, provider = _patch_pending_clarification_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "pending-abandon"
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await self._post(client, conversation_id, "abandon-e1", "哪个表现最好？")
                provider.active = "abandon"
                result = await self._post(
                    client, conversation_id, "abandon-e2", "重新开始，总销售额"
                )
                assert result.json()["terminal_state"] == "completed"
                assert await service.pipeline.get_pending_clarification(
                    conversation_id, RuntimeDataMode.REAL
                ) is None
                committed = await service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )
                assert committed is not None
                assert committed.measures == ["Total Sales"]
                assert committed.dimensions == []

    @pytest.mark.asyncio
    async def test_new_standalone_query_does_not_leak_old_ranking(self, monkeypatch):
        app, provider = _patch_pending_clarification_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "pending-unrelated"
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await self._post(client, conversation_id, "unrelated-e1", "哪个表现最好？")
                provider.active = "unrelated"
                result = await self._post(
                    client, conversation_id, "unrelated-e2", "总销售额是多少？"
                )
                body = result.json()
                assert body["terminal_state"] == "completed"
                plan = body["execution_audit"]["canonical_query_plan"]
                assert plan["measures"] == ["Total Sales"]
                assert plan["dimensions"] == []
                assert plan["sort"] is None
                assert plan["top_n"] is None
                assert await service.pipeline.get_pending_clarification(
                    conversation_id, RuntimeDataMode.REAL
                ) is None


class TestM24DeepSeekLocalChat:
    @pytest.mark.asyncio
    async def test_m571_rich_model_absolute_month_uses_bound_date_role(
        self, monkeypatch
    ):
        app, provider = _patch_m533_multi_turn_composition(
            monkeypatch, _M571RichTemporalAdapter
        )
        provider.active = "absolute"
        conversation_id = "m571-rich-absolute-month"

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                dax_calls = service.powerbi.dax_calls
                response = await client.post("/api/v1/chat", json={
                    "message": "2025年5月销售额",
                    "conversation_id": conversation_id,
                    "request_id": "m571-rich-absolute-month-request",
                    "semantic_model_key": "local_desktop_model",
                })

            body = response.json()
            assert response.status_code == 200, body
            assert body["terminal_state"] == "completed", body
            assert body["memory_commit"] is True
            audit = body["execution_audit"]
            assert audit["dax_executed"] is True
            plan = audit["canonical_query_plan"]
            assert plan["time_range"]["date_field"] == "Date"
            assert plan["time_range"]["start_date"] == "2025-05-01"
            assert plan["time_range"]["end_date"] == "2025-05-31"
            assert plan["dimension_tables"]["Date"] == "Date"
            assert service.powerbi.dax_calls == dax_calls + 1
            committed = await service.pipeline.get_latest_committed_memory(
                conversation_id, RuntimeDataMode.REAL
            )
            assert committed is not None
            assert committed.time_range is not None
            assert committed.time_range.date_field == "Date"

    @pytest.mark.asyncio
    async def test_m571_unproven_date_role_fails_closed_before_dax(
        self, monkeypatch
    ):
        app, provider = _patch_m533_multi_turn_composition(
            monkeypatch, _M571AmbiguousTemporalAdapter
        )
        provider.active = "absolute"
        conversation_id = "m571-ambiguous-date-role"

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                dax_calls = service.powerbi.dax_calls
                response = await client.post("/api/v1/chat", json={
                    "message": "2025年5月销售额",
                    "conversation_id": conversation_id,
                    "request_id": "m571-ambiguous-date-role-request",
                    "semantic_model_key": "local_desktop_model",
                })

            body = response.json()
            assert response.status_code == 200, body
            assert body["terminal_state"] == "clarification_required", body
            assert body["memory_commit"] is False
            assert body["execution_audit"]["dax_executed"] is False
            assert service.powerbi.dax_calls == dax_calls
            assert await service.pipeline.get_latest_committed_memory(
                conversation_id, RuntimeDataMode.REAL
            ) is None

    @pytest.mark.asyncio
    async def test_m55_unknown_member_fails_closed_before_dax_and_commit(
        self, monkeypatch
    ):
        app, provider = _patch_m533_multi_turn_composition(monkeypatch)
        transport = ASGITransport(app=app)
        provider.active = "m55_unknown_member"
        conversation_id = "m55-unknown-member"

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                dax_calls = service.powerbi.dax_calls
                response = await client.post("/api/v1/chat", json={
                    "message": "火星区销售额",
                    "conversation_id": conversation_id,
                    "request_id": "m55-unknown-member-request",
                    "semantic_model_key": "local_desktop_model",
                })

            body = response.json()
            assert response.status_code == 200, body
            assert body["terminal_state"] == "clarification_required"
            assert body["memory_commit"] is False
            audit = body["execution_audit"]
            assert audit["dax_executed"] is False
            assert audit["memory_committed"] is False
            assert audit["current_explicit_slots"] == ["filters", "measure"]
            assert audit["member_grounding_status"][0]["status"] == "UNRESOLVED"
            assert service.powerbi.dax_calls == dax_calls
            assert await service.pipeline.get_latest_committed_memory(
                conversation_id, RuntimeDataMode.REAL
            ) is None

    @pytest.mark.asyncio
    async def test_m55_four_turn_slot_inheritance(self, monkeypatch):
        app, provider = _patch_m533_multi_turn_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "m55-four-turn"

        async def post(client, active, message):
            provider.active = active
            response = await client.post("/api/v1/chat", json={
                "message": message,
                "conversation_id": conversation_id,
                "request_id": f"m55-four-turn-{active}",
                "semantic_model_key": "local_desktop_model",
            })
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["terminal_state"] == "completed", body
            audit = body["execution_audit"]
            assert audit["dax_executed"] is True
            assert audit["memory_committed"] is True
            assert len(audit["canonical_plan_hash"]) == 64
            return audit["canonical_query_plan"]

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                first = await post(client, "absolute", "2025年5月销售额")
                second = await post(client, "m55_south", "那南区呢")
                third = await post(client, "m55_last_year", "换成去年")
                fourth = await post(client, "m55_top_product", "前三个产品呢")

        assert first["measures"] == ["Total Sales"]
        assert first["time_range"]["start_date"] == "2025-05-01"
        assert second["measures"] == ["Total Sales"]
        assert second["time_range"]["start_date"] == "2025-05-01"
        assert second["filters"] == [{
            "field": "Region", "operator": "eq", "value": "华南"
        }]
        assert third["measures"] == ["Total Sales"]
        assert third["filters"] == second["filters"]
        assert third["time_range"]["start_date"] == "2025-01-01"
        assert fourth["measures"] == ["Total Sales"]
        assert fourth["dimensions"] == ["Product"]
        assert fourth["sort"] == "desc"
        assert fourth["top_n"] == 3
        assert fourth["filters"] == second["filters"]
        assert fourth["time_range"] == third["time_range"]
        assert fourth["dimension_tables"] == {
            "OrderDate": "Sales",
            "Product": "Sales",
            "Region": "Sales",
        }

    @pytest.mark.asyncio
    async def test_intent_recovery_requires_a_complete_query_language_draft(
        self, monkeypatch
    ):
        app, provider = _patch_m533_multi_turn_composition(monkeypatch)
        transport = ASGITransport(app=app)
        conversation_id = "m55-llm-fallback"

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                provider.active = "absolute"
                seeded = await client.post("/api/v1/chat", json={
                    "message": "2025年5月销售额",
                    "conversation_id": conversation_id,
                    "request_id": "m55-llm-fallback-seed",
                    "semantic_model_key": "local_desktop_model",
                })
                assert seeded.json()["terminal_state"] == "completed"

                provider.active = "m55_top_product"
                provider.fail_intent_once = True
                ranking = await client.post("/api/v1/chat", json={
                    "message": "前三个产品",
                    "conversation_id": conversation_id,
                    "request_id": "m55-intent-fallback",
                    "semantic_model_key": "local_desktop_model",
                })
                ranking_body = ranking.json()
                assert ranking_body["terminal_state"] == "completed", ranking_body
                ranking_plan = ranking_body["execution_audit"]["canonical_query_plan"]
                assert ranking_plan["measures"] == ["Total Sales"]
                assert ranking_plan["dimensions"] == ["Product"]
                assert ranking_plan["top_n"] == 3
                assert ranking_body["execution_audit"]["intent_fallback"] is True

                provider.active = "failed"
                provider.fail_query_plan_once = True
                scalar = await client.post("/api/v1/chat", json={
                    "message": "总销售额是多少？",
                    "conversation_id": "m55-query-plan-fallback",
                    "request_id": "m55-query-plan-fallback-request",
                    "semantic_model_key": "local_desktop_model",
                })
                scalar_body = scalar.json()
                # Missing language extraction cannot certify absent filters.
                assert scalar_body["terminal_state"] == "validation_failed", scalar_body
                assert not scalar_body.get("memory_commit")
                assert not scalar_body.get("execution_audit", {}).get("dax_executed")

    @pytest.mark.asyncio
    async def test_unsupported_intent_routing_and_memory_boundaries(self, monkeypatch):
        app, provider = _patch_unsupported_routing_composition(monkeypatch)
        transport = ASGITransport(app=app)
        cases = (
            ("normal", "总销售额是多少？", "completed"),
            ("unknown", "客户幸福指数是多少？", "clarification_required"),
            ("comparison", "销售额同比去年如何？", "clarification_required"),
            ("filter", "销售额中类别包含 Furniture", "clarification_required"),
            ("non_data", "帮我写一首诗", "unsupported"),
        )
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                for active, message, terminal_state in cases:
                    provider.active = active
                    conversation_id = f"unsupported-routing-{active}"
                    response = await client.post("/api/v1/chat", json={
                        "message": message,
                        "conversation_id": conversation_id,
                        "request_id": f"unsupported-routing-{active}-request",
                        "semantic_model_key": "local_desktop_model",
                    })
                    body = response.json()
                    assert response.status_code == 200, body
                    assert body["terminal_state"] == terminal_state, body
                    committed = await service.pipeline.get_latest_committed_memory(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    if active == "normal":
                        assert committed is not None
                        assert body["intent"] == "data_question"
                    else:
                        assert committed is None
                    if active in {"comparison", "filter", "non_data"}:
                        assert await service.pipeline.get_pending_clarification(
                            conversation_id, RuntimeDataMode.REAL
                        ) is None

    @pytest.mark.asyncio
    async def test_readonly_unsupported_preflight_never_uses_llm_dax_or_memory(
        self, monkeypatch
    ):
        app, provider = _patch_unsupported_routing_composition(monkeypatch)
        transport = ASGITransport(app=app)
        messages = (
            "估算明年销售额",
            "预测下个月销售额",
            "假设明年增长10%",
            "帮我修改这个 PBIX 里的度量值",
            "删除所有数据",
        )
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for index, message in enumerate(messages):
                    conversation_id = f"m533-unsupported-{index}"
                    llm_calls = len(provider.calls)
                    dax_calls = service.powerbi.dax_calls
                    response = await client.post("/api/v1/chat", json={
                        "message": message,
                        "conversation_id": conversation_id,
                        "request_id": f"m533-unsupported-request-{index}",
                        "semantic_model_key": "local_desktop_model",
                    })
                    body = response.json()
                    assert response.status_code == 200
                    assert body["terminal_state"] == "unsupported"
                    assert body["memory_commit"] is False
                    assert len(provider.calls) == llm_calls
                    assert service.powerbi.dax_calls == dax_calls
                    assert await service.pipeline.get_latest_committed_memory(
                        conversation_id, RuntimeDataMode.REAL
                    ) is None

    @pytest.mark.asyncio
    async def test_approximate_existing_fact_is_not_prediction(self, monkeypatch):
        app, provider = _patch_unsupported_routing_composition(monkeypatch)
        transport = ASGITransport(app=app)
        provider.active = "normal"

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/chat", json={
                    "message": "总销售额大概是多少",
                    "conversation_id": "m55-approximate-read",
                    "request_id": "m55-approximate-read-request",
                    "semantic_model_key": "local_desktop_model",
                })

            body = response.json()
            assert response.status_code == 200, body
            assert body["terminal_state"] == "completed", body
            assert body["execution_audit"]["capability_decision"] == "READ_ANALYSIS"
            assert service.powerbi.dax_calls == 1

    @pytest.mark.asyncio
    async def test_catalog_alias_can_correct_intent_clarification(self, monkeypatch):
        class ClarifyingProvider(_M24ScriptedDeepSeekProvider):
            async def generate(self, request, output_type):
                if request.task == LLMTask.INTENT_RECOGNITION:
                    self.calls.append(request)
                    return LLMResponse(
                        content="{}",
                        structured=IntentSpec(
                            intent=IntentType.CLARIFICATION,
                            confidence=0.7,
                            normalized_question="销售额是多少？",
                            needs_clarification=True,
                            clarification_question="请明确指标。",
                        ),
                        model="fake-deepseek",
                    )
                return await super().generate(request, output_type)

        import backend.app.llm.factory as llm_factory
        import backend.app.main as main_module

        provider = ClarifyingProvider()
        registry = LLMProviderRegistry()
        registry.register(_deepseek_test_profile(), provider)
        monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
        _patch_fake_runtime_glossary(monkeypatch)
        monkeypatch.setattr(main_module, "LocalMCPPowerBIAdapter", _M24FakeLocalPowerBIAdapter)
        app = main_module.create_app(settings=Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            deepseek_api_key="test-key-not-real",
        ))

        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/chat", json={
                    "message": "销售额是多少？",
                    "request_id": "intent-grounding-correction",
                    "semantic_model_key": "local_desktop_model",
                })
        body = response.json()
        assert body["terminal_state"] == "completed"
        assert body["intent"] == "data_question"
        assert body["tool_sequence"] == [
            "get_semantic_model_schema", "execute_dax"
        ]

    @pytest.mark.asyncio
    async def test_local_chat_and_replay_use_one_pipeline_without_reexecution(self, monkeypatch):
        app, provider = _patch_m24_local_composition(
            monkeypatch, _M24FakeLocalPowerBIAdapter
        )
        transport = ASGITransport(app=app)
        payload = {
            "message": "总销售额是多少？",
            "conversation_id": "conv-m24-local",
            "request_id": "req-m24-local",
            "semantic_model_key": "local_desktop_model",
        }
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            adapter = service.powerbi
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                first = await c.post("/api/v1/chat", json=payload)
                replay = await c.post("/api/v1/chat", json=payload)

            assert first.status_code == 200
            first_data = first.json()
            assert first_data["terminal_state"] == "completed"
            assert first_data["source_mode"] == "real"
            assert first_data["powerbi_mode"] == "local_mcp"
            assert first_data["tool_sequence"] == [
                "get_semantic_model_schema",
                "execute_dax",
            ]
            assert replay.status_code == 200
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["source_mode"] == "real"
            assert len(provider.calls) == 2
            assert all(
                call.task not in {LLMTask.DAX, LLMTask.ANSWER}
                for call in provider.calls
            )
            assert adapter.schema_calls == 1
            assert adapter.dax_calls == 1
            query_plan_prompt = next(
                call for call in provider.calls if call.task == LLMTask.QUERY_PLAN
            )
            assert "Total Sales" in str(query_plan_prompt.messages)
            assert "local_desktop_model" in str(query_plan_prompt.messages)
            assert first_data["answer"] == "销售额为100.00。"
            assert [
                block["type"] for block in first_data["presentation"]["blocks"]
            ] == ["text"]
            assert first_data["presentation"]["datasets"][0]["rows"] == [[100.0]]
            audit = first_data["execution_audit"]
            assert audit["deterministic_dax"] is True
            assert audit["layer3_pass"] is True
            assert audit["query_result_success"] is True
            assert audit["verified_fact_count"] >= 2
            assert audit["factual_validation_pass"] is True
            assert audit["llm_dax_call_count"] == 0
            assert audit["memory_version"] == 1

    @pytest.mark.asyncio
    async def test_monthly_sales_trend_uses_metadata_and_readable_presentation(
        self, monkeypatch
    ):
        app = _patch_m56_monthly_trend_composition(monkeypatch)
        from backend.tests.fixtures.model_overrides import activate_registry, bound_registry

        transport = ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            adapter = app.state.turn_service.powerbi
            # Startup owns the adapter. Pin configuration before the request,
            # while retaining production CatalogBuilder/runtime validation.
            schema = await adapter.get_semantic_model_schema("local_desktop_model")
            activate_registry(monkeypatch, bound_registry(schema, ["desktop_sales_language", "desktop_calendar_roles"]))
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "每个月销售额趋势",
                    "conversation_id": "m56-monthly-sales-trend",
                    "request_id": "m56-monthly-sales-trend-request",
                    "semantic_model_key": "local_desktop_model",
                })

        body = response.json()
        assert response.status_code == 200, body
        assert body["terminal_state"] == "completed", (
            body.get("error_type"), body.get("execution_audit")
        )
        assert body["memory_commit"] is True
        audit = body["execution_audit"]
        plan = audit["canonical_query_plan"]
        assert plan["dimensions"] == ["YearMonth"]
        assert plan["dimension_tables"] == {"YearMonth": "Date"}
        assert plan["dimension_order"] == "asc"
        assert audit["dax_executed"] is True
        assert adapter.dax_calls == 1
        assert "'Date'[YearMonth]" in adapter.last_dax

        presentation = body["presentation"]
        assert [block["type"] for block in presentation["blocks"]] == [
            "text", "table", "chart"
        ]
        chart = next(
            block for block in presentation["blocks"] if block["type"] == "chart"
        )
        assert chart["visual_type"] == "line"
        dataset = presentation["datasets"][0]
        assert "T00:00:00" not in str(dataset["formatted_rows"])
        assert [row[0] for row in dataset["formatted_rows"]] == [
            "2025年1月", "2025年2月", "2025年3月", "2025年4月"
        ]
        answer = body["answer"]
        assert "2025年2月" in answer
        assert "达到最高点" in answer
        assert "随后回落" in answer
        assert "2025年4月出现回升" in answer
        assert "T00:00:00" not in answer
        assert "2025年1月" not in answer
        assert "2025年3月" not in answer
        assert len(answer) < 180

    @pytest.mark.asyncio
    async def test_preview_missing_rows_is_controlled_and_never_falls_back(self, monkeypatch):
        app, provider = _patch_m24_local_composition(
            monkeypatch, _M24PreviewMissingRowsAdapter
        )
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            adapter = app.state.turn_service.powerbi
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "总销售额是多少？",
                    "request_id": "req-m24-preview-failure",
                    "semantic_model_key": "local_desktop_model",
                })
            data = response.json()
            assert response.status_code == 200
            assert data["terminal_state"] == "tool_failed"
            assert data["error_type"] == "preview_row_data_missing"
            assert data["source_mode"] == "real"
            assert len(provider.calls) == 2
            assert all(call.task != LLMTask.DAX for call in provider.calls)
            assert adapter.dax_calls == 1

    @pytest.mark.asyncio
    async def test_local_connection_failure_is_controlled_without_mock_fallback(self, monkeypatch):
        app, provider = _patch_m24_local_composition(
            monkeypatch, _M24ConnectionFailureAdapter
        )
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            adapter = app.state.turn_service.powerbi
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "总销售额是多少？",
                    "request_id": "req-m24-connection-failure",
                })
            data = response.json()
            assert response.status_code == 200
            assert data["terminal_state"] == "tool_failed"
            assert data["source_mode"] == "real"
            assert adapter.schema_calls == 1
            assert adapter.dax_calls == 0
            assert len(provider.calls) == 1


class _M582ShapeProvider(LLMProvider):
    def __init__(self, question: str) -> None:
        self.question = question
        self.calls: list[LLMRequest] = []

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(self, request, output_type):
        self.calls.append(request)
        text = self.question
        if request.task == LLMTask.INTENT_RECOGNITION:
            measures = []
            dimensions = []
            if "平均订单" in text:
                measures = ["平均订单金额"]
            elif "订单数" in text:
                measures = ["总订单数"]
            elif "销量" in text:
                measures = ["销量"]
            elif "销售额" in text:
                measures = ["销售额"]
            if "产品" in text:
                dimensions = ["产品"]
            structured = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.99,
                normalized_question=text,
                detected_measures=measures,
                detected_dimensions=dimensions,
                detected_time_range=(text if "2025年8月" in text else None),
            )
        elif request.task == LLMTask.QUERY_PLAN:
            measures = []
            dimensions = []
            if "平均订单" in text:
                measures = ["Average Order Value"]
            elif "订单数" in text:
                measures = ["Total Orders"]
            elif "销量" in text:
                measures = ["Total Quantity"]
            elif "销售额" in text:
                measures = ["Total Sales"]
            if "产品" in text:
                dimensions = ["Product"]
            structured = QueryPlan(
                normalized_question=text,
                semantic_model_key="local_desktop_model",
                measures=measures,
                dimensions=dimensions,
                time_range=(text if "2025年8月" in text else None),
            )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="fake-deepseek",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


class _M582ShapeAdapter(_M24FakeLocalPowerBIAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_dax = ""
        self.member_calls = 0

    async def get_semantic_model_schema(self, semantic_model_key: str):
        self.schema_calls += 1
        return SemanticModelSchema(
            name="M5.8.2 fixture",
            key=semantic_model_key,
            tables=[
                TableSchema(
                    name="Sales",
                    columns=[
                        ColumnSchema(name="Product", data_type="string"),
                        ColumnSchema(name="Category", data_type="string"),
                        ColumnSchema(name="OrderDate", data_type="datetime"),
                        ColumnSchema(name="Region", data_type="string"),
                    ],
                    measures=[
                        MeasureSchema(name="Total Sales", data_type="decimal"),
                        MeasureSchema(name="Total Quantity", data_type="int64"),
                        MeasureSchema(name="Total Orders", data_type="int64"),
                        MeasureSchema(name="Average Order Value", data_type="decimal"),
                    ],
                ),
                TableSchema(
                    name="Date",
                    columns=[
                        ColumnSchema(name="Date", data_type="datetime"),
                        ColumnSchema(name="YearMonth", data_type="datetime"),
                    ],
                ),
            ],
            relationships=[RelationshipSchema(
                from_table="Sales",
                from_column="OrderDate",
                to_table="Date",
                to_column="Date",
                is_active=True,
            )],
        )

    async def get_column_members(self, request: ColumnMembersRequest):
        self.member_calls += 1
        assert request.field_name == "Product"
        return ColumnMembersResult(
            semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,
            field_name=request.field_name,
            values=["手机", "笔记本", "电脑"],
            source_mode="real",
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        self.last_dax = request.dax
        if "'Date'[YearMonth]" in request.dax:
            columns = ["Date[YearMonth]", "[Total Sales]"]
            rows = [["2025-08-01", 80], ["2026-01-01", 100]]
        elif (
            "SUMMARIZECOLUMNS(\n    'Sales'[Product]," in request.dax
            and "[Total Quantity]" in request.dax
        ):
            columns = ["Sales[Product]", "[Total Quantity]"]
            rows = [["手机", 20], ["笔记本", 10]]
        elif "'Sales'[Product]" in request.dax and "[Total Quantity]" not in request.dax:
            columns = ["Sales[Product]"]
            rows = [["手机"], ["笔记本"], ["电脑"]]
        elif "[Average Order Value]" in request.dax:
            columns, rows = ["[Average Order Value]"], [[125.5]]
        elif "[Total Orders]" in request.dax:
            columns, rows = ["[Total Orders]"], [[8]]
        else:
            columns, rows = ["[Total Quantity]"], [[30]]
        return QueryResult(
            result_id=f"qr-{request.request_id}",
            semantic_model_key=request.semantic_model_key,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            source_mode="real",
            request_id=request.request_id,
        )


def _patch_m582_shape_composition(monkeypatch, question: str):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _M582ShapeProvider(question)
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(main_module, "LocalMCPPowerBIAdapter", _M582ShapeAdapter)
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    )
    return main_module.create_app(settings=settings), provider


class TestM582ProductionRoutingAndShapes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "response_type", "fragment"),
        [
            ("你支持回答哪些问题？", "answer", "指标查询"),
            ("数据分析支持的范围在哪", "answer", "不预测"),
            ("你是什么模型", "answer", "DeepSeek"),
            ("1+1等于几", "answer", "2"),
            ("50乘50是几", "answer", "2500"),
            ("我是谁", "unsupported", "无法判断"),
        ],
    )
    async def test_non_business_routes_are_zero_llm_schema_dax_and_memory(
        self, monkeypatch, question, response_type, fragment
    ):
        app, provider = _patch_m582_shape_composition(monkeypatch, question)
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/chat", json={
                    "message": question,
                    "conversation_id": str(uuid.uuid4()),
                    "request_id": str(uuid.uuid4()),
                    "semantic_model_key": "local_desktop_model",
                })

        body = response.json()
        visible_text = body.get("answer") or body.get("unsupported_reason") or ""
        assert response.status_code == 200, body
        assert body["response_type"] == response_type
        assert fragment in visible_text
        assert body["memory_commit"] is False
        assert body["tool_sequence"] == []
        assert provider.calls == []
        assert service.powerbi.schema_calls == 0
        assert service.powerbi.dax_calls == 0

    @pytest.mark.asyncio
    async def test_report_route_reaches_template_gate_before_schema(self, monkeypatch):
        question = "生成销售报表"
        app, provider = _patch_m582_shape_composition(monkeypatch, question)
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/chat", json={
                    "message": question,
                    "conversation_id": str(uuid.uuid4()),
                    "request_id": str(uuid.uuid4()),
                    "semantic_model_key": "local_desktop_model",
                })

        body = response.json()
        assert body["terminal_state"] == "clarification_required"
        assert body["clarification_question"] == "生成报表前请选择有效的模板"
        assert service.powerbi.schema_calls == 0
        assert service.powerbi.dax_calls == 0
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "shape", "measure", "dimension"),
        [
            ("平均订单金额是多少", "scalar", "Average Order Value", None),
            ("总订单数是多少", "scalar", "Total Orders", None),
            ("我们销售了哪些产品？", "entity_list", None, "Product"),
            ("销量最高的是哪款产品？", "ranking", "Total Quantity", "Product"),
            ("手机和笔记本的销量分别是多少？", "member_set", "Total Quantity", "Product"),
            ("手机和电脑加起来销量是多少", "filtered_aggregation", "Total Quantity", None),
            ("2025年8月到2026年1月销售额月趋势", "bounded_trend", "Total Sales", "YearMonth"),
            ("从2025年8月至2026年1月按月看销售额", "bounded_trend", "Total Sales", "YearMonth"),
        ],
    )
    async def test_formal_pipeline_executes_each_shape(
        self, monkeypatch, question, shape, measure, dimension
    ):
        app, _ = _patch_m582_shape_composition(monkeypatch, question)
        request_id = str(uuid.uuid4())
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/chat", json={
                    "message": question,
                    "conversation_id": str(uuid.uuid4()),
                    "request_id": request_id,
                    "semantic_model_key": "local_desktop_model",
                })

        body = response.json()
        assert response.status_code == 200, body
        assert body["terminal_state"] == "completed", body
        plan = body["execution_audit"]["canonical_query_plan"]
        assert plan["query_shape"] == shape
        assert plan["measures"] == ([] if measure is None else [measure])
        assert plan["dimensions"] == ([] if dimension is None else [dimension])
        assert body["execution_audit"]["dax_executed"] is True
        assert body["memory_commit"] is True

    @pytest.mark.asyncio
    async def test_ambiguous_best_asks_only_for_measure_and_executes_zero_dax(
        self, monkeypatch
    ):
        app, _ = _patch_m582_shape_composition(monkeypatch, "哪些产品卖得最好？")
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/chat", json={
                    "message": "哪些产品卖得最好？",
                    "conversation_id": str(uuid.uuid4()),
                    "request_id": str(uuid.uuid4()),
                    "semantic_model_key": "local_desktop_model",
                })
            dax_calls = service.powerbi.dax_calls

        body = response.json()
        assert body["terminal_state"] == "clarification_required", body
        assert body["clarification_question"] == "请明确用于判断排名的业务指标。"
        assert body["execution_audit"]["missing_slots"] == ["measure"]
        assert dax_calls == 0
        assert body["memory_commit"] is False


class TestM25BusinessGoldenOffline:
    @pytest.mark.parametrize(
        ("question", "measure", "dimension", "sort", "top_n"),
        [
            ("按类别看销售额。", "Total Sales", "Category", None, None),
            ("销售额最高的前3个产品是什么？", "Total Sales", "Product", "desc", 3),
            ("按产品看总数量。", "Total Quantity", "Product", None, None),
            ("总数量最高的前3个类别是什么？", "Total Quantity", "Category", "desc", 3),
        ],
    )
    @pytest.mark.asyncio
    async def test_business_case_uses_formal_pipeline_and_commits_grounded_memory(
        self,
        monkeypatch,
        question,
        measure,
        dimension,
        sort,
        top_n,
    ):
        from backend.app.memory.models import RuntimeDataMode

        provider = _M25BusinessGoldenProvider(
            question=question,
            measure=measure,
            dimension=dimension,
            sort=sort,
            top_n=top_n,
        )
        app = _patch_m25_business_golden_composition(monkeypatch, provider)
        transport = ASGITransport(app=app)
        request_id = f"req-m25-{dimension}-{measure}".replace(" ", "-").lower()

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            adapter = service.powerbi
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": question,
                    "request_id": request_id,
                    "semantic_model_key": "local_desktop_model",
                })
            memory = await service.pipeline.get_memory_by_request_id(
                request_id, RuntimeDataMode.REAL
            )

        data = response.json()
        assert response.status_code == 200
        assert data["terminal_state"] == "completed"
        assert data["source_mode"] == "real"
        assert data["memory_commit"] is True
        assert data["tool_sequence"] == [
            "get_semantic_model_schema",
            "execute_dax",
        ]
        assert memory is not None
        assert memory.measures == [measure]
        assert memory.dimensions == [dimension]
        assert memory.sort == sort
        assert memory.top_n == top_n
        assert memory.last_dax is not None
        assert f"[{measure}]" in memory.last_dax
        assert f"[{dimension}]" in memory.last_dax
        assert adapter.schema_calls == 1
        assert adapter.dax_calls == 1
        assert len(provider.calls) == 2
        assert all(
            call.task not in {LLMTask.DAX, LLMTask.ANSWER}
            for call in provider.calls
        )
        assert data["execution_audit"]["llm_dax_call_count"] == 0
        assert data["execution_audit"]["factual_validation_pass"] is True

    def test_manual_business_golden_definitions_are_generalized_and_sanitized(self):
        from scripts.manual_smoke.m2_business_golden_smoke import (
            BUSINESS_GOLDEN_CASES,
        )

        assert len(BUSINESS_GOLDEN_CASES) == 7
        generalized = [
            case for case in BUSINESS_GOLDEN_CASES if case["generalization"]
        ]
        assert len(generalized) >= 2
        assert {dimension for case in generalized for dimension in case["dimensions"]} >= {
            "Product",
            "Category",
        }
        assert any(case["top_n"] == 3 and case["sort"] == "desc" for case in generalized)
        forbidden_keys = {
            "dax",
            "expected_value",
            "pbix_path",
            "prompt",
            "raw_response",
        }
        assert all(forbidden_keys.isdisjoint(case) for case in BUSINESS_GOLDEN_CASES)


class TestM58RequestScopedProfileSelection:
    @staticmethod
    def _app(monkeypatch):
        import backend.app.llm.factory as llm_factory
        import backend.app.main as main_module

        deepseek = _M533MultiTurnProvider()
        kimi = _M533MultiTurnProvider()
        registry = LLMProviderRegistry()
        registry.register(_llm_test_profile("deepseek", "fake-deepseek"), deepseek)
        registry.register(_llm_test_profile("kimi-k2.6", "azure/Kimi-K2.6"), kimi)
        monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
        _patch_fake_runtime_glossary(monkeypatch)
        monkeypatch.setattr(
            main_module, "LocalMCPPowerBIAdapter", _M533MultiTurnAdapter
        )
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.OPENAI_COMPATIBLE,
            llm_default_profile="deepseek",
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            deepseek_api_key="test-key-not-real",
        )
        return main_module.create_app(settings=settings), deepseek, kimi

    @pytest.mark.asyncio
    async def test_two_conversations_do_not_cross_contaminate_profiles(self, monkeypatch):
        app, deepseek, kimi = self._app(monkeypatch)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                responses = await asyncio.gather(
                    client.post(
                        "/api/v1/chat",
                        json={
                            "message": "本月销售额是多少？",
                            "conversation_id": "m58-conv-deepseek",
                            "request_id": "m58-req-deepseek",
                            "semantic_model_key": "local_desktop_model",
                            "llm_profile_key": "deepseek",
                        },
                    ),
                    client.post(
                        "/api/v1/chat",
                        json={
                            "message": "本月销售额是多少？",
                            "conversation_id": "m58-conv-kimi",
                            "request_id": "m58-req-kimi",
                            "semantic_model_key": "local_desktop_model",
                            "llm_profile_key": "kimi-k2.6",
                        },
                    ),
                )

        assert [response.status_code for response in responses] == [200, 200]
        assert [response.json()["llm_profile_key"] for response in responses] == [
            "deepseek",
            "kimi-k2.6",
        ]
        assert deepseek.calls and kimi.calls

    @pytest.mark.asyncio
    async def test_mid_conversation_switch_preserves_canonical_memory(self, monkeypatch):
        app, deepseek, kimi = self._app(monkeypatch)
        kimi.active = "m55_south"
        conversation_id = "m58-profile-switch"
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/api/v1/chat",
                    json={
                        "message": "本月销售额是多少？",
                        "conversation_id": conversation_id,
                        "request_id": "m58-profile-switch-1",
                        "semantic_model_key": "local_desktop_model",
                        "llm_profile_key": "deepseek",
                    },
                )
                second = await client.post(
                    "/api/v1/chat",
                    json={
                        "message": "那南区呢",
                        "conversation_id": conversation_id,
                        "request_id": "m58-profile-switch-2",
                        "semantic_model_key": "local_desktop_model",
                        "llm_profile_key": "kimi-k2.6",
                    },
                )
                memory = await app.state.turn_service.pipeline.get_latest_committed_memory(
                    conversation_id, RuntimeDataMode.REAL
                )

        assert first.status_code == second.status_code == 200
        assert first.json()["llm_profile_key"] == "deepseek"
        assert second.json()["llm_profile_key"] == "kimi-k2.6"
        assert memory is not None
        assert memory.measures == ["Total Sales"]
        assert memory.time_range is not None
        assert memory.filters[0]["value"] == "华南"
        assert memory.llm_provider == "kimi-k2.6"
        assert "provider" not in memory.last_query_plan
        assert deepseek.calls and kimi.calls
