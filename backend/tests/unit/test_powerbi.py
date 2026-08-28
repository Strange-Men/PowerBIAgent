"""Power BI Adapter 单元测试。"""

import asyncio
import ast
import inspect
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from backend.app.core.async_runtime import AsyncSingleFlight
import backend.app.powerbi.local_mcp as local_mcp_module
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.tool_registry import (
    SchemaInput,
    create_default_tool_gateway,
)
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.powerbi.local_mcp import (
    DAX_EXECUTE_OPERATION_WHITELIST,
    LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
    MAX_DAX_RESULT_ROWS,
    M2_1_ALLOWED_TOOL_NAMES,
    SCHEMA_READ_OPERATION_WHITELIST,
    DiscoveredLocalTool,
    LocalMCPConnection,
    LocalMCPConnectionError,
    LocalMCPCompatibilitySnapshot,
    LocalMCPDiagnostics,
    LocalMCPDiscoveredModel,
    LocalMCPDiscoverySnapshot,
    LocalMCPDAXSnapshot,
    LocalMCPErrorCategory,
    LocalMCPPowerBIAdapter,
    LocalMCPSchemaSnapshot,
    PowerBILocalMCPClient,
)
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.schemas.data_contracts import (
    ColumnMembersRequest,
    DAXRequest,
    SemanticModelSchema,
    UserContext,
)


TEST_INSTANCE = {
    "processId": 1001,
    "port": 54321,
    "connectionString": "Data Source=localhost:54321;Application Name=test",
    "parentProcessName": "PBIDesktop",
    "parentWindowTitle": "财务销售分析 - Power BI Desktop",
    "startTime": "2026-08-24T09:00:00+08:00",
}
TEST_MODEL_KEY = PowerBILocalMCPClient._desktop_semantic_model_key(
    process_id=1001,
    data_source="localhost:54321",
    start_time="2026-08-24T09:00:00+08:00",
)
# Existing focused cases use this historical symbol as their selected key.
LOCAL_DESKTOP_SEMANTIC_MODEL_KEY = TEST_MODEL_KEY


@pytest.fixture
def mock_adapter():
    return MockPowerBIAdapter()


class FakeLocalMCPClient:
    def __init__(
        self,
        result: LocalMCPDiagnostics | None = None,
        error: LocalMCPConnectionError | None = None,
        schema_snapshot: LocalMCPSchemaSnapshot | None = None,
        schema_error: LocalMCPConnectionError | None = None,
        dax_snapshot: LocalMCPDAXSnapshot | None = None,
        dax_error: LocalMCPConnectionError | None = None,
        discovery_snapshot: LocalMCPDiscoverySnapshot | None = None,
        discovery_error: LocalMCPConnectionError | None = None,
        probe_snapshot: LocalMCPCompatibilitySnapshot | None = None,
        probe_error: LocalMCPConnectionError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.schema_snapshot = schema_snapshot
        self.schema_error = schema_error
        self.dax_snapshot = dax_snapshot
        self.dax_error = dax_error
        self.discovery_snapshot = discovery_snapshot
        self.discovery_error = discovery_error
        self.probe_snapshot = probe_snapshot
        self.probe_error = probe_error
        self.calls = 0
        self.schema_calls = 0
        self.schema_keys: list[str] = []
        self.dax_calls = 0
        self.dax_keys: list[str] = []
        self.discovery_calls = 0
        self.probe_calls: list[str] = []
        self.session_generation = 1
        self.validation_calls: list[str] = []
        self.validation_error: LocalMCPConnectionError | None = None
        self.close_calls = 0

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result

    async def read_semantic_model_schema(
        self, semantic_model_key: str
    ) -> LocalMCPSchemaSnapshot:
        self.schema_calls += 1
        self.schema_keys.append(semantic_model_key)
        if self.schema_error is not None:
            raise self.schema_error
        assert self.schema_snapshot is not None
        return LocalMCPSchemaSnapshot(
            diagnostics=self.schema_snapshot.diagnostics,
            semantic_model_key=semantic_model_key,
            tables=self.schema_snapshot.tables,
            columns=self.schema_snapshot.columns,
            measures=self.schema_snapshot.measures,
            relationships=self.schema_snapshot.relationships,
            hierarchies=self.schema_snapshot.hierarchies,
        )

    async def discover_semantic_models(self) -> LocalMCPDiscoverySnapshot:
        self.discovery_calls += 1
        if self.discovery_error is not None:
            raise self.discovery_error
        assert self.discovery_snapshot is not None
        return self.discovery_snapshot

    async def probe_compatibility(
        self, semantic_model_key: str
    ) -> LocalMCPCompatibilitySnapshot:
        self.probe_calls.append(semantic_model_key)
        if self.probe_error is not None:
            raise self.probe_error
        assert self.probe_snapshot is not None
        return self.probe_snapshot

    async def execute_dax(self, request: DAXRequest) -> LocalMCPDAXSnapshot:
        self.dax_calls += 1
        self.dax_keys.append(request.semantic_model_key)
        if self.dax_error is not None:
            raise self.dax_error
        assert self.dax_snapshot is not None
        return LocalMCPDAXSnapshot(
            diagnostics=self.dax_snapshot.diagnostics,
            request=request,
            wire_max_rows=request.max_rows + 1,
            payload=self.dax_snapshot.payload,
        )

    async def validate_semantic_model(self, semantic_model_key: str) -> None:
        self.validation_calls.append(semantic_model_key)
        if self.validation_error is not None:
            raise self.validation_error

    async def aclose(self) -> None:
        self.close_calls += 1


class FlakyLocalNetworkClient:
    def __init__(self) -> None:
        self.calls = 0

    async def discover_semantic_models(self) -> LocalMCPDiscoverySnapshot:
        self.calls += 1
        if self.calls == 1:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.NETWORK,
                "npm_registry_timeout",
                retryable=True,
            )
        return _discovery_snapshot()

    async def probe_compatibility(
        self, semantic_model_key: str
    ) -> LocalMCPCompatibilitySnapshot:
        return _compatibility_snapshot(semantic_model_key)


class FlakyLocalDAXNetworkClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    async def execute_dax(self, request: DAXRequest) -> LocalMCPDAXSnapshot:
        self.calls += 1
        if self.calls == 1:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.NETWORK,
                "npm_registry_timeout",
                retryable=True,
            )
        return _dax_snapshot(self.payload, request=request)


