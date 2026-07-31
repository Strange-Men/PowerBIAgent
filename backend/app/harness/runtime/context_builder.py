"""ContextBuilder — 安全组装 LLM 上下文

只注入允许的内容类型，严格排除 Secret 和敏感数据。
"""

import copy
from typing import Any, Optional

from backend.app.harness.models import HarnessConfig
from backend.app.memory.models import StructuredWorkMemory


# 禁止注入上下文的敏感字段模式
SECRET_FIELD_PATTERNS = [
    "api_key", "token", "secret", "password", "credential",
    "client_secret", "access_token", "refresh_token", "auth",
]


def _is_secret_key(key: str) -> bool:
    """判断字段名是否为敏感字段"""
    key_lower = key.lower().replace("_", "")
    for pattern in SECRET_FIELD_PATTERNS:
        if pattern.replace("_", "") in key_lower:
            return True
    return False


def _filter_secrets(data: Any, depth: int = 0) -> Any:
    """递归过滤 Secret 字段"""
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            k: "[REDACTED]" if _is_secret_key(str(k)) else _filter_secrets(v, depth + 1)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [_filter_secrets(item, depth + 1) for item in data]
    return data


class ContextBuilder:
    """上下文构建器

    输入：
    - 当前用户消息
    - committed structured memory
    - 最近消息
    - 滚动摘要
    - Schema 子集
    - semantic_model_key
    - report_template_key
    - 系统规则
    - 运行模式

    注入规则：
    必须注入：系统规则、当前输入、当前模型、committed memory、最近5轮、
              滚动摘要、Schema子集、Mock/Real标记、工具限制
    禁止注入：全部历史、完整Schema、大量原始QueryResult、Secret、
              failed/pending memory、与当前模型无关的Schema
    """

    def __init__(self, config: HarnessConfig):
        self.config = config
        self.max_recent_messages = 5
        self.max_input_length = config.max_user_input_length

    def build(
        self,
        user_message: str,
        committed_memory: Optional[StructuredWorkMemory] = None,
        recent_messages: Optional[list[dict[str, str]]] = None,
        rolling_summary: Optional[str] = None,
        schema_subset: Optional[dict[str, Any]] = None,
        semantic_model_key: Optional[str] = None,
        report_template_key: Optional[str] = None,
        system_rules: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构建安全上下文字典

        Returns:
            结构化上下文，可直接注入 LLM 或 Agent
        """
        context: dict[str, Any] = {
            "system_rules": system_rules or {},
            "current_input": self._truncate_input(user_message),
            "current_model_info": {
                "semantic_model_key": semantic_model_key,
                "report_template_key": report_template_key,
            },
            "mock_real_flag": "mock" if self.config.is_mock else "real",
            "runtime_modes": {
                "llm": self.config.llm_mode.value,
                "powerbi": self.config.powerbi_mode.value,
                "harness": self.config.harness_mode.value,
            },
        }

        # committed memory（过滤后）
        if committed_memory is not None:
            memory_dict = committed_memory.model_dump()
            context["committed_memory"] = _filter_secrets(memory_dict)

        # 最近消息（最多5轮）
        if recent_messages:
            context["recent_messages"] = recent_messages[-self.max_recent_messages:]
        else:
            context["recent_messages"] = []

        # 滚动摘要
        if rolling_summary:
            context["rolling_summary"] = rolling_summary

        # Schema 子集（过滤 Secret）
        if schema_subset:
            context["schema_subset"] = _filter_secrets(schema_subset)

        # 工具限制
        context["tool_restrictions"] = {
            "max_tool_calls": self.config.max_tool_calls,
            "read_only": True,
        }

        return context

    def _truncate_input(self, message: str) -> str:
        """截断过长输入"""
        if len(message) > self.max_input_length:
            return message[: self.max_input_length] + "...[truncated]"
        return message
