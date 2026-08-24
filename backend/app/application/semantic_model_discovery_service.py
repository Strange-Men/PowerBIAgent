"""M5.2 read-only semantic-model discovery application service."""

from pydantic import BaseModel, ConfigDict

from backend.app.config.settings import PowerBIMode, Settings
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.tool_registry import (
    SchemaInput,
    TOOL_NAME_SCHEMA,
    register_schema_tool,
)
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
    ToolSpec,
)
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.models import (
    PowerBICompatibilityProbe,
    SemanticModelCatalog,
    SemanticModelOption,
)
from backend.app.query_plan.semantic_catalog import (
    GlossaryCatalogError,
    SemanticCatalogBuilder,
)
from backend.app.schemas.data_contracts import UserContext


TOOL_NAME_DISCOVER_SEMANTIC_MODELS = "discover_semantic_models"
TOOL_NAME_PROBE_SEMANTIC_MODEL = "probe_semantic_model_compatibility"
TOOL_NAME_CHECK_SEMANTIC_MODEL = TOOL_NAME_SCHEMA


class SemanticModelDiscoveryInput(BaseModel):
    """Discovery has no caller-controlled connection parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticModelProbeInput(BaseModel):
    """One safe catalog key; provider connection details remain internal."""

    semantic_model_key: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticModelDiscoveryService:
    """Expose Adapter discovery only through the read-only ToolGateway."""

    def __init__(self, adapter: PowerBIAdapter, settings: Settings) -> None:
        self._runtime_mode = (
            RuntimeDataMode.MOCK if adapter.is_mock else RuntimeDataMode.REAL
        )
        self._glossary_scope_key = (
            settings.powerbi_local_semantic_model_key
            if settings.powerbi_mode == PowerBIMode.LOCAL_MCP
            else None
        )
        self._gateway = ToolGateway()
        config = HarnessConfig.from_settings(settings)

        async def _discover(_: SemanticModelDiscoveryInput) -> SemanticModelCatalog:
            return await adapter.discover_semantic_models()

        async def _probe(
            request: SemanticModelProbeInput,
        ) -> PowerBICompatibilityProbe:
            return await adapter.probe_compatibility(request.semantic_model_key)

        register_schema_tool(self._gateway, adapter, config)
        self._gateway.register(
            ToolSpec(
                name=TOOL_NAME_DISCOVER_SEMANTIC_MODELS,
                description="发现当前后端可连接的 Power BI 语义模型",
                input_model=SemanticModelDiscoveryInput,
                output_model=SemanticModelCatalog,
                timeout_seconds=float(config.request_timeout_seconds),
                max_retries=0,
                read_only=True,
                allowed_intents=[IntentType.DATA_QUESTION],
                supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
                handler=_discover,
            )
        )
        self._gateway.register(
            ToolSpec(
                name=TOOL_NAME_PROBE_SEMANTIC_MODEL,
                description="只读验证一个已发现模型的 MCP 兼容能力",
                input_model=SemanticModelProbeInput,
                output_model=PowerBICompatibilityProbe,
                timeout_seconds=float(config.request_timeout_seconds),
                max_retries=0,
                read_only=True,
                allowed_intents=[IntentType.DATA_QUESTION],
                supported_modes=[RuntimeDataMode.REAL],
                handler=_probe,
            )
        )

    async def discover(self) -> SemanticModelCatalog:
        context = ToolExecutionContext(
            runtime_mode=self._runtime_mode,
            intent=IntentType.DATA_QUESTION,
            user=UserContext(
                allowed_tools=[
                    TOOL_NAME_DISCOVER_SEMANTIC_MODELS,
                    TOOL_NAME_CHECK_SEMANTIC_MODEL,
                    TOOL_NAME_PROBE_SEMANTIC_MODEL,
                ],
            ),
        )
        try:
            catalog = await self._gateway.execute(
                TOOL_NAME_DISCOVER_SEMANTIC_MODELS,
                context,
                SemanticModelDiscoveryInput(),
            )
        except ToolTimeoutError:
            return SemanticModelCatalog(
                runtime_mode=self._runtime_mode,
                error_type="semantic_model_discovery_timeout",
            )
        except (
            ToolExecutionError,
            ToolOutputValidationError,
            ToolPolicyDeniedError,
        ):
            return SemanticModelCatalog(
                runtime_mode=self._runtime_mode,
                error_type="semantic_model_discovery_unavailable",
            )

        checked_items: list[SemanticModelOption] = []
        for item in catalog.items:
            if not item.available or not item.connected:
                checked_items.append(item)
                continue
            if self._runtime_mode == RuntimeDataMode.MOCK:
                checked_items.append(
                    item.model_copy(
                        update={
                            "agent_compatible": True,
                            "selectable": True,
                            "schema_drift": False,
                            "compatibility_status": "compatible",
                        }
                    )
                )
                continue
            try:
                probe_context = ToolExecutionContext(
                    runtime_mode=self._runtime_mode,
                    intent=IntentType.DATA_QUESTION,
                    user=UserContext(
                        allowed_semantic_models=[item.key],
                        allowed_tools=[TOOL_NAME_PROBE_SEMANTIC_MODEL],
                    ),
                )
                probe = await self._gateway.execute(
                    TOOL_NAME_PROBE_SEMANTIC_MODEL,
                    probe_context,
                    SemanticModelProbeInput(semantic_model_key=item.key),
                )
            except (
                ToolTimeoutError,
                ToolExecutionError,
                ToolOutputValidationError,
                ToolPolicyDeniedError,
            ):
                checked_items.append(item.model_copy(update={
                    "agent_compatible": False,
                    "selectable": False,
                    "compatibility_status": "unavailable",
                }))
                continue
            if not probe.compatible:
                stale = probe.error_type == "powerbi_stale_instance"
                checked_items.append(item.model_copy(update={
                    "available": item.available and not stale,
                    "connected": item.connected and probe.connected and not stale,
                    "agent_compatible": False,
                    "selectable": False,
                    "schema_drift": False,
                    "compatibility_status": "unavailable",
                }))
                continue
            try:
                compatibility_context = ToolExecutionContext(
                    runtime_mode=self._runtime_mode,
                    intent=IntentType.DATA_QUESTION,
                    user=UserContext(
                        allowed_semantic_models=[item.key],
                        allowed_tools=[TOOL_NAME_CHECK_SEMANTIC_MODEL],
                    ),
                )
                schema = await self._gateway.execute(
                    TOOL_NAME_CHECK_SEMANTIC_MODEL,
                    compatibility_context,
                    SchemaInput(
                        semantic_model_key=item.key
                    ),
                )
            except (
                ToolTimeoutError,
                ToolExecutionError,
                ToolOutputValidationError,
                ToolPolicyDeniedError,
            ):
                checked_items.append(
                    item.model_copy(
                        update={
                            "agent_compatible": False,
                            "selectable": False,
                            "schema_drift": False,
                            "compatibility_status": "unavailable",
                        }
                    )
                )
                continue
            try:
                semantic_catalog = SemanticCatalogBuilder().build(
                    schema,
                    glossary_scope_key=self._glossary_scope_key,
                )
            except GlossaryCatalogError:
                checked_items.append(
                    item.model_copy(
                        update={
                            "agent_compatible": False,
                            "selectable": False,
                            "schema_drift": False,
                            "compatibility_status": "incompatible",
                        }
                    )
                )
                continue
            checked_items.append(
                item.model_copy(
                    update={
                        "agent_compatible": True,
                        "selectable": True,
                        "schema_drift": semantic_catalog.schema_drift,
                        "compatibility_status": "compatible",
                    }
                )
            )
        return catalog.model_copy(update={"items": checked_items})
