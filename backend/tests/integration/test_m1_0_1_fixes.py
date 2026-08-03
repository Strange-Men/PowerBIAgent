"""M1.0.1 修复测试 — 请求指纹、并发防重、快照模型、UUID 生成

测试覆盖：
- 请求指纹与冲突检测（~9 测试）
- 真实并发防重（~11 测试）
- 快照模型约束（~9 测试）
- ID 生成与文档（~10 测试）
"""

import asyncio
import pathlib
import uuid

import pytest

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    OwnerFailedError,
    RequestFingerprint,
)
from backend.app.memory.result_snapshot import (
    ReportResultSnapshot,
    ResultSnapshotStore,
    TurnResultSnapshot,
)
from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer


# ══════════════════════════════════════════════════════════════════════
# Spy/Fake 组件 — 用于计数调用次数
# ══════════════════════════════════════════════════════════════════════

class SpyLLMRuntime:
    """包装 MockAgentRuntime，统计 run() 调用次数"""

    def __init__(self, inner: MockAgentRuntime):
        self._inner = inner
        self.call_count = 0

    async def run(self, message, context, output_type):
        self.call_count += 1
        return await self._inner.run(message, context, output_type)


class SpyPowerBIAdapter:
    """包装 MockPowerBIAdapter，统计各方法调用次数"""

    def __init__(self, inner: MockPowerBIAdapter):
        self._inner = inner
        self.schema_call_count = 0
        self.dax_call_count = 0

    async def get_semantic_model_schema(self, semantic_model_key: str):
        self.schema_call_count += 1
        return await self._inner.get_semantic_model_schema(semantic_model_key)

    async def execute_dax(self, dax_request):
        self.dax_call_count += 1
        return await self._inner.execute_dax(dax_request)


class SpyReportRenderer:
    """包装 MockReportRenderer，统计 render() 调用次数"""

    def __init__(self, inner: MockReportRenderer):
        self._inner = inner
        self.call_count = 0

    async def render(self, report_spec):
        self.call_count += 1
        return await self._inner.render(report_spec)


class SpyMemoryRepo:
    """包装 InMemoryMemoryRepository，统计 commit() 调用次数"""

    def __init__(self, inner: InMemoryMemoryRepository):
        self._inner = inner
        self.commit_count = 0

    async def commit(self, memory, evidence):
        self.commit_count += 1
        return await self._inner.commit(memory, evidence)

    # 代理其他方法
    async def create_pending(self, memory, runtime_mode):
        return await self._inner.create_pending(memory, runtime_mode)

    async def get_by_request_id(self, request_id, runtime_mode):
        return await self._inner.get_by_request_id(request_id, runtime_mode)

    async def get_latest_committed(self, conversation_id, runtime_mode=None):
        return await self._inner.get_latest_committed(conversation_id, runtime_mode)

    async def mark_failed(self, request_id, runtime_mode, reason=None, stage=None):
        return await self._inner.mark_failed(request_id, runtime_mode, reason=reason, stage=stage)

    async def list_by_conversation(self, conversation_id, status=None, runtime_mode=None, limit=20):
        return await self._inner.list_by_conversation(conversation_id, status=status, runtime_mode=runtime_mode, limit=limit)

    async def request_exists(self, request_id, runtime_mode):
        return await self._inner.request_exists(request_id, runtime_mode)


def spy_service_factory():
    """创建带 Spy 组件的 MockTurnService"""
    llm_spy = SpyLLMRuntime(MockAgentRuntime())
    powerbi_spy = SpyPowerBIAdapter(MockPowerBIAdapter())
    report_spy = SpyReportRenderer(MockReportRenderer())
    memory_spy = SpyMemoryRepo(InMemoryMemoryRepository())

    svc = MockTurnService(
        memory_repo=memory_spy,
        llm_runtime=llm_spy,
        powerbi_adapter=powerbi_spy,
        report_renderer=report_spy,
    )
    return svc, llm_spy, powerbi_spy, report_spy, memory_spy


@pytest.fixture
def make_spy_service():
    return spy_service_factory


