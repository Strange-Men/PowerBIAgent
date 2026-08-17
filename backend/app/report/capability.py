"""M3.4 deterministic schema-aware report section capability engine.

The registry below is the *only* source of reportable sales sections.  A
section resolves only when ALL of these hold:

  - the template contract declares the section (allowed capability catalog);
  - the runtime schema provides every required object with the required type
    (registered semantic requirements);
  - the sealed execution chain produced verified, non-empty fact evidence
    for the section's query requirements (validated query/fact evidence).

This module never consults an LLM, never reads expected/oracle values, never
constructs QueryResults, and never invents sections for schema extra fields.
An unresolvable section is simply UNAVAILABLE — no placeholder, no mock chart.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from backend.app.report.contracts import (
    ReportContractValidator,
    TemplateContract,
)
from backend.app.schemas.data_contracts import SemanticModelSchema


class SectionKey(str, Enum):
    """Every reportable section the sales_report design system can express."""

    SALES_KPI = "sales_kpi"
    QUANTITY_KPI = "quantity_kpi"
    ORDERS_KPI = "orders_kpi"
    AOV_KPI = "aov_kpi"
    TIME_TREND = "time_trend"
    CATEGORY_CONTRIBUTION = "category_contribution"
    REGION_COMPARISON = "region_comparison"
    TOP_PRODUCTS = "top_products"
    TOP_CUSTOMERS = "top_customers"


# ── Registry: section → deterministic query requirements ──────────────────
# One section may need several sub-queries (e.g. a KPI anchor plus its
# breakdown); one sub-query is executed at most once per report.

SECTION_REQUIREMENTS: Mapping[SectionKey, tuple[str, ...]] = {
    SectionKey.SALES_KPI: ("total_sales",),
    SectionKey.QUANTITY_KPI: ("total_quantity",),
    SectionKey.ORDERS_KPI: ("total_orders",),
    SectionKey.AOV_KPI: ("average_order_value",),
    SectionKey.TIME_TREND: ("monthly_sales",),
    SectionKey.CATEGORY_CONTRIBUTION: ("sales_by_category",),
    SectionKey.REGION_COMPARISON: ("sales_by_region",),
    SectionKey.TOP_PRODUCTS: ("top_products",),
    SectionKey.TOP_CUSTOMERS: ("top_customers",),
}

# Registry-owned presentation roles consumed by the deterministic
# VisualizationPolicy / LayoutPolicy.  Unknown roles never render.
KPI_SECTION_ORDER: tuple[SectionKey, ...] = (
    SectionKey.SALES_KPI,
    SectionKey.QUANTITY_KPI,
    SectionKey.ORDERS_KPI,
    SectionKey.AOV_KPI,
)
ANALYSIS_SECTION_ORDER: tuple[SectionKey, ...] = (
    SectionKey.TIME_TREND,
    SectionKey.CATEGORY_CONTRIBUTION,
    SectionKey.REGION_COMPARISON,
    SectionKey.TOP_PRODUCTS,
    SectionKey.TOP_CUSTOMERS,
)

ALLOWED_SECTION_IDS = frozenset(item.value for item in SectionKey)


def parse_section_ids(ids: Any) -> tuple[str, ...]:
    """Filter arbitrary input down to registry-owned section IDs.

    Used for the LLM report-intent weak-signal draft: unknown or malformed
    IDs are discarded (fail closed), never interpreted, never expanded.
    """
    if not isinstance(ids, (list, tuple)):
        return ()
    seen: list[str] = []
    for item in ids:
        if isinstance(item, str) and item in ALLOWED_SECTION_IDS:
            if item not in seen:
                seen.append(item)
    return tuple(seen)


class SectionAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class SectionInfo(BaseModel):
    """Immutable gating result for one section.

    The planner and renderer MUST treat unavailable sections as absent:
    no placeholder, no "coming soon", no mock chart.
    """

    key: SectionKey
    availability: SectionAvailability
    row_count: int = Field(default=0, ge=0)
    reason: str = ""

    model_config = ConfigDict(frozen=True)

    @property
    def available(self) -> bool:
        return self.availability == SectionAvailability.AVAILABLE


def _unavailable(key: SectionKey, reason: str = "") -> SectionInfo:
    return SectionInfo(
        key=key, availability=SectionAvailability.UNAVAILABLE, reason=reason
    )


def _available(key: SectionKey, row_count: int = 0) -> SectionInfo:
    return SectionInfo(
        key=key,
        availability=SectionAvailability.AVAILABLE,
        row_count=row_count,
    )


def gate_section(
    template_key: str,
    section_key: SectionKey,
    contract: TemplateContract | None,
    schema: SemanticModelSchema,
    *,
    fact_row_counts: Mapping[str, int] | None = None,
    validator: ReportContractValidator | None = None,
) -> SectionInfo:
    """Gate one section against schema (and optional fact) evidence."""
    if contract is None:
        return _unavailable(section_key, "report_contract_missing")
    if template_key != contract.template_key:
        return _unavailable(section_key, "report_template_mismatch")
    requirement_keys = SECTION_REQUIREMENTS.get(section_key)
    if requirement_keys is None:
        return _unavailable(section_key, "report_section_not_registered")
    resolver = validator or ReportContractValidator()
    for requirement_key in requirement_keys:
        if not resolver.requirement_available(contract, requirement_key, schema):
            return _unavailable(
                section_key, f"report_requirement_unavailable:{requirement_key}"
            )
    if fact_row_counts is not None:
        for requirement_key in requirement_keys:
            if fact_row_counts.get(requirement_key, 0) < 1:
                return _unavailable(
                    section_key,
                    f"report_requirement_empty:{requirement_key}",
                )
        return _available(section_key, row_count=sum(
            fact_row_counts.get(key, 0) for key in requirement_keys
        ))
    return _available(section_key)


def compute_section_capabilities(
    template_key: str,
    contract: TemplateContract | None,
    schema: SemanticModelSchema,
) -> dict[SectionKey, SectionInfo]:
    """Schema-level capabilities: what this runtime model can truthfully show."""
    return {
        key: gate_section(template_key, key, contract, schema)
        for key in SectionKey
    }


def apply_fact_evidence(
    schema_capabilities: Mapping[SectionKey, SectionInfo],
    *,
    template_key: str,
    contract: TemplateContract | None,
    schema: SemanticModelSchema,
    fact_row_counts: Mapping[str, int],
) -> dict[SectionKey, SectionInfo]:
    """Final section set = schema capability ∩ non-empty verified evidence."""
    resolver = ReportContractValidator()
    resolved: dict[SectionKey, SectionInfo] = {}
    for key, info in schema_capabilities.items():
        if not info.available:
            resolved[key] = info
            continue
        gated = gate_section(
            template_key,
            key,
            contract,
            schema,
            fact_row_counts=fact_row_counts,
            validator=resolver,
        )
        resolved[key] = gated
    return resolved


def resolve_requested_sections(
    requested_ids: tuple[str, ...],
    capabilities: Mapping[SectionKey, SectionInfo],
) -> tuple[tuple[SectionKey, ...], tuple[SectionKey, ...]]:
    """Split requested IDs into resolved (renderable) and unavailable.

    Requested but unavailable sections are dropped — never mocked, never
    replaced by placeholders.  Unknown IDs were already filtered by
    parse_section_ids().
    """
    resolved: list[SectionKey] = []
    unavailable: list[SectionKey] = []
    for raw in requested_ids:
        key = SectionKey(raw)
        if capabilities.get(key, _unavailable(key)).available:
            if key not in resolved:
                resolved.append(key)
        else:
            if key not in unavailable:
                unavailable.append(key)
    return tuple(resolved), tuple(unavailable)
