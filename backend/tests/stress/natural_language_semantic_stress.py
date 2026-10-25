"""Natural-language semantic stress harness (test-side oracle only).

The harness generates ordinary business questions from a runtime model profile
whose canonical identities are known only to the test.  Production code never
imports this module and never reads the oracle.

It deliberately avoids schema syntax: questions use the business labels a user
would say, never ``Table[Column]`` or canonical IDs unless the profile says the
user literally speaks that way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

Layer = Literal[
    "UNDERSTANDING",
    "RETRIEVAL",
    "RESOLUTION",
    "MEMBER",
    "TEMPORAL",
    "STATE",
    "PLAN",
    "DAX",
    "WIRE_NORMALIZATION",
    "FACTS",
    "ANSWER",
]


@dataclass(frozen=True)
class MeasureProfile:
    canonical: str
    natural: str
    description: str = ""
    format_string: str | None = None


@dataclass(frozen=True)
class DimensionProfile:
    canonical: str
    table: str
    natural: str
    plural: str
    description: str = ""


@dataclass(frozen=True)
class MemberProfile:
    field: str
    value: str
    natural: str


@dataclass(frozen=True)
class StressModelProfile:
    key: str
    label: str
    measures: tuple[MeasureProfile, ...]
    dimensions: tuple[DimensionProfile, ...]
    members: tuple[MemberProfile, ...] = ()
    date_field: str | None = None
    year: int = 2025
    no_match_member: str = "Atlantis"
    unknown_term: str = "customer happiness index"
    ambiguous_phrase: str | None = None
    localized_measure: str | None = None
    localized_dimension: str | None = None
    localized_member: str | None = None


@dataclass(frozen=True)
class StressCase:
    case_id: str
    model_key: str
    kind: str
    question: str
    expected_shape: str | None
    expected_measure: str | None = None
    expected_measures: tuple[str, ...] = ()
    expected_dimension: str | None = None
    expected_member: str | None = None
    expected_member_field: str | None = None
    expected_time_range: tuple[str, str] | None = None
    expected_sort: str | None = None
    expected_top_n: int | None = None
    relation: str = "fresh_question"
    chain_id: str | None = None
    expects_clarification: bool = False
    clarification_layer: Layer | None = None

    def oracle(self) -> dict[str, Any]:
        """Test-side expected semantics; never passed to production."""

        return {
            "shape": self.expected_shape,
            "measure": self.expected_measure,
            "measures": list(self.expected_measures),
            "dimension": self.expected_dimension,
            "member": self.expected_member,
            "member_field": self.expected_member_field,
            "time_range": self.expected_time_range,
            "sort": self.expected_sort,
            "top_n": self.expected_top_n,
            "relation": self.relation,
            "clarification": self.expects_clarification,
        }


def _measure(profile: StressModelProfile, index: int = 0) -> MeasureProfile:
    return profile.measures[index]


def _dimension(profile: StressModelProfile, index: int = 0) -> DimensionProfile:
    return profile.dimensions[index]


def _member(profile: StressModelProfile, index: int = 0) -> MemberProfile | None:
    return profile.members[index] if profile.members else None


def generate_cases(profile: StressModelProfile) -> tuple[StressCase, ...]:
    """Generate a fixed 16-20 case family for one real/model profile."""

    measure = _measure(profile)
    measure2 = _measure(profile, 1) if len(profile.measures) > 1 else measure
    dimension = _dimension(profile)
    member = _member(profile)
    member2 = _member(profile, 1) if len(profile.members) > 1 else member
    prefix = profile.key
    cases: list[StressCase] = []

    def add(
        kind: str,
        question: str,
        shape: str | None,
        **kwargs: Any,
    ) -> None:
        cases.append(StressCase(
            case_id=f"{prefix}-{len(cases) + 1:02d}-{kind}",
            model_key=profile.key,
            kind=kind,
            question=question,
            expected_shape=shape,
            **kwargs,
        ))

    add(
        "scalar",
        f"What is the total {measure.natural}?",
        "scalar",
        expected_measure=measure.canonical,
    )
    add(
        "grouped",
        f"Show {measure.natural} by {dimension.natural}.",
        "grouped",
        expected_measure=measure.canonical,
        expected_dimension=dimension.canonical,
    )
    add(
        "ranking_desc",
        f"Which five {dimension.plural} generated the highest {measure.natural}?",
        "ranking",
        expected_measure=measure.canonical,
        expected_dimension=dimension.canonical,
        expected_sort="desc",
        expected_top_n=5,
    )
    add(
        "ranking_asc",
        f"Which three {dimension.plural} had the lowest {measure.natural}?",
        "ranking",
        expected_measure=measure.canonical,
        expected_dimension=dimension.canonical,
        expected_sort="asc",
        expected_top_n=3,
    )
    if member is not None:
        add(
            "member_filter",
            f"How much {measure.natural} did {member.natural} generate?",
            "filtered_aggregation",
            expected_measure=measure.canonical,
            expected_member=member.value,
            expected_member_field=member.field,
        )
        add(
            "multi_measure",
            f"What are {measure.natural} and {measure2.natural} for {member.natural}?",
            "filtered_aggregation",
            expected_measures=(measure.canonical, measure2.canonical),
            expected_member=member.value,
            expected_member_field=member.field,
        )
    add(
        "time_range",
        f"What was {measure.natural} in the first half of {profile.year}?",
        "scalar",
        expected_measure=measure.canonical,
        expected_time_range=(f"{profile.year}-01-01", f"{profile.year}-06-30"),
    )
    add(
        "bounded_trend",
        f"Show the monthly {measure.natural} trend from January to June {profile.year}.",
        "bounded_trend",
        expected_measure=measure.canonical,
        expected_time_range=(f"{profile.year}-01-01", f"{profile.year}-06-30"),
    )
    add(
        "trend",
        f"Show the {measure.natural} trend over the last 6 months.",
        "trend",
        expected_measure=measure.canonical,
    )
    if member is not None:
        add(
            "follow_up_measure",
            f"Now show {measure2.natural} instead.",
            None,
            expected_measure=measure2.canonical,
            relation="follow_up",
            chain_id=f"{prefix}-chain",
            expected_dimension=None,
        )
        add(
            "follow_up_filter",
            f"Only for {member.natural}.",
            None,
            relation="follow_up",
            chain_id=f"{prefix}-chain",
            expected_member=member.value,
            expected_member_field=member.field,
        )
    add(
        "fresh_reset",
        f"New question: what is the total {measure2.natural}?",
        "scalar",
        expected_measure=measure2.canonical,
        relation="fresh_question",
    )
    if profile.ambiguous_phrase:
        add(
            "ambiguity",
            f"What is the {profile.ambiguous_phrase}?",
            None,
            expects_clarification=True,
            clarification_layer="UNDERSTANDING",
        )
    add(
        "member_no_match",
        f"How much {measure.natural} did {profile.no_match_member} generate?",
        None,
        expects_clarification=True,
        clarification_layer="MEMBER",
    )
    add(
        "unknown_term",
        f"What is the {profile.unknown_term}?",
        None,
        expects_clarification=True,
        clarification_layer="UNDERSTANDING",
    )
    if profile.localized_measure and profile.localized_dimension:
        add(
            "cross_language",
            f"按{profile.localized_dimension}看{profile.localized_measure}",
            "grouped",
            expected_measure=measure.canonical,
            expected_dimension=dimension.canonical,
        )
    add(
        "scalar_second_measure",
        f"What is the total {measure2.natural}?",
        "scalar",
        expected_measure=measure2.canonical,
    )
    return tuple(cases)


def generate_matrix(
    profiles: Iterable[StressModelProfile],
) -> tuple[StressCase, ...]:
    cases: list[StressCase] = []
    for profile in profiles:
        cases.extend(generate_cases(profile))
    return tuple(cases)


_SCHEMA_SYNTAX = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_.]*|'[^']+')\[[^\]]+\]"
)


def assert_natural_questions(cases: Iterable[StressCase]) -> None:
    """Guard the harness itself against schema-aware benchmark phrasing."""

    for case in cases:
        if _SCHEMA_SYNTAX.search(case.question):
            raise AssertionError(
                f"schema syntax leaked into natural question: {case.case_id}"
            )
        if case.question.strip() != case.question:
            raise AssertionError(f"question has outer whitespace: {case.case_id}")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    model_key: str
    kind: str
    question: str
    outcome: Literal["PASS", "CLARIFICATION", "FAIL"]
    layer: Layer | None = None
    detail: str = ""

    def safe(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_key": self.model_key,
            "kind": self.kind,
            "question": self.question,
            "outcome": self.outcome,
            "layer": self.layer,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class StressReport:
    results: tuple[CaseResult, ...] = ()

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(item.outcome == "PASS" for item in self.results)

    @property
    def clarifications(self) -> int:
        return sum(item.outcome == "CLARIFICATION" for item in self.results)

    @property
    def failed(self) -> int:
        return sum(item.outcome == "FAIL" for item in self.results)

    def clusters(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.results:
            if item.outcome != "FAIL":
                continue
            key = f"{item.layer or 'UNKNOWN'}:{item.kind}"
            result[key] = result.get(key, 0) + 1
        return dict(sorted(result.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "clarifications": self.clarifications,
            "failed": self.failed,
            "clusters": self.clusters(),
            "results": [item.safe() for item in self.results],
        }

    def safe_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)


def _frame(audit: dict[str, Any]) -> dict[str, Any]:
    value = (audit.get("execution_audit") or {}).get("semantic_frame")
    return value if isinstance(value, dict) else {}


def _plan(audit: dict[str, Any]) -> dict[str, Any]:
    value = (audit.get("execution_audit") or {}).get("canonical_query_plan")
    return value if isinstance(value, dict) else {}


def _filter_values(plan: dict[str, Any]) -> list[tuple[str, str]]:
    result = []
    for item in plan.get("filters") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        values = value if isinstance(value, list) else [value]
        result.extend((str(item.get("field")), str(entry)) for entry in values)
    return result


def evaluate_case(case: StressCase, audit: dict[str, Any]) -> CaseResult:
    """Classify one real product audit against the test-side oracle.

    The first wrong layer wins; later layers are not re-litigated.
    """

    state = str(audit.get("terminal_state") or "")
    plan = _plan(audit)
    frame = _frame(audit)
    execution = audit.get("execution_audit") or {}

    if case.expects_clarification:
        if state == "clarification_required":
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "CLARIFICATION", case.clarification_layer,
                str(execution.get("clarification_reason") or ""),
            )
        if state == "completed":
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", case.clarification_layer or "UNDERSTANDING",
                "expected clarification but the turn completed",
            )
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", case.clarification_layer or "UNDERSTANDING",
            f"expected clarification, got {state}",
        )

    if state != "completed":
        layer: Layer = "UNDERSTANDING"
        if state == "clarification_required":
            layer = "RESOLUTION"
        elif state == "tool_failed":
            layer = "DAX"
        elif state == "validation_failed":
            stage = str((audit.get("failure") or {}).get("stage") or "")
            if "grounding" in stage or "semantic" in stage:
                layer = "RESOLUTION"
            elif "plan" in stage:
                layer = "PLAN"
            elif "dax" in stage:
                layer = "DAX"
            elif "result" in stage:
                layer = "WIRE_NORMALIZATION"
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", layer, f"terminal_state={state}",
        )

    expected_shape = case.expected_shape
    actual_shape = plan.get("query_shape") or frame.get("query_shape")
    if expected_shape is not None and actual_shape != expected_shape:
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "UNDERSTANDING",
            f"shape expected={expected_shape} actual={actual_shape}",
        )
    expected_measures = (
        case.expected_measures
        or ((case.expected_measure,) if case.expected_measure else ())
    )
    actual_measures = tuple(plan.get("measures") or ())
    if expected_measures and not set(expected_measures).issubset(set(actual_measures)):
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "RESOLUTION",
            f"measures expected={expected_measures} actual={actual_measures}",
        )
    if case.expected_dimension is not None:
        actual_dimensions = tuple(plan.get("dimensions") or ())
        if case.expected_dimension not in actual_dimensions:
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", "RESOLUTION",
                f"dimension expected={case.expected_dimension} actual={actual_dimensions}",
            )
    if case.expected_member is not None:
        filters = _filter_values(plan)
        expected = (case.expected_member_field, case.expected_member)
        if case.expected_member_field is None:
            matched = any(value == case.expected_member for _, value in filters)
        else:
            matched = expected in filters or any(
                field == case.expected_member_field and value == case.expected_member
                for field, value in filters
            )
        if not matched:
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", "MEMBER",
                f"member expected={expected} actual={filters}",
            )
    if case.expected_time_range is not None:
        time_range = plan.get("time_range") or {}
        start = str(time_range.get("start_date") or "")
        end = str(time_range.get("end_date") or "")
        if (start, end) != case.expected_time_range:
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", "TEMPORAL",
                f"time expected={case.expected_time_range} actual={(start, end)}",
            )
    if case.expected_sort is not None and plan.get("sort") != case.expected_sort:
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "PLAN",
            f"sort expected={case.expected_sort} actual={plan.get('sort')}",
        )
    if case.expected_top_n is not None and plan.get("top_n") != case.expected_top_n:
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "PLAN",
            f"top_n expected={case.expected_top_n} actual={plan.get('top_n')}",
        )
    if case.chain_id is not None and case.relation == "follow_up":
        relation = (execution.get("turn_relation_evidence") or {}).get("kind")
        if relation != "follow_up":
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", "STATE",
                f"relation expected=follow_up actual={relation}",
            )
    dax = execution.get("dax") or audit.get("dax")
    if dax is not None and expected_measures:
        if not all(f"[{name}]" in str(dax) for name in expected_measures):
            return CaseResult(
                case.case_id, case.model_key, case.kind, case.question,
                "FAIL", "DAX", "deterministic DAX does not use the expected measure",
            )
    if audit.get("memory_commit") is not True:
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "FACTS", "completed turn did not commit a verified fact memory",
        )
    answer = audit.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return CaseResult(
            case.case_id, case.model_key, case.kind, case.question,
            "FAIL", "ANSWER", "completed turn has no answer text",
        )
    return CaseResult(
        case.case_id, case.model_key, case.kind, case.question, "PASS"
    )
