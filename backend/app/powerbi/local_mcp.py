"""Power BI Local Modeling MCP Adapter and stdio client boundary.

The official Local MCP SDK, tool names, and raw payloads stay behind the
existing PowerBIAdapter boundary. Schema reads and DAX execution each use one
read-only stdio/Desktop connection lifecycle and explicit operation
whitelists.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.schemas.data_contracts import (
    ColumnMembersRequest,
    ColumnMembersResult,
    DAXRequest,
    ColumnSchema,
    HierarchySchema,
    MeasureSchema,
    PowerBIError,
    QueryResult,
    RelationshipSchema,
    SemanticModelSchema,
    TableSchema,
)


LOCAL_MCP_PACKAGE = "@microsoft/powerbi-modeling-mcp@0.5.0-beta.12"
M2_1_ALLOWED_TOOL_NAMES = frozenset({"connection_operations"})
LOCAL_DESKTOP_SEMANTIC_MODEL_KEY = "local_desktop_model"
MAX_DAX_RESULT_ROWS = 10_000
SCHEMA_READ_OPERATION_WHITELIST = {
    "table_operations": frozenset({"List", "Get"}),
    "column_operations": frozenset({"List", "Get"}),
    "measure_operations": frozenset({"List", "Get"}),
    "relationship_operations": frozenset({"List", "Get"}),
    "user_hierarchy_operations": frozenset({"List", "Get"}),
}
DAX_EXECUTE_OPERATION_WHITELIST = frozenset({"Execute"})
_SCHEMA_CAPABILITY_TOOLS = frozenset(SCHEMA_READ_OPERATION_WHITELIST)
_DAX_CAPABILITY_TOOL = "dax_query_operations"
_T = TypeVar("_T")


class LocalMCPErrorCategory(str, Enum):
    """Safe Local MCP failure categories."""

    LOCAL_PREREQUISITE = "LOCAL_PREREQUISITE"
    MCP_STARTUP = "MCP_STARTUP"
    MCP_PROTOCOL = "MCP_PROTOCOL"
    DESKTOP_NOT_FOUND = "DESKTOP_NOT_FOUND"
    DESKTOP_CONNECTION = "DESKTOP_CONNECTION"
    SCHEMA_TOOL_MISSING = "SCHEMA_TOOL_MISSING"
    SCHEMA_READ_FAILED = "SCHEMA_READ_FAILED"
    SCHEMA_MALFORMED_RESPONSE = "SCHEMA_MALFORMED_RESPONSE"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    DAX_TOOL_MISSING = "DAX_TOOL_MISSING"
    DAX_ERROR = "DAX_ERROR"
    DAX_TIMEOUT = "DAX_TIMEOUT"
    DAX_PERMISSION_DENIED = "DAX_PERMISSION_DENIED"
    DAX_MALFORMED_RESPONSE = "DAX_MALFORMED_RESPONSE"
    DAX_PREVIEW_ROW_DATA_MISSING = "DAX_PREVIEW_ROW_DATA_MISSING"
    DAX_OVERSIZED = "DAX_OVERSIZED"
    NETWORK = "NETWORK"
    BUG = "BUG"


@dataclass(frozen=True)
class DiscoveredLocalTool:
    """Static MCP tool metadata safe for tests and controlled diagnostics."""

    name: str
    description: str
    schema_type: str | None
    properties: tuple[str, ...]
    required: tuple[str, ...]

    def safe_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": self.schema_type,
                "properties": list(self.properties),
                "required": list(self.required),
            },
        }


@dataclass(frozen=True)
class LocalMCPDiagnostics:
    """Connection result containing no model identity, path, or business data."""

    server_started: bool = False
    protocol: str | None = None
    tools: tuple[DiscoveredLocalTool, ...] = ()
    desktop_detected: bool = False
    connection: bool = False
    schema_capability: bool = False
    dax_capability: bool = False
    readonly: bool = True
    error_category: LocalMCPErrorCategory | None = None
    error_type: str | None = None

    @property
    def healthy(self) -> bool:
        return (
            self.server_started
            and bool(self.protocol)
            and self.desktop_detected
            and self.connection
            and self.schema_capability
            and self.dax_capability
            and self.readonly
            and self.error_category is None
        )

    @classmethod
    def failure(
        cls,
        category: LocalMCPErrorCategory,
        error_type: str,
        **state: object,
    ) -> "LocalMCPDiagnostics":
        return cls(error_category=category, error_type=error_type, **state)

    def safe_dict(self) -> dict[str, object]:
        return {
            "desktop_detected": self.desktop_detected,
            "connection": self.connection,
            "protocol": self.protocol,
            "tool_count": len(self.tools),
            "schema_capability": self.schema_capability,
            "dax_capability": self.dax_capability,
            "readonly": self.readonly,
            "error_category": self.error_category.value if self.error_category else None,
            "error_type": self.error_type,
        }


class LocalMCPConnectionError(Exception):
    """Controlled local MCP exception with only a safe category and type."""

    def __init__(
        self,
        category: LocalMCPErrorCategory,
        error_type: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(f"{category.value}:{error_type}")
        self.category = category
        self.error_type = error_type
        self.retryable = retryable


class LocalMCPConnection(Protocol):
    """Injectable boundary used by the Adapter and offline tests."""

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        ...

    async def read_semantic_model_schema(self) -> "LocalMCPSchemaSnapshot":
        ...

    async def execute_dax(self, request: DAXRequest) -> "LocalMCPDAXSnapshot":
        ...


@dataclass(frozen=True)
class LocalMCPSchemaSnapshot:
    """Raw Local MCP schema payloads contained within the Adapter boundary."""

    diagnostics: LocalMCPDiagnostics
    tables: tuple[dict[str, object], ...]
    columns: tuple[dict[str, object], ...]
    measures: tuple[dict[str, object], ...]
    relationships: tuple[dict[str, object], ...]
    hierarchies: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class LocalMCPDAXSnapshot:
    """One raw Execute payload plus request context inside the Adapter boundary."""

    diagnostics: LocalMCPDiagnostics
    request: DAXRequest
    payload: dict[str, object]


class PowerBILocalMCPClient:
    """Minimal official MCP v2 stdio client for the Microsoft local server."""

    def __init__(
        self,
        *,
        executable: str = "npx",
        package: str = LOCAL_MCP_PACKAGE,
        readonly: bool = True,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not executable.strip() or not package.strip():
            raise ValueError("Local MCP executable and package are required")
        if not readonly:
            raise ValueError("M2.1 Local MCP must run in read-only mode")
        if timeout_seconds <= 0:
            raise ValueError("Local MCP timeout must be positive")
        self._executable = executable
        self._package = package
        self._readonly = readonly
        self._timeout_seconds = timeout_seconds

    async def connect_and_discover(self) -> LocalMCPDiagnostics:
        return await self._run_session(self._discover_and_connect_desktop)

    async def read_semantic_model_schema(self) -> LocalMCPSchemaSnapshot:
        """Read all supported schema objects in one stdio/Desktop connection."""
        return await self._run_session(self._read_schema_in_session)

    async def execute_dax(self, request: DAXRequest) -> LocalMCPDAXSnapshot:
        """Execute one read-only DAX query in one stdio/Desktop connection."""

        async def _execute(
            client: Client,
            protocol: str | None,
            tools: tuple[DiscoveredLocalTool, ...],
        ) -> LocalMCPDAXSnapshot:
            return await self._execute_dax_in_session(
                client,
                protocol,
                tools,
                request=request,
            )

        return await self._run_session(_execute)

    async def _run_session(
        self,
        handler: Callable[
            [Client, str | None, tuple[DiscoveredLocalTool, ...]],
            Awaitable[_T],
        ],
    ) -> _T:
        executable = shutil.which(self._executable)
        if executable is None:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "local_mcp_executable_missing",
            )

        args = ["-y", self._package, "--start", "--readonly"]
        parameters = StdioServerParameters(command=executable, args=args)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    transport = stdio_client(parameters, errlog=errlog)
                    async with Client(
                        transport,
                        raise_exceptions=True,
                        read_timeout_seconds=self._timeout_seconds,
                    ) as client:
                        tools = await self._list_all_tools(client)
                        protocol = (
                            str(client.protocol_version)
                            if client.protocol_version is not None
                            else None
                        )
                        return await handler(client, protocol, tools)
            except LocalMCPConnectionError:
                raise
            except Exception as exc:
                raise self._classify_exception(
                    exc,
                    diagnostic_text=self._read_diagnostic_text(errlog),
                ) from None

    async def _read_schema_in_session(
        self,
        client: Client,
        protocol: str | None,
        tools: tuple[DiscoveredLocalTool, ...],
    ) -> LocalMCPSchemaSnapshot:
        diagnostics = await self._discover_and_connect_desktop(
            client,
            protocol,
            tools,
            require_future_capabilities=False,
        )
        if diagnostics.error_category is not None:
            raise LocalMCPConnectionError(
                diagnostics.error_category,
                diagnostics.error_type or "desktop_connection_failed",
            )

        tool_names = {tool.name for tool in tools}
        missing = _SCHEMA_CAPABILITY_TOOLS - tool_names
        if missing:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_TOOL_MISSING,
                "required_schema_tool_missing",
            )

        details: dict[str, tuple[dict[str, object], ...]] = {}
        for tool_name in SCHEMA_READ_OPERATION_WHITELIST:
            list_payload = await self._call_schema_tool(
                client,
                tool_name,
                "List",
            )
            references = self._schema_references(tool_name, list_payload)
            if not references:
                details[tool_name] = ()
                continue
            get_payload = await self._call_schema_tool(
                client,
                tool_name,
                "Get",
                references=references,
            )
            details[tool_name] = self._schema_detail_records(
                get_payload,
                expected_count=len(references),
            )

        return LocalMCPSchemaSnapshot(
            diagnostics=diagnostics,
            tables=details["table_operations"],
            columns=details["column_operations"],
            measures=details["measure_operations"],
            relationships=details["relationship_operations"],
            hierarchies=details["user_hierarchy_operations"],
        )

    async def _execute_dax_in_session(
        self,
        client: Client,
        protocol: str | None,
        tools: tuple[DiscoveredLocalTool, ...],
        *,
        request: DAXRequest,
    ) -> LocalMCPDAXSnapshot:
        diagnostics = await self._discover_and_connect_desktop(
            client,
            protocol,
            tools,
            require_future_capabilities=False,
        )
        if diagnostics.error_category is not None:
            raise LocalMCPConnectionError(
                diagnostics.error_category,
                diagnostics.error_type or "desktop_connection_failed",
            )
        if _DAX_CAPABILITY_TOOL not in {tool.name for tool in tools}:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_TOOL_MISSING,
                "dax_execute_tool_missing",
            )

        operation = "Execute"
        if operation not in DAX_EXECUTE_OPERATION_WHITELIST:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_ERROR,
                "dax_operation_not_allowed",
            )
        arguments = {
            "request": {
                "operation": operation,
                "query": request.dax,
                "maxRows": request.max_rows,
                "timeoutSeconds": request.timeout_seconds,
                "getExecutionMetrics": False,
                "executionMetricsOnly": False,
                "resultMode": "Inline",
            }
        }
        try:
            result = await client.call_tool(
                _DAX_CAPABILITY_TOOL,
                arguments,
                read_timeout_seconds=float(request.timeout_seconds),
            )
        except TimeoutError:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_TIMEOUT,
                "dax_execute_timeout",
            ) from None

        payload = self._result_payload(result)
        if result.is_error or self._payload_failed(payload):
            raise self._classify_dax_tool_failure(payload)
        if not isinstance(payload, dict):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                "dax_payload_not_object",
            )
        return LocalMCPDAXSnapshot(
            diagnostics=diagnostics,
            request=request,
            payload=payload,
        )

    @staticmethod
    def _classify_dax_tool_failure(payload: object) -> LocalMCPConnectionError:
        """Classify a failed tool result without exposing its raw message."""
        try:
            text = json.dumps(payload, ensure_ascii=False).lower()
        except (TypeError, ValueError):
            text = ""
        if re.search(r"permission|unauthori[sz]ed|forbidden|access denied", text):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_PERMISSION_DENIED,
                "dax_permission_denied",
            )
        if re.search(r"timed?\s*out|timeout", text):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_TIMEOUT,
                "dax_execute_timeout",
            )
        return LocalMCPConnectionError(
            LocalMCPErrorCategory.DAX_ERROR,
            "dax_execute_failed",
        )

    async def _discover_and_connect_desktop(
        self,
        client: Client,
        protocol: str | None,
        tools: tuple[DiscoveredLocalTool, ...],
        *,
        require_future_capabilities: bool = True,
    ) -> LocalMCPDiagnostics:
        tool_names = {tool.name for tool in tools}
        state = {
            "server_started": True,
            "protocol": protocol,
            "tools": tools,
            "schema_capability": _SCHEMA_CAPABILITY_TOOLS.issubset(tool_names),
            "dax_capability": _DAX_CAPABILITY_TOOL in tool_names,
            "readonly": self._readonly,
        }
        if not protocol:
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.MCP_PROTOCOL,
                "protocol_not_negotiated",
                **state,
            )
        if not M2_1_ALLOWED_TOOL_NAMES.issubset(tool_names):
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.MCP_PROTOCOL,
                "connection_tool_missing",
                **state,
            )
        if require_future_capabilities and (
            not state["schema_capability"] or not state["dax_capability"]
        ):
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.MCP_PROTOCOL,
                "required_future_capabilities_missing",
                **state,
            )

        list_result = await client.call_tool(
            "connection_operations",
            {"request": {"operation": "ListLocalInstances"}},
            read_timeout_seconds=self._timeout_seconds,
        )
        if list_result.is_error:
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
                "desktop_discovery_failed",
                **state,
            )
        instances = self._find_desktop_instances(self._result_payload(list_result))
        if not instances:
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
                "desktop_instance_not_found",
                **state,
            )

        data_source = self._desktop_data_source(instances[0])
        if data_source is None:
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.DESKTOP_CONNECTION,
                "desktop_connection_target_missing",
                desktop_detected=True,
                **state,
            )
        connect_result = await client.call_tool(
            "connection_operations",
            {"request": {"operation": "Connect", "dataSource": data_source}},
            read_timeout_seconds=self._timeout_seconds,
        )
        connect_payload = self._result_payload(connect_result)
        if connect_result.is_error or self._payload_failed(connect_payload):
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.DESKTOP_CONNECTION,
                "desktop_connection_failed",
                desktop_detected=True,
                **state,
            )

        verification_result = await client.call_tool(
            "connection_operations",
            {"request": {"operation": "ListConnections"}},
            read_timeout_seconds=self._timeout_seconds,
        )
        verified = (
            not verification_result.is_error
            and bool(
                self._find_connection_records(
                    self._result_payload(verification_result)
                )
            )
        )
        if not verified:
            return LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.DESKTOP_CONNECTION,
                "desktop_connection_not_verified",
                desktop_detected=True,
                **state,
            )
        return LocalMCPDiagnostics(
            desktop_detected=True,
            connection=True,
            **state,
        )

    async def _call_schema_tool(
        self,
        client: Client,
        tool_name: str,
        operation: str,
        **request: object,
    ) -> dict[str, object]:
        allowed_operations = SCHEMA_READ_OPERATION_WHITELIST.get(tool_name)
        if allowed_operations is None:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_TOOL_MISSING,
                "schema_tool_not_allowed",
            )
        if operation not in allowed_operations:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_READ_FAILED,
                "schema_operation_not_allowed",
            )

        result = await client.call_tool(
            tool_name,
            {"request": {"operation": operation, **request}},
            read_timeout_seconds=self._timeout_seconds,
        )
        payload = self._result_payload(result)
        if result.is_error or self._payload_failed(payload):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_READ_FAILED,
                "schema_tool_call_failed",
            )
        if not isinstance(payload, dict):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_payload_not_object",
            )
        return payload

    @classmethod
    def _schema_references(
        cls,
        tool_name: str,
        payload: dict[str, object],
    ) -> list[dict[str, str]]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_list_data_missing",
            )
        if not all(isinstance(item, dict) for item in data):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_list_item_malformed",
            )

        if tool_name == "table_operations":
            return [
                {"name": cls._required_text(item, "name")}
                for item in data
            ]
        if tool_name in {"column_operations", "measure_operations"}:
            child_key = (
                "columns" if tool_name == "column_operations" else "measures"
            )
            references: list[dict[str, str]] = []
            for group in data:
                table_name = cls._required_text(group, "tableName")
                children = group.get(child_key)
                if not isinstance(children, list) or not all(
                    isinstance(item, dict) for item in children
                ):
                    raise LocalMCPConnectionError(
                        LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                        "schema_group_items_malformed",
                    )
                references.extend(
                    {
                        "tableName": table_name,
                        "name": cls._required_text(item, "name"),
                    }
                    for item in children
                )
            return references
        if tool_name == "relationship_operations":
            return [
                {"name": cls._required_text(item, "name")}
                for item in data
            ]
        if tool_name == "user_hierarchy_operations":
            references = []
            for group in data:
                hierarchy = group.get("hierarchy")
                if not isinstance(hierarchy, dict):
                    raise LocalMCPConnectionError(
                        LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                        "schema_hierarchy_malformed",
                    )
                references.append(
                    {
                        "tableName": cls._required_text(group, "tableName"),
                        "hierarchyName": cls._required_text(hierarchy, "name"),
                    }
                )
            return references
        raise LocalMCPConnectionError(
            LocalMCPErrorCategory.SCHEMA_TOOL_MISSING,
            "schema_tool_not_allowed",
        )

    @classmethod
    def _schema_detail_records(
        cls,
        payload: dict[str, object],
        *,
        expected_count: int,
    ) -> tuple[dict[str, object], ...]:
        results = payload.get("results")
        if not isinstance(results, list) or not all(
            isinstance(item, dict) for item in results
        ):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_get_results_missing",
            )

        summary = payload.get("summary")
        if isinstance(summary, dict):
            failure_count = summary.get("failureCount")
            if isinstance(failure_count, int) and failure_count:
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.SCHEMA_READ_FAILED,
                    "schema_get_item_failed",
                )

        records: list[dict[str, object]] = []
        for item in results:
            record = item.get("data")
            if not isinstance(record, dict):
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                    "schema_get_item_data_missing",
                )
            records.append(record)
        if len(records) != expected_count:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_get_item_count_mismatch",
            )
        return tuple(records)

    @staticmethod
    def _required_text(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.SCHEMA_MALFORMED_RESPONSE,
                "schema_required_field_missing",
            )
        return value.strip()

    async def _list_all_tools(self, client: Client) -> tuple[DiscoveredLocalTool, ...]:
        tools: list[DiscoveredLocalTool] = []
        cursor: str | None = None
        for _ in range(100):
            page = await client.list_tools(cursor=cursor)
            tools.extend(self._summarize_tool(tool) for tool in page.tools)
            cursor = page.next_cursor
            if cursor is None:
                return tuple(tools)
        raise LocalMCPConnectionError(
            LocalMCPErrorCategory.MCP_PROTOCOL,
            "tool_pagination_limit",
        )

    @staticmethod
    def _summarize_tool(tool: Any) -> DiscoveredLocalTool:
        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        description = re.sub(r"\s+", " ", str(tool.description or "")).strip()[:160]
        return DiscoveredLocalTool(
            name=str(tool.name),
            description=description,
            schema_type=(
                str(schema["type"])
                if schema.get("type") is not None
                else None
            ),
            properties=(
                tuple(sorted(str(name) for name in properties))
                if isinstance(properties, dict)
                else ()
            ),
            required=(
                tuple(sorted(str(name) for name in required))
                if isinstance(required, list)
                else ()
            ),
        )

    @staticmethod
    def _result_payload(result: Any) -> object:
        if isinstance(result.structured_content, (dict, list)):
            return result.structured_content
        for block in result.content:
            text = getattr(block, "text", None)
            if not isinstance(text, str):
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                for opening, closing in (("{", "}"), ("[", "]")):
                    start = text.find(opening)
                    end = text.rfind(closing)
                    if start >= 0 and end > start:
                        try:
                            return json.loads(text[start : end + 1])
                        except json.JSONDecodeError:
                            pass
        return None

    @classmethod
    def _find_desktop_instances(cls, payload: object) -> list[dict[str, object]]:
        instances: list[dict[str, object]] = []
        if isinstance(payload, list):
            for value in payload:
                instances.extend(cls._find_desktop_instances(value))
            return instances
        if not isinstance(payload, dict):
            return instances

        lowered = {str(key).lower(): value for key, value in payload.items()}
        has_target = any(
            key in lowered
            for key in ("port", "datasource", "connectionstring")
        )
        process_name = str(lowered.get("parentprocessname", "")).lower()
        if has_target and (not process_name or "pbidesktop" in process_name):
            instances.append(payload)
        for value in payload.values():
            if isinstance(value, (dict, list)):
                instances.extend(cls._find_desktop_instances(value))
        return instances

    @staticmethod
    def _desktop_data_source(instance: dict[str, object]) -> str | None:
        lowered = {str(key).lower(): value for key, value in instance.items()}
        candidate = lowered.get("datasource")
        if not isinstance(candidate, str):
            connection_string = lowered.get("connectionstring")
            if isinstance(connection_string, str):
                match = re.search(
                    r"(?i)\bdata\s+source\s*=\s*([^;]+)",
                    connection_string,
                )
                candidate = match.group(1).strip() if match else None
        if not isinstance(candidate, str):
            port = lowered.get("port")
            if isinstance(port, int) or (isinstance(port, str) and port.isdigit()):
                candidate = f"localhost:{port}"
        if not isinstance(candidate, str):
            return None
        candidate = candidate.strip()
        if not re.fullmatch(r"(?:localhost|127\.0\.0\.1):\d{1,5}", candidate):
            return None
        return candidate

    @classmethod
    def _payload_failed(cls, payload: object) -> bool:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if str(key).lower() == "success" and isinstance(value, bool):
                    return not value
            return any(cls._payload_failed(value) for value in payload.values())
        if isinstance(payload, list):
            return any(cls._payload_failed(value) for value in payload)
        return False

    @classmethod
    def _find_connection_records(cls, payload: object) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        if isinstance(payload, list):
            for value in payload:
                records.extend(cls._find_connection_records(value))
            return records
        if not isinstance(payload, dict):
            return records
        if any(str(key).lower() == "connectionname" for key in payload):
            records.append(payload)
        for value in payload.values():
            if isinstance(value, (dict, list)):
                records.extend(cls._find_connection_records(value))
        return records

    @staticmethod
    def _read_diagnostic_text(errlog: Any) -> str:
        """Read bounded ephemeral stderr for classification; never return it to callers."""
        try:
            errlog.flush()
            errlog.seek(0)
            return str(errlog.read(64 * 1024))
        except (OSError, UnicodeError):
            return ""

    @classmethod
    def _classify_exception(
        cls,
        exc: Exception,
        *,
        diagnostic_text: str = "",
    ) -> LocalMCPConnectionError:
        if isinstance(exc, BaseExceptionGroup):
            classified = [
                cls._classify_exception(
                    nested,
                    diagnostic_text=diagnostic_text,
                )
                for nested in exc.exceptions
                if isinstance(nested, Exception)
            ]
            for category in (
                LocalMCPErrorCategory.NETWORK,
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                LocalMCPErrorCategory.MCP_PROTOCOL,
                LocalMCPErrorCategory.MCP_STARTUP,
                LocalMCPErrorCategory.DAX_PERMISSION_DENIED,
                LocalMCPErrorCategory.DAX_TIMEOUT,
                LocalMCPErrorCategory.DAX_ERROR,
                LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                LocalMCPErrorCategory.DAX_PREVIEW_ROW_DATA_MISSING,
                LocalMCPErrorCategory.DAX_OVERSIZED,
            ):
                match = next((item for item in classified if item.category == category), None)
                if match is not None:
                    return match
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.BUG,
                "exception_group",
            )
        if isinstance(exc, LocalMCPConnectionError):
            return exc
        text = f"{exc}\n{diagnostic_text}".lower()
        if re.search(r"enotfound|etimedout|dns|proxy|tls|registry|network", text):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.NETWORK,
                "local_mcp_package_network_error",
                retryable=True,
            )
        if "node" in text and re.search(r"version|required|not found", text):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "node_runtime_unavailable",
            )
        if isinstance(exc, (FileNotFoundError, PermissionError)):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "local_mcp_executable_unavailable",
            )
        if isinstance(exc, TimeoutError):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.MCP_STARTUP,
                "local_mcp_startup_timeout",
            )
        if isinstance(exc, MCPError):
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.MCP_PROTOCOL,
                "mcp_protocol_error",
            )
        if type(exc).__name__ in {
            "BrokenResourceError",
            "ClosedResourceError",
            "EndOfStream",
        }:
            return LocalMCPConnectionError(
                LocalMCPErrorCategory.MCP_STARTUP,
                "local_mcp_server_exited",
            )
        return LocalMCPConnectionError(
            LocalMCPErrorCategory.BUG,
            type(exc).__name__,
        )


class LocalMCPPowerBIAdapter(PowerBIAdapter):
    """Local MCP provider behind the existing PowerBIAdapter boundary."""

    PROVIDER_NAME = "local_mcp"

    def __init__(
        self,
        *,
        executable: str = "npx",
        package: str = LOCAL_MCP_PACKAGE,
        semantic_model_key: str = LOCAL_DESKTOP_SEMANTIC_MODEL_KEY,
        readonly: bool = True,
        timeout: float = 120.0,
        max_retries: int = 1,
        client: LocalMCPConnection | None = None,
    ) -> None:
        self._executable = executable
        self._package = package
        self._semantic_model_key = semantic_model_key.strip()
        self._readonly = readonly
        self._timeout = timeout
        self._max_retries = min(max(max_retries, 0), 1)
        self._client = client
        self._last_diagnostics = LocalMCPDiagnostics.failure(
            LocalMCPErrorCategory.LOCAL_PREREQUISITE,
            "health_check_not_run",
            readonly=readonly,
        )

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def last_diagnostics(self) -> LocalMCPDiagnostics:
        return self._last_diagnostics

    async def health_check(self) -> bool:
        if not self._readonly:
            self._last_diagnostics = LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "readonly_required",
                readonly=False,
            )
            return False
        try:
            client = self._ensure_client()
        except ValueError:
            self._last_diagnostics = LocalMCPDiagnostics.failure(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "invalid_local_mcp_configuration",
                readonly=self._readonly,
            )
            return False

        for attempt in range(self._max_retries + 1):
            try:
                diagnostics = await client.connect_and_discover()
            except LocalMCPConnectionError as exc:
                diagnostics = LocalMCPDiagnostics.failure(
                    exc.category,
                    exc.error_type,
                    readonly=self._readonly,
                )
            self._last_diagnostics = diagnostics
            if diagnostics.healthy:
                return True
            if (
                diagnostics.error_category == LocalMCPErrorCategory.NETWORK
                and attempt < self._max_retries
            ):
                await asyncio.sleep(0.25)
                continue
            return False
        return False

    async def get_semantic_model_schema(
        self,
        semantic_model_key: str,
    ) -> SemanticModelSchema:
        if not self._readonly:
            raise PowerBIAdapterError(
                "Local MCP schema access requires read-only mode",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.SCHEMA_VALIDATION_FAILED.value,
            )
        if (
            not semantic_model_key.strip()
            or semantic_model_key != self._semantic_model_key
        ):
            raise PowerBIAdapterError(
                "Semantic model key is not configured for Local MCP",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.SCHEMA_VALIDATION_FAILED.value,
            )

        try:
            client = self._ensure_client()
        except ValueError:
            raise PowerBIAdapterError(
                "Local MCP configuration is invalid",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.LOCAL_PREREQUISITE.value,
            ) from None

        for attempt in range(self._max_retries + 1):
            try:
                snapshot = await client.read_semantic_model_schema()
                self._last_diagnostics = snapshot.diagnostics
                return self._map_schema(snapshot, semantic_model_key)
            except LocalMCPConnectionError as exc:
                self._last_diagnostics = LocalMCPDiagnostics.failure(
                    exc.category,
                    exc.error_type,
                    readonly=self._readonly,
                )
                if (
                    exc.category == LocalMCPErrorCategory.NETWORK
                    and attempt < self._max_retries
                ):
                    await asyncio.sleep(0.25)
                    continue
                raise self._schema_adapter_error(exc) from None
            except (ValidationError, ValueError, TypeError):
                raise PowerBIAdapterError(
                    "Local MCP schema validation failed",
                    provider=self.PROVIDER_NAME,
                    error_type=(
                        LocalMCPErrorCategory.SCHEMA_VALIDATION_FAILED.value
                    ),
                ) from None
        raise PowerBIAdapterError(
            "Local MCP schema read failed",
            provider=self.PROVIDER_NAME,
            error_type=LocalMCPErrorCategory.SCHEMA_READ_FAILED.value,
        )

    def _ensure_client(self) -> LocalMCPConnection:
        if self._client is None:
            self._client = PowerBILocalMCPClient(
                executable=self._executable,
                package=self._package,
                readonly=self._readonly,
                timeout_seconds=self._timeout,
            )
        return self._client

    @classmethod
    def _schema_adapter_error(
        cls,
        exc: LocalMCPConnectionError,
    ) -> PowerBIAdapterError:
        return PowerBIAdapterError(
            f"Local MCP schema read failed ({exc.error_type})",
            provider=cls.PROVIDER_NAME,
            retryable=exc.retryable,
            error_type=exc.category.value,
        )

    @classmethod
    def _map_schema(
        cls,
        snapshot: LocalMCPSchemaSnapshot,
        semantic_model_key: str,
    ) -> SemanticModelSchema:
        tables_by_name: dict[str, TableSchema] = {}
        for raw_table in snapshot.tables:
            name = cls._required_schema_text(raw_table, "name")
            if name in tables_by_name:
                raise ValueError("duplicate table")
            tables_by_name[name] = TableSchema(
                name=name,
                is_hidden=cls._optional_bool(raw_table, "isHidden"),
                is_system_managed=cls._optional_bool(
                    raw_table,
                    "systemManaged",
                ),
                description=cls._optional_text(raw_table, "description"),
            )

        if not tables_by_name:
            raise ValueError("schema contains no tables")

        seen_columns: set[tuple[str, str]] = set()
        for raw_column in snapshot.columns:
            table_name = cls._required_schema_text(raw_column, "tableName")
            name = cls._required_schema_text(raw_column, "name")
            key = (table_name, name)
            if table_name not in tables_by_name or key in seen_columns:
                raise ValueError("invalid column ownership")
            seen_columns.add(key)
            tables_by_name[table_name].columns.append(ColumnSchema(
                name=name,
                data_type=cls._required_schema_text(raw_column, "dataType"),
                is_hidden=cls._optional_bool(raw_column, "isHidden"),
                description=cls._optional_text(raw_column, "description"),
            ))

        seen_measures: set[tuple[str, str]] = set()
        for raw_measure in snapshot.measures:
            table_name = cls._required_schema_text(raw_measure, "tableName")
            name = cls._required_schema_text(raw_measure, "name")
            key = (table_name, name)
            if table_name not in tables_by_name or key in seen_measures:
                raise ValueError("invalid measure ownership")
            seen_measures.add(key)
            tables_by_name[table_name].measures.append(MeasureSchema(
                name=name,
                expression=cls._required_schema_text(
                    raw_measure,
                    "expression",
                ),
                data_type=cls._required_schema_text(raw_measure, "dataType"),
                is_hidden=cls._optional_bool(raw_measure, "isHidden"),
                description=cls._optional_text(raw_measure, "description"),
            ))

        seen_hierarchies: set[tuple[str, str]] = set()
        for raw_hierarchy in snapshot.hierarchies:
            table_name = cls._required_schema_text(raw_hierarchy, "tableName")
            name = cls._required_schema_text(raw_hierarchy, "name")
            key = (table_name, name)
            levels = raw_hierarchy.get("levels")
            if (
                table_name not in tables_by_name
                or key in seen_hierarchies
                or not isinstance(levels, list)
                or not all(isinstance(level, dict) for level in levels)
            ):
                raise ValueError("invalid hierarchy")
            seen_hierarchies.add(key)
            tables_by_name[table_name].hierarchies.append(HierarchySchema(
                name=name,
                levels=[
                    cls._required_schema_text(level, "name")
                    for level in levels
                ],
            ))

        relationships: list[RelationshipSchema] = []
        seen_relationships: set[tuple[str, str, str, str]] = set()
        for raw_relationship in snapshot.relationships:
            from_table = cls._required_schema_text(raw_relationship, "fromTable")
            from_column = cls._required_schema_text(raw_relationship, "fromColumn")
            to_table = cls._required_schema_text(raw_relationship, "toTable")
            to_column = cls._required_schema_text(raw_relationship, "toColumn")
            key = (from_table, from_column, to_table, to_column)
            if (
                from_table not in tables_by_name
                or to_table not in tables_by_name
                or (from_table, from_column) not in seen_columns
                or (to_table, to_column) not in seen_columns
                or key in seen_relationships
            ):
                raise ValueError("invalid relationship")
            seen_relationships.add(key)
            relationships.append(RelationshipSchema(
                from_table=from_table,
                from_column=from_column,
                to_table=to_table,
                to_column=to_column,
                is_active=cls._optional_bool(
                    raw_relationship,
                    "isActive",
                    default=True,
                ),
                from_cardinality=cls._optional_text(
                    raw_relationship,
                    "fromCardinality",
                ),
                to_cardinality=cls._optional_text(
                    raw_relationship,
                    "toCardinality",
                ),
            ))

        return SemanticModelSchema(
            name=semantic_model_key,
            key=semantic_model_key,
            tables=list(tables_by_name.values()),
            relationships=relationships,
        )

    @staticmethod
    def _required_schema_text(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("required schema field missing")
        return value.strip()

    @staticmethod
    def _optional_text(
        record: dict[str, object],
        field: str,
    ) -> str | None:
        value = record.get(field)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("optional schema text malformed")
        value = value.strip()
        return value or None

    @staticmethod
    def _optional_bool(
        record: dict[str, object],
        field: str,
        *,
        default: bool = False,
    ) -> bool:
        value = record.get(field, default)
        if not isinstance(value, bool):
            raise ValueError("optional schema boolean malformed")
        return value

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        if not self._readonly:
            raise PowerBIAdapterError(
                "Local MCP DAX execution requires read-only mode",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_ERROR.value,
            )
        if (
            not request.semantic_model_key.strip()
            or request.semantic_model_key != self._semantic_model_key
        ):
            raise PowerBIAdapterError(
                "Semantic model key is not configured for Local MCP",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_ERROR.value,
            )
        if request.max_rows > MAX_DAX_RESULT_ROWS:
            error = await self.normalize_error(LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_OVERSIZED,
                "dax_max_rows_exceeds_limit",
            ))
            return self._query_error_result(request, error, truncated=True)

        try:
            client = self._ensure_client()
        except ValueError:
            error = await self.normalize_error(LocalMCPConnectionError(
                LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                "invalid_local_mcp_configuration",
            ))
            return self._query_error_result(request, error)

        for attempt in range(self._max_retries + 1):
            try:
                snapshot = await client.execute_dax(request)
                self._last_diagnostics = snapshot.diagnostics
                return await self.normalize_result(snapshot)
            except LocalMCPConnectionError as exc:
                self._last_diagnostics = LocalMCPDiagnostics.failure(
                    exc.category,
                    exc.error_type,
                    readonly=self._readonly,
                )
                if (
                    exc.category == LocalMCPErrorCategory.NETWORK
                    and attempt < self._max_retries
                ):
                    await asyncio.sleep(0.25)
                    continue
                error = await self.normalize_error(exc)
                return self._query_error_result(request, error)
            except (ValidationError, ValueError, TypeError):
                error = await self.normalize_error(LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                    "dax_result_validation_failed",
                ))
                return self._query_error_result(request, error)

        error = await self.normalize_error(LocalMCPConnectionError(
            LocalMCPErrorCategory.DAX_ERROR,
            "dax_execute_failed",
        ))
        return self._query_error_result(request, error)

    async def get_column_members(
        self, request: ColumnMembersRequest
    ) -> ColumnMembersResult:
        """Execute one adapter-owned, bounded, read-only distinct-member DAX."""
        if request.semantic_model_key != self._semantic_model_key:
            raise PowerBIAdapterError(
                "Semantic model key is not configured for Local MCP",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_ERROR.value,
            )
        schema = await self.get_semantic_model_schema(request.semantic_model_key)
        table = next(
            (
                item for item in schema.tables
                if item.name == request.table_name
                and not item.is_hidden
                and not item.is_system_managed
            ),
            None,
        )
        if table is None or not any(
            item.name == request.field_name and not item.is_hidden
            for item in table.columns
        ):
            raise PowerBIAdapterError(
                "Member lookup field is not a visible runtime column",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_ERROR.value,
            )

        table_name = request.table_name.replace("'", "''")
        field_name = request.field_name.replace("]", "]]")
        dax_request = DAXRequest(
            semantic_model_key=request.semantic_model_key,
            dax=(
                f"EVALUATE TOPN({request.limit + 1}, "
                f"DISTINCT(SELECTCOLUMNS('{table_name}', "
                f'\"MemberValue\", \'{table_name}\'[{field_name}])), '
                f"[MemberValue], ASC)"
            ),
            max_rows=request.limit + 1,
            timeout_seconds=min(int(self._timeout), 300),
        )
        query_result = await self.execute_dax(dax_request)
        if query_result.error is not None:
            raise PowerBIAdapterError(
                "Local MCP bounded member lookup failed",
                provider=self.PROVIDER_NAME,
                retryable=query_result.error.retryable,
                error_type=query_result.error.type,
            )
        if len(query_result.columns) != 1:
            raise PowerBIAdapterError(
                "Local MCP bounded member lookup returned an invalid shape",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE.value,
            )
        raw_values = [row[0] for row in query_result.rows]
        return ColumnMembersResult(
            semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,
            field_name=request.field_name,
            values=raw_values[:request.limit],
            truncated=len(raw_values) > request.limit,
            source_mode="real",
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        if not isinstance(raw, LocalMCPDAXSnapshot):
            raise PowerBIAdapterError(
                "Local MCP query response is malformed",
                provider=self.PROVIDER_NAME,
                error_type=LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE.value,
            )
        try:
            return self._map_dax_result(raw)
        except LocalMCPConnectionError as exc:
            error = await self.normalize_error(exc)
            return self._query_error_result(raw.request, error)

    async def normalize_error(self, raw: object) -> PowerBIError:
        if isinstance(raw, PowerBIError):
            return raw
        if not isinstance(raw, LocalMCPConnectionError):
            return PowerBIError(
                type="malformed_response",
                message="Power BI returned an unrecognized query response",
                retryable=False,
            )

        mapping: dict[LocalMCPErrorCategory, tuple[str, str, bool]] = {
            LocalMCPErrorCategory.DAX_TIMEOUT: (
                "timeout",
                "Power BI DAX query timed out",
                False,
            ),
            LocalMCPErrorCategory.DAX_PERMISSION_DENIED: (
                "permission_denied",
                "Power BI query permission denied",
                False,
            ),
            LocalMCPErrorCategory.DAX_ERROR: (
                "dax_error",
                "Power BI rejected the DAX query",
                False,
            ),
            LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE: (
                "malformed_response",
                "Power BI returned an unrecognized query response",
                False,
            ),
            LocalMCPErrorCategory.DAX_PREVIEW_ROW_DATA_MISSING: (
                "preview_row_data_missing",
                "Power BI MCP did not return query row data",
                False,
            ),
            LocalMCPErrorCategory.DAX_OVERSIZED: (
                "oversized",
                "Power BI query exceeds the allowed row limit",
                False,
            ),
            LocalMCPErrorCategory.MCP_PROTOCOL: (
                "mcp_protocol",
                "Power BI MCP protocol error",
                False,
            ),
            LocalMCPErrorCategory.DAX_TOOL_MISSING: (
                "mcp_protocol",
                "Power BI MCP DAX capability is unavailable",
                False,
            ),
            LocalMCPErrorCategory.NETWORK: (
                "connection_error",
                "Power BI MCP network connection failed",
                True,
            ),
        }
        connection_categories = {
            LocalMCPErrorCategory.LOCAL_PREREQUISITE,
            LocalMCPErrorCategory.MCP_STARTUP,
            LocalMCPErrorCategory.DESKTOP_NOT_FOUND,
            LocalMCPErrorCategory.DESKTOP_CONNECTION,
        }
        if raw.category in connection_categories:
            error_type, message, retryable = (
                "connection_error",
                "Power BI Desktop connection failed",
                False,
            )
        else:
            error_type, message, retryable = mapping.get(
                raw.category,
                (
                    "malformed_response",
                    "Power BI returned an unrecognized query response",
                    False,
                ),
            )
        return PowerBIError(
            type=error_type,
            message=message,
            retryable=retryable and raw.retryable,
        )

    @classmethod
    def _map_dax_result(cls, snapshot: LocalMCPDAXSnapshot) -> QueryResult:
        payload = snapshot.payload
        data: dict[str, object]
        nested = payload.get("data")
        if isinstance(nested, dict):
            data = nested
        elif "columns" in payload or "rows" in payload:
            data = payload
        else:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                "dax_data_object_missing",
            )

        if data.get("success") is False or payload.get("success") is False:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_ERROR,
                "dax_execute_failed",
            )
        if "rows" not in data:
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_PREVIEW_ROW_DATA_MISSING,
                "dax_row_data_missing",
            )

        raw_columns = data.get("columns")
        raw_rows = data.get("rows")
        if not isinstance(raw_columns, list) or not isinstance(raw_rows, list):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                "dax_columns_or_rows_malformed",
            )
        wire_columns = cls._dax_column_names(raw_columns)
        rows = cls._dax_rows(raw_rows, wire_columns)
        columns = cls._normalize_dax_column_names(wire_columns)

        declared_row_count = data.get("rowCount")
        if declared_row_count is not None and (
            isinstance(declared_row_count, bool)
            or not isinstance(declared_row_count, int)
            or declared_row_count < 0
        ):
            raise LocalMCPConnectionError(
                LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                "dax_row_count_malformed",
            )

        truncated = len(rows) > snapshot.request.max_rows
        if (
            isinstance(declared_row_count, int)
            and declared_row_count > len(rows)
        ):
            truncated = True
        rows = rows[:snapshot.request.max_rows]
        return QueryResult(
            semantic_model_key=snapshot.request.semantic_model_key,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=cls._dax_execution_time_ms(payload, data),
            source_mode="real",
            request_id=snapshot.request.request_id or None,
            truncated=truncated,
        )

    @staticmethod
    def _dax_column_names(raw_columns: list[object]) -> list[str]:
        columns: list[str] = []
        for item in raw_columns:
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                name = item["name"]
            else:
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                    "dax_column_malformed",
                )
            if not name.strip() or name in columns:
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                    "dax_column_name_invalid",
                )
            columns.append(name)
        return columns

    @staticmethod
    def _normalize_dax_column_names(wire_columns: list[str]) -> list[str]:
        """Normalize runtime-qualified group-by labels to QueryResult fields.

        Power BI returns base group-by columns as ``Table[Column]`` while the
        canonical QueryPlan and independent oracle use the runtime column name
        ``Column``.  Calculated/measure labels such as ``[Total Sales]`` remain
        unchanged.  A collision fails closed instead of inventing ownership.
        """
        normalized: list[str] = []
        for wire_name in wire_columns:
            match = re.fullmatch(r"(?:'[^']+'|[^\[]+)\[([^\[\]]+)\]", wire_name)
            name = match.group(1) if match else wire_name
            if name in normalized:
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                    "dax_normalized_column_name_collision",
                )
            normalized.append(name)
        return normalized

    @staticmethod
    def _dax_rows(raw_rows: list[object], columns: list[str]) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for item in raw_rows:
            if isinstance(item, dict):
                if any(column not in item for column in columns):
                    raise LocalMCPConnectionError(
                        LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                        "dax_row_column_missing",
                    )
                row = [item[column] for column in columns]
            elif isinstance(item, list):
                if len(item) != len(columns):
                    raise LocalMCPConnectionError(
                        LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                        "dax_row_width_mismatch",
                    )
                row = list(item)
            else:
                raise LocalMCPConnectionError(
                    LocalMCPErrorCategory.DAX_MALFORMED_RESPONSE,
                    "dax_row_malformed",
                )
            rows.append(row)
        return rows

    @staticmethod
    def _dax_execution_time_ms(
        payload: dict[str, object],
        data: dict[str, object],
    ) -> int | None:
        for candidate in (
            data.get("executionTimeMs"),
            payload.get("executionTimeMs"),
        ):
            if (
                isinstance(candidate, (int, float))
                and not isinstance(candidate, bool)
                and candidate >= 0
            ):
                return int(round(candidate))

        metrics = payload.get("executionMetrics")
        if not isinstance(metrics, dict):
            metrics = data.get("executionMetrics")
        if isinstance(metrics, dict):
            reported = metrics.get("reportedExecutionMetrics")
            if isinstance(reported, dict):
                candidate = reported.get("durationMs")
                if (
                    isinstance(candidate, (int, float))
                    and not isinstance(candidate, bool)
                    and candidate >= 0
                ):
                    return int(round(candidate))
        return None

    @staticmethod
    def _query_error_result(
        request: DAXRequest,
        error: PowerBIError,
        *,
        truncated: bool = False,
    ) -> QueryResult:
        return QueryResult(
            semantic_model_key=request.semantic_model_key,
            source_mode="real",
            request_id=request.request_id or None,
            error=error,
            truncated=truncated,
        )