class FakeStdioMCPClient:
    """Mimics the official Client surface after stdio protocol negotiation."""

    def __init__(
        self,
        instances: list[dict[str, object]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.instances = instances if instances is not None else [dict(TEST_INSTANCE)]

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
                "data": self.instances,
            }
        elif operation == "ListConnections":
            payload = {
                "success": True,
                "data": [{"connectionName": "safe-test-connection"}],
            }
        else:
            payload = {"success": True, "data": "safe-test-connection"}
        return SimpleNamespace(
            is_error=False,
            structured_content=payload,
            content=[],
        )


class FakeSchemaStdioMCPClient(FakeStdioMCPClient):
    """Fake observed Local MCP List/Get response shapes for offline CI."""

    def __init__(
        self,
        snapshot: LocalMCPSchemaSnapshot,
        *,
        malformed_tool: str | None = None,
        error_tool: str | None = None,
        permission_tool: str | None = None,
    ) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.malformed_tool = malformed_tool
        self.error_tool = error_tool
        self.permission_tool = permission_tool

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        **kwargs: object,
    ) -> object:
        if name == "connection_operations":
            return await super().call_tool(name, arguments, **kwargs)

        self.calls.append((name, arguments))
        request = arguments["request"]
        assert isinstance(request, dict)
        operation = request["operation"]
        assert operation in {"List", "Get"}
        if name == self.error_tool:
            return SimpleNamespace(
                is_error=True,
                structured_content={"operation": operation},
                content=[],
            )
        if name == self.permission_tool:
            return SimpleNamespace(
                is_error=True,
                structured_content={
                    "operation": operation,
                    "error": "permission denied at private-path",
                },
                content=[],
            )
        if name == self.malformed_tool and operation == "List":
            return SimpleNamespace(
                is_error=False,
                structured_content={"operation": "List", "message": "safe"},
                content=[],
            )

        if operation == "List":
            payload = self._list_payload(name)
        else:
            references = request.get("references")
            assert isinstance(references, list)
            payload = self._get_payload(name, references)
        return SimpleNamespace(
            is_error=False,
            structured_content=payload,
            content=[],
        )

    def _list_payload(self, name: str) -> dict[str, object]:
        if name == "table_operations":
            data = [{"name": item["name"]} for item in self.snapshot.tables]
        elif name == "column_operations":
            data = self._group_list(self.snapshot.columns, "columns")
        elif name == "measure_operations":
            data = self._group_list(self.snapshot.measures, "measures")
        elif name == "relationship_operations":
            data = [{"name": item.get("name", f"relationship-{index}")}
                    for index, item in enumerate(self.snapshot.relationships)]
        elif name == "user_hierarchy_operations":
            data = [
                {
                    "tableName": item["tableName"],
                    "hierarchy": {"name": item["name"], "levels": item["levels"]},
                }
                for item in self.snapshot.hierarchies
            ]
        else:
            raise AssertionError("unexpected schema tool")
        return {"operation": "List", "message": "safe", "data": data}

    @staticmethod
    def _group_list(
        records: tuple[dict[str, object], ...],
        child_key: str,
    ) -> list[dict[str, object]]:
        groups: dict[str, list[dict[str, object]]] = {}
        for item in records:
            table_name = item["tableName"]
            assert isinstance(table_name, str)
            groups.setdefault(table_name, []).append({"name": item["name"]})
        return [
            {"tableName": table_name, child_key: children}
            for table_name, children in groups.items()
        ]

    def _get_payload(
        self,
        name: str,
        references: list[object],
    ) -> dict[str, object]:
        source = {
            "table_operations": self.snapshot.tables,
            "column_operations": self.snapshot.columns,
            "measure_operations": self.snapshot.measures,
            "relationship_operations": self.snapshot.relationships,
            "user_hierarchy_operations": self.snapshot.hierarchies,
        }[name]
        results = []
        for index, reference in enumerate(references):
            assert isinstance(reference, dict)
            if name == "table_operations":
                match = next(item for item in source if item["name"] == reference["name"])
            elif name in {"column_operations", "measure_operations"}:
                match = next(
                    item for item in source
                    if item["tableName"] == reference["tableName"]
                    and item["name"] == reference["name"]
                )
            elif name == "relationship_operations":
                match = source[index]
            else:
                match = next(
                    item for item in source
                    if item["tableName"] == reference["tableName"]
                    and item["name"] == reference["hierarchyName"]
                )
            results.append({"index": index, "data": match, "message": "safe"})
        return {
            "operation": "Get",
            "message": "safe",
            "results": results,
            "summary": {
                "totalItems": len(results),
                "successCount": len(results),
                "failureCount": 0,
            },
        }


