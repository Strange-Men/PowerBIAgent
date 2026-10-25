"""Operator-run real-LLM semantic stress (no Power BI/business rows).

This drives the production Understanding + Grounding chain with the configured
real LLM and synthetic semantic-model metadata.  It proves that ordinary
natural-language questions reach the intended canonical objects without schema
syntax.  It is not a CI test and never prints prompts or raw model output.

Usage (owned output path required):
    python -m backend.tests.stress.real_llm_semantic_stress \
        --output D:/AAA_Workfile/PBIAgentTest/M6.5.2FIX4/Real/llm-stress.json \
        --limit 16
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from backend.app.config.settings import get_settings
from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter,
    SemanticInterpretationError,
)
from backend.app.llm.factory import build_llm_registry
from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    GroundingStatus,
    SemanticGroundingService,
)
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    MeasureSchema,
    QueryShape,
    RelationshipSchema,
    SemanticModelSchema,
    TableSchema,
)
from backend.tests.stress.natural_language_semantic_stress import (
    DimensionProfile,
    MeasureProfile,
    MemberProfile,
    StressModelProfile,
    StressCase,
    generate_cases,
)

PROFILES: tuple[StressModelProfile, ...] = (
    StressModelProfile(
        key="retail_real",
        label="Retail",
        measures=(
            MeasureProfile("Total Sales", "sales", format_string="$#,##0.00"),
            MeasureProfile("Total Quantity", "quantity"),
        ),
        dimensions=(
            DimensionProfile("City", "Geography", "city", "cities"),
            DimensionProfile("Product", "Product", "product", "products"),
        ),
        members=(
            MemberProfile("City", "Shanghai", "Shanghai"),
            MemberProfile("Product", "Mountain Bike", "Mountain Bike"),
        ),
        date_field="OrderDate",
        ambiguous_phrase="performance",
    ),
    StressModelProfile(
        key="education_real",
        label="Education",
        measures=(
            MeasureProfile("Pass Rate", "pass rate"),
            MeasureProfile("Enrollment Count", "enrollment"),
        ),
        dimensions=(
            DimensionProfile("Program", "Programs", "program", "programs"),
            DimensionProfile("Campus", "Campuses", "campus", "campuses"),
        ),
        members=(MemberProfile("Program", "Data Science", "Data Science"),),
        date_field="AcademicDate",
        ambiguous_phrase="attendance",
    ),
    StressModelProfile(
        key="operations_real",
        label="Operations",
        measures=(
            MeasureProfile("On Hand Units", "on-hand units"),
            MeasureProfile("Reserved Units", "reserved units"),
        ),
        dimensions=(
            DimensionProfile("Warehouse", "Warehouses", "warehouse", "warehouses"),
            DimensionProfile("Bin", "Bins", "bin", "bins"),
        ),
        members=(MemberProfile("Warehouse", "North Hub", "North Hub"),),
        date_field="CaptureDate",
        ambiguous_phrase="inventory",
    ),
)


def build_schema(profile: StressModelProfile) -> SemanticModelSchema:
    fact_columns = [
        ColumnSchema(name="DateKey", data_type="Int64", is_key=True),
        ColumnSchema(name="OrderDate", data_type="DateTime"),
    ]
    fact_measures = [
        MeasureSchema(
            name=measure.canonical,
            data_type="Decimal",
            format_string=measure.format_string,
        )
        for measure in profile.measures
    ]
    tables: list[TableSchema] = []
    relationships = [RelationshipSchema(
        from_table="Sales",
        from_column="OrderDate",
        to_table="Calendar",
        to_column="Date",
        from_cardinality="many",
        to_cardinality="one",
        is_active=True,
    )]
    tables.append(TableSchema(
        name="Calendar",
        columns=[
            ColumnSchema(name="Date", data_type="DateTime", is_key=True),
            ColumnSchema(
                name="MonthStart",
                data_type="DateTime",
                expression="DATE(YEAR([Date]),MONTH([Date]),1)",
            ),
        ],
    ))
    for dimension in profile.dimensions:
        fact_columns.append(
            ColumnSchema(name=f"{dimension.table}Key", data_type="Int64")
        )
        relationships.append(RelationshipSchema(
            from_table="Sales",
            from_column=f"{dimension.table}Key",
            to_table=dimension.table,
            to_column="Key",
            from_cardinality="many",
            to_cardinality="one",
            is_active=True,
        ))
        tables.append(TableSchema(
            name=dimension.table,
            columns=[
                ColumnSchema(name="Key", data_type="Int64", is_key=True),
                ColumnSchema(
                    name=dimension.canonical,
                    data_type="String",
                    description=dimension.description or dimension.natural,
                ),
            ],
        ))
    tables.insert(0, TableSchema(
        name="Sales", columns=fact_columns, measures=fact_measures
    ))
    return SemanticModelSchema(
        name=profile.label,
        key=profile.key,
        tables=tables,
        relationships=relationships,
        runtime_identity=profile.key,
    )


@dataclass
class Result:
    case_id: str
    kind: str
    outcome: str
    layer: str | None = None
    detail: str = ""


async def _member_lookup_for(profile, field, _limit):
    for member in profile.members:
        if member.field == field.canonical_name:
            return ColumnMembersResult(
                semantic_model_key=profile.key,
                table_name=field.table_name,
                field_name=field.canonical_name,
                values=[member.value],
                source_mode="real",
            )
    return ColumnMembersResult(
        semantic_model_key=profile.key,
        table_name=field.table_name,
        field_name=field.canonical_name,
        values=[],
        source_mode="real",
    )


def _committed_from(
    profile: StressModelProfile, case: StressCase
) -> StructuredWorkMemory | None:
    """A test-side previous turn for follow-up inheritance."""

    if case.relation == "fresh_question":
        return None
    measure = profile.measures[0].canonical
    dimension = profile.dimensions[0].canonical
    return StructuredWorkMemory(
        conversation_id="real-stress",
        request_id="previous",
        semantic_model_key=case.model_key,
        state_status=MemoryStatus.COMMITTED,
        measures=[measure],
        dimensions=[dimension],
        filters=[],
        time_range=None,
        sort=None,
        top_n=None,
        last_query_plan={
            "query_shape": "grouped",
            "measures": [measure],
            "dimensions": [dimension],
            "filters": [],
        },
        memory_version=1,
    )


async def run_profile(profile, provider, limit):
    schema = build_schema(profile)
    catalog = SemanticCatalogBuilder().build(schema)
    service = SemanticGroundingService(
        catalog,
        selector=BoundedLLMObjectSelector(provider),
        today=lambda: date(2026, 10, 23),
    )
    interpreter = LLMSemanticInterpreter(provider)
    cases = generate_cases(profile)[:limit]
    results = []
    for case in cases:
        committed = _committed_from(profile, case)
        try:
            frame = await interpreter.interpret(
                case.question,
                committed_context=(
                    committed.model_dump(mode="json") if committed else None
                ),
            )
        except SemanticInterpretationError as exc:
            results.append(Result(
                case.case_id, case.kind, "FAIL", "UNDERSTANDING", exc.code
            ))
            continue
        if not case.expects_clarification and case.expected_shape is not None and frame.query_shape is not None:
            expected_shape = QueryShape(case.expected_shape)
            if frame.query_shape is not expected_shape:
                results.append(Result(
                    case.case_id, case.kind, "FAIL", "UNDERSTANDING",
                    f"shape={frame.query_shape.value}",
                ))
                continue
        outcome = await service.ground_frame(
            case.question,
            frame,
            committed,
            lambda field, limit_value: _member_lookup_for(
                profile, field, limit_value
            ),
        )
        if outcome.status is not GroundingStatus.RESOLVED or outcome.delta is None:
            layer = "RESOLUTION"
            if (
                outcome.clarification_reason is not None
                and "member" in outcome.clarification_reason.value
            ):
                layer = "MEMBER"
            elif (
                outcome.clarification_reason is not None
                and "time" in outcome.clarification_reason.value
            ):
                layer = "TEMPORAL"
            if case.expects_clarification:
                results.append(Result(
                    case.case_id, case.kind, "CLARIFICATION", layer
                ))
            else:
                results.append(Result(
                    case.case_id, case.kind, "FAIL", layer,
                    outcome.clarification_reason.value
                    if outcome.clarification_reason else outcome.status.value,
                ))
            continue
        if case.expects_clarification:
            results.append(Result(
                case.case_id, case.kind, "FAIL",
                case.clarification_layer or "RESOLUTION",
                "expected clarification but grounding resolved",
            ))
            continue
        delta = outcome.delta
        expected_measures = set(
            case.expected_measures
            or ((case.expected_measure,) if case.expected_measure else ())
        )
        if expected_measures and not expected_measures.issubset(
            set(delta.measures or ())
        ):
            results.append(Result(
                case.case_id, case.kind, "FAIL", "RESOLUTION",
                f"measures={delta.measures}",
            ))
            continue
        if case.expected_dimension and case.expected_dimension not in (
            delta.dimensions or ()
        ):
            results.append(Result(
                case.case_id, case.kind, "FAIL", "RESOLUTION",
                f"dimensions={delta.dimensions}",
            ))
            continue
        if case.expected_member:
            values = {
                (item.field, str(item.value))
                for item in (delta.filters or [])
            }
            if (case.expected_member_field, case.expected_member) not in values:
                results.append(Result(
                    case.case_id, case.kind, "FAIL", "MEMBER",
                    "member not bound",
                ))
                continue
        results.append(Result(case.case_id, case.kind, "PASS"))
    return results


async def run(output: Path, limit: int):
    registry = build_llm_registry(get_settings())
    provider = registry.get("deepseek").provider
    all_results = []
    try:
        for profile in PROFILES:
            all_results.extend(await run_profile(profile, provider, limit))
    finally:
        await registry.aclose()
    summary = {
        "total": len(all_results),
        "passed": sum(item.outcome == "PASS" for item in all_results),
        "clarifications": sum(
            item.outcome == "CLARIFICATION" for item in all_results
        ),
        "failed": sum(item.outcome == "FAIL" for item in all_results),
        "clusters": {},
        "results": [
            {
                "case_id": item.case_id,
                "kind": item.kind,
                "outcome": item.outcome,
                "layer": item.layer,
                "detail": item.detail,
            }
            for item in all_results
        ],
    }
    for item in all_results:
        if item.outcome == "FAIL":
            key = f"{item.layer}:{item.kind}"
            summary["clusters"][key] = summary["clusters"].get(key, 0) + 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        key: summary[key]
        for key in ("total", "passed", "clarifications", "failed", "clusters")
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=16)
    args = parser.parse_args()
    asyncio.run(run(Path(args.output), args.limit))


if __name__ == "__main__":
    main()
