"""Repository-owned presentation contract for the executive sales template.

This module owns presentation decisions only. It never selects queries,
calculates metrics, aggregates facts, or changes canonical identities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutiveVisualSlot:
    business_role: str
    visual_type: str
    title: str
    section: str
    desktop_columns: int


@dataclass(frozen=True, slots=True)
class ExecutiveKpiSlot:
    field: str
    tone: str
    icon: str


@dataclass(frozen=True, slots=True)
class ExecutiveTemplatePresentationContract:
    template_key: str
    contract_key: str
    section_order: tuple[str, ...]
    desktop_grid_columns: int
    desktop_trend_label_limit: int
    tablet_trend_label_limit: int
    mobile_trend_label_limit: int
    donut_legend_limit: int
    visual_slots: tuple[ExecutiveVisualSlot, ...]
    kpi_slots: tuple[ExecutiveKpiSlot, ...]
    responsive_variants: tuple[str, ...]
    detail_variants: tuple[str, ...]
    theme_tokens: tuple[tuple[str, str], ...]

    def visual_for_role(self, role: str) -> ExecutiveVisualSlot:
        for slot in self.visual_slots:
            if slot.business_role == role:
                return slot
        raise KeyError(role)

    def kpi_for_field(self, field: str) -> ExecutiveKpiSlot:
        for slot in self.kpi_slots:
            if slot.field == field:
                return slot
        raise KeyError(field)

    def css_variables(self) -> str:
        return " ".join(f"--{name}: {value};" for name, value in self.theme_tokens)


EXECUTIVE_TEMPLATE_CONTRACT = ExecutiveTemplatePresentationContract(
    template_key="sales_executive_report",
    contract_key="executive-12-column",
    section_order=(
        "kpi_summary",
        "hero_sales_trend",
        "business_structure",
        "customer_analysis",
        "detail",
    ),
    desktop_grid_columns=12,
    desktop_trend_label_limit=18,
    tablet_trend_label_limit=8,
    mobile_trend_label_limit=4,
    donut_legend_limit=8,
    visual_slots=(
        ExecutiveVisualSlot(
            "time_trend", "line", "月度销售趋势", "hero_sales_trend", 12
        ),
        ExecutiveVisualSlot(
            "region_comparison", "column", "区域销售对比", "business_structure", 4
        ),
        ExecutiveVisualSlot(
            "category_contribution", "donut", "品类销售贡献", "business_structure", 4
        ),
        ExecutiveVisualSlot(
            "top_products", "hbar", "Top 产品", "business_structure", 4
        ),
        ExecutiveVisualSlot(
            "top_customers", "table", "Top 客户", "customer_analysis", 12
        ),
    ),
    kpi_slots=(
        ExecutiveKpiSlot("Total Sales", "blue", "sales"),
        ExecutiveKpiSlot("Total Quantity", "green", "quantity"),
        ExecutiveKpiSlot("Total Orders", "purple", "orders"),
        ExecutiveKpiSlot("Average Order Value", "orange", "average"),
    ),
    responsive_variants=("desktop", "tablet", "mobile"),
    detail_variants=("detail_available", "detail_unavailable"),
    theme_tokens=(
        ("navy-950", "#071a33"),
        ("navy-900", "#0b2b55"),
        ("navy-800", "#123f78"),
        ("blue-650", "#1769d2"),
        ("blue-500", "#2f86ed"),
        ("blue-300", "#83baf3"),
        ("blue-100", "#eaf3ff"),
        ("green", "#18a879"),
        ("purple", "#7867d9"),
        ("orange", "#ed9148"),
        ("ink", "#102845"),
        ("ink-soft", "#526b87"),
        ("ink-muted", "#7b8fa6"),
        ("surface", "#ffffff"),
        ("canvas", "#eef3f8"),
        ("line", "#dbe5ef"),
        ("grid-line", "#d9e4ef"),
    ),
)
