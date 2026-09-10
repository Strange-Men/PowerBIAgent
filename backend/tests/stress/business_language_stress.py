"""Deterministic Business Language Stress generator and safe reporter.

This module is test infrastructure.  It owns fixture language and expectations;
production code must never import it or copy its domain terms as authority.
"""

from __future__ import annotations

import hashlib
import json
import random
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from itertools import combinations, product
from typing import Callable, Iterable, Mapping, Sequence

from backend.app.dax.builder import DeterministicDAXBuilder
from backend.app.dax.verifier import RestrictedDAXVerifier
from backend.app.facts.inspection import ResultSemanticInspectionGate
from backend.app.facts.verified import FactType, VerifiedFactSetBuilder
from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.intent.temporal_expression import parse_explicit_month_range
from backend.app.presentation.query_scope import DeterministicQueryScopeDescriptor
from backend.app.query_plan.completeness import CanonicalShapeCompletenessGate
from backend.app.query_plan.grounding import SemanticGroundingService
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
    TemporalGroupingBinding,
)
from backend.app.query_plan.turn_relation import (
    TurnRelationEvidence,
    TurnRelationKind,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnSchema,
    FilterOperator,
    MeasureSchema,
    QueryResult,
    QueryShape,
    RelationshipSchema,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
    TimeRangeMode,
    TimeRangeSpec,
)


DEFAULT_SEED = 594_20260909
DEFAULT_CASES_PER_DOMAIN_SHAPE = 1_600


@dataclass(frozen=True)
class StressDomain:
    fixture_id: str
    measure: tuple[str, str, str]
    dimension: tuple[str, str, str]
    filter_field: tuple[str, str, str]
    known_members: tuple[str, str, str]
    known_dimension_member: str
    unknown_member: str
    ambiguous_member: str


DOMAINS: tuple[StressDomain, ...] = (
    StressDomain(
        "sales_star_duplicate",
        ("Net Revenue", "净营收", "销售收入"),
        ("Product Name", "产品", "商品"),
        ("Area Name", "区域", "经营分区"),
        ("华南", "华北", "华东"),
        "手机",
        "火星区",
        "中心",
    ),
    StressDomain(
        "education_snowflake",
        ("Pass Ratio", "课程通过率", "通过比例"),
        ("Program Title", "学习项目", "课程项目"),
        ("Campus Name", "校区", "教学点"),
        ("东校区", "西校区", "北校区"),
        "数据科学",
        "月球校区",
        "总部",
    ),
    StressDomain(
        "inventory_flat_multidate",
        ("On Hand Units", "在库件数", "当前库存"),
        ("Warehouse Label", "仓库", "库房"),
        ("Stock Status", "库存状态", "状态"),
        ("正常", "预警", "冻结"),
        "一号仓",
        "未知状态",
        "其他",
    ),
    StressDomain(
        "logistics_technical_label_peer",
        ("Shipment Count", "运单数", "总运单量"),
        ("Carrier Name", "承运商", "承运单位"),
        ("Hub Name", "枢纽", "中转站"),
        ("North Hub", "South Hub", "East Hub"),
        "Swift Cargo",
        "Mars Hub",
        "Central",
    ),
)


COMMON_FACTORS: Mapping[str, Sequence[str]] = {
    "register": ("formal", "spoken", "terse", "mixed"),
    "courtesy": ("none", "please", "help", "could_you", "kindly"),
    "noise": ("none", "roughly", "directly", "briefly", "also"),
    "punctuation": ("none", "cn_question", "en_question", "period", "comma"),
    "word_order": ("default", "metric_first", "modifier_first", "reordered"),
    "relation": ("unspecified", "fresh", "follow_up", "replace"),
    "relation_surface": ("primary", "alternate", "scope", "among"),
    "object_surface": ("display", "canonical", "synonym"),
}


SHAPE_FACTORS: Mapping[QueryShape, Mapping[str, Sequence[str]]] = {
    QueryShape.SCALAR: {
        "filter_state": ("none", "known", "unknown", "ambiguous"),
        "filter_count": ("single", "multiple"),
        "time_form": ("none", "absolute_month", "relative_month", "absolute_year"),
        "scalar_cue": ("amount", "how_many", "show", "total"),
    },
    QueryShape.GROUPED: {
        "grouping_cue": ("each", "every", "by", "split", "respectively"),
        "filter_state": ("none", "known", "unknown", "ambiguous"),
        "filter_count": ("single", "multiple"),
        "time_form": ("none", "absolute_month", "relative_month"),
    },
    QueryShape.RANKING: {
        "ranking_cue": ("front", "highest", "lowest", "ordinal", "vague"),
        "number_form": ("arabic3", "chinese3", "top3", "arabic10", "chinese10", "first", "missing"),
        "filter_state": ("none", "known", "unknown"),
        "filter_count": ("single", "multiple"),
        "time_form": ("none", "absolute_month", "relative_month"),
    },
    QueryShape.TREND: {
        "trend_cue": ("trend", "change", "monthly", "by_month", "english"),
        "time_form": ("none", "recent6", "recent12", "relative_year"),
        "filter_state": ("none", "known", "unknown"),
        "filter_count": ("single", "multiple"),
    },
    QueryShape.BOUNDED_TREND: {
        "range_form": ("full", "abbreviated_end_year", "numeric", "fullwidth", "current_year", "yearless"),
        "range_separator": ("to_cn", "until_cn", "hyphen", "tilde"),
        "trend_cue": ("trend", "monthly", "by_month", "change"),
        "filter_state": ("none", "known", "unknown"),
        "filter_count": ("single", "multiple"),
    },
    QueryShape.ENTITY_LIST: {
        "entity_cue": ("which", "list", "all", "show", "english"),
    },
    QueryShape.MEMBER_SET: {
        "member_state": ("known_pair", "known_triple", "known_unknown", "unknown_pair", "ambiguous_pair"),
        "conjunction": ("and_cn", "with_cn", "enumeration", "including", "english"),
        "set_cue": ("respectively", "each_own", "how_much", "formal"),
        "time_form": ("none", "absolute_month", "relative_month"),
    },
    QueryShape.FILTERED_AGGREGATION: {
        "member_state": ("known_pair", "known_triple", "known_unknown", "unknown_pair", "ambiguous_pair"),
        "conjunction": ("and_cn", "with_cn", "enumeration", "including", "english"),
        "aggregation_cue": ("add_up", "combine", "total", "altogether", "together"),
        "time_form": ("none", "absolute_month", "relative_month"),
    },
}


