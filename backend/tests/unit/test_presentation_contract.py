"""M5.3 structured response stays a deterministic QueryResult projection."""

import pytest

from backend.app.facts import VerifiedFactSetBuilder
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.formatter import PresentationFormatKind
from backend.app.presentation.localization import (
    DisplayLocalization,
    DisplayLocalizationSource,
)
from backend.app.presentation.models import PresentationEnvelope
from backend.app.query_plan.semantic_catalog import SemanticObjectType
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult


def _plan(*, dimensions: list[str] | None = None) -> CanonicalQueryPlan:
    return CanonicalQueryPlan(
        normalized_question="query",
        semantic_model_key="model",
        measures=["Total Sales"],
        dimensions=dimensions or [],
    )


def _result(columns: list[str], rows: list[list[object]]) -> QueryResult:
    return QueryResult(
        result_id="result-1",
        semantic_model_key="model",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        source_mode="real",
    )


def _binding(
    canonical_field: str,
    canonical_name: str,
    display_name: str,
    *,
    object_type: SemanticObjectType,
    kind: PresentationFormatKind,
) -> tuple[str, DisplayLocalization]:
    return canonical_field, DisplayLocalization(
        semantic_model_key="model",
        object_identity=f"{object_type.value}:Facts:{canonical_name}",
        object_type=object_type,
        canonical_name=canonical_name,
        locale="zh-CN",
        display_name=display_name,
        source=DisplayLocalizationSource.MODEL_GLOSSARY,
        schema_identity="b" * 64,
        data_type="decimal" if object_type == SemanticObjectType.MEASURE else "string",
        format_kind=kind,
    )


def test_scalar_uses_text_only_without_redundant_metric_card() -> None:
    plan = _plan()
    result = _result(["[Total Sales]"], [[123.5]])
    facts = VerifiedFactSetBuilder().build(plan, result)

    presentation = StructuredPresentationBuilder.build_answer(
        plan, result, facts, "总销售额为 123.5。"
    )

    assert presentation.datasets[0].rows == [[123.5]]
    assert presentation.datasets[0].verified_fact_set_id == facts.fact_set_id
    assert [block.type for block in presentation.blocks] == ["text"]


