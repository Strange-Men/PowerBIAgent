"""Deterministic multi-turn semantic state transitions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.app.memory.models import StructuredWorkMemory
from backend.app.query_plan.grounding import GroundedSemanticDelta
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    QueryPlan,
    StructuredFilter,
    TimeRangeSpec,
)


class SlotTransition(str, Enum):
    KEEP = "KEEP"
    REPLACE = "REPLACE"
    CLEAR = "CLEAR"


class FilterTransition(str, Enum):
    KEEP = "KEEP"
    ADD = "ADD"
    REPLACE_SAME_FIELD = "REPLACE_SAME_FIELD"
    REMOVE = "REMOVE"
    CLEAR = "CLEAR"


class StateTransitionRecord(BaseModel):
    measure: SlotTransition
    dimension: SlotTransition
    time: SlotTransition
    sort: SlotTransition
    top_n: SlotTransition
    filters: list[FilterTransition] = Field(default_factory=list)


class StateTransitionResult(BaseModel):
    query_plan: CanonicalQueryPlan
    transitions: StateTransitionRecord


class StateTransitionService:
    """Merge a grounded current-turn delta with last committed state only."""

    def merge(
        self,
        draft: QueryPlan,
        delta: GroundedSemanticDelta,
        committed: StructuredWorkMemory | None,
        *,
        canonical_template_key: str | None = None,
    ) -> StateTransitionResult:
        previous_measures = list(committed.measures) if committed else []
        previous_dimensions = list(committed.dimensions) if committed else []
        previous_filters = self._previous_filters(committed)
        previous_time = self._previous_time(committed)
        previous_sort = committed.sort if committed else None
        previous_top_n = committed.top_n if committed else None

        if delta.measures is None:
            measures = previous_measures
            measure_transition = SlotTransition.KEEP
        else:
            measures = delta.measures
            measure_transition = (
                SlotTransition.KEEP
                if measures == previous_measures else SlotTransition.REPLACE
            )

        if delta.dimensions is None:
            dimensions = previous_dimensions
            dimension_transition = SlotTransition.KEEP
        elif not delta.dimensions:
            dimensions = []
            dimension_transition = SlotTransition.CLEAR
        else:
            dimensions = delta.dimensions
            dimension_transition = (
                SlotTransition.KEEP
                if dimensions == previous_dimensions else SlotTransition.REPLACE
            )

        filters = list(previous_filters)
        filter_transitions: list[FilterTransition] = []
        if delta.clear_filters:
            filters = []
            filter_transitions.append(FilterTransition.CLEAR)
        else:
            for field in delta.remove_filter_fields:
                before = len(filters)
                filters = [item for item in filters if item.field != field]
                if len(filters) != before:
                    filter_transitions.append(FilterTransition.REMOVE)
            for current in delta.filters or []:
                same_field = [item for item in filters if item.field == current.field]
                filters = [item for item in filters if item.field != current.field]
                filters.append(current)
                filter_transitions.append(
                    FilterTransition.REPLACE_SAME_FIELD
                    if same_field else FilterTransition.ADD
                )
        if not filter_transitions:
            filter_transitions.append(FilterTransition.KEEP)

        if delta.clear_time:
            time_range = None
            time_transition = SlotTransition.CLEAR
        elif delta.time_specified:
            time_range = delta.time_range
            time_transition = (
                SlotTransition.KEEP
                if time_range == previous_time else SlotTransition.REPLACE
            )
        else:
            time_range = previous_time
            time_transition = SlotTransition.KEEP

        if delta.clear_sort:
            sort = None
            sort_transition = SlotTransition.CLEAR
        elif delta.sort_specified:
            sort = delta.sort
            sort_transition = (
                SlotTransition.KEEP
                if sort == previous_sort else SlotTransition.REPLACE
            )
        else:
            sort = previous_sort
            sort_transition = SlotTransition.KEEP

        if delta.clear_top_n:
            top_n = None
            top_n_transition = SlotTransition.CLEAR
        elif delta.top_n_specified:
            top_n = delta.top_n
            top_n_transition = (
                SlotTransition.KEEP
                if top_n == previous_top_n else SlotTransition.REPLACE
            )
        else:
            top_n = previous_top_n
            top_n_transition = SlotTransition.KEEP

        if top_n is not None and sort is None:
            raise ValueError("canonical_top_n_requires_sort")
        if not measures:
            raise ValueError("canonical_measure_required")

        plan = CanonicalQueryPlan(
            normalized_question=draft.normalized_question,
            semantic_model_key=draft.semantic_model_key,
            measures=measures,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            sort=sort,
            top_n=top_n,
            comparison_mode=None,
            requested_template=canonical_template_key,
            inherited_context=draft.inherited_context,
            is_mock=draft.is_mock,
        )
        return StateTransitionResult(
            query_plan=plan,
            transitions=StateTransitionRecord(
                measure=measure_transition,
                dimension=dimension_transition,
                time=time_transition,
                sort=sort_transition,
                top_n=top_n_transition,
                filters=filter_transitions,
            ),
        )

    @staticmethod
    def _previous_filters(
        committed: StructuredWorkMemory | None,
    ) -> list[StructuredFilter]:
        if committed is None:
            return []
        parsed: list[StructuredFilter] = []
        for item in committed.filters:
            try:
                parsed.append(StructuredFilter.model_validate(item))
            except (TypeError, ValueError):
                continue
        return parsed

    @staticmethod
    def _previous_time(
        committed: StructuredWorkMemory | None,
    ) -> TimeRangeSpec | None:
        if committed is None or committed.time_range is None:
            return None
        try:
            return TimeRangeSpec.model_validate(committed.time_range)
        except (TypeError, ValueError):
            # Legacy free-text committed time cannot cross the canonical boundary.
            return None