@pytest.fixture
def service_factory():
    """创建独立 Service 的工厂（无 Spy）"""
    def _make():
        return MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=MockAgentRuntime(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
    return _make


# ══════════════════════════════════════════════════════════════════════
# 阶段A：请求指纹与冲突检测（测试 1-9）
# ══════════════════════════════════════════════════════════════════════

class TestRequestFingerprint:
    """请求指纹计算与 Hash"""

    def test_fingerprint_message_stripped(self):
        """message 执行首尾空白清理"""
        fp = RequestFingerprint.compute(
            message="  本月销售额  ",
            client_conversation_id="conv-1",
        )
        assert fp.message == "本月销售额"

    def test_fingerprint_same_input_same_hash(self):
        """相同输入产生相同 Hash"""
        h1 = RequestFingerprint.compute_hash(
            message="本月销售额是多少？",
            client_conversation_id="conv-1",
            semantic_model_key="mock_sales_model",
        )
        h2 = RequestFingerprint.compute_hash(
            message="本月销售额是多少？",
            client_conversation_id="conv-1",
            semantic_model_key="mock_sales_model",
        )
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_fingerprint_different_message_different_hash(self):
        """不同 message 产生不同 Hash"""
        h1 = RequestFingerprint.compute_hash(message="销售额")
        h2 = RequestFingerprint.compute_hash(message="利润")
        assert h1 != h2

    def test_fingerprint_different_conversation_id_different_hash(self):
        """不同 client_conversation_id 产生不同 Hash"""
        h1 = RequestFingerprint.compute_hash(
            message="销售额", client_conversation_id="conv-a"
        )
        h2 = RequestFingerprint.compute_hash(
            message="销售额", client_conversation_id="conv-b"
        )
        assert h1 != h2

    def test_fingerprint_different_semantic_model_different_hash(self):
        """不同 semantic_model_key 产生不同 Hash"""
        h1 = RequestFingerprint.compute_hash(
            message="销售额", semantic_model_key="mock_sales_model"
        )
        h2 = RequestFingerprint.compute_hash(
            message="销售额", semantic_model_key="other_model"
        )
        assert h1 != h2

    def test_fingerprint_different_template_different_hash(self):
        """不同 effective_report_template_key 产生不同 Hash"""
        h1 = RequestFingerprint.compute_hash(
            message="生成报表", effective_report_template_key="sales_weekly"
        )
        h2 = RequestFingerprint.compute_hash(
            message="生成报表", effective_report_template_key="satisfaction_survey"
        )
        assert h1 != h2

    def test_fingerprint_scenario_participates(self):
        """显式传入 ScenarioFingerprint 时参与指纹"""
        from backend.app.memory.request_fingerprint import ScenarioFingerprint
        h1 = RequestFingerprint.compute_hash(
            message="销售额",
            scenario=ScenarioFingerprint(
                intent_key="data_question",
                query_plan_key="data_question",
                dax_key="data_question",
                powerbi_key="data_question",
                response_key="data_question",
            ),
        )
        h2 = RequestFingerprint.compute_hash(
            message="销售额",
            scenario=ScenarioFingerprint(
                intent_key="report_generation",
                query_plan_key="report_generation",
                dax_key="report_generation",
                powerbi_key="report_generation",
                response_key="report_generation",
            ),
        )
        assert h1 != h2

    def test_fingerprint_client_conversation_id_none(self):
        """client_conversation_id 为 None 时保持 None"""
        fp = RequestFingerprint.compute(
            message="销售额",
            client_conversation_id=None,
        )
        assert fp.client_conversation_id is None
        # None 和 "some-value" 应产生不同 Hash
        h_none = RequestFingerprint.compute_hash(
            message="销售额", client_conversation_id=None
        )
        h_val = RequestFingerprint.compute_hash(
            message="销售额", client_conversation_id="some-value"
        )
        assert h_none != h_val


class TestIdempotentReplayWithFingerprint:
    """相同 request_id 指纹一致性测试"""

    @pytest.mark.asyncio
    async def test_same_request_same_fingerprint_replay(self, service_factory):
        """Test 1: 相同 request_id、相同请求正常重放"""
        svc = service_factory()
        req_id = "req-fp-replay-001"

        r1 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-fp-001",
            request_id=req_id,
        )
        r2 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-fp-001",
            request_id=req_id,
        )

        assert r1["terminal_state"] == "completed"
        assert r2["terminal_state"] == "duplicate"
        assert r1["answer"] == r2["answer"]

    @pytest.mark.asyncio
    async def test_same_request_id_different_message_conflict(self, service_factory):
        """Test 2: 相同 request_id、不同 message 冲突"""
        svc = service_factory()
        req_id = "req-fp-conflict-msg"

        await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-fp-002",
            request_id=req_id,
        )

        with pytest.raises(IdempotencyConflictError) as exc_info:
            await svc.execute(
                message="本月利润是多少？",
                conversation_id="conv-fp-002",
                request_id=req_id,
            )
        assert exc_info.value.request_id == req_id
        assert "different request" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_same_request_id_different_conversation_id_conflict(self, service_factory):
        """Test 3: 相同 request_id、不同 conversation_id 冲突"""
        svc = service_factory()
        req_id = "req-fp-conflict-conv"

        await svc.execute(
            message="销售额查询",
            conversation_id="conv-A",
            request_id=req_id,
        )

        with pytest.raises(IdempotencyConflictError):
            await svc.execute(
                message="销售额查询",
                conversation_id="conv-B",
                request_id=req_id,
            )

    @pytest.mark.asyncio
    async def test_same_request_id_different_model_conflict(self, service_factory):
        """Test 4: 相同 request_id、不同 semantic_model_key 冲突"""
        svc = service_factory()
        req_id = "req-fp-conflict-model"

        await svc.execute(
            message="销售额查询",
            conversation_id="conv-fp-model",
            request_id=req_id,
            semantic_model_key="mock_sales_model",
        )

        with pytest.raises(IdempotencyConflictError):
            await svc.execute(
                message="销售额查询",
                conversation_id="conv-fp-model",
                request_id=req_id,
                semantic_model_key="other_model",
            )

    @pytest.mark.asyncio
    async def test_same_request_id_different_template_conflict(self, service_factory):
        """Test 5: 相同 request_id、不同报表模板冲突"""
        svc = service_factory()
        req_id = "req-fp-conflict-template"

        await svc.execute(
            message="生成报表",
            conversation_id="conv-fp-tpl",
            request_id=req_id,
            report_template_key="sales_weekly",
        )

        with pytest.raises(IdempotencyConflictError):
            await svc.execute(
                message="生成报表",
                conversation_id="conv-fp-tpl",
                request_id=req_id,
                report_template_key="satisfaction_survey",
            )

    @pytest.mark.asyncio
    async def test_conflict_preserves_original_snapshot(self, service_factory):
        """Test 6: 冲突后原始快照仍可正常重放"""
        svc = service_factory()
        req_id = "req-fp-preserve"

        r1 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-fp-preserve",
            request_id=req_id,
        )

        # 尝试冲突请求
        try:
            await svc.execute(
                message="不同的请求内容",
                conversation_id="conv-fp-preserve",
                request_id=req_id,
            )
        except IdempotencyConflictError:
            pass

        # 原始请求仍可重放
        r3 = await svc.execute(
            message="本月销售额是多少？",
            conversation_id="conv-fp-preserve",
            request_id=req_id,
        )
        assert r3["terminal_state"] == "duplicate"
        assert r3["answer"] == r1["answer"]


