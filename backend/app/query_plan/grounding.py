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


class ObjectGroundingResult(BaseModel):
    status: GroundingStatus
    role: Literal["measure", "dimension", "filter_field", "date_field"]
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
    measures: list[str] | None = None
    dimensions: list[str] | None = None
    dimension_tables: dict[str, str] = Field(default_factory=dict)
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
    _ABSOLUTE_MONTH = re.compile(r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月")
    _RELATIVE_NAMED_MONTH = re.compile(
        r"去年\s*(十[一二]|十二|十|[一二三四五六七八九]|\d{1,2})\s*月"
    )
    _QUARTER = re.compile(
        r"(?:(?P<year>\d{4})\s*年|(?P<relative>今年|去年))?\s*"
        r"第?\s*(?P<quarter>[一二三四1-4])\s*季度"
    )
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
        today = self._today()
        absolute_month = self._ABSOLUTE_MONTH.search(user_input)
        if absolute_month:
            return self._month_range(
                date_field, int(absolute_month.group(1)), int(absolute_month.group(2))
            )
        relative_named_month = self._RELATIVE_NAMED_MONTH.search(user_input)
        if relative_named_month:
            month = self._parse_number(relative_named_month.group(1))
            if month is not None:
                return self._month_range(date_field, today.year - 1, month)
        quarter_match = self._QUARTER.search(user_input)
        if quarter_match:
            quarter = self._parse_number(quarter_match.group("quarter"))
            raw_year = quarter_match.group("year")
            relative = quarter_match.group("relative")
            year = (
                int(raw_year) if raw_year else today.year - 1
                if relative == "去年" else today.year
            )
            if quarter is not None:
                return self._quarter_range(date_field, year, quarter)
        if "上个月" in user_input:
            year, month = self._shift_month(today.year, today.month, -1)
            return self._month_range(date_field, year, month)
        if "本月" in user_input:
            return self._month_range(
                date_field, today.year, today.month, mode=TimeRangeMode.CURRENT_MONTH
            )
        if "今年" in user_input:
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31),
                mode=TimeRangeMode.CURRENT_YEAR,
                grain="year",
            )
        if "去年" in user_input:
            previous_year = today.year - 1
            return TimeRangeSpec(
                date_field=date_field.canonical_name,
                start_date=date(previous_year, 1, 1),
                end_date=date(previous_year, 12, 31),
                mode=TimeRangeMode.EXPLICIT_RANGE,
                grain="year",
            )
        recent = self._RECENT_MONTHS.search(user_input)
        recent_count = 6 if "最近半年" in user_input else None
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
        dates = self._ISO_DATE.findall(user_input)
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
        if self._draft_has_current_evidence(user_input, time_intent):
            return self._resolve_draft(time_intent, date_field, today)
        return None

    @classmethod
    def is_explicit(
        cls, user_input: str, time_intent: TimeIntentDraft | None = None
    ) -> bool:
        return bool(
            "本月" in user_input
            or "上个月" in user_input
            or "今年" in user_input
            or "去年" in user_input
            or "最近半年" in user_input
            or cls._ABSOLUTE_MONTH.search(user_input)
            or cls._RELATIVE_NAMED_MONTH.search(user_input)
            or cls._QUARTER.search(user_input)
            or cls._RECENT_MONTHS.search(user_input)
            or len(cls._ISO_DATE.findall(user_input)) == 2
            or cls._draft_has_current_evidence(user_input, time_intent)
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


MemberLookup = Callable[[CatalogObject, int], Awaitable[ColumnMembersResult]]


class SemanticGroundingService:
    """Orchestrate grounding without owning Turn or Memory writes."""

    _TOP_N = re.compile(r"(?:前|top\s*)(\d+)", re.IGNORECASE)

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
    ) -> GroundingOutcome:
        object_results: list[ObjectGroundingResult] = []
        member_results: list[MemberGroundingResult] = []
        disagreements: list[str] = []
        delta = GroundedSemanticDelta()

        measure = self.objects.find_mentions(
            user_input, SemanticObjectType.MEASURE, "measure"
        )
        if measure.status == GroundingStatus.NOT_MENTIONED:
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
        if measure.status == GroundingStatus.UNRESOLVED:
            measure = await self.objects.select_bounded(
                measure.phrase,
                user_input,
                SemanticObjectType.MEASURE,
                "measure",
            )
        object_results.append(measure)
        if self._requires_clarification(measure):
            return self._clarification(
                measure.status, object_results, member_results,
                "请明确您要查询的业务指标。", disagreements,
            )
        if measure.status == GroundingStatus.RESOLVED and measure.canonical_object:
            delta.measures = [measure.canonical_object.canonical_name]
            if (
                intent.detected_measures
                and measure.canonical_object.canonical_name
                not in intent.detected_measures
            ):
                disagreements.append("intent_measure_disagrees_with_grounding")
        elif measure.status == GroundingStatus.NOT_MENTIONED and not (
            (pending and pending.measures) or (committed and committed.measures)
        ):
            return self._clarification(
                GroundingStatus.NOT_MENTIONED,
                object_results,
                member_results,
                "请明确您要查询的业务指标。",
                disagreements,
            )

        raw_filters = [
            item for item in draft.filters
            if self._value_is_current(item.value, user_input)
            if not self._filter_is_explicit_grouping(item, user_input)
        ]
        if not raw_filters:
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
        grounded_filters: list[StructuredFilter] = []
        grounded_filter_ids: set[str] = set()
        if not raw_filters:
            (
                discovered_filters,
                discovered_objects,
                discovered_members,
                discovery_ambiguous,
            ) = await self._discover_runtime_member_filters(
                user_input, committed, member_lookup
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

        current_dimension = self.objects.find_mentions(
            user_input, SemanticObjectType.FIELD, "dimension"
        )
        weak_dimension_phrases = self._current_weak_phrases(
            [*intent.detected_dimensions, *draft.dimensions], user_input
        )
        dimension_requested = self._has_dimension_cue(
            user_input, current_dimension
        ) or any(
            self._has_dimension_phrase_cue(user_input, phrase)
            for phrase in weak_dimension_phrases
        )
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
                        "dimension", user_input, remaining[0], "current_input_non_filter"
                    )
            if dimension.status == GroundingStatus.NOT_MENTIONED:
                dimension = self._resolve_unique_weak(
                    weak_dimension_phrases,
                    SemanticObjectType.FIELD,
                    "dimension",
                )
            if dimension.status == GroundingStatus.UNRESOLVED:
                dimension = await self.objects.select_bounded(
                    dimension.phrase,
                    user_input,
                    SemanticObjectType.FIELD,
                    "dimension",
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

        if self.time.is_explicit(user_input, intent.time_intent):
            date_fields = tuple(
                obj for obj in self.catalog.by_type(SemanticObjectType.FIELD)
                if "date" in obj.data_type.casefold() or "time" in obj.data_type.casefold()
            )
            glossary_date_fields = tuple(
                obj
                for obj in date_fields
                if obj.source == SemanticObjectSource.RUNTIME_GLOSSARY
            )
            if glossary_date_fields:
                date_fields = glossary_date_fields
            if len(date_fields) != 1:
                candidates = tuple(item.object_id for item in date_fields)
                date_result = ObjectGroundingResult(
                    status=(
                        GroundingStatus.AMBIGUOUS
                        if len(date_fields) > 1 else GroundingStatus.UNRESOLVED
                    ),
                    role="date_field",
                    phrase=user_input,
                    candidate_ids=candidates,
                    method="date_field_cardinality",
                )
                object_results.append(date_result)
                return self._clarification(
                    date_result.status, object_results, member_results,
                    "请明确要使用的日期字段。", disagreements,
                )
            date_result = ObjectGrounder._resolved(
                "date_field", user_input, date_fields[0], "unique_runtime_date_field"
            )
            object_results.append(date_result)
            time_range = self.time.ground(
                user_input, date_fields[0], intent.time_intent
            )
            if time_range is None:
                return self._clarification(
                    GroundingStatus.UNRESOLVED, object_results, member_results,
                    "时间范围无法确定，请提供明确日期。", disagreements,
                )
            delta.time_range = time_range
            delta.time_specified = True
            delta.dimension_tables[
                date_fields[0].canonical_name
            ] = date_fields[0].table_name

        self._ground_analysis(user_input, draft, delta)
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
        role: Literal["measure", "dimension", "filter_field", "date_field"],
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
    ) -> tuple[
        list[StructuredFilter],
        list[ObjectGroundingResult],
        list[MemberGroundingResult],
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
            return [], [], [], True

        matches: list[tuple[CatalogObject, Any]] = []
        member_results: list[MemberGroundingResult] = []
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
                field_matches.extend(
                    value
                    for value in members.values
                    if isinstance(value, str)
                    and normalize_semantic_text(value)
                    == normalize_semantic_text(target)
                )
            unique_matches: list[Any] = []
            for value in field_matches:
                if value not in unique_matches:
                    unique_matches.append(value)
            if len(unique_matches) > 1:
                return [], [], member_results, True
            if len(unique_matches) == 1:
                value = unique_matches[0]
                matches.append((field, value))
                member_results.append(MemberGroundingResult(
                    status=GroundingStatus.RESOLVED,
                    field=field,
                    requested_value=value,
                    canonical_value=value,
                    method="runtime_current_input_member",
                ))
        if len(matches) > 1:
            return [], [], member_results, True

        filters: list[StructuredFilter] = []
        objects: list[ObjectGroundingResult] = []
        for field, value in matches:
            filters.append(StructuredFilter(
                field=field.canonical_name,
                operator=FilterOperator.EQ,
                value=value,
            ))
            objects.append(ObjectGrounder._resolved(
                "filter_field", user_input, field, "runtime_member_field"
            ))
        return filters, objects, member_results, False

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
                rf"前\s*\d+\s*个?\s*{escaped}",
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

    @staticmethod
    def _has_dimension_phrase_cue(user_input: str, phrase: str) -> bool:
        escaped = re.escape(phrase)
        return any(re.search(pattern, user_input, re.IGNORECASE) for pattern in (
            rf"按\s*{escaped}",
            rf"各\s*{escaped}",
            rf"每(?:个)?\s*{escaped}",
            rf"{escaped}\s*(?:排名|排行|分组|分别)",
        ))

    @classmethod
    def _ground_analysis(
        cls, user_input: str, draft: QueryPlan, delta: GroundedSemanticDelta
    ) -> None:
        match = cls._TOP_N.search(user_input)
        if match:
            delta.top_n = int(match.group(1))
            delta.top_n_specified = True
        if any(term in user_input for term in ("最高", "最大", "最多")):
            delta.sort = "desc"
            delta.sort_specified = True
        elif any(term in user_input for term in ("最低", "最小", "最少")):
            delta.sort = "asc"
            delta.sort_specified = True
        elif match and draft.sort in {"asc", "desc"}:
            delta.sort = draft.sort
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
    ) -> GroundingOutcome:
        return GroundingOutcome(
            status=status,
            object_results=object_results,
            member_results=member_results,
            clarification_question=question,
            intent_disagreements=disagreements,
            pending_eligible=pending_eligible,
        )
