"""Deterministic partial clarification context merging.

Pending clarification is non-executable and repository-owned.  This module may
retain only identities already resolved by Semantic Grounding/runtime members
and analysis operators derived by fixed rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pydantic import BaseModel

from backend.app.memory.models import (
    PendingClarificationContext,
    PendingSemanticSlot,
    PendingSlotProvenance,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.query_plan.grounding import (
    GroundedSemanticDelta,
    GroundingOutcome,
    GroundingStatus,
)
from backend.app.schemas.data_contracts import QueryShape, StructuredFilter


class ClarificationMergeResult(BaseModel):
    context: PendingClarificationContext
    complete: bool
    executable_delta: GroundedSemanticDelta | None = None
    clarification_question: str


class PendingClarificationService:
    """Merge current authoritative partial semantics into a pending chain."""

    _ABANDON_TERMS = (
        "重新开始",
        "新问题",
        "忽略之前",
        "取消澄清",
    )
    _INDEPENDENT_QUERY_TERMS = (
        "是多少",
        "多少",
        "单独看",
        "不比较",
        "重新分析",
    )

    @classmethod
    def should_abandon(cls, user_input: str) -> bool:
        return any(term in user_input for term in cls._ABANDON_TERMS)

    def merge(
        self,
        *,
        previous: PendingClarificationContext | None,
        outcome: GroundingOutcome,
        user_input: str,
        conversation_id: str,
        request_id: str,
        semantic_model_key: str,
        schema_fingerprint: str,
        runtime_mode: RuntimeDataMode,
        intent: str,
        committed: StructuredWorkMemory | None,
    ) -> ClarificationMergeResult:
        if previous is not None and (
            previous.semantic_model_key != semantic_model_key
            or previous.schema_fingerprint != schema_fingerprint
            or previous.runtime_mode != runtime_mode
            or previous.intent != intent
        ):
            previous = None
        if (
            previous is not None
            and self._starts_independent_query(previous, outcome, user_input)
        ):
            previous = None

        measures = list(previous.measures) if previous else []
        dimensions = list(previous.dimensions) if previous else []
        filters = list(previous.filters) if previous else []
        time_range = previous.time_range if previous else None
        sort = previous.sort if previous else None
        top_n = previous.top_n if previous else None
        query_shape = previous.query_shape if previous else None
        provenance = {
            key: list(values)
            for key, values in (previous.slot_provenance.items() if previous else [])
        }

        delta = outcome.delta or GroundedSemanticDelta()
        if delta.query_shape is not None:
            query_shape = delta.query_shape
        resolved_measures = self._resolved_names(outcome, "measure")
        resolved_dimensions = [
            *self._resolved_names(outcome, "dimension"),
            *self._resolved_names(outcome, "ranking_dimension"),
        ]
        blocked_roles = {
            item.role
            for item in outcome.object_results
            if item.status in {
                GroundingStatus.AMBIGUOUS,
                GroundingStatus.UNRESOLVED,
                GroundingStatus.CONFIG_CONFLICT,
            }
        }
        if "measure" in blocked_roles:
            measures = []
        if {"dimension", "ranking_dimension"} & blocked_roles:
            dimensions = []
        if "filter_field" in blocked_roles:
            filters = []
        if "date_field" in blocked_roles:
            time_range = None
        for item in outcome.member_results:
            if item.status != GroundingStatus.RESOLVED:
                filters = [
                    value
                    for value in filters
                    if value.field != item.field.canonical_name
                ]
        if delta.measures is not None:
            measures = list(delta.measures)
        elif resolved_measures:
            measures = resolved_measures[:1]
        if delta.dimensions is not None:
            dimensions = list(delta.dimensions)
        elif resolved_dimensions:
            dimensions = resolved_dimensions[:1]

        grounded_filters = list(delta.filters or [])
        if not grounded_filters:
            grounded_filters = [
                StructuredFilter(
                    field=item.field.canonical_name,
                    value=item.canonical_value,
                )
                for item in outcome.member_results
                if item.status == GroundingStatus.RESOLVED
            ]
        for current in grounded_filters:
            filters = [item for item in filters if item.field != current.field]
            filters.append(current)
        if delta.clear_filters:
            filters = []
        for field in delta.remove_filter_fields:
            filters = [item for item in filters if item.field != field]

        if delta.time_specified:
            time_range = delta.time_range
        elif delta.clear_time:
            time_range = None
        if delta.sort_specified:
            sort = delta.sort
        elif delta.clear_sort:
            sort = None
        if delta.top_n_specified:
            top_n = delta.top_n
        elif delta.clear_top_n:
            top_n = None

        analysis_sort, analysis_top_n = self._safe_analysis(user_input)
        if analysis_sort is not None:
            sort = analysis_sort
            self._record(
                provenance, "analysis", request_id,
                "deterministic_analysis", "best/ranking rule",
            )
        if analysis_top_n is not None:
            top_n = analysis_top_n
            self._record(
                provenance, "analysis", request_id,
                "deterministic_analysis", "best/top_n rule",
            )

        if delta.measures is not None or resolved_measures:
            self._record(
                provenance, "measure", request_id,
                "semantic_catalog", "current grounded measure",
            )
        if delta.dimensions is not None or resolved_dimensions:
            self._record(
                provenance, "dimension", request_id,
                "semantic_catalog", "current grounded dimension",
            )
        if grounded_filters:
            self._record(
                provenance, "filter", request_id,
                "runtime_member", "current runtime member",
            )
        if delta.time_specified:
            self._record(
                provenance, "time", request_id,
                "deterministic_analysis", "resolved time boundary",
            )

        missing = self._missing_slots(
            measures, dimensions, sort, top_n, outcome, query_shape
        )
        now = datetime.utcnow()
        context_values = dict(
            conversation_id=conversation_id,
            semantic_model_key=semantic_model_key,
            schema_fingerprint=schema_fingerprint,
            intent=intent,  # type: ignore[arg-type]
            query_shape=query_shape,
            measures=measures,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            sort=sort,
            top_n=top_n,
            missing_slots=missing,
            slot_provenance=provenance,
            base_committed_version=(
                previous.base_committed_version
                if previous else (committed.memory_version if committed else 0)
            ),
            runtime_mode=runtime_mode,
            last_request_id=request_id,
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )
        if previous is not None:
            context_values["chain_id"] = previous.chain_id
        context = PendingClarificationContext.model_validate(context_values)

        complete = outcome.status == GroundingStatus.RESOLVED and not missing
        executable = self._to_delta(context) if complete else None
        return ClarificationMergeResult(
            context=context,
            complete=complete,
            executable_delta=executable,
            clarification_question=self._question(missing, outcome),
        )

    @staticmethod
    def _resolved_names(outcome: GroundingOutcome, role: str) -> list[str]:
        return [
            item.canonical_object.canonical_name
            for item in outcome.object_results
            if item.role == role
            and item.status == GroundingStatus.RESOLVED
            and item.canonical_object is not None
        ]

    @staticmethod
    def _safe_analysis(user_input: str) -> tuple[str | None, int | None]:
        if "最好" in user_input:
            return "desc", 1
        return None, None

    @classmethod
    def _starts_independent_query(
        cls,
        previous: PendingClarificationContext,
        outcome: GroundingOutcome,
        user_input: str,
    ) -> bool:
        """Discard an unfinished ranking chain for a standalone scalar query.

        Business identity still comes from the Grounding outcome.  The fixed
        language rule only classifies the current utterance as a new analysis
        request rather than a one-slot clarification answer.
        """
        if previous.top_n is None and previous.sort is None:
            return False
        if any(term in user_input for term in ("最好", "最高", "最低", "排名", "Top", "top")):
            return False
        resolved_measure = any(
            item.role == "measure"
            and item.status == GroundingStatus.RESOLVED
            for item in outcome.object_results
        )
        return resolved_measure and any(
            term in user_input for term in cls._INDEPENDENT_QUERY_TERMS
        )

    @staticmethod
    def _missing_slots(
        measures: list[str],
        dimensions: list[str],
        sort: str | None,
        top_n: int | None,
        outcome: GroundingOutcome,
        query_shape: QueryShape | None,
    ) -> list[PendingSemanticSlot]:
        missing: list[PendingSemanticSlot] = []
        effective_shape = query_shape or QueryShape.SCALAR
        if not measures and effective_shape != QueryShape.ENTITY_LIST:
            missing.append("measure")
        dimension_required = effective_shape in {
            QueryShape.ENTITY_LIST,
            QueryShape.GROUPED,
            QueryShape.RANKING,
            QueryShape.MEMBER_SET,
            QueryShape.TREND,
            QueryShape.BOUNDED_TREND,
        }
        ranking_requested = top_n is not None or sort is not None
        if (dimension_required or ranking_requested) and not dimensions:
            missing.append("dimension")
        if top_n is not None and sort is None:
            missing.append("analysis")
        for item in outcome.object_results:
            if item.status not in {
                GroundingStatus.AMBIGUOUS,
                GroundingStatus.UNRESOLVED,
                GroundingStatus.CONFIG_CONFLICT,
            }:
                continue
            slot: PendingSemanticSlot = (
                "measure" if item.role == "measure"
                else "dimension" if item.role in {"dimension", "ranking_dimension"}
                else "filter" if item.role == "filter_field"
                else "time"
            )
            if slot not in missing:
                missing.append(slot)
        if any(
            item.status != GroundingStatus.RESOLVED
            for item in outcome.member_results
        ) and "filter" not in missing:
            missing.append("filter")
        order: tuple[PendingSemanticSlot, ...] = (
            "measure", "dimension", "filter", "time", "analysis", "template"
        )
        return [slot for slot in order if slot in missing]

    @staticmethod
    def _record(
        provenance: dict[str, list[PendingSlotProvenance]],
        slot: str,
        request_id: str,
        authority: str,
        source: str,
    ) -> None:
        record = PendingSlotProvenance(
            request_id=request_id,
            authority=authority,  # type: ignore[arg-type]
            source=source,
        )
        values = provenance.setdefault(slot, [])
        if record not in values:
            values.append(record)

    @staticmethod
    def _to_delta(context: PendingClarificationContext) -> GroundedSemanticDelta:
        return GroundedSemanticDelta(
            query_shape=context.query_shape,
            measures=list(context.measures),
            dimensions=list(context.dimensions),
            filters=list(context.filters),
            time_range=context.time_range,
            time_specified=context.time_range is not None,
            sort=context.sort,
            sort_specified=context.sort is not None,
            top_n=context.top_n,
            top_n_specified=context.top_n is not None,
        )

    @staticmethod
    def _question(
        missing: Iterable[PendingSemanticSlot], outcome: GroundingOutcome
    ) -> str:
        slots = set(missing)
        if {"measure", "dimension"}.issubset(slots):
            return "请分别明确要比较的业务指标和分析维度。"
        if "measure" in slots:
            if slots == {"measure"} and outcome.clarification_question:
                return outcome.clarification_question
            return "请明确要使用的业务指标。"
        if "dimension" in slots:
            return "请明确要按哪个分析维度比较。"
        if "filter" in slots:
            return "请明确唯一的筛选字段和值。"
        if "time" in slots:
            return "请明确要使用的时间范围。"
        return outcome.clarification_question or "请补充完成当前查询所需的信息。"