@dataclass(frozen=True)
class StressCase:
    case_id: str
    seed: int
    domain: StressDomain
    shape: QueryShape
    factors: tuple[tuple[str, str], ...]
    question: str
    expected_shape: QueryShape | None
    expected_relation: TurnRelationKind
    expected_top_n: int | None = None
    expected_sort: str | None = None
    expected_execution: bool = True
    expected_time: tuple[int, int, int, int] | None = None
    expected_bounded_expression: bool = False
    semantic_factors: tuple[str, ...] = ()
    language_pattern: str = ""

    def factor(self, name: str, default: str = "") -> str:
        return dict(self.factors).get(name, default)

    def canonical_signature(self) -> str:
        payload = {
            "domain": self.domain.fixture_id,
            "shape": self.shape.value,
            "filter": self.factor("filter_state") or self.factor("member_state"),
            "filter_count": self.factor("filter_count"),
            "time": self.expected_time or self.factor("time_form"),
            "ranking": [self.expected_sort, self.expected_top_n],
            "relation": self.expected_relation.value,
            "execution": self.expected_execution,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def safe_descriptor(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "seed": self.seed,
            "domain_fixture": self.domain.fixture_id,
            "shape": self.shape.value,
            "semantic_factors": list(self.semantic_factors),
            "language_pattern": self.language_pattern,
            "factor_values": dict(self.factors),
            "question": self.question[:240],
            "expected_execution": self.expected_execution,
            "canonical_digest": self.canonical_signature(),
        }


@dataclass(frozen=True)
class StressFailure:
    category: str
    expected: str
    actual: str
    case: StressCase
    minimum_question: str

    def safe_descriptor(self) -> dict[str, object]:
        return {
            **self.case.safe_descriptor(),
            "category": self.category,
            "expected": self.expected,
            "actual": self.actual,
            "minimum_question": self.minimum_question[:240],
        }


@dataclass
class StressSummary:
    seed: int
    total: int = 0
    passed: int = 0
    failed: int = 0
    fail_by_shape: Counter[str] = field(default_factory=Counter)
    fail_by_semantic_factor: Counter[str] = field(default_factory=Counter)
    fail_by_language_pattern: Counter[str] = field(default_factory=Counter)
    zero_dax_invariant_failures: int = 0
    canonical_mismatch: int = 0
    cross_model_bleed: int = 0
    unexpected_clarification: int = 0
    unexpected_execution: int = 0
    silent_modifier_loss: int = 0
    incorrect_dax_execution: int = 0
    semantic_execution_cases: int = 0
    metamorphic_groups: int = 0
    metamorphic_variants: int = 0
    unknown_ambiguous_cases: int = 0
    failures: list[StressFailure] = field(default_factory=list)

    def add_failure(self, failure: StressFailure) -> None:
        self.failed += 1
        self.fail_by_shape[failure.case.shape.value] += 1
        self.fail_by_language_pattern[failure.case.language_pattern] += 1
        for factor in failure.case.semantic_factors:
            self.fail_by_semantic_factor[factor] += 1
        if failure.category in {"unknown_executed", "ambiguous_executed"}:
            self.zero_dax_invariant_failures += 1
            self.unexpected_execution += 1
        if failure.category == "canonical_mismatch":
            self.canonical_mismatch += 1
        if failure.category == "cross_model_bleed":
            self.cross_model_bleed += 1
        if failure.category == "unexpected_clarification":
            self.unexpected_clarification += 1
        if failure.category in {"shape_mismatch", "time_range_mismatch", "ranking_mismatch"}:
            self.silent_modifier_loss += 1
        if failure.category == "dax_mismatch":
            self.incorrect_dax_execution += 1
        if len(self.failures) < 100:
            self.failures.append(failure)

    def finish(self) -> None:
        self.passed = self.total - self.failed

    def as_dict(self, *, failure_limit: int = 20) -> dict[str, object]:
        return {
            "seed": self.seed,
            "total": self.total,
            "pass": self.passed,
            "fail": self.failed,
            "fail_by_shape": dict(sorted(self.fail_by_shape.items())),
            "fail_by_semantic_factor": dict(sorted(self.fail_by_semantic_factor.items())),
            "fail_by_language_pattern": dict(sorted(self.fail_by_language_pattern.items())),
            "zero_dax_invariant_failures": self.zero_dax_invariant_failures,
            "canonical_mismatch": self.canonical_mismatch,
            "cross_model_bleed": self.cross_model_bleed,
            "unexpected_clarification": self.unexpected_clarification,
            "unexpected_execution": self.unexpected_execution,
            "silent_modifier_loss": self.silent_modifier_loss,
            "incorrect_dax_execution": self.incorrect_dax_execution,
            "semantic_execution_cases": self.semantic_execution_cases,
            "metamorphic_groups": self.metamorphic_groups,
            "metamorphic_variants": self.metamorphic_variants,
            "unknown_ambiguous_cases": self.unknown_ambiguous_cases,
            "failures": [item.safe_descriptor() for item in self.failures[:failure_limit]],
        }


def _pairs(row: Mapping[str, str]) -> set[tuple[str, str, str, str]]:
    names = sorted(row)
    return {
        (left, row[left], right, row[right])
        for left, right in combinations(names, 2)
    }


def greedy_pairwise_rows(
    factors: Mapping[str, Sequence[str]], *, seed: int = DEFAULT_SEED
) -> list[dict[str, str]]:
    """Return deterministic rows covering every cross-factor value pair."""
    names = tuple(sorted(factors))
    uncovered = {
        (left, left_value, right, right_value)
        for left, right in combinations(names, 2)
        for left_value in factors[left]
        for right_value in factors[right]
    }
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    while uncovered:
        anchor = min(uncovered)
        candidates: list[dict[str, str]] = []
        for _ in range(96):
            row = {name: rng.choice(tuple(factors[name])) for name in names}
            row[anchor[0]] = anchor[1]
            row[anchor[2]] = anchor[3]
            candidates.append(row)
        best = max(
            candidates,
            key=lambda row: (len(_pairs(row) & uncovered), tuple(row[name] for name in names)),
        )
        rows.append(best)
        uncovered -= _pairs(best)
    return rows


def _bounded_three_way_rows(
    factors: Mapping[str, Sequence[str]], *, seed: int
) -> list[dict[str, str]]:
    names = tuple(sorted(factors))
    selected = names[: min(5, len(names))]
    rng = random.Random(seed ^ 0x594)
    rows: list[dict[str, str]] = []
    for triple in combinations(selected, 3):
        for values in product(*(factors[name] for name in triple)):
            row = {name: rng.choice(tuple(factors[name])) for name in names}
            row.update(dict(zip(triple, values)))
            rows.append(row)
    return rows


def _sample_factor_rows(
    factors: Mapping[str, Sequence[str]], *, count: int, seed: int
) -> list[dict[str, str]]:
    names = tuple(sorted(factors))
    rows = greedy_pairwise_rows(factors, seed=seed)
    rows.extend(_bounded_three_way_rows(factors, seed=seed))
    seen = {tuple(row[name] for name in names) for row in rows}
    rng = random.Random(seed)
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 200:
            raise RuntimeError("stress_factor_space_exhausted")
        values = tuple(rng.choice(tuple(factors[name])) for name in names)
        if values in seen:
            continue
        seen.add(values)
        rows.append(dict(zip(names, values)))
    return rows[:count]


def _surface(values: tuple[str, str, str], choice: str) -> str:
    return values[{"canonical": 0, "display": 1, "synonym": 2}[choice]]


def _time_text(form: str) -> str:
    return {
        "none": "",
        "absolute_month": "2025年5月",
        "relative_month": "上个月",
        "absolute_year": "2025年",
        "recent6": "最近6个月",
        "recent12": "过去12个月",
        "relative_year": "今年",
    }.get(form, "")


def _member_values(domain: StressDomain, state: str) -> tuple[list[str], bool]:
    known = list(domain.known_members)
    if state in {"none", "known"}:
        return ([known[0]] if state == "known" else []), True
    if state == "unknown":
        return [domain.unknown_member], False
    if state == "ambiguous":
        return [domain.ambiguous_member], False
    if state == "known_pair":
        return known[:2], True
    if state == "known_triple":
        return known[:3], True
    if state == "known_unknown":
        return [known[0], domain.unknown_member], False
    if state == "unknown_pair":
        return [domain.unknown_member, f"{domain.unknown_member}二"], False
    if state == "ambiguous_pair":
        return [known[0], domain.ambiguous_member], False
    raise ValueError(state)


def _join_members(values: Sequence[str], conjunction: str) -> str:
    if len(values) < 2:
        return "".join(values)
    if conjunction == "and_cn":
        return "和".join(values)
    if conjunction == "with_cn":
        return "与".join(values)
    if conjunction == "enumeration":
        return "、".join(values)
    if conjunction == "including" and len(values) >= 3:
        return "、".join(values[:-1]) + "以及" + values[-1]
    if conjunction == "including":
        return "以及".join(values)
    return " and ".join(values)


def _ranking_values(cue: str, number_form: str) -> tuple[str, int | None, str | None, bool]:
    token = {
        "arabic3": "3",
        "chinese3": "三",
        "top3": "Top 3",
        "arabic10": "10",
        "chinese10": "十",
        "first": "一",
        "missing": "",
    }[number_form]
    expected_n = {"arabic3": 3, "chinese3": 3, "top3": 3, "arabic10": 10, "chinese10": 10, "first": 1}.get(number_form)
    direction = "asc" if cue == "lowest" else "desc"
    if cue == "ordinal":
        return "第一个", 1, direction, True
    if cue == "vague" or number_form == "missing":
        return "前几个", None, direction, False
    if number_form == "top3":
        return token, expected_n, direction, True
    if cue == "front":
        return f"前{token}个", expected_n, direction, True
    return f"{'最低' if cue == 'lowest' else '最高'}的{token}个", expected_n, direction, True


def _range_text(form: str, separator: str) -> tuple[str, tuple[int, int, int, int] | None, bool]:
    sep = {"to_cn": "到", "until_cn": "至", "hyphen": "-", "tilde": "~"}[separator]
    if form == "full":
        return f"2025年1月{sep}2025年6月", (2025, 1, 2025, 6), True
    if form == "abbreviated_end_year":
        return f"2025年1月{sep}6月", (2025, 1, 2025, 6), True
    if form == "numeric":
        numeric_sep = {
            "to_cn": "到",
            "until_cn": "至",
            "hyphen": "~",
            "tilde": "～",
        }[separator]
        return f"2025-01{numeric_sep}2025-06", (2025, 1, 2025, 6), True
    if form == "fullwidth":
        return f"２０２５年１月{sep}６月", (2025, 1, 2025, 6), True
    if form == "current_year":
        return f"今年1月{sep}6月", (2026, 1, 2026, 6), True
    return f"1月{sep}6月", None, False


def _render_core(
    domain: StressDomain, shape: QueryShape, factors: Mapping[str, str]
) -> tuple[str, int | None, str | None, bool, tuple[int, int, int, int] | None, bool]:
    measure = _surface(domain.measure, factors["object_surface"])
    dimension = _surface(domain.dimension, factors["object_surface"])
    filter_field = _surface(domain.filter_field, factors["object_surface"])
    time = _time_text(factors.get("time_form", "none"))
    filter_state = factors.get("filter_state", "none")
    values, executable = _member_values(domain, filter_state)
    # A filter is business scope, not turn-relation evidence.  Keep explicit
    # follow-up/replace wording owned by the independent relation factor.
    filter_text = f"{values[0]}的" if values else ""
    if values and factors.get("filter_count") == "multiple":
        filter_text = f"{values[0]}且{domain.known_dimension_member}的"
    top_n = None
    sort = None
    expected_time = None
    bounded_expression = False

    if shape == QueryShape.SCALAR:
        cue = factors["scalar_cue"]
        core = {
            "amount": f"{time}{filter_text}{measure}是多少",
            "how_many": f"{time}{filter_text}{measure}有多少",
            "show": f"{time}{filter_text}看一下{measure}",
            "total": f"{time}{filter_text}{measure}总计",
        }[cue]
    elif shape == QueryShape.GROUPED:
        cue = factors["grouping_cue"]
        core = {
            "each": f"{time}{filter_text}各{dimension}{measure}",
            "every": f"{time}{filter_text}每个{dimension}{measure}",
            "by": f"{time}{filter_text}按{dimension}看{measure}",
            "split": f"{time}{filter_text}分{dimension}统计{measure}",
            "respectively": f"{time}{filter_text}{dimension}{measure}分别是多少",
        }[cue]
    elif shape == QueryShape.RANKING:
        token, top_n, sort, ranking_complete = _ranking_values(
            factors["ranking_cue"], factors["number_form"]
        )
        executable &= ranking_complete
        if factors["word_order"] == "metric_first":
            core = f"{time}{filter_text}{measure}{token}{dimension}"
        else:
            core = f"{time}{filter_text}{token}{dimension}{measure}"
    elif shape == QueryShape.TREND:
        cue = factors["trend_cue"]
        core = {
            "trend": f"{time}{filter_text}{measure}趋势",
            "change": f"{time}{filter_text}{measure}变化",
            "monthly": f"{time}{filter_text}每个月{measure}走势",
            "by_month": f"{time}{filter_text}按月看{measure}",
            "english": f"{time}{filter_text}{measure} monthly trend",
        }[cue]
    elif shape == QueryShape.BOUNDED_TREND:
        range_text, expected_time, range_resolved = _range_text(
            factors["range_form"], factors["range_separator"]
        )
        bounded_expression = True
        executable &= range_resolved
        core = f"{range_text}{filter_text}每个月{measure}趋势"
    elif shape == QueryShape.ENTITY_LIST:
        cue = factors["entity_cue"]
        core = {
            "which": f"有哪些{dimension}",
            "list": f"列出所有{dimension}",
            "all": f"全部{dimension}都有什么",
            "show": f"展示{dimension}清单",
            "english": f"list all {dimension}",
        }[cue]
    elif shape in {QueryShape.MEMBER_SET, QueryShape.FILTERED_AGGREGATION}:
        values, executable = _member_values(domain, factors["member_state"])
        members = _join_members(values, factors["conjunction"])
        if shape == QueryShape.MEMBER_SET:
            cue = factors["set_cue"]
            core = {
                "respectively": f"{time}{members}的{measure}分别是多少",
                "each_own": f"{time}{members}各自的{measure}是多少",
                "how_much": f"{time}{members}的{measure}分别有多少",
                "formal": f"{time}请分别统计{members}的{measure}",
            }[cue]
        else:
            cue = factors["aggregation_cue"]
            core = {
                "add_up": f"{time}{members}的{measure}加起来多少",
                "combine": f"{time}{members}的{measure}合起来多少",
                "total": f"{time}{members}的{measure}总共多少",
                "altogether": f"{time}{members}的{measure}合计多少",
                "together": f"{time}{members}一起的{measure}是多少",
            }[cue]
    else:  # pragma: no cover - enum exhaustiveness
        raise AssertionError(shape)
    if filter_state == "unknown":
        executable = False
    if filter_state == "ambiguous":
        executable = False
    return core, top_n, sort, executable, expected_time, bounded_expression


def _decorate(core: str, factors: Mapping[str, str]) -> str:
    courtesy = {
        "none": "",
        "please": "请问",
        "help": "帮我",
        "could_you": "能不能帮忙",
        "kindly": "麻烦",
    }[factors["courtesy"]]
    noise = {
        "none": "",
        "roughly": "大概",
        "directly": "直接",
        "briefly": "简单看下",
        "also": "顺便",
    }[factors["noise"]]
    relation_surface = factors["relation_surface"]
    relation = {
        "unspecified": "",
        "fresh": {
            "primary": "独立问题：", "alternate": "新问题：",
            "scope": "单独问：", "among": "重新分析：",
        }[relation_surface],
        "follow_up": {
            "primary": "那", "alternate": "再看",
            "scope": "只看", "among": "其中",
        }[relation_surface],
        "replace": {
            "primary": "换成", "alternate": "改看",
            "scope": "换为", "among": "调整为",
        }[relation_surface],
    }[factors["relation"]]
    punctuation = {
        "none": "",
        "cn_question": "？",
        "en_question": "?",
        "period": "。",
        "comma": "，",
    }[factors["punctuation"]]
    if factors["register"] == "mixed":
        core = core.replace("总计", " total").replace("趋势", " trend")
    if factors["word_order"] == "reordered" and "只看" in core:
        before, after = core.split("只看", 1)
        core = f"只看{after}，{before}" if before else core
    return f"{relation}{courtesy}{noise}{core}{punctuation}"


def generate_cases(
    *, seed: int = DEFAULT_SEED,
    cases_per_domain_shape: int = DEFAULT_CASES_PER_DOMAIN_SHAPE,
) -> Iterable[StressCase]:
    for domain_index, domain in enumerate(DOMAINS):
        for shape_index, shape in enumerate(QueryShape):
            factors = {**COMMON_FACTORS, **SHAPE_FACTORS[shape]}
            rows = _sample_factor_rows(
                factors,
                count=cases_per_domain_shape,
                seed=seed + domain_index * 10_000 + shape_index * 101,
            )
            for row_index, row in enumerate(rows):
                core, top_n, sort, executable, expected_time, bounded = _render_core(
                    domain, shape, row
                )
                question = _decorate(core, row)
                relation = TurnRelationKind(row["relation"])
                expected_shape: QueryShape | None = shape
                if shape == QueryShape.SCALAR and relation in {
                    TurnRelationKind.FOLLOW_UP,
                    TurnRelationKind.REPLACE,
                }:
                    expected_shape = None
                member_state = row.get("member_state") or row.get("filter_state", "none")
                semantic_factors = [
                    shape.value,
                    f"relation:{relation.value}",
                    f"member:{member_state}",
                ]
                if bounded:
                    semantic_factors.append(f"time:{row['range_form']}")
                if shape == QueryShape.RANKING:
                    semantic_factors.append(f"ranking:{row['ranking_cue']}")
                case_id = f"m594-{domain_index}-{shape_index}-{row_index:04d}"
                yield StressCase(
                    case_id=case_id,
                    seed=seed,
                    domain=domain,
                    shape=shape,
                    factors=tuple(sorted(row.items())),
                    question=question,
                    expected_shape=expected_shape,
                    expected_relation=relation,
                    expected_top_n=top_n,
                    expected_sort=sort,
                    expected_execution=executable,
                    expected_time=expected_time,
                    expected_bounded_expression=bounded,
                    semantic_factors=tuple(semantic_factors),
                    language_pattern=(
                        row.get("grouping_cue")
                        or row.get("ranking_cue")
                        or row.get("trend_cue")
                        or row.get("entity_cue")
                        or row.get("set_cue")
                        or row.get("aggregation_cue")
                        or row.get("scalar_cue")
                        or "generic"
                    ),
                )


def _shrink_question(case: StressCase, still_fails: Callable[[str], bool]) -> str:
    candidates = [case.question]
    question = case.question
    for token in (
        "能不能帮忙", "简单看下", "独立问题：", "请问", "帮我", "麻烦",
        "大概", "直接", "顺便", "那", "换成",
    ):
        candidate = question.replace(token, "")
        if candidate and still_fails(candidate):
            question = candidate
            candidates.append(question)
    candidate = question.rstrip("？?。，")
    if candidate and still_fails(candidate):
        question = candidate
        candidates.append(question)
    return min(candidates, key=lambda value: (len(value), value))


@dataclass(frozen=True)
class RuntimeStressFixture:
    """A runtime-owned schema topology used only by the stress harness."""

    schema: SemanticModelSchema
    catalog: SemanticCatalog
    measure_table: str
    dimension_table: str
    filter_table: str
    date_table: str
    date_field: str
    temporal_dimension: str


def _runtime_fixture(domain: StressDomain) -> RuntimeStressFixture:
    """Build structurally different runtime schemas without business rules."""
    key = domain.fixture_id
    measure, dimension, filter_field = (
        domain.measure[0], domain.dimension[0], domain.filter_field[0]
    )
    if key == "sales_star_duplicate":
        measure_table, dimension_table, filter_table, date_table = (
            "SalesFacts", "Products", "Areas", "Calendar"
        )
        date_field, temporal_dimension = "Order Date", "Month"
        tables = [
            TableSchema(
                name=measure_table,
                columns=[
                    ColumnSchema(name=dimension, data_type="string"),
                    ColumnSchema(name=filter_field, data_type="string"),
                    ColumnSchema(name="Product Key", data_type="int64", is_key=True),
                    ColumnSchema(name="Area Key", data_type="int64", is_key=True),
                ],
                measures=[MeasureSchema(name=measure, expression="SUM('SalesFacts'[Amount])")],
            ),
            TableSchema(name=dimension_table, columns=[
                ColumnSchema(name="Product Key", data_type="int64", is_key=True),
                ColumnSchema(name=dimension, data_type="string"),
            ]),
            TableSchema(name=filter_table, columns=[
                ColumnSchema(name="Area Key", data_type="int64", is_key=True),
                ColumnSchema(name=filter_field, data_type="string"),
            ]),
            TableSchema(name=date_table, columns=[
                ColumnSchema(name=date_field, data_type="datetime"),
                ColumnSchema(name=temporal_dimension, data_type="datetime"),
            ]),
        ]
        relationships = [
            RelationshipSchema(from_table=measure_table, from_column="Product Key", to_table=dimension_table, to_column="Product Key"),
            RelationshipSchema(from_table=measure_table, from_column="Area Key", to_table=filter_table, to_column="Area Key"),
        ]
    elif key == "education_snowflake":
        measure_table, dimension_table, filter_table, date_table = (
            "EnrollmentFacts", "Programs", "Campuses", "AcademicCalendar"
        )
        date_field, temporal_dimension = "Enrollment Date", "Academic Month"
        tables = [
            TableSchema(name=measure_table, columns=[
                ColumnSchema(name="Program Link", data_type="int64", is_key=True),
                ColumnSchema(name="Campus Key", data_type="int64", is_key=True),
            ], measures=[MeasureSchema(name=measure, expression="DIVIDE([Pass],[Total])")]),
            TableSchema(name="ProgramBridge", columns=[
                ColumnSchema(name="Program Link", data_type="int64", is_key=True),
                ColumnSchema(name="Program Key", data_type="int64", is_key=True),
            ]),
            TableSchema(name=dimension_table, columns=[
                ColumnSchema(name="Program Key", data_type="int64", is_key=True),
                ColumnSchema(name=dimension, data_type="string"),
            ]),
            TableSchema(name=filter_table, columns=[
                ColumnSchema(name="Campus Key", data_type="int64", is_key=True),
                ColumnSchema(name=filter_field, data_type="string"),
            ]),
            TableSchema(name=date_table, columns=[
                ColumnSchema(name=date_field, data_type="datetime"),
                ColumnSchema(name=temporal_dimension, data_type="datetime"),
            ]),
        ]
        relationships = [
            RelationshipSchema(from_table=measure_table, from_column="Program Link", to_table="ProgramBridge", to_column="Program Link"),
            RelationshipSchema(from_table="ProgramBridge", from_column="Program Key", to_table=dimension_table, to_column="Program Key"),
            RelationshipSchema(from_table=measure_table, from_column="Campus Key", to_table=filter_table, to_column="Campus Key"),
        ]
    elif key == "inventory_flat_multidate":
        measure_table = dimension_table = filter_table = date_table = "InventorySnapshot"
        date_field, temporal_dimension = "Snapshot Date", "Snapshot Month"
        tables = [TableSchema(name=measure_table, columns=[
            ColumnSchema(name="Warehouse Key", data_type="int64", is_key=True),
            ColumnSchema(name=dimension, data_type="string"),
            ColumnSchema(name=filter_field, data_type="string"),
            ColumnSchema(name=date_field, data_type="datetime"),
            ColumnSchema(name=temporal_dimension, data_type="datetime"),
            ColumnSchema(name="Received Date", data_type="datetime"),
        ], measures=[MeasureSchema(name=measure, expression="SUM('InventorySnapshot'[Units])")])]
        relationships = []
    else:
        measure_table, dimension_table, filter_table, date_table = (
            "ShipmentFacts", "Carriers", "Hubs", "ServiceCalendar"
        )
        date_field, temporal_dimension = "Ship Date", "Service Month"
        tables = [
            TableSchema(name=measure_table, columns=[
                ColumnSchema(name="Carrier Key", data_type="int64", is_key=True),
                ColumnSchema(name="Hub Key", data_type="int64", is_key=True),
            ], measures=[MeasureSchema(name=measure, expression="COUNTROWS('ShipmentFacts')")]),
            TableSchema(name=dimension_table, columns=[
                ColumnSchema(name="Carrier Key", data_type="int64", is_key=True),
                ColumnSchema(name=dimension, data_type="string"),
            ]),
            TableSchema(name=filter_table, columns=[
                ColumnSchema(name="Hub Key", data_type="int64", is_key=True),
                ColumnSchema(name=filter_field, data_type="string"),
            ]),
            TableSchema(name=date_table, columns=[
                ColumnSchema(name=date_field, data_type="datetime"),
                ColumnSchema(name=temporal_dimension, data_type="datetime"),
            ]),
        ]
        relationships = [
            RelationshipSchema(from_table=measure_table, from_column="Carrier Key", to_table=dimension_table, to_column="Carrier Key"),
            RelationshipSchema(from_table=measure_table, from_column="Hub Key", to_table=filter_table, to_column="Hub Key"),
        ]
    schema = SemanticModelSchema(
        name=f"M5.9.4 {key}", key=key, tables=tables,
        relationships=relationships, runtime_identity=f"stress:{key}",
        session_generation=1, metadata_source="mock",
    )
    catalog = SemanticCatalog(
        semantic_model_key=key,
        schema_fingerprint=f"stress-fingerprint:{key}",
        objects=(
            CatalogObject(object_id=f"measure:{measure_table}:{measure}", canonical_name=measure, object_type=SemanticObjectType.MEASURE, table_name=measure_table, data_type="double", aliases=domain.measure[1:]),
            CatalogObject(object_id=f"field:{dimension_table}:{dimension}", canonical_name=dimension, object_type=SemanticObjectType.FIELD, table_name=dimension_table, data_type="string", aliases=domain.dimension[1:], member_aliases={domain.known_dimension_member.casefold(): domain.known_dimension_member}),
            CatalogObject(object_id=f"field:{filter_table}:{filter_field}", canonical_name=filter_field, object_type=SemanticObjectType.FIELD, table_name=filter_table, data_type="string", aliases=domain.filter_field[1:], member_aliases={value.casefold(): value for value in domain.known_members}),
            CatalogObject(
                object_id=f"field:{date_table}:{date_field}", canonical_name=date_field,
                object_type=SemanticObjectType.FIELD, table_name=date_table,
                data_type="datetime", temporal_role="default",
            ),
            CatalogObject(
                object_id=f"field:{date_table}:{temporal_dimension}",
                canonical_name=temporal_dimension,
                object_type=SemanticObjectType.FIELD, table_name=date_table,
                data_type="datetime",
                temporal_grouping=TemporalGroupingBinding(
                    grain="month", date_field=date_field, date_table_name=date_table
                ),
            ),
        ),
    )
    return RuntimeStressFixture(
        schema=schema, catalog=catalog, measure_table=measure_table,
        dimension_table=dimension_table, filter_table=filter_table,
        date_table=date_table, date_field=date_field,
        temporal_dimension=temporal_dimension,
    )


def _time_spec(case: StressCase, date_field: str) -> TimeRangeSpec | None:
    form = case.factor("time_form")
    if case.expected_time is not None:
        start_year, start_month, end_year, end_month = case.expected_time
        return TimeRangeSpec(
            date_field=date_field,
            start_date=date(start_year, start_month, 1),
            end_date=date(end_year, end_month, monthrange(end_year, end_month)[1]),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        )
    ranges = {
        "absolute_month": (date(2025, 5, 1), date(2025, 5, 31), TimeRangeMode.EXPLICIT_RANGE),
        "relative_month": (date(2026, 8, 1), date(2026, 8, 31), TimeRangeMode.EXPLICIT_RANGE),
        "absolute_year": (date(2025, 1, 1), date(2025, 12, 31), TimeRangeMode.EXPLICIT_RANGE),
        "recent6": (date(2026, 3, 1), date(2026, 8, 31), TimeRangeMode.RECENT_MONTHS),
        "recent12": (date(2025, 9, 1), date(2026, 8, 31), TimeRangeMode.RECENT_MONTHS),
        "relative_year": (date(2026, 1, 1), date(2026, 9, 9), TimeRangeMode.CURRENT_YEAR),
    }
    if form not in ranges:
        return None
    start, end, mode = ranges[form]
    return TimeRangeSpec(
        date_field=date_field, start_date=start, end_date=end, mode=mode,
        grain="month" if case.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND} else "day",
    )


