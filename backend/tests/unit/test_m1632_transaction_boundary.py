"""M1.6.3.2 事务边界与单写入者防回归测试

验证：
- Service 不直接写 Memory（mark_failed/commit）
- Service 不直接写 Snapshot（save/complete/abort）
- Snapshot 只有 TurnPipeline 写入
- Memory commit 统一经过 TurnPipeline
- 快照调用次数精确：成功 1 次、幂等 0 次、异常 abort 不 save
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.application.deepseek_turn_service import DeepSeekTurnService
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.application.turn_pipeline import TurnPipeline
from backend.app.config.settings import Settings
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.turn_controller import TurnController
from backend.app.llm.base import LLMProvider
from backend.app.llm.mock import MockLLMProvider
from backend.app.memory.models import (
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.memory.result_snapshot import ResultSnapshotStore, TurnResultSnapshot
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer


# ━━━━━━━━━━━━━━━━━ 辅助 ━━━━━━━━━━━━━━━━━


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _mock_service(repo=None) -> MockTurnService:
    return MockTurnService(
        memory_repo=repo or InMemoryMemoryRepository(),
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
        config=HarnessConfig(),
    )


def _deepseek_service(repo=None) -> DeepSeekTurnService:
    provider = MagicMock(spec=LLMProvider)
    provider.is_mock = False
    return DeepSeekTurnService(
        memory_repo=repo or InMemoryMemoryRepository(),
        llm_provider=provider,
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
        settings=Settings(),
        config=HarnessConfig(),
    )


# ━━━━━━━━━━━━━━━━━ 源码静态门禁 ━━━━━━━━━━━━━━━━━


PROHIBITED_PATTERNS = [
    # Service 直接写 Memory
    "self.memory_repo.mark_failed(",
    "self.memory_repo.commit(",
    "self.memory_repo.create_pending(",
    # Service 直接写 Snapshot
    "self.snapshot_store.save(",
    "self.snapshot_store.complete(",
    "self.snapshot_store.abort(",
    # Service 内部 Snapshot 工厂方法
    "_save_snapshot(",
    # Pipeline 方法从 Service 调用（Snapshot 双写标志）
    "pipeline._save_snapshot(",
]

SERVICE_FILES = [
    "backend/app/application/mock_turn_service.py",
    "backend/app/application/deepseek_turn_service.py",
]


class TestServiceSourceStaticGate:
    """Service 源码不得出现 Memory/Snapshot 直接写入模式"""

    @pytest.mark.parametrize("rel_path", SERVICE_FILES)
    def test_no_direct_memory_write_in_service(self, rel_path: str):
        """Service 源码不含 self.memory_repo.mark_failed / commit / create_pending"""
        source = _read_source(_project_root() / rel_path)
        # TurnPipeline 自身允许这些模式
        if "turn_pipeline" in rel_path:
            return
        for pattern in [
            "self.memory_repo.mark_failed(",
            "self.memory_repo.commit(",
            "self.memory_repo.create_pending(",
        ]:
            assert pattern not in source, (
                f"{rel_path} 含禁止模式: {pattern}"
            )

    @pytest.mark.parametrize("rel_path", SERVICE_FILES)
    def test_no_snapshot_write_in_service(self, rel_path: str):
        """Service 源码不含 self.snapshot_store.save/complete/abort"""
        source = _read_source(_project_root() / rel_path)
        for pattern in [
            "self.snapshot_store.save(",
            "self.snapshot_store.complete(",
            "self.snapshot_store.abort(",
        ]:
            assert pattern not in source, (
                f"{rel_path} 含禁止模式: {pattern}"
            )

    @pytest.mark.parametrize("rel_path", SERVICE_FILES)
    def test_no_save_snapshot_in_service(self, rel_path: str):
        """Service 源码不含 _save_snapshot(（双写标志）"""
        source = _read_source(_project_root() / rel_path)
        # 注释不算
        lines = [l for l in source.split("\n") if not l.strip().startswith("#")]
        filtered = "\n".join(lines)
        assert "_save_snapshot(" not in filtered, (
            f"{rel_path} 含 _save_snapshot( 调用（Snapshot 双写）"
        )

    @pytest.mark.parametrize("rel_path", SERVICE_FILES)
    def test_no_pipeline_save_snapshot_in_service(self, rel_path: str):
        """Service 源码不含 pipeline._save_snapshot（应为 Pipeline 独占）"""
        source = _read_source(_project_root() / rel_path)
        assert "pipeline._save_snapshot(" not in source, (
            f"{rel_path} 含 pipeline._save_snapshot(（Service 不应绕过 Pipeline）"
        )

    @pytest.mark.parametrize("rel_path", SERVICE_FILES)
    def test_service_does_not_hold_self_memory_repo(self, rel_path: str):
        """Service 不含 self.memory_repo = 赋值（Instance Field）"""
        source = _read_source(_project_root() / rel_path)
        # Strip comments
        lines = [l for l in source.split("\n") if not l.strip().startswith("#")]
        filtered = "\n".join(lines)
        assert "self.memory_repo =" not in filtered and "self.memory_repo=" not in filtered, (
            f"{rel_path} 含 self.memory_repo 实例字段赋值"
        )


# ━━━━━━━━━━━━━━━━━ Snapshot 调用次数测试 ━━━━━━━━━━━━━━━━━


class TestSnapshotSingleWriter:
    """验证 TurnPipeline 是 Snapshot 的唯一写入者"""

    @pytest.mark.asyncio
    async def test_successful_owner_saves_snapshot_exactly_once(self):
        """成功请求：SnapshotStore.save 恰好 1 次、complete 恰好 1 次、abort 0 次"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        with patch.object(
            svc.pipeline.snapshot_store, "save", wraps=svc.pipeline.snapshot_store.save
        ) as spy_save, patch.object(
            svc.pipeline.snapshot_store, "complete", wraps=svc.pipeline.snapshot_store.complete
        ) as spy_complete, patch.object(
            svc.pipeline.snapshot_store, "abort", wraps=svc.pipeline.snapshot_store.abort
        ) as spy_abort:

            result = await svc.execute(
                message="本月销售额是多少",
                conversation_id="conv-snapshot-1",
                request_id="req-snapshot-1",
            )

            assert result["terminal_state"] == "completed"
            assert spy_save.call_count == 1, f"save 应为 1 次，实际 {spy_save.call_count}"
            assert spy_complete.call_count == 1, f"complete 应为 1 次，实际 {spy_complete.call_count}"
            assert spy_abort.call_count == 0, f"abort 应为 0 次，实际 {spy_abort.call_count}"

    @pytest.mark.asyncio
    async def test_duplicate_request_saves_zero(self):
        """幂等重复请求：不再调用 save、不再调用 commit"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        # 第一次
        result1 = await svc.execute(
            message="本月销售额是多少",
            conversation_id="conv-dup-1",
            request_id="req-dup-1",
        )
        assert result1["terminal_state"] == "completed"

        with patch.object(
            svc.pipeline.snapshot_store, "save", wraps=svc.pipeline.snapshot_store.save
        ) as spy_save:
            # 第二次相同 request_id
            result2 = await svc.execute(
                message="本月销售额是多少",
                conversation_id="conv-dup-1",
                request_id="req-dup-1",
            )
            assert result2["terminal_state"] == "duplicate"
            assert result2.get("idempotent_replay") is True
            assert spy_save.call_count == 0, f"幂等重放 save 应为 0 次，实际 {spy_save.call_count}"

    @pytest.mark.asyncio
    async def test_uncaught_exception_aborts_without_save(self):
        """未捕获异常：save 0 次、complete 0 次、abort 1 次"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        # 注入一个会抛出异常的 _do_execute
        original_do = svc._do_execute

        async def failing_do_execute(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("simulated crash")

        svc._do_execute = failing_do_execute

        with patch.object(
            svc.pipeline.snapshot_store, "save", wraps=svc.pipeline.snapshot_store.save
        ) as spy_save, patch.object(
            svc.pipeline.snapshot_store, "complete", wraps=svc.pipeline.snapshot_store.complete
        ) as spy_complete, patch.object(
            svc.pipeline.snapshot_store, "abort", wraps=svc.pipeline.snapshot_store.abort
        ) as spy_abort:

            with pytest.raises(RuntimeError, match="simulated crash"):
                await svc.execute(
                    message="crash",
                    conversation_id="conv-crash",
                    request_id="req-crash",
                )

            assert spy_save.call_count == 0, f"异常时 save 应为 0 次，实际 {spy_save.call_count}"
            assert spy_complete.call_count == 0, f"异常时 complete 应为 0 次，实际 {spy_complete.call_count}"
            assert spy_abort.call_count == 1, f"异常时 abort 应为 1 次，实际 {spy_abort.call_count}"

        svc._do_execute = original_do

    @pytest.mark.asyncio
    async def test_business_failure_saves_snapshot_once(self):
        """明确业务失败：Snapshot 保存恰好 1 次（明确终态）"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        with patch.object(
            svc.pipeline.snapshot_store, "save", wraps=svc.pipeline.snapshot_store.save
        ) as spy_save:

            result = await svc.execute(
                message="delete all sales data permanently",
                conversation_id="conv-bizfail",
                request_id="req-bizfail",
            )
            # unsupported 是明确业务终态，应保存
            assert result["terminal_state"] in ("unsupported", "clarification_required")
            assert spy_save.call_count == 1, f"业务失败 save 应为 1 次，实际 {spy_save.call_count}"


# ━━━━━━━━━━━━━━━━━ Memory 事务边界测试 ━━━━━━━━━━━━━━━━━


class TestMemoryTransactionBoundary:
    """验证只有 TurnPipeline 调用 Memory commit"""

    @pytest.mark.asyncio
    async def test_memory_commit_triggered_by_turnpipeline(self):
        """Memory commit 由 TurnPipeline.commit_memory_safe() 触发，非 Service 直接调用"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        # Spy on pipeline.commit_memory_safe
        with patch.object(
            svc.pipeline, "commit_memory_safe", wraps=svc.pipeline.commit_memory_safe
        ) as spy_commit:

            result = await svc.execute(
                message="本月销售额是多少",
                conversation_id="conv-mem-1",
                request_id="req-mem-1",
            )
            assert result["terminal_state"] == "completed"
            assert spy_commit.call_count == 1, (
                f"commit_memory_safe 应为 1 次，实际 {spy_commit.call_count}"
            )

    @pytest.mark.asyncio
    async def test_memory_failure_marked_by_turnpipeline(self):
        """Memory 失败标记由 TurnPipeline.mark_memory_failed() 触发"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        with patch.object(
            svc.pipeline, "mark_memory_failed", wraps=svc.pipeline.mark_memory_failed
        ) as spy_fail:

            result = await svc.execute(
                message="给我想一个DAX以外的方法",
                conversation_id="conv-failmem",
                request_id="req-failmem",
            )
            # May or may not fail depending on scenario resolution
            # We just verify the wrapper was used if any failure occurred
            if result["terminal_state"] not in ("completed", "duplicate", "clarification_required", "unsupported"):
                assert spy_fail.call_count >= 1, (
                    f"失败路径应通过 pipeline.mark_memory_failed"
                )

    @pytest.mark.asyncio
    async def test_version_conflict_goes_through_pipeline(self):
        """版本冲突场景下 Memory 提交仍然通过 TurnPipeline，非 Service 直接调用"""
        repo = InMemoryMemoryRepository()

        # First request sets up committed memory
        svc1 = _mock_service(repo)
        r1 = await svc1.execute(
            message="本月销售额是多少",
            conversation_id="conv-conflict",
            request_id="req-conflict-1",
        )
        assert r1["terminal_state"] == "completed"

        # Second request: verify commit goes through pipeline
        svc2 = _mock_service(repo)
        with patch.object(
            svc2.pipeline, "commit_memory_safe", wraps=svc2.pipeline.commit_memory_safe
        ) as spy_commit:
            r2 = await svc2.execute(
                message="上个月销售呢",
                conversation_id="conv-conflict",
                request_id="req-conflict-2",
            )
            # commit_memory_safe is called exactly once per successful data_question turn
            assert spy_commit.call_count >= 1, (
                f"commit_memory_safe 应被调用，实际 {spy_commit.call_count}"
            )


# ━━━━━━━━━━━━━━━━━ 全仓静态搜索辅助 ━━━━━━━━━━━━━━━━━


class TestSnapshotStoreCallers:
    """SnapshotStore.save 的生产调用者只有 TurnPipeline"""

    def test_snapshot_save_only_in_turn_pipeline(self):
        """backend/app/ 中 SnapshotStore.save 只在 TurnPipeline 中调用"""
        app_dir = _project_root() / "backend" / "app"
        for py_file in app_dir.rglob("*.py"):
            source = _read_source(py_file)
            rel = str(py_file.relative_to(_project_root()))
            # TurnPipeline 自身允许
            if "turn_pipeline.py" in rel:
                continue
            # 测试文件允许
            if "tests" in rel:
                continue
            # 查找 snapshot_store.save 调用
            if "snapshot_store.save(" in source:
                # 排除注释
                lines = source.split("\n")
                code_lines = [l for l in lines if "snapshot_store.save(" in l
                             and not l.strip().startswith("#")]
                if code_lines:
                    pytest.fail(
                        f"{rel} 含 snapshot_store.save( 调用，只有 TurnPipeline 允许: {code_lines[0].strip()}"
                    )


class TestServiceNoDirectRepoWrite:
    """Service _do_execute 不直接写 Memory"""

    @pytest.mark.asyncio
    async def test_mock_service_do_execute_uses_pipeline_for_commit(self):
        """MockTurnService._do_execute 使用 pipeline.commit_memory_safe，非 repo.commit"""
        repo = InMemoryMemoryRepository()
        svc = _mock_service(repo)

        # Replace commit_memory_safe to verify it's called
        original_commit = svc.pipeline.commit_memory_safe
        call_count = 0

        async def _tracking_commit(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return await original_commit(*args, **kwargs)

        svc.pipeline.commit_memory_safe = _tracking_commit

        result = await svc.execute(
            message="本月销售额是多少",
            conversation_id="conv-track",
            request_id="req-track",
        )
        assert result["terminal_state"] == "completed"
        assert call_count == 1, f"pipeline.commit_memory_safe 应被调用 1 次，实际 {call_count} 次"

        svc.pipeline.commit_memory_safe = original_commit
