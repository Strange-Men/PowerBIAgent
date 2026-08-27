"""M3.4 adaptive sales_report smoke through the sealed M2 Real execution chain.

Runs against whichever model is active in Power BI Desktop (--model simple
for PowerBIAgent_M3_Test.pbix, --model rich for PowerBIAgent_M3_Rich_Test.pbix
must be the open one).  The deterministic planner resolves the requested
sections against the REAL runtime schema; every query reuses the sealed M2
chain.  Expected scalar values are mandatory CLI acceptance oracles. They are
never used to construct QueryResult or any production artifact.

The final HTML, repository hash, acceptance copy, and view/download endpoints
are also checked.  All factual LLM counters must be 0; the report-intent weak
signal is 0 here because this smoke drives the deterministic chain directly
(no LLM provider).
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
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
    model: str,
    message: str,
    expected_scalars: dict[str, Decimal],
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
    from backend.app.report.assembly import (
        SalesReportDataAssembler,
        SalesReportSpecBuilder,
    )
    from backend.app.report.fixed import SalesReportRenderer
    from backend.app.report.intent import resolve_report_intent
    from backend.app.report.plan import ReportPlanner
    from backend.app.report.resources import LocalReportRepository
    from backend.app.schemas.data_contracts import UserContext

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    pbix_name = (
        "PowerBIAgent_M3_Test.pbix"
        if model == "simple"
        else "PowerBIAgent_M3_Rich_Test.pbix"
    )
    prerequisites_ready = (
        sys.platform == "win32"
        and (_PROJECT_ROOT / "demo_data" / pbix_name).exists()
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

    config = HarnessConfig.from_settings(settings).model_copy(
        update={"max_powerbi_retries": 0, "max_tool_calls": 16}
    )
    repository = LocalReportRepository(_PROJECT_ROOT / "local_state" / "reports")
    gateway = create_default_tool_gateway(
        adapter,
        SalesReportRenderer(),
        config,
        repository,
    )
    context = ToolExecutionContext(
        intent=IntentType.REPORT_GENERATION,
        user=UserContext(
            allowed_semantic_models=[settings.powerbi_local_semantic_model_key],
            allowed_templates=["sales_report"],
            allowed_tools=[
                "get_semantic_model_schema",
                "execute_dax",
                "render_report",
            ],
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
        signal = resolve_report_intent(message)
        report_plan = ReportPlanner().plan(
            "sales_report", schema, signal.requested_ids, signal
        )
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
    query_results: dict[str, Any] = {}
    verified_fact_sets: dict[str, Any] = {}
    try:
        for query in report_plan.data_plan.queries:
            request = DeterministicDAXBuilder().build(
                query.query_plan,
                schema,
                request_id=f"m3-{model}-{query.requirement_key}",
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
            query_results[query.requirement_key] = result
            verified_fact_sets[query.requirement_key] = facts
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

    try:
        report_data = SalesReportDataAssembler().build(
            report_plan.data_plan,
            query_results,
            verified_fact_sets,
        )
        report_spec = SalesReportSpecBuilder().build(report_data)
        artifact = await gateway.execute("render_report", context, report_spec)
        acceptance_path = await repository.export_acceptance_copy(
            artifact.report_id
        )
        stored_artifact, stored_html = await repository.read_html(
            artifact.report_id
        )
        stored_bytes = stored_html.encode("utf-8")
        hash_match = (
            hashlib.sha256(stored_bytes).hexdigest()
            == stored_artifact.content_hash
            == artifact.content_hash
        )
        managed_path = repository.root / f"{artifact.report_id}.html"
        file_match = (
            managed_path.is_file()
            and acceptance_path.is_file()
            and managed_path.read_bytes() == stored_bytes
            and acceptance_path.read_bytes() == stored_bytes
        )

        from fastapi import FastAPI
        import httpx
        from backend.app.api.routes import router

        api = FastAPI()
        api.state.report_repository = repository
        api.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://acceptance",
        ) as client:
            view_response = await client.get(artifact.view_reference)
            download_response = await client.get(artifact.download_reference)
        view_ok = view_response.status_code == 200 and view_response.content == stored_bytes
        download_ok = (
            download_response.status_code == 200
            and download_response.content == stored_bytes
            and "attachment" in download_response.headers.get(
                "content-disposition", ""
            )
        )

        lowered = stored_html.casefold()
        static_safe = (
            stored_html.startswith("<!DOCTYPE html>")
            and "<script" not in lowered
            and "http://" not in lowered
            and "https://" not in lowered
            and "<link" not in lowered
            and "javascript:" not in lowered
            and "url(" not in lowered
            and "src=" not in lowered
        )

        tracked = subprocess.run(
            ["git", "ls-files", "--", "local_state", "*.pbix"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(acceptance_path)],
            cwd=_PROJECT_ROOT,
            timeout=10,
            check=False,
        )
        git_safe = tracked.returncode == 0 and not tracked.stdout.strip()
        gitignored = ignored.returncode == 0
    except Exception as exc:
        _print_summary({
            "result": "FAIL",
            "error_type": getattr(exc, "code", type(exc).__name__),
            "schema_fingerprint": report_plan.schema_fingerprint,
            "query_count": len(query_results),
            "source_mode": "real",
            "fallback_count": 0,
            "dax_llm_calls": 0,
            "report_data_llm_calls": 0,
            "report_factual_llm_calls": 0,
            "renderer_llm_calls": 0,
            "report_intent_llm_calls": 0,
            "fake_query_result_count": 0,
        })
        return 1

    scalar_oracle_match = all(
        actual_scalars.get(key) == expected
        for key, expected in expected_scalars.items()
    )
    all_queries_nonempty = all(
        query_rows.get(query.requirement_key, 0) > 0
        for query in report_plan.data_plan.queries
    )
    expected_sections = {
        "simple": {
            "sales_kpi",
            "quantity_kpi",
            "category_contribution",
            "top_products",
        },
        "rich": {
            "sales_kpi",
            "quantity_kpi",
            "orders_kpi",
            "aov_kpi",
            "time_trend",
            "category_contribution",
            "region_comparison",
            "top_products",
            "top_customers",
        },
    }
    resolved_names = {item.value for item in report_plan.resolved_sections}
    sections_match = resolved_names == expected_sections[model]

    visual_types = {item.visual_type for item in report_spec.charts}
    visuals_match = {
        "simple": visual_types == {"donut", "hbar"},
        "rich": visual_types == {"line", "donut", "column", "hbar"},
    }[model]

    success = (
        scalar_oracle_match
        and all_queries_nonempty
        and sections_match
        and visuals_match
        and static_safe
        and hash_match
        and file_match
        and view_ok
        and download_ok
        and git_safe
        and gitignored
    )
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
        "model": model,
        "message": message,
        "template_key": report_plan.template_key,
        "semantic_model_key": report_plan.data_plan.semantic_model_key,
        "schema_fingerprint": report_plan.schema_fingerprint,
        "sales_field_types": field_types,
        "sales_measure_types": measure_types,
        "scalar_oracle_match": scalar_oracle_match,
        "query_count": len(report_plan.data_plan.queries),
        "resolved_sections": ",".join(sorted(resolved_names)),
        "sections_match": sections_match,
        "visual_types": ",".join(sorted(visual_types)),
        "visuals_match": visuals_match,
        "all_queries_nonempty": all_queries_nonempty,
        "static_safe": static_safe,
        "source_mode": "real",
        "fallback_count": 0,
        "dax_llm_calls": 0,
        "report_data_llm_calls": 0,
        "report_factual_llm_calls": 0,
        "renderer_llm_calls": 0,
        "report_intent_llm_calls": 0,
        "fake_query_result_count": 0,
        "renderer_calls": 1,
        "report_id": artifact.report_id,
        "html_path": str(acceptance_path),
        "managed_html_path": str(managed_path),
        "html_size_bytes": len(stored_bytes),
        "content_hash": artifact.content_hash,
        "content_hash_match": hash_match,
        "view_status": view_response.status_code,
        "download_status": download_response.status_code,
        "gitignored": gitignored,
        "git_tracked_output_empty": git_safe,
    })
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        choices=("simple", "rich"),
        required=True,
    )
    parser.add_argument(
        "--message",
        default="生成完整销售分析报表",
    )
    parser.add_argument(
        "--expected-total-sales",
        type=Decimal,
        default=None,
    )
    parser.add_argument(
        "--expected-total-quantity",
        type=Decimal,
        default=None,
    )
    parser.add_argument(
        "--expected-total-orders",
        type=Decimal,
        default=None,
    )
    parser.add_argument(
        "--expected-average-order-value",
        type=Decimal,
        default=None,
    )
    args = parser.parse_args()
    expected: dict[str, Decimal] = {}
    for key, value in (
        ("total_sales", args.expected_total_sales),
        ("total_quantity", args.expected_total_quantity),
        ("total_orders", args.expected_total_orders),
        ("average_order_value", args.expected_average_order_value),
    ):
        if value is not None:
            expected[key] = value
    return asyncio.run(_run_smoke(args.model, args.message, expected))


if __name__ == "__main__":
    raise SystemExit(main())