def _canonical_plan(case: StressCase, fixture: RuntimeStressFixture) -> CanonicalQueryPlan:
    shape = case.shape
    dimensions: list[str] = []
    measures = [] if shape == QueryShape.ENTITY_LIST else [case.domain.measure[0]]
    if shape in {QueryShape.ENTITY_LIST, QueryShape.GROUPED, QueryShape.RANKING}:
        dimensions = [case.domain.dimension[0]]
    elif shape == QueryShape.MEMBER_SET:
        dimensions = [case.domain.filter_field[0]]
    elif shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
        dimensions = [fixture.temporal_dimension]
    filters: list[StructuredFilter] = []
    filter_state = case.factor("filter_state")
    if filter_state == "known":
        filters.append(StructuredFilter(
            field=case.domain.filter_field[0], value=case.domain.known_members[0]
        ))
        if case.factor("filter_count") == "multiple":
            filters.append(StructuredFilter(
                field=case.domain.dimension[0],
                value=case.domain.known_dimension_member,
            ))
    member_state = case.factor("member_state")
    if shape in {QueryShape.MEMBER_SET, QueryShape.FILTERED_AGGREGATION}:
        member_values, _ = _member_values(case.domain, member_state)
        filters = [StructuredFilter(
            field=case.domain.filter_field[0], operator=FilterOperator.IN_SET,
            value=member_values,
        )]
    hints = {
        case.domain.dimension[0]: fixture.dimension_table,
        case.domain.filter_field[0]: fixture.filter_table,
        fixture.date_field: fixture.date_table,
        fixture.temporal_dimension: fixture.date_table,
    }
    return CanonicalQueryPlan(
        normalized_question=f"stress:{case.canonical_signature()}",
        semantic_model_key=case.domain.fixture_id,
        query_shape=shape,
        measures=measures,
        dimensions=dimensions,
        filters=filters,
        time_range=_time_spec(case, fixture.date_field),
        sort=case.expected_sort if shape == QueryShape.RANKING else None,
        top_n=case.expected_top_n if shape == QueryShape.RANKING else None,
        dimension_tables=hints,
        dimension_order=("asc" if shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND} else None),
    )


