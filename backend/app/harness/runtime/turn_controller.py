"""TurnController — 轮次状态机与生命周期管理"""

import time
from enum import Enum
from typing import Optional

from backend.app.harness.errors import TurnLimitExceededError, TurnStateError
from backend.app.harness.models import HarnessConfig
from backend.app.memory.models import MemoryCommitEvidence


class TurnState(str, Enum):
    """Turn 状态枚举"""
    RECEIVED = "received"
    CONTEXT_READY = "context_ready"
    INTENT_CLASSIFIED = "intent_classified"
    PLAN_READY = "plan_ready"
    QUERY_VALIDATED = "query_validated"
    TOOL_EXECUTED = "tool_executed"
    RESULT_VALIDATED = "result_validated"
    RESPONSE_READY = "response_ready"
    MEMORY_COMMITTED = "memory_committed"
    COMPLETED = "completed"

    # 终止状态
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    VALIDATION_FAILED = "validation_failed"
    TOOL_FAILED = "tool_failed"
    RESPONSE_FAILED = "response_failed"
    MEMORY_CONFLICT = "memory_conflict"
    CANCELLED = "cancelled"


# 合法状态转换表
LEGAL_TRANSITIONS: dict[TurnState, set[TurnState]] = {
    TurnState.RECEIVED: {TurnState.CONTEXT_READY, TurnState.CANCELLED},
    TurnState.CONTEXT_READY: {
        TurnState.INTENT_CLASSIFIED,
        TurnState.CLARIFICATION_REQUIRED,
        TurnState.UNSUPPORTED,
    },
    TurnState.INTENT_CLASSIFIED: {
        TurnState.PLAN_READY,
        TurnState.CLARIFICATION_REQUIRED,
        TurnState.UNSUPPORTED,
    },
    TurnState.PLAN_READY: {
        TurnState.QUERY_VALIDATED,
        TurnState.TOOL_EXECUTED,
        TurnState.CLARIFICATION_REQUIRED,
        TurnState.VALIDATION_FAILED,
        TurnState.TOOL_FAILED,
    },
    TurnState.QUERY_VALIDATED: {
        TurnState.TOOL_EXECUTED,
        TurnState.VALIDATION_FAILED,
        TurnState.TOOL_FAILED,
    },
    TurnState.TOOL_EXECUTED: {TurnState.RESULT_VALIDATED, TurnState.VALIDATION_FAILED, TurnState.TOOL_FAILED},
    TurnState.RESULT_VALIDATED: {TurnState.RESPONSE_READY, TurnState.RESPONSE_FAILED},
    TurnState.RESPONSE_READY: {TurnState.MEMORY_COMMITTED, TurnState.MEMORY_CONFLICT},
    TurnState.MEMORY_COMMITTED: {TurnState.COMPLETED},
    # 终止状态不可再转换
    TurnState.COMPLETED: set(),
    TurnState.CLARIFICATION_REQUIRED: set(),
    TurnState.UNSUPPORTED: set(),
    TurnState.VALIDATION_FAILED: set(),
    TurnState.TOOL_FAILED: set(),
    TurnState.RESPONSE_FAILED: set(),
    TurnState.MEMORY_CONFLICT: set(),
    TurnState.CANCELLED: set(),
}

# 终止状态集合
TERMINAL_STATES: set[TurnState] = {
    TurnState.COMPLETED,
    TurnState.CLARIFICATION_REQUIRED,
    TurnState.UNSUPPORTED,
    TurnState.VALIDATION_FAILED,
    TurnState.TOOL_FAILED,
    TurnState.RESPONSE_FAILED,
    TurnState.MEMORY_CONFLICT,
    TurnState.CANCELLED,
}


