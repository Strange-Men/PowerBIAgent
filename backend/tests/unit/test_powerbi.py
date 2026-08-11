"""Power BI Adapter 单元测试。"""

import ast
import inspect
from importlib.metadata import version
from types import SimpleNamespace

import pytest

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
    LocalMCPDiagnostics,
    LocalMCPDAXSnapshot,
    LocalMCPErrorCategory,
    LocalMCPPowerBIAdapter,
    LocalMCPSchemaSnapshot,
    PowerBILocalMCPClient,
)
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.schemas.data_contracts import (
    DAXRequest,
    SemanticModelSchema,
    UserContext,
)


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
    ) -> None:
        self.result = result
        self.error = error
        self.schema_snapshot = schema_snapshot
        self.schema_error = schema_error
        self.dax_snapshot = dax_snapshot
        self.dax_error = dax_error
        self.calls = 0
        self.schema_calls = 0
        self.dax_calls = 0

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result

    async def read_semantic_model_schema(self) -> LocalMCPSchemaSnapshot:
        self.schema_calls += 1
        if self.schema_error is not None:
            raise self.schema_error
        assert self.schema_snapshot is not None
        return self.schema_snapshot

    async def execute_dax(self, request: DAXRequest) -> LocalMCPDAXSnapshot:
        self.dax_calls += 1
        if self.dax_error is not None:
            raise self.dax_error
        assert self.dax_snapshot is not None
        return LocalMCPDAXSnapshot(
            diagnostics=self.dax_snapshot.diagnostics,
            request=request,
            payload=self.dax_snapshot.payload,
        )


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


class FakeSchemaStdioMCPClient(FakeStdioMCPClient):
    """Fake observed Local MCP List/Get response shapes for offline CI."""

    def __init__(
        self,
        snapshot: LocalMCPSchemaSnapshot,
        *,
        malformed_tool: str | None = None,
        error_tool: str | None = None,
    ) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.malformed_tool = malformed_tool
        self.error_tool = error_tool

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


def _schema_snapshot() -> LocalMCPSchemaSnapshot:
    diagnostics = _healthy_local_diagnostics()
    return LocalMCPSchemaSnapshot(
        diagnostics=diagnostics,
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
            semantic_model_key=LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
            dax='EVALUATE ROW("TestValue", 1)',
            request_id="request-123",
        ),
        payload=payload,
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

    @pytest.mark.asyncio
    async def test_stdio_schema_read_uses_one_connection_and_read_operations_only(self):
        client = PowerBILocalMCPClient()
        fake = FakeSchemaStdioMCPClient(_schema_snapshot())

        snapshot = await client._read_schema_in_session(
            fake,  # type: ignore[arg-type]
            "2025-11-25",
            _local_tools(),
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
            )
        assert failed_info.value.category == LocalMCPErrorCategory.SCHEMA_READ_FAILED

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
            "query": request.dax,
            "maxRows": 25,
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

    def test_official_mcp_v2_dependency_is_installed(self):
        assert version("mcp") == "2.0.0"
