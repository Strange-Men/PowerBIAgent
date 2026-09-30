"""Deterministic business scope projection; grants no query/section capability."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.report.contracts import SALES_QUERY_REQUIREMENTS
from backend.app.schemas.data_contracts import SemanticModelSchema


class SemanticModelProfile(BaseModel):
    semantic_model_key: str
    domains: frozenset[str]

    model_config = ConfigDict(frozen=True)


# Reuse the Sales contract's canonical object identities. Quantity alone is
# generic and cannot establish Sales scope. Types remain the capability gate's
# responsibility: a recognized but mistyped Sales measure is still Sales.
_SALES_IDENTITIES = frozenset(
    f"{obj.object_type.value}:{obj.table_name}:{obj.canonical_name}"
    for requirement in SALES_QUERY_REQUIREMENTS
    if requirement.key in {"total_sales", "total_orders", "average_order_value"}
    for obj in requirement.required_objects
)


def build_semantic_model_profile(schema: SemanticModelSchema) -> SemanticModelProfile:
    # Existing context builder validates identity, duplicates and visibility.
    # Model keys/names, descriptions, prompts and LLM drafts are never rules.
    context = ModelSemanticContextBuilder().build(schema)
    domains: set[str] = set()
    if _SALES_IDENTITIES.intersection(item.object_id for item in context.measures):
        domains.add("sales")
    # Small exact canonical combination for logistics scope, independent of
    # template availability. No fuzzy field matching or numeric KPI discovery.
    measures = {item.canonical_name for item in context.measures}
    fields = {item.canonical_name for item in context.columns}
    if "Total Shipments" in measures and {"Carrier", "Route"}.issubset(fields):
        domains.add("logistics")
    return SemanticModelProfile(
        semantic_model_key=context.semantic_model_key,
        domains=frozenset(domains),
    )
