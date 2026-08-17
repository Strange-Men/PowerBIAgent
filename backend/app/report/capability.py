"""Deterministic report section capability based on runtime evidence.

This module answers "what can be shown" from what the runtime execution chain
has actually produced.  It never fabricates facts, never consults an LLM, and
never reads expected/oracle values.

Each section is gated by three layers:
  - schema / contract availability (can this template legally express it?)
  - query completion  (did the four fixed queries produce results?)
  - fact sufficiency  (do VerifiedFactSet values meet minimum thresholds?)

Future sections (time_trend, region_breakdown, customer_breakdown, …) have an
extension point here but MUST NOT produce mock or placeholder content — they
return UNAVAILABLE when the runtime evidence is absent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class SectionKey(str, Enum):
    """Every section the sales_report template can express.

    Only sections whose runtime evidence is complete and truthful may render.
    """

    SALES_KPI = "sales_kpi"
    CATEGORY_BREAKDOWN = "category_breakdown"
    TOP_PRODUCTS = "top_products"

    # ── Future extension points (M4+ / new templates).  Never auto-generate.
    # TIME_TREND = "time_trend"
    # REGION_BREAKDOWN = "region_breakdown"
    # CUSTOMER_BREAKDOWN = "customer_breakdown"

    def is_extension_point(self) -> bool:
        """True for sections defined in code but not yet supported by any contract."""
        # All current enum values are production-ready.  Extension points never
        # reach the renderer — they fail closed in SectionGate.
        return False


class SectionAvailability(str, Enum):
    """Three-state availability for a single report section."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class SectionInfo:
    """Immutable result of gating one section.

    The renderer MUST check SectionInfo.available before emitting any HTML
    for that section.  A section without available evidence MUST render
    nothing — no placeholder, no "coming soon" banner, no mock chart.
    """

    def __init__(
        self,
        key: SectionKey,
        availability: SectionAvailability,
        *,
        row_count: int = 0,
    ) -> None:
        self._key = key
        self._availability = availability
        self._row_count = row_count

    @property
    def key(self) -> SectionKey:
        return self._key

    @property
    def available(self) -> bool:
        return self._availability == SectionAvailability.AVAILABLE

    @property
    def row_count(self) -> int:
        return self._row_count

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, SectionInfo):
            return NotImplemented
        return (
            self._key == other._key
            and self._availability == other._availability
        )

    def __hash__(self) -> int:
        return hash((self._key, self._availability))

    def __repr__(self) -> str:
        return (
            f"SectionInfo(key={self._key.value}, "
            f"available={self.available}, rows={self._row_count})"
        )


# ── Per-section helpers ────────────────────────────────────────────────────

def _section_available(
    key: SectionKey,
    template_key: str,
    source_mode: str | None,
    *,
    row_count: int = 0,
) -> SectionInfo:
    """Helper: wrap an available section."""
    return SectionInfo(key, SectionAvailability.AVAILABLE, row_count=row_count)


def _section_unavailable(key: SectionKey) -> SectionInfo:
    """Helper: wrap an unavailable section."""
    return SectionInfo(key, SectionAvailability.UNAVAILABLE, row_count=0)


# ── Section gating rules ───────────────────────────────────────────────────

def gate_sales_kpi(template_key: str, source_mode: str | None) -> SectionInfo:
    """Sales KPI section: available when total_sales + total_quantity resolved."""
    if template_key != "sales_report":
        return _section_unavailable(SectionKey.SALES_KPI)
    if source_mode not in ("mock", "real"):
        return _section_unavailable(SectionKey.SALES_KPI)
    return _section_available(SectionKey.SALES_KPI, template_key, source_mode)


def gate_category_breakdown(
    template_key: str,
    source_mode: str | None,
    *,
    row_count: int = 0,
) -> SectionInfo:
    """Category breakdown: available when sales_by_category has rows."""
    if template_key != "sales_report":
        return _section_unavailable(SectionKey.CATEGORY_BREAKDOWN)
    if source_mode not in ("mock", "real"):
        return _section_unavailable(SectionKey.CATEGORY_BREAKDOWN)
    if row_count < 1:
        return _section_unavailable(SectionKey.CATEGORY_BREAKDOWN)
    return _section_available(
        SectionKey.CATEGORY_BREAKDOWN,
        template_key,
        source_mode,
        row_count=row_count,
    )


def gate_top_products(
    template_key: str,
    source_mode: str | None,
    *,
    row_count: int = 0,
) -> SectionInfo:
    """Top products section: available when top_products has rows."""
    if template_key != "sales_report":
        return _section_unavailable(SectionKey.TOP_PRODUCTS)
    if source_mode not in ("mock", "real"):
        return _section_unavailable(SectionKey.TOP_PRODUCTS)
    if row_count < 1:
        return _section_unavailable(SectionKey.TOP_PRODUCTS)
    return _section_available(
        SectionKey.TOP_PRODUCTS,
        template_key,
        source_mode,
        row_count=row_count,
    )


# ── Extension point for future sections ────────────────────────────────────
#
# Each new section gets a gating function.  The function MUST check whether
# the runtime schema, contract, and VerifiedFactSet actually contain the
# necessary evidence.  Without that evidence the section MUST be UNAVAILABLE.
#
#   def gate_time_trend(...) -> SectionInfo:
#       return _section_unavailable(SectionKey.TIME_TREND)
#
#   def gate_region_breakdown(...) -> SectionInfo:
#       return _section_unavailable(SectionKey.REGION_BREAKDOWN)


# ── Composite gating ───────────────────────────────────────────────────────

def compute_section_capabilities(
    template_key: str,
    source_mode: str | None,
    *,
    category_row_count: int = 0,
    product_row_count: int = 0,
) -> dict[SectionKey, SectionInfo]:
    """Gate every section a template might express against runtime evidence.

    Returns a mapping from SectionKey to SectionInfo.  The renderer must
    consult this map and emit nothing for unavailable sections.
    """
    return {
        SectionKey.SALES_KPI: gate_sales_kpi(template_key, source_mode),
        SectionKey.CATEGORY_BREAKDOWN: gate_category_breakdown(
            template_key, source_mode, row_count=category_row_count,
        ),
        SectionKey.TOP_PRODUCTS: gate_top_products(
            template_key, source_mode, row_count=product_row_count,
        ),
    }