def test_grouped_result_produces_table_and_bar_without_copying_rows() -> None:
    plan = _plan(dimensions=["Category"])
    result = _result(
        ["Sales[Category]", "[Total Sales]"],
        [["A", 10], ["B", 20]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)

    presentation = StructuredPresentationBuilder.build_answer(
        plan, result, facts, "按类别对比如下。"
    )

    assert len(presentation.datasets) == 1
    assert [block.type for block in presentation.blocks] == ["text", "table", "chart"]
    chart = presentation.blocks[-1]
    assert chart.type == "chart"
    assert chart.visual_type == "bar"
    assert chart.data_reference == presentation.datasets[0].result_id


def test_unverified_query_result_column_is_not_exposed_in_presentation() -> None:
    plan = _plan(dimensions=["Category"])
    result = _result(
        ["Sales[Category]", "[Total Sales]", "Unexpected Secret"],
        [["A", 10, "hidden-a"], ["B", 20, "hidden-b"]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)

    presentation = StructuredPresentationBuilder.build_answer(
        plan, result, facts, "按类别对比如下。"
    )

    dataset = presentation.datasets[0]
    assert dataset.columns == ["Sales[Category]", "[Total Sales]"]
    assert dataset.rows == [["A", 10], ["B", 20]]
    assert "Unexpected Secret" not in presentation.model_dump_json()


def test_metric_table_and_chart_references_resolve_to_verified_dataset() -> None:
    scalar_plan = _plan()
    scalar_result = _result(["[Total Sales]"], [[123.5]])
    scalar_facts = VerifiedFactSetBuilder().build(scalar_plan, scalar_result)
    scalar = StructuredPresentationBuilder.build_answer(
        scalar_plan, scalar_result, scalar_facts, "总销售额为 123.5。"
    )
    scalar_dataset = scalar.datasets[0]
    assert [block.type for block in scalar.blocks] == ["text"]
    assert scalar_dataset.rows == [[123.5]]

    grouped_plan = _plan(dimensions=["Category"])
    grouped_result = _result(
        ["Sales[Category]", "[Total Sales]"],
        [["A", 10], ["B", 20]],
    )
    grouped_facts = VerifiedFactSetBuilder().build(grouped_plan, grouped_result)
    grouped = StructuredPresentationBuilder.build_answer(
        grouped_plan, grouped_result, grouped_facts, "按类别对比如下。"
    )
    grouped_dataset = grouped.datasets[0]
    table = next(block for block in grouped.blocks if block.type == "table")
    chart = next(block for block in grouped.blocks if block.type == "chart")
    assert table.data_reference == grouped_dataset.result_id
    assert chart.data_reference == grouped_dataset.result_id
    assert {chart.x_field, chart.y_field}.issubset(grouped_dataset.columns)


def test_date_dimension_selects_line_chart() -> None:
    plan = _plan(dimensions=["OrderDate"])
    result = _result(
        ["Sales[OrderDate]", "[Total Sales]"],
        [["2026-01", 10], ["2026-02", 20]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)

    presentation = StructuredPresentationBuilder.build_answer(
        plan, result, facts, "销售趋势如下。"
    )

    chart = next(block for block in presentation.blocks if block.type == "chart")
    assert chart.visual_type == "line"


def test_display_fields_and_formatted_rows_do_not_change_canonical_facts() -> None:
    plan = _plan(dimensions=["Year Month"])
    result = _result(
        ["Facts[Year Month]", "[Total Sales]"],
        [["2025-01-01T00:00:00", 6943997.509999986]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    display_bindings = dict([
        _binding(
            "Facts[Year Month]",
            "Year Month",
            "月份",
            object_type=SemanticObjectType.FIELD,
            kind=PresentationFormatKind.DATE,
        ),
        _binding(
            "[Total Sales]",
            "Total Sales",
            "销售额",
            object_type=SemanticObjectType.MEASURE,
            kind=PresentationFormatKind.AMOUNT,
        ),
    ])

    presentation = StructuredPresentationBuilder.build_answer(
        plan,
        result,
        facts,
        "该期间销售额明细如下。",
        display_bindings=display_bindings,
    )

    dataset = presentation.datasets[0]
    assert dataset.columns == result.columns
    assert dataset.rows == result.rows
    assert [field.display_name for field in dataset.display_fields] == ["月份", "销售额"]
    assert dataset.formatted_rows == [["2025年1月", "6,943,997.51"]]
    assert "2025-01-01T00:00:00" not in str(dataset.formatted_rows)


def test_mismatched_fact_authority_fails_closed() -> None:
    plan = _plan()
    result = _result(["[Total Sales]"], [[10]])
    facts = VerifiedFactSetBuilder().build(plan, result).model_copy(
        update={"result_id": "other-result"}
    )
    with pytest.raises(ValueError, match="presentation_authority_mismatch"):
        StructuredPresentationBuilder.build_answer(plan, result, facts, "answer")


def test_query_result_row_column_shape_mismatch_fails_closed() -> None:
    plan = _plan(dimensions=["Category"])
    valid_result = _result(
        ["Sales[Category]", "[Total Sales]"],
        [["A", 10]],
    )
    facts = VerifiedFactSetBuilder().build(plan, valid_result)
    malformed_result = QueryResult.model_construct(
        result_id=valid_result.result_id,
        semantic_model_key=valid_result.semantic_model_key,
        columns=list(valid_result.columns),
        rows=[["A"]],
        row_count=1,
        source_mode=valid_result.source_mode,
        error=None,
        truncated=False,
    )

    with pytest.raises(ValueError, match="presentation_authority_mismatch"):
        StructuredPresentationBuilder.build_answer(
            plan, malformed_result, facts, "answer"
        )


def test_report_attachment_has_no_factual_dataset() -> None:
    presentation = StructuredPresentationBuilder.build_report("report-1")
    assert presentation.datasets == []
    assert presentation.blocks[-1].type == "report_attachment"
    assert presentation.blocks[-1].report_id == "report-1"


def test_dangling_data_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="presentation_data_reference_missing"):
        PresentationEnvelope.model_validate(
            {
                "version": 1,
                "datasets": [],
                "blocks": [
                    {
                        "type": "table",
                        "data_reference": "missing",
                        "title": "结果",
                    }
                ],
            }
        )
