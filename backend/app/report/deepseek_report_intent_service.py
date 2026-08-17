"""Bounded DeepSeek report-intent weak-signal draft service.

This is the ONLY LLM call in the M3.4 report path.  It answers "which
registry-owned analysis goals does the user want?" and nothing else.  Any
failure, malformed output or unknown ID fails closed to an empty draft — the
deterministic planner keeps full authority.  Counted separately from factual
LLM calls (llm_report_intent_call_count), never as DAX/ReportData/Report
factual authority.
"""

from __future__ import annotations

from typing import Optional

from backend.app.harness.observability.llm_observer import LLMCallCollector
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)
from backend.app.report.capability import ALLOWED_SECTION_IDS, parse_section_ids
from backend.app.report.intent import ReportIntentDraft
from backend.app.report.intent_prompt import build_report_intent_messages


class ReportIntentDraftError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class DeepSeekReportIntentService:
    """Produce a bounded report-intent draft from the provider."""

    def __init__(
        self,
        provider: LLMProvider,
        max_format_repairs: int = 1,
    ) -> None:
        if provider.is_mock:
            raise ReportIntentDraftError(
                "DeepSeekReportIntentService 要求非 Mock Provider"
            )
        self._provider = provider
        self._max_format_repairs = max(0, min(max_format_repairs, 1))

    async def draft(
        self,
        user_input: str,
        collector: Optional[LLMCallCollector] = None,
    ) -> tuple[str, ...]:
        """Return registry-owned section IDs, or () on any failure.

        Fail-closed contract: the planner falls back to the deterministic
        signal when this returns empty.
        """
        try:
            draft = await self._try_draft(user_input)
            return parse_section_ids(draft.report_section_ids)
        except LLMValidationError:
            # Format-level failure: one bounded repair, then fail closed.
            if self._max_format_repairs < 1:
                return ()
            try:
                repaired = await self._try_draft(
                    user_input, repair_error_code="invalid_content_json_or_schema"
                )
                return parse_section_ids(repaired.report_section_ids)
            except (LLMValidationError, LLMProviderError):
                return ()
            except Exception:
                return ()
        except LLMProviderError:
            # Network / auth / rate-limit failures never block the report.
            return ()
        except Exception:
            # Fail closed on any unexpected provider behavior.
            return ()

    async def _try_draft(
        self,
        user_input: str,
        repair_error_code: Optional[str] = None,
    ) -> ReportIntentDraft:
        messages = build_report_intent_messages(user_input)
        if repair_error_code is not None:
            messages[-1] = {
                "role": "user",
                "content": (
                    messages[-1]["content"]
                    + f"\n（上次输出格式无效：{repair_error_code}。"
                    "请只输出合法 JSON。）"
                ),
            }
        request = LLMRequest(
            messages=messages,
            task=LLMTask.REPORT_INTENT,
            scenario_key=None,
            metadata={
                "allowed_section_ids": sorted(ALLOWED_SECTION_IDS),
            },
        )
        response = await self._provider.generate(request, ReportIntentDraft)
        if response.structured is None:
            raise LLMValidationError(
                "report intent draft structured output missing",
            )
        return response.structured