def _query_result(case: StressCase, plan: CanonicalQueryPlan) -> QueryResult:
    if case.shape == QueryShape.ENTITY_LIST:
        columns, rows = list(plan.dimensions), [["A"], ["B"], ["C"]]
    elif case.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
        if plan.time_range is not None:
            first, last = plan.time_range.start_date, plan.time_range.end_date
        else:
            first, last = date(2025, 1, 1), date(2025, 3, 1)
        columns = [plan.dimensions[0], plan.measures[0]]
        rows = [[first.isoformat(), 1], [last.isoformat(), 2]] if first != last else [[first.isoformat(), 1]]
    elif plan.dimensions:
        count = 1 if plan.top_n == 1 else min(plan.top_n or 3, 3)
        labels = ["A", "B", "C"][:count]
        metrics = list(range(1, count + 1))
        if plan.sort == "desc":
            metrics.reverse()
        columns = [plan.dimensions[0], plan.measures[0]]
        rows = [[label, value] for label, value in zip(labels, metrics)]
    else:
        columns, rows = [plan.measures[0]], [[42]]
    return QueryResult(
        result_id=f"result:{case.canonical_signature()}",
        semantic_model_key=plan.semantic_model_key,
        columns=columns, rows=rows, row_count=len(rows), source_mode="mock",
        request_id=f"request:{case.canonical_signature()}",
    )


