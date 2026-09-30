"""Legacy deferred Remote MCP Power BI Adapter skeleton.

ADR-006 is SUPERSEDED. The historical endpoint, constructor defaults and
ADR-006 exception wording below are not a production contract. Endpoint,
auth, identity and RLS/OLS must be revalidated against Microsoft official
capabilities before a user-approved M6 implementation. OAuth and transport
remain unimplemented; this applicability correction changes no behavior.
"""

from backend.app.powerbi.base import PowerBIAdapter
from backend.app.schemas.data_contracts import (
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)


class RemoteMCPPowerBIAdapter(PowerBIAdapter):
    """Remote MCP production provider reserved for a later approved stage."""

    PROVIDER_NAME = "remote_mcp"

    def __init__(
        self,
        server_url: str = "https://api.fabric.microsoft.com/v1/mcp/powerbi",
        tenant_id: str = "",
        client_id: str = "",
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._server_url = server_url
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        raise NotImplementedError(
            "Deferred: implement ADR-006 Remote MCP health in an approved production stage."
        )

    async def get_semantic_model_schema(
        self,
        semantic_model_key: str,
    ) -> SemanticModelSchema:
        raise NotImplementedError(
            "Deferred: read Semantic Model metadata through Remote MCP."
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        raise NotImplementedError(
            "Deferred: execute DAX through Remote MCP."
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        raise NotImplementedError(
            "Deferred: normalize Remote MCP query results."
        )

    async def normalize_error(self, raw: object) -> PowerBIError:
        raise NotImplementedError(
            "Deferred: normalize Remote MCP errors."
        )
