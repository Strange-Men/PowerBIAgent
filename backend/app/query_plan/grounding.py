"""Business object, member, time, and analysis grounding.

This module may interpret language, but canonical identities can only be
returned by mapping a bounded candidate ID back to the validated catalog or a
member returned by the Power BI adapter boundary.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Awaitable, Callable
from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.intent.models import IntentSpec, TimeIntentDraft, TimeIntentKind
from backend.app.llm.base import LLMProvider, LLMRequest, LLMTask
from backend.app.memory.models import PendingClarificationContext, StructuredWorkMemory
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectSource,
    SemanticObjectType,
    normalize_semantic_text,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    FilterOperator,
    QueryPlan,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


class GroundingStatus(str, Enum):
    NOT_MENTIONED = "NOT_MENTIONED"
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    EXPLICIT_CLEAR = "EXPLICIT_CLEAR"
    CONFIG_CONFLICT = "CONFIG_CONFLICT"


SemanticObjectRole = Literal[
    "measure", "dimension", "filter_field", "date_field", "ranking_dimension"
]


class ObjectGroundingResult(BaseModel):
    status: GroundingStatus
    role: SemanticObjectRole
    phrase: str = ""
    canonical_object: CatalogObject | None = None
    candidate_ids: tuple[str, ...] = ()
    method: str = ""

    model_config = ConfigDict(frozen=True)


class MemberGroundingResult(BaseModel):
    status: GroundingStatus
    field: CatalogObject
    requested_value: Any
    canonical_value: Any = None
    method: str = ""

    model_config = ConfigDict(frozen=True)


class GroundedSemanticDelta(BaseModel):
    query_shape: QueryShape | None = None
    measures: list[str] | None = None
    dimensions: list[str] | None = None
    dimension_tables: dict[str, str] = Field(default_factory=dict)
    dimension_order: Literal["asc", "desc"] | None = None
    filters: list[StructuredFilter] | None = None
    remove_filter_fields: list[str] = Field(default_factory=list)
    clear_filters: bool = False
    time_range: TimeRangeSpec | None = None
    time_specified: bool = False
    clear_time: bool = False
    sort: Literal["asc", "desc"] | None = None
    sort_specified: bool = False
    clear_sort: bool = False
    top_n: int | None = Field(default=None, ge=1)
    top_n_specified: bool = False
    clear_top_n: bool = False


class GroundingOutcome(BaseModel):
    status: GroundingStatus
    delta: GroundedSemanticDelta | None = None
    object_results: list[ObjectGroundingResult] = Field(default_factory=list)
    member_results: list[MemberGroundingResult] = Field(default_factory=list)
    clarification_question: str | None = None
    intent_disagreements: list[str] = Field(default_factory=list)
    pending_eligible: bool = True


class CandidateSelection(BaseModel):
    outcome: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED"]
    candidate_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_selection(self) -> "CandidateSelection":
        if self.outcome == "RESOLVED" and not self.candidate_id:
            raise ValueError("RESOLVED selection requires candidate_id")
        if self.outcome != "RESOLVED" and self.candidate_id is not None:
            raise ValueError("non-resolved selection cannot include candidate_id")
        return self


class BoundedLLMObjectSelector:
    """One-shot selection over code-owned candidate IDs."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    async def select(
        self,
        phrase: str,
        user_input: str,
        candidates: tuple[CatalogObject, ...],
        committed_context: str = "",
    ) -> ObjectGroundingResult:
        candidate_lines = "\n".join(
            f"- candidate_id={item.object_id}; canonical_name={item.canonical_name}; "
            f"description={item.description or '（无）'}; aliases={list(item.aliases)}"
            for item in candidates
        )
        messages = [{
            "role": "system",
            "content": (
                "你只负责在给定候选中选择用户明确指向的一个对象。"
                "不得生成对象名、DAX、QueryPlan 或业务定义。只输出一个 JSON 对象，"
                "JSON 必须符合结构："
                '{"outcome":"RESOLVED|AMBIGUOUS|UNRESOLVED",'
                '"candidate_id":"候选ID或null"}。没有充分唯一依据时必须返回 '
                "AMBIGUOUS 或 UNRESOLVED。"
            ),
        }, {
            "role": "user",
            "content": (
                f"当前短语：{phrase}\n当前输入：{user_input}\n"
                f"必要的已提交上下文：{committed_context or '（无）'}\n"
                f"候选：\n{candidate_lines}"
            ),
        }]
        response = await self._provider.generate(
            LLMRequest(messages=messages, task=LLMTask.SEMANTIC_SELECTION),
            CandidateSelection,
        )
        selection = response.structured
        if not isinstance(selection, CandidateSelection):
            return ObjectGroundingResult(
                status=GroundingStatus.UNRESOLVED,
                role="measure",
                phrase=phrase,
                method="bounded_llm_invalid",
            )
        candidate_map = {item.object_id: item for item in candidates}
        if selection.outcome == "RESOLVED":
            selected = candidate_map.get(selection.candidate_id or "")
            if selected is None:
                return ObjectGroundingResult(
                    status=GroundingStatus.UNRESOLVED,
                    role="measure",
                    phrase=phrase,
                    method="bounded_llm_unknown_candidate",
                )
            return ObjectGroundingResult(
                status=GroundingStatus.RESOLVED,
                role="measure",
                phrase=phrase,
                canonical_object=selected,
                candidate_ids=tuple(candidate_map),
                method="bounded_llm",
            )
        return ObjectGroundingResult(
            status=GroundingStatus(selection.outcome),
            role="measure",
            phrase=phrase,
            candidate_ids=tuple(candidate_map),
            method="bounded_llm",
        )


