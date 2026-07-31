"""ToolGateway — 工具注册、权限检查和执行网关

MVP 只注册三个工具：
1. get_semantic_model_schema
2. execute_dax
3. render_report
"""

import asyncio
import time
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict

from backend.app.harness.errors import ToolNotRegisteredError, ToolPolicyDeniedError
from backend.app.schemas.data_contracts import UserContext
from backend.app.intent.models import IntentType


class ToolSpec(BaseModel):
    """工具规格"""
    name: str
    description: str = ""
    input_model: Optional[type[BaseModel]] = None
    output_model: Optional[type[BaseModel]] = None
    timeout_seconds: float = 30.0
    max_retries: int = 1
    read_only: bool = True
    allowed_intents: list[IntentType] = []
    supported_modes: list[str] = ["mock", "real"]
    handler: Optional[Callable] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


# 内置工具策略矩阵
TOOL_INTENT_POLICY: dict[str, list[IntentType]] = {
    "get_semantic_model_schema": [IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
    "execute_dax": [IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
    "render_report": [IntentType.REPORT_GENERATION],
}


class ToolGateway:
    """工具网关

    职责：
    1. 工具注册
    2. 重复注册拒绝
    3. 未注册工具拒绝
    4. Intent 权限检查
    5. UserContext 权限检查
    6. 输入 Pydantic 校验
    7. async timeout
    8. 有限重试
    9. Handler 执行
    10. 输出 Pydantic 校验
    11. Trace 事件
    12. 标准化异常
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

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
        """检查 Intent 是否有权使用工具"""
        tool = self.get_tool(tool_name)
        allowed = TOOL_INTENT_POLICY.get(tool_name, [])
        if intent not in allowed:
            raise ToolPolicyDeniedError(
                f"Intent '{intent.value}' not allowed to use tool '{tool_name}'. "
                f"Allowed intents: {[i.value for i in allowed]}"
            )
        return True

    def check_user_permission(
        self, tool_name: str, user: UserContext
    ) -> bool:
        """检查 UserContext 是否有权使用工具"""
        if tool_name not in user.allowed_tools:
            raise ToolPolicyDeniedError(
                f"User '{user.user_id}' not allowed to use tool '{tool_name}'"
            )
        return True

    async def execute(
        self,
        tool_name: str,
        intent: IntentType,
        user: UserContext,
        input_data: BaseModel,
    ) -> Any:
        """执行工具 — 完整权限检查、校验、超时和重试"""
        tool = self.get_tool(tool_name)

        # 权限检查
        self.check_intent_permission(tool_name, intent)
        self.check_user_permission(tool_name, user)

        # 输入校验
        if tool.input_model is not None:
            if not isinstance(input_data, tool.input_model):
                raise ToolPolicyDeniedError(
                    f"Tool '{tool_name}' expects input type {tool.input_model.__name__}, "
                    f"got {type(input_data).__name__}"
                )

        if tool.handler is None:
            raise ToolNotRegisteredError(f"Tool '{tool_name}' has no handler")

        # 执行（含超时和重试）
        last_error: Optional[Exception] = None
        for attempt in range(tool.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    tool.handler(input_data),
                    timeout=tool.timeout_seconds,
                )
                # 输出校验
                if tool.output_model is not None and not isinstance(result, tool.output_model):
                    raise ToolPolicyDeniedError(
                        f"Tool '{tool_name}' output type mismatch: "
                        f"expected {tool.output_model.__name__}"
                    )
                return result
            except asyncio.TimeoutError:
                last_error = ToolPolicyDeniedError(
                    f"Tool '{tool_name}' timed out after {tool.timeout_seconds}s"
                )
            except Exception as e:
                last_error = e
                if attempt < tool.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))

        raise last_error  # type: ignore[misc]
