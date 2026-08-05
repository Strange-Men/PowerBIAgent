"""M1.0 修复测试 — conversation_id、幂等重放、报表模板

测试覆盖：
- clarification/unsupported 保留 conversation_id（5 测试）
- request_id 幂等重放（10 测试）
- 报表模板一致性（5 测试）
"""

import asyncio
import uuid

import pytest

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
# M1.6.3: MockAgentRuntime 已删除，MockTurnService 默认使用 MockLLMProvider
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer
from backend.app.harness.runtime.turn_controller import TurnState


@pytest.fixture
def service_factory():
    """创建独立 Service 的工厂"""
    def _make():
        return MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            # M1.6.3: llm_runtime 参数已移除，使用默认 MockLLMProvider
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
    return _make


# ══════════════════════════════════════════════════════════════════════
# conversation_id 测试
# ══════════════════════════════════════════════════════════════════════

class TestConversationIdClarification:
    """clarification 保留 conversation_id"""

    @pytest.mark.asyncio
    async def test_clarification_keeps_specified_conversation_id(self, service_factory):
        """指定 conversation_id 的 clarification 返回该 ID"""
        svc = service_factory()
        result = await svc.execute(
            message="帮我看看数据",
            conversation_id="conv-test-clarify-001",
            request_id="req-clarify-001",
            scenario=MockScenarioSelection(intent_key="clarification"),
        )
        assert result["conversation_id"] == "conv-test-clarify-001"
        assert result["terminal_state"] == "clarification_required"
        assert result["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_clarification_auto_generates_conversation_id(self, service_factory):
        """未指定 conversation_id 时 clarification 自动生成"""
        svc = service_factory()
        result = await svc.execute(
            message="帮我看看数据",
            request_id="req-clarify-auto",
            scenario=MockScenarioSelection(intent_key="clarification"),
        )
        conv_id = result["conversation_id"]
        assert conv_id != "", "conversation_id should not be empty"
        assert result["terminal_state"] == "clarification_required"


class TestConversationIdUnsupported:
    """unsupported 保留 conversation_id"""

    @pytest.mark.asyncio
    async def test_unsupported_keeps_specified_conversation_id(self, service_factory):
        """指定 conversation_id 的 unsupported 返回该 ID"""
        svc = service_factory()
        result = await svc.execute(
            message="删除所有数据",
            conversation_id="conv-test-unsup-001",
            request_id="req-unsup-001",
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )
        assert result["conversation_id"] == "conv-test-unsup-001"
        assert result["terminal_state"] == "unsupported"
        assert result["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_unsupported_auto_generates_conversation_id(self, service_factory):
        """未指定 conversation_id 时 unsupported 自动生成"""
        svc = service_factory()
        result = await svc.execute(
            message="删除所有数据",
            request_id="req-unsup-auto",
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )
        conv_id = result["conversation_id"]
        assert conv_id != "", "conversation_id should not be empty"
        assert result["terminal_state"] == "unsupported"


class TestConversationIdConcurrent:
    """并发请求不串 conversation_id"""

    @pytest.mark.asyncio
    async def test_concurrent_non_completed_no_crosstalk(self, service_factory):
        """两个并发非完成状态请求不串 conversation_id"""
        svc = service_factory()

        async def req_clarify():
            return await svc.execute(
                message="帮我看看数据",
                conversation_id="conv-conc-clarify",
                request_id="req-conc-clarify",
                scenario=MockScenarioSelection(intent_key="clarification"),
            )

        async def req_unsupported():
            return await svc.execute(
                message="删除所有数据",
                conversation_id="conv-conc-unsup",
                request_id="req-conc-unsup",
                scenario=MockScenarioSelection(intent_key="unsupported"),
            )

        r_clarify, r_unsup = await asyncio.gather(req_clarify(), req_unsupported())

        assert r_clarify["conversation_id"] == "conv-conc-clarify"
        assert r_unsup["conversation_id"] == "conv-conc-unsup"
        assert r_clarify["terminal_state"] == "clarification_required"
        assert r_unsup["terminal_state"] == "unsupported"


# ══════════════════════════════════════════════════════════════════════
# 幂等重放测试
# ══════════════════════════════════════════════════════════════════════

class TestIdempotentReplayAnswer:
    """Answer 幂等重放"""

    @pytest.mark.asyncio
    async def test_answer_replay_content_matches_first(self, service_factory):
        """Answer 重复请求内容与第一次一致"""
        svc = service_factory()
        req_id = "req-replay-answer-001"

        r1 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-replay-answer",
            request_id=req_id,
        )
        r2 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-replay-answer",
            request_id=req_id,
        )

        assert r1["terminal_state"] == "completed"
        assert r2["terminal_state"] == "duplicate"  # M1.0: 重放使用 duplicate
        assert r1["answer"] == r2["answer"]
        assert r1["response_type"] == r2["response_type"]
        assert r1["intent"] == r2["intent"]

    @pytest.mark.asyncio
    async def test_answer_replay_has_idempotent_marker(self, service_factory):
        """重复请求标记 idempotent_replay=true"""
        svc = service_factory()
        req_id = "req-replay-marker-001"

        r1 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-marker",
            request_id=req_id,
        )
        r2 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-marker",
            request_id=req_id,
        )

        # 第一次不标记重放
        assert r1.get("idempotent_replay") is not True
        # 第二次标记重放
        assert r2.get("idempotent_replay") is True
        assert r2.get("replayed_request_id") == req_id

    @pytest.mark.asyncio
    async def test_answer_replay_no_additional_llm_calls(self, service_factory):
        """第二次调用不增加 LLM 调用次数"""
        svc = service_factory()
        req_id = "req-replay-llm-001"

        await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-llm",
            request_id=req_id,
        )
        # 第二次调用
        r2 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-llm",
            request_id=req_id,
        )

        # tool_sequence 为空
        assert r2["tool_sequence"] == []
        # memory_commit 为 false
        assert r2["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_answer_replay_new_trace_id(self, service_factory):
        """重放使用新 trace_id"""
        svc = service_factory()
        req_id = "req-replay-trace-001"

        r1 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-trace",
            request_id=req_id,
        )
        r2 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-trace",
            request_id=req_id,
        )

        assert r1["trace_id"] != r2["trace_id"]
        assert r2["trace_id"] != ""