class TurnController:
    """轮次控制器

    管理单次 Turn 的完整生命周期：
    - 状态转换和合法性检查
    - 资源限制（工具调用次数、重试次数）
    - MemoryCommitEvidence 生成
    - 终止状态判断
    """

    def __init__(self, config: HarnessConfig, request_id: str = ""):
        self.config = config
        self.request_id = request_id
        self._state: TurnState = TurnState.RECEIVED
        self._start_time = time.monotonic()

        # 计数器
        self._tool_call_count = 0
        self._dax_repair_count = 0
        self._llm_format_retry_count = 0
        self._powerbi_retry_count = 0
        self._token_usage: dict[str, int] = {}

        # 失败原因
        self._failure_reason: Optional[str] = None

        # 证据累积
        self._intent_valid = False
        self._request_allowed = True
        self._query_plan_valid = False
        self._dax_valid = False
        self._tool_execution_succeeded = False
        self._query_result_valid = False
        self._response_valid = False
        self._version_matches = False

    # -----------------------------------------------------------------
    # 状态管理
    # -----------------------------------------------------------------

    @property
    def state(self) -> TurnState:
        return self._state

    def transition(self, to_state: TurnState) -> None:
        """执行状态转换 — 非法跳转拒绝"""
        if to_state not in LEGAL_TRANSITIONS.get(self._state, set()):
            raise TurnStateError(
                f"Illegal transition: {self._state.value} → {to_state.value}"
            )
        self._state = to_state

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    @property
    def can_continue(self) -> bool:
        """是否可以继续执行"""
        return not self.is_terminal

    @property
    def can_commit_memory(self) -> bool:
        """是否允许提交 Memory"""
        return self._state in {
            TurnState.RESPONSE_READY,
            TurnState.MEMORY_COMMITTED,
        }

    # -----------------------------------------------------------------
    # 资源限制
    # -----------------------------------------------------------------

    def check_tool_call_limit(self) -> None:
        """检查工具调用次数"""
        self._tool_call_count += 1
        if self._tool_call_count > self.config.max_tool_calls:
            raise TurnLimitExceededError(
                f"Tool call limit exceeded: {self.config.max_tool_calls}"
            )

    def check_dax_repair_limit(self) -> None:
        self._dax_repair_count += 1
        if self._dax_repair_count > self.config.max_dax_repairs:
            raise TurnLimitExceededError("DAX repair limit exceeded")

    def check_llm_retry_limit(self) -> None:
        self._llm_format_retry_count += 1
        if self._llm_format_retry_count > self.config.max_llm_format_retries:
            raise TurnLimitExceededError("LLM format retry limit exceeded")

    def check_powerbi_retry_limit(self) -> None:
        self._powerbi_retry_count += 1
        if self._powerbi_retry_count > self.config.max_powerbi_retries:
            raise TurnLimitExceededError("Power BI retry limit exceeded")

    # -----------------------------------------------------------------
    # 证据记录
    # -----------------------------------------------------------------

    def record_intent_valid(self) -> None:
        self._intent_valid = True

    def record_request_allowed(self) -> None:
        self._request_allowed = True

    def record_query_plan_valid(self) -> None:
        self._query_plan_valid = True

    def record_dax_valid(self) -> None:
        self._dax_valid = True

    def record_tool_execution_succeeded(self) -> None:
        self._tool_execution_succeeded = True

    def record_query_result_valid(self) -> None:
        self._query_result_valid = True

    def record_response_valid(self) -> None:
        self._response_valid = True

    def record_version_matches(self) -> None:
        self._version_matches = True

    def set_failure_reason(self, reason: str) -> None:
        self._failure_reason = reason

    def record_token_usage(self, usage: dict[str, int]) -> None:
        self._token_usage = usage

    # -----------------------------------------------------------------
    # 证据生成
    # -----------------------------------------------------------------

    def build_commit_evidence(self) -> MemoryCommitEvidence:
        """生成 MemoryCommitEvidence"""
        from backend.app.memory.models import MemoryCommitEvidence

        return MemoryCommitEvidence(
            intent_valid=self._intent_valid,
            request_allowed=self._request_allowed,
            query_plan_valid=self._query_plan_valid,
            dax_valid=self._dax_valid,
            tool_execution_succeeded=self._tool_execution_succeeded,
            query_result_valid=self._query_result_valid,
            response_valid=self._response_valid,
            version_matches=self._version_matches,
            failure_reason=self._failure_reason,
        )

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    @property
    def failure_reason(self) -> Optional[str]:
        return self._failure_reason
