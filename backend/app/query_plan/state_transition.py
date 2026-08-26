"""Deterministic multi-turn semantic state transitions."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field

from backend.app.intent.models import IntentSpec, TurnRelation
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


class InheritanceMode(str, Enum):
    """Deterministic meaning of omitted slots for the current turn."""

    FRESH_QUESTION = "FRESH_QUESTION"
    FOLLOW_UP = "FOLLOW_UP"
    REPLACE = "REPLACE"


class InheritanceDecision(BaseModel):
    mode: InheritanceMode | None = None
    requires_clarification: bool = False
    reason: str


class TurnInheritancePolicy:
    """Bounded relation policy; it never chooses canonical slot identities."""

    _REPLACE_CUE = re.compile(
        r"^\s*(?:改成|改为|换成|换为|调整为|改看|换看|改|换)"
    )
    _FOLLOW_PREFIX = re.compile(r"^\s*(?:那|那么|只看|再看|继续|然后)")
    _FOLLOW_SUFFIX = re.compile(r"呢\s*[？?。.]?\s*$")

    @classmethod
    def decide(
        cls,
        user_input: str,
        intent: IntentSpec,
        delta: GroundedSemanticDelta,
        committed: StructuredWorkMemory | None,
    ) -> InheritanceDecision:
        if committed is None:
            return InheritanceDecision(
                mode=InheritanceMode.FRESH_QUESTION,
                reason="no_committed_context",
            )

        has_current_slot = bool(
            delta.measures is not None
            or delta.dimensions is not None
            or delta.filters
            or delta.time_specified
            or delta.sort_specified
            or delta.top_n_specified
            or delta.clear_filters
            or delta.clear_time
            or delta.clear_sort
            or delta.clear_top_n
        )
        if cls._REPLACE_CUE.search(user_input):
            return InheritanceDecision(
                mode=InheritanceMode.REPLACE,
                reason="deterministic_replace_cue",
            )
        if cls._FOLLOW_PREFIX.search(user_input) or cls._FOLLOW_SUFFIX.search(user_input):
            if has_current_slot:
                return InheritanceDecision(
                    mode=InheritanceMode.FOLLOW_UP,
                    reason="deterministic_follow_up_cue",
                )
            return InheritanceDecision(
                requires_clarification=True,
                reason="follow_up_without_current_slot",
            )

        if (
            delta.time_specified
            and delta.measures is None
            and delta.dimensions is None
            and not delta.filters
            and not delta.sort_specified
            and not delta.top_n_specified
        ):
            return InheritanceDecision(
                mode=InheritanceMode.REPLACE,
                reason="deterministic_time_only_replacement",
            )

        if (
            delta.measures is None
            and delta.dimensions
            and delta.top_n_specified
        ):
            return InheritanceDecision(
                mode=InheritanceMode.FOLLOW_UP,
                reason="deterministic_ranking_refinement",
            )

        # A grounded measure makes the current question self-contained.  This
        # check intentionally precedes the LLM relation signal so an inherited
        # draft echo cannot turn a complete new question into a follow-up.
        if delta.measures:
            return InheritanceDecision(
                mode=InheritanceMode.FRESH_QUESTION,
                reason="current_grounded_measure_is_self_contained",
            )
        if intent.turn_relation == TurnRelation.REPLACE and has_current_slot:
            return InheritanceDecision(
                mode=InheritanceMode.REPLACE,
                reason="bounded_replace_signal",
            )
        if intent.turn_relation == TurnRelation.FOLLOW_UP and has_current_slot:
            return InheritanceDecision(
                mode=InheritanceMode.FOLLOW_UP,
                reason="bounded_follow_up_signal",
            )
        if intent.turn_relation == TurnRelation.FRESH_QUESTION:
            return InheritanceDecision(
                requires_clarification=True,
                reason="fresh_question_missing_measure",
            )
        return InheritanceDecision(
            requires_clarification=True,
            reason="insufficient_inheritance_evidence",
        )


class CommittedMemoryCorruptionError(ValueError):
    """Committed canonical state cannot be safely inherited."""

    def __init__(
        self,
        code: str,
        *,
        filter_index: int | None = None,
    ) -> None:
        super().__init__(code)
        self.filter_index = filter_index


class StateTransitionRecord(BaseModel):
    inheritance_mode: InheritanceMode = InheritanceMode.FOLLOW_UP
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
        inheritance_mode: InheritanceMode = InheritanceMode.FOLLOW_UP,
    ) -> StateTransitionResult:
        previous_measures = list(committed.measures) if committed else []
        previous_dimensions = list(committed.dimensions) if committed else []
        previous_dimension_tables = self._previous_dimension_tables(committed)
        previous_dimension_order = self._previous_dimension_order(committed)
        previous_filters = self._previous_filters(committed)
        previous_time = self._previous_time(committed)
        previous_sort = committed.sort if committed else None
        previous_top_n = committed.top_n if committed else None

        inherit_omitted = inheritance_mode != InheritanceMode.FRESH_QUESTION

        if delta.measures is None:
            measures = previous_measures if inherit_omitted else []
            measure_transition = (
                SlotTransition.KEEP
                if inherit_omitted or not previous_measures else SlotTransition.CLEAR
            )
        else:
            measures = delta.measures
            measure_transition = (
                SlotTransition.KEEP
                if measures == previous_measures else SlotTransition.REPLACE
            )

        if delta.dimensions is None:
            dimensions = previous_dimensions if inherit_omitted else []
            dimension_tables = (
                {**previous_dimension_tables, **delta.dimension_tables}
                if inherit_omitted else dict(delta.dimension_tables)
            )
            dimension_transition = (
                SlotTransition.KEEP
                if inherit_omitted or not previous_dimensions else SlotTransition.CLEAR
            )
            dimension_order = previous_dimension_order if inherit_omitted else None
        elif not delta.dimensions:
            dimensions = []
            dimension_tables = dict(delta.dimension_tables)
            dimension_transition = SlotTransition.CLEAR
            dimension_order = None
        else:
            dimensions = delta.dimensions
            dimension_tables = dict(delta.dimension_tables)
            dimension_transition = (
                SlotTransition.KEEP
                if dimensions == previous_dimensions else SlotTransition.REPLACE
            )
            dimension_order = delta.dimension_order

        filters = list(previous_filters) if inherit_omitted else []
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
            filter_transitions.append(
                FilterTransition.KEEP
                if inherit_omitted or not previous_filters else FilterTransition.CLEAR
            )

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
            time_range = previous_time if inherit_omitted else None
            time_transition = (
                SlotTransition.KEEP
                if inherit_omitted or previous_time is None else SlotTransition.CLEAR
            )

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
            sort = previous_sort if inherit_omitted else None
            sort_transition = (
                SlotTransition.KEEP
                if inherit_omitted or previous_sort is None else SlotTransition.CLEAR
            )

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
            top_n = previous_top_n if inherit_omitted else None
            top_n_transition = (
                SlotTransition.KEEP
                if inherit_omitted or previous_top_n is None else SlotTransition.CLEAR
            )

        if top_n is not None and sort is None:
            raise ValueError("canonical_top_n_requires_sort")
        if not measures:
            raise ValueError("canonical_measure_required")

        active_hint_fields = {
            *dimensions,
            *(item.field for item in filters),
            *([time_range.date_field] if time_range is not None else []),
        }
        dimension_tables = {
            field: table
            for field, table in {
                **previous_dimension_tables,
                **dimension_tables,
                **delta.dimension_tables,
            }.items()
            if field in active_hint_fields
        }

        plan = CanonicalQueryPlan(
            normalized_question=draft.normalized_question,
            semantic_model_key=draft.semantic_model_key,
            measures=measures,
            dimensions=dimensions,
            dimension_tables=dimension_tables or None,
            dimension_order=dimension_order,
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
                inheritance_mode=inheritance_mode,
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
        for index, item in enumerate(committed.filters):
            try:
                parsed.append(StructuredFilter.model_validate(item))
            except (TypeError, ValueError) as exc:
                raise CommittedMemoryCorruptionError(
                    f"committed_memory_filter_invalid:{index}",
                    filter_index=index,
                ) from exc
        return parsed

    @staticmethod
    def _previous_time(
        committed: StructuredWorkMemory | None,
    ) -> TimeRangeSpec | None:
        if committed is None or committed.time_range is None:
            return None
        if isinstance(committed.time_range, str):
            # Sealed legacy contract: old free-text time is non-executable.
            return None
        try:
            return TimeRangeSpec.model_validate(committed.time_range)
        except (TypeError, ValueError) as exc:
            raise CommittedMemoryCorruptionError(
                "committed_memory_time_range_invalid"
            ) from exc

    @staticmethod
    def _previous_dimension_tables(
        committed: StructuredWorkMemory | None,
    ) -> dict[str, str]:
        if committed is None or committed.last_query_plan is None:
            return {}
        raw = committed.last_query_plan.get("dimension_tables")
        if raw is None:
            return {}
        if not isinstance(raw, dict) or any(
            not isinstance(field, str)
            or not field
            or not isinstance(table, str)
            or not table
            for field, table in raw.items()
        ):
            raise CommittedMemoryCorruptionError(
                "committed_memory_dimension_tables_invalid"
            )
        return dict(raw)

    @staticmethod
    def _previous_dimension_order(
        committed: StructuredWorkMemory | None,
    ) -> str | None:
        if committed is None or committed.last_query_plan is None:
            return None
        raw = committed.last_query_plan.get("dimension_order")
        return raw if raw in {"asc", "desc"} else None
