"""Power BI Adapter 单元测试。"""

import ast
import inspect
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.powerbi.local_mcp import (
    M2_1_ALLOWED_TOOL_NAMES,
    DiscoveredLocalTool,
    LocalMCPConnection,
    LocalMCPConnectionError,
    LocalMCPDiagnostics,
    LocalMCPErrorCategory,
    LocalMCPPowerBIAdapter,
    PowerBILocalMCPClient,
)
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.schemas.data_contracts import DAXRequest, SemanticModelSchema


@pytest.fixture
def mock_adapter():
    return MockPowerBIAdapter()


class FakeLocalMCPClient:
    def __init__(
        self,
        result: LocalMCPDiagnostics | None = None,
        error: LocalMCPConnectionError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FlakyLocalNetworkClient:
    def __init__(self) -> None:
        self.calls = 0

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        self.calls += 1
        if self.calls == 1:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.NETWORK,
                "npm_registry_timeout",
                retryable=True,
            )
        return _healthy_local_diagnostics()


class FakeStdioMCPClient:
    """Mimics the official Client surface after stdio protocol negotiation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        **_: object,
    ) -> object:
        self.calls.append((name, arguments))
        operation = arguments["request"]["operation"]  # type: ignore[index]
        if operation == "ListLocalInstances":
            payload = {
                "success": True,
                "data": [{
                    "parentProcessName": "PBIDesktop",
                    "connectionString": "Data Source=localhost:54321;Application Name=test",
                }],
            }
        elif operation == "ListConnections":
            payload = {
                "success": True,
                "data": [{"connectionName": "safe-test-connection"}],
            }
        else:
            payload = {"connectionName": "safe-test-connection"}
        return SimpleNamespace(
            is_error=False,
            structured_content=payload,
            content=[],
        )


def _tool(name: str) -> DiscoveredLocalTool:
    return DiscoveredLocalTool(
        name=name,
        description=f"Safe description for {name}",
        schema_type="object",
        properties=("request",),
        required=("request",),
    )


def _local_tools() -> tuple[DiscoveredLocalTool, ...]:
    return tuple(
        _tool(name)
        for name in (
            "connection_operations",
            "table_operations",
            "column_operations",
            "measure_operations",
            "relationship_operations",
            "user_hierarchy_operations",
            "dax_query_operations",
            "database_operations",
        )
    )


def _healthy_local_diagnostics() -> LocalMCPDiagnostics:
    return LocalMCPDiagnostics(
        server_started=True,
        protocol="2026-07-28",
        tools=_local_tools(),
        desktop_detected=True,
        connection=True,
        schema_capability=True,
        dax_capability=True,
        readonly=True,
    )


def _local_adapter(
    client: LocalMCPConnection,
    *,
    max_retries: int = 0,
) -> LocalMCPPowerBIAdapter:
    return LocalMCPPowerBIAdapter(client=client, max_retries=max_retries)


class TestMockPowerBIAdapter:
    """Mock Power BI Adapter 测试。"""

    @pytest.mark.asyncio
    async def test_health_check(self, mock_adapter):
        assert await mock_adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_get_schema(self, mock_adapter):
        schema = await mock_adapter.get_semantic_model_schema("mock_sales_model")
        assert isinstance(schema, SemanticModelSchema)
        assert schema.key == "mock_sales_model"
        assert len(schema.tables) > 0

    @pytest.mark.asyncio
    async def test_get_schema_not_found(self, mock_adapter):
        with pytest.raises(PowerBIAdapterError, match="not found"):
            await mock_adapter.get_semantic_model_schema("nonexistent_model")

    @pytest.mark.asyncio
    async def test_execute_dax(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE SUMMARIZECOLUMNS('Sales'[Region], \"Total\", SUM('Sales'[SalesAmount]))",
            request_id="data_question",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.row_count == 1
        assert result.columns == ["TotalSales"]

    @pytest.mark.asyncio
    async def test_execute_dax_empty_data(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE FILTER(...)",
            request_id="empty_data",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.row_count == 0
        assert result.rows == []

    @pytest.mark.asyncio
    async def test_execute_dax_timeout(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="timeout",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "timeout"

    @pytest.mark.asyncio
    async def test_execute_dax_permission_denied(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="permission_denied",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "permission_denied"

    @pytest.mark.asyncio
    async def test_execute_dax_error(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE BAD_DAX",
            request_id="dax_error",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "dax_error"

    @pytest.mark.asyncio
    async def test_execute_dax_oversized(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="oversized_result",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_unknown_scenario(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="nonexistent_xyz",
        )
        with pytest.raises(PowerBIAdapterError, match="not found"):
            await mock_adapter.execute_dax(request)

    @pytest.mark.asyncio
    async def test_is_mock(self, mock_adapter):
        assert mock_adapter.is_mock is True
        assert mock_adapter.provider_name == "mock_powerbi"

    @pytest.mark.asyncio
    async def test_available_scenarios(self, mock_adapter):
        scenarios = mock_adapter.available_scenarios()
        assert "data_question" in scenarios
        assert "timeout" in scenarios


class TestLocalMCPPowerBIAdapter:
    """M2.1 Local MCP 只验证 stdio、协议、工具与 Desktop 连接。"""

    def test_adapter_contract_and_identity(self):
        adapter = _local_adapter(FakeLocalMCPClient(_healthy_local_diagnostics()))
        assert isinstance(adapter, PowerBIAdapter)
        assert adapter.provider_name == "local_mcp"
        assert adapter.is_mock is False

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = FakeLocalMCPClient(result=_healthy_local_diagnostics())
        adapter = _local_adapter(client)

        assert await adapter.health_check() is True
        assert adapter.last_diagnostics.healthy is True
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_process_startup_failure_is_explicit(self):
        client = FakeLocalMCPClient(error=LocalMCPConnectionError(
            LocalMCPErrorCategory.MCP_STARTUP,
            "local_mcp_server_exited",
        ))
        adapter = _local_adapter(client)

        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_category == LocalMCPErrorCategory.MCP_STARTUP
        assert adapter.last_diagnostics.error_type == "local_mcp_server_exited"

    @pytest.mark.asyncio
    async def test_protocol_or_list_tools_failure_is_explicit(self):
        diagnostics = LocalMCPDiagnostics.failure(
            LocalMCPErrorCategory.MCP_PROTOCOL,
            "required_future_capabilities_missing",
            server_started=True,
            protocol="2026-07-28",
            tools=(_tool("connection_operations"),),
            readonly=True,
        )
        adapter = _local_adapter(FakeLocalMCPClient(result=diagnostics))

        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_category == LocalMCPErrorCategory.MCP_PROTOCOL

    @pytest.mark.asyncio
    async def test_desktop_not_found_is_not_ready(self):
        diagnostics = LocalMCPDiagnostics.failure(
            LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
            "desktop_instance_not_found",
            server_started=True,
            protocol="2026-07-28",
            tools=_local_tools(),
            schema_capability=True,
            dax_capability=True,
            readonly=True,
        )
        adapter = _local_adapter(FakeLocalMCPClient(result=diagnostics))

        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.desktop_detected is False
        assert adapter.last_diagnostics.error_category == LocalMCPErrorCategory.DESKTOP_NOT_FOUND

    @pytest.mark.asyncio
    async def test_network_failure_retries_at_most_once(self):
        client = FlakyLocalNetworkClient()
        adapter = _local_adapter(client, max_retries=1)

        assert await adapter.health_check() is True
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_failure_never_falls_back_to_mock(self):
        client = FakeLocalMCPClient(error=LocalMCPConnectionError(
            LocalMCPErrorCategory.DESKTOP_CONNECTION,
            "desktop_connection_failed",
        ))
        adapter = _local_adapter(client, max_retries=1)

        assert await adapter.health_check() is False
        assert adapter.provider_name == "local_mcp"
        assert adapter.is_mock is False
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_readonly_is_mandatory(self):
        adapter = LocalMCPPowerBIAdapter(readonly=False)
        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_type == "readonly_required"

    @pytest.mark.asyncio
    async def test_schema_and_dax_business_methods_remain_unimplemented(self):
        adapter = _local_adapter(FakeLocalMCPClient(_healthy_local_diagnostics()))
        with pytest.raises(NotImplementedError, match="M2.2"):
            await adapter.get_semantic_model_schema("friendly-model")
        with pytest.raises(NotImplementedError, match="M2.3"):
            await adapter.execute_dax(DAXRequest(
                semantic_model_key="friendly-model",
                dax="EVALUATE ROW(\"x\", 1)",
            ))

    def test_m2_1_never_exposes_modeling_write_tools(self):
        write_tools = {
            "database_operations",
            "table_operations",
            "column_operations",
            "measure_operations",
            "relationship_operations",
        }
        assert M2_1_ALLOWED_TOOL_NAMES == {"connection_operations"}
        assert M2_1_ALLOWED_TOOL_NAMES.isdisjoint(write_tools)

    def test_local_adapter_has_no_llm_or_mock_dependency(self):
        module = inspect.getmodule(LocalMCPPowerBIAdapter)
        assert module is not None
        source = inspect.getsource(module)
        tree = ast.parse(source)
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert not any(name.startswith("backend.app.llm") for name in modules)
        assert "MockPowerBIAdapter" not in source

    def test_safe_diagnostics_exclude_desktop_identity_and_data(self):
        safe = _healthy_local_diagnostics().safe_dict()
        safe_text = str(safe)
        assert "pbix" not in safe_text.lower()
        assert "localhost" not in safe_text.lower()
        assert "connectionstring" not in safe_text.lower()

    def test_desktop_target_parsing_accepts_localhost_only(self):
        instance = {
            "parentProcessName": "PBIDesktop",
            "connectionString": "Data Source=localhost:54321;Application Name=test",
        }
        assert PowerBILocalMCPClient._desktop_data_source(instance) == "localhost:54321"
        assert PowerBILocalMCPClient._desktop_data_source(
            {"dataSource": "remote.example.com:443"}
        ) is None

    def test_stdio_stderr_is_classified_without_leaking_raw_text(self):
        private_marker = "private-desktop-path-must-not-leak"
        classified = PowerBILocalMCPClient._classify_exception(
            RuntimeError("stdio closed"),
            diagnostic_text=f"npm ENOTFOUND registry; {private_marker}",
        )
        assert classified.category == LocalMCPErrorCategory.NETWORK
        assert classified.error_type == "local_mcp_package_network_error"
        assert private_marker not in str(classified)

    @pytest.mark.asyncio
    async def test_stdio_client_logic_only_calls_connection_operations(self):
        client = PowerBILocalMCPClient()
        fake = FakeStdioMCPClient()

        diagnostics = await client._discover_and_connect_desktop(
            fake,  # type: ignore[arg-type]
            "2026-07-28",
            _local_tools(),
        )

        assert diagnostics.healthy is True
        assert [name for name, _ in fake.calls] == [
            "connection_operations",
            "connection_operations",
            "connection_operations",
        ]
        assert [call[1]["request"]["operation"] for call in fake.calls] == [  # type: ignore[index]
            "ListLocalInstances",
            "Connect",
            "ListConnections",
        ]

    def test_official_mcp_v2_dependency_is_installed(self):
        assert version("mcp") == "2.0.0"
