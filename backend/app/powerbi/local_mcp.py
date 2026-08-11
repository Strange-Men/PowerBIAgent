"""Power BI Local Modeling MCP Adapter and stdio client boundary.

M2.1 only starts the official local server, negotiates MCP, discovers tools,
finds a running Power BI Desktop instance, and verifies a connection. It does
not read model metadata, execute DAX, or expose modeling tools to the app.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError

from backend.app.powerbi.base import PowerBIAdapter
from backend.app.schemas.data_contracts import (
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)


LOCAL_MCP_PACKAGE = "@microsoft/powerbi-modeling-mcp@0.5.0-beta.12"
M2_1_ALLOWED_TOOL_NAMES = frozenset({"connection_operations"})
_SCHEMA_CAPABILITY_TOOLS = frozenset(
    {
        "table_operations",
        "column_operations",
        "measure_operations",
        "relationship_operations",
        "user_hierarchy_operations",
    }
)
_DAX_CAPABILITY_TOOL = "dax_query_operations"


class LocalMCPErrorCategory(str, Enum):
    """Safe M2.1 failure categories."""

    LOCAL_PREREQUISITE = "LOCAL_PREREQUISITE"
    MCP_STARTUP = "MCP_STARTUP"
    MCP_PROTOCOL = "MCP_PROTOCOL"
    DESKTOP_NOT_FOUND = "DESKTOP_NOT_FOUND"
    DESKTOP_CONNECTION = "DESKTOP_CONNECTION"
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
                        return await self._discover_and_connect_desktop(
                            client,
                            protocol,
                            tools,
                        )
            except LocalMCPConnectionError:
                raise
            except Exception as exc:
                raise self._classify_exception(
                    exc,
                    diagnostic_text=self._read_diagnostic_text(errlog),
                ) from None

    async def _discover_and_connect_desktop(
        self,
        client: Client,
        protocol: str | None,
        tools: tuple[DiscoveredLocalTool, ...],
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
        if not state["schema_capability"] or not state["dax_capability"]:
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
        readonly: bool = True,
        timeout: float = 120.0,
        max_retries: int = 1,
        client: LocalMCPConnection | None = None,
    ) -> None:
        self._executable = executable
        self._package = package
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
        if self._client is None:
            try:
                self._client = PowerBILocalMCPClient(
                    executable=self._executable,
                    package=self._package,
                    readonly=self._readonly,
                    timeout_seconds=self._timeout,
                )
            except ValueError:
                self._last_diagnostics = LocalMCPDiagnostics.failure(
                    LocalMCPErrorCategory.LOCAL_PREREQUISITE,
                    "invalid_local_mcp_configuration",
                    readonly=self._readonly,
                )
                return False

        for attempt in range(self._max_retries + 1):
            try:
                diagnostics = await self._client.connect_and_discover()
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
        raise NotImplementedError(
            "TODO: M2.2 — read Semantic Model metadata through Local MCP."
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        raise NotImplementedError(
            "TODO: M2.3 — execute DAX through Local MCP."
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        raise NotImplementedError(
            "TODO: M2.3 — normalize Local MCP query results."
        )

    async def normalize_error(self, raw: object) -> PowerBIError:
        raise NotImplementedError(
            "TODO: M2.3 — normalize Local MCP errors."
        )
