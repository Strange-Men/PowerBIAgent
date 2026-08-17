"""Deterministic Visualization / Layout / Theme policies for sales_report.

The "template" is a fixed design system, not fixed output content (ADR-011):
these policies decide *how* a resolved section is presented, never *what*
business facts it shows.  Visual choice is ordinary code — the LLM never picks
charts.  All geometry is derived from verified values only; nothing here
creates or re-aggregates business numbers.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.report.capability import SectionKey


class VisualType(str, Enum):
    """Fixed visual vocabulary of the design system."""

    KPI_CARD = "kpi_card"
    LINE = "line"
    DONUT = "donut"
    COLUMN = "column"
    HBAR = "hbar"


class SectionVisualSpec(BaseModel):
    """Presentation decision for one resolved section."""

    section_key: SectionKey
    visual_type: VisualType
    title: str
    layout_hint: Literal["full", "half"]

    model_config = ConfigDict(frozen=True)


class VisualizationPolicy:
    """Choose the visual by business role + verified data shape/cardinality.

    Rules (registry-owned, fixed):
      - scalar KPI                 → KPI card
      - time series                → line
      - category composition (few) → donut; many categories → horizontal bar
      - region comparison          → vertical column
      - Top N / ranking            → horizontal bar
    Never: every grouped result forced to horizontal bar; duplicate visuals
    of the same business fact.
    """

    MAX_DONUT_SLICES = 8

    TITLES = {
        SectionKey.SALES_KPI: "总销售额",
        SectionKey.QUANTITY_KPI: "总销量",
        SectionKey.ORDERS_KPI: "总订单数",
        SectionKey.AOV_KPI: "平均订单金额",
        SectionKey.TIME_TREND: "月度销售趋势",
        SectionKey.CATEGORY_CONTRIBUTION: "品类销售贡献",
        SectionKey.REGION_COMPARISON: "区域销售对比",
        SectionKey.TOP_PRODUCTS: "Top 5 产品销售额",
        SectionKey.TOP_CUSTOMERS: "Top 5 客户销售额",
    }

    def choose(
        self, section_key: SectionKey, *, row_count: int = 0
    ) -> SectionVisualSpec:
        title = self.TITLES[section_key]
        if section_key in {
            SectionKey.SALES_KPI,
            SectionKey.QUANTITY_KPI,
            SectionKey.ORDERS_KPI,
            SectionKey.AOV_KPI,
        }:
            return SectionVisualSpec(
                section_key=section_key,
                visual_type=VisualType.KPI_CARD,
                title=title,
                layout_hint="half",
            )
        if section_key == SectionKey.TIME_TREND:
            return SectionVisualSpec(
                section_key=section_key,
                visual_type=VisualType.LINE,
                title=title,
                layout_hint="full",
            )
        if section_key == SectionKey.CATEGORY_CONTRIBUTION:
            return SectionVisualSpec(
                section_key=section_key,
                visual_type=(
                    VisualType.DONUT
                    if 2 <= row_count <= self.MAX_DONUT_SLICES
                    else VisualType.HBAR
                ),
                title=title,
                layout_hint="half",
            )
        if section_key == SectionKey.REGION_COMPARISON:
            return SectionVisualSpec(
                section_key=section_key,
                visual_type=VisualType.COLUMN,
                title=title,
                layout_hint="half",
            )
        return SectionVisualSpec(
            section_key=section_key,
            visual_type=VisualType.HBAR,
            title=title,
            layout_hint="half",
        )


class LayoutPolicy:
    """Fixed section placement for the sales_report design system.

    Resolved sections fill fixed slots; missing sections emit nothing.
    """

    # KPI row → full-width trend → two half-width pairs.
    KPI_ROW: tuple[SectionKey, ...] = (
        SectionKey.SALES_KPI,
        SectionKey.QUANTITY_KPI,
        SectionKey.ORDERS_KPI,
        SectionKey.AOV_KPI,
    )
    FULL_SLOTS: tuple[SectionKey, ...] = (SectionKey.TIME_TREND,)
    HALF_PAIRS: tuple[tuple[SectionKey, SectionKey], ...] = (
        (SectionKey.CATEGORY_CONTRIBUTION, SectionKey.REGION_COMPARISON),
        (SectionKey.TOP_PRODUCTS, SectionKey.TOP_CUSTOMERS),
    )

    @staticmethod
    def order_sections(sections: tuple[SectionKey, ...]) -> tuple[SectionKey, ...]:
        """Deterministic visual order: KPI row first, then analysis slots."""
        ordered: list[SectionKey] = []
        groups = (
            *LayoutPolicy.KPI_ROW,
            *LayoutPolicy.FULL_SLOTS,
            *(item for pair in LayoutPolicy.HALF_PAIRS for item in pair),
        )
        for key in groups:
            if key in sections and key not in ordered:
                ordered.append(key)
        return tuple(ordered)


class ThemePolicy:
    """Fixed design tokens for the self-contained static report.

    Palette slots come from the dataviz-validated reference palette (light
    mode): fixed categorical hue order (never cycled), blue sequential hue
    for magnitude, neutral ink/surface.  No JS, no CDN, no external assets.
    """

    # Surfaces & ink
    SURFACE = "#fcfcfb"
    PAGE_BACKGROUND = "#f2f1ee"
    INK_PRIMARY = "#0b0b0b"
    INK_SECONDARY = "#52514e"
    INK_MUTED = "#8a8985"
    CARD_BACKGROUND = "#ffffff"
    BORDER = "#e4e2dc"
    TRACK = "#ecebe7"

    # Sequential (magnitude) — blue light→dark
    SEQUENTIAL_700 = "#0d366b"
    SEQUENTIAL_550 = "#1c5cab"
    SEQUENTIAL_400 = "#3987e5"
    SEQUENTIAL_250 = "#86b6ef"
    SEQUENTIAL_100 = "#cde2fb"

    # Categorical (identity) — fixed order, never cycled within one report
    CATEGORICAL = (
        "#2a78d6",  # blue
        "#eb6834",  # orange
        "#1baf7a",  # aqua
        "#eda100",  # yellow
        "#e87ba4",  # magenta
        "#008300",  # green
        "#4a3aa7",  # violet
        "#e34948",  # red
    )

    FONT_STACK = (
        '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", '
        '"Segoe UI", system-ui, sans-serif'
    )