class ObjectGrounder:
    def __init__(
        self,
        catalog: SemanticCatalog,
        selector: BoundedLLMObjectSelector | None = None,
    ):
        self.catalog = catalog
        self.selector = selector

    def resolve_phrase(
        self,
        phrase: str,
        object_type: SemanticObjectType,
        role: SemanticObjectRole,
    ) -> ObjectGroundingResult:
        normalized = normalize_semantic_text(phrase)
        if not normalized:
            return ObjectGroundingResult(
                status=GroundingStatus.NOT_MENTIONED,
                role=role,
                phrase="",
                method="empty_phrase",
            )
        objects = self.catalog.by_type(object_type)

        canonical = [
            obj for obj in objects
            if normalize_semantic_text(obj.canonical_name) == normalized
        ]
        if len(canonical) == 1:
            return self._resolved(role, phrase, canonical[0], "canonical_exact")
        if len(canonical) > 1:
            return self._ambiguous(role, phrase, canonical, "canonical_conflict")

        conflict_ids = self.catalog.alias_conflicts.get(normalized)
        if conflict_ids:
            return ObjectGroundingResult(
                status=GroundingStatus.CONFIG_CONFLICT,
                role=role,
                phrase=phrase,
                candidate_ids=conflict_ids,
                method="alias_conflict",
            )
        aliases = [
            obj for obj in objects
            if normalized in {normalize_semantic_text(alias) for alias in obj.aliases}
        ]
        if len(aliases) == 1:
            return self._resolved(role, phrase, aliases[0], "alias_exact")
        if len(aliases) > 1:
            return self._ambiguous(role, phrase, aliases, "alias_conflict")

        descriptions = [
            obj for obj in objects
            if obj.description
            and normalize_semantic_text(obj.description) == normalized
        ]
        if len(descriptions) == 1:
            return self._resolved(role, phrase, descriptions[0], "description_exact")
        if len(descriptions) > 1:
            return self._ambiguous(role, phrase, descriptions, "description_conflict")
        return ObjectGroundingResult(
            status=GroundingStatus.UNRESOLVED,
            role=role,
            phrase=phrase,
            method="deterministic_no_match",
        )

    def find_mentions(
        self,
        text: str,
        object_type: SemanticObjectType,
        role: SemanticObjectRole,
    ) -> ObjectGroundingResult:
        normalized_text = normalize_semantic_text(text)
        matched: dict[str, CatalogObject] = {}
        conflict_ids: set[str] = set()
        matched_terms: list[str] = []
        for obj in self.catalog.by_type(object_type):
            terms = (obj.canonical_name, *obj.aliases)
            for term in terms:
                normalized_term = normalize_semantic_text(term)
                if normalized_term and normalized_term in normalized_text:
                    conflict_ids.update(
                        self.catalog.alias_conflicts.get(normalized_term, ())
                    )
                    matched[obj.object_id] = obj
                    matched_terms.append(term)
        if conflict_ids:
            return ObjectGroundingResult(
                status=GroundingStatus.CONFIG_CONFLICT,
                role=role,
                phrase=text,
                candidate_ids=tuple(sorted(conflict_ids)),
                method="mentioned_alias_conflict",
            )
        if len(matched) == 1:
            return self._resolved(
                role, ", ".join(matched_terms), next(iter(matched.values())),
                "current_input_mention",
            )
        if len(matched) > 1:
            return self._ambiguous(
                role, text, tuple(matched.values()), "multiple_current_mentions"
            )
        return ObjectGroundingResult(
            status=GroundingStatus.NOT_MENTIONED,
            role=role,
            phrase="",
            method="no_current_mention",
        )

    async def select_bounded(
        self,
        phrase: str,
        user_input: str,
        object_type: SemanticObjectType,
        role: SemanticObjectRole,
        committed_context: str = "",
    ) -> ObjectGroundingResult:
        if self.selector is None:
            return ObjectGroundingResult(
                status=GroundingStatus.UNRESOLVED, role=role, phrase=phrase
            )
        candidates, unique_best_id = self._evidence_candidates(
            user_input, object_type
        )
        if not candidates:
            return ObjectGroundingResult(
                status=GroundingStatus.UNRESOLVED,
                role=role,
                phrase=phrase,
                method="bounded_llm_no_metadata_evidence",
            )
        if unique_best_id is None:
            return ObjectGroundingResult(
                status=GroundingStatus.AMBIGUOUS,
                role=role,
                phrase=phrase,
                candidate_ids=tuple(item.object_id for item in candidates),
                method="bounded_llm_evidence_tie",
            )
        result = await self.selector.select(
            phrase, user_input, candidates, committed_context
        )
        if (
            result.status == GroundingStatus.RESOLVED
            and result.canonical_object is not None
            and result.canonical_object.object_id != unique_best_id
        ):
            return ObjectGroundingResult(
                status=GroundingStatus.AMBIGUOUS,
                role=role,
                phrase=phrase,
                candidate_ids=tuple(item.object_id for item in candidates),
                method="bounded_llm_conflicts_with_metadata_evidence",
            )
        return result.model_copy(update={"role": role})

    def _evidence_candidates(
        self,
        user_input: str,
        object_type: SemanticObjectType,
    ) -> tuple[tuple[CatalogObject, ...], str | None]:
        """Return a metadata-backed shortlist and its unique strongest ID.

        Exact canonical names and approved aliases are resolved before this
        method.  The selector is therefore limited to conservative partial
        metadata evidence; an unknown phrase never receives the whole catalog
        as a forced-choice menu.  Equal strongest evidence remains ambiguous.
        """

        normalized_input = normalize_semantic_text(user_input)
        scored: list[tuple[tuple[int, float], CatalogObject]] = []
        for obj in self.catalog.by_type(object_type):
            best = (0, 0.0)
            for term in (obj.canonical_name, *obj.aliases, obj.description or ""):
                normalized_term = normalize_semantic_text(term)
                if not normalized_term:
                    continue
                common = self._longest_common_substring(
                    normalized_input, normalized_term
                )
                minimum = 3 if self._contains_cjk(normalized_term) else 4
                ratio = common / len(normalized_term)
                if common >= minimum and ratio >= 0.5:
                    best = max(best, (common, ratio))
            if best[0] > 0:
                scored.append((best, obj))
        if not scored:
            return (), None
        scored.sort(key=lambda item: (item[0], item[1].object_id), reverse=True)
        best_score = scored[0][0]
        best_ids = [obj.object_id for score, obj in scored if score == best_score]
        return (
            tuple(obj for _, obj in scored),
            best_ids[0] if len(best_ids) == 1 else None,
        )

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in value)

    @staticmethod
    def _longest_common_substring(left: str, right: str) -> int:
        if not left or not right:
            return 0
        previous = [0] * (len(right) + 1)
        longest = 0
        for left_char in left:
            current = [0]
            for index, right_char in enumerate(right, start=1):
                value = previous[index - 1] + 1 if left_char == right_char else 0
                current.append(value)
                longest = max(longest, value)
            previous = current
        return longest

    @staticmethod
    def _resolved(
        role: SemanticObjectRole,
        phrase: str,
        obj: CatalogObject,
        method: str,
    ) -> ObjectGroundingResult:
        return ObjectGroundingResult(
            status=GroundingStatus.RESOLVED,
            role=role,
            phrase=phrase,
            canonical_object=obj,
            candidate_ids=(obj.object_id,),
            method=method,
        )

    @staticmethod
    def _ambiguous(
        role: SemanticObjectRole,
        phrase: str,
        objects: tuple[CatalogObject, ...] | list[CatalogObject],
        method: str,
    ) -> ObjectGroundingResult:
        return ObjectGroundingResult(
            status=GroundingStatus.AMBIGUOUS,
            role=role,
            phrase=phrase,
            candidate_ids=tuple(obj.object_id for obj in objects),
            method=method,
        )


class MemberGrounder:
    @staticmethod
    def resolve(
        field: CatalogObject,
        requested_value: Any,
        members: ColumnMembersResult,
    ) -> MemberGroundingResult:
        exact = [value for value in members.values if value == requested_value]
        if len(exact) == 1:
            return MemberGroundingResult(
                status=GroundingStatus.RESOLVED,
                field=field,
                requested_value=requested_value,
                canonical_value=exact[0],
                method="runtime_exact",
            )
        if len(exact) > 1:
            return MemberGroundingResult(
                status=GroundingStatus.AMBIGUOUS,
                field=field,
                requested_value=requested_value,
                method="runtime_duplicate_exact",
            )
        if isinstance(requested_value, str):
            normalized = normalize_semantic_text(requested_value)
            matches = [
                value for value in members.values
                if isinstance(value, str)
                and normalize_semantic_text(value) == normalized
            ]
            if len(matches) == 1:
                return MemberGroundingResult(
                    status=GroundingStatus.RESOLVED,
                    field=field,
                    requested_value=requested_value,
                    canonical_value=matches[0],
                    method="runtime_normalized",
                )
            if len(matches) > 1:
                return MemberGroundingResult(
                    status=GroundingStatus.AMBIGUOUS,
                    field=field,
                    requested_value=requested_value,
                    method="runtime_normalized_ambiguous",
                )
            alias_target = field.member_aliases.get(normalized)
            if alias_target is not None:
                alias_matches = [
                    value
                    for value in members.values
                    if isinstance(value, str)
                    and normalize_semantic_text(value)
                    == normalize_semantic_text(alias_target)
                ]
                if len(alias_matches) == 1:
                    return MemberGroundingResult(
                        status=GroundingStatus.RESOLVED,
                        field=field,
                        requested_value=requested_value,
                        canonical_value=alias_matches[0],
                        method="glossary_alias_runtime_verified",
                    )
                if len(alias_matches) > 1:
                    return MemberGroundingResult(
                        status=GroundingStatus.AMBIGUOUS,
                        field=field,
                        requested_value=requested_value,
                        method="glossary_alias_runtime_ambiguous",
                    )
        return MemberGroundingResult(
            status=GroundingStatus.UNRESOLVED,
            field=field,
            requested_value=requested_value,
            method="runtime_no_match",
        )


