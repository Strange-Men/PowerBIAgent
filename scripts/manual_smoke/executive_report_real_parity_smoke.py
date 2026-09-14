"""Real PBIX one-snapshot Simple/Executive factual-parity acceptance.

The professional template is publicly available after activation.  One shared
sales ReportDataPlan executes through the production Local
MCP → deterministic DAX → Layer 3 → QueryResult → VerifiedFactSet chain.  The
resulting immutable data contract is projected twice and rendered in memory;
there is no duplicate query, LLM factual call, report artifact, or persistence.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _fact_projection(report: Any) -> dict[str, object]:
    charts = {
        item.business_role: [
            (point.get("label"), point.get("value"), point.get("position"))
            for point in item.series
        ]
        for item in report.charts
    }
    customer_rows: list[tuple[object, object, object]] = []
    for table in report.tables:
        if table.title not in {"关键明细", "Top 客户"}:
            continue
        if table.columns == ["客户", "销售额（元）"]:
            customer_rows = [
                (index, row[0], row[1])
                for index, row in enumerate(table.rows, start=1)
            ]
        elif table.columns == ["排名", "客户", "销售额（元）"]:
            customer_rows = [tuple(row) for row in table.rows]
    return {
        "kpis": [(item.field, item.value) for item in report.kpis],
        "charts": charts,
        "top_customers": customer_rows,
        "query_result_ids": list(report.query_result_ids),
        "verified_fact_set_ids": list(report.verified_fact_set_ids),
    }


def _scope_plan(scope: str, schema_key: str):
    from backend.app.schemas.data_contracts import (
        CanonicalQueryPlan,
        FilterOperator,
        StructuredFilter,
        TimeRangeMode,
        TimeRangeSpec,
    )

    filters = []
    time_range = None
    hints: dict[str, str] = {}
    if scope in {"region_filter", "multiple_filters"}:
        filters.append(StructuredFilter(
            field="Region", operator=FilterOperator.EQ, value="South"
        ))
        hints["Region"] = "Sales"
    if scope == "multiple_filters":
        filters.append(StructuredFilter(
            field="Category", operator=FilterOperator.EQ, value="Furniture"
        ))
        hints["Category"] = "Sales"
    if scope == "bounded":
        time_range = TimeRangeSpec(
            date_field="OrderDate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            mode=TimeRangeMode.EXPLICIT_RANGE,
        )
        hints["OrderDate"] = "Sales"
    if not filters and time_range is None:
        return None
    return CanonicalQueryPlan(
        normalized_question=f"real acceptance canonical scope: {scope}",
        semantic_model_key=schema_key,
        measures=["Total Sales"],
        filters=filters,
        time_range=time_range,
        dimension_tables=hints or None,
    )


async def _run(scope: str, expected_model: str) -> dict[str, object]:
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.dax.builder import DeterministicDAXBuilder
    from backend.app.dax.safety import DAXSafetyValidator
    from backend.app.facts import VerifiedFactSetBuilder
    from backend.app.harness.models import HarnessConfig
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import SchemaInput, create_default_tool_gateway
    from backend.app.harness.validators.validation_service import ValidationService
    from backend.app.intent.models import IntentType
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
    from backend.app.report.assembly import SalesReportDataAssembler, SalesReportSpecBuilder
    from backend.app.report.contracts import (
        SALES_EXECUTIVE_REPORT_CONTRACT,
        SALES_QUERY_REQUIREMENTS,
        ReportContractValidator,
    )
    from backend.app.report.executive import ExecutiveSalesReportRenderer
    from backend.app.report.fixed import SalesReportRenderer
    from backend.app.report.intent import resolve_report_intent
    from backend.app.report.plan import ReportPlanner
    from backend.app.report.reading_context import (
        ReportDataSnapshotBuilder,
        ReportReadingContextBuilder,
        ReportScopeContextBuilder,
        SALES_METRIC_DEFINITIONS,
    )
    from backend.app.schemas.data_contracts import UserContext
    from backend.app.schemas.report_context import ExceptionAssessment, ReportDataSourceKind

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    if shutil.which(settings.powerbi_local_mcp_executable) is None:
        raise RuntimeError("local_mcp_executable_missing")
    adapter = LocalMCPPowerBIAdapter(
        executable=settings.powerbi_local_mcp_executable,
        package=settings.powerbi_local_mcp_package,
        semantic_model_key=settings.powerbi_local_semantic_model_key,
        readonly=settings.powerbi_local_mcp_readonly,
        timeout=float(settings.request_timeout_seconds),
        max_retries=0,
    )
    outcome: dict[str, object] | None = None
    try:
        if not await adapter.health_check():
            raise RuntimeError(adapter.last_diagnostics.error_type or "health_check_failed")
        catalog = await adapter.discover_semantic_models()
        # The adapter owns raw instance discovery.  ``selectable`` is assigned
        # later by SemanticModelDiscoveryService after compatibility probing,
        # so the direct adapter catalog intentionally leaves it false.
        model_keys = [
            item.key for item in catalog.items if item.available and item.connected
        ]
        if catalog.error_type or not model_keys:
            raise RuntimeError(catalog.error_type or "no_powerbi_model_discovered")
        config = HarnessConfig.from_settings(settings).model_copy(
            update={"max_powerbi_retries": 0, "max_tool_calls": 16}
        )
        gateway = create_default_tool_gateway(
            adapter, SalesReportRenderer(), config
        )
        context = ToolExecutionContext(
            intent=IntentType.REPORT_GENERATION,
            user=UserContext(
                allowed_semantic_models=model_keys,
                allowed_templates=["sales_report"],
                allowed_tools=["get_semantic_model_schema", "execute_dax"],
            ),
            runtime_mode=RuntimeDataMode.REAL,
        )
        schemas = [
            await gateway.execute(
                "get_semantic_model_schema",
                context,
                SchemaInput(semantic_model_key=model_key),
            )
            for model_key in model_keys
        ]
        contract_validator = ReportContractValidator(
            binding_scope_key=settings.powerbi_local_semantic_model_key,
        )
        candidates = []
        for schema in schemas:
            contract_check = contract_validator.validate("sales_report", schema)
            if not any(item.available for item in contract_check.requirement_availability):
                continue
            candidates.append((
                schema,
                "rich"
                if {"Total Orders", "Average Order Value"}.issubset(
                    set(schema.get_all_measures())
                )
                else "simple",
            ))
        selected = (
            candidates
            if expected_model == "auto"
            else [item for item in candidates if item[1] == expected_model]
        )
        if len(selected) != 1:
            raise RuntimeError(
                f"active_pbix_selection_not_unique:{expected_model}:{len(selected)}"
            )
        schema, model_kind = selected[0]
        scope_plan = _scope_plan(scope, schema.key)
        message = (
            "生成包含销售额、销量、订单数、平均订单金额、月度趋势、区域、"
            "品类、Top产品和Top客户的完整销售报表"
        )
        signal = resolve_report_intent(message)
        report_plan = ReportPlanner(validator=contract_validator).plan(
            "sales_report",
            schema,
            signal.requested_ids,
            signal,
            scope_plan=scope_plan,
        )
        validator = ValidationService(
            allowed_semantic_models=[schema.key],
            allowed_templates=["sales_report"],
        )
        query_results: dict[str, Any] = {}
        fact_sets: dict[str, Any] = {}
        dax_fingerprints: dict[str, str] = {}
        import hashlib
        for query in report_plan.data_plan.queries:
            request = DeterministicDAXBuilder().build(
                query.query_plan,
                schema,
                request_id=f"m5101-{scope}-{query.requirement_key}",
                timeout_seconds=settings.powerbi_query_timeout_seconds,
            )
            if not DAXSafetyValidator().validate(request.dax, schema).is_valid:
                raise RuntimeError("dax_safety_failed")
            if not validator.validate_dax_query_plan_consistency(
                request, query.query_plan, schema
            ).is_valid:
                raise RuntimeError("independent_layer3_failed")
            result = await gateway.execute("execute_dax", context, request)
            if result.error is not None:
                raise RuntimeError(f"dax_execution_failed:{result.error.type}")
            if not validator.validate_query_result(
                result, expected_source_mode="real"
            ).is_valid:
                raise RuntimeError("query_result_validation_failed")
            facts = VerifiedFactSetBuilder().build(query.query_plan, result)
            query_results[query.requirement_key] = result
            fact_sets[query.requirement_key] = facts
            dax_fingerprints[query.requirement_key] = hashlib.sha256(
                request.dax.encode("utf-8")
            ).hexdigest()

        empty_requirements = tuple(
            key for key, result in query_results.items() if result.row_count == 0
        )
        if empty_requirements:
            raise RuntimeError(
                "required_query_empty:" + ",".join(empty_requirements)
            )
        simple_data = SalesReportDataAssembler().build(
            report_plan.data_plan, query_results, fact_sets
        )
        executive_data = simple_data.model_copy(update={
            "template_key": "sales_executive_report",
            "contract_version": SALES_EXECUTIVE_REPORT_CONTRACT.contract_version,
        })
        analysis_period, active_filters = ReportScopeContextBuilder().build(
            {item.requirement_key: item.query_plan for item in report_plan.data_plan.queries},
            fact_sets,
        )
        snapshot_at = simple_data.generated_at
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)
        snapshot = ReportDataSnapshotBuilder().build(
            semantic_model_identity=schema.key,
            schema_fingerprint=simple_data.schema_fingerprint,
            query_results=query_results,
            verified_fact_sets=fact_sets,
            source_kind=ReportDataSourceKind.LOCAL_MCP,
            queried_at=snapshot_at,
            snapshot_at=snapshot_at,
        )
        by_measure = {
            definition.canonical_measure: key
            for key, definition in SALES_METRIC_DEFINITIONS.items()
        }
        metric_keys = tuple(dict.fromkeys(
            by_measure[item.measure]
            for item in (*simple_data.kpis, *simple_data.sections)
        ))
        reading_context = ReportReadingContextBuilder().build(
            report_title="销售经营分析报告",
            analysis_period=analysis_period,
            active_filters=active_filters,
            metric_definition_keys=metric_keys,
            exception_assessment=ExceptionAssessment.cannot_determine(),
            snapshot=snapshot,
            generated_at=simple_data.generated_at,
        )
        simple_spec = SalesReportSpecBuilder().build(simple_data)
        executive_spec = SalesReportSpecBuilder().build(
            executive_data,
            reading_context=reading_context,
            data_snapshot=snapshot,
        )
        simple_started = perf_counter()
        simple_html = await SalesReportRenderer().render(simple_spec)
        simple_ms = (perf_counter() - simple_started) * 1000
        executive_started = perf_counter()
        executive_html = await ExecutiveSalesReportRenderer().render(executive_spec)
        executive_ms = (perf_counter() - executive_started) * 1000

        simple_projection = _fact_projection(simple_spec)
        executive_projection = _fact_projection(executive_spec)
        parity = simple_projection == executive_projection
        all_authority_keys = tuple(item.key for item in SALES_QUERY_REQUIREMENTS)
        shared_identity = all(
            left is right
            for left, right in zip(
                SALES_QUERY_REQUIREMENTS,
                SALES_EXECUTIVE_REPORT_CONTRACT.query_requirements,
                strict=True,
            )
        )
        lifecycle = adapter.runtime_lifecycle_snapshot() or {}
        outcome = {
            "result": "PASS" if parity and shared_identity else "FAIL",
            "active_model_kind": model_kind,
            "scope": scope,
            "schema_fingerprint": report_plan.schema_fingerprint,
            "authority_requirement_keys": all_authority_keys,
            "executed_requirement_keys": tuple(query_results),
            "query_count": len(query_results),
            "query_result_ids": list(simple_data.query_result_ids),
            "verified_fact_set_ids": list(simple_data.verified_fact_set_ids),
            "dax_fingerprints": dax_fingerprints,
            "source_mode": simple_data.source_mode,
            "simple_executive_factual_parity": parity,
            "shared_requirement_object_identity": shared_identity,
            "simple_template_identity": simple_spec.template_key,
            "executive_template_identity": executive_spec.template_key,
            "reading_context_before_numbers": (
                executive_html.index('data-section="reading_context"')
                < executive_html.index('data-section="kpi_summary"')
                if executive_spec.kpis else True
            ),
            "unknown_freshness_visible": "数据更新时间：模型未提供" in executive_html,
            "exception_unknown_visible": (
                "当前模型未提供可验证的目标、预测或异常判断基准"
                in executive_html
            ),
            "simple_renderer_ms": round(simple_ms, 3),
            "executive_renderer_ms": round(executive_ms, 3),
            "simple_html_bytes": len(simple_html.encode("utf-8")),
            "executive_html_bytes": len(executive_html.encode("utf-8")),
            "llm_calls": 0,
            "fake_query_result_count": 0,
            "report_artifact_count": 0,
            "runtime_lifecycle_before_close": lifecycle,
        }
    finally:
        await adapter.aclose()
        if outcome is not None:
            lifecycle_after_close = adapter.runtime_lifecycle_snapshot() or {}
            outcome["runtime_lifecycle_after_close"] = lifecycle_after_close
            lifecycle_clean = (
                lifecycle_after_close.get("session_residual") == 0
                and lifecycle_after_close.get("active_workers") == 0
            )
            outcome["runtime_lifecycle_clean"] = lifecycle_clean
            if not lifecycle_clean:
                outcome["result"] = "FAIL"
    if outcome is None:
        raise RuntimeError("real_acceptance_missing_outcome")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=("full", "bounded", "region_filter", "multiple_filters"),
        default="full",
    )
    parser.add_argument("--expect-model", choices=("auto", "simple", "rich"), default="auto")
    args = parser.parse_args()
    try:
        result = asyncio.run(_run(args.scope, args.expect_model))
    except Exception as exc:
        print(json.dumps({
            "result": "FAIL",
            "error_type": getattr(exc, "code", type(exc).__name__),
            "error": str(exc),
            "scope": args.scope,
            "llm_calls": 0,
            "fake_query_result_count": 0,
            "report_artifact_count": 0,
        }, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
