"""Application-owned report-template and renderer dispatch authority."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.app.report.base import ReportRenderer
from backend.app.schemas.data_contracts import ReportSpec
from backend.app.schemas.report_context import ReportTemplateTier


class ReportTemplateAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ReportTemplateDescriptor(BaseModel):
    template_key: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    renderer_key: str = Field(min_length=1)
    availability: ReportTemplateAvailability
    tier: ReportTemplateTier = ReportTemplateTier.SIMPLE
    aliases: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class ReportTemplateCatalogItem(BaseModel):
    template_key: str
    display_name: str
    description: str
    availability: ReportTemplateAvailability

    model_config = ConfigDict(frozen=True)


class ReportTemplateCatalogResponse(BaseModel):
    items: list[ReportTemplateCatalogItem]

    model_config = ConfigDict(frozen=True)


class ReportTemplateUnavailableError(ValueError):
    """The requested template or its renderer is not currently available."""


class ReportTemplateRegistry:
    def __init__(self, descriptors: tuple[ReportTemplateDescriptor, ...]) -> None:
        self._descriptors = descriptors
        self._by_key = {item.template_key: item for item in descriptors}
        if len(self._by_key) != len(descriptors):
            raise ValueError("report_template_registry_duplicate_key")

    @property
    def available_keys(self) -> tuple[str, ...]:
        return tuple(
            item.template_key
            for item in self._descriptors
            if item.availability == ReportTemplateAvailability.AVAILABLE
        )

    @property
    def descriptors(self) -> tuple[ReportTemplateDescriptor, ...]:
        return self._descriptors

    def get(self, template_key: str) -> ReportTemplateDescriptor | None:
        return self._by_key.get(template_key)

    def require_available(self, template_key: str) -> ReportTemplateDescriptor:
        descriptor = self._by_key.get(template_key)
        if (
            descriptor is None
            or descriptor.availability != ReportTemplateAvailability.AVAILABLE
        ):
            raise ReportTemplateUnavailableError(
                f"report_template_unavailable:{template_key}"
            )
        return descriptor

    def public_catalog(self) -> ReportTemplateCatalogResponse:
        return ReportTemplateCatalogResponse(
            items=[
                ReportTemplateCatalogItem(
                    template_key=item.template_key,
                    display_name=item.display_name,
                    description=item.description,
                    availability=item.availability,
                )
                for item in self._descriptors
                if item.availability == ReportTemplateAvailability.AVAILABLE
            ]
        )


class ReportRendererRegistry:
    def __init__(self, renderers: tuple[tuple[str, ReportRenderer], ...]) -> None:
        self._renderers = dict(renderers)
        if len(self._renderers) != len(renderers):
            raise ValueError("report_renderer_registry_duplicate_key")

    def require(self, renderer_key: str) -> ReportRenderer:
        renderer = self._renderers.get(renderer_key)
        if renderer is None:
            raise ReportTemplateUnavailableError(
                f"report_renderer_unavailable:{renderer_key}"
            )
        return renderer


class ReportRendererDispatcher(ReportRenderer):
    """Resolve template -> renderer with no default or fallback path."""

    def __init__(
        self,
        *,
        template_registry: ReportTemplateRegistry,
        renderer_registry: ReportRendererRegistry,
    ) -> None:
        self.template_registry = template_registry
        self.renderer_registry = renderer_registry

    @property
    def supported_templates(self) -> list[str]:
        return list(self.template_registry.available_keys)

    async def render(self, report: ReportSpec) -> str:
        descriptor = self.template_registry.require_available(report.template_key)
        if descriptor.tier is ReportTemplateTier.COMPLEX:
            self._validate_complex_contract(report)
        renderer = self.renderer_registry.require(descriptor.renderer_key)
        return await renderer.render(report)

    @staticmethod
    def _validate_complex_contract(report: ReportSpec) -> None:
        context = report.reading_context
        snapshot = report.data_snapshot
        if context is None:
            raise ReportTemplateUnavailableError(
                "complex_report_reading_context_required"
            )
        if snapshot is None:
            raise ReportTemplateUnavailableError(
                "complex_report_data_snapshot_required"
            )
        coherent = (
            report.title == context.report_title
            and report.generated_at == context.generated_at
            and report.semantic_model_key == context.semantic_model
            and report.semantic_model_key == snapshot.semantic_model_identity
            and report.schema_fingerprint == snapshot.schema_fingerprint
            and report.source_mode == snapshot.source_mode
            and context.data_source.source_mode == snapshot.source_mode
            and context.data_source.kind == snapshot.source_kind
        )
        if not coherent:
            raise ReportTemplateUnavailableError(
                "complex_report_reading_context_incoherent"
            )


DEFAULT_REPORT_TEMPLATE_REGISTRY = ReportTemplateRegistry(
    (
        ReportTemplateDescriptor(
            template_key="sales_report",
            display_name="简易模板",
            description="适合快速查看关键指标、趋势与分类明细",
            renderer_key="simple_report",
            availability=ReportTemplateAvailability.AVAILABLE,
            tier=ReportTemplateTier.SIMPLE,
            aliases=("销售报表", "销售报告"),
        ),
        ReportTemplateDescriptor(
            template_key="sales_executive_report",
            display_name="专业销售经营分析模板",
            description="复杂报表合同已建立；专业 Renderer 尚未开放",
            renderer_key="executive_sales_report",
            availability=ReportTemplateAvailability.UNAVAILABLE,
            tier=ReportTemplateTier.COMPLEX,
            aliases=("专业销售报表", "销售经营分析报表"),
        ),
    )
)


def build_report_dispatcher(renderer: ReportRenderer) -> ReportRendererDispatcher:
    return ReportRendererDispatcher(
        template_registry=DEFAULT_REPORT_TEMPLATE_REGISTRY,
        renderer_registry=ReportRendererRegistry((("simple_report", renderer),)),
    )