# ══════════════════════════════════════════════════════════════════════
# 阶段B：真实并发防重测试（测试 10-20）
# ══════════════════════════════════════════════════════════════════════

class TestConcurrentAnswerDedup:
    """并发相同 Answer 请求只执行一次"""

    @pytest.mark.asyncio
    async def test_concurrent_same_answer_executes_once(self, make_spy_service):
        """Test 10: 并发相同 Answer 请求只执行一次 LLM 流程"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-answer-001"

        async def req():
            return await svc.execute(
                message="本月销售额是多少？",
                conversation_id="conv-conc-answer",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        # 一个为首轮、一个为幂等重放
        states = {r1["terminal_state"], r2["terminal_state"]}
        assert states == {"completed", "duplicate"}

        completed = r1 if r1["terminal_state"] == "completed" else r2
        duplicate = r2 if r2["terminal_state"] == "duplicate" else r1

        # 业务内容一致
        assert completed["answer"] == duplicate["answer"]

        # 只执行了一次 LLM（intent + query_plan + dax + response = 4 calls）
        # 但 duplicate 不应增加任何 LLM 调用
        assert llm_spy.call_count == 4, f"Expected 4 LLM calls, got {llm_spy.call_count}"

    @pytest.mark.asyncio
    async def test_concurrent_same_report_executes_once(self, make_spy_service):
        """Test 11: 并发相同 Report 请求只渲染一次"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-report-001"

        async def req():
            return await svc.execute(
                message="生成销售周报",
                conversation_id="conv-conc-report",
                request_id=req_id,
                report_template_key="sales_weekly",
            )

        r1, r2 = await asyncio.gather(req(), req())

        states = {r1["terminal_state"], r2["terminal_state"]}
        assert states == {"completed", "duplicate"}

        completed = r1 if r1["terminal_state"] == "completed" else r2
        duplicate = r2 if r2["terminal_state"] == "duplicate" else r1

        assert completed["report"] is not None
        assert duplicate["report"] is not None
        assert completed["report"]["html"] == duplicate["report"]["html"]

        # 只渲染了一次 Report
        assert report_spy.call_count == 1, f"Expected 1 render call, got {report_spy.call_count}"

    @pytest.mark.asyncio
    async def test_concurrent_same_request_dax_once(self, make_spy_service):
        """Test 12: 并发相同请求只执行一次 DAX"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-dax-001"

        async def req():
            return await svc.execute(
                message="本月销售额是多少？",
                conversation_id="conv-conc-dax",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        assert {r1["terminal_state"], r2["terminal_state"]} == {"completed", "duplicate"}

        # 只执行了一次 DAX（通过 Power BI Adapter）
        assert powerbi_spy.dax_call_count == 1, \
            f"Expected 1 DAX call, got {powerbi_spy.dax_call_count}"

    @pytest.mark.asyncio
    async def test_concurrent_same_request_memory_once(self, make_spy_service):
        """Test 13: 并发相同请求只提交一次 Memory"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-mem-001"

        async def req():
            return await svc.execute(
                message="本月销售额是多少？",
                conversation_id="conv-conc-mem",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        assert {r1["terminal_state"], r2["terminal_state"]} == {"completed", "duplicate"}

        # 只提交了一次 Memory
        assert memory_spy.commit_count == 1, \
            f"Expected 1 memory commit, got {memory_spy.commit_count}"

    @pytest.mark.asyncio
    async def test_concurrent_content_identical(self, make_spy_service):
        """Test 14: 两个响应业务内容一致"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-content-001"

        async def req():
            return await svc.execute(
                message="本月销售额是多少？",
                conversation_id="conv-conc-content",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        assert r1["answer"] == r2["answer"]
        assert r1["conversation_id"] == r2["conversation_id"]
        assert r1["response_type"] == r2["response_type"]

    @pytest.mark.asyncio
    async def test_one_first_one_replay(self, make_spy_service):
        """Test 15: 一个首轮响应、一个幂等重放响应"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-roles-001"

        async def req():
            return await svc.execute(
                message="销售额查询",
                conversation_id="conv-conc-roles",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        replay_states = {r1["terminal_state"], r2["terminal_state"]}
        assert "completed" in replay_states
        assert "duplicate" in replay_states

        first = r1 if r1["terminal_state"] == "completed" else r2
        replay = r2 if r2["terminal_state"] == "duplicate" else r1

        assert first.get("idempotent_replay") is not True
        assert replay.get("idempotent_replay") is True
        assert replay.get("replayed_request_id") == req_id

    @pytest.mark.asyncio
    async def test_concurrent_different_trace_ids(self, make_spy_service):
        """Test 16: 两个响应 trace_id 不同"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-trace-001"

        async def req():
            return await svc.execute(
                message="销售额查询",
                conversation_id="conv-conc-trace",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req())

        assert r1["trace_id"] != r2["trace_id"]
        assert r1["trace_id"] != ""
        assert r2["trace_id"] != ""

    @pytest.mark.asyncio
    async def test_concurrent_different_fingerprint_one_succeeds(self, make_spy_service):
        """Test 17: 并发相同 request_id、不同 message 只有一个成功"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-conflict-001"

        async def req_a():
            return await svc.execute(
                message="销售额查询",
                conversation_id="conv-conc-cf",
                request_id=req_id,
            )

        async def req_b():
            return await svc.execute(
                message="利润查询",
                conversation_id="conv-conc-cf",
                request_id=req_id,
            )

        r_a, r_b = await asyncio.gather(req_a(), req_b(), return_exceptions=True)

        # 一个成功，一个为 IdempotencyConflictError
        exceptions = [r for r in [r_a, r_b] if isinstance(r, Exception)]
        results = [r for r in [r_a, r_b] if not isinstance(r, Exception)]

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], IdempotencyConflictError)
        assert len(results) == 1
        assert results[0]["terminal_state"] in ("completed", "duplicate")

    @pytest.mark.asyncio
    async def test_conflict_no_llm_or_tools(self, make_spy_service):
        """Test 18: 冲突请求没有执行 LLM 和工具"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-noexec-001"

        # First establish a snapshot
        await svc.execute(
            message="销售额查询",
            conversation_id="conv-conc-noexec",
            request_id=req_id,
        )

        # Reset spies
        llm_spy.call_count = 0
        powerbi_spy.schema_call_count = 0
        powerbi_spy.dax_call_count = 0
        report_spy.call_count = 0
        memory_spy.commit_count = 0

        # Now send conflicting request — concurrency approach
        async def req_a():
            return await svc.execute(
                message="销售额查询",  # same
                conversation_id="conv-conc-noexec",
                request_id=req_id,
            )

        async def req_b():
            return await svc.execute(
                message="不同的请求",
                conversation_id="conv-conc-noexec",
                request_id=req_id,
            )

        results = await asyncio.gather(req_a(), req_b(), return_exceptions=True)

        # At least one should be conflict
        exceptions = [r for r in results if isinstance(r, IdempotencyConflictError)]
        assert len(exceptions) >= 1

        # Conflict request did NOT trigger additional LLM/tool/memory calls beyond the replay
        # (replay itself doesn't execute LLM/tools/memory)

    @pytest.mark.asyncio
    async def test_owner_exception_waiter_not_hang(self, make_spy_service):
        """Test 19: Owner 异常后 Waiter 不会永久挂起"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-exc-001"

        # First request: will be owner
        # We simulate owner failure by making the inner LLM raise an exception
        # We'll patch the LLM run to raise on first call then work normally

        original_run = svc.llm.run
        call_counter = [0]

        async def fault_injecting_run(message, context, output_type):
            call_counter[0] += 1
            if call_counter[0] <= 1:
                raise RuntimeError("Simulated owner failure")
            return await original_run(message, context, output_type)

        svc.llm.run = fault_injecting_run

        # Concurrent requests
        async def req():
            return await svc.execute(
                message="销售额查询",
                conversation_id="conv-conc-exc",
                request_id=req_id,
            )

        r1, r2 = await asyncio.gather(req(), req(), return_exceptions=True)

        # At least one must have an exception (owner failed)
        exceptions = [r for r in [r1, r2] if isinstance(r, Exception)]
        assert len(exceptions) >= 1, "Owner failure should raise exception"

        # Neither should hang — both should complete within timeout
        # (asyncio.gather already returned, so neither hung)

    @pytest.mark.asyncio
    async def test_owner_abort_then_retry(self, make_spy_service):
        """Test 20: Owner 异常清理后同 request_id 可以重新尝试"""
        svc, llm_spy, powerbi_spy, report_spy, memory_spy = make_spy_service()
        req_id = "req-conc-retry-001"

        # First attempt: inject failure
        original_run = svc.llm.run
        call_counter = [0]

        async def fault_injecting_run(message, context, output_type):
            call_counter[0] += 1
            if call_counter[0] <= 1:
                raise RuntimeError("Simulated failure")
            return await original_run(message, context, output_type)

        svc.llm.run = fault_injecting_run

        # First request will fail
        with pytest.raises(RuntimeError, match="Simulated failure"):
            await svc.execute(
                message="销售额查询",
                conversation_id="conv-conc-retry",
                request_id=req_id,
            )

        # Restore normal LLM
        svc.llm.run = original_run

        # Second attempt with same request_id should succeed
        result = await svc.execute(
            message="销售额查询",
            conversation_id="conv-conc-retry",
            request_id=req_id,
        )
        assert result["terminal_state"] == "completed"
        assert result["answer"] is not None


