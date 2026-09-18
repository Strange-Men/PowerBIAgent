"""Small immutable contracts for requested-scope factual presentation."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ObservedCoverageStatus(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    EMPTY = "empty"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class DataHorizonStatus(str, Enum):
    KNOWN = "known"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class ObservedDataCoverage(BaseModel):
    """Time coverage proved by returned rows, never by requested scope."""

    status: ObservedCoverageStatus
    start_date: date | None = None
    end_date: date | None = None
    grain: Literal["month"] | None = None
    source_field: str | None = None
    source_rows: tuple[int, ...] = ()
    authority: Literal["query_result_verified_fact_set"] = (
        "query_result_verified_fact_set"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_state(self) -> "ObservedDataCoverage":
        bounded = self.status in {
            ObservedCoverageStatus.FULL,
            ObservedCoverageStatus.PARTIAL,
        }
        if bounded:
            if (
                self.start_date is None
                or self.end_date is None
                or self.end_date < self.start_date
                or self.grain != "month"
                or not self.source_field
                or not self.source_rows
            ):
                raise ValueError("observed_coverage_evidence_incomplete")
        elif any(
            value is not None
            for value in (
                self.start_date,
                self.end_date,
                self.grain,
                self.source_field,
            )
        ) or self.source_rows:
            raise ValueError("observed_coverage_non_bounded_has_evidence")
        return self


class AvailableDataHorizon(BaseModel):
    """Latest verified period containing a non-empty measure observation."""

    status: DataHorizonStatus
    latest_period: date | None = None
    grain: Literal["month"] | None = None
    semantic_model_key: str
    measure: str
    temporal_dimension: str
    source_result_id: str | None = None
    source_fact_set_id: str | None = None
    authority: Literal["deterministic_availability_probe_verified_fact_set"] = (
        "deterministic_availability_probe_verified_fact_set"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_evidence(self) -> "AvailableDataHorizon":
        if self.status is DataHorizonStatus.KNOWN:
            if (
                self.latest_period is None
                or self.grain != "month"
                or not self.source_result_id
                or not self.source_fact_set_id
            ):
                raise ValueError("available_data_horizon_evidence_incomplete")
        elif self.latest_period is not None or self.grain is not None:
            raise ValueError("unknown_data_horizon_has_period")
        return self


class DataAvailabilityContext(BaseModel):
    """Keep requested-query coverage separate from model/fact availability."""

    observed_data_coverage: ObservedDataCoverage
    available_data_horizon: AvailableDataHorizon | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")
