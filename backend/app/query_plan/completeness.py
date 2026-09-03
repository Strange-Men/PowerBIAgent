"""M5.8.5 fail-closed semantic obligation and canonical shape gates."""

from __future__ import annotations

import re
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from backend.app.query_plan.grounding import GroundingOutcome, GroundingStatus
from backend.app.query_plan.semantic_catalog import SemanticCatalog
from backend.app.query_plan.turn_relation import TurnRelationEvidence
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    QueryShape,
)


class SemanticObligationKind(str, Enum):
    MEASURE = "measure"
    DIMENSION = "dimension"
    EXPLICIT_FILTER_MEMBER = "explicit_filter_member"
    TIME = "time"
    RANKING = "ranking"
    TURN_RELATION = "turn_relation"
    EXPLICIT_CLEAR = "explicit_clear"


class SemanticObligationStatus(str, Enum):
    RESOLVED = "RESOLVED"
    EXPLICITLY_CLEARED = "EXPLICITLY_CLEARED"
    UNSUPPORTED = "UNSUPPORTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class SemanticObligation(BaseModel):
    kind: SemanticObligationKind
    status: SemanticObligationStatus
    phrase: str = ""
    canonical_identity: str | None = None
    evidence: str

    model_config = ConfigDict(frozen=True)


class SemanticObligationReport(BaseModel):
    obligations: list[SemanticObligation] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @property
    def executable(self) -> bool:
        return all(item.status in {
            SemanticObligationStatus.RESOLVED,
            SemanticObligationStatus.EXPLICITLY_CLEARED,
        } for item in self.obligations)

    @property
    def unresolved_phrases(self) -> list[str]:
        return [
            item.phrase for item in self.obligations
            if item.status == SemanticObligationStatus.NEEDS_CLARIFICATION
            and item.phrase
        ]


