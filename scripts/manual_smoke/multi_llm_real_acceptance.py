"""M5.8 DeepSeek/Kimi acceptance against the currently open Rich PBIX.

The runner uses the formal application and Chat API, observes the deterministic
Power BI boundary, and never prints prompts, answers, result values, endpoints,
headers, or credentials.  It compares canonical plans and normalized result
digests across providers; it does not depend on or modify a frozen numeric
oracle from an older PBIX fixture.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PROFILES = ("deepseek", "kimi-k2.6")
PROTOCOL = "openai_chat_completions"
RICH_MODEL_DISPLAY_NAME = "PowerBIAgent_M3_Rich_Test"


@dataclass(frozen=True)
class Case:
    key: str
    message: str
    expected: dict[str, Any]


CASES = (
    Case("total", "总销售额是多少？", {"measures": ["Total Sales"]}),
    Case(
        "absolute_month",
        "2025年5月销售额",
        {
            "measures": ["Total Sales"],
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    ),
    Case(
        "region",
        "按区域看销售额",
        {"measures": ["Total Sales"], "dimensions": ["Region"]},
    ),
    Case(
        "monthly_trend",
        "每个月销售额趋势",
        {
            "measures": ["Total Sales"],
            "dimensions": ["YearMonth"],
            "dimension_tables": {"YearMonth": "Date"},
            "dimension_order": "asc",
        },
    ),
    Case(
        "top3_product",
        "销售额最高的前3个产品是什么？",
        {
            "measures": ["Total Sales"],
            "dimensions": ["Product"],
            "sort": "desc",
            "top_n": 3,
        },
    ),
)


def _desktop_running() -> bool:
    if sys.platform != "win32":
        return False
    result = subprocess.run(
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
    return result.returncode == 0


def _plan_signature(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: plan.get(key)
        for key in (
            "measures",
            "dimensions",
            "dimension_tables",
            "dimension_order",
            "filters",
            "time_range",
            "sort",
            "top_n",
            "comparison_mode",
            "requested_template",
            "grounding_authority",
        )
    }


def _matches_expected(plan: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        actual = plan.get(key)
        if key == "time_range":
            if not isinstance(actual, dict):
                return False
            if any(actual.get(field) != wanted for field, wanted in value.items()):
                return False
        elif actual != value:
            return False
    return plan.get("grounding_authority") == "semantic_catalog"


def _result_digest(result: Any) -> str:
    safe_contract = {
        "semantic_model_key": result.semantic_model_key,
        "source_mode": result.source_mode,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "error": result.error.model_dump(mode="json") if result.error else None,
    }
    serialized = json.dumps(
        safe_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _profile_evidence(body: dict[str, Any], profile: str, public_model: str) -> bool:
    if (
        body.get("llm_profile_key") != profile
        or body.get("llm_model") != public_model
        or body.get("llm_provider_protocol") != PROTOCOL
    ):
        return False
    calls = (body.get("usage") or {}).get("calls") or []
    return all(
        call.get("profile_key") == profile
        and call.get("provider_name") == profile
        and call.get("provider_protocol") == PROTOCOL
        for call in calls
    )


def _successful_turn(
    response: Any,
    body: dict[str, Any],
    result: Any,
    profile: str,
    public_model: str,
) -> bool:
    audit = body.get("execution_audit") or {}
    per_task = (body.get("usage") or {}).get("per_task") or {}
    return bool(
        response.status_code == 200
        and body.get("terminal_state") == "completed"
        and body.get("memory_commit") is True
        and body.get("source_mode") == "real"
        and _profile_evidence(body, profile, public_model)
        and result is not None
        and result.error is None
        and result.source_mode == "real"
        and audit.get("deterministic_dax") is True
        and audit.get("layer3_pass") is True
        and audit.get("query_result_success") is True
        and audit.get("factual_validation_pass") is True
        and audit.get("llm_dax_call_count") == 0
        and per_task.get("dax", 0) == 0
        and per_task.get("answer", 0) == 0
    )


async def _run(*, boundaries_only: bool = False) -> tuple[int, dict[str, Any]]:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import (
        LLMMode,
        PersistenceBackend,
        PowerBIMode,
        Settings,
    )
    from backend.app.harness.tool_registry import TOOL_NAME_DAX
    from backend.app.main import create_app
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.schemas.data_contracts import QueryResult

    temporary = tempfile.TemporaryDirectory(prefix="powerbiagent-m58-real-")
    temp_root = Path(temporary.name)
    try:
        settings = Settings(
            llm_mode=LLMMode.OPENAI_COMPATIBLE,
            llm_default_profile="deepseek",
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            persistence_backend=PersistenceBackend.MEMORY,
            report_artifacts_path=str(temp_root / "reports"),
            presentation_localization_registry_path=str(
                temp_root / "runtime" / "display_localizations.json"
            ),
        )
        configured = {
            profile: settings.is_llm_profile_configured(profile)
            for profile in PROFILES
        }
        ready = bool(
            sys.platform == "win32"
            and all(configured.values())
            and settings.is_powerbi_local_mcp_configured
            and shutil.which(settings.powerbi_local_mcp_executable) is not None
            and _desktop_running()
        )
        if not ready:
            return 1, {
                "passed": False,
                "status": "local_prerequisite_missing",
                "profile_configured": configured,
                "residual": 0,
            }

        app = create_app(settings=settings)
        captured: dict[str, list[QueryResult]] = {}
        profile_results: dict[str, dict[str, Any]] = {}
        profile_mismatch_count = 0

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            original_gateway_execute = service.tool_gateway.execute

            async def observed_gateway_execute(
                tool_name: str,
                execution_context: Any,
                input_data: Any,
                trace: Any = None,
                controller: Any = None,
            ) -> Any:
                result = await original_gateway_execute(
                    tool_name,
                    execution_context,
                    input_data,
                    trace=trace,
                    controller=controller,
                )
                if tool_name == TOOL_NAME_DAX and isinstance(result, QueryResult):
                    captured.setdefault(execution_context.request_id, []).append(
                        result.model_copy(deep=True)
                    )
                return result

            service.tool_gateway.execute = observed_gateway_execute
            transport = ASGITransport(app=app, raise_app_exceptions=True)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                profile_response = await client.get("/api/v1/llm-profiles")
                profile_catalog = {
                    item["profile_key"]: item
                    for item in profile_response.json().get("items", [])
                }
                discovery_response = await client.get("/api/v1/semantic-models")
                selectable = [
                    item
                    for item in discovery_response.json().get("items", [])
                    if item.get("selectable") is True
                ]
                rich_models = [
                    item
                    for item in selectable
                    if item.get("display_name") == RICH_MODEL_DISPLAY_NAME
                ]
                if profile_response.status_code != 200 or any(
                    not profile_catalog.get(profile, {}).get("available")
                    for profile in PROFILES
                ):
                    return 1, {
                        "passed": False,
                        "status": "llm_profile_unavailable",
                        "profile_configured": configured,
                        "residual": 0,
                    }
                if discovery_response.status_code != 200 or len(rich_models) != 1:
                    return 1, {
                        "passed": False,
                        "status": "rich_semantic_model_selection_required",
                        "selectable_model_count": len(selectable),
                        "rich_model_match_count": len(rich_models),
                        "profile_configured": configured,
                        "residual": 0,
                    }
                semantic_model_key = rich_models[0]["key"]

                async def post(
                    *,
                    profile: str,
                    message: str,
                    case_key: str,
                    conversation_id: str | None = None,
                    report_template_key: str | None = None,
                ) -> dict[str, Any]:
                    nonlocal profile_mismatch_count
                    request_id = f"m58-real-{case_key}-{uuid.uuid4().hex}"
                    response = await client.post(
                        "/api/v1/chat",
                        json={
                            "message": message,
                            "conversation_id": conversation_id
                            or f"m58-real-{case_key}-{uuid.uuid4().hex}",
                            "request_id": request_id,
                            "semantic_model_key": semantic_model_key,
                            "llm_profile_key": profile,
                            "report_template_key": report_template_key,
                        },
                    )
                    body = response.json()
                    if body.get("llm_profile_key") != profile:
                        profile_mismatch_count += 1
                    return {
                        "response": response,
                        "body": body,
                        "request_id": request_id,
                        "results": captured.get(request_id, []),
                    }

                for profile in PROFILES:
                    public_model = profile_catalog[profile]["model"]
                    cases: dict[str, Any] = {}
                    for case in (() if boundaries_only else CASES):
                        observed = await post(
                            profile=profile,
                            message=case.message,
                            case_key=f"{profile}-{case.key}",
                        )
                        body = observed["body"]
                        result = observed["results"][-1] if observed["results"] else None
                        plan = (body.get("execution_audit") or {}).get(
                            "canonical_query_plan"
                        ) or {}
                        passed = bool(
                            _successful_turn(
                                observed["response"], body, result, profile, public_model
                            )
                            and _matches_expected(plan, case.expected)
                        )
                        cases[case.key] = {
                            "passed": passed,
                            "http_status": observed["response"].status_code,
                            "terminal_state": body.get("terminal_state"),
                            "error_type": body.get("error_type"),
                            "profile_match": _profile_evidence(
                                body, profile, public_model
                            ),
                            "plan": _plan_signature(plan),
                            "result_digest": _result_digest(result) if result else None,
                        }

                    conversation_id = f"m58-real-chain-{profile}-{uuid.uuid4().hex}"
                    chain_messages = (
                        ()
                        if boundaries_only
                        else (
                            ("absolute", "2025年5月销售额"),
                            ("region_followup", "那华南区呢"),
                            ("time_replace", "换成去年"),
                            ("ranking_followup", "前三个产品呢"),
                        )
                    )
                    chain: list[dict[str, Any]] = []
                    for key, message in chain_messages:
                        observed = await post(
                            profile=profile,
                            message=message,
                            case_key=f"{profile}-chain-{key}",
                            conversation_id=conversation_id,
                        )
                        body = observed["body"]
                        result = observed["results"][-1] if observed["results"] else None
                        plan = (body.get("execution_audit") or {}).get(
                            "canonical_query_plan"
                        ) or {}
                        chain.append(
                            {
                                "key": key,
                                "passed": _successful_turn(
                                    observed["response"],
                                    body,
                                    result,
                                    profile,
                                    public_model,
                                ),
                                "http_status": observed["response"].status_code,
                                "terminal_state": body.get("terminal_state"),
                                "error_type": body.get("error_type"),
                                "plan": _plan_signature(plan),
                                "result_digest": _result_digest(result) if result else None,
                            }
                        )
                    chain_contract = bool(
                        boundaries_only
                        or (
                        len(chain) == 4
                        and all(item["passed"] for item in chain)
                        and chain[0]["plan"].get("time_range", {}).get("start_date")
                        == "2025-05-01"
                        and chain[1]["plan"].get("time_range")
                        == chain[0]["plan"].get("time_range")
                        and len(chain[1]["plan"].get("filters") or []) == 1
                        and chain[1]["plan"]["filters"][0].get("field") == "Region"
                        and chain[1]["plan"]["filters"][0].get("operator") == "eq"
                        and bool(chain[1]["plan"]["filters"][0].get("value"))
                        and chain[2]["plan"].get("filters")
                        == chain[1]["plan"].get("filters")
                        and chain[2]["plan"].get("time_range")
                        != chain[1]["plan"].get("time_range")
                        and chain[3]["plan"].get("measures") == ["Total Sales"]
                        and chain[3]["plan"].get("dimensions") == ["Product"]
                        and chain[3]["plan"].get("sort") == "desc"
                        and chain[3]["plan"].get("top_n") == 3
                        and chain[3]["plan"].get("filters")
                        == chain[2]["plan"].get("filters")
                        and chain[3]["plan"].get("time_range")
                        == chain[2]["plan"].get("time_range")
                        )
                    )

                    unknown_conversation = (
                        f"m58-real-unknown-{profile}-{uuid.uuid4().hex}"
                    )
                    unknown_before = await service.pipeline.get_latest_committed_memory(
                        unknown_conversation, RuntimeDataMode.REAL
                    )
                    unknown = await post(
                        profile=profile,
                        message="火星区销售额",
                        case_key=f"{profile}-unknown-member",
                        conversation_id=unknown_conversation,
                    )
                    unknown_after = await service.pipeline.get_latest_committed_memory(
                        unknown_conversation, RuntimeDataMode.REAL
                    )
                    unknown_audit = unknown["body"].get("execution_audit") or {}
                    unknown_passed = bool(
                        unknown["response"].status_code == 200
                        and unknown["body"].get("terminal_state")
                        == "clarification_required"
                        and unknown["body"].get("memory_commit") is False
                        and _profile_evidence(
                            unknown["body"], profile, public_model
                        )
                        and not unknown["results"]
                        and unknown_before is None
                        and unknown_after is None
                        and unknown_audit.get("dax_executed") is False
                    )

                    unsupported_conversation = (
                        f"m58-real-unsupported-{profile}-{uuid.uuid4().hex}"
                    )
                    unsupported = await post(
                        profile=profile,
                        message="预测明年销售额",
                        case_key=f"{profile}-unsupported",
                        conversation_id=unsupported_conversation,
                    )
                    unsupported_after = (
                        await service.pipeline.get_latest_committed_memory(
                            unsupported_conversation, RuntimeDataMode.REAL
                        )
                    )
                    unsupported_audit = unsupported["body"].get("execution_audit") or {}
                    unsupported_passed = bool(
                        unsupported["response"].status_code == 200
                        and unsupported["body"].get("terminal_state") == "unsupported"
                        and unsupported["body"].get("memory_commit") is False
                        and unsupported["body"].get("llm_profile_key") == profile
                        and not unsupported["results"]
                        and unsupported_after is None
                        and unsupported_audit.get("dax_executed") is False
                    )

                    report = await post(
                        profile=profile,
                        message="生成销售分析报告",
                        case_key=f"{profile}-report",
                        report_template_key="sales_report",
                    )
                    report_body = report["body"]
                    report_contract = report_body.get("report") or {}
                    report_audit = report_body.get("execution_audit") or {}
                    report_passed = bool(
                        report["response"].status_code == 200
                        and report_body.get("terminal_state") == "completed"
                        and report_body.get("memory_commit") is True
                        and _profile_evidence(report_body, profile, public_model)
                        and report_contract.get("template_key") == "sales_report"
                        and bool(report_contract.get("report_id"))
                        and report_audit.get("deterministic_dax") is True
                        and report_audit.get("layer3_pass") is True
                        and report_audit.get("factual_validation_pass") is True
                        and report_audit.get("llm_dax_call_count") == 0
                        and report_audit.get("renderer_llm_call_count") == 0
                    )
                    profile_results[profile] = {
                        "passed": bool(
                            all(item["passed"] for item in cases.values())
                            and chain_contract
                            and unknown_passed
                            and unsupported_passed
                            and report_passed
                        ),
                        "cases": cases,
                        "multi_turn": {
                            "passed": chain_contract,
                            "turns": chain,
                        },
                        "unknown_member_fail_closed": unknown_passed,
                        "unsupported_fail_closed": unsupported_passed,
                        "report": {
                            "passed": report_passed,
                            "http_status": report["response"].status_code,
                            "terminal_state": report_body.get("terminal_state"),
                            "error_type": report_body.get("error_type"),
                            "template_key": report_contract.get("template_key"),
                        },
                    }

                compared_keys = [] if boundaries_only else [case.key for case in CASES]
                cross_provider_cases = {
                    key: bool(
                        profile_results["deepseek"]["cases"][key]["plan"]
                        == profile_results["kimi-k2.6"]["cases"][key]["plan"]
                        and profile_results["deepseek"]["cases"][key]["result_digest"]
                        == profile_results["kimi-k2.6"]["cases"][key]["result_digest"]
                    )
                    for key in compared_keys
                }

                concurrent = await asyncio.gather(
                    post(
                        profile="deepseek",
                        message="总销售额是多少？",
                        case_key="concurrent-deepseek",
                    ),
                    post(
                        profile="kimi-k2.6",
                        message="总销售额是多少？",
                        case_key="concurrent-kimi",
                    ),
                )
                concurrent_passed = True
                concurrent_digests: list[str] = []
                for profile, item in zip(PROFILES, concurrent, strict=True):
                    result = item["results"][-1] if item["results"] else None
                    concurrent_passed = bool(
                        concurrent_passed
                        and _successful_turn(
                            item["response"],
                            item["body"],
                            result,
                            profile,
                            profile_catalog[profile]["model"],
                        )
                    )
                    if result is not None:
                        concurrent_digests.append(_result_digest(result))
                concurrent_passed = bool(
                    concurrent_passed
                    and len(concurrent_digests) == 2
                    and len(set(concurrent_digests)) == 1
                )

                switch_conversation = f"m58-real-switch-{uuid.uuid4().hex}"
                switch_first = await post(
                    profile="deepseek",
                    message="2025年5月销售额",
                    case_key="switch-deepseek",
                    conversation_id=switch_conversation,
                )
                first_memory = await service.pipeline.get_latest_committed_memory(
                    switch_conversation, RuntimeDataMode.REAL
                )
                switch_second = await post(
                    profile="kimi-k2.6",
                    message="前三个产品呢",
                    case_key="switch-kimi",
                    conversation_id=switch_conversation,
                )
                second_memory = await service.pipeline.get_latest_committed_memory(
                    switch_conversation, RuntimeDataMode.REAL
                )
                first_body = switch_first["body"]
                second_body = switch_second["body"]
                first_result = (
                    switch_first["results"][-1] if switch_first["results"] else None
                )
                second_result = (
                    switch_second["results"][-1] if switch_second["results"] else None
                )
                second_plan = (second_body.get("execution_audit") or {}).get(
                    "canonical_query_plan"
                ) or {}
                provider_fact_keys = {
                    key
                    for key in second_plan
                    if any(token in key.lower() for token in ("provider", "model_session"))
                }
                switch_passed = bool(
                    _successful_turn(
                        switch_first["response"],
                        first_body,
                        first_result,
                        "deepseek",
                        profile_catalog["deepseek"]["model"],
                    )
                    and _successful_turn(
                        switch_second["response"],
                        second_body,
                        second_result,
                        "kimi-k2.6",
                        profile_catalog["kimi-k2.6"]["model"],
                    )
                    and first_memory is not None
                    and second_memory is not None
                    and second_memory.memory_version == first_memory.memory_version + 1
                    and second_memory.llm_provider == "kimi-k2.6"
                    and second_memory.measures == ["Total Sales"]
                    and second_memory.time_range == first_memory.time_range
                    and second_memory.dimensions == ["Product"]
                    and second_memory.sort == "desc"
                    and second_memory.top_n == 3
                    and not provider_fact_keys
                )

        passed = bool(
            all(item["passed"] for item in profile_results.values())
            and all(cross_provider_cases.values())
            and concurrent_passed
            and switch_passed
            and profile_mismatch_count == 0
        )
        summary = {
            "passed": passed,
            "status": "pass" if passed else "acceptance_failed",
            "focus": "boundaries_only" if boundaries_only else "full",
            "profile_configured": configured,
            "profiles": profile_results,
            "cross_provider": {
                "passed": all(cross_provider_cases.values()),
                "cases": cross_provider_cases,
            },
            "concurrent_isolation": concurrent_passed,
            "mid_conversation_switch": switch_passed,
            "profile_mismatch_count": profile_mismatch_count,
            "raw_business_values_printed": False,
        }
    finally:
        temporary.cleanup()

    residual = int(temp_root.exists())
    summary["residual"] = residual
    summary["passed"] = bool(summary["passed"] and residual == 0)
    if not summary["passed"]:
        summary["status"] = "acceptance_failed"
    return (0 if summary["passed"] else 1), summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundaries-only", action="store_true")
    args = parser.parse_args()
    exit_code, summary = asyncio.run(_run(boundaries_only=args.boundaries_only))
    serialized = json.dumps(summary, ensure_ascii=False, indent=2)
    lowered = serialized.lower()
    if any(secret_marker in lowered for secret_marker in ("authorization", "bearer", "api_key")):
        print(json.dumps({"passed": False, "status": "unsafe_output_blocked"}))
        return 1
    print(serialized)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