def _semantic_observation(case: StressCase, router: QuestionRouter) -> tuple[object, ...]:
    decision = router.route(case.question)
    parsed = parse_explicit_month_range(case.question, reference_year=2026)
    time_value = None if parsed is None else (
        parsed.start_year, parsed.start_month, parsed.end_year, parsed.end_month
    )
    return (
        decision.route.value,
        getattr(decision.query_shape, "value", None),
        TurnRelationEvidence.classify(case.question).kind.value,
        SemanticGroundingService._extract_top_n(case.question)
        if case.shape == QueryShape.RANKING else None,
        case.expected_sort,
        time_value if case.shape == QueryShape.BOUNDED_TREND else case.factor("time_form"),
    )


class BusinessLanguageStressHarness:
    """Run language metamorphs and the frozen deterministic fact pipeline."""

    def __init__(self, *, seed: int = DEFAULT_SEED) -> None:
        self.seed = seed
        self.router = QuestionRouter()

    def _failure(
        self,
        case: StressCase,
        category: str,
        expected: object,
        actual: object,
        predicate: Callable[[str], bool],
    ) -> StressFailure:
        return StressFailure(
            category=category,
            expected=str(expected),
            actual=str(actual),
            case=case,
            minimum_question=_shrink_question(case, predicate),
        )

    def evaluate(self, case: StressCase) -> StressFailure | None:
        decision = self.router.route(case.question)
        actual_shape = decision.query_shape
        if decision.route != QuestionRoute.BUSINESS_DATA_QUERY or actual_shape != case.expected_shape:
            return self._failure(
                case,
                "shape_mismatch",
                getattr(case.expected_shape, "value", None),
                getattr(actual_shape, "value", decision.route.value),
                lambda text: self.router.route(text).query_shape != case.expected_shape,
            )
        relation = TurnRelationEvidence.classify(case.question).kind
        if relation != case.expected_relation:
            return self._failure(
                case,
                "turn_relation_mismatch",
                case.expected_relation.value,
                relation.value,
                lambda text: TurnRelationEvidence.classify(text).kind != case.expected_relation,
            )
        if case.shape == QueryShape.RANKING:
            actual_top_n = SemanticGroundingService._extract_top_n(case.question)
            if actual_top_n != case.expected_top_n:
                return self._failure(
                    case,
                    "ranking_mismatch",
                    case.expected_top_n,
                    actual_top_n,
                    lambda text: SemanticGroundingService._extract_top_n(text) != case.expected_top_n,
                )
        if case.shape == QueryShape.BOUNDED_TREND:
            parsed = parse_explicit_month_range(case.question, reference_year=2026)
            actual_time = (
                (parsed.start_year, parsed.start_month, parsed.end_year, parsed.end_month)
                if parsed is not None
                else None
            )
            if actual_time != case.expected_time:
                return self._failure(
                    case,
                    "time_range_mismatch",
                    case.expected_time,
                    actual_time,
                    lambda text: (
                        (lambda item: None if item is None else (
                            item.start_year, item.start_month, item.end_year, item.end_month
                        ))(parse_explicit_month_range(text, reference_year=2026))
                        != case.expected_time
                    ),
                )
        return None

    @staticmethod
    def _direct_failure(
        case: StressCase, category: str, expected: object, actual: object
    ) -> StressFailure:
        return StressFailure(
            category=category,
            expected=str(expected),
            actual=str(actual),
            case=case,
            minimum_question=case.question,
        )

    def evaluate_execution(
        self, case: StressCase
    ) -> tuple[StressFailure | None, str | None]:
        """Prove one unique canonical semantic through DAX and fact authority."""
        try:
            fixture = _runtime_fixture(case.domain)
            plan = _canonical_plan(case, fixture)
            completeness = CanonicalShapeCompletenessGate().validate(
                plan, catalog=fixture.catalog
            )
            if not completeness.complete:
                return self._direct_failure(
                    case, "canonical_mismatch", "complete", completeness
                ), None
            first = DeterministicDAXBuilder().build(plan, fixture.schema)
            second = DeterministicDAXBuilder().build(plan, fixture.schema)
            if first.dax != second.dax:
                return self._direct_failure(
                    case, "dax_mismatch", "identical deterministic DAX", "changed DAX"
                ), None
            verification_errors = RestrictedDAXVerifier().validate(
                first, plan, fixture.schema
            )
            if verification_errors:
                return self._direct_failure(
                    case, "dax_mismatch", "independent verifier PASS",
                    verification_errors,
                ), None
            result = _query_result(case, plan)
            inspection = ResultSemanticInspectionGate().inspect(
                plan, result, dax_semantic_verified=True
            )
            facts = VerifiedFactSetBuilder().build(plan, result)
            if facts.semantic_model_key != plan.semantic_model_key:
                return self._direct_failure(
                    case, "cross_model_bleed", plan.semantic_model_key,
                    facts.semantic_model_key,
                ), None
            if any(
                fact.provenance.plan_semantics != plan.model_dump(mode="json")
                for fact in facts.facts
            ):
                return self._direct_failure(
                    case, "result_fact_mismatch", "canonical plan provenance",
                    "fact provenance diverged",
                ), None
            if len(facts.by_type(FactType.APPLIED_FILTER)) != len(plan.filters):
                return self._direct_failure(
                    case, "result_fact_mismatch", len(plan.filters),
                    len(facts.by_type(FactType.APPLIED_FILTER)),
                ), None
            expected_time_facts = 1 if plan.time_range is not None else 0
            if len(facts.by_type(FactType.APPLIED_TIME_RANGE)) != expected_time_facts:
                return self._direct_failure(
                    case, "result_fact_mismatch", expected_time_facts,
                    len(facts.by_type(FactType.APPLIED_TIME_RANGE)),
                ), None
            scope = DeterministicQueryScopeDescriptor().build(plan)
            required_scope = [
                *plan.measures, *plan.dimensions,
                *(str(value) for item in plan.filters for value in (
                    item.value if item.operator == FilterOperator.IN_SET else [item.value]
                )),
            ]
            if any(value not in scope for value in required_scope):
                return self._direct_failure(
                    case, "result_fact_mismatch", required_scope, scope
                ), None
            witness = hashlib.sha256(json.dumps({
                "plan": plan.model_dump(mode="json"),
                "dax": first.dax,
                "inspection": inspection.model_dump(mode="json"),
                "facts": facts.model_dump(mode="json"),
                "scope": scope,
            }, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            return None, witness
        except Exception as exc:  # pragma: no cover - diagnostics exercised on failure
            category = (
                "dax_mismatch" if "dax" in type(exc).__name__.casefold()
                or "dax" in str(exc).casefold()
                else "result_fact_mismatch"
            )
            return self._direct_failure(
                case, category, "frozen deterministic pipeline PASS",
                f"{type(exc).__name__}:{exc}",
            ), None

    def run(
        self, *, cases_per_domain_shape: int = DEFAULT_CASES_PER_DOMAIN_SHAPE
    ) -> StressSummary:
        summary = StressSummary(seed=self.seed)
        observations: dict[str, tuple[object, ...]] = {}
        execution_witnesses: dict[str, str] = {}
        signature_counts: Counter[str] = Counter()
        for case in generate_cases(
            seed=self.seed, cases_per_domain_shape=cases_per_domain_shape
        ):
            summary.total += 1
            signature = case.canonical_signature()
            signature_counts[signature] += 1
            member_state = case.factor("member_state") or case.factor("filter_state")
            if member_state in {
                "unknown", "ambiguous", "known_unknown", "unknown_pair",
                "ambiguous_pair",
            }:
                summary.unknown_ambiguous_cases += 1
            failure = self.evaluate(case)
            if failure is not None:
                summary.add_failure(failure)
                continue
            observation = _semantic_observation(case, self.router)
            prior_observation = observations.get(signature)
            if prior_observation is not None and prior_observation != observation:
                summary.add_failure(self._direct_failure(
                    case, "canonical_mismatch", prior_observation, observation
                ))
                continue
            observations.setdefault(signature, observation)
            if case.expected_execution and signature not in execution_witnesses:
                summary.semantic_execution_cases += 1
                execution_failure, witness = self.evaluate_execution(case)
                if execution_failure is not None:
                    summary.add_failure(execution_failure)
                    continue
                assert witness is not None
                execution_witnesses[signature] = witness
        summary.metamorphic_groups = sum(
            1 for count in signature_counts.values() if count > 1
        )
        summary.metamorphic_variants = sum(
            count for count in signature_counts.values() if count > 1
        )
        summary.finish()
        return summary


def coverage_matrix(cases: Iterable[StressCase]) -> dict[str, object]:
    shapes: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    patterns: Counter[str] = Counter()
    factors: defaultdict[str, set[str]] = defaultdict(set)
    total = 0
    for case in cases:
        total += 1
        shapes[case.shape.value] += 1
        domains[case.domain.fixture_id] += 1
        patterns[case.language_pattern] += 1
        for name, value in case.factors:
            factors[name].add(value)
    return {
        "total": total,
        "by_shape": dict(sorted(shapes.items())),
        "by_domain": dict(sorted(domains.items())),
        "by_language_pattern": dict(sorted(patterns.items())),
        "factor_cardinality": {
            name: len(values) for name, values in sorted(factors.items())
        },
    }