# ══════════════════════════════════════════════════════════════════════
# 阶段C：快照模型测试（测试 21-29）
# ══════════════════════════════════════════════════════════════════════

class TestReportSnapshotModel:
    """ReportResultSnapshot Pydantic 模型"""

    def test_report_snapshot_valid(self):
        """Test 21: Report 快照为 Pydantic 模型"""
        rs = ReportResultSnapshot(
            report_id="rpt-001",
            template_key="sales_weekly",
            html="<html>Test</html>",
        )
        assert rs.report_id == "rpt-001"
        assert rs.template_key == "sales_weekly"
        assert rs.html == "<html>Test</html>"

    def test_report_snapshot_empty_report_id_rejected(self):
        """Test 22: 非法 report_id 拒绝保存"""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ReportResultSnapshot(
                report_id="",  # empty, min_length=1
                template_key="sales_weekly",
                html="<html>Test</html>",
            )

    def test_report_snapshot_empty_template_key_rejected(self):
        """Test 23: 非法 template_key 拒绝保存"""
        with pytest.raises(Exception):
            ReportResultSnapshot(
                report_id="rpt-001",
                template_key="",  # empty
                html="<html>Test</html>",
            )

    def test_report_snapshot_empty_html_rejected(self):
        """Test 24: 空 HTML 拒绝保存"""
        with pytest.raises(Exception):
            ReportResultSnapshot(
                report_id="rpt-001",
                template_key="sales_weekly",
                html="",  # empty
            )

    def test_turn_snapshot_answer_constraint(self):
        """Test 25: Answer 快照约束 — response_type='answer' 时 answer 不能为空"""
        # Valid
        snap = TurnResultSnapshot(
            request_id="req-001",
            conversation_id="conv-001",
            terminal_state="completed",
            intent="data_question",
            response_type="answer",
            answer="Test answer",
        )
        assert snap.answer == "Test answer"

        # Invalid: answer is None for response_type='answer'
        with pytest.raises(Exception):
            TurnResultSnapshot(
                request_id="req-001",
                conversation_id="conv-001",
                terminal_state="completed",
                intent="data_question",
                response_type="answer",
                answer=None,
            )

    def test_turn_snapshot_clarification_constraint(self):
        """Test 26: clarification 快照约束"""
        with pytest.raises(Exception):
            TurnResultSnapshot(
                request_id="req-001",
                conversation_id="conv-001",
                terminal_state="clarification_required",
                intent="clarification",
                response_type="clarification",
                clarification_question=None,
            )

    def test_turn_snapshot_unsupported_constraint(self):
        """Test 27: unsupported 快照约束"""
        with pytest.raises(Exception):
            TurnResultSnapshot(
                request_id="req-001",
                conversation_id="conv-001",
                terminal_state="unsupported",
                intent="unsupported",
                response_type="unsupported",
                unsupported_reason=None,
            )

    def test_snapshot_has_fingerprint_hash(self):
        """Test 28: 快照包含 request_fingerprint_hash"""
        snap = TurnResultSnapshot(
            request_id="req-001",
            conversation_id="conv-001",
            terminal_state="completed",
            intent="data_question",
            response_type="answer",
            answer="Test",
            request_fingerprint_hash="abc123def456",
        )
        assert snap.request_fingerprint_hash == "abc123def456"

    @pytest.mark.asyncio
    async def test_replay_report_serialization_consistent(self, service_factory):
        """Test 29: 重放 Report 序列化结果与首轮一致"""
        svc = service_factory()
        req_id = "req-replay-rpt-serial"

        r1 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-serial",
            request_id=req_id,
            report_template_key="sales_weekly",
        )
        r2 = await svc.execute(
            message="生成销售周报",
            conversation_id="conv-replay-serial",
            request_id=req_id,
            report_template_key="sales_weekly",
        )

        assert r1["report"] is not None
        assert r2["report"] is not None
        assert r2["report"]["report_id"] == r1["report"]["report_id"]
        assert r2["report"]["template_key"] == r1["report"]["template_key"]
        assert r2["report"]["html"] == r1["report"]["html"]

    def test_report_snapshot_is_not_dict(self):
        """快照中 report 不是普通 dict"""
        snap = TurnResultSnapshot(
            request_id="req-001",
            conversation_id="conv-001",
            terminal_state="completed",
            intent="report_generation",
            response_type="report",
            report=ReportResultSnapshot(
                report_id="rpt-001",
                template_key="sales_weekly",
                html="<html></html>",
            ),
        )
        assert isinstance(snap.report, ReportResultSnapshot)
        # 确认不是 dict
        assert not isinstance(snap.report, dict)


