"""Bounded FIRST-WRONG-LAYER diagnostics for cloud turns.

A cloud turn can end in ``INTERNAL_FAILURE`` with no server-side evidence of
*which* stage produced it.  This module records, per request, a bounded sequence
of stage transitions plus the terminal failure's exception *class* and stage, so
a root cause is located instead of guessed.

Safety contract (enforced, not aspirational):

* Only a fixed stage vocabulary and a fixed allowlist of metadata keys are
  accepted; unknown keys are dropped.
* Metadata values are restricted to short canonical identifiers, booleans and
  small integers (counts).  Business row values, prompts, tokens, cookies,
  credentials, user identity, model secrets and DAX result content can never be
  recorded because no field accepts them.
* An exception contributes only its class name, never its message or repr.
* Every write is best-effort: a diagnostics failure can never fail a request.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


_LOGGER = logging.getLogger("powerbiagent.diagnostics")

# Canonical coarse stages, in execution order.
UNDERSTANDING = "UNDERSTANDING"
COVERAGE = "COVERAGE"
GROUNDING = "GROUNDING"
MEMBER_DISCOVERY = "MEMBER_DISCOVERY"
STATE_TRANSITION = "STATE_TRANSITION"
PLAN_VALIDATION = "PLAN_VALIDATION"
DAX_BUILD = "DAX_BUILD"
TOOL_EXECUTION = "TOOL_EXECUTION"
RESULT_INSPECTION = "RESULT_INSPECTION"
VERIFIED_FACTS = "VERIFIED_FACTS"
ANSWER_GENERATION = "ANSWER_GENERATION"
PRESENTATION = "PRESENTATION"
TERMINAL = "TERMINAL"

STAGES = (
    UNDERSTANDING, COVERAGE, GROUNDING, MEMBER_DISCOVERY, STATE_TRANSITION,
    PLAN_VALIDATION, DAX_BUILD, TOOL_EXECUTION, RESULT_INSPECTION,
    VERIFIED_FACTS, ANSWER_GENERATION, PRESENTATION, TERMINAL,
)

# Internal pipeline stage constants (the values already passed to
# ``_fail_result`` / ``mark_memory_failed``) mapped onto the coarse vocabulary.
_INTERNAL_STAGE_MAP: dict[str, str] = {
    "intent": UNDERSTANDING,
    "semantic_frame_projection": UNDERSTANDING,
    "semantic_interpretation": UNDERSTANDING,
    "coverage": COVERAGE,
    "template_grounding": GROUNDING,
    "semantic_grounding": GROUNDING,
    "inheritance_policy": GROUNDING,
    "semantic_catalog": GROUNDING,
    "canonical_shape_completeness": GROUNDING,
    "member_grounding": MEMBER_DISCOVERY,
    "state_transition": STATE_TRANSITION,
    "query_plan_validation": PLAN_VALIDATION,
    "dax_generation": DAX_BUILD,
    "dax_safety": DAX_BUILD,
    "dax_semantic_consistency": DAX_BUILD,
    "schema_fetch": TOOL_EXECUTION,
    "dax_execution": TOOL_EXECUTION,
    "query_result_error": TOOL_EXECUTION,
    "result_validation": RESULT_INSPECTION,
    "result_semantic_inspection": RESULT_INSPECTION,
    "verified_fact_set": VERIFIED_FACTS,
    "answer_generation": ANSWER_GENERATION,
    "answer_validation": ANSWER_GENERATION,
    "presentation": PRESENTATION,
    "memory_commit": TERMINAL,
}

# Metadata keys that are safe to persist.  Everything else is dropped.
_META_KEYS = frozenset({
    "relation", "query_shape", "collection", "changed_slots",
    "referenced_context_slots", "measure_count", "dimension_count",
    "filter_count", "candidate_count", "matched_field_count", "hit_count",
    "member_literal_present", "field_explicit", "field_count",
})
_MAX_TEXT = 64
_MAX_ITEMS = 24


def coarse_stage(internal_stage: str | None) -> str:
    if not internal_stage:
        return TERMINAL
    if internal_stage in STAGES:
        return internal_stage
    return _INTERNAL_STAGE_MAP.get(internal_stage, TERMINAL)


def _safe_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or len(text) > _MAX_TEXT:
            return None
        return text
    return None


def _safe_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_safe_text(item) for item in value]
        cleaned = tuple(item for item in items if item is not None)
        return cleaned[:_MAX_ITEMS] if cleaned else None
    return None


def safe_metadata(**kwargs: Any) -> dict[str, Any]:
    """Keep only allowlisted keys with bounded, non-identifying values."""
    result: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in _META_KEYS:
            continue
        safe = _safe_value(value)
        if safe is None:
            continue
        result[key] = safe
    return result


@dataclass
class TurnDiagnosticRecorder:
    """One request's bounded stage timeline and terminal failure."""

    request_id: str
    runtime_build_id: str = ""
    conversation_id: str | None = None
    operation: str = "chat"
    provider: str = "internal"
    synthetic: bool = False
    trace_id: str | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    first_wrong_stage: str | None = None
    error_class: str | None = None
    failure_code: str | None = None
    _started: float = field(default_factory=time.monotonic)
    _last_stage: str | None = None
    _last_started: float = field(default_factory=time.monotonic)

    # ── recording ──
    def mark(
        self,
        stage: str,
        *,
        status: str = "ok",
        detail: str | None = None,
        reason: str | None = None,
        error_type: str | None = None,
        error_class: str | None = None,
        **meta: Any,
    ) -> None:
        if len(self.stages) >= 64:
            return
        now = time.monotonic()
        record: dict[str, Any] = {
            "stage": coarse_stage(stage),
            "status": _safe_text(status) or "ok",
            "elapsed_ms": int((now - self._last_started) * 1000),
        }
        detail_text = _safe_text(detail)
        if detail_text:
            record["detail"] = detail_text
        reason_text = _safe_text(reason)
        if reason_text:
            record["reason"] = reason_text
        error_type_text = _safe_text(error_type)
        if error_type_text:
            record["error_type"] = error_type_text
        if error_class:
            record["error_class"] = error_class
        safe = safe_metadata(**meta)
        if safe:
            record["meta"] = safe
        self.stages.append(record)
        self._last_stage = record["stage"]
        self._last_started = now
        if status not in {"ok", "resolved"} and self.first_wrong_stage is None:
            self.first_wrong_stage = record["stage"]
            if error_class and self.error_class is None:
                self.error_class = error_class

    def fail(self, error: BaseException, *, stage: str | None = None) -> None:
        """Record an exception by class name only (never its message)."""
        if self.first_wrong_stage is None:
            self.first_wrong_stage = coarse_stage(stage) if stage else self._last_stage
        if self.error_class is None:
            self.error_class = type(error).__name__
        self.mark(
            stage or TERMINAL,
            status="failed",
            detail="exception",
            error_class=type(error).__name__,
        )

    def note_trace(self, trace_id: str | None) -> None:
        if trace_id and self.trace_id is None:
            self.trace_id = trace_id

    def finalize(
        self,
        *,
        terminal_state: str | None = None,
        failure_code: str | None = None,
        failure_stage: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if conversation_id and self.conversation_id is None:
            self.conversation_id = conversation_id
        if failure_code and self.failure_code is None:
            self.failure_code = failure_code
            if failure_stage and self.first_wrong_stage is None:
                self.first_wrong_stage = coarse_stage(failure_stage)
        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "conversation_id": self.conversation_id,
            "runtime_build_id": self.runtime_build_id,
            "operation": self.operation,
            "provider": self.provider,
            "synthetic": self.synthetic,
            "terminal_state": terminal_state,
            "failure_code": self.failure_code,
            "first_wrong_stage": self.first_wrong_stage,
            "error_class": self.error_class,
            "total_ms": int((time.monotonic() - self._started) * 1000),
            "stages": self.stages,
        }


