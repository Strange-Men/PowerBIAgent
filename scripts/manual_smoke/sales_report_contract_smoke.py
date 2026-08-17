"""M3 sales_report contract smoke through the sealed M2 Real execution chain.

Expected scalar values are mandatory CLI acceptance oracles. They are never
used to construct QueryResult or any production artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any


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


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOperation("boolean_is_not_a_business_measure")
    return Decimal(str(value))


def _print_summary(values: dict[str, object]) -> None:
    for key, value in values.items():
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}={value}")


async def _run_smoke(
    expected_total_sales: Decimal,
    expected_total_quantity: Decimal,
) -> int:
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.dax.builder import DeterministicDAXBuilder
    from backend.app.facts import FactType, VerifiedFactSetBuilder
    from backend.app.harness.models import HarnessConfig
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import (
        SchemaInput,
        create_default_tool_gateway,
    )
    from backend.app.harness.validators.validation_service import ValidationService
    from backend.app.intent.models import IntentType
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
    from backend.app.report.contracts import ReportDataPlanBuilder
    from backend.app.schemas.data_contracts import UserContext

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    prerequisites_ready = (
        sys.platform == "win32"
        and settings.is_powerbi_local_mcp_configured
        and shutil.which(settings.powerbi_local_mcp_executable) is not None
        and _powerbi_desktop_is_running()
    )
    if not prerequisites_ready:
        _print_summary({"result": "FAIL", "error_type": "prerequisite_failed"})
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
        raise RuntimeError("renderer_not_used_in_m3_contract_smoke")

    config = HarnessConfig.from_settings(settings).model_copy(
        update={"max_powerbi_retries": 0}
    )
    gateway = create_default_tool_gateway(
        adapter,
        SimpleNamespace(render=_unused_renderer),
        config,
    )
    context = ToolExecutionContext(
        intent=IntentType.REPORT_GENERATION,
        user=UserContext(
            allowed_semantic_models=[settings.powerbi_local_semantic_model_key],
            allowed_templates=["sales_report"],
            allowed_tools=["get_semantic_model_schema", "execute_dax"],
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
        report_plan = ReportDataPlanBuilder().build("sales_report", schema)
    except Exception as exc:
        _print_summary({
            "result": "FAIL",
            "error_type": getattr(exc, "code", type(exc).__name__),
            "fallback_count": 0,
            "llm_calls": 0,
            "renderer_calls": 0,
        })
        return 1

    validator = ValidationService(
        allowed_semantic_models=[settings.powerbi_local_semantic_model_key],
        allowed_templates=["sales_report"],
    )
    actual_scalars: dict[str, Decimal] = {}
    query_rows: dict[str, int] = {}
    try:
        for query in report_plan.queries:
            request = DeterministicDAXBuilder().build(
                query.query_plan,
                schema,
                request_id=f"m3-contract-{query.requirement_key}",
                timeout_seconds=settings.powerbi_query_timeout_seconds,
            )
            layer3 = validator.validate_dax_query_plan_consistency(
                request,
                query.query_plan,
                schema,
            )
            if not layer3.is_valid:
                raise RuntimeError("independent_layer3_failed")
            result = await gateway.execute("execute_dax", context, request)
            result_validation = validator.validate_query_result(
                result,
                expected_source_mode="real",
            )
            if result.error is not None or not result_validation.is_valid:
                raise RuntimeError("query_result_validation_failed")
            facts = VerifiedFactSetBuilder().build(query.query_plan, result)
            query_rows[query.requirement_key] = result.row_count
            if query.shape.value == "scalar":
                scalar_facts = facts.by_type(FactType.SCALAR_METRIC)
                if len(scalar_facts) != 1:
                    raise RuntimeError("scalar_fact_shape_invalid")
                actual_scalars[query.requirement_key] = _decimal(
                    scalar_facts[0].value
                )
    except Exception as exc:
        _print_summary({
            "result": "FAIL",
            "error_type": getattr(exc, "code", type(exc).__name__),
            "schema_fingerprint": report_plan.schema_fingerprint,
            "fallback_count": 0,
            "llm_calls": 0,
            "renderer_calls": 0,
        })
        return 1

    total_sales = actual_scalars.get("total_sales")
    total_quantity = actual_scalars.get("total_quantity")
    scalar_oracle_match = (
        total_sales == expected_total_sales
        and total_quantity == expected_total_quantity
    )
    all_queries_nonempty = all(
        query_rows.get(query.requirement_key, 0) > 0
        for query in report_plan.queries
    )
    success = scalar_oracle_match and all_queries_nonempty
    sales = next(table for table in schema.tables if table.name == "Sales")
    field_types = ",".join(
        f"{item.name}:{item.data_type}"
        for item in sales.columns
        if not item.is_hidden
    )
    measure_types = ",".join(
        f"{item.name}:{item.data_type}"
        for item in sales.measures
        if not item.is_hidden
    )
    _print_summary({
        "result": "PASS" if success else "FAIL",
        "template_key": report_plan.template_key,
        "semantic_model_key": report_plan.semantic_model_key,
        "schema_fingerprint": report_plan.schema_fingerprint,
        "sales_field_types": field_types,
        "sales_measure_types": measure_types,
        "total_sales": total_sales,
        "total_quantity": total_quantity,
        "scalar_oracle_match": scalar_oracle_match,
        "query_count": len(report_plan.queries),
        "all_queries_nonempty": all_queries_nonempty,
        "source_mode": "real",
        "fallback_count": 0,
        "llm_calls": 0,
        "renderer_calls": 0,
    })
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-total-sales",
        type=Decimal,
        required=True,
    )
    parser.add_argument(
        "--expected-total-quantity",
        type=Decimal,
        required=True,
    )
    args = parser.parse_args()
    return asyncio.run(_run_smoke(
        args.expected_total_sales,
        args.expected_total_quantity,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
