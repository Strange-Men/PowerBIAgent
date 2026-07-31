"""记忆系统策略规则

固化的记忆提交准入条件和一致性规则。
本轮不实现查询工具，但准入条件必须固化为策略接口。
"""

from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
from backend.app.memory.repository import MemoryCommitDeniedError


class MemoryPolicies:
    """记忆系统策略集合

    所有规则在 M0.2 固化为接口，M0.3 Harness 中强制执行。
    """

    # -----------------------------------------------------------------
    # 10.3 — 提交准入
    # -----------------------------------------------------------------

    @staticmethod
    def check_commit_eligibility(memory: StructuredWorkMemory) -> None:
        """检查记忆是否满足完整成功边界

        完整成功边界至少要求：
        1. 意图有效
        2. 请求未被拒绝（非 unsupported）
        3. 查询计划有效
        4. DAX 校验成功
        5. 工具执行成功
        6. 查询结果校验成功
        7. 最终回答或 ReportSpec 成功
        8. memory_version 未冲突

        本轮 (M0.2) 固化为策略接口。M0.3 Harness 在 TurnController 中强制执行。

        Raises:
            MemoryCommitDeniedError: 不满足提交条件
        """
        failures: list[str] = []

        # 意图有效
        if not memory.current_intent:
            failures.append("无有效意图")
        elif memory.current_intent == "unsupported":
            failures.append("意图被拒绝 (unsupported)")

        # 非暂停状态
        if memory.clarification_pending:
            failures.append("存在待澄清问题")

        # 状态检查
        if memory.state_status == MemoryStatus.FAILED:
            failures.append("记忆已标记为 failed")
        elif memory.state_status == MemoryStatus.COMMITTED:
            failures.append("记忆已提交，不可重复提交")

        # Mock 检查
        if memory.is_mock:
            failures.append("Mock 结果不可标记为真实业务结果")

        # 后续 M0.3 将增加：查询计划有效、DAX 校验、工具执行成功等

        if failures:
            raise MemoryCommitDeniedError(f"记忆提交被拒绝: {'; '.join(failures)}")

    # -----------------------------------------------------------------
    # 10.4 — 一致性规则
    # -----------------------------------------------------------------

    @staticmethod
    def check_request_id_idempotent(
        existing: StructuredWorkMemory | None, new_request_id: str
    ) -> bool:
        """request_id 幂等检查

        相同 request_id 的请求不应重复处理。
        """
        if existing is not None and existing.request_id == new_request_id:
            return True
        return False

    @staticmethod
    def check_version_conflict(
        current_version: int, expected_version: int
    ) -> bool:
        """memory_version 乐观锁检查

        期望版本与当前版本不一致时拒绝写入。
        """
        return current_version != expected_version

    # -----------------------------------------------------------------
    # 上下文切换规则
    # -----------------------------------------------------------------

    @staticmethod
    def on_model_switch(memory: StructuredWorkMemory, new_model_key: str) -> StructuredWorkMemory:
        """切换语义模型时的清理策略

        - 清理旧模型的分析状态（measures, dimensions, filters, time_range 等）
        - 清理 last_query_plan, last_dax, last_query_result_id
        - 保留 conversation_id 和审计信息
        - 递增 memory_version
        """
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
        memory.bump_version()
        return memory

    @staticmethod
    def on_template_switch(memory: StructuredWorkMemory, new_template_key: str) -> StructuredWorkMemory:
        """切换报表模板时的策略

        - 保留分析条件（measures, dimensions, filters）
        - 清理旧 ReportSpec
        - 更新模板 Key
        """
        memory.report_template_key = new_template_key
        memory.last_report_id = None
        memory.bump_version()
        return memory

    @staticmethod
    def on_reset(memory: StructuredWorkMemory) -> StructuredWorkMemory:
        """"重新开始" 策略

        - 清空工作记忆（分析要素、查询结果）
        - 保留 conversation_id
        - 保留审计记录（不删除历史 committed 记录）
        - 重置为 pending 状态
        """
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
        memory.bump_version()
        return memory

    @staticmethod
    def on_correction(
        memory: StructuredWorkMemory,
        field: str,
        old_value: object,
        new_value: object,
    ) -> StructuredWorkMemory:
        """用户纠正口径

        - 记录旧值和新值
        - 更新对应字段
        - 递增 memory_version
        """
        if hasattr(memory, field):
            setattr(memory, field, new_value)
        memory.bump_version()
        return memory

    # -----------------------------------------------------------------
    # Context Assembly 契约
    # -----------------------------------------------------------------

    @staticmethod
    def allowed_context_keys() -> set[str]:
        """Context Assembly 允许包含的上下文类型

        只允许：
        - 系统规则
        - 当前用户输入
        - committed structured memory
        - 最近 5 轮消息
        - 滚动摘要
        - 相关 Schema 子集
        - 当前模型与模板
        - Mock/真实标识

        禁止：
        - 全部历史对话
        - 完整 Schema
        - 大量原始查询结果
        - Secret
        - failed/pending 状态
        - 与当前模型无关的数据
        """
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
