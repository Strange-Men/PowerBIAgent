"""TraceRecorder — JSON 结构化日志与 Trace

记录请求全链路事件，禁止记录 Secret。
每个 Turn 生成唯一 non-empty trace_id。
"""

import copy
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional


class TraceEvent:
    """单条 Trace 事件"""

    def __init__(
        self,
        event_type: str,
        trace_id: str = "",
        request_id: str = "",
        conversation_id: str = "",
        stage: str = "",
        data_summary: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        token_usage: Optional[dict[str, int]] = None,
    ):
        self.event_type = event_type
        self.trace_id = trace_id
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.stage = stage
        self.timestamp = datetime.utcnow().isoformat()
        self.duration_ms: Optional[float] = None
        self.data_summary = data_summary or {}
        self.error_type = error_type
        self.token_usage = token_usage or {}
        self.runtime_modes: dict[str, str] = {}
        self._start_time: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "event_type": self.event_type,
            "stage": self.stage,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "data_summary": self.data_summary,
            "error_type": self.error_type,
            "token_usage": self.token_usage,
            "runtime_modes": self.runtime_modes,
        }


# Secret 字段模式 — 规范化匹配
SECRET_FIELDS_LOWER = {
    "api_key", "apikey", "token", "secret", "password", "credential",
    "client_secret", "clientsecret", "access_token", "accesstoken",
    "refresh_token", "refreshtoken", "authorization", "auth",
}

# 敏感字符串模式
SECRET_VALUE_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{10,}'),
    re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]+'),
    re.compile(r'eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'),
]


def _redact_secrets(obj: Any, depth: int = 0, max_depth: int = 20) -> Any:
    """递归脱敏 Secret 字段和字符串值"""
    if depth > max_depth:
        return "[MAX_DEPTH_REACHED]"
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower().replace("_", "") in SECRET_FIELDS_LOWER
            else _redact_secrets(v, depth + 1, max_depth)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_redact_secrets(item, depth + 1, max_depth) for item in obj]
    elif isinstance(obj, str):
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(obj):
                return "[REDACTED]"
        return obj
    return obj


class TraceRecorder:
    """Trace 记录器

    M0.3 实现：JSON 结构化 logging + 内存事件列表（供测试断言）。
    每个事件通过索引关联，完成时准确更新对应事件。
    """

    def __init__(self, config):
        self.config = config
        self._events: list[TraceEvent] = []
        self._event_index: dict[str, int] = {}  # event_key → index

    def record(
        self,
        event_type: str,
        trace_id: str = "",
        request_id: str = "",
        conversation_id: str = "",
        stage: str = "",
        data_summary: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        token_usage: Optional[dict[str, int]] = None,
    ) -> TraceEvent:
        """记录 Trace 事件 — 自动携带 trace_id/request_id/conversation_id"""
        if not trace_id:
            trace_id = str(uuid.uuid4())

        safe_summary = _redact_secrets(data_summary or {})

        event = TraceEvent(
            event_type=event_type,
            trace_id=trace_id,
            request_id=request_id,
            conversation_id=conversation_id,
            stage=stage or event_type,
            data_summary=safe_summary,
            error_type=error_type,
            token_usage=token_usage,
        )
        event.runtime_modes = {
            "llm": self.config.llm_mode.value if hasattr(self.config.llm_mode, 'value') else str(self.config.llm_mode),
            "powerbi": self.config.powerbi_mode.value if hasattr(self.config.powerbi_mode, 'value') else str(self.config.powerbi_mode),
        }
        event._start_time = time.monotonic()

        # 记录事件索引，用于后续精确更新
        idx = len(self._events)
        event_key = f"{event_type}:{request_id}:{idx}"
        self._event_index[event_key] = idx
        self._events.append(event)

        # 完成事件自动记录耗时
        if event_type in ("request_completed", "request_failed", "tool_call_completed",
                         "tool_call_failed", "memory_committed"):
            if event._start_time is not None:
                event.duration_ms = (time.monotonic() - event._start_time) * 1000

        return event

    def record_completed(self, event_type: str, request_id: str = "") -> None:
        """标记事件完成并记录耗时 — 精确查找对应事件"""
        now = time.monotonic()
        for event in reversed(self._events):
            if event.event_type == event_type:
                if not request_id or event.request_id == request_id:
                    if event._start_time is not None:
                        event.duration_ms = (now - event._start_time) * 1000
                    return

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def get_events_by_type(self, event_type: str) -> list[TraceEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def get_tool_sequence(self) -> list[str]:
        """从 Trace 事件中提取真实工具调用序列"""
        tools = []
        for e in self._events:
            if e.event_type == "tool_call_completed":
                tool_name = e.data_summary.get("tool", "")
                if tool_name:
                    tools.append(tool_name)
        return tools

    def to_json(self) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(
            [e.to_dict() for e in self._events],
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    def clear(self) -> None:
        self._events.clear()
        self._event_index.clear()
