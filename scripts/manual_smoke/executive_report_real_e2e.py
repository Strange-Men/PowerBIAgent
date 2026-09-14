"""M5.10.2 exact-phrase Real TurnService acceptance (DeepSeek only).

The script discovers the explicitly requested Rich/Simple Desktop model through
the formal ToolGateway, executes the production report turn, validates only
safe metadata, deletes the in-memory artifact, and closes both provider stacks.
It never prints configuration secrets, DAX text, result rows, or report HTML.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import sys


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def _run(
    expected_model: str,
    output_html: Path | None = None,
) -> dict[str, object]:
    from backend.app.application.deepseek_turn_service import DeepSeekTurnService
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.models import HarnessConfig
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import SchemaInput, create_default_tool_gateway
    from backend.app.intent.models import IntentType
    from backend.app.llm.factory import build_llm_registry
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.memory.repository import InMemoryMemoryRepository
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
    from backend.app.report.contracts import ReportContractValidator
    from backend.app.report.executive import ExecutiveSalesReportRenderer
    from backend.app.report.fixed import SalesReportRenderer
    from backend.app.report.registry import build_report_dispatcher
    from backend.app.report.resources import (
        InMemoryReportRepository,
        ReportNotFoundError,
    )
    from backend.app.schemas.data_contracts import UserContext

    base = Settings()
    settings = base.model_copy(update={
        "llm_mode": LLMMode.DEEPSEEK,
        "llm_default_profile": "deepseek",
        "powerbi_mode": PowerBIMode.LOCAL_MCP,
        "max_tool_calls": 8,
    })
    if not settings.is_deepseek_configured:
        raise RuntimeError("deepseek_configuration_missing")
    if shutil.which(settings.powerbi_local_mcp_executable) is None:
        raise RuntimeError("local_mcp_executable_missing")

    adapter = LocalMCPPowerBIAdapter(
        executable=settings.powerbi_local_mcp_executable,
        package=settings.powerbi_local_mcp_package,
        semantic_model_key=settings.powerbi_local_semantic_model_key,
        readonly=settings.powerbi_local_mcp_readonly,
        timeout=float(settings.request_timeout_seconds),
        max_retries=0,
        worker_count=settings.powerbi_local_mcp_workers,
        max_pending_operations=settings.powerbi_local_mcp_queue_capacity,
        max_operations_per_request=settings.powerbi_local_mcp_per_request_limit,
        admission_timeout_seconds=(
            settings.powerbi_local_mcp_admission_timeout_seconds
        ),
    )
    registry = build_llm_registry(settings)
    repository = InMemoryReportRepository()
    artifact_id: str | None = None
    outcome: dict[str, object] | None = None
    try:
        if not await adapter.health_check():
            raise RuntimeError(adapter.last_diagnostics.error_type or "health_check_failed")
        catalog = await adapter.discover_semantic_models()
        model_keys = [
            item.key for item in catalog.items if item.available and item.connected
        ]
        if catalog.error_type or not model_keys:
            raise RuntimeError(catalog.error_type or "no_powerbi_model_discovered")

        config = HarnessConfig.from_settings(settings).model_copy(update={
            "max_powerbi_retries": 0,
        })
        discovery_gateway = create_default_tool_gateway(
            adapter, SalesReportRenderer(), config
        )
        discovery_context = ToolExecutionContext(
            intent=IntentType.REPORT_GENERATION,
            user=UserContext(
                allowed_semantic_models=model_keys,
                allowed_templates=["sales_executive_report"],
                allowed_tools=["get_semantic_model_schema"],
            ),
            runtime_mode=RuntimeDataMode.REAL,
        )
        schemas = [
            await discovery_gateway.execute(
                "get_semantic_model_schema",
                discovery_context,
                SchemaInput(semantic_model_key=model_key),
            )
            for model_key in model_keys
        ]
        contract_validator = ReportContractValidator(
            binding_scope_key=settings.powerbi_local_semantic_model_key
        )
        candidates = []
        for schema in schemas:
            validation = contract_validator.validate(
                "sales_executive_report", schema
            )
            if not any(item.available for item in validation.requirement_availability):
                continue
            kind = (
                "rich"
                if {"Total Orders", "Average Order Value"}.issubset(
                    set(schema.get_all_measures())
                )
                else "simple"
            )
            if kind == expected_model:
                candidates.append(schema)
        if len(candidates) != 1:
            raise RuntimeError(
                f"active_pbix_selection_not_unique:{expected_model}:{len(candidates)}"
            )
        schema = candidates[0]

        service = DeepSeekTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_provider=None,
            llm_registry=registry,
            powerbi_adapter=adapter,
            report_renderer=build_report_dispatcher(
                SalesReportRenderer(), ExecutiveSalesReportRenderer()
            ),
            report_repository=repository,
            settings=settings,
            config=config,
        )
        result = await service.execute(
            message="生成一份完整的销售经营分析报表",
            conversation_id=f"m5102-real-{expected_model}",
            request_id=f"m5102-real-{expected_model}-request",
            semantic_model_key=schema.key,
            report_template_key="sales_executive_report",
            llm_profile_key="deepseek",
        )
        if result.get("terminal_state") != "completed":
            raise RuntimeError(
                f"real_turn_failed:{result.get('error_type') or 'unknown'}"
            )
        report = result["report"]
        artifact_id = report["report_id"]
        html = report["html"]
        main_visual = html.split('data-section="audit_footer"', maxsplit=1)[0]
        raw_tokens = tuple(
            token for token in (
                "local_desktop:", "local_mcp", "cannot_determine",
                "UNKNOWN", "semantic_measure",
            )
            if token in main_visual
        )
        if output_html is not None:
            output_html.parent.mkdir(parents=True, exist_ok=True)
            output_html.write_text(html, encoding="utf-8")
        audit = result["execution_audit"]
        expected_query_count = 9 if expected_model == "rich" else 4
        passed = (
            result.get("intent") == "report_generation"
            and report["template_key"] == "sales_executive_report"
            and audit["requested_coverage"] == "full_available"
            and audit["query_count"] == expected_query_count
            and audit["assembled_query_count"] == expected_query_count
            and audit["dropped_after_facts"] == []
            and audit["llm_dax_call_count"] == 0
            and audit["llm_report_data_call_count"] == 0
            and audit["renderer_llm_call_count"] == 0
            and not raw_tokens
        )
        outcome = {
            "result": "PASS" if passed else "FAIL",
            "active_model_kind": expected_model,
            "route_intent": result.get("intent"),
            "template_key": report["template_key"],
            "requested_coverage": audit["requested_coverage"],
            "requested_sections": audit["requested_sections"],
            "resolved_sections": audit["final_resolved_sections"],
            "unavailable_sections": audit["unavailable_sections"],
            "dropped_after_facts": audit["dropped_after_facts"],
            "query_count": audit["query_count"],
            "llm_profile": "deepseek",
            "llm_report_intent_call_count": audit["llm_report_intent_call_count"],
            "llm_dax_call_count": audit["llm_dax_call_count"],
            "renderer_llm_call_count": audit["renderer_llm_call_count"],
            "raw_main_tokens": raw_tokens,
            "report_artifact_count_before_cleanup": 1,
            "automation_html_exported": output_html is not None,
        }
    finally:
        if artifact_id is not None:
            await repository.delete(artifact_id)
            try:
                await repository.get(artifact_id)
            except ReportNotFoundError:
                if outcome is not None:
                    outcome["report_artifact_count_after_cleanup"] = 0
            else:
                if outcome is not None:
                    outcome["result"] = "FAIL"
                    outcome["report_artifact_count_after_cleanup"] = 1
        await adapter.aclose()
        await registry.aclose()
        if outcome is not None:
            lifecycle = adapter.runtime_lifecycle_snapshot() or {}
            outcome["runtime_lifecycle_after_close"] = lifecycle
            if (
                lifecycle.get("session_residual") != 0
                or lifecycle.get("active_workers") != 0
            ):
                outcome["result"] = "FAIL"
    if outcome is None:
        raise RuntimeError("real_e2e_missing_outcome")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-model", choices=("simple", "rich"), required=True)
    parser.add_argument("--output-html", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(_run(args.expect_model, args.output_html))
    except Exception as exc:
        result = {
            "result": "FAIL",
            "error_type": getattr(exc, "code", type(exc).__name__),
            "error": str(exc),
            "llm_profile": "deepseek",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
