"""Typed, non-authoritative UI projection of verified query artifacts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PresentationField(BaseModel):
    """Display-only metadata bound one-to-one to a canonical result column."""

    canonical_field: str = Field(min_length=1)
    object_identity: str = Field(min_length=1)
    object_type: Literal["measure", "field"]
    canonical_name: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    source: Literal[
        "powerbi_metadata",
        "model_glossary",
        "registry",
        "bounded_translation",
        "fallback",
    ]
    schema_identity: str = Field(min_length=64, max_length=64)
    format_kind: Literal[
        "auto", "integer", "decimal", "percentage", "amount", "date", "month", "text"
    ] = "text"

    model_config = ConfigDict(extra="forbid", frozen=True)


class PresentationDataset(BaseModel):
    """The single fact data copy exposed to the frontend for one QueryResult."""

    result_id: str
    verified_fact_set_id: str
    semantic_model_key: str
    source_mode: Literal["mock", "real"]
    columns: list[str]
    rows: list[list[Any]]
    display_fields: list[PresentationField] = Field(default_factory=list)
    formatted_rows: list[list[str]] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    truncated: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_shape(self) -> "PresentationDataset":
        if self.row_count != len(self.rows):
            raise ValueError("presentation_dataset_row_count_mismatch")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("presentation_dataset_columns_not_unique")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("presentation_dataset_row_shape_mismatch")
        if self.display_fields and (
            len(self.display_fields) != len(self.columns)
            or [field.canonical_field for field in self.display_fields] != self.columns
        ):
            raise ValueError("presentation_dataset_display_field_shape_mismatch")
        if self.display_fields:
            if (
                len(self.formatted_rows) != self.row_count
                or any(len(row) != len(self.columns) for row in self.formatted_rows)
            ):
                raise ValueError("presentation_dataset_formatted_row_shape_mismatch")
        elif self.formatted_rows:
            raise ValueError("presentation_dataset_display_projection_incomplete")
        return self


class TextPresentationBlock(BaseModel):
    type: Literal["text"] = "text"
    content: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricPresentationBlock(BaseModel):
    type: Literal["metric"] = "metric"
    data_reference: str
    label: str = Field(min_length=1)
    value_field: str = Field(min_length=1)
    row_index: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class TablePresentationBlock(BaseModel):
    type: Literal["table"] = "table"
    data_reference: str
    title: str = "查询结果"

    model_config = ConfigDict(extra="forbid", frozen=True)


class ChartPresentationBlock(BaseModel):
    type: Literal["chart"] = "chart"
    data_reference: str
    visual_type: Literal["bar", "line"]
    title: str = "查询结果"
    x_field: str
    y_field: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportPresentationBlock(BaseModel):
    type: Literal["report_attachment"] = "report_attachment"
    report_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


PresentationBlock = Annotated[
    TextPresentationBlock
    | MetricPresentationBlock
    | TablePresentationBlock
    | ChartPresentationBlock
    | ReportPresentationBlock,
    Field(discriminator="type"),
]


class PresentationEnvelope(BaseModel):
    """Dynamic blocks whose data references resolve inside ``datasets`` only."""

    version: Literal[1] = 1
    datasets: list[PresentationDataset] = Field(default_factory=list)
    blocks: list[PresentationBlock] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_references(self) -> "PresentationEnvelope":
        datasets = {item.result_id: item for item in self.datasets}
        if len(datasets) != len(self.datasets):
            raise ValueError("presentation_dataset_reference_collision")
        for block in self.blocks:
            if isinstance(block, (TextPresentationBlock, ReportPresentationBlock)):
                continue
            dataset = datasets.get(block.data_reference)
            if dataset is None:
                raise ValueError("presentation_data_reference_missing")
            if isinstance(block, MetricPresentationBlock):
                if block.value_field not in dataset.columns:
                    raise ValueError("presentation_metric_field_missing")
                if block.row_index >= dataset.row_count:
                    raise ValueError("presentation_metric_row_missing")
            if isinstance(block, ChartPresentationBlock):
                if (
                    block.x_field not in dataset.columns
                    or block.y_field not in dataset.columns
                ):
                    raise ValueError("presentation_chart_field_missing")
        return self


def is_presentation_number(value: object) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def is_presentation_time(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    return len(normalized) >= 7 and normalized[:4].isdigit() and normalized[4] in "-/"
