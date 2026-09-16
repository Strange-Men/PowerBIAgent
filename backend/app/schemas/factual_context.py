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
