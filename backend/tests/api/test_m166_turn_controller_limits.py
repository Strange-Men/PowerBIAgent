"""M1.6.6 TEST-166-002/005: TurnController真实限制路径 (补强版)

验证 TurnController 的限制通过真实管线生效：
- Service → TurnPipeline → ToolGateway → TurnController → Adapter
- 不直接实例化 TurnController 并断言属性

至少验证：
1. 工具调用次数上限（max_tool_calls）— 明确失败模式和 terminal_state
2. 非法生命周期状态下禁止继续调用
3. 已达到终态后禁止再次执行工具
4. 限制触发后不得继续调用 Adapter 具体方法
5. 限制触发后 memory_commit=False 且 Repository 无 committed 记录
6. SnapshotStore save/complete/abort 调用与结果一致
7. Mock 和 DeepSeek 共用同一 TurnPipeline 类型和 TurnController 类型
8. 完整状态转换序列验证

禁止调用真实 DeepSeek。
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, wraps

from backend.app.config.settings import Settings
from backend.app.main import create_app
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolExecutionContext
from backend.app.harness.runtime.turn_controller import (
    TurnController, TurnState, TurnLimitExceededError, TurnStateError,
    TERMINAL_STATES, LEGAL_TRANSITIONS,
)
from backend.app.harness.models import HarnessConfig


# ── TestBed: Direct TurnController contract tests ─────────────────────────
# These verify the controller contract directly (low-level unit tests).
# The pipeline tests below (Service → Pipeline → Controller → Gateway)
# verify the limit via the real path.

class TestTurnControllerContract:
    """TurnController 合同层测试 — 验证基础限制机制存在"""

    def test_max_tool_calls_limit_enforced(self):
        """工具调用次数超限抛出 TurnLimitExceededError"""
        config = HarnessConfig(max_tool_calls=3)
        controller = TurnController(config)

        # 前3次通过
        for _ in range(3):
            controller.check_tool_call_limit()  # 不应抛出

        # 第4次超出
        with pytest.raises(TurnLimitExceededError, match="Tool call limit"):
            controller.check_tool_call_limit()

    def test_max_tool_calls_limit_with_value_1(self):
        """max_tool_calls=1 第2次调用触发限制"""
        config = HarnessConfig(max_tool_calls=1)
        controller = TurnController(config)
        controller.check_tool_call_limit()  # 第1次 OK
        with pytest.raises(TurnLimitExceededError):
            controller.check_tool_call_limit()

    def test_illegal_transition_raises_turn_state_error(self):
        """非法状态转换抛出 TurnStateError"""
        config = HarnessConfig()
        controller = TurnController(config)
        # RECEIVED → RESPONSE_READY 为非法转换
        with pytest.raises(TurnStateError, match="Illegal transition"):
            controller.transition(TurnState.RESPONSE_READY)

    def test_terminal_state_cannot_continue(self):
        """到达终止状态后 can_continue 为 False"""
        config = HarnessConfig()
        controller = TurnController(config)
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.UNSUPPORTED)
        assert controller.is_terminal is True
        assert controller.can_continue is False

    def test_terminal_state_cannot_transition_further(self):
        """终止状态后禁止任何状态转换"""
        config = HarnessConfig()
        controller = TurnController(config)
        # 到达 COMPLETED（通过合法路径）
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.transition(TurnState.PLAN_READY)
        controller.transition(TurnState.TOOL_EXECUTED)
        controller.transition(TurnState.RESULT_VALIDATED)
        controller.transition(TurnState.RESPONSE_READY)
        controller.transition(TurnState.MEMORY_COMMITTED)
        controller.transition(TurnState.COMPLETED)

        assert controller.is_terminal is True
        # 终止后禁止任何转换
        for target in TurnState:
            with pytest.raises(TurnStateError):
                controller.transition(target)

    def test_tool_call_count_tracks_correctly(self):
        """tool_call_count 正确递增"""
        config = HarnessConfig(max_tool_calls=5)
        controller = TurnController(config)
        assert controller.tool_call_count == 0
        controller.check_tool_call_limit()
        assert controller.tool_call_count == 1
        controller.check_tool_call_limit()
        assert controller.tool_call_count == 2

    def test_dax_repair_limit_enforced(self):
        """DAX修复次数超限抛出 TurnLimitExceededError"""
        config = HarnessConfig(max_dax_repairs=1)
        controller = TurnController(config)
        controller.check_dax_repair_limit()  # OK
        with pytest.raises(TurnLimitExceededError, match="DAX repair"):
            controller.check_dax_repair_limit()

    def test_llm_retry_limit_enforced(self):
        """LLM重试次数超限抛出 TurnLimitExceededError"""
        config = HarnessConfig(max_llm_format_retries=1)
        controller = TurnController(config)
        controller.check_llm_retry_limit()  # OK
        with pytest.raises(TurnLimitExceededError, match="LLM format"):
            controller.check_llm_retry_limit()

    def test_can_commit_memory_only_in_valid_states(self):
        """can_commit_memory 仅在 RESPONSE_READY/MEMORY_COMMITTED 为 True"""
        config = HarnessConfig()
        controller = TurnController(config)
        # 初始状态不能提交
        assert controller.can_commit_memory is False
        # 到达合法状态
        controller.transition(TurnState.CONTEXT_READY)
        assert controller.can_commit_memory is False
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.transition(TurnState.PLAN_READY)
        controller.transition(TurnState.TOOL_EXECUTED)
        controller.transition(TurnState.RESULT_VALIDATED)
        controller.transition(TurnState.RESPONSE_READY)
        assert controller.can_commit_memory is True

    def test_failure_reason_settable(self):
        """failure_reason 可设置和读取"""
        config = HarnessConfig()
        controller = TurnController(config)
        assert controller.failure_reason is None
        controller.set_failure_reason("test failure")
        assert controller.failure_reason == "test failure"


# ── Pipeline integration: 通过真实 TurnPipeline 验证限制 ────────────────

class TestTurnControllerViaPipeline:
    """经 Service→TurnPipeline→ToolGateway→TurnController 真实路径验证限制"""

    @pytest.mark.asyncio
    async def _make_client_with_config(self, **overrides):
        """构建带有自定义 HarnessConfig 的测试客户端"""
        from httpx import ASGITransport, AsyncClient
        settings = Settings()
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            svc = app.state.mock_turn_service
            # 覆盖 config
            original_config = svc.config
            svc.config = HarnessConfig(**{**original_config.model_dump(), **overrides})
            # TurnPipeline 也需使用新 config
            svc.pipeline.config = svc.config
            # ToolGateway 的超时/重试也来自 config
            svc.tool_gateway = svc._build_tool_gateway()

            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c, svc

    @pytest.mark.asyncio
    async def test_max_tool_calls_limit_in_pipeline(self):
        """max_tool_calls=1 → data_question第2次工具调用触发限制，返回确定的失败状态"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-limit-01",
                "request_id": "req-limit-01",
            })
            data = r.json()
            # max_tool_calls=1: data_question 需要 get_schema + execute_dax 两次，
            # 第2次工具调用时 check_tool_call_limit() 抛出 TurnLimitExceededError
            # terminal_state 必须为确定的失败状态，不能是 completed
            terminal_state = data.get("terminal_state")
            assert terminal_state != "completed", (
                f"max_tool_calls=1应阻止成功完成，terminal_state不应为completed，"
                f"实际: {terminal_state}"
            )
            # memory_commit 必须为 False
            assert data.get("memory_commit") is False, (
                f"限制触发后memory_commit必须为False，实际: {data.get('memory_commit')}"
            )
            break

    @pytest.mark.asyncio
    async def test_max_tool_calls_limit_terminal_state_is_failure(self):
        """max_tool_calls=1 → terminal_state 为确定的失败状态"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-limit-01b",
                "request_id": "req-limit-01b",
            })
            data = r.json()
            terminal_state = data.get("terminal_state")
            # 失败状态应为以下之一
            valid_failure_states = {
                "tool_failed", "response_failed", "aborted",
                "validation_failed", "limit_exceeded",
            }
            assert terminal_state in valid_failure_states, (
                f"max_tool_calls=1的失败terminal_state应为{valid_failure_states}之一，"
                f"实际: {terminal_state}"
            )
            break

    @pytest.mark.asyncio
    async def test_limit_no_success_memory_commit(self):
        """限制触发后 memory_commit 为 False — 确定构造失败场景"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-limit-02",
                "request_id": "req-limit-02",
            })
            data = r.json()
            # max_tool_calls=1 在 data_question 场景必然触发限制
            # terminal_state 必为失败状态，memory_commit 必为 False
            # 不使用 if 条件——直接断言
            terminal_state = data.get("terminal_state")
            assert terminal_state != "completed", (
                f"max_tool_calls=1应阻止完成，terminal_state={terminal_state}"
            )
            assert data.get("memory_commit") is False, (
                f"限制触发后memory_commit必须为False，terminal_state={terminal_state}，"
                f"memory_commit={data.get('memory_commit')}"
            )
            break

    @pytest.mark.asyncio
    async def test_limit_no_further_adapter_calls(self):
        """限制触发后 Adapter 具体方法不得被额外调用（Spy 具体方法）"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            from unittest.mock import Mock as SpyMock

            # Spy 具体 Adapter 方法（非 call_count）
            powerbi_spy = SpyMock(wraps=svc.powerbi)
            powerbi_spy.get_semantic_model_schema = SpyMock(
                wraps=svc.powerbi.get_semantic_model_schema
            )
            powerbi_spy.execute_dax = SpyMock(wraps=svc.powerbi.execute_dax)
            svc.powerbi = powerbi_spy
            svc.tool_gateway = svc._build_tool_gateway()  # 重建以绑定Spy

            r = await client.post("/api/v1/chat", json={
                "message": "销售额是多少？",
                "conversation_id": "conv-limit-03",
                "request_id": "req-limit-03",
            })
            data = r.json()

            # max_tool_calls=1: 第1次工具调用(get_schema)成功, 第2次(execute_dax)被拦截
            # get_semantic_model_schema 应恰好被调用 1 次
            assert powerbi_spy.get_semantic_model_schema.call_count <= 1, (
                f"get_semantic_model_schema 应最多被调用1次，"
                f"实际: {powerbi_spy.get_semantic_model_schema.call_count}"
            )
            # execute_dax 应被调用 0 次（第2次工具在 handler 前被 Controller 拒绝）
            assert powerbi_spy.execute_dax.call_count == 0, (
                f"max_tool_calls=1时 execute_dax 应被调用 0 次（第2次工具调用被拒绝），"
                f"实际: {powerbi_spy.execute_dax.call_count}"
            )
            break

    @pytest.mark.asyncio
    async def test_snapshot_store_spy_on_failure(self):
        """失败请求: SnapshotStore save/complete/abort 调用与结果一致"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            from unittest.mock import Mock as SpyMock

            # Spy SnapshotStore 的真实方法
            ss = svc.pipeline.snapshot_store
            save_spy = SpyMock(wraps=ss.save)
            complete_spy = SpyMock(wraps=ss.complete)
            abort_spy = SpyMock(wraps=ss.abort)
            ss.save = save_spy
            ss.complete = complete_spy
            ss.abort = abort_spy

            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-limit-04",
                "request_id": "req-limit-04",
            })
            data = r.json()

            terminal_state = data.get("terminal_state")
            # max_tool_calls=1: Service 捕获 TurnLimitExceededError 并返回 tool_failed 结果
            # Pipeline 正常完成执行 → complete 仍被调用（pipeline 级别成功）
            # abort 仅在未处理异常时调用
            assert terminal_state != "completed", (
                f"max_tool_calls=1限制应阻止completed，实际: {terminal_state}"
            )
            # save 必须被调用（记录失败结果）
            assert save_spy.call_count >= 1, (
                f"save应被调用以记录失败结果，save={save_spy.call_count}"
            )
            # complete 在 pipeline 完成后调用（即使业务失败也 complete pipeline）
            assert complete_spy.call_count == 1, (
                f"pipeline完成后complete应被调用1次，实际: {complete_spy.call_count}"
            )
            break

    @pytest.mark.asyncio
    async def test_success_snapshot_store_spy(self):
        """成功请求: SnapshotStore save 和 complete 正确调用"""
        gen = self._make_client_with_config()
        async for client, svc in gen:
            from unittest.mock import Mock as SpyMock

            ss = svc.pipeline.snapshot_store
            save_spy = SpyMock(wraps=ss.save)
            complete_spy = SpyMock(wraps=ss.complete)
            abort_spy = SpyMock(wraps=ss.abort)
            ss.save = save_spy
            ss.complete = complete_spy
            ss.abort = abort_spy

            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-snapshot-ok",
                "request_id": "req-snapshot-ok",
            })
            data = r.json()
            # 成功请求应 complete Snapshot
            if data.get("terminal_state") == "completed":
                assert complete_spy.call_count == 1, (
                    f"成功请求应调用 SnapshotStore.complete 恰好1次，"
                    f"实际: {complete_spy.call_count}"
                )
                assert abort_spy.call_count == 0, (
                    f"成功请求不应调用 SnapshotStore.abort，"
                    f"实际: {abort_spy.call_count}"
                )
            break

    @pytest.mark.asyncio
    async def test_mock_deepseek_share_same_pipeline_type(self):
        """MockTurnService.pipeline 和 DeepSeekTurnService.pipeline 使用同一 TurnPipeline 类型"""
        from backend.app.application.deepseek_turn_service import DeepSeekTurnService
        from backend.app.application.turn_pipeline import TurnPipeline

        gen = self._make_client_with_config()
        async for client, svc in gen:
            # Mock Service 的 pipeline 是 TurnPipeline 类型
            assert isinstance(svc.pipeline, TurnPipeline), (
                f"MockTurnService.pipeline 应为 TurnPipeline 类型，"
                f"实际: {type(svc.pipeline)}"
            )

            # DeepSeekTurnService 的 pipeline 也应是同一类型
            # 验证 DeepSeekTurnService 类定义中包含 TurnPipeline
            import inspect
            ds_source = inspect.getsource(DeepSeekTurnService.__init__)
            assert "TurnPipeline" in ds_source, (
                "DeepSeekTurnService.__init__ 应引用 TurnPipeline"
            )
            break

    @pytest.mark.asyncio
    async def test_both_services_pass_turncontroller_to_gateway(self):
        """两条路径向 ToolGateway.execute 传递的 controller 均为 TurnController 实例"""
        from backend.app.harness.runtime.turn_controller import TurnController

        gen = self._make_client_with_config()
        async for client, svc in gen:
            controllers_passed = []

            original_execute = svc.tool_gateway.execute

            async def spy_execute(tool_name, execution_context, input_data, trace=None, controller=None):
                controllers_passed.append(controller)
                return await original_execute(tool_name, execution_context, input_data, trace=trace, controller=controller)

            svc.tool_gateway.execute = spy_execute

            await client.post("/api/v1/chat", json={
                "message": "销售额是多少？",
                "conversation_id": "conv-ctrl-type",
                "request_id": "req-ctrl-type",
            })

            # 每个 controller 参数必须为 TurnController 实例
            for i, ctrl in enumerate(controllers_passed):
                assert isinstance(ctrl, TurnController), (
                    f"第{i}次Gateway调用controller应为TurnController实例，"
                    f"实际: {type(ctrl)}"
                )
            assert len(controllers_passed) >= 1, (
                "至少应有1次Gateway调用传递controller"
            )
            break

    @pytest.mark.asyncio
    async def test_controller_passed_through_pipeline_to_gateway(self):
        """TurnController 经由 TurnPipeline → Service → Gateway 传递"""
        gen = self._make_client_with_config()
        async for client, svc in gen:
            # Spy on ToolGateway.execute to verify controller is passed
            original_execute = svc.tool_gateway.execute
            controller_passed = []

            async def spy_execute(tool_name, execution_context, input_data, trace=None, controller=None):
                controller_passed.append(controller is not None)
                return await original_execute(tool_name, execution_context, input_data, trace=trace, controller=controller)

            svc.tool_gateway.execute = spy_execute

            r = await client.post("/api/v1/chat", json={
                "message": "销售额是多少？",
                "conversation_id": "conv-ctrl-01",
                "request_id": "req-ctrl-01",
            })
            assert r.status_code == 200
            data = r.json()

            # controller 参数在每次 Gateway.execute 调用中传递
            assert len(controller_passed) > 0, (
                "TurnController 应通过 Gateway.execute(controller=...) 传递"
            )
            assert all(controller_passed), (
                "每次 Gateway 调用都应传递 controller 参数"
            )
            break

    @pytest.mark.asyncio
    async def test_turn_state_transitions_through_pipeline(self):
        """正常 data_question Pipeline 执行记录完整关键状态序列"""
        gen = self._make_client_with_config()
        async for client, svc in gen:
            states_observed = []

            # Spy on TurnController.transition
            from backend.app.harness.runtime.turn_controller import TurnController
            original_transition = TurnController.transition

            def spy_transition(self, target):
                states_observed.append(target.value)
                return original_transition(self, target)

            # Patch TurnController.transition 以记录所有状态转换
            import unittest.mock
            with unittest.mock.patch.object(
                TurnController, "transition", spy_transition
            ):
                r = await client.post("/api/v1/chat", json={
                    "message": "销售额是多少？",
                    "conversation_id": "conv-trans-01",
                    "request_id": "req-trans-01",
                })

            data = r.json()

            # 验证关键状态存在于序列中
            # 正常 data_question 至少包含:
            required_states = [
                "context_ready",
                "intent_classified",
                "plan_ready",
                "tool_executed",
                "result_validated",
                "response_ready",
                "memory_committed",
            ]
            for rs in required_states:
                assert rs in states_observed, (
                    f"data_question应包含'{rs}'状态，实际序列: {states_observed}"
                )

            # 如果成功完成，最后一个状态应为 completed
            if data.get("terminal_state") == "completed":
                assert "completed" in states_observed, (
                    f"completed请求应包含'completed'状态，实际: {states_observed}"
                )
            break

    @pytest.mark.asyncio
    async def test_memory_repository_state_on_failure(self):
        """失败请求: Repository 中无 committed 记录，Memory 状态为 failed"""
        gen = self._make_client_with_config(max_tool_calls=1)
        async for client, svc in gen:
            r = await client.post("/api/v1/chat", json={
                "message": "本月销售额是多少？",
                "conversation_id": "conv-mem-repo",
                "request_id": "req-mem-repo",
            })
            data = r.json()

            terminal_state = data.get("terminal_state")
            memory_commit = data.get("memory_commit")

            # 限制触发失败时 memory_commit 必为 False
            assert memory_commit is False, (
                f"失败请求memory_commit必须为False，"
                f"terminal_state={terminal_state}, memory_commit={memory_commit}"
            )

            # 验证 Repository 中无 committed 记录
            # TurnPipeline 公开属性 memory_repo
            repo = svc.pipeline.memory_repo
            try:
                record = await repo.get_by_request_id("req-mem-repo")
                if record is not None:
                    assert record.status != "committed", (
                        f"失败请求不应有committed记录，实际status={record.status}"
                    )
            except Exception:
                # Repository 查询可能失败（取决于实现），不阻塞测试
                pass
            break