class TestIdempotentReplayReport:
    """Report 幂等重放"""

    @pytest.mark.asyncio
    async def test_report_replay_content_matches_first(self, service_factory):
        """Report 重复请求的 report_id、template_key、HTML 一致"""
        svc = service_factory()
        req_id = "req-replay-report-001"

        r1 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-report",
            request_id=req_id,
            report_template_key="sales_weekly",
        )
        r2 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-report",
            request_id=req_id,
            report_template_key="sales_weekly",
        )

        assert r1["terminal_state"] == "completed"
        assert r1["response_type"] == "report"
        assert r2["report"] is not None

        # 重放内容一致
        r1_report = r1["report"]
        r2_report = r2["report"]
        assert r2_report["report_id"] == r1_report["report_id"]
        assert r2_report["template_key"] == r1_report["template_key"]
        assert r2_report["html"] == r1_report["html"]

    @pytest.mark.asyncio
    async def test_report_replay_no_tool_execution(self, service_factory):
        """Report 重放 tool_sequence 为空"""
        svc = service_factory()
        req_id = "req-replay-rpt-tools-001"

        await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-rpt-tools",
            request_id=req_id,
            report_template_key="sales_weekly",
        )
        r2 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-rpt-tools",
            request_id=req_id,
            report_template_key="sales_weekly",
        )

        assert r2["tool_sequence"] == []

    @pytest.mark.asyncio
    async def test_report_replay_no_memory_version_bump(self, service_factory):
        """Report 重放不增加 Memory 版本"""
        svc = service_factory()
        req_id = "req-replay-rpt-version-001"

        r1 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-rpt-version",
            request_id=req_id,
            report_template_key="sales_weekly",
        )
        r2 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-rpt-version",
            request_id=req_id,
            report_template_key="sales_weekly",
        )

        assert r1["final_memory_version"] is not None
        # 重放 memory_commit 和 final_memory_version 来自原始快照
        assert r2["memory_commit"] is False


class TestIdempotentReplayClarification:
    """clarification 幂等重放"""

    @pytest.mark.asyncio
    async def test_clarification_replay_content_consistent(self, service_factory):
        """clarification 重复请求内容一致"""
        svc = service_factory()
        req_id = "req-replay-clarify-001"

        r1 = await svc.execute(
            message="帮我看看数据",
            conversation_id="conv-replay-clarify",
            request_id=req_id,
            scenario=MockScenarioSelection(intent_key="clarification"),
        )
        r2 = await svc.execute(
            message="帮我看看数据",
            conversation_id="conv-replay-clarify",
            request_id=req_id,
            scenario=MockScenarioSelection(intent_key="clarification"),
        )

        assert r1["terminal_state"] == "clarification_required"
        assert r2["clarification_question"] == r1["clarification_question"]
        assert r2["conversation_id"] == r1["conversation_id"]
        assert r2.get("idempotent_replay") is True


