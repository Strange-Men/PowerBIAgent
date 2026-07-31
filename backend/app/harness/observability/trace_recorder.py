"""TraceRecorder — JSON 结构化日志与 Trace

记录请求全链路事件，禁止记录 Secret。
"""

import copy
import json
import time
from datetime import datetime
from typing import Any, Optional

from backend.app.harness.models import HarnessConfig


class TraceEvent:
    """单条 Trace 事件"""

    def __init__(
        self,
        event_type: str,
        trace_id: str = "",
        request_id: str = "",
        conversation_id: str = "",
        data_summary: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        token_usage: Optional[dict[str, int]] = None,
    ):
        self.event_type = event_type
        self.trace_id = trace_id
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.timestamp = datetime.utcnow().isoformat()
        self.duration_ms: Optional[float] = None
        self.data_summary = data_summary or {}
        self.error_type = error_type
        self.token_usage = token_usage or {}
        self.runtime_modes: dict[str, str] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "data_summary": self.data_summary,
            "error_type": self.error_type,
            "token_usage": self.token_usage,
            "runtime_modes": self.runtime_modes,
        }


# Secret 字段模式
SECRET_FIELDS = {
    "api_key", "token", "secret", "password", "credential",
    "client_secret", "access_token", "refresh_token", "authorization",
}


def _redact_secrets(obj: Any, depth: int = 0) -> Any:
    """递归脱敏 Secret 字段"""
    if depth > 20:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower() in SECRET_FIELDS
            else _redact_secrets(v, depth + 1)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_redact_secrets(item, depth + 1) for item in obj]
    return obj


class TraceRecorder:
    """Trace 记录器

    M0.3 实现：JSON 结构化 logging + 内存事件列表（供测试断言）。
    不实现 SQLite Trace 持久化和 OpenTelemetry。
    """

    def __init__(self, config: HarnessConfig):
        self.config = config
        self._events: list[TraceEvent] = []
        self._start_times: dict[str, float] = {}

    def record(
        self,
        event_type: str,
        trace_id: str = "",
        request_id: str = "",
        conversation_id: str = "",
        data_summary: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        token_usage: Optional[dict[str, int]] = None,
    ) -> TraceEvent:
        """记录 Trace 事件"""
        # 脱敏数据
        safe_summary = _redact_secrets(data_summary or {})

        event = TraceEvent(
            event_type=event_type,
            trace_id=trace_id,
            request_id=request_id,
            conversation_id=conversation_id,
            data_summary=safe_summary,
            error_type=error_type,
            token_usage=token_usage,
        )
        event.runtime_modes = {
            "llm": self.config.llm_mode.value,
            "powerbi": self.config.powerbi_mode.value,
        }

        self._events.append(event)
        self._start_times[event_type] = time.monotonic()
        return event

    def record_completed(self, event_type: str) -> None:
        """标记事件完成并记录耗时"""
        start = self._start_times.get(event_type)
        if start is not None and self._events:
            self._events[-1].duration_ms = (time.monotonic() - start) * 1000

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def get_events_by_type(self, event_type: str) -> list[TraceEvent]:
        return [e for e in self._events if e.event_type == event_type]

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
        self._start_times.clear()