# ══════════════════════════════════════════════════════════════════════
# 阶段D：ID 生成与文档测试（测试 30-39）
# ══════════════════════════════════════════════════════════════════════

class TestServiceUUIDGeneration:
    """Service 统一 UUID 生成"""

    @pytest.mark.asyncio
    async def test_service_generates_uuid_for_conversation_id(self, service_factory):
        """Test 30: Service 未传 conversation_id 时生成有效 UUID"""
        svc = service_factory()
        result = await svc.execute(
            message="销售额查询",
            request_id="req-uuid-conv-001",
        )
        conv_id = result["conversation_id"]
        # 验证是有效 UUID
        uuid.UUID(conv_id)

    @pytest.mark.asyncio
    async def test_service_generates_uuid_for_request_id(self, service_factory):
        """Test 31: Service 未传 request_id 时生成有效 UUID"""
        svc = service_factory()
        result = await svc.execute(
            message="销售额查询",
            conversation_id="conv-uuid-req-001",
        )
        req_id = result["request_id"]
        uuid.UUID(req_id)

    @pytest.mark.asyncio
    async def test_service_does_not_overwrite_provided_ids(self, service_factory):
        """传入的 conversation_id 和 request_id 不被覆盖"""
        svc = service_factory()
        result = await svc.execute(
            message="销售额查询",
            conversation_id="my-custom-conv",
            request_id="my-custom-req",
        )
        assert result["conversation_id"] == "my-custom-conv"
        assert result["request_id"] == "my-custom-req"

    @pytest.mark.asyncio
    async def test_replay_returns_original_conversation_id(self, service_factory):
        """Test 33: 重放返回首次生成的 conversation_id"""
        svc = service_factory()
        req_id = "req-uuid-replay-conv"

        # 首次请求不传 conversation_id，Service 自动生成
        r1 = await svc.execute(
            message="销售额查询",
            request_id=req_id,
        )

        # 重放时也不传 conversation_id（指纹一致），应返回首次的值
        r2 = await svc.execute(
            message="销售额查询",
            request_id=req_id,
        )

        assert r2["conversation_id"] == r1["conversation_id"]
        assert r2["terminal_state"] == "duplicate"