class SemanticObligationCoverageGate:
    """Audit result-affecting modifiers without requiring every token to bind."""

    _FUNCTIONAL_TERMS: ClassVar[tuple[str, ...]] = (
        "请问", "请帮我", "帮我", "查询", "查一下", "看一下", "看看", "分析", "统计", "汇总", "比较", "告诉我",
        "我们", "销售了", "列出", "展示", "显示", "包含", "包括", "提供",
        "独立问题", "新问题", "重新开始", "忽略之前", "单独问", "重新分析",
        "改成", "改为", "换成", "换为", "调整为", "那", "那么", "只看", "再看", "继续", "然后",
        "是多少", "是什么", "有多少", "有哪些", "多少", "哪些", "哪个", "哪款", "如何", "怎么样", "情况", "结果",
        "总", "平均", "合计", "加起来", "合起来", "分别", "按照", "按", "来看", "看", "的", "呢", "为", "大概", "大约", "约",
        "最高", "最低", "最大", "最小", "最多", "最少", "最好", "最差", "最准", "最严重", "最快", "最慢", "最早", "最晚", "卖得最好", "卖的最好",
        "前十", "前三", "第一", "排名", "趋势", "月度", "前", "第", "个", "是", "哪", "款", "从", "至", "到", "月", "年",
        "and", "or", "what", "which", "how", "many", "show", "list", "me", "please", "by",
        "is", "are", "has", "have", "the", "all", "for", "from", "to", "of",
        "total", "average", "top", "highest", "lowest", "trend", "monthly", "yearly", "per", "question", "new",
        "等于", "等于多少", "时",
    )
    _TIME_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*[日号])?"),
        re.compile(r"\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?"),
        re.compile(r"(?:本|上|下|这|去|今|明)(?:年|月|季度)"),
        re.compile(r"\d+\s*(?:个)?月"),
    )

    def inspect(
        self,
        *,
        user_input: str,
        outcome: GroundingOutcome,
        catalog: SemanticCatalog,
        relation: TurnRelationEvidence,
        language_evidence: tuple[str, ...] = (),
    ) -> SemanticObligationReport:
        obligations: list[SemanticObligation] = []
        role_kind = {
            "measure": SemanticObligationKind.MEASURE,
            "dimension": SemanticObligationKind.DIMENSION,
            "ranking_dimension": SemanticObligationKind.DIMENSION,
            "filter_field": SemanticObligationKind.EXPLICIT_FILTER_MEMBER,
            "date_field": SemanticObligationKind.TIME,
        }
        status_map = {
            GroundingStatus.RESOLVED: SemanticObligationStatus.RESOLVED,
            GroundingStatus.EXPLICIT_CLEAR: SemanticObligationStatus.EXPLICITLY_CLEARED,
            GroundingStatus.AMBIGUOUS: SemanticObligationStatus.NEEDS_CLARIFICATION,
            GroundingStatus.UNRESOLVED: SemanticObligationStatus.NEEDS_CLARIFICATION,
            GroundingStatus.CONFIG_CONFLICT: SemanticObligationStatus.UNSUPPORTED,
        }
        for item in outcome.object_results:
            if item.status == GroundingStatus.NOT_MENTIONED:
                continue
            canonical = item.canonical_object.canonical_name if item.canonical_object else None
            obligations.append(SemanticObligation(
                kind=role_kind[item.role],
                status=status_map[item.status],
                phrase=item.phrase,
                canonical_identity=canonical,
                evidence=item.method or "grounding",
            ))
        for item in outcome.member_results:
            obligations.append(SemanticObligation(
                kind=SemanticObligationKind.EXPLICIT_FILTER_MEMBER,
                status=status_map[item.status],
                phrase=str(item.requested_value),
                canonical_identity=(
                    f"{item.field.table_name}[{item.field.canonical_name}]={item.canonical_value}"
                    if item.status == GroundingStatus.RESOLVED else None
                ),
                evidence=item.method or "runtime_member",
            ))

        delta = outcome.delta
        if delta is not None:
            if delta.measures and not any(item.kind == SemanticObligationKind.MEASURE for item in obligations):
                obligations.append(self._resolved(SemanticObligationKind.MEASURE, delta.measures[0], "grounded_delta"))
            if delta.dimensions and not any(item.kind == SemanticObligationKind.DIMENSION for item in obligations):
                obligations.append(self._resolved(SemanticObligationKind.DIMENSION, delta.dimensions[0], "grounded_delta"))
            if delta.filters and not outcome.member_results:
                for item in delta.filters:
                    obligations.append(self._resolved(
                        SemanticObligationKind.EXPLICIT_FILTER_MEMBER,
                        str(item.value),
                        f"canonical_filter:{item.field}",
                    ))
            if delta.time_specified:
                obligations.append(SemanticObligation(
                    kind=SemanticObligationKind.TIME,
                    status=(SemanticObligationStatus.RESOLVED if delta.time_range else SemanticObligationStatus.NEEDS_CLARIFICATION),
                    phrase="time",
                    canonical_identity=(delta.time_range.date_field if delta.time_range else None),
                    evidence="grounded_time",
                ))
            if delta.sort_specified or delta.top_n_specified:
                complete = delta.sort is not None and delta.top_n is not None
                obligations.append(SemanticObligation(
                    kind=SemanticObligationKind.RANKING,
                    status=(SemanticObligationStatus.RESOLVED if complete else SemanticObligationStatus.NEEDS_CLARIFICATION),
                    phrase="ranking",
                    canonical_identity=(f"{delta.sort}:top{delta.top_n}" if complete else None),
                    evidence="deterministic_analysis",
                ))
            for cleared, phrase in (
                (delta.clear_filters, "filters"), (delta.clear_time, "time"),
                (delta.clear_sort, "sort"), (delta.clear_top_n, "top_n"),
            ):
                if cleared:
                    obligations.append(SemanticObligation(
                        kind=SemanticObligationKind.EXPLICIT_CLEAR,
                        status=SemanticObligationStatus.EXPLICITLY_CLEARED,
                        phrase=phrase,
                        evidence="explicit_clear_modifier",
                    ))
        if relation.explicit:
            obligations.append(self._resolved(
                SemanticObligationKind.TURN_RELATION,
                relation.matched_cue or relation.kind.value,
                relation.source,
            ))

        if not any(item.status in {
            SemanticObligationStatus.NEEDS_CLARIFICATION,
            SemanticObligationStatus.UNSUPPORTED,
        } for item in obligations):
            residue = self._semantic_modifier_residue(
                user_input,
                outcome,
                catalog,
                language_evidence=language_evidence,
            )
            if residue:
                obligations.append(SemanticObligation(
                    kind=SemanticObligationKind.EXPLICIT_FILTER_MEMBER,
                    status=SemanticObligationStatus.NEEDS_CLARIFICATION,
                    phrase=residue,
                    evidence="bounded_result_affecting_modifier_residue",
                ))
        return SemanticObligationReport(obligations=obligations)

    @staticmethod
    def _resolved(kind: SemanticObligationKind, phrase: str, evidence: str) -> SemanticObligation:
        return SemanticObligation(
            kind=kind,
            status=SemanticObligationStatus.RESOLVED,
            phrase=phrase,
            canonical_identity=phrase,
            evidence=evidence,
        )

    @classmethod
    def _semantic_modifier_residue(
        cls,
        user_input: str,
        outcome: GroundingOutcome,
        catalog: SemanticCatalog,
        *,
        language_evidence: tuple[str, ...] = (),
    ) -> str:
        """Return only bounded noun-like residue around a resolved business query."""
        if outcome.delta is None or not (
            outcome.delta.measures or outcome.delta.dimensions
        ):
            return ""
        text = user_input
        consumable: set[str] = set(cls._FUNCTIONAL_TERMS)
        consumable.update(language_evidence)
        for item in outcome.object_results:
            if item.phrase:
                consumable.add(item.phrase)
            if item.canonical_object:
                consumable.update(item.canonical_object.language_terms)
        for item in outcome.member_results:
            consumable.add(str(item.requested_value))
            if item.canonical_value is not None:
                consumable.add(str(item.canonical_value))
        # Catalog terms are identities already available to the one authority;
        # consuming them here cannot create a binding or make a plan executable.
        for obj in catalog.objects:
            consumable.update(obj.language_terms)
        for pattern in cls._TIME_PATTERNS:
            text = pattern.sub(" ", text)
        for term in sorted((value for value in consumable if value), key=len, reverse=True):
            text = re.sub(re.escape(term), " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:\d+|asc|desc)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[\s\u3000，,。.!！?？:：;；·、/\\()（）\[\]{}<>《》\-—_\"']+", "", text)
        if not text:
            return ""
        # One isolated CJK character or one one-letter Latin token is normally
        # connective noise, not a safe basis for blocking a business query.
        if len(text) < 2:
            return ""
        return text[:80]


