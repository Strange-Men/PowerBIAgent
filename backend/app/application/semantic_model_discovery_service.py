"""M5.2 read-only semantic-model discovery application service."""

from pydantic import BaseModel, ConfigDict

from backend.app.config.settings import Settings
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
    ToolSpec,
)
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.models import SemanticModelCatalog
from backend.app.schemas.data_contracts import UserContext


TOOL_NAME_DISCOVER_SEMANTIC_MODELS = "discover_semantic_models"


class SemanticModelDiscoveryInput(BaseModel):
    """Discovery has no caller-controlled connection parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticModelDiscoveryService:
    """Expose Adapter discovery only through the read-only ToolGateway."""

    def __init__(self, adapter: PowerBIAdapter, settings: Settings) -> None:
        self._runtime_mode = (
            RuntimeDataMode.MOCK if adapter.is_mock else RuntimeDataMode.REAL
        )
        self._gateway = ToolGateway()
        config = HarnessConfig.from_settings(settings)

        async def _discover(_: SemanticModelDiscoveryInput) -> SemanticModelCatalog:
            return await adapter.discover_semantic_models()

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

    async def discover(self) -> SemanticModelCatalog:
        context = ToolExecutionContext(
            runtime_mode=self._runtime_mode,
            intent=IntentType.DATA_QUESTION,
            user=UserContext(
                allowed_tools=[TOOL_NAME_DISCOVER_SEMANTIC_MODELS],
            ),
        )
        try:
            return await self._gateway.execute(
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