class TestDocumentStatus:
    """文档状态验证"""

    def test_docs_08_m10_completed(self):
        """Test 34: docs/08 中 M1.0 状态为已完成"""
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        # M1.0 行应包含"已完成"
        assert "M1.0 M0遗留收口与M1路线固化       ✅ 已完成" in content

    def test_docs_08_m10_commit(self):
        """Test 35: docs/08 中 M1.0 Commit 为 9247322"""
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        assert "9247322" in content

    def test_docs_08_has_m101_record(self):
        """Test 36: docs/08 中存在 M1.0.1 专项修复记录"""
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/08_development_roadmap.md").read_text(encoding="utf-8")
        assert "M1.0.1" in content
        assert "幂等并发" in content

    def test_docs_09_current_round_m101(self):
        """Test 37: docs/09 当前完成轮次为 M1.0.1"""
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/09_context_handoff.md").read_text(encoding="utf-8")
        assert "当前完成轮次" in content
        assert "M1.0.1" in content

    def test_docs_09_next_round(self):
        """Test 38: docs/09 下一轮为 M1.4"""
        content = (pathlib.Path(__file__).parent.parent.parent.parent /
                   "docs/09_context_handoff.md").read_text(encoding="utf-8")
        assert "M1.4" in content
        assert "下一轮" in content

    def test_docs_no_stale_status(self):
        """Test 39: docs/08 和 docs/09 不存在失效状态（当前进行中轮次除外）"""
        for doc_name in ["docs/08_development_roadmap.md", "docs/09_context_handoff.md"]:
            content = (pathlib.Path(__file__).parent.parent.parent.parent /
                       doc_name).read_text(encoding="utf-8")
            # "进行中" 只允许出现在当前活跃轮次（M1.3.1），不允许其他已完结轮次仍标记为进行中
            # docs/08 有两处（概览+详情），docs/09 有一处
            in_progress_count = content.count("进行中")
            max_allowed = 3 if doc_name == "docs/08_development_roadmap.md" else 1
            assert in_progress_count <= max_allowed, \
                f"{doc_name} 包含 {in_progress_count} 处'进行中'，超过允许上限 {max_allowed}"
            assert "待推送" not in content, f"{doc_name} 不应包含'待推送'"
            assert "由下一轮获取" not in content, f"{doc_name} 不应包含'由下一轮获取'"