class CanonicalShapeCompletenessError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CanonicalShapeCompletenessReport(BaseModel):
    complete: bool = True
    shape: QueryShape
    required_slots: tuple[str, ...]
    scope_fields: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class CanonicalShapeCompletenessGate:
    """Prove shape-specific canonical slots before deterministic DAX."""

    def validate(
        self, plan: CanonicalQueryPlan, *, catalog: SemanticCatalog | None = None,
    ) -> CanonicalShapeCompletenessReport:
        shape = plan.query_shape or QueryShape.SCALAR
        if shape != QueryShape.ENTITY_LIST and not plan.measures:
            self._fail("canonical_shape_measure_required")
        required: tuple[str, ...]
        if shape == QueryShape.SCALAR:
            required = ("measure",)
        elif shape == QueryShape.ENTITY_LIST:
            required = ("dimension",)
            if not plan.dimensions:
                self._fail("canonical_shape_entity_list_dimension_required")
        elif shape == QueryShape.GROUPED:
            required = ("measure", "dimension")
            if not plan.dimensions:
                self._fail("canonical_shape_grouped_dimension_required")
        elif shape == QueryShape.RANKING:
            required = ("measure", "dimension", "sort", "top_n")
            if not plan.dimensions:
                self._fail("canonical_shape_ranking_dimension_required")
            if plan.sort is None:
                self._fail("canonical_shape_ranking_sort_required")
            if plan.top_n is None:
                self._fail("canonical_shape_ranking_top_n_required")
        elif shape == QueryShape.MEMBER_SET:
            required = ("authoritative_filter_field", "complete_member_set")
            if len(plan.filters) != 1:
                self._fail("canonical_shape_member_set_single_field_required")
            item = plan.filters[0]
            if item.operator != FilterOperator.IN_SET:
                self._fail("canonical_shape_member_set_operator_required")
            if not isinstance(item.value, (list, tuple)) or not item.value:
                self._fail("canonical_shape_member_set_values_required")
            if len({str(value) for value in item.value}) != len(item.value):
                self._fail("canonical_shape_member_set_duplicate_value")
        elif shape == QueryShape.FILTERED_AGGREGATION:
            required = ("measure", "complete_filter")
            if not plan.filters:
                self._fail("canonical_shape_filtered_filter_required")
            if any(
                item.operator == FilterOperator.IN_SET
                and (not isinstance(item.value, (list, tuple)) or not item.value)
                for item in plan.filters
            ):
                self._fail("canonical_shape_filtered_filter_values_required")
        elif shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
            required = ("measure", "temporal_grouping") + (
                ("bounded_time_range",) if shape == QueryShape.BOUNDED_TREND else ()
            )
            if not plan.dimensions or not self._has_temporal_grouping(plan, catalog):
                self._fail("canonical_shape_trend_temporal_dimension_required")
            if plan.dimension_order != "asc":
                self._fail("canonical_shape_trend_ascending_required")
            if shape == QueryShape.BOUNDED_TREND and plan.time_range is None:
                self._fail("canonical_shape_bounded_trend_time_required")
        else:  # pragma: no cover - enum exhaustiveness
            self._fail("canonical_shape_unsupported")
        return CanonicalShapeCompletenessReport(
            shape=shape,
            required_slots=required,
            scope_fields=tuple([
                *plan.measures, *plan.dimensions,
                *(item.field for item in plan.filters),
                *([plan.time_range.date_field] if plan.time_range else []),
            ]),
        )

    @staticmethod
    def _has_temporal_grouping(
        plan: CanonicalQueryPlan, catalog: SemanticCatalog | None,
    ) -> bool:
        if plan.dimension_order != "asc":
            return False
        if catalog is None:
            return True
        hints = plan.dimension_tables or {}
        for name in plan.dimensions:
            matches = [
                obj for obj in catalog.objects
                if obj.canonical_name == name
                and (hints.get(name) is None or obj.table_name == hints[name])
            ]
            if any(
                obj.temporal_grouping is not None
                or "date" in obj.data_type.casefold()
                or "time" in obj.data_type.casefold()
                for obj in matches
            ):
                return True
        return False

    @staticmethod
    def _fail(code: str) -> None:
        raise CanonicalShapeCompletenessError(code)
