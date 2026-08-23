"""Deterministic presentation projection; never parses answer text for facts."""

from __future__ import annotations

from backend.app.facts.verified import FactType, VerifiedFactSet
from backend.app.presentation.models import (
    ChartPresentationBlock,
    MetricPresentationBlock,
    PresentationDataset,
    PresentationEnvelope,
    ReportPresentationBlock,
    TablePresentationBlock,
    TextPresentationBlock,
    is_presentation_number,
    is_presentation_time,
)
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult


class StructuredPresentationBuilder:
    """Create UI blocks from one already verified QueryResult/FactSet pair."""

    _DATA_FACT_TYPES = frozenset({
        FactType.SCALAR_METRIC,
        FactType.GROUPED_METRIC,
        FactType.RANKING,
        FactType.MAXIMUM,
        FactType.MINIMUM,
    })

    @classmethod
    def build_answer(
        cls,
        plan: CanonicalQueryPlan,
        result: QueryResult,
        facts: VerifiedFactSet,
        answer_text: str,
    ) -> PresentationEnvelope:
        cls._validate_authority(result, facts)
        dataset = cls._project_verified_dataset(result, facts)
        blocks: list[object] = [TextPresentationBlock(content=answer_text)]

        for fact in facts.by_type(FactType.SCALAR_METRIC):
            if not fact.source_fields or not fact.source_rows:
                continue
            blocks.append(
                MetricPresentationBlock(
                    data_reference=result.result_id,
                    label=fact.measure or fact.source_fields[-1],
                    value_field=fact.source_fields[-1],
                    row_index=fact.source_rows[0],
                )
            )

        grouped = facts.by_type(FactType.GROUPED_METRIC)
        if grouped and dataset.rows:
            blocks.append(
                TablePresentationBlock(data_reference=result.result_id)
            )
            first = grouped[0]
            if len(first.source_fields) >= 2:
                x_field = first.source_fields[0]
                y_field = first.source_fields[-1]
                y_index = dataset.columns.index(y_field)
                if dataset.row_count >= 2 and all(
                    is_presentation_number(row[y_index]) for row in dataset.rows
                ):
                    blocks.append(
                        ChartPresentationBlock(
                            data_reference=result.result_id,
                            visual_type=(
                                "line"
                                if cls._is_time_series(plan, dataset, x_field)
                                else "bar"
                            ),
                            title=(
                                "趋势"
                                if cls._is_time_series(plan, dataset, x_field)
                                else "对比"
                            ),
                            x_field=x_field,
                            y_field=y_field,
                        )
                    )
        return PresentationEnvelope(
            datasets=[dataset],
            blocks=blocks,
        )

    @staticmethod
    def build_report(report_id: str) -> PresentationEnvelope:
        return PresentationEnvelope(
            blocks=[
                TextPresentationBlock(
                    content="报表已生成，可以查看或下载 HTML 文件。"
                ),
                ReportPresentationBlock(report_id=report_id),
            ]
        )

    @staticmethod
    def _validate_authority(
        result: QueryResult, facts: VerifiedFactSet
    ) -> None:
        coherent = (
            result.error is None
            and facts.result_id == result.result_id
            and facts.semantic_model_key == result.semantic_model_key
            and facts.source_mode == result.source_mode
            and facts.result_columns == result.columns
            and facts.row_count == result.row_count
            and facts.truncated == result.truncated
        )
        if not coherent:
            raise ValueError("presentation_authority_mismatch")

        if (
            len(set(result.columns)) != len(result.columns)
            or any(len(row) != len(result.columns) for row in result.rows)
        ):
            raise ValueError("presentation_authority_mismatch")

    @classmethod
    def _project_verified_dataset(
        cls,
        result: QueryResult,
        facts: VerifiedFactSet,
    ) -> PresentationDataset:
        verified_fields = {
            field
            for fact in facts.facts
            if fact.fact_type in cls._DATA_FACT_TYPES
            for field in fact.source_fields
        }
        columns = [
            column for column in result.columns if column in verified_fields
        ]
        indexes = [result.columns.index(column) for column in columns]
        return PresentationDataset(
            result_id=result.result_id,
            verified_fact_set_id=facts.fact_set_id,
            semantic_model_key=result.semantic_model_key,
            source_mode=result.source_mode,
            columns=columns,
            rows=[
                [row[index] for index in indexes]
                for row in result.rows
            ],
            row_count=result.row_count,
            truncated=result.truncated,
        )

    @staticmethod
    def _is_time_series(
        plan: CanonicalQueryPlan,
        dataset: PresentationDataset,
        x_field: str,
    ) -> bool:
        dimension_text = " ".join([*plan.dimensions, x_field]).casefold()
        if any(token in dimension_text for token in ("date", "month", "year", "日期", "月", "年")):
            return True
        x_index = dataset.columns.index(x_field)
        return bool(dataset.rows) and all(
            is_presentation_time(row[x_index]) for row in dataset.rows
        )
