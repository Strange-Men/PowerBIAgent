"""M2.2 real Semantic Model Schema smoke through the production boundaries.

This script intentionally prints only aggregate counts and fixed expectation
flags. It never prints model identity, connection details, expressions, or data.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _powerbi_desktop_is_running() -> bool:
    if sys.platform != "win32":
        return False
    check = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "if (Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue) "
                "{ exit 0 } else { exit 1 }"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return check.returncode == 0


def _print_summary(values: dict[str, object]) -> None:
    for key, value in values.items():
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}={value}")


async def _run_smoke() -> int:
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.models import HarnessConfig
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import (
        SchemaInput,
        create_default_tool_gateway,
    )
    from backend.app.intent.models import IntentType
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
    from backend.app.schemas.data_contracts import UserContext

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    if sys.platform != "win32":
        _print_summary({"schema_loaded": False, "error_type": "windows_required"})
        return 1
    if not settings.is_powerbi_local_mcp_configured:
        _print_summary({
            "schema_loaded": False,
            "error_type": "invalid_local_mcp_configuration",
        })
        return 1
    if shutil.which(settings.powerbi_local_mcp_executable) is None:
        _print_summary({
            "schema_loaded": False,
            "error_type": "local_mcp_executable_missing",
        })
        return 1
    if not _powerbi_desktop_is_running():
        _print_summary({
            "schema_loaded": False,
            "error_type": "powerbi_desktop_not_running",
        })
        return 1

    adapter = LocalMCPPowerBIAdapter(
        executable=settings.powerbi_local_mcp_executable,
        package=settings.powerbi_local_mcp_package,
        semantic_model_key=settings.powerbi_local_semantic_model_key,
        readonly=settings.powerbi_local_mcp_readonly,
        timeout=float(settings.request_timeout_seconds),
        max_retries=0,
    )

    async def _unused_renderer(_: object) -> str:
        raise RuntimeError("renderer_not_used_in_schema_smoke")

    config = HarnessConfig.from_settings(settings).model_copy(
        update={"max_powerbi_retries": 0}
    )
    gateway = create_default_tool_gateway(
        adapter,
        SimpleNamespace(render=_unused_renderer),
        config,
    )
    context = ToolExecutionContext(
        intent=IntentType.DATA_QUESTION,
        user=UserContext(
            allowed_semantic_models=[settings.powerbi_local_semantic_model_key],
            allowed_tools=["get_semantic_model_schema"],
        ),
        runtime_mode=RuntimeDataMode.REAL,
    )
    try:
        schema = await gateway.execute(
            "get_semantic_model_schema",
            context,
            SchemaInput(
                semantic_model_key=settings.powerbi_local_semantic_model_key
            ),
        )
    except Exception as exc:
        diagnostics = adapter.last_diagnostics
        _print_summary({
            "schema_loaded": False,
            "error_category": (
                diagnostics.error_category.value
                if diagnostics.error_category is not None
                else "BUG"
            ),
            "error_type": diagnostics.error_type or type(exc).__name__,
            "dax_executed": False,
            "deepseek_calls": 0,
        })
        return 1

    table_count = len(schema.tables)
    column_count = sum(len(table.columns) for table in schema.tables)
    measure_count = sum(len(table.measures) for table in schema.tables)
    hierarchy_count = sum(len(table.hierarchies) for table in schema.tables)
    measures = set(schema.get_all_measures())
    sales_tables = [table for table in schema.tables if table.name == "Sales"]
    sales_columns = (
        {column.name for column in sales_tables[0].columns}
        if len(sales_tables) == 1
        else set()
    )
    expected_columns = {"OrderDate", "Product", "Category", "Quantity", "UnitPrice"}
    total_sales = next(
        (
            measure
            for table in schema.tables
            for measure in table.measures
            if measure.name == "Total Sales"
        ),
        None,
    )
    total_quantity = next(
        (
            measure
            for table in schema.tables
            for measure in table.measures
            if measure.name == "Total Quantity"
        ),
        None,
    )
    schema_valid = (
        table_count > 0
        and column_count > 0
        and measure_count >= 2
        and len(sales_tables) == 1
        and expected_columns.issubset(sales_columns)
        and total_sales is not None
        and total_quantity is not None
        and bool(total_sales.expression)
        and bool(total_quantity.expression)
    )
    _print_summary({
        "schema_loaded": schema_valid,
        "desktop_connection": adapter.last_diagnostics.connection,
        "protocol": adapter.last_diagnostics.protocol,
        "table_count": table_count,
        "column_count": column_count,
        "measure_count": measure_count,
        "relationship_count": len(schema.relationships),
        "hierarchy_count": hierarchy_count,
        "expected_measure_total_sales": "Total Sales" in measures,
        "expected_measure_total_quantity": "Total Quantity" in measures,
        "expected_sales_columns": expected_columns.issubset(sales_columns),
        "expected_measure_expressions_nonempty": (
            total_sales is not None
            and total_quantity is not None
            and bool(total_sales.expression)
            and bool(total_quantity.expression)
        ),
        "dax_executed": False,
        "deepseek_calls": 0,
    })
    return 0 if schema_valid else 1


def main() -> int:
    return asyncio.run(_run_smoke())


if __name__ == "__main__":
    raise SystemExit(main())