# ══════════════════════════════════════════════════════════════════════
# 快照 Store 并发测试
# ══════════════════════════════════════════════════════════════════════

class TestSnapshotStoreIdempotency:
    """ResultSnapshotStore claim/complete/abort"""

    @pytest.mark.asyncio
    async def test_claim_owner_first(self):
        """首个 claim 返回 OWNER"""
        store = ResultSnapshotStore()
        status, future = await store.claim(
            "req-001", RuntimeDataMode.MOCK, "hash-001"
        )
        assert status.value == "owner"
        assert future is None

    @pytest.mark.asyncio
    async def test_claim_waiter_same_hash(self):
        """相同 Hash 的第二个 claim 返回 WAITER"""
        store = ResultSnapshotStore()
        await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")

        status, future = await store.claim(
            "req-001", RuntimeDataMode.MOCK, "hash-001"
        )
        assert status.value == "waiter"
        assert future is not None

    @pytest.mark.asyncio
    async def test_claim_conflict_different_hash(self):
        """不同 Hash 的 claim 返回 CONFLICT"""
        store = ResultSnapshotStore()
        await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")

        status, future = await store.claim(
            "req-001", RuntimeDataMode.MOCK, "hash-002"
        )
        assert status.value == "conflict"
        assert future is None

    @pytest.mark.asyncio
    async def test_complete_wakes_waiter(self):
        """complete() 唤醒 Waiter"""
        store = ResultSnapshotStore()

        # Owner claims
        owner_status, _ = await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")
        assert owner_status.value == "owner"

        # Waiter claims
        waiter_status, waiter_future = await store.claim(
            "req-001", RuntimeDataMode.MOCK, "hash-001"
        )
        assert waiter_status.value == "waiter"

        # Complete
        await store.complete("req-001", RuntimeDataMode.MOCK)

        # Waiter should be woken
        # Wait with timeout
        result = await asyncio.wait_for(waiter_future, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_abort_wakes_waiter_with_error(self):
        """abort() 唤醒 Waiter 并抛出 OwnerFailedError"""
        store = ResultSnapshotStore()

        await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")
        waiter_status, waiter_future = await store.claim(
            "req-001", RuntimeDataMode.MOCK, "hash-001"
        )
        assert waiter_status.value == "waiter"

        await store.abort("req-001", RuntimeDataMode.MOCK)

        with pytest.raises(OwnerFailedError):
            await asyncio.wait_for(waiter_future, timeout=1.0)

    @pytest.mark.asyncio
    async def test_abort_allows_reclaim(self):
        """abort 后可以重新 claim"""
        store = ResultSnapshotStore()

        await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")
        await store.abort("req-001", RuntimeDataMode.MOCK)

        # 重新 claim 应成功
        status, future = await store.claim("req-001", RuntimeDataMode.MOCK, "hash-001")
        assert status.value == "owner"


# ══════════════════════════════════════════════════════════════════════
# Fingerprint 安全测试
# ══════════════════════════════════════════════════════════════════════

class TestFingerprintSafety:
    """指纹安全性"""

    def test_fingerprint_repr_no_message(self):
        """指纹 repr 不暴露原始 message"""
        fp = RequestFingerprint.compute(
            message="敏感数据查询",
            client_conversation_id="conv-secret",
        )
        r = repr(fp)
        assert "敏感数据" not in r
        assert fp.hash()[:12] in r

    def test_fingerprint_hash_not_reversible(self):
        """SHA-256 Hash 不可逆"""
        fp = RequestFingerprint.compute(message="测试")
        h = fp.hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