_current: ContextVar[TurnDiagnosticRecorder | None] = ContextVar(
    "turn_diagnostics", default=None
)


def current_diagnostics() -> TurnDiagnosticRecorder | None:
    return _current.get()


@contextmanager
def bind_diagnostics(
    recorder: TurnDiagnosticRecorder,
) -> Iterator[TurnDiagnosticRecorder]:
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def mark_stage(stage: str, **kwargs: Any) -> None:
    """Cheap no-op when no recorder is active; never raises."""
    recorder = _current.get()
    if recorder is None:
        return
    try:
        recorder.mark(stage, **kwargs)
    except Exception:  # diagnostics must never break a request
        pass


def record_failure_stage(
    internal_stage: str | None,
    *,
    error_type: str | None = None,
    terminal_state: str | None = None,
) -> None:
    recorder = _current.get()
    if recorder is None:
        return
    try:
        recorder.mark(
            coarse_stage(internal_stage),
            status="failed",
            detail=_safe_text(internal_stage),
            error_type=_safe_text(error_type),
        )
        if terminal_state:
            recorder.mark(TERMINAL, status="failed", detail=_safe_text(terminal_state))
    except Exception:
        pass


def record_build_failure(
    *,
    error_type: str | None,
    failure_stage: str | None,
) -> None:
    """Record the first terminal failure only; later calls are ignored."""
    recorder = _current.get()
    if recorder is None or recorder.first_wrong_stage is not None:
        return
    try:
        recorder.mark(
            coarse_stage(failure_stage),
            status="failed",
            detail=_safe_text(failure_stage),
            error_type=_safe_text(error_type),
        )
    except Exception:
        pass


# ── persistence ──

_DIAGNOSTICS_DIR = Path("local_state") / "runtime" / "diagnostics"
_DIAGNOSTICS_FILE = "turns.jsonl"
_MAX_BYTES = 8 * 1024 * 1024


def _diagnostics_path() -> Path | None:
    root = os.environ.get("POWERBIAGENT_DIAGNOSTICS_DIR")
    base = Path(root) if root else _DIAGNOSTICS_DIR
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return base / _DIAGNOSTICS_FILE


def emit_diagnostic(record: dict[str, Any]) -> None:
    """Best-effort bounded append; a failure here never affects the request."""
    try:
        _LOGGER.info("turn_diagnostic %s", json.dumps(record, separators=(",", ":")))
    except Exception:
        pass
    path = _diagnostics_path()
    if path is None:
        return
    try:
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            rotated = path.with_suffix(".1.jsonl")
            try:
                if rotated.exists():
                    rotated.unlink()
                path.rename(rotated)
            except OSError:
                pass
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except OSError:
        pass