class TimeGrounder:
    _RECENT_MONTHS = re.compile(r"最近\s*(\d+)\s*个?月")
    _ABSOLUTE_MONTH = re.compile(
        r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月(?:份)?"
    )
    _NUMERIC_MONTH = re.compile(
        r"(?<!\d)(\d{4})\s*[-/]\s*(0?[1-9]|1[0-2])(?!\s*[-/]?\s*\d)"
    )
    _RELATIVE_NAMED_MONTH = re.compile(
        r"(?P<relative>今年|去年)\s*"
        r"(?P<month>十[一二]|十二|十|[一二三四五六七八九]|\d{1,2})"
        r"\s*月(?:份)?"
    )
    _QUARTER = re.compile(
        r"(?:(?P<year>\d{4})\s*年|(?P<relative>今年|去年))?\s*"
        r"(?:第?\s*(?P<quarter>[一二三四1-4])\s*季度|"
        r"q\s*(?P<q_quarter>[1-4]))"
    )
    _ABSOLUTE_YEAR = re.compile(r"(?<!\d)(\d{4})\s*年")
    _ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
    _CHINESE_NUMBER = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
        "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
    }

    def __init__(self, today: Callable[[], date] = date.today):
        self._today = today

    def ground(
        self,
        user_input: str,
        date_field: CatalogObject | None,
        time_intent: TimeIntentDraft | None = None,
    ) -> TimeRangeSpec | None:
        if date_field is None:
            return None
        normalized_input = normalize_semantic_text(user_input)
        today = self._today()
        bounded_month = self._bounded_month_range(normalized_input, date_field)
        if bounded_month is not None or self._has_bounded_month_expression(
            normalized_input
        ):
            return bounded_month
        absolute_month = self._ABSOLUTE_MONTH.search(normalized_input)
        if absolute_month:
            return self._month_range(
                date_field, int(absolute_month.group(1)), int(absolute_month.group(2))
            )
        numeric_month = self._NUMERIC_MONTH.search(normalized_input)
        if numeric_month:
            return self._month_range(
                date_field, int(numeric_month.group(1)), int(numeric_month.group(2))
            )
        relative_named_month = self._RELATIVE_NAMED_MONTH.search(normalized_input)
        if relative_named_month:
            month = self._parse_number(relative_named_month.group("month"))
            if month is not None:
                offset = -1 if relative_named_month.group("relative") == "去年" else 0
                return self._month_range(date_field, today.year + offset, month)
        quarter_match = self._QUARTER.search(normalized_input)
        if quarter_match:
            quarter = self._parse_number(
                quarter_match.group("quarter") or quarter_match.group("q_quarter")
            )
            raw_year = quarter_match.group("year")
            relative = quarter_match.group("relative")
            year = (
                int(raw_year) if raw_year else today.year - 1
                if relative == "去年" else today.year
            )
            if quarter is not None:
                return self._quarter_range(date_field, year, quarter)
        if "上个月" in normalized_input or "上月" in normalized_input:
            year, month = self._shift_month(today.year, today.month, -1)
            return self._month_range(date_field, year, month)
        if "本月" in normalized_input:
            return self._month_range(
                date_field, today.year, today.month, mode=TimeRangeMode.CURRENT_MONTH
            )
        if "今年" in normalized_input:
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31),
                mode=TimeRangeMode.CURRENT_YEAR,
                grain="year",
            )
        if "去年" in normalized_input:
            previous_year = today.year - 1
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(previous_year, 1, 1),
                end_date=date(previous_year, 12, 31),
                mode=TimeRangeMode.EXPLICIT_RANGE,
                grain="year",
            )
        recent = self._RECENT_MONTHS.search(normalized_input)
        recent_count = 6 if "最近半年" in normalized_input else None
        if recent:
            recent_count = int(recent.group(1))
        if recent_count is not None:
            count = recent_count
            if count < 1:
                return None
            start_year, start_month = self._shift_month(
                today.year, today.month, -(count - 1)
            )
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(start_year, start_month, 1),
                end_date=today.replace(
                    day=calendar.monthrange(today.year, today.month)[1]
                ),
                mode=TimeRangeMode.RECENT_MONTHS,
                grain="month",
            )
        dates = self._ISO_DATE.findall(normalized_input)
        if len(dates) == 2:
            try:
                start, end = (date.fromisoformat(item) for item in dates)
                return TimeRangeSpec(
                    date_field=date_field.canonical_name,
                    start_date=start,
                    end_date=end,
                    mode=TimeRangeMode.EXPLICIT_RANGE,
                )
            except ValueError:
                return None
        absolute_year = self._ABSOLUTE_YEAR.search(normalized_input)
        if absolute_year:
            return self._year_range(date_field, int(absolute_year.group(1)))
        if self._draft_has_current_evidence(normalized_input, time_intent):
            return self._resolve_draft(time_intent, date_field, today)
        return None

    @classmethod
    def is_explicit(
        cls, user_input: str, time_intent: TimeIntentDraft | None = None
    ) -> bool:
        normalized_input = normalize_semantic_text(user_input)
        return bool(
            "本月" in normalized_input
            or "上个月" in normalized_input
            or "上月" in normalized_input
            or "今年" in normalized_input
            or "去年" in normalized_input
            or "最近半年" in normalized_input
            or cls._ABSOLUTE_MONTH.search(normalized_input)
            or cls._NUMERIC_MONTH.search(normalized_input)
            or cls._RELATIVE_NAMED_MONTH.search(normalized_input)
            or cls._QUARTER.search(normalized_input)
            or cls._RECENT_MONTHS.search(normalized_input)
            or cls._ABSOLUTE_YEAR.search(normalized_input)
            or len(cls._ISO_DATE.findall(normalized_input)) == 2
            or cls._draft_has_current_evidence(normalized_input, time_intent)
        )

    @staticmethod
    def _draft_has_current_evidence(
        user_input: str, time_intent: TimeIntentDraft | None
    ) -> bool:
        if time_intent is None:
            return False
        expression = normalize_semantic_text(time_intent.expression)
        return bool(expression and expression in normalize_semantic_text(user_input))

    def _resolve_draft(
        self,
        draft: TimeIntentDraft | None,
        date_field: CatalogObject,
        today: date,
    ) -> TimeRangeSpec | None:
        if draft is None:
            return None
        if draft.kind == TimeIntentKind.ABSOLUTE_MONTH:
            return self._month_range(date_field, draft.year or 0, draft.month or 0)
        if draft.kind == TimeIntentKind.ABSOLUTE_YEAR:
            year = draft.year or 0
            return self._year_range(date_field, year)
        if draft.kind == TimeIntentKind.RELATIVE_MONTH:
            year, month = self._shift_month(
                today.year, today.month, draft.relative_offset or 0
            )
            return self._month_range(date_field, year, month)
        if draft.kind == TimeIntentKind.RELATIVE_YEAR:
            return self._year_range(
                date_field, today.year + (draft.relative_offset or 0)
            )
        if draft.kind == TimeIntentKind.QUARTER:
            year = draft.year
            if year is None:
                year = today.year + (draft.relative_offset or 0)
            return self._quarter_range(date_field, year, draft.quarter or 0)
        if draft.kind == TimeIntentKind.RECENT_MONTHS:
            count = draft.months or 0
            if count < 1:
                return None
            start_year, start_month = self._shift_month(
                today.year, today.month, -(count - 1)
            )
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(start_year, start_month, 1),
                end_date=date(
                    today.year,
                    today.month,
                    calendar.monthrange(today.year, today.month)[1],
                ),
                mode=TimeRangeMode.RECENT_MONTHS,
                grain="month",
            )
        if draft.kind == TimeIntentKind.BOUNDED_RANGE:
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=draft.start_date,
                end_date=draft.end_date,
                mode=TimeRangeMode.EXPLICIT_RANGE,
            )
        return None

    @staticmethod
    def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
        zero_based = year * 12 + (month - 1) + offset
        shifted_year, shifted_month = divmod(zero_based, 12)
        return shifted_year, shifted_month + 1

    @staticmethod
    def _month_range(
        date_field: CatalogObject,
        year: int,
        month: int,
        *,
        mode: TimeRangeMode = TimeRangeMode.EXPLICIT_RANGE,
    ) -> TimeRangeSpec | None:
        if year < 1 or not 1 <= month <= 12:
            return None
        return TimeRangeSpec(
            date_field=date_field.canonical_name,
            start_date=date(year, month, 1),
            end_date=date(year, month, calendar.monthrange(year, month)[1]),
            mode=mode,
            grain="month",
        )

    @staticmethod
    def _year_range(date_field: CatalogObject, year: int) -> TimeRangeSpec | None:
        if year < 1:
            return None
        return TimeRangeSpec(
            date_field=date_field.canonical_name,
            start_date=date(year, 1, 1),
            end_date=date(year, 12, 31),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="year",
        )

    @staticmethod
    def _quarter_range(
        date_field: CatalogObject, year: int, quarter: int
    ) -> TimeRangeSpec | None:
        if year < 1 or not 1 <= quarter <= 4:
            return None
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        return TimeRangeSpec(
            date_field=date_field.canonical_name,
            start_date=date(year, start_month, 1),
            end_date=date(year, end_month, calendar.monthrange(year, end_month)[1]),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        )

    @classmethod
    def _parse_number(cls, value: str) -> int | None:
        if value.isdigit():
            return int(value)
        return cls._CHINESE_NUMBER.get(value)

    def _bounded_month_range(
        self,
        user_input: str,
        date_field: CatalogObject,
    ) -> TimeRangeSpec | None:
        matches: list[tuple[int, int, int, int]] = []
        for pattern in (self._ABSOLUTE_MONTH, self._NUMERIC_MONTH):
            for match in pattern.finditer(user_input):
                matches.append((
                    match.start(), match.end(),
                    int(match.group(1)), int(match.group(2)),
                ))
        matches.sort()
        if len(matches) < 2:
            return None
        first, second = matches[0], matches[1]
        if not re.search(r"(?:到|至|~|～)", user_input[first[1]:second[0]]):
            return None
        start_year, start_month = first[2], first[3]
        end_year, end_month = second[2], second[3]
        if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
            return None
        start = date(start_year, start_month, 1)
        end = date(
            end_year,
            end_month,
            calendar.monthrange(end_year, end_month)[1],
        )
        if start > end:
            return None
        return TimeRangeSpec(
            date_field=date_field.canonical_name,
            start_date=start,
            end_date=end,
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        )

    def _has_bounded_month_expression(self, user_input: str) -> bool:
        spans = sorted([
            *(match.span() for match in self._ABSOLUTE_MONTH.finditer(user_input)),
            *(match.span() for match in self._NUMERIC_MONTH.finditer(user_input)),
        ])
        return bool(
            len(spans) >= 2
            and re.search(r"(?:到|至|~|～)", user_input[spans[0][1]:spans[1][0]])
        )


MemberLookup = Callable[[CatalogObject, int], Awaitable[ColumnMembersResult]]


class SemanticGroundingService:
    """Orchestrate grounding without owning Turn or Memory writes."""

    _RANKING_NUMBER = r"(?:\d+|[零〇一二两三四五六七八九十百]+)"
    _TOP_N = re.compile(
        rf"(?:前\s*(?P<front>{_RANKING_NUMBER})\s*个?|"
        rf"top\s*(?P<top>{_RANKING_NUMBER})|"
        rf"(?:最高|最大|最多|最低|最小|最少)(?:的)?\s*"
        rf"(?P<extreme>{_RANKING_NUMBER})\s*个?)",
        re.IGNORECASE,
    )
    _CHINESE_DIGITS = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }

    def __init__(
        self,
        catalog: SemanticCatalog,
        *,
        selector: BoundedLLMObjectSelector | None = None,
        today: Callable[[], date] = date.today,
    ):
        self.catalog = catalog
        self.objects = ObjectGrounder(catalog, selector)
        self.time = TimeGrounder(today)

    async def ground(
        self,
        user_input: str,
        intent: IntentSpec,
        draft: QueryPlan,
        committed: StructuredWorkMemory | None,
        member_lookup: MemberLookup,
        pending: PendingClarificationContext | None = None,
        query_shape: QueryShape | None = None,
    ) -> GroundingOutcome:
        object_results: list[ObjectGroundingResult] = []
        member_results: list[MemberGroundingResult] = []
        disagreements: list[str] = []
        effective_shape = (
            query_shape
            or draft.query_shape
            or self._committed_query_shape(committed)
            or QueryShape.SCALAR
        )
        delta = GroundedSemanticDelta(query_shape=effective_shape)

        measure_required = effective_shape != QueryShape.ENTITY_LIST
        measure = (
            self.objects.find_mentions(
                user_input, SemanticObjectType.MEASURE, "measure"
            )
            if measure_required
            else ObjectGroundingResult(
                status=GroundingStatus.NOT_MENTIONED,
                role="measure",
                method="query_shape_does_not_require_measure",
            )
        )
        if measure_required and measure.status == GroundingStatus.NOT_MENTIONED:
            weak_measure_phrases = self._current_weak_phrases(
                [*intent.detected_measures, *draft.measures], user_input
            )
            if weak_measure_phrases:
                measure = self._resolve_unique_weak(
                    weak_measure_phrases, SemanticObjectType.MEASURE, "measure"
                )
            elif (
                intent.detected_measures or draft.measures
            ) and not self._signals_only_repeat_inherited_measure(
                intent, draft, committed, pending, user_input
            ):
                # Intent/QueryPlan remain weak signals: they may prove that the
                # current turn expresses a measure requirement, but may not
                # provide the canonical identity.  The identity must still be
                # selected from catalog-owned candidate IDs.
                measure = ObjectGroundingResult(
                    status=GroundingStatus.UNRESOLVED,
                    role="measure",
                    phrase=user_input,
                    method="current_linguistic_measure_signal",
                )
        if measure_required and measure.status == GroundingStatus.UNRESOLVED:
            measure = await self.objects.select_bounded(
                measure.phrase,
                user_input,
                SemanticObjectType.MEASURE,
                "measure",
            )
        object_results.append(measure)
        measure_blocked = measure_required and self._requires_clarification(measure)
        if measure.status == GroundingStatus.RESOLVED and measure.canonical_object:
            delta.measures = [measure.canonical_object.canonical_name]
            if (
                intent.detected_measures
                and measure.canonical_object.canonical_name
                not in intent.detected_measures
            ):
                disagreements.append("intent_measure_disagrees_with_grounding")
        elif measure_required and measure.status == GroundingStatus.NOT_MENTIONED and not (
            (pending and pending.measures) or (committed and committed.measures)
        ):
            measure_blocked = True

        raw_filters = [
            item for item in draft.filters
            if self._value_is_current(item.value, user_input)
            if not self._filter_is_explicit_grouping(item, user_input)
        ]
        if not raw_filters and effective_shape != QueryShape.ENTITY_LIST:
            raw_filters = [
                StructuredFilter(
                    field=item.field,
                    operator=FilterOperator(item.operator.value),
                    value=item.value,
                )
                for item in intent.detected_filters
                if item.operator.value == FilterOperator.EQ.value
                and self._value_is_current(item.value, user_input)
                and not self._filter_is_explicit_grouping(item, user_input)
            ]
        if effective_shape in {
            QueryShape.MEMBER_SET,
            QueryShape.FILTERED_AGGREGATION,
        }:
            # Combined values in an LLM draft are never canonical member sets.
            # Resolve every literal independently against one runtime field.
            raw_filters = []
        grounded_filters: list[StructuredFilter] = []
        grounded_filter_ids: set[str] = set()
        if not raw_filters:
            (
                discovered_filters,
                discovered_objects,
                discovered_members,
                discovery_ambiguous,
                discovery_unresolved,
            ) = await self._discover_runtime_member_filters(
                user_input,
                committed,
                member_lookup,
                allow_member_set=effective_shape in {
                    QueryShape.MEMBER_SET,
                    QueryShape.FILTERED_AGGREGATION,
                },
            )
            object_results.extend(discovered_objects)
            member_results.extend(discovered_members)
            if discovery_ambiguous:
                return self._clarification(
                    GroundingStatus.AMBIGUOUS,
                    object_results,
                    member_results,
                    "筛选值无法唯一匹配模型中的成员，请明确选择。",
                    disagreements,
                )
            if discovery_unresolved:
                return self._clarification(
                    GroundingStatus.UNRESOLVED,
                    object_results,
                    member_results,
                    "筛选值未匹配模型中的任何成员，请确认后重试。",
                    disagreements,
                )
            grounded_filters.extend(discovered_filters)
            for item in discovered_objects:
                if item.canonical_object is not None:
                    grounded_filter_ids.add(item.canonical_object.object_id)
                    delta.dimension_tables[
                        item.canonical_object.canonical_name
                    ] = item.canonical_object.table_name
        for raw_filter in raw_filters:
            if raw_filter.operator != FilterOperator.EQ:
                return self._clarification(
                    GroundingStatus.UNRESOLVED, object_results, member_results,
                    "当前仅支持等值筛选，请改为明确的等值条件。", disagreements,
                    pending_eligible=False,
                )
            draft_field = self.objects.resolve_phrase(
                raw_filter.field, SemanticObjectType.FIELD, "filter_field"
            )
            draft_field_mentioned = any(
                normalize_semantic_text(term) in normalize_semantic_text(user_input)
                for term in (
                    raw_filter.field,
                    *(
                        draft_field.canonical_object.aliases
                        if draft_field.canonical_object else ()
                    ),
                )
            )
            mentioned_field = self.objects.find_mentions(
                user_input, SemanticObjectType.FIELD, "filter_field"
            )
            if mentioned_field.status == GroundingStatus.AMBIGUOUS:
                non_grouping = [
                    self.catalog.get(object_id)
                    for object_id in mentioned_field.candidate_ids
                ]
                non_grouping = [
                    item for item in non_grouping
                    if item is not None
                    and not self._field_has_dimension_cue(user_input, item)
                ]
                if len(non_grouping) == 1:
                    mentioned_field = ObjectGrounder._resolved(
                        "filter_field",
                        user_input,
                        non_grouping[0],
                        "current_input_non_grouping",
                    )
            if mentioned_field.status != GroundingStatus.NOT_MENTIONED:
                field_result = mentioned_field
            elif member_candidates := self._member_evidence_fields(user_input):
                if len(member_candidates) == 1:
                    field_result = ObjectGrounder._resolved(
                        "filter_field",
                        str(raw_filter.value),
                        member_candidates[0],
                        "model_scoped_member_evidence",
                    )
                else:
                    field_result = ObjectGrounder._ambiguous(
                        "filter_field",
                        str(raw_filter.value),
                        member_candidates,
                        "model_scoped_member_evidence_ambiguous",
                    )
            elif draft_field_mentioned:
                # Unknown phrases are current requirements too; preserve their
                # UNRESOLVED status instead of treating them as omission.
                field_result = draft_field
            elif (
                committed
                and committed.filters
                and len({str(item.get("field")) for item in committed.filters}) == 1
            ):
                committed_field = str(committed.filters[0].get("field"))
                field_result = self.objects.resolve_phrase(
                    committed_field,
                    SemanticObjectType.FIELD,
                    "filter_field",
                )
            elif committed and len(committed.dimensions) == 1:
                # A member-only refinement may use the sole committed grouping
                # field as its bounded field candidate.  The value is still
                # accepted only after runtime member lookup; multiple dimensions
                # remain ambiguous and never reach execution.
                field_result = self.objects.resolve_phrase(
                    committed.dimensions[0],
                    SemanticObjectType.FIELD,
                    "filter_field",
                )
            else:
                field_result = ObjectGroundingResult(
                    status=GroundingStatus.NOT_MENTIONED,
                    role="filter_field",
                    method="filter_field_not_mentioned",
                )
            if (
                field_result.status == GroundingStatus.AMBIGUOUS
                and committed is not None
                and committed.last_query_plan is not None
            ):
                raw_hints = committed.last_query_plan.get("dimension_tables")
                if isinstance(raw_hints, dict):
                    matching = [
                        candidate
                        for object_id in field_result.candidate_ids
                        if (candidate := self.catalog.get(object_id)) is not None
                        and raw_hints.get(candidate.canonical_name)
                        == candidate.table_name
                    ]
                    if len(matching) == 1:
                        field_result = ObjectGrounder._resolved(
                            "filter_field",
                            user_input,
                            matching[0],
                            "committed_canonical_table_owner",
                        )
            object_results.append(field_result)
            if self._requires_clarification(field_result) or not field_result.canonical_object:
                return self._clarification(
                    field_result.status, object_results, member_results,
                    "请明确要筛选的字段。", disagreements,
                )
            field = field_result.canonical_object
            grounded_filter_ids.add(field.object_id)
            delta.dimension_tables[field.canonical_name] = field.table_name
            members = await member_lookup(field, 100)
            member = MemberGrounder.resolve(field, raw_filter.value, members)
            member_results.append(member)
            if member.status != GroundingStatus.RESOLVED:
                return self._clarification(
                    member.status, object_results, member_results,
                    "筛选值无法唯一匹配模型中的成员，请明确选择。", disagreements,
                )
            grounded_filters.append(StructuredFilter(
                field=field.canonical_name,
                operator=FilterOperator.EQ,
                value=member.canonical_value,
            ))
        if grounded_filters:
            delta.filters = grounded_filters

        dimension_role: SemanticObjectRole = (
            "ranking_dimension"
            if effective_shape == QueryShape.RANKING
            else "dimension"
        )
        current_dimension = self.objects.find_mentions(
            user_input, SemanticObjectType.FIELD, dimension_role
        )
        if (
            effective_shape in {
                QueryShape.GROUPED,
                QueryShape.RANKING,
                QueryShape.TREND,
                QueryShape.BOUNDED_TREND,
            }
            and current_dimension.status == GroundingStatus.NOT_MENTIONED
            and committed is not None
            and len(committed.dimensions) == 1
        ):
            inherited_dimension = next(
                (
                    item
                    for item in self.catalog.by_type(SemanticObjectType.FIELD)
                    if item.canonical_name == committed.dimensions[0]
                ),
                None,
            )
            if inherited_dimension is not None:
                current_dimension = ObjectGrounder._resolved(
                    dimension_role,
                    user_input,
                    inherited_dimension,
                    "committed_unique_shape_dimension",
                )
        if (
            effective_shape == QueryShape.MEMBER_SET
            and current_dimension.status == GroundingStatus.NOT_MENTIONED
            and len(grounded_filter_ids) == 1
        ):
            member_field = self.catalog.get(next(iter(grounded_filter_ids)))
            if member_field is not None:
                current_dimension = ObjectGrounder._resolved(
                    dimension_role,
                    user_input,
                    member_field,
                    "member_set_filter_field",
                )
        weak_dimension_phrases = self._current_weak_phrases(
            [*intent.detected_dimensions, *draft.dimensions], user_input
        )
        dimension_requested = self._has_dimension_cue(
            user_input, current_dimension
        ) or any(
            self._has_dimension_phrase_cue(user_input, phrase)
            for phrase in weak_dimension_phrases
        ) or effective_shape in {
            QueryShape.ENTITY_LIST,
            QueryShape.GROUPED,
            QueryShape.RANKING,
            QueryShape.MEMBER_SET,
        }
        if dimension_requested:
            dimension = current_dimension
            if dimension.status == GroundingStatus.AMBIGUOUS and grounded_filter_ids:
                remaining = [
                    self.catalog.get(item)
                    for item in dimension.candidate_ids
                    if item not in grounded_filter_ids
                ]
                remaining = [item for item in remaining if item is not None]
                if len(remaining) == 1:
                    dimension = ObjectGrounder._resolved(
                        dimension_role,
                        user_input,
                        remaining[0],
                        "current_input_non_filter",
                    )
            if dimension.status == GroundingStatus.NOT_MENTIONED:
                dimension = self._resolve_unique_weak(
                    weak_dimension_phrases,
                    SemanticObjectType.FIELD,
                    dimension_role,
                )
            if dimension.status == GroundingStatus.UNRESOLVED:
                dimension = await self.objects.select_bounded(
                    dimension.phrase,
                    user_input,
                    SemanticObjectType.FIELD,
                    dimension_role,
                )
            object_results.append(dimension)
            if self._requires_clarification(dimension) or not dimension.canonical_object:
                return self._clarification(
                    dimension.status, object_results, member_results,
                    "请明确分析维度。", disagreements,
                )
            delta.dimensions = [dimension.canonical_object.canonical_name]
            delta.dimension_tables[
                dimension.canonical_object.canonical_name
            ] = dimension.canonical_object.table_name
        else:
            object_results.append(ObjectGroundingResult(
                status=GroundingStatus.NOT_MENTIONED,
                role="dimension",
                method="no_dimension_requirement",
            ))

        grouping_grain = self._temporal_grouping_grain(user_input)
        if grouping_grain is not None:
            grouping_fields = [
                obj
                for obj in self.catalog.by_type(SemanticObjectType.FIELD)
                if obj.temporal_grouping is not None
                and obj.temporal_grouping.grain == grouping_grain
            ]
            if len(grouping_fields) != 1:
                status = (
                    GroundingStatus.AMBIGUOUS
                    if len(grouping_fields) > 1
                    else GroundingStatus.UNRESOLVED
                )
                object_results.append(ObjectGroundingResult(
                    status=status,
                    role="dimension",
                    phrase=user_input,
                    candidate_ids=tuple(item.object_id for item in grouping_fields),
                    method="temporal_grouping_binding_cardinality",
                ))
                return self._clarification(
                    status,
                    object_results,
                    member_results,
                    "当前模型无法唯一支持请求的时间分组。",
                    disagreements,
                    pending_eligible=False,
                )
            grouping_field = grouping_fields[0]
            dimensions = list(delta.dimensions or [])
            if grouping_field.canonical_name not in dimensions:
                dimensions.append(grouping_field.canonical_name)
            delta.dimensions = dimensions
            delta.dimension_tables[grouping_field.canonical_name] = (
                grouping_field.table_name
            )
            delta.dimension_order = "asc"
            object_results.append(ObjectGrounder._resolved(
                "dimension",
                user_input,
                grouping_field,
                "runtime_temporal_grouping_binding",
            ))

        if self.time.is_explicit(user_input, intent.time_intent):
            date_result = self._resolve_date_field(user_input)
            if self._requires_clarification(date_result):
                object_results.append(date_result)
                return self._clarification(
                    date_result.status, object_results, member_results,
                    "请明确要使用的日期字段。", disagreements,
                )
            object_results.append(date_result)
            date_field = date_result.canonical_object
            if date_field is None:
                return self._clarification(
                    GroundingStatus.UNRESOLVED,
                    object_results,
                    member_results,
                    "请明确要使用的日期字段。",
                    disagreements,
                )
            time_range = self.time.ground(
                user_input, date_field, intent.time_intent
            )
            if time_range is None:
                return self._clarification(
                    GroundingStatus.UNRESOLVED, object_results, member_results,
                    "时间范围无法确定，请提供明确日期。", disagreements,
                )
            delta.time_range = time_range
            delta.time_specified = True
            delta.dimension_tables[
                date_field.canonical_name
            ] = date_field.table_name

        self._ground_analysis(user_input, draft, delta)
        if measure_blocked:
            return self._clarification(
                measure.status,
                object_results,
                member_results,
                (
                    "请明确用于判断排名的业务指标。"
                    if effective_shape == QueryShape.RANKING
                    else "请明确您要查询的业务指标。"
                ),
                disagreements,
                delta=(delta if effective_shape != QueryShape.SCALAR else None),
            )
        if delta.clear_time:
            object_results.append(ObjectGroundingResult(
                status=GroundingStatus.EXPLICIT_CLEAR,
                role="date_field",
                method="explicit_time_clear",
            ))
        current_comparison = any(
            term in normalize_semantic_text(user_input)
            for term in ("同比", "环比", "对比", "比较")
        )
        if current_comparison:
            return self._clarification(
                GroundingStatus.UNRESOLVED, object_results, member_results,
                "当前尚未支持该对比口径，请改为单一时间范围查询。", disagreements,
                pending_eligible=False,
            )
        return GroundingOutcome(
            status=GroundingStatus.RESOLVED,
            delta=delta,
            object_results=object_results,
            member_results=member_results,
            intent_disagreements=disagreements,
        )

    def _resolve_date_field(self, user_input: str) -> ObjectGroundingResult:
        date_fields = tuple(
            obj
            for obj in self.catalog.by_type(SemanticObjectType.FIELD)
            if (
                "date" in obj.data_type.casefold()
                or "time" in obj.data_type.casefold()
            )
            and obj.temporal_grouping is None
        )
        if not date_fields:
            return ObjectGroundingResult(
                status=GroundingStatus.UNRESOLVED,
                role="date_field",
                phrase=user_input,
                method="runtime_date_field_missing",
            )

        normalized_input = normalize_semantic_text(user_input)
        scored_mentions: list[tuple[int, str, CatalogObject]] = []
        for obj in date_fields:
            terms = (
                obj.canonical_name,
                obj.display_name or "",
                *obj.aliases,
            )
            for term in terms:
                normalized_term = normalize_semantic_text(term)
                if normalized_term and normalized_term in normalized_input:
                    scored_mentions.append((len(normalized_term), normalized_term, obj))
        if scored_mentions:
            strongest = max(score for score, _, _ in scored_mentions)
            strongest_mentions = [
                (term, obj)
                for score, term, obj in scored_mentions
                if score == strongest
            ]
            mentioned = {
                obj.object_id: obj for _, obj in strongest_mentions
            }
            conflict_ids = {
                object_id
                for term, _ in strongest_mentions
                for object_id in self.catalog.alias_conflicts.get(term, ())
            }
            if conflict_ids:
                return ObjectGroundingResult(
                    status=GroundingStatus.CONFIG_CONFLICT,
                    role="date_field",
                    phrase=user_input,
                    candidate_ids=tuple(sorted(conflict_ids)),
                    method="explicit_date_role_alias_conflict",
                )
            if len(mentioned) == 1:
                return ObjectGrounder._resolved(
                    "date_field",
                    user_input,
                    next(iter(mentioned.values())),
                    "explicit_current_date_role",
                )
            return ObjectGrounder._ambiguous(
                "date_field",
                user_input,
                tuple(mentioned.values()),
                "multiple_explicit_date_roles",
            )

        defaults = tuple(
            obj for obj in date_fields if obj.temporal_role == "default"
        )
        if len(defaults) == 1:
            return ObjectGrounder._resolved(
                "date_field",
                user_input,
                defaults[0],
                "model_scoped_default_temporal_role",
            )
        if len(defaults) > 1:
            return ObjectGrounder._ambiguous(
                "date_field",
                user_input,
                defaults,
                "multiple_default_temporal_roles",
            )

        grouping_targets: dict[str, CatalogObject] = {}
        for obj in self.catalog.by_type(SemanticObjectType.FIELD):
            binding = obj.temporal_grouping
            if binding is None:
                continue
            target = next(
                (
                    candidate
                    for candidate in date_fields
                    if candidate.table_name == binding.date_table_name
                    and candidate.canonical_name == binding.date_field
                ),
                None,
            )
            if target is not None:
                grouping_targets[target.object_id] = target
        if len(grouping_targets) == 1:
            return ObjectGrounder._resolved(
                "date_field",
                user_input,
                next(iter(grouping_targets.values())),
                "unique_temporal_grouping_date_binding",
            )
        if len(grouping_targets) > 1:
            return ObjectGrounder._ambiguous(
                "date_field",
                user_input,
                tuple(grouping_targets.values()),
                "multiple_temporal_grouping_date_bindings",
            )

        glossary_dates = tuple(
            obj
            for obj in date_fields
            if obj.source == SemanticObjectSource.RUNTIME_GLOSSARY
        )
        if len(glossary_dates) == 1:
            return ObjectGrounder._resolved(
                "date_field",
                user_input,
                glossary_dates[0],
                "unique_model_scoped_temporal_object",
            )

        if len(date_fields) == 1:
            return ObjectGrounder._resolved(
                "date_field",
                user_input,
                date_fields[0],
                "unique_runtime_date_field",
            )
        return ObjectGrounder._ambiguous(
            "date_field",
            user_input,
            date_fields,
            "unproven_default_date_role",
        )

    def _signals_only_repeat_inherited_measure(
        self,
        intent: IntentSpec,
        draft: QueryPlan,
        committed: StructuredWorkMemory | None,
        pending: PendingClarificationContext | None,
        user_input: str,
    ) -> bool:
        """Detect inherited LLM echo without granting it semantic authority.

        Intent and the draft often repeat the committed measure on a filter-,
        dimension-, time-, or analysis-only follow-up.  That repetition is not
        evidence that the current input mentioned a measure.  It is treated as
        omission only when every resolvable weak signal equals the committed
        measure and the input independently expresses another semantic slot.
        """
        inherited_measures = (
            list(pending.measures)
            if pending and pending.measures
            else list(committed.measures) if committed else []
        )
        if len(inherited_measures) != 1:
            return False
        signals = [*intent.detected_measures, *draft.measures]
        if not signals:
            return False
        resolved_names: set[str] = set()
        for phrase in signals:
            result = self.objects.resolve_phrase(
                phrase, SemanticObjectType.MEASURE, "measure"
            )
            if result.status != GroundingStatus.RESOLVED or not result.canonical_object:
                return False
            resolved_names.add(result.canonical_object.canonical_name)
        if resolved_names != {inherited_measures[0]}:
            return False
        return self._has_current_non_measure_requirement(user_input, intent, draft)

    def _has_current_non_measure_requirement(
        self, user_input: str, intent: IntentSpec, draft: QueryPlan
    ) -> bool:
        current_filters = [
            item for item in draft.filters
            if self._value_is_current(item.value, user_input)
        ] or [
            item for item in intent.detected_filters
            if self._value_is_current(item.value, user_input)
        ]
        dimension = self.objects.find_mentions(
            user_input, SemanticObjectType.FIELD, "dimension"
        )
        weak_dimensions = self._current_weak_phrases(
            [*intent.detected_dimensions, *draft.dimensions], user_input
        )
        dimension_requested = self._has_dimension_cue(
            user_input, dimension
        ) or any(
            self._has_dimension_phrase_cue(user_input, phrase)
            for phrase in weak_dimensions
        )
        normalized = normalize_semantic_text(user_input)
        explicit_clear = any(term in normalized for term in (
            "清除筛选", "取消筛选", "不限条件",
            "清除时间", "取消时间", "不限时间",
            "取消top", "不限前", "清除排名",
        ))
        return bool(
            current_filters
            or dimension_requested
            or self.time.is_explicit(user_input, intent.time_intent)
            or self._TOP_N.search(user_input)
            or explicit_clear
        )

    def _resolve_unique_weak(
        self,
        phrases: list[str],
        object_type: SemanticObjectType,
        role: SemanticObjectRole,
    ) -> ObjectGroundingResult:
        resolved: dict[str, ObjectGroundingResult] = {}
        conflicts: list[ObjectGroundingResult] = []
        for phrase in phrases:
            item = self.objects.resolve_phrase(phrase, object_type, role)
            if item.status == GroundingStatus.RESOLVED and item.canonical_object:
                resolved[item.canonical_object.object_id] = item
            elif item.status in {
                GroundingStatus.AMBIGUOUS, GroundingStatus.CONFIG_CONFLICT
            }:
                conflicts.append(item)
        if conflicts:
            return conflicts[0]
        if len(resolved) == 1:
            return next(iter(resolved.values()))
        if len(resolved) > 1:
            return ObjectGroundingResult(
                status=GroundingStatus.AMBIGUOUS,
                role=role,
                phrase=", ".join(phrases),
                candidate_ids=tuple(resolved),
                method="weak_signal_disagreement",
            )
        return ObjectGroundingResult(
            status=(
                GroundingStatus.UNRESOLVED
                if phrases else GroundingStatus.NOT_MENTIONED
            ),
            role=role,
            phrase=", ".join(phrases),
            method=(
                "weak_signal_unresolved" if phrases else "no_current_weak_signal"
            ),
        )

    @staticmethod
    def _current_weak_phrases(phrases: list[str], user_input: str) -> list[str]:
        normalized_input = normalize_semantic_text(user_input)
        current: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            normalized = normalize_semantic_text(phrase)
            if normalized and normalized in normalized_input and normalized not in seen:
                current.append(phrase)
                seen.add(normalized)
        return current

    @staticmethod
    def _value_is_current(value: Any, user_input: str) -> bool:
        if isinstance(value, str):
            return normalize_semantic_text(value) in normalize_semantic_text(user_input)
        return str(value) in user_input

    def _filter_is_explicit_grouping(
        self, item: StructuredFilter, user_input: str
    ) -> bool:
        """A weak draft filter cannot override an explicit grouping cue."""
        resolved = self.objects.resolve_phrase(
            item.field, SemanticObjectType.FIELD, "filter_field"
        )
        return bool(
            resolved.status == GroundingStatus.RESOLVED
            and resolved.canonical_object is not None
            and self._field_has_dimension_cue(
                user_input, resolved.canonical_object
            )
        )

    async def _discover_runtime_member_filters(
        self,
        user_input: str,
        committed: StructuredWorkMemory | None,
        member_lookup: MemberLookup,
        *,
        allow_member_set: bool = False,
    ) -> tuple[
        list[StructuredFilter],
        list[ObjectGroundingResult],
        list[MemberGroundingResult],
        bool,
        bool,
    ]:
        """Find explicit runtime members without granting the draft authority.

        Only fields mentioned in the current input, or the sole committed field
        in a member-only refinement, are eligible.  Values must be returned by
        the runtime member boundary and occur literally after stable text
        normalization.  At most two bounded field lookups are allowed so the
        production tool-call budget remains deterministic.
        """
        mention = self.objects.find_mentions(
            user_input, SemanticObjectType.FIELD, "filter_field"
        )
        candidate_ids = list(mention.candidate_ids)
        normalized_input = normalize_semantic_text(user_input)
        member_evidence_fields = self._member_evidence_fields(user_input)
        member_evidence_ids = {field.object_id for field in member_evidence_fields}
        explicit_member_requirement = False
        for field in member_evidence_fields:
            candidate_ids.append(field.object_id)
            explicit_member_requirement = True
        member_only_cue = any(
            term in normalized_input for term in ("只看", "换成", "改成")
        )
        if (
            not candidate_ids
            and committed is not None
            and member_only_cue
            and not self.time.is_explicit(user_input)
        ):
            committed_fields = {
                str(item.get("field")) for item in committed.filters
            }
            if not committed_fields and len(committed.dimensions) == 1:
                committed_fields = {committed.dimensions[0]}
            committed_hints: dict[str, str] = {}
            if committed.last_query_plan is not None:
                raw_hints = committed.last_query_plan.get("dimension_tables")
                if isinstance(raw_hints, dict):
                    committed_hints = {
                        field: table
                        for field, table in raw_hints.items()
                        if isinstance(field, str) and isinstance(table, str)
                    }
            for field_name in committed_fields:
                resolved = self.objects.resolve_phrase(
                    field_name, SemanticObjectType.FIELD, "filter_field"
                )
                table_hint = committed_hints.get(field_name)
                candidate_ids.extend(
                    object_id
                    for object_id in resolved.candidate_ids
                    if table_hint is None
                    or (
                        (candidate := self.catalog.get(object_id)) is not None
                        and candidate.table_name == table_hint
                    )
                )

        candidates: list[CatalogObject] = []
        seen: set[str] = set()
        for object_id in candidate_ids:
            obj = self.catalog.get(object_id)
            if (
                obj is not None
                and obj.object_id not in seen
                and not self._field_has_dimension_cue(user_input, obj)
            ):
                candidates.append(obj)
                seen.add(obj.object_id)
        if len(candidates) > 2:
            return [], [], [], True, False

        matches: list[tuple[CatalogObject, list[Any]]] = []
        member_results: list[MemberGroundingResult] = []
        unresolved_requested_member = False
        for field in candidates:
            members = await member_lookup(field, 100)
            field_matches = [
                value
                for value in members.values
                if isinstance(value, str)
                and len(normalize_semantic_text(value)) >= 2
                and normalize_semantic_text(value) in normalized_input
            ]
            for alias, target in field.member_aliases.items():
                if alias not in normalized_input:
                    continue
                alias_result = MemberGrounder.resolve(field, target, members)
                member_results.append(alias_result.model_copy(update={
                    "requested_value": alias,
                }))
                if alias_result.status == GroundingStatus.RESOLVED:
                    field_matches.append(alias_result.canonical_value)
                else:
                    unresolved_requested_member = True
            unique_matches: list[Any] = []
            for value in field_matches:
                if value not in unique_matches:
                    unique_matches.append(value)
            if len(unique_matches) > 1 and not allow_member_set:
                return [], [], member_results, True, False
            if unique_matches:
                matches.append((field, unique_matches))
                for value in unique_matches:
                    if any(
                        item.field.object_id == field.object_id
                        and item.status == GroundingStatus.RESOLVED
                        and item.canonical_value == value
                        for item in member_results
                    ):
                        continue
                    member_results.append(MemberGroundingResult(
                        status=GroundingStatus.RESOLVED,
                        field=field,
                        requested_value=value,
                        canonical_value=value,
                        method="runtime_current_input_member",
                    ))
            elif field.object_id in member_evidence_ids:
                member_results.append(MemberGroundingResult(
                    status=GroundingStatus.UNRESOLVED,
                    field=field,
                    requested_value="",
                    method="runtime_no_match_current_literal",
                ))
        if len(matches) > 1:
            return [], [], member_results, True, False

        filters: list[StructuredFilter] = []
        objects: list[ObjectGroundingResult] = []
        for field, values in matches:
            filters.append(StructuredFilter(
                field=field.canonical_name,
                operator=(
                    FilterOperator.IN_SET
                    if len(values) > 1 else FilterOperator.EQ
                ),
                value=values if len(values) > 1 else values[0],
            ))
            objects.append(ObjectGrounder._resolved(
                "filter_field", user_input, field, "runtime_member_field"
            ))
        return (
            filters,
            objects,
            member_results,
            False,
            unresolved_requested_member
            or (explicit_member_requirement and not matches),
        )

    @staticmethod
    def _committed_query_shape(
        committed: StructuredWorkMemory | None,
    ) -> QueryShape | None:
        """Recover shape from committed canonical state, including legacy rows."""
        if committed is None:
            return None
        raw_shape = (
            committed.last_query_plan.get("query_shape")
            if isinstance(committed.last_query_plan, dict)
            else None
        )
        if raw_shape is not None:
            try:
                return QueryShape(raw_shape)
            except (TypeError, ValueError):
                pass
        if committed.top_n is not None:
            return QueryShape.RANKING
        if committed.dimensions:
            return QueryShape.GROUPED
        if committed.measures:
            return QueryShape.SCALAR
        return None

    def _member_evidence_fields(self, user_input: str) -> list[CatalogObject]:
        """Return only catalog fields implicated by current member language."""

        normalized_input = normalize_semantic_text(user_input)
        candidates: list[CatalogObject] = []
        for field in self.catalog.by_type(SemanticObjectType.FIELD):
            if self._field_has_dimension_cue(user_input, field):
                continue
            alias_hit = any(
                alias and alias in normalized_input
                for alias in field.member_aliases
            )
            suffix_hit = any(
                normalize_semantic_text(suffix) in normalized_input
                for suffix in field.member_suffixes
            )
            if alias_hit or suffix_hit:
                candidates.append(field)
        return candidates

    def _has_dimension_cue(
        self, user_input: str, result: ObjectGroundingResult
    ) -> bool:
        candidate_ids = result.candidate_ids
        terms: list[str] = []
        for candidate_id in candidate_ids:
            obj = self.catalog.get(candidate_id)
            if obj is not None:
                terms.extend((obj.canonical_name, *obj.aliases))
        for term in terms:
            escaped = re.escape(term)
            patterns = (
                rf"按\s*{escaped}",
                rf"各\s*{escaped}",
                rf"每(?:个)?\s*{escaped}",
                rf"前\s*{self._RANKING_NUMBER}\s*个?\s*{escaped}",
                rf"top\s*{self._RANKING_NUMBER}\s*个?\s*{escaped}",
                rf"(?:最高|最大|最多|最低|最小|最少)(?:的)?\s*"
                rf"{self._RANKING_NUMBER}\s*个?\s*{escaped}",
                rf"(?:哪个|哪款|哪一个)\s*{escaped}",
                rf"(?:哪些|什么)\s*{escaped}",
                rf"{escaped}.{{0,3}}(?:有哪些|有什么)",
                rf"(?:最高|最低|最大|最小|最多|最少|最好|最差).{{0,8}}{escaped}",
                rf"{escaped}\s*(?:排名|排行|分组|分别)",
            )
            if any(re.search(pattern, user_input, re.IGNORECASE) for pattern in patterns):
                return True
        return False

    def _field_has_dimension_cue(
        self, user_input: str, field: CatalogObject
    ) -> bool:
        return self._has_dimension_cue(
            user_input,
            ObjectGrounder._resolved(
                "dimension", user_input, field, "dimension_cue_candidate"
            ),
        )

    @classmethod
    def _has_dimension_phrase_cue(cls, user_input: str, phrase: str) -> bool:
        escaped = re.escape(phrase)
        return any(re.search(pattern, user_input, re.IGNORECASE) for pattern in (
            rf"按\s*{escaped}",
            rf"各\s*{escaped}",
            rf"每(?:个)?\s*{escaped}",
            rf"前\s*{cls._RANKING_NUMBER}\s*个?\s*{escaped}",
            rf"top\s*{cls._RANKING_NUMBER}\s*个?\s*{escaped}",
            rf"(?:最高|最大|最多|最低|最小|最少)(?:的)?\s*"
            rf"{cls._RANKING_NUMBER}\s*个?\s*{escaped}",
            rf"(?:哪个|哪款|哪一个)\s*{escaped}",
            rf"(?:哪些|什么)\s*{escaped}",
            rf"{escaped}.{{0,3}}(?:有哪些|有什么)",
            rf"(?:最高|最低|最大|最小|最多|最少|最好|最差).{{0,8}}{escaped}",
            rf"{escaped}\s*(?:排名|排行|分组|分别)",
        ))

    @classmethod
    def _ground_analysis(
        cls, user_input: str, draft: QueryPlan, delta: GroundedSemanticDelta
    ) -> None:
        top_n = cls._extract_top_n(user_input)
        if top_n is not None:
            delta.top_n = top_n
            delta.top_n_specified = True
        if any(term in user_input for term in ("最高", "最大", "最多")):
            delta.sort = "desc"
            delta.sort_specified = True
        elif any(term in user_input for term in ("最低", "最小", "最少")):
            delta.sort = "asc"
            delta.sort_specified = True
        elif top_n is not None:
            delta.sort = "desc"
            delta.sort_specified = True

        normalized = normalize_semantic_text(user_input)
        if any(term in normalized for term in ("清除筛选", "取消筛选", "不限条件")):
            delta.clear_filters = True
            delta.filters = None
        if any(term in normalized for term in ("清除时间", "取消时间", "不限时间")):
            delta.clear_time = True
            delta.time_range = None
            delta.time_specified = False
        if any(term in normalized for term in ("取消top", "不限前", "清除排名")):
            delta.clear_top_n = True
            delta.clear_sort = True
            delta.top_n = None
            delta.sort = None

    @classmethod
    def _extract_top_n(cls, user_input: str) -> int | None:
        match = cls._TOP_N.search(user_input)
        if match is None:
            if re.search(
                r"(?:最高|最低|最大|最小|最多|最少|最好|最差).{0,8}"
                r"(?:哪个|哪款|哪一个|谁|什么)",
                user_input,
            ):
                return 1
            return None
        raw = next((value for value in match.groupdict().values() if value), "")
        if raw.isdigit():
            value = int(raw)
        else:
            value = cls._parse_chinese_integer(raw)
        return value if value is not None and value >= 1 else None

    @classmethod
    def _parse_chinese_integer(cls, value: str) -> int | None:
        if not value:
            return None
        if "百" in value:
            left, right = value.split("百", 1)
            hundreds = cls._CHINESE_DIGITS.get(left, 1) if left else 1
            tail = cls._parse_chinese_integer(right) if right else 0
            return None if tail is None else hundreds * 100 + tail
        if "十" in value:
            left, right = value.split("十", 1)
            tens = cls._CHINESE_DIGITS.get(left, 1) if left else 1
            ones = cls._CHINESE_DIGITS.get(right, 0) if right else 0
            return tens * 10 + ones
        digits = [cls._CHINESE_DIGITS.get(char) for char in value]
        if any(item is None for item in digits):
            return None
        return int("".join(str(item) for item in digits))

    @staticmethod
    def _temporal_grouping_grain(user_input: str) -> Literal["month", "year"] | None:
        if re.search(r"(?:每(?:个)?月|按月|逐月|月度)", user_input):
            return "month"
        if re.search(r"(?:每(?:一)?年|按年|逐年|年度)", user_input):
            return "year"
        if "趋势" in user_input and (
            re.search(r"(?:最近|过去)\s*\d+\s*个?月", user_input)
            or len(TimeGrounder._ABSOLUTE_MONTH.findall(user_input)) >= 2
            or len(TimeGrounder._NUMERIC_MONTH.findall(user_input)) >= 2
        ):
            return "month"
        return None

    @staticmethod
    def _requires_clarification(result: ObjectGroundingResult) -> bool:
        return result.status in {
            GroundingStatus.AMBIGUOUS,
            GroundingStatus.UNRESOLVED,
            GroundingStatus.CONFIG_CONFLICT,
        }

    @staticmethod
    def _clarification(
        status: GroundingStatus,
        object_results: list[ObjectGroundingResult],
        member_results: list[MemberGroundingResult],
        question: str,
        disagreements: list[str],
        *,
        pending_eligible: bool = True,
        delta: GroundedSemanticDelta | None = None,
    ) -> GroundingOutcome:
        return GroundingOutcome(
            status=status,
            delta=delta,
            object_results=object_results,
            member_results=member_results,
            clarification_question=question,
            intent_disagreements=disagreements,
            pending_eligible=pending_eligible,
        )
