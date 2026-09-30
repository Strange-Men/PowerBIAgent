"""Read-only schema-aware projection for registered report templates."""

from __future__ import annotations

from backend.app.application.semantic_model_profile import build_semantic_model_profile
from backend.app.config.settings import Settings
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext, ToolGateway
from backend.app.harness.tool_registry import SchemaInput, TOOL_NAME_SCHEMA, register_schema_tool
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.report.capability import SectionKey, compute_section_capabilities
from backend.app.report.contracts import ReportContractValidator
from backend.app.report.registry import (
    DEFAULT_REPORT_TEMPLATE_REGISTRY,
    ReportTemplateAvailability,
    ReportTemplateCatalogItem,
    ReportTemplateCatalogResponse,
    ReportTemplateCompatibilityStatus,
    ReportTemplateDescriptor,
    ReportTemplateRegistry,
)
from backend.app.schemas.data_contracts import SemanticModelSchema, UserContext


class ReportTemplateCompatibilityService:
    """Fetch one runtime schema and reuse the canonical report capability engine."""

    def __init__(
        self,
        adapter: PowerBIAdapter,
        settings: Settings,
        *,
        registry: ReportTemplateRegistry = DEFAULT_REPORT_TEMPLATE_REGISTRY,
    ) -> None:
        self._runtime_mode = (
            RuntimeDataMode.MOCK if adapter.is_mock else RuntimeDataMode.REAL
        )
        self._registry = registry
        self._validator = ReportContractValidator(
            binding_scope_key=settings.powerbi_local_semantic_model_key
        )
        self._gateway = ToolGateway()
        register_schema_tool(
            self._gateway,
            adapter,
            HarnessConfig.from_settings(settings),
        )

    async def discover(self, semantic_model_key: str) -> ReportTemplateCatalogResponse:
        context = ToolExecutionContext(
            runtime_mode=self._runtime_mode,
            intent=IntentType.REPORT_GENERATION,
            user=UserContext(
                allowed_semantic_models=[semantic_model_key],
                allowed_tools=[TOOL_NAME_SCHEMA],
            ),
        )
        try:
            schema = await self._gateway.execute(
                TOOL_NAME_SCHEMA,
                context,
                SchemaInput(semantic_model_key=semantic_model_key),
            )
            profile = build_semantic_model_profile(schema)
            if profile.semantic_model_key != semantic_model_key:
                raise ValueError("semantic_model_profile_identity_mismatch")
        except (
            ToolTimeoutError,
            ToolExecutionError,
            ToolOutputValidationError,
            ToolPolicyDeniedError,
            ValueError,
        ):
            return ReportTemplateCatalogResponse(
                items=[], reason_code="semantic_model_schema_unavailable",
            )

        candidates = tuple(
            item for item in self._registry.descriptors
            if item.domains.intersection(profile.domains)
        )
        return ReportTemplateCatalogResponse(
            items=[self._project(item, schema) for item in candidates],
            reason_code=None if candidates else "no_eligible_report_template",
        )

    def _project(
        self,
        descriptor: ReportTemplateDescriptor,
        schema: SemanticModelSchema,
    ) -> ReportTemplateCatalogItem:
        if descriptor.availability != ReportTemplateAvailability.AVAILABLE:
            return self._unavailable(
                descriptor, reason_code="report_template_unavailable"
            )
        validation = self._validator.validate(descriptor.template_key, schema)
        if not validation.available or validation.contract is None:
            status = (
                ReportTemplateCompatibilityStatus.INCOMPATIBLE
                if validation.status.value == "semantic_model_mismatch"
                else ReportTemplateCompatibilityStatus.UNAVAILABLE
            )
            return ReportTemplateCatalogItem(
                template_key=descriptor.template_key,
                display_name=descriptor.display_name,
                description=descriptor.description,
                availability=descriptor.availability,
                compatibility_status=status,
                selectable=False,
                available_section_count=0,
                total_section_count=len(SectionKey),
                reason_code=(
                    validation.errors[0]
                    if validation.errors
                    else validation.status.value
                ),
            )
        capabilities = compute_section_capabilities(
            descriptor.template_key,
            validation.contract,
            schema,
        )
        available_count = sum(info.available for info in capabilities.values())
        total_count = len(capabilities)
        if available_count == total_count:
            status = ReportTemplateCompatibilityStatus.COMPATIBLE
        elif available_count > 0:
            status = ReportTemplateCompatibilityStatus.PARTIAL
        else:
            status = ReportTemplateCompatibilityStatus.INCOMPATIBLE
        return ReportTemplateCatalogItem(
            template_key=descriptor.template_key,
            display_name=descriptor.display_name,
            description=descriptor.description,
            availability=descriptor.availability,
            compatibility_status=status,
            selectable=available_count > 0,
            available_section_count=available_count,
            total_section_count=total_count,
            reason_code=(
                None if available_count > 0 else "report_no_resolved_sections"
            ),
        )

    @staticmethod
    def _unavailable(
        descriptor: ReportTemplateDescriptor,
        *,
        reason_code: str,
    ) -> ReportTemplateCatalogItem:
        return ReportTemplateCatalogItem(
            template_key=descriptor.template_key,
            display_name=descriptor.display_name,
            description=descriptor.description,
            availability=descriptor.availability,
            compatibility_status=ReportTemplateCompatibilityStatus.UNAVAILABLE,
            selectable=False,
            available_section_count=0,
            total_section_count=len(SectionKey),
            reason_code=reason_code,
        )
