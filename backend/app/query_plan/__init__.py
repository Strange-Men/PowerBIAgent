"""Runtime semantic binding and canonical deterministic query planning."""

from backend.app.query_plan.grounding import (
    CandidateSelection,
    SemanticEquivalenceVeto,
)

__all__ = ["CandidateSelection", "SemanticEquivalenceVeto"]