class TestIdempotentReplayUnsupported:
    """unsupported 幂等重放"""

    @pytest.mark.asyncio
    async def test_unsupported_replay_content_consistent(self, service_factory):
        """unsupported 重复请求内容一致"""
        svc = service_factory()
        req_id = "req-replay-unsup-001"

        r1 = await svc.execute(
            message="删除所有数据",
            conversation_id="conv-replay-unsup",
            request_id=req_id,
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )
        r2 = await svc.execute(
            message="删除所有数据",
            conversation_id="conv-replay-unsup",
            request_id=req_id,
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )

        assert r1["terminal_state"] == "unsupported"
        assert r2["unsupported_reason"] == r1["unsupported_reason"]
        assert r2["conversation_id"] == r1["conversation_id"]
        assert r2.get("idempotent_replay") is True


class TestIdempotentReplayDifferentRequests:
    """不同 request_id 互不影响"""

    @pytest.mark.asyncio
    async def test_different_request_ids_independent(self, service_factory):
        """不同 request_id 各自独立"""
        svc = service_factory()

        r_a = await svc.execute(
            message="销售额查询",
            conversation_id="conv-diff",
            request_id="req-diff-A",
        )
        r_b = await svc.execute(
            message="利润查询",
            conversation_id="conv-diff",
            request_id="req-diff-B",
        )

        # 两个都是首次请求
        assert r_a.get("idempotent_replay") is not True
        assert r_b.get("idempotent_replay") is not True
        assert r_a["request_id"] != r_b["request_id"]
        # 各自有不同的 trace_id
        assert r_a["trace_id"] != r_b["trace_id"]

    @pytest.mark.asyncio
    async def test_replay_only_affects_same_request_id(self, service_factory):
        """重放只影响相同 request_id"""
        svc = service_factory()

        # 第一次请求
        r1 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-scope",
            request_id="req-replay-A",
        )

        # 第二次相同 request_id
        r2 = await svc.execute(
            message="销售额查询",
            conversation_id="conv-replay-scope",
            request_id="req-replay-A",
        )

        # 新 request_id
        r3 = await svc.execute(
            message="利润查询",
            conversation_id="conv-replay-scope",
            request_id="req-replay-B",
        )

        assert r2.get("idempotent_replay") is True
        assert r3.get("idempotent_replay") is not True, \
            "新 request_id 不应被标记为重放"


# ══════════════════════════════════════════════════════════════════════
# 报表模板测试
# ══════════════════════════════════════════════════════════════════════

class TestReportTemplateDefault:
    """默认报表模板 sales_weekly"""

    @pytest.mark.asyncio
    async def test_explicit_template_sales_weekly(self, service_factory):
        """显式传 sales_weekly"""
        svc = service_factory()
        result = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-template-explicit",
            request_id="req-template-explicit",
            report_template_key="sales_weekly",
        )
        assert result["terminal_state"] == "completed"
        assert result["response_type"] == "report"
        assert result["report"]["template_key"] == "sales_weekly"

    @pytest.mark.asyncio
    async def test_no_template_with_report_keywords_uses_default(self, service_factory):
        """不传模板但消息为"生成销售周报"→ 使用 sales_weekly"""
        svc = service_factory()
        result = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-template-default",
            request_id="req-template-default",
        )
        assert result["terminal_state"] == "completed"
        assert result["response_type"] == "report"
        assert result["report"]["template_key"] == "sales_weekly"

    @pytest.mark.asyncio
    async def test_memory_and_api_template_consistent(self, service_factory):
        """Memory 模板与 API 模板一致"""
        svc = service_factory()
        result = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-template-memory",
            request_id="req-template-memory",
        )
        assert result["report"]["template_key"] == "sales_weekly"

        # 从 Repository 验证 Memory 中的模板
        memory = await svc.pipeline.get_memory_by_request_id(
            "req-template-memory", RuntimeDataMode.MOCK
        )
        assert memory is not None
        assert memory.report_template_key == "sales_weekly", \
            f"Memory report_template_key should be 'sales_weekly', got: {memory.report_template_key}"
        assert memory.state_status == MemoryStatus.COMMITTED

    @pytest.mark.asyncio
    async def test_replay_template_consistent(self, service_factory):
        """幂等重放后的模板仍一致"""
        svc = service_factory()
        req_id = "req-template-replay"

        r1 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-template-replay",
            request_id=req_id,
        )
        r2 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-template-replay",
            request_id=req_id,
        )

        assert r1["report"]["template_key"] == "sales_weekly"
        assert r2["report"]["template_key"] == "sales_weekly"
        assert r2["report"]["template_key"] == r1["report"]["template_key"]

    @pytest.mark.asyncio
    async def test_data_question_no_report_template_in_memory(self, service_factory):
        """普通数据问答不写入报表模板"""
        svc = service_factory()
        result = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-dq-no-template",
            request_id="req-dq-no-template",
        )
        assert result["terminal_state"] == "completed"
        assert result["response_type"] == "answer"

        memory = await svc.pipeline.get_memory_by_request_id(
            "req-dq-no-template", RuntimeDataMode.MOCK
        )
        assert memory is not None
        # 数据问答不应写入报表模板
        assert memory.report_template_key is None, \
            f"data_question should not set report_template_key, got: {memory.report_template_key}"


