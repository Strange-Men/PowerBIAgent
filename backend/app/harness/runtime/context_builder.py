"""ContextBuilder — 安全组装 LLM 上下文

只注入允许的内容类型，严格排除 Secret 和敏感数据。
ContextBuilder 自身检查 Memory 状态、模式和模型边界。
"""

import copy
import re
from typing import Any, Optional

from backend.app.harness.models import HarnessConfig
from backend.app.memory.models import MemoryStatus, RuntimeDataMode, StructuredWorkMemory


# 禁止注入上下文的敏感字段模式（字段名匹配）
SECRET_FIELD_PATTERNS = [
    "api_key", "token", "secret", "password", "credential",
    "client_secret", "access_token", "refresh_token", "auth",
]

# 敏感字符串值模式
SECRET_VALUE_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{10,}'),           # sk- API Key
    re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]+'),     # Bearer token
    re.compile(r'eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'),  # JWT
]


def _is_secret_key(key: str) -> bool:
    """判断字段名是否为敏感字段"""
    key_lower = key.lower().replace("_", "")
    for pattern in SECRET_FIELD_PATTERNS:
        if pattern.replace("_", "") in key_lower:
            return True
    return False


def _is_secret_value(value: str) -> bool:
    """判断字符串值是否为敏感值"""
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _filter_secrets(data: Any, depth: int = 0, max_depth: int = 15) -> Any:
    """递归过滤 Secret 字段和值"""
    if depth > max_depth:
        return "[MAX_DEPTH_REACHED]"
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if _is_secret_key(str(k)):
                result[k] = "[REDACTED]"
            else:
                result[k] = _filter_secrets(v, depth + 1, max_depth)
        return result
    elif isinstance(data, list):
        return [_filter_secrets(item, depth + 1, max_depth) for item in data]
    elif isinstance(data, str):
        if _is_secret_value(data):
            return "[REDACTED]"
        return data
    return data


class ContextBuilder:
    """上下文构建器

    输入：
    - 当前用户消息
    - committed structured memory（必须已 committed，模式匹配）
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
    ContextBuilder 自身检查 committed 状态、runtime_mode、semantic_model_key。
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

        ContextBuilder 自身检查：
        - Memory 状态必须为 committed
        - runtime_mode 与当前配置一致
        - semantic_model_key 与当前选择一致
        - failed/pending 不能注入
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

        # committed memory（严格检查后注入）
        if committed_memory is not None:
            # 状态检查：只注入 committed
            if committed_memory.state_status != MemoryStatus.COMMITTED:
                # 不注入非 committed 记忆
                context["committed_memory"] = None
            else:
                # 模式检查：只注入与当前模式一致的记忆
                current_mode = RuntimeDataMode.MOCK if self.config.is_mock else RuntimeDataMode.REAL
                if committed_memory.runtime_mode != current_mode:
                    context["committed_memory"] = None
                elif (semantic_model_key is not None
                      and committed_memory.semantic_model_key is not None
                      and committed_memory.semantic_model_key != semantic_model_key):
                    # 不相关模型 Memory 不注入
                    context["committed_memory"] = None
                else:
                    memory_dict = committed_memory.model_dump()
                    context["committed_memory"] = _filter_secrets(memory_dict)
        else:
            context["committed_memory"] = None

        # 最近消息（最多5轮，递归 Secret 过滤）
        if recent_messages:
            filtered_messages = _filter_secrets(recent_messages[-self.max_recent_messages:])
            context["recent_messages"] = filtered_messages
        else:
            context["recent_messages"] = []

        # 滚动摘要
        if rolling_summary:
            context["rolling_summary"] = _filter_secrets(rolling_summary)

        # Schema 子集（Secret 过滤）
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