class FakeDAXStdioMCPClient(FakeStdioMCPClient):
    """Fake beta.12 Inline Execute boundary for offline CI."""

    def __init__(
        self,
        payload: dict[str, object],
        *,
        is_error: bool = False,
    ) -> None:
        super().__init__()
        self.payload = payload
        self.is_error = is_error

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        **kwargs: object,
    ) -> object:
        if name == "connection_operations":
            return await super().call_tool(name, arguments, **kwargs)
        assert name == "dax_query_operations"
        self.calls.append((name, arguments))
        return SimpleNamespace(
            is_error=self.is_error,
            structured_content=self.payload,
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


def _schema_snapshot(
    semantic_model_key: str = TEST_MODEL_KEY,
) -> LocalMCPSchemaSnapshot:
    diagnostics = _healthy_local_diagnostics()
    return LocalMCPSchemaSnapshot(
        diagnostics=diagnostics,
        semantic_model_key=semantic_model_key,
        tables=(
            {
                "name": "Sales",
                "description": "Sales facts",
                "isHidden": False,
                "systemManaged": False,
                "unknownFutureField": "ignored",
            },
            {
                "name": "Products",
                "description": None,
                "isHidden": False,
                "systemManaged": False,
            },
        ),
        columns=(
            {
                "tableName": "Sales",
                "name": "Quantity",
                "dataType": "Int64",
                "isHidden": False,
                "description": "Units sold",
            },
            {
                "tableName": "Sales",
                "name": "UnitPrice",
                "dataType": "Double",
                "isHidden": False,
                "description": None,
            },
            {
                "tableName": "Sales",
                "name": "ProductKey",
                "dataType": "Int64",
                "isHidden": True,
            },
            {
                "tableName": "Products",
                "name": "ProductKey",
                "dataType": "Int64",
                "isHidden": True,
            },
            {
                "tableName": "Products",
                "name": "Product",
                "dataType": "String",
                "isHidden": False,
            },
            {
                "tableName": "Products",
                "name": "Category",
                "dataType": "String",
                "isHidden": False,
            },
        ),
        measures=(
            {
                "tableName": "Sales",
                "name": "Total Sales",
                "expression": "SUMX(Sales, Sales[Quantity] * Sales[UnitPrice])",
                "dataType": "Double",
                "isHidden": False,
                "description": "Revenue measure",
            },
            {
                "tableName": "Sales",
                "name": "Total Quantity",
                "expression": "SUM(Sales[Quantity])",
                "dataType": "Int64",
                "isHidden": False,
            },
        ),
        relationships=(
            {
                "fromTable": "Sales",
                "fromColumn": "ProductKey",
                "toTable": "Products",
                "toColumn": "ProductKey",
                "isActive": True,
                "fromCardinality": "Many",
                "toCardinality": "One",
            },
        ),
        hierarchies=(
            {
                "tableName": "Products",
                "name": "Product Hierarchy",
                "levels": [
                    {"name": "Category", "columnName": "Category"},
                    {"name": "Product", "columnName": "Product"},
                ],
            },
        ),
    )


def _dax_snapshot(
    payload: dict[str, object],
    *,
    request: DAXRequest | None = None,
) -> LocalMCPDAXSnapshot:
    return LocalMCPDAXSnapshot(
        diagnostics=_healthy_local_diagnostics(),
        request=request or DAXRequest(
            semantic_model_key=TEST_MODEL_KEY,
            dax='EVALUATE ROW("TestValue", 1)',
            request_id="request-123",
        ),
        wire_max_rows=(request.max_rows if request else 1000) + 1,
        payload=payload,
    )


def _discovery_snapshot(
    *models: LocalMCPDiscoveredModel,
) -> LocalMCPDiscoverySnapshot:
    return LocalMCPDiscoverySnapshot(
        diagnostics=_healthy_local_diagnostics(),
        models=models or (
            LocalMCPDiscoveredModel(
                semantic_model_key=TEST_MODEL_KEY,
                display_name="财务销售分析",
            ),
        ),
    )


def _compatibility_snapshot(
    semantic_model_key: str = TEST_MODEL_KEY,
    *,
    value: object = 1,
) -> LocalMCPCompatibilitySnapshot:
    request = DAXRequest(
        semantic_model_key=semantic_model_key,
        dax='EVALUATE ROW("__pbiagent_probe", 1)',
        max_rows=2,
    )
    dax = _dax_snapshot(
        {
            "operation": "Execute",
            "data": {
                "rowCount": 1,
                "columns": [{"name": "[__pbiagent_probe]", "ordinal": 0}],
                "rows": [{"[__pbiagent_probe]": value}],
            },
        },
        request=request,
    )
    return LocalMCPCompatibilitySnapshot(
        diagnostics=_healthy_local_diagnostics(),
        schema=_schema_snapshot(semantic_model_key),
        dax=dax,
    )


def _successful_dax_payload(
    *,
    rows: list[dict[str, object]] | None = None,
    row_count: int | None = None,
) -> dict[str, object]:
    result_rows = rows if rows is not None else [
        {"[Second]": 2, "[First]": 1}
    ]
    return {
        "success": True,
        "operation": "Execute",
        "data": {
            "success": True,
            "rowCount": len(result_rows) if row_count is None else row_count,
            "columns": [
                {"name": "[First]", "ordinal": 0},
                {"name": "[Second]", "ordinal": 1},
            ],
            "rows": result_rows,
            "executionTimeMs": 7,
        },
    }


def _local_adapter(
    client: LocalMCPConnection,
    *,
    max_retries: int = 0,
) -> LocalMCPPowerBIAdapter:
    return LocalMCPPowerBIAdapter(
        client=client,
        max_retries=max_retries,
        semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
    )


class TestMockPowerBIAdapter:
    """Mock Power BI Adapter 测试。"""

    @pytest.mark.asyncio
    async def test_health_check(self, mock_adapter):
        assert await mock_adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_discovery_returns_only_chat_selectable_mock_model(self, mock_adapter):
        catalog = await mock_adapter.discover_semantic_models()

        assert catalog.runtime_mode == RuntimeDataMode.MOCK
        assert [item.key for item in catalog.items] == ["mock_sales_model"]
        assert catalog.items[0].available is True
        assert catalog.items[0].connected is True

        # The unsupported fixture remains available to focused tests, but discovery
        # must not promote fixture presence into formal Chat capability.
        schema = await mock_adapter.get_semantic_model_schema(
            "mock_satisfaction_model"
        )
        assert schema.key == "mock_satisfaction_model"

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

    def test_legacy_schema_contract_remains_compatible(self):
        schema = SemanticModelSchema.model_validate({
            "name": "legacy",
            "key": "legacy",
            "tables": [{
                "name": "Sales",
                "columns": [{"name": "Quantity", "data_type": "integer"}],
                "measures": [{"name": "Total Quantity"}],
                "hierarchies": [{"name": "Date", "levels": ["Year"]}],
            }],
            "relationships": [{
                "from_table": "Sales",
                "from_column": "Quantity",
                "to_table": "Sales",
                "to_column": "Quantity",
            }],
        })

        assert schema.tables[0].description is None
        assert schema.tables[0].is_hidden is False
        assert schema.tables[0].measures[0].description is None
        assert schema.relationships[0].is_active is True


class TestLocalMCPPowerBIAdapter:
    """M2.1 Local MCP 只验证 stdio、协议、工具与 Desktop 连接。"""

    def test_adapter_contract_and_identity(self):
        adapter = _local_adapter(FakeLocalMCPClient(_healthy_local_diagnostics()))
        assert isinstance(adapter, PowerBIAdapter)
        assert adapter.provider_name == "local_mcp"
        assert adapter.is_mock is False

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = FakeLocalMCPClient(
            discovery_snapshot=_discovery_snapshot(),
            probe_snapshot=_compatibility_snapshot(),
        )
        adapter = _local_adapter(client)

        assert await adapter.health_check() is True
        assert adapter.last_diagnostics.healthy is True
        assert client.discovery_calls == 1
        assert client.probe_calls == [TEST_MODEL_KEY]

    @pytest.mark.asyncio
    async def test_real_discovery_returns_only_safe_current_desktop_model(self):
        client = FakeLocalMCPClient(
            discovery_snapshot=_discovery_snapshot()
        )
        adapter = _local_adapter(client)

        catalog = await adapter.discover_semantic_models()

        assert catalog.runtime_mode == RuntimeDataMode.REAL
        assert catalog.error_type is None
        assert len(catalog.items) == 1
        assert catalog.items[0].model_dump() == {
            "key": LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            "display_name": "财务销售分析",
            "source": "local_desktop",
            "type": "semantic_model",
            "available": True,
            "connected": True,
            "agent_compatible": False,
            "selectable": False,
            "schema_drift": False,
            "compatibility_status": "unavailable",
        }
        assert client.discovery_calls == 1

    @pytest.mark.asyncio
    async def test_discovery_desktop_absent_is_safe_empty_catalog(self):
        private_marker = "C:/private/customer.pbix"
        client = FakeLocalMCPClient(
            discovery_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
                "desktop_instance_not_found",
            )
        )
        adapter = _local_adapter(client)

        catalog = await adapter.discover_semantic_models()

        assert catalog.items == []
        assert catalog.error_type == "powerbi_desktop_not_connected"
        assert private_marker not in catalog.model_dump_json()

    @pytest.mark.asyncio
    async def test_discovery_multiple_desktops_returns_unique_safe_options(self):
        second_key = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=1002,
            data_source="localhost:54322",
            start_time="2026-08-24T09:01:00+08:00",
        )
        client = FakeLocalMCPClient(discovery_snapshot=_discovery_snapshot(
            LocalMCPDiscoveredModel(
                semantic_model_key=TEST_MODEL_KEY,
                display_name="同名模型",
            ),
            LocalMCPDiscoveredModel(
                semantic_model_key=second_key,
                display_name="同名模型",
            ),
        ))
        catalog = await _local_adapter(client).discover_semantic_models()

        assert [item.display_name for item in catalog.items] == ["同名模型", "同名模型"]
        assert {item.key for item in catalog.items} == {TEST_MODEL_KEY, second_key}
        assert all(item.key.startswith("local_desktop:") for item in catalog.items)
        assert catalog.error_type is None

    @pytest.mark.asyncio
    async def test_discovery_duplicate_instance_identity_fails_closed(self):
        client = FakeLocalMCPClient(
            discovery_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.DESKTOP_MULTIPLE_INSTANCES,
                "desktop_instance_identity_not_unique",
            )
        )
        catalog = await _local_adapter(client).discover_semantic_models()

        assert catalog.items == []
        assert catalog.error_type == "powerbi_multiple_desktop_instances"

    @pytest.mark.asyncio
    async def test_process_startup_failure_is_explicit(self):
        client = FakeLocalMCPClient(discovery_error=LocalMCPConnectionError(
            LocalMCPErrorCategory.MCP_STARTUP,
            "local_mcp_server_exited",
        ))
        adapter = _local_adapter(client)

        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_category == LocalMCPErrorCategory.MCP_STARTUP
        assert adapter.last_diagnostics.error_type == "local_mcp_server_exited"

    @pytest.mark.asyncio
    async def test_protocol_or_list_tools_failure_is_explicit(self):
        adapter = _local_adapter(FakeLocalMCPClient(
            discovery_snapshot=_discovery_snapshot(),
            probe_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.MCP_PROTOCOL,
                "required_future_capabilities_missing",
            ),
        ))

        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_category == LocalMCPErrorCategory.MCP_PROTOCOL

    @pytest.mark.asyncio
    async def test_desktop_not_found_is_not_ready(self):
        adapter = _local_adapter(FakeLocalMCPClient(
            discovery_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
                "desktop_instance_not_found",
            )
        ))

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
        client = FakeLocalMCPClient(discovery_error=LocalMCPConnectionError(
            LocalMCPErrorCategory.DESKTOP_CONNECTION,
            "desktop_connection_failed",
        ))
        adapter = _local_adapter(client, max_retries=1)

        assert await adapter.health_check() is False
        assert adapter.provider_name == "local_mcp"
        assert adapter.is_mock is False
        assert client.discovery_calls == 1

    @pytest.mark.asyncio
    async def test_readonly_is_mandatory(self):
        adapter = LocalMCPPowerBIAdapter(readonly=False)
        assert await adapter.health_check() is False
        assert adapter.last_diagnostics.error_type == "readonly_required"
        with pytest.raises(PowerBIAdapterError) as exc_info:
            await adapter.get_semantic_model_schema(
                LOCAL_DESKTOP_SEMANTIC_MODEL_KEY
            )
        assert exc_info.value.error_type == "SCHEMA_VALIDATION_FAILED"
        with pytest.raises(PowerBIAdapterError) as dax_info:
            await adapter.execute_dax(DAXRequest(
                semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
                dax='EVALUATE ROW("TestValue", 1)',
            ))
        assert dax_info.value.error_type == "DAX_ERROR"

    @pytest.mark.asyncio
    async def test_schema_mapping_remains_compatible(self):
        client = FakeLocalMCPClient(schema_snapshot=_schema_snapshot())
        adapter = _local_adapter(client)

        schema = await adapter.get_semantic_model_schema(
            LOCAL_DESKTOP_SEMANTIC_MODEL_KEY
        )

        assert schema.key == LOCAL_DESKTOP_SEMANTIC_MODEL_KEY
        assert [table.name for table in schema.tables] == ["Sales", "Products"]
        sales = schema.tables[0]
        assert sales.description == "Sales facts"
        assert sales.is_hidden is False
        assert sales.is_system_managed is False
        assert [column.name for column in sales.columns] == [
            "Quantity", "UnitPrice", "ProductKey"
        ]
        assert sales.columns[0].data_type == "Int64"
        assert sales.columns[0].description == "Units sold"
        assert sales.columns[2].is_hidden is True
        assert [measure.name for measure in sales.measures] == [
            "Total Sales", "Total Quantity"
        ]
        assert sales.measures[0].expression.startswith("SUMX")
        assert sales.measures[0].data_type == "Double"
        assert sales.measures[0].description == "Revenue measure"
        assert "Total Sales" not in [column.name for column in sales.columns]
        products = schema.tables[1]
        assert products.hierarchies[0].levels == ["Category", "Product"]
        relationship = schema.relationships[0]
        assert relationship.from_table == "Sales"
        assert relationship.to_table == "Products"
        assert relationship.is_active is True
        assert relationship.from_cardinality == "Many"
        assert relationship.to_cardinality == "One"
        assert schema.get_all_measures() == ["Total Sales", "Total Quantity"]
        assert client.schema_calls == 1

    @pytest.mark.asyncio
    async def test_execute_dax_maps_ordered_rows_and_query_metadata(self):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("First", 1, "Second", 2)',
            max_rows=10,
            timeout_seconds=15,
            request_id="request-123",
        )
        client = FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(_successful_dax_payload(), request=request)
        )
        result = await _local_adapter(client).execute_dax(request)

        assert result.columns == ["[First]", "[Second]"]
        assert result.rows == [[1, 2]]
        assert result.row_count == len(result.rows) == 1
        assert result.execution_time_ms == 7
        assert result.source_mode == "real"
        assert result.request_id == "request-123"
        assert result.error is None
        assert result.truncated is False
        assert client.dax_calls == 1

    @pytest.mark.asyncio
    async def test_execute_dax_normalizes_qualified_group_by_column_label(self):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax=(
                "EVALUATE SUMMARIZECOLUMNS('Sales'[Category], "
                '"Total Sales", [Total Sales])'
            ),
            request_id="qualified-group",
        )
        payload = {
            "success": True,
            "data": {
                "success": True,
                "rowCount": 1,
                "columns": [
                    {"name": "Sales[Category]", "ordinal": 0},
                    {"name": "[Total Sales]", "ordinal": 1},
                ],
                "rows": [
                    {"Sales[Category]": "A", "[Total Sales]": 10},
                ],
            },
        }

        result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(payload, request=request)
        )).execute_dax(request)

        assert result.columns == ["Category", "[Total Sales]"]
        assert result.rows == [["A", 10]]

    def test_qualified_column_normalization_rejects_collisions(self):
        with pytest.raises(
            LocalMCPConnectionError,
            match="dax_normalized_column_name_collision",
        ):
            LocalMCPPowerBIAdapter._normalize_dax_column_names(
                ["Sales[Category]", "Products[Category]"]
            )

    @pytest.mark.asyncio
    async def test_bounded_member_lookup_is_adapter_owned_and_real(self):
        request = ColumnMembersRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            table_name="Products",
            field_name="Category",
            limit=2,
        )
        payload = {
            "success": True,
            "operation": "Execute",
            "data": {
                "success": True,
                "rowCount": 3,
                "columns": [{"name": "[MemberValue]", "ordinal": 0}],
                "rows": [
                    {"[MemberValue]": "A"},
                    {"[MemberValue]": "B"},
                    {"[MemberValue]": "C"},
                ],
            },
        }
        client = FakeLocalMCPClient(
            schema_snapshot=_schema_snapshot(),
            dax_snapshot=_dax_snapshot(payload),
        )
        result = await _local_adapter(client).get_column_members(request)

        assert result.values == ["A", "B"]
        assert result.truncated is True
        assert result.source_mode == "real"
        assert client.schema_calls == 1
        assert client.dax_calls == 1
        assert client.schema_keys == [TEST_MODEL_KEY]
        assert client.dax_keys == [TEST_MODEL_KEY]

    @pytest.mark.asyncio
    async def test_member_lookup_fails_closed_if_selected_instance_disappears(self):
        client = FakeLocalMCPClient(
            schema_snapshot=_schema_snapshot(),
            dax_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.DESKTOP_STALE_INSTANCE,
                "desktop_selected_instance_stale",
            ),
        )

        with pytest.raises(PowerBIAdapterError) as exc_info:
            await _local_adapter(client).get_column_members(ColumnMembersRequest(
                semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
                table_name="Products",
                field_name="Category",
                limit=2,
            ))

        assert exc_info.value.error_type == "stale_instance"
        assert client.schema_calls == 1
        assert client.dax_calls == 1

    @pytest.mark.asyncio
    async def test_member_lookup_rejects_unbounded_or_unknown_field_before_dax(self):
        with pytest.raises(ValueError):
            ColumnMembersRequest(
                semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
                table_name="Products",
                field_name="Category",
                limit=201,
            )

        client = FakeLocalMCPClient(schema_snapshot=_schema_snapshot())
        with pytest.raises(PowerBIAdapterError, match="visible runtime column"):
            await _local_adapter(client).get_column_members(ColumnMembersRequest(
                semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
                table_name="Products",
                field_name="Unknown",
                limit=10,
            ))
        assert client.dax_calls == 0

    @pytest.mark.asyncio
    async def test_execute_dax_maps_empty_and_truncated_results(self):
        empty_request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax="EVALUATE FILTER({1}, FALSE())",
            request_id="empty",
        )
        empty_payload = _successful_dax_payload(rows=[])
        empty_payload["data"].pop("executionTimeMs")  # type: ignore[union-attr]
        empty_payload["executionMetrics"] = {
            "reportedExecutionMetrics": {"durationMs": 4}
        }
        empty_result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(empty_payload, request=empty_request)
        )).execute_dax(empty_request)
        assert empty_result.rows == []
        assert empty_result.row_count == 0
        assert empty_result.columns == ["[First]", "[Second]"]
        assert empty_result.execution_time_ms == 4

        limited_request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax="EVALUATE {1, 2, 3}",
            max_rows=2,
            request_id="limited",
        )
        rows = [
            {"[Second]": value * 2, "[First]": value}
            for value in (1, 2, 3)
        ]
        limited_result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(
                _successful_dax_payload(rows=rows),
                request=limited_request,
            )
        )).execute_dax(limited_request)
        assert limited_result.rows == [[1, 2], [2, 4]]
        assert limited_result.row_count == 2
        assert limited_result.truncated is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("category", "expected_type"),
        [
            (LocalMCPErrorCategory.DAX_ERROR, "dax_error"),
            (LocalMCPErrorCategory.DAX_TIMEOUT, "timeout"),
            (LocalMCPErrorCategory.DAX_PERMISSION_DENIED, "permission_denied"),
            (LocalMCPErrorCategory.DESKTOP_CONNECTION, "connection_error"),
            (LocalMCPErrorCategory.MCP_PROTOCOL, "mcp_protocol"),
        ],
    )
    async def test_execute_dax_standardizes_errors_without_retry(
        self,
        category: LocalMCPErrorCategory,
        expected_type: str,
    ):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax="EVALUATE BAD_DAX",
            request_id="failed",
        )
        private_marker = "private-port-path-must-not-leak"
        client = FakeLocalMCPClient(dax_error=LocalMCPConnectionError(
            category,
            private_marker,
        ))
        adapter = _local_adapter(client, max_retries=1)
        result = await adapter.execute_dax(request)

        assert result.error is not None
        assert result.error.type == expected_type
        assert result.error.retryable is False
        assert private_marker not in result.error.message
        assert result.source_mode == "real"
        assert result.request_id == "failed"
        assert adapter.is_mock is False
        assert client.dax_calls == 1

    @pytest.mark.asyncio
    async def test_execute_dax_retries_network_once_only(self):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("TestValue", 1)',
        )
        client = FlakyLocalDAXNetworkClient(_successful_dax_payload())
        result = await _local_adapter(
            client,  # type: ignore[arg-type]
            max_retries=1,
        ).execute_dax(request)

        assert result.error is None
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_execute_dax_rejects_malformed_and_preview_missing_rows(self):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("TestValue", 1)',
            request_id="preview",
        )
        missing_rows = {
            "success": True,
            "operation": "Execute",
            "data": {
                "success": True,
                "rowCount": 1,
                "columns": [{"name": "[TestValue]"}],
                "executionTimeMs": 3,
            },
            "executionMetrics": {
                "reportedExecutionMetrics": {
                    "queryResultRows": 1,
                    "durationMs": 3,
                }
            },
        }
        preview_result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(missing_rows, request=request)
        )).execute_dax(request)
        assert preview_result.error is not None
        assert preview_result.error.type == "preview_row_data_missing"

        malformed = _successful_dax_payload()
        malformed["data"]["columns"] = [{"unknown": "value"}]  # type: ignore[index]
        malformed_result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(malformed, request=request)
        )).execute_dax(request)
        assert malformed_result.error is not None
        assert malformed_result.error.type == "malformed_response"

    @pytest.mark.asyncio
    async def test_execute_dax_rejects_invalid_key_and_oversized_request(self):
        client = FakeLocalMCPClient()
        adapter = _local_adapter(client)
        with pytest.raises(PowerBIAdapterError):
            await adapter.execute_dax(DAXRequest(
                semantic_model_key="localhost:54321",
                dax='EVALUATE ROW("TestValue", 1)',
            ))
        assert client.dax_calls == 0

        oversized = await adapter.execute_dax(DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("TestValue", 1)',
            max_rows=MAX_DAX_RESULT_ROWS + 1,
        ))
        assert oversized.error is not None
        assert oversized.error.type == "oversized"
        assert oversized.truncated is True
        assert client.dax_calls == 0

    @pytest.mark.asyncio
    async def test_schema_key_is_friendly_and_cannot_be_arbitrary_connection(self):
        client = FakeLocalMCPClient(schema_snapshot=_schema_snapshot())
        adapter = _local_adapter(client)

        with pytest.raises(PowerBIAdapterError) as exc_info:
            await adapter.get_semantic_model_schema("localhost:54321")

        assert exc_info.value.error_type == "SCHEMA_VALIDATION_FAILED"
        assert client.schema_calls == 0

    @pytest.mark.asyncio
    async def test_schema_errors_are_standardized_without_mock_fallback(self):
        client = FakeLocalMCPClient(schema_error=LocalMCPConnectionError(
            LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
            "schema_payload_not_object",
        ))
        adapter = _local_adapter(client)

        with pytest.raises(PowerBIAdapterError) as exc_info:
            await adapter.get_semantic_model_schema(
                LOCAL_DESKTOP_SEMANTIC_MODEL_KEY
            )

        assert exc_info.value.error_type == "SCHEMA_MALFORMED_RESPONSE"
        assert exc_info.value.provider == "local_mcp"
        assert adapter.is_mock is False
        assert client.schema_calls == 1
        assert (
            adapter.last_diagnostics.error_category
            == LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE
        )
        assert adapter.last_diagnostics.error_type == "schema_payload_not_object"

    @pytest.mark.asyncio
    async def test_schema_validation_rejects_invalid_ownership(self):
        snapshot = _schema_snapshot()
        malformed = LocalMCPSchemaSnapshot(
            diagnostics=snapshot.diagnostics,
            semantic_model_key=snapshot.semantic_model_key,
            tables=snapshot.tables,
            columns=snapshot.columns + ({
                "tableName": "Unknown",
                "name": "Ghost",
                "dataType": "String",
            },),
            measures=snapshot.measures,
            relationships=snapshot.relationships,
            hierarchies=snapshot.hierarchies,
        )
        adapter = _local_adapter(FakeLocalMCPClient(schema_snapshot=malformed))

        with pytest.raises(PowerBIAdapterError) as exc_info:
            await adapter.get_semantic_model_schema(
                LOCAL_DESKTOP_SEMANTIC_MODEL_KEY
            )

        assert exc_info.value.error_type == "SCHEMA_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_tool_gateway_exposes_only_powerbi_abstractions(self):
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("First", 1, "Second", 2)',
            request_id="gateway",
        )
        client = FakeLocalMCPClient(
            schema_snapshot=_schema_snapshot(),
            dax_snapshot=_dax_snapshot(_successful_dax_payload(), request=request),
        )
        adapter = _local_adapter(client)

        async def render(_: object) -> str:
            return "<html></html>"

        gateway = create_default_tool_gateway(
            adapter,
            SimpleNamespace(render=render),
            HarnessConfig(max_powerbi_retries=0),
        )
        context = ToolExecutionContext(
            intent=IntentType.DATA_QUESTION,
            user=UserContext(
                allowed_semantic_models=[LOCAL_DESKTOP_SEMANTIC_MODEL_KEY],
                allowed_tools=["get_semantic_model_schema", "execute_dax"],
            ),
            runtime_mode=RuntimeDataMode.REAL,
        )

        schema = await gateway.execute(
            "get_semantic_model_schema",
            context,
            SchemaInput(semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY),
        )
        query_result = await gateway.execute(
            "execute_dax",
            context,
            request,
        )

        assert isinstance(schema, SemanticModelSchema)
        assert query_result.rows == [[1, 2]]
        assert query_result.source_mode == "real"
        assert client.dax_calls == 1
        assert gateway.list_tools() == [
            "get_semantic_model_schema",
            "get_column_members",
            "execute_dax",
            "render_report",
        ]
        assert not set(SCHEMA_READ_OPERATION_WHITELIST).intersection(
            gateway.list_tools()
        )
        assert "dax_query_operations" not in gateway.list_tools()

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

    def test_schema_operation_whitelist_contains_only_list_and_get(self):
        assert set(SCHEMA_READ_OPERATION_WHITELIST) == {
            "table_operations",
            "column_operations",
            "measure_operations",
            "relationship_operations",
            "user_hierarchy_operations",
        }
        assert all(
            operations == {"List", "Get"}
            for operations in SCHEMA_READ_OPERATION_WHITELIST.values()
        )

    def test_dax_operation_whitelist_contains_only_execute(self):
        assert DAX_EXECUTE_OPERATION_WHITELIST == {"Execute"}

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

    @pytest.mark.asyncio
    async def test_schema_cache_singleflight_ttl_and_session_generation(self):
        client = FakeLocalMCPClient(schema_snapshot=_schema_snapshot())
        adapter = LocalMCPPowerBIAdapter(
            client=client,
            max_retries=0,
            schema_ttl_seconds=0.02,
        )

        schemas = await asyncio.gather(*(
            adapter.get_semantic_model_schema(TEST_MODEL_KEY)
            for _ in range(20)
        ))
        assert all(schema.key == TEST_MODEL_KEY for schema in schemas)
        assert client.schema_calls == 1

        await asyncio.sleep(0.03)
        await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        assert client.schema_calls == 2

        client.session_generation += 1
        await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        assert client.schema_calls == 3

    @pytest.mark.asyncio
    async def test_discovery_and_successful_probe_use_short_ttl_caches(self):
        client = FakeLocalMCPClient(
            discovery_snapshot=_discovery_snapshot(),
            probe_snapshot=_compatibility_snapshot(),
        )
        adapter = LocalMCPPowerBIAdapter(
            client=client,
            max_retries=0,
            discovery_ttl_seconds=0.02,
            probe_ttl_seconds=0.02,
        )

        await adapter.discover_semantic_models()
        await adapter.discover_semantic_models()
        assert client.discovery_calls == 1

        first = await adapter.probe_compatibility(TEST_MODEL_KEY)
        second = await adapter.probe_compatibility(TEST_MODEL_KEY)
        assert first.compatible is second.compatible is True
        assert client.probe_calls == [TEST_MODEL_KEY]

        await asyncio.sleep(0.03)
        await adapter.discover_semantic_models()
        await adapter.probe_compatibility(TEST_MODEL_KEY)
        assert client.discovery_calls == 2
        assert client.probe_calls == [TEST_MODEL_KEY, TEST_MODEL_KEY]

    @pytest.mark.asyncio
    async def test_discovery_failure_is_not_cached_and_retry_recovers(self):
        client = FakeLocalMCPClient(
            discovery_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.MCP_STARTUP,
                "local_mcp_server_exited",
            ),
        )
        adapter = _local_adapter(client)

        failed = await adapter.discover_semantic_models()
        assert failed.error_type == "semantic_model_discovery_unavailable"
        client.discovery_error = None
        client.discovery_snapshot = _discovery_snapshot()
        recovered = await adapter.discover_semantic_models()
        assert len(recovered.items) == 1
        assert client.discovery_calls == 2

    @pytest.mark.asyncio
    async def test_schema_cache_isolated_by_pbix_and_stale_validation_clears(self):
        second_key = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=2002,
            data_source="localhost:60002",
            start_time="2026-08-28T10:00:00+08:00",
        )
        client = FakeLocalMCPClient(schema_snapshot=_schema_snapshot())
        adapter = _local_adapter(client)

        await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        await adapter.get_semantic_model_schema(second_key)
        assert client.schema_keys == [TEST_MODEL_KEY, second_key]

        client.validation_error = LocalMCPConnectionError(
            LocalMCPErrorCategory.DESKTOP_STALE_INSTANCE,
            "desktop_selected_instance_stale",
        )
        with pytest.raises(PowerBIAdapterError) as exc_info:
            await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        assert exc_info.value.error_type == "DESKTOP_STALE_INSTANCE"

        client.validation_error = None
        await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        assert client.schema_keys == [TEST_MODEL_KEY, second_key, TEST_MODEL_KEY]

    @pytest.mark.asyncio
    async def test_member_cache_singleflight_expiry_and_no_query_result_cache(self):
        payload = {
            "success": True,
            "operation": "Execute",
            "data": {
                "success": True,
                "rowCount": 2,
                "columns": [{"name": "[MemberValue]", "ordinal": 0}],
                "rows": [
                    {"[MemberValue]": "A"},
                    {"[MemberValue]": "B"},
                ],
            },
        }
        client = FakeLocalMCPClient(
            schema_snapshot=_schema_snapshot(),
            dax_snapshot=_dax_snapshot(payload),
        )
        adapter = LocalMCPPowerBIAdapter(
            client=client,
            max_retries=0,
            member_ttl_seconds=0.02,
        )
        request = ColumnMembersRequest(
            semantic_model_key=TEST_MODEL_KEY,
            table_name="Products",
            field_name="Category",
            limit=2,
        )

        results = await asyncio.gather(*(adapter.get_column_members(request) for _ in range(20)))
        assert all(result.values == ["A", "B"] for result in results)
        assert client.schema_calls == 1
        assert client.dax_calls == 1

        await asyncio.sleep(0.03)
        await adapter.get_column_members(request)
        assert client.dax_calls == 2

        business_query = DAXRequest(
            semantic_model_key=TEST_MODEL_KEY,
            dax='EVALUATE ROW("Value", 1)',
        )
        client.dax_snapshot = _dax_snapshot(
            _successful_dax_payload(),
            request=business_query,
        )
        await adapter.execute_dax(business_query)
        await adapter.execute_dax(business_query)
        assert client.dax_calls == 4

    @pytest.mark.asyncio
    async def test_failed_schema_singleflight_does_not_poison_retry(self):
        client = FakeLocalMCPClient(
            schema_error=LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_READ_FAILED,
                "temporary_schema_failure",
            ),
        )
        adapter = _local_adapter(client)

        failed = await asyncio.gather(*(
            adapter.get_semantic_model_schema(TEST_MODEL_KEY)
            for _ in range(20)
        ), return_exceptions=True)
        assert all(isinstance(item, PowerBIAdapterError) for item in failed)
        assert client.schema_calls == 1

        client.schema_error = None
        client.schema_snapshot = _schema_snapshot()
        recovered = await adapter.get_semantic_model_schema(TEST_MODEL_KEY)
        assert recovered.key == TEST_MODEL_KEY
        assert client.schema_calls == 2

    @pytest.mark.asyncio
    async def test_adapter_shutdown_closes_application_client_once(self):
        client = FakeLocalMCPClient()
        adapter = _local_adapter(client)
        await adapter.aclose()
        assert client.close_calls == 1

    @pytest.mark.asyncio
    async def test_singleflight_waiter_cancellation_does_not_cancel_leader(self):
        singleflight: AsyncSingleFlight[str, int] = AsyncSingleFlight()
        release = asyncio.Event()
        calls = 0

        async def load() -> int:
            nonlocal calls
            calls += 1
            await release.wait()
            return 7

        cancelled_waiter = asyncio.create_task(singleflight.run("schema", load))
        surviving_waiter = asyncio.create_task(singleflight.run("schema", load))
        await asyncio.sleep(0)
        cancelled_waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_waiter
        release.set()
        assert await surviving_waiter == 7
        assert calls == 1

        assert await singleflight.run("schema", lambda: asyncio.sleep(0, result=8)) == 8
        assert calls == 1

    @pytest.mark.asyncio
    async def test_stdio_session_is_reused_and_closed_by_owner_task(self, monkeypatch):
        sessions: list[SimpleNamespace] = []

        class FakePersistentClient:
            protocol_version = "2025-11-25"

            def __init__(self, *_: object, **__: object) -> None:
                self.closed = False
                sessions.append(self)  # type: ignore[arg-type]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_: object) -> None:
                self.closed = True

            async def list_tools(self, *, cursor=None):
                return SimpleNamespace(tools=[], next_cursor=None)

        monkeypatch.setattr(local_mcp_module.shutil, "which", lambda _: "npx")
        monkeypatch.setattr(local_mcp_module, "stdio_client", lambda *_args, **_kwargs: object())
        monkeypatch.setattr(local_mcp_module, "Client", FakePersistentClient)
        client = PowerBILocalMCPClient(timeout_seconds=1)

        first = await client._run_session(lambda active, *_: asyncio.sleep(0, result=id(active)))
        second = await client._run_session(lambda active, *_: asyncio.sleep(0, result=id(active)))

        assert first == second
        assert len(sessions) == 1
        assert client.session_generation == 1
        assert sessions[0].closed is False
        await client.aclose()
        assert sessions[0].closed is True

    @pytest.mark.asyncio
    async def test_stdio_crash_invalidates_session_and_later_retry_recovers(self, monkeypatch):
        sessions: list[object] = []

        class FakePersistentClient:
            protocol_version = "2025-11-25"

            def __init__(self, *_: object, **__: object) -> None:
                sessions.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def list_tools(self, *, cursor=None):
                return SimpleNamespace(tools=[], next_cursor=None)

        class BrokenResourceError(Exception):
            pass

        async def crash(*_: object) -> None:
            raise BrokenResourceError()

        monkeypatch.setattr(local_mcp_module.shutil, "which", lambda _: "npx")
        monkeypatch.setattr(local_mcp_module, "stdio_client", lambda *_args, **_kwargs: object())
        monkeypatch.setattr(local_mcp_module, "Client", FakePersistentClient)
        client = PowerBILocalMCPClient(timeout_seconds=1)

        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._run_session(crash)
        assert exc_info.value.category == LocalMCPErrorCategory.MCP_STARTUP

        recovered = await client._run_session(
            lambda *_: asyncio.sleep(0, result="recovered")
        )
        assert recovered == "recovered"
        assert len(sessions) == 2
        assert client.session_generation == 2
        await client.aclose()

    def test_desktop_target_parsing_accepts_localhost_only(self):
        instance = {
            "parentProcessName": "PBIDesktop",
            "connectionString": "Data Source=localhost:54321;Application Name=test",
        }
        assert PowerBILocalMCPClient._desktop_data_source(instance) == "localhost:54321"
        assert PowerBILocalMCPClient._desktop_data_source(
            {"dataSource": "remote.example.com:443"}
        ) is None

    def test_desktop_display_name_removes_path_extension_and_app_suffix(self):
        instance = {
            "parentWindowTitle": (
                r"C:\Business\财务销售分析.pbix - Power BI Desktop"
            ),
            "connectionString": "Data Source=localhost:54321",
            "processId": 12345,
        }
        assert PowerBILocalMCPClient._desktop_display_name(instance) == "财务销售分析"
        assert PowerBILocalMCPClient._desktop_display_name(
            {"connectionString": "Data Source=localhost:54321"}
        ) == "当前已连接 Power BI Desktop 模型"

    def test_stdio_stderr_is_classified_without_leaking_raw_text(self):
        private_marker = "private-desktop-path-must-not-leak"
        classified = PowerBILocalMCPClient._classify_exception(
            RuntimeError("stdio closed"),
            diagnostic_text=f"npm ENOTFOUND registry; {private_marker}",
        )
        assert classified.category == LocalMCPErrorCategory.NETWORK
        assert classified.error_type == "local_mcp_package_network_error"
        assert private_marker not in str(classified)

    def test_exception_group_preserves_controlled_dax_error(self):
        classified = PowerBILocalMCPClient._classify_exception(
            ExceptionGroup(
                "stdio shutdown",
                [
                    LocalMCPConnectionError(
                        LocalMCPErrorCategory.DAX_ERROR,
                        "dax_execute_failed",
                    ),
                    RuntimeError("resource cleanup"),
                ],
            )
        )

        assert classified.category == LocalMCPErrorCategory.DAX_ERROR
        assert classified.error_type == "dax_execute_failed"

    def test_exception_group_preserves_multiple_desktop_error(self):
        classified = PowerBILocalMCPClient._classify_exception(
            ExceptionGroup(
                "stdio shutdown",
                [
                    LocalMCPConnectionError(
                        LocalMCPErrorCategory.DESKTOP_MULTIPLE_INSTANCES,
                        "desktop_instance_identity_not_unique",
                    ),
                    RuntimeError("resource cleanup"),
                ],
            )
        )

        assert classified.category == LocalMCPErrorCategory.DESKTOP_MULTIPLE_INSTANCES
        assert classified.error_type == "desktop_instance_identity_not_unique"

    def test_result_payload_prefers_structured_and_supports_inline_text(self):
        structured = SimpleNamespace(
            structured_content={"source": "structured"},
            content=[SimpleNamespace(text='{"source":"text"}')],
        )
        assert PowerBILocalMCPClient._result_payload(structured) == {
            "source": "structured"
        }

        inline = SimpleNamespace(
            structured_content=None,
            content=[SimpleNamespace(text='result: {"source":"inline"}')],
        )
        assert PowerBILocalMCPClient._result_payload(inline) == {
            "source": "inline"
        }

    @pytest.mark.asyncio
    async def test_stdio_client_logic_only_calls_connection_operations(self):
        client = PowerBILocalMCPClient()
        fake = FakeStdioMCPClient()

        diagnostics, connected = await client._connect_selected_desktop(
            fake,  # type: ignore[arg-type]
            "2026-07-28",
            _local_tools(),
            semantic_model_key=TEST_MODEL_KEY,
        )

        assert diagnostics.healthy is True
        assert connected.instance.semantic_model_key == TEST_MODEL_KEY
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

    @pytest.mark.asyncio
    async def test_stdio_client_reports_zero_desktop_instances_without_connecting(self):
        client = PowerBILocalMCPClient()
        fake = FakeStdioMCPClient(instances=[])

        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._enumerate_desktop_instances(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
            )

        assert exc_info.value.category == LocalMCPErrorCategory.DESKTOP_NOT_FOUND
        assert exc_info.value.error_type == "desktop_instance_not_found"
        assert [call[1]["request"]["operation"] for call in fake.calls] == [  # type: ignore[index]
            "ListLocalInstances",
        ]

    @pytest.mark.asyncio
    async def test_stdio_client_enumerates_multiple_desktop_instances(self):
        client = PowerBILocalMCPClient()
        second = {
            **TEST_INSTANCE,
            "processId": 1002,
            "port": 54322,
            "connectionString": "Data Source=localhost:54322",
            "startTime": "2026-08-24T09:01:00+08:00",
        }
        fake = FakeStdioMCPClient(instances=[dict(TEST_INSTANCE), second])

        diagnostics, instances = await client._enumerate_desktop_instances(
            fake,  # type: ignore[arg-type]
            "2025-11-25",
            _local_tools(),
        )

        assert diagnostics.desktop_detected is True
        assert len(instances) == 2
        assert len({item.semantic_model_key for item in instances}) == 2
        assert [call[1]["request"]["operation"] for call in fake.calls] == [  # type: ignore[index]
            "ListLocalInstances",
        ]
        assert "instances[0]" not in inspect.getsource(PowerBILocalMCPClient)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["schema", "dax"])
    async def test_schema_and_dax_sessions_connect_exact_selected_desktop(self, path: str):
        client = PowerBILocalMCPClient()
        second_start = "2026-08-24T09:01:00+08:00"
        second_key = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=1002,
            data_source="localhost:54322",
            start_time=second_start,
        )
        instances = [
            {
                **TEST_INSTANCE,
            },
            {
                **TEST_INSTANCE,
                "processId": 1002,
                "port": 54322,
                "parentProcessName": "PBIDesktop",
                "connectionString": "Data Source=localhost:54322",
                "startTime": second_start,
            },
        ]
        if path == "schema":
            fake = FakeSchemaStdioMCPClient(_schema_snapshot(second_key))
            fake.instances = instances
            call = client._read_schema_in_session(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                semantic_model_key=second_key,
            )
        else:
            fake = FakeDAXStdioMCPClient(_successful_dax_payload())
            fake.instances = instances
            call = client._execute_dax_in_session(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                request=DAXRequest(
                    semantic_model_key=second_key,
                    dax='EVALUATE ROW("Value", 1)',
                ),
            )

        snapshot = await call

        assert snapshot.diagnostics.connection is True
        connect_request = fake.calls[1][1]["request"]
        assert connect_request["operation"] == "Connect"  # type: ignore[index]
        assert connect_request["dataSource"] == "localhost:54322"  # type: ignore[index]

    @pytest.mark.asyncio
    async def test_selected_instance_disappearing_fails_closed(self):
        client = PowerBILocalMCPClient()
        fake = FakeDAXStdioMCPClient(_successful_dax_payload())
        stale_key = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=9999,
            data_source="localhost:59999",
            start_time="2026-08-24T08:00:00+08:00",
        )

        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._execute_dax_in_session(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                request=DAXRequest(
                    semantic_model_key=stale_key,
                    dax='EVALUATE ROW("Value", 1)',
                ),
            )

        assert exc_info.value.category == LocalMCPErrorCategory.DESKTOP_STALE_INSTANCE
        assert [call[1]["request"]["operation"] for call in fake.calls] == [  # type: ignore[index]
            "ListLocalInstances",
        ]

    @pytest.mark.asyncio
    async def test_stdio_schema_read_uses_one_connection_and_read_operations_only(self):
        client = PowerBILocalMCPClient()
        fake = FakeSchemaStdioMCPClient(_schema_snapshot())

        snapshot = await client._read_schema_in_session(
            fake,  # type: ignore[arg-type]
            "2025-11-25",
            _local_tools(),
            semantic_model_key=TEST_MODEL_KEY,
        )

        assert len(snapshot.tables) == 2
        assert len(snapshot.columns) == 6
        assert len(snapshot.measures) == 2
        assert len(snapshot.relationships) == 1
        assert len(snapshot.hierarchies) == 1
        assert [name for name, _ in fake.calls[:3]] == [
            "connection_operations",
            "connection_operations",
            "connection_operations",
        ]
        schema_calls = fake.calls[3:]
        assert len(schema_calls) == 10
        assert all(
            call[1]["request"]["operation"] in {"List", "Get"}  # type: ignore[index]
            for call in schema_calls
        )
        assert all(name != "dax_query_operations" for name, _ in fake.calls)

    @pytest.mark.asyncio
    async def test_stdio_schema_read_reports_missing_tool(self):
        client = PowerBILocalMCPClient()
        fake = FakeSchemaStdioMCPClient(_schema_snapshot())
        tools = tuple(
            tool for tool in _local_tools()
            if tool.name != "user_hierarchy_operations"
        )

        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._read_schema_in_session(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                tools,
                semantic_model_key=TEST_MODEL_KEY,
            )

        assert exc_info.value.category == LocalMCPErrorCategory.SCHEMA_TOOL_MISSING

    @pytest.mark.asyncio
    async def test_stdio_schema_read_reports_malformed_and_tool_errors(self):
        client = PowerBILocalMCPClient()
        malformed = FakeSchemaStdioMCPClient(
            _schema_snapshot(),
            malformed_tool="column_operations",
        )
        with pytest.raises(LocalMCPConnectionError) as malformed_info:
            await client._read_schema_in_session(
                malformed,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                semantic_model_key=TEST_MODEL_KEY,
            )
        assert (
            malformed_info.value.category
            == LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE
        )

        failed = FakeSchemaStdioMCPClient(
            _schema_snapshot(),
            error_tool="measure_operations",
        )
        with pytest.raises(LocalMCPConnectionError) as failed_info:
            await client._read_schema_in_session(
                failed,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                semantic_model_key=TEST_MODEL_KEY,
            )
        assert failed_info.value.category == LocalMCPErrorCategory.SCHEMA_READ_FAILED

        denied = FakeSchemaStdioMCPClient(
            _schema_snapshot(),
            permission_tool="measure_operations",
        )
        with pytest.raises(LocalMCPConnectionError) as denied_info:
            await client._read_schema_in_session(
                denied,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                semantic_model_key=TEST_MODEL_KEY,
            )
        assert (
            denied_info.value.category
            == LocalMCPErrorCategory.MCP_PERMISSION_DENIED
        )
        assert "private-path" not in str(denied_info.value)

    @pytest.mark.asyncio
    async def test_stdio_dax_execute_uses_inline_readonly_query_contract(self):
        client = PowerBILocalMCPClient()
        fake = FakeDAXStdioMCPClient(_successful_dax_payload())
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("First", 1, "Second", 2)',
            max_rows=25,
            timeout_seconds=18,
            request_id="stdio",
        )

        snapshot = await client._execute_dax_in_session(
            fake,  # type: ignore[arg-type]
            "2025-11-25",
            _local_tools(),
            request=request,
        )

        assert snapshot.request is request
        assert [name for name, _ in fake.calls[:3]] == [
            "connection_operations",
            "connection_operations",
            "connection_operations",
        ]
        assert len(fake.calls) == 4
        tool_name, arguments = fake.calls[-1]
        assert tool_name == "dax_query_operations"
        dax_request = arguments["request"]
        assert isinstance(dax_request, dict)
        assert dax_request == {
            "operation": "Execute",
            "connectionName": "safe-test-connection",
            "query": request.dax,
            "maxRows": 26,
            "timeoutSeconds": 18,
            "getExecutionMetrics": False,
            "executionMetricsOnly": False,
            "resultMode": "Inline",
        }

    @pytest.mark.asyncio
    async def test_stdio_dax_tool_error_is_classified_without_raw_leak(self):
        client = PowerBILocalMCPClient()
        fake = FakeDAXStdioMCPClient(
            {
                "success": False,
                "operation": "Execute",
                "message": "permission denied at private-path",
            },
            is_error=True,
        )
        request = DAXRequest(
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax="EVALUATE BAD_DAX",
        )

        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._execute_dax_in_session(
                fake,  # type: ignore[arg-type]
                "2025-11-25",
                _local_tools(),
                request=request,
            )

        assert exc_info.value.category == LocalMCPErrorCategory.DAX_PERMISSION_DENIED
        assert "private-path" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_compatibility_probe_verifies_schema_and_one_row_value(self):
        client = FakeLocalMCPClient(
            probe_snapshot=_compatibility_snapshot(),
        )

        probe = await _local_adapter(client).probe_compatibility(TEST_MODEL_KEY)

        assert probe.compatible is True
        assert probe.protocol_negotiated is True
        assert probe.required_tools_available is True
        assert probe.schema_read is True
        assert probe.dax_execute is True
        assert probe.row_data_verified is True
        assert client.probe_calls == [TEST_MODEL_KEY]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "safe_type"),
        [
            (
                LocalMCPConnectionError(
                    LocalMCPErrorCategory.MCP_PROTOCOL,
                    "required_future_capabilities_missing",
                ),
                "powerbi_mcp_protocol_incompatible",
            ),
            (
                LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_TOOL_MISSING,
                    "dax_execute_tool_missing",
                ),
                "powerbi_mcp_tool_missing",
            ),
            (
                LocalMCPConnectionError(
                    LocalMCPErrorCategory.MCP_TIMEOUT,
                    "private-timeout-detail",
                ),
                "powerbi_mcp_timeout",
            ),
            (
                LocalMCPConnectionError(
                    LocalMCPErrorCategory.NETWORK,
                    "private-network-detail",
                ),
                "powerbi_mcp_network_error",
            ),
            (
                LocalMCPConnectionError(
                    LocalMCPErrorCategory.MCP_PERMISSION_DENIED,
                    "private-permission-detail",
                ),
                "powerbi_permission_denied",
            ),
        ],
    )
    async def test_compatibility_probe_classifies_safe_failures(
        self,
        error: LocalMCPConnectionError,
        safe_type: str,
    ):
        probe = await _local_adapter(FakeLocalMCPClient(
            probe_error=error,
        )).probe_compatibility(TEST_MODEL_KEY)

        assert probe.compatible is False
        assert probe.error_type == safe_type
        assert "private" not in probe.model_dump_json()

    @pytest.mark.asyncio
    async def test_compatibility_probe_rejects_malformed_schema(self):
        snapshot = _compatibility_snapshot()
        malformed_schema = LocalMCPSchemaSnapshot(
            diagnostics=snapshot.schema.diagnostics,
            semantic_model_key=TEST_MODEL_KEY,
            tables=snapshot.schema.tables,
            columns=snapshot.schema.columns + ({
                "tableName": "Unknown",
                "name": "Ghost",
                "dataType": "String",
            },),
            measures=snapshot.schema.measures,
            relationships=snapshot.schema.relationships,
            hierarchies=snapshot.schema.hierarchies,
        )
        malformed = LocalMCPCompatibilitySnapshot(
            diagnostics=snapshot.diagnostics,
            schema=malformed_schema,
            dax=snapshot.dax,
        )

        probe = await _local_adapter(FakeLocalMCPClient(
            probe_snapshot=malformed,
        )).probe_compatibility(TEST_MODEL_KEY)

        assert probe.compatible is False
        assert probe.schema_read is False
        assert probe.error_type == "powerbi_schema_malformed"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("payload", "expected_type"),
        [
            (
                {
                    "data": {
                        "rowCount": 1,
                        "columns": [{"name": "[__pbiagent_probe]"}],
                    }
                },
                "powerbi_dax_probe_row_missing",
            ),
            (
                {
                    "data": {
                        "rowCount": 1,
                        "columns": [{"name": "[__pbiagent_probe]"}],
                        "rows": [{"[__pbiagent_probe]": 0}],
                    }
                },
                "powerbi_dax_probe_value_invalid",
            ),
        ],
    )
    async def test_compatibility_probe_rejects_missing_or_wrong_row_data(
        self,
        payload: dict[str, object],
        expected_type: str,
    ):
        snapshot = _compatibility_snapshot()
        malformed = LocalMCPCompatibilitySnapshot(
            diagnostics=snapshot.diagnostics,
            schema=snapshot.schema,
            dax=LocalMCPDAXSnapshot(
                diagnostics=snapshot.dax.diagnostics,
                request=snapshot.dax.request,
                wire_max_rows=snapshot.dax.wire_max_rows,
                payload=payload,
            ),
        )

        probe = await _local_adapter(FakeLocalMCPClient(
            probe_snapshot=malformed,
        )).probe_compatibility(TEST_MODEL_KEY)

        assert probe.compatible is False
        assert probe.error_type == expected_type

    @pytest.mark.asyncio
    async def test_explicit_truncation_metadata_maps_to_query_result(self):
        request = DAXRequest(
            semantic_model_key=TEST_MODEL_KEY,
            dax='EVALUATE ROW("Value", 1)',
            max_rows=10,
        )
        payload = {
            "data": {
                "rowCount": 1,
                "columns": [{"name": "[Value]"}],
                "rows": [{"[Value]": 1}],
                "isTruncated": True,
            }
        }

        result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(payload, request=request),
        )).execute_dax(request)

        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_explicit_complete_metadata_can_prove_exact_limit_complete(self):
        request = DAXRequest(
            semantic_model_key=TEST_MODEL_KEY,
            dax='EVALUATE ROW("Value", 1)',
            max_rows=1,
        )
        payload = {
            "data": {
                "rowCount": 1,
                "columns": [{"name": "[Value]"}],
                "rows": [{"[Value]": 1}],
                "isTruncated": False,
            }
        }

        result = await _local_adapter(FakeLocalMCPClient(
            dax_snapshot=_dax_snapshot(payload, request=request),
        )).execute_dax(request)

        assert result.truncated is False

    def test_opaque_instance_key_is_deterministic_and_connection_safe(self):
        repeated = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=1001,
            data_source="localhost:54321",
            start_time="2026-08-24T09:00:00+08:00",
        )
        changed = PowerBILocalMCPClient._desktop_semantic_model_key(
            process_id=1001,
            data_source="localhost:54322",
            start_time="2026-08-24T09:00:00+08:00",
        )

        assert repeated == TEST_MODEL_KEY
        assert changed != TEST_MODEL_KEY
        assert "54321" not in TEST_MODEL_KEY
        assert "1001" not in TEST_MODEL_KEY

    def test_official_mcp_v2_dependency_is_installed(self):
        assert version("mcp") == "2.0.0"
