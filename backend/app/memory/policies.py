"""记忆系统策略规则

固化的记忆提交准入条件和一致性规则。
M0.2 固化为策略接口，M0.3 Harness 在 TurnController 中强制执行。
"""

from datetime import datetime
from typing import Optional

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryCorrectionRecord,
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import MemoryCommitDeniedError


# 允许通过纠正接口修改的字段白名单
CORRECTION_ALLOWED_FIELDS = frozenset({
    "measures",
    "dimensions",
    "filters",
    "time_range",
    "sort",
    "top_n",
    "comparison_mode",
    "analysis_goal",
})

# 禁止通过纠正接口修改的内部字段
CORRECTION_BLOCKED_FIELDS = frozenset({
    "conversation_id",
    "request_id",
    "base_memory_version",
    "memory_version",
    "state_status",
    "created_at",
    "runtime_mode",
})


class MemoryPolicies:
    """记忆系统策略集合

    所有规则在 M0.2 固化为接口，M0.3 Harness 中强制执行。
    """

    # -----------------------------------------------------------------
    # 提交准入
    # -----------------------------------------------------------------

    @staticmethod
    def check_commit_eligibility(memory: StructuredWorkMemory) -> None:
        """检查记忆是否满足完整成功边界

        完整成功边界要求：
        1. 意图有效
        2. 请求未被拒绝（非 unsupported）
        3. 查询计划有效
        4. DAX 校验成功
        5. 工具执行成功
        6. 查询结果校验成功
        7. 最终回答或 ReportSpec 成功
        8. memory_version 未冲突

        Mock 空间规则：
        - Mock 成功轮次在 Mock 空间允许提交
        - Mock 结果在 Real 空间不允许提交
        - Production/Real 不得加载 Mock committed memory

        Raises:
            MemoryCommitDeniedError: 不满足提交条件
        """
        failures: list[str] = []

        # 意图有效
        if not memory.current_intent:
            failures.append("无有效意图")
        elif memory.current_intent in ("unsupported", "clarification"):
            failures.append(f"意图不允许提交: {memory.current_intent}")

        # 非暂停状态
        if memory.clarification_pending:
            failures.append("存在待澄清问题")

        # 状态检查
        if memory.state_status == MemoryStatus.FAILED:
            failures.append("记忆已标记为 failed")
        elif memory.state_status == MemoryStatus.COMMITTED:
            failures.append("记忆已提交，不可重复提交")
        elif memory.state_status != MemoryStatus.PENDING:
            failures.append(f"仅有 pending 状态可提交，当前: {memory.state_status.value}")

        # Mock 空间规则
        if memory.is_mock and memory.runtime_mode == RuntimeDataMode.REAL:
            failures.append("Mock 结果不可在 Real 空间提交")

        # 证据检查（如果存在）— 只检查 business_satisfied，不要求 all_satisfied
        # 因为 version_matches 只能由 Repository 在原子提交时设置
        if memory.commit_evidence is not None:
            if not memory.commit_evidence.business_satisfied:
                failures.append(
                    f"提交业务证据不完整: {memory.commit_evidence.failure_reason or '部分条件未满足'}"
                )

        if failures:
            raise MemoryCommitDeniedError(f"记忆提交被拒绝: {'; '.join(failures)}")

    @staticmethod
    def check_evidence_required(memory: StructuredWorkMemory) -> None:
        """检查是否具备完整提交证据

        M0.3.2: 只检查 business_satisfied，version_matches 由 Repository 原子设置。
        """
        if memory.commit_evidence is None:
            raise MemoryCommitDeniedError("缺少 MemoryCommitEvidence，不允许提交")
        if not memory.commit_evidence.business_satisfied:
            raise MemoryCommitDeniedError(
                f"MemoryCommitEvidence 业务条件不完整: {memory.commit_evidence.failure_reason or '未知原因'}"
            )

    # -----------------------------------------------------------------
    # 一致性规则
    # -----------------------------------------------------------------

    @staticmethod
    def check_request_id_idempotent(
        existing: Optional[StructuredWorkMemory], new_request_id: str
    ) -> bool:
        """request_id 幂等检查"""
        if existing is not None and existing.request_id == new_request_id:
            return True
        return False

    @staticmethod
    def check_version_conflict(
        base_version: int, current_committed_version: int
    ) -> bool:
        """memory_version 乐观锁检查 — base 版本与当前最新 committed 版本不一致时拒绝写入"""
        return base_version != current_committed_version

    # -----------------------------------------------------------------
    # 上下文切换规则
    # -----------------------------------------------------------------

    @staticmethod
    def on_model_switch(memory: StructuredWorkMemory, new_model_key: str) -> StructuredWorkMemory:
        """切换语义模型时的清理策略"""
        memory.semantic_model_key = new_model_key
        memory.measures = []
        memory.dimensions = []
        memory.filters = []
        memory.time_range = None
        memory.sort = None
        memory.top_n = None
        memory.comparison_mode = None
        memory.last_query_plan = None
        memory.last_dax = None
        memory.last_query_result_id = None
        memory.last_result_summary = None
        memory.updated_at = datetime.utcnow()
        return memory

    @staticmethod
    def on_template_switch(memory: StructuredWorkMemory, new_template_key: str) -> StructuredWorkMemory:
        """切换报表模板时的策略 — 保留分析条件，清理旧 ReportSpec"""
        memory.report_template_key = new_template_key
        memory.last_report_id = None
        memory.updated_at = datetime.utcnow()
        return memory

    @staticmethod
    def on_reset(memory: StructuredWorkMemory) -> StructuredWorkMemory:
        """"重新开始" 策略"""
        memory.current_intent = None
        memory.analysis_goal = None
        memory.measures = []
        memory.dimensions = []
        memory.filters = []
        memory.time_range = None
        memory.sort = None
        memory.top_n = None
        memory.comparison_mode = None
        memory.last_query_plan = None
        memory.last_dax = None
        memory.last_query_result_id = None
        memory.last_result_summary = None
        memory.last_report_id = None
        memory.clarification_pending = False
        memory.clarification_question = None
        memory.state_status = MemoryStatus.PENDING
        memory.updated_at = datetime.utcnow()
        return memory

    @staticmethod
    def on_correction(
        memory: StructuredWorkMemory,
        field: str,
        old_value: object,
        new_value: object,
        reason: str = "",
        request_id: str = "",
    ) -> StructuredWorkMemory:
        """用户纠正 — 记录审计信息

        规则：
        - 纠正字段必须使用白名单
        - 禁止通过纠正接口修改内部字段
        - 记录完整的 MemoryCorrectionRecord
        """
        # 空字段名忽略
        if not field:
            return memory

        # 禁止修改内部字段
        if field in CORRECTION_BLOCKED_FIELDS:
            return memory

        # 仅允许白名单字段
        if field not in CORRECTION_ALLOWED_FIELDS:
            return memory

        # 记录审计
        record = MemoryCorrectionRecord(
            field=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            corrected_at=datetime.utcnow(),
            request_id=request_id or memory.request_id,
        )
        memory.add_correction_record(record)

        # 更新字段
        if hasattr(memory, field):
            setattr(memory, field, new_value)

        return memory

    # -----------------------------------------------------------------
    # Context Assembly 契约
    # -----------------------------------------------------------------

    @staticmethod
    def allowed_context_keys() -> set[str]:
        """Context Assembly 允许包含的上下文类型"""
        return {
            "system_rules",
            "current_input",
            "committed_memory",
            "recent_messages",       # 最近 5 轮
            "rolling_summary",
            "schema_subset",
            "current_model_info",
            "mock_real_flag",
        }
