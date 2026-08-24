"""ToolGateway — 工具注册、权限检查和执行网关

MVP 只注册三个工具：
1. get_semantic_model_schema
2. execute_dax
3. render_report

M0.3.2 修复：
- 取消全局 TOOL_INTENT_POLICY，以 ToolSpec.allowed_intents 为唯一来源
- 完整策略检查（read_only、模式、用户模型/模板/工具权限）
- 正确的异常分类（不重试 vs 有限重试）
- 结构化 ToolExecutionContext
- Gateway 真实产生 Trace 事件
- 输出类型错误使用 ToolOutputValidationError
"""

import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.harness.errors import (
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.memory.models import RuntimeDataMode
from backend.app.schemas.data_contracts import UserContext
from backend.app.intent.models import IntentType


class ToolExecutionContext(BaseModel):
    """结构化工具执行上下文"""
    trace_id: str = ""
    request_id: str = ""
    conversation_id: str = ""
    runtime_mode: RuntimeDataMode = RuntimeDataMode.MOCK
    intent: IntentType = IntentType.DATA_QUESTION
    user: UserContext = Field(default_factory=UserContext)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolSpec(BaseModel):
    """工具规格 — 安全默认值使用 default_factory"""
    name: str
    description: str = ""
    input_model: Optional[type[BaseModel]] = None
    output_model: Optional[type[BaseModel]] = None
    timeout_seconds: float = 30.0
    max_retries: int = 1
    read_only: bool = True
    allowed_intents: list[IntentType] = Field(default_factory=list)
    supported_modes: list[RuntimeDataMode] = Field(
        default_factory=lambda: [RuntimeDataMode.MOCK, RuntimeDataMode.REAL]
    )
    handler: Optional[Callable] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolGateway:
    """工具网关

    职责：
    1. 工具注册
    2. 重复注册拒绝
    3. 未注册工具拒绝
    4. read_only 检查
    5. Intent 权限检查（以 ToolSpec.allowed_intents 为唯一来源）
    6. runtime_mode 支持检查
    7. UserContext 工具/模型/模板权限检查
    8. 输入 Pydantic 校验
    9. async timeout
    10. 正确的异常分类和有限重试
    11. Handler 执行
    12. 输出 Pydantic 校验
    13. Trace 事件产生
    14. 标准化异常
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        # M0.4: 删除 _trace_recorder / _turn_controller 共享实例字段
        # TraceRecorder 和 TurnController 通过 execute() 参数显式传入

    def register(self, tool: ToolSpec) -> None:
        """注册工具 — 重复注册拒绝"""
        if tool.name in self._tools:
            raise ToolNotRegisteredError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolSpec:
        """获取已注册工具 — 未注册拒绝"""
        if name not in self._tools:
            raise ToolNotRegisteredError(
                f"Tool '{name}' not registered. Available: {list(self._tools.keys())}"
            )
        return self._tools[name]

    def list_tools(self) -> list[str]:
        """列出所有已注册工具"""
        return list(self._tools.keys())

    def check_intent_permission(
        self, tool_name: str, intent: IntentType
    ) -> bool:
        """检查 Intent 是否有权使用工具 — 以 ToolSpec.allowed_intents 为唯一来源"""
        tool = self.get_tool(tool_name)
        if intent not in tool.allowed_intents:
            raise ToolPolicyDeniedError(
                f"Intent '{intent.value}' not allowed to use tool '{tool_name}'. "
                f"Allowed intents: {[i.value for i in tool.allowed_intents]}"
            )
        return True

    def _check_read_only(self, tool: ToolSpec) -> None:
        """检查工具是否为只读"""
        if not tool.read_only:
            raise ToolPolicyDeniedError(
                f"Tool '{tool.name}' is not read-only — execution denied"
            )

    def _check_mode_support(self, tool: ToolSpec, runtime_mode: RuntimeDataMode) -> None:
        """检查 runtime_mode 是否被工具支持"""
        if runtime_mode not in tool.supported_modes:
            raise ToolPolicyDeniedError(
                f"Tool '{tool.name}' does not support mode '{runtime_mode.value}'. "
                f"Supported: {[m.value for m in tool.supported_modes]}"
            )

    def _check_user_tool_permission(
        self, tool_name: str, user: UserContext
    ) -> None:
        """检查 UserContext 是否有工具权限"""
        if tool_name not in user.allowed_tools:
            raise ToolPolicyDeniedError(
                f"User '{user.user_id}' not allowed to use tool '{tool_name}'"
            )

    def _check_user_model_permission(
        self, user: UserContext, semantic_model_key: Optional[str]
    ) -> None:
        """检查用户是否有语义模型权限"""
        if semantic_model_key and semantic_model_key not in user.allowed_semantic_models:
            raise ToolPolicyDeniedError(
                f"User '{user.user_id}' not allowed to access model '{semantic_model_key}'. "
                f"Allowed: {user.allowed_semantic_models}"
            )

    def _check_user_template_permission(
        self, user: UserContext, template_key: Optional[str]
    ) -> None:
        """检查用户是否有模板权限"""
        if template_key and template_key not in user.allowed_templates:
            raise ToolPolicyDeniedError(
                f"User '{user.user_id}' not allowed to use template '{template_key}'. "
                f"Allowed: {user.allowed_templates}"
            )

    def _extract_semantic_model_key(self, input_data: BaseModel) -> Optional[str]:
        """从输入安全提取 semantic_model_key"""
        if hasattr(input_data, "semantic_model_key"):
            return getattr(input_data, "semantic_model_key", None)
        return None

    def _extract_template_key(self, input_data: BaseModel) -> Optional[str]:
        """从输入安全提取 template_key"""
        if hasattr(input_data, "template_key"):
            return getattr(input_data, "template_key", None)
        return None

    async def execute(
        self,
        tool_name: str,
        execution_context: ToolExecutionContext,
        input_data: BaseModel,
        trace: Any = None,
        controller: Any = None,
    ) -> Any:
        """执行工具 — 完整策略检查、校验、超时和重试

        Args:
            tool_name: 工具名称
            execution_context: 结构化执行上下文
            input_data: 工具输入
            trace: 当前请求的 TraceRecorder（M0.4: 显式传入，不保存到实例字段）
            controller: 当前请求的 TurnController（M0.4: 显式传入，不保存到实例字段）

        Returns:
            工具执行结果

        Raises:
            ToolNotRegisteredError: 工具未注册
            ToolPolicyDeniedError: 策略拒绝（不重试）
            ToolTimeoutError: 超时
            ToolExecutionError: 执行失败
            ToolOutputValidationError: 输出校验失败
        """
        tool = self.get_tool(tool_name)

        # === 策略检查（不重试类错误） ===

        # 1. read_only 检查
        self._check_read_only(tool)

        # 2. Intent 权限（以 ToolSpec.allowed_intents 为唯一来源）
        self.check_intent_permission(tool_name, execution_context.intent)

        # 3. runtime_mode 支持
        self._check_mode_support(tool, execution_context.runtime_mode)

        # 4. UserContext 工具权限
        self._check_user_tool_permission(tool_name, execution_context.user)

        # 5. 用户模型权限
        model_key = self._extract_semantic_model_key(input_data)
        self._check_user_model_permission(execution_context.user, model_key)

        # 6. 用户模板权限
        template_key = self._extract_template_key(input_data)
        self._check_user_template_permission(execution_context.user, template_key)

        # 7. 输入类型校验
        if tool.input_model is not None:
            if not isinstance(input_data, tool.input_model):
                raise ToolPolicyDeniedError(
                    f"Tool '{tool_name}' expects input type {tool.input_model.__name__}, "
                    f"got {type(input_data).__name__}"
                )

        # 8. Handler 存在
        if tool.handler is None:
            raise ToolNotRegisteredError(f"Tool '{tool_name}' has no handler")

        # === 执行（含超时和正确重试） ===

        # Trace: tool_call_started
        self._record_trace(trace, "tool_call_started", execution_context, tool_name,
                           attempt=1, max_attempts=tool.max_retries + 1,
                           input_summary=self._safe_summary(input_data))

        last_error: Optional[Exception] = None
        for attempt in range(tool.max_retries + 1):
            try:
                # 检查 TurnController 工具调用限制
                if controller is not None:
                    controller.check_tool_call_limit()

                start = time.monotonic()
                result = await asyncio.wait_for(
                    tool.handler(input_data),
                    timeout=tool.timeout_seconds,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                # 输出校验
                if tool.output_model is not None and not isinstance(result, tool.output_model):
                    self._record_trace(trace, "tool_call_failed", execution_context, tool_name,
                                       attempt=attempt + 1, max_attempts=tool.max_retries + 1,
                                       error_type="output_validation",
                                       duration_ms=elapsed_ms)
                    raise ToolOutputValidationError(
                        f"Tool '{tool_name}' output type mismatch: "
                        f"expected {tool.output_model.__name__}, got {type(result).__name__}"
                    )

                # Trace: tool_call_completed
                self._record_trace(trace, "tool_call_completed", execution_context, tool_name,
                                   attempt=attempt + 1, max_attempts=tool.max_retries + 1,
                                   output_summary=self._safe_summary(result),
                                   duration_ms=elapsed_ms)
                return result

            except asyncio.TimeoutError:
                elapsed_ms = tool.timeout_seconds * 1000
                last_error = ToolTimeoutError(
                    f"Tool '{tool_name}' timed out after {tool.timeout_seconds}s"
                )
                self._record_trace(trace, "tool_call_failed", execution_context, tool_name,
                                   attempt=attempt + 1, max_attempts=tool.max_retries + 1,
                                   error_type="timeout",
                                   duration_ms=elapsed_ms)
                if attempt < tool.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))

            except (ToolNotRegisteredError, ToolPolicyDeniedError,
                    ToolOutputValidationError):
                # 不重试类异常 — 直接抛出
                raise

            except Exception as e:
                # 仅对可重试的已知错误类型重试
                last_error = ToolExecutionError(
                    f"Tool '{tool_name}' execution failed: {e}",
                    error_type=str(
                        getattr(e, "error_type", type(e).__name__)
                    ),
                )
                if self._is_retryable(e) and attempt < tool.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                self._record_trace(trace, "tool_call_failed", execution_context, tool_name,
                                   attempt=attempt + 1, max_attempts=tool.max_retries + 1,
                                   error_type=type(e).__name__)
                raise last_error

        # 所有重试耗尽
        raise last_error  # type: ignore[misc]

    def _is_retryable(self, error: Exception) -> bool:
        """判断异常是否可重试"""
        # PowerBIAdapterError 带有 retryable 标记
        if hasattr(error, "retryable") and getattr(error, "retryable", False):
            return True
        # 明确的重试标记
        retryable_names = {
            "ConnectionError", "TimeoutError", "TemporaryError",
        }
        return type(error).__name__ in retryable_names

    def _record_trace(
        self,
        trace: Any,
        event_type: str,
        ctx: ToolExecutionContext,
        tool_name: str,
        attempt: int = 1,
        max_attempts: int = 1,
        input_summary: Optional[dict[str, Any]] = None,
        output_summary: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """通过 TraceRecorder 记录工具事件 — M0.4: trace 显式传入"""
        if trace is None:
            return

        data = {
            "tool": tool_name,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }
        if input_summary:
            data["input"] = input_summary
        if output_summary:
            data["output"] = output_summary
        if error_type:
            data["error_type"] = error_type
        if duration_ms > 0:
            data["duration_ms"] = duration_ms

        trace.record(
            event_type,
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            conversation_id=ctx.conversation_id,
            data_summary=data,
            error_type=error_type,
        )

    def _safe_summary(self, obj: Any) -> dict[str, Any]:
        """生成安全摘要 — 不含完整数据和 Secret"""
        if obj is None:
            return {}
        if isinstance(obj, BaseModel):
            d = obj.model_dump(exclude_defaults=True) if hasattr(obj, "model_dump") else {}
            # 只保留结构信息，排除完整数据
            safe = {}
            for k, v in d.items():
                if k in ("rows", "html", "data"):
                    continue  # 排除完整数据
                if isinstance(v, list):
                    safe[k] = f"[{len(v)} items]"
                elif isinstance(v, str) and len(v) > 200:
                    safe[k] = v[:200] + "..."
                else:
                    safe[k] = v
            return safe
        return {"type": type(obj).__name__}