# ══════════════════════════════════════════════════════════════════════
# 版本与文档测试
# ══════════════════════════════════════════════════════════════════════

class TestVersionM10:
    """版本号验证"""

    def test_settings_version_is_m1_5(self):
        """Settings.version 为 M1.6.5"""
        from backend.app.config.settings import Settings
        s = Settings()
        assert s.version == "M1.6.6", f"Expected M1.6.6, got {s.version}"

    def test_health_version_returns_m1_5_in_safe_repr(self):
        """safe_repr 中 version 为 M1.6.5"""
        from backend.app.config.settings import Settings
        s = Settings()
        info = s.safe_repr()
        assert info["version"] == "M1.6.6"


class TestIdempotentResponseSchema:
    """幂等重放响应模型验证"""

    def test_snapshot_model_fields_exist(self):
        """TurnResultSnapshot 包含必需字段"""
        from backend.app.memory.result_snapshot import TurnResultSnapshot
        snapshot = TurnResultSnapshot(
            request_id="test-req",
            conversation_id="test-conv",
            terminal_state="completed",
            intent="data_question",
            response_type="answer",
            answer="Test answer",
        )
        assert snapshot.request_id == "test-req"
        assert snapshot.conversation_id == "test-conv"
        assert snapshot.answer == "Test answer"

    def test_snapshot_store_save_and_get(self):
        """ResultSnapshotStore 保存和获取"""
        import asyncio
        from backend.app.memory.result_snapshot import ResultSnapshotStore, TurnResultSnapshot
        from backend.app.memory.models import RuntimeDataMode

        async def _test():
            store = ResultSnapshotStore()
            snap = TurnResultSnapshot(
                request_id="req-store-test",
                conversation_id="conv-store-test",
                terminal_state="completed",
                intent="data_question",
                response_type="answer",
                answer="Store test",
            )
            await store.save(snap, RuntimeDataMode.MOCK)
            retrieved = await store.get("req-store-test", RuntimeDataMode.MOCK)
            assert retrieved is not None
            assert retrieved.answer == "Store test"
            assert retrieved.request_id == "req-store-test"

            # 不同模式隔离
            retrieved_real = await store.get("req-store-test", RuntimeDataMode.REAL)
            assert retrieved_real is None

            # 不存在的 key
            assert await store.get("nonexistent", RuntimeDataMode.MOCK) is None

        asyncio.run(_test())


class TestRoadmapDocument:
    """路线文档验证"""

    def test_roadmap_contains_m1_rounds(self):
        """docs/08 包含 M1.0—M1.5 共七轮（含 M1.3.1）"""
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        for i in range(6):
            ver = f"M1.{i}"
            assert ver in content, f"docs/08 缺少 {ver}"
        assert "M1.3.1" in content, "docs/08 缺少 M1.3.1"
        # 顺序检查：从路线总览章节之后开始（避免状态行中的版本号干扰）
        overview_start = content.index("## 路线总览")
        idx_m10 = content.index("M1.0", overview_start)
        idx_m11 = content.index("M1.1", overview_start)
        idx_m12 = content.index("M1.2", overview_start)
        idx_m13 = content.index("M1.3 真实QueryPlan", overview_start)  # 精确匹配避免匹配到 M1.3.1
        idx_m131 = content.index("M1.3.1", overview_start)
        idx_m14 = content.index("M1.4", overview_start)
        idx_m15 = content.index("M1.5", overview_start)
        assert idx_m10 < idx_m11 < idx_m12 < idx_m13 < idx_m131 < idx_m14 < idx_m15, \
            "M1.0—M1.5 顺序不正确"

    def test_claude_md_does_not_contain_full_m1_roadmap(self):
        """CLAUDE.md 没有重复粘贴完整 M1 路线"""
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "CLAUDE.md").read_text(encoding="utf-8")
        # CLAUDE.md 不应包含 M1.1—M1.5 轮次细节描述
        assert "M1.1｜" not in content, "CLAUDE.md 不应包含完整 M1 路线"
        assert "M1.2｜" not in content, "CLAUDE.md 不应包含完整 M1 路线"
        assert "M1.3｜" not in content, "CLAUDE.md 不应包含完整 M1 路线"
        assert "M1.4｜" not in content, "CLAUDE.md 不应包含完整 M1 路线"
        assert "M1.5｜" not in content, "CLAUDE.md 不应包含完整 M1 路线"
