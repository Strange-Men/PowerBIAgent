"""Verified facts and fact-bounded response projection."""

from backend.app.facts.verified import (
    FactOutputValidator,
    FactType,
    FactVerificationError,
    FactBoundedAnswerBuilder,
    FactBoundedReportBuilder,
    VerifiedFact,
    VerifiedFactSet,
    VerifiedFactSetBuilder,
)
from backend.app.schemas.factual_context import (
    ObservedCoverageStatus,
    ObservedDataCoverage,
)

__all__ = [
    "FactOutputValidator",
    "FactType",
    "FactVerificationError",
    "FactBoundedAnswerBuilder",
    "FactBoundedReportBuilder",
    "VerifiedFact",
    "VerifiedFactSet",
    "VerifiedFactSetBuilder",
    "ObservedCoverageStatus",
    "ObservedDataCoverage",
]
