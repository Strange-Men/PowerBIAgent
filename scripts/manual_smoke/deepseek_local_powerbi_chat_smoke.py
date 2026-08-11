"""M2.4 real DeepSeek + Local Power BI chat smoke through the formal API.

The script uses create_app -> /api/v1/chat -> DeepSeekTurnService ->
TurnPipeline -> ToolGateway -> LocalMCPPowerBIAdapter. It never prints prompts,
DAX, answers, model identity, connection details, business values, or secrets.
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
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


_CASES = (
    {
        "case": "total_sales",
        "message": "总销售额是多少？",
        "expected_measure": "Total Sales",
        "expected_filter": None,
    },
    {
        "case": "total_quantity",
        "message": "总共卖了多少件商品？",
        "expected_measure": "Total Quantity",
        "expected_filter": None,
    },
    {
        "case": "category_sales_filter",
        "message": "Electronics 类别的销售额是多少？",
        "expected_measure": "Total Sales",
        "expected_filter": ("Category", "Electronics"),
    },
)


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


def _safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _write_local_trace(request_id: str, trace: dict[str, Any]) -> str:
    """Persist an exact smoke trace outside the repository for local recovery."""
    trace_dir = Path(tempfile.gettempdir()) / "powerbiagent-m2.4-smoke-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    recovery_key = _safe_hash(request_id)
    trace_path = trace_dir / f"{recovery_key}.json"
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return recovery_key


def _safe_query_plan(raw: Any) -> dict[str, Any] | None:
    """只保留 QueryPlan 契约字段，不输出 Prompt/响应正文或其他元数据。"""
    if not isinstance(raw, dict):
        return None
    allowed = (
        "normalized_question",
        "semantic_model_key",
        "measures",
        "dimensions",
        "filters",
        "time_range",
        "sort",
        "top_n",
        "comparison_mode",
        "requested_template",
        "inherited_context",
        "is_mock",
    )
    return {key: raw.get(key) for key in allowed if key in raw}


def _safe_answer_provenance(raw: Any) -> dict[str, Any] | None:
    """Answer 诊断只保留 metric 名和 source_field，不输出业务值/文本。"""
    if not isinstance(raw, dict):
        return None
    metrics = raw.get("metrics")
    evidence = raw.get("evidence")
    provenance = evidence.get("metric_provenance") if isinstance(evidence, dict) else None
    source_fields: dict[str, Any] = {}
    if isinstance(provenance, dict):
        for metric_name, item in provenance.items():
            if isinstance(item, dict):
                source_fields[str(metric_name)] = item.get("source_field")
    return {
        "metric_names": sorted(str(name) for name in metrics) if isinstance(metrics, dict) else [],
        "source_fields": source_fields,
    }


async def _run_smoke(selected_case: str | None = None, diagnostics: bool = False) -> int:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import SchemaInput, TOOL_NAME_SCHEMA
    from backend.app.intent.models import IntentType
    from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
    from backend.app.main import create_app
    from backend.app.memory.models import RuntimeDataMode

    class _CapturingProvider(LLMProvider):
        """Manual-smoke-only read-through observer for sanitized QueryPlan diagnostics."""

        def __init__(self, inner: LLMProvider):
            self._inner = inner
            self.query_plan_attempts: list[dict[str, Any]] = []
            self.dax_attempts: list[dict[str, Any]] = []
            self.answer_attempts: list[dict[str, Any]] = []
            self.query_result_columns: list[str] = []

        @property
        def provider_name(self) -> str:
            return self._inner.provider_name

        @property
        def is_mock(self) -> bool:
            return self._inner.is_mock

        async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
            response = await self._inner.generate(request, output_type)
            if request.task == LLMTask.QUERY_PLAN:
                try:
                    raw = json.loads(response.content)
                except (TypeError, json.JSONDecodeError):
                    raw = None
                structured = (
                    response.structured.model_dump(mode="json")
                    if response.structured is not None
                    else None
                )
                self.query_plan_attempts.append({
                    "raw_query_plan": _safe_query_plan(raw),
                    "parsed_query_plan": _safe_query_plan(structured),
                })
            elif request.task == LLMTask.DAX:
                try:
                    raw = json.loads(response.content)
                except (TypeError, json.JSONDecodeError):
                    raw = None
                structured = (
                    response.structured.model_dump(mode="json")
                    if response.structured is not None
                    else None
                )
                self.dax_attempts.append({
                    "raw_dax_request": raw if isinstance(raw, dict) else None,
                    "parsed_dax_request": (
                        structured if isinstance(structured, dict) else None
                    ),
                })
            elif request.task == LLMTask.ANSWER:
                marker = "- QueryResult.columns: "
                for message in request.messages:
                    for line in message.get("content", "").splitlines():
                        if line.startswith(marker):
                            try:
                                parsed_columns = json.loads(line[len(marker):])
                            except json.JSONDecodeError:
                                parsed_columns = None
                            if (
                                isinstance(parsed_columns, list)
                                and all(isinstance(item, str) for item in parsed_columns)
                            ):
                                self.query_result_columns = parsed_columns
                try:
                    raw = json.loads(response.content)
                except (TypeError, json.JSONDecodeError):
                    raw = None
                structured = (
                    response.structured.model_dump(mode="json")
                    if response.structured is not None
                    else None
                )
                self.answer_attempts.append({
                    "raw_answer_provenance": _safe_answer_provenance(raw),
                    "parsed_answer_provenance": _safe_answer_provenance(structured),
                })
            return response

    settings = Settings(
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    prerequisites_ready = (
        sys.platform == "win32"
        and settings.is_deepseek_configured
        and settings.is_powerbi_local_mcp_configured
        and shutil.which(settings.powerbi_local_mcp_executable) is not None
        and _powerbi_desktop_is_running()
    )
    if not prerequisites_ready:
        print(json.dumps({
            "overall_success": False,
            "error_type": "LOCAL_PREREQUISITE",
        }, ensure_ascii=False, indent=2))
        return 1

    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    results: list[dict[str, Any]] = []
    total_llm_calls = 0

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        if service is None:
            print(json.dumps({
                "overall_success": False,
                "error_type": "CONFIGURATION_NOT_READY",
            }, ensure_ascii=False, indent=2))
            return 1

        capturing_provider = _CapturingProvider(service.llm_provider)
        service.llm_provider = capturing_provider
        layer3_attempts: list[dict[str, Any]] = []
        validate_layer3 = service.validator.validate_dax_query_plan_consistency

        def _capture_layer3(dax_request: Any, plan: Any, schema: Any) -> Any:
            result = validate_layer3(dax_request, plan, schema)
            layer3_attempts.append({
                "valid": result.is_valid,
                "error_code": result.error_code,
                "error_codes": [
                    error.split(":", 1)[0] for error in result.errors
                ],
            })
            return result

        service.validator.validate_dax_query_plan_consistency = _capture_layer3

        cases = tuple(
            case for case in _CASES
            if selected_case is None or case["case"] == selected_case
        )

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            for index, case in enumerate(cases, start=1):
                query_plan_start = len(capturing_provider.query_plan_attempts)
                dax_start = len(capturing_provider.dax_attempts)
                answer_start = len(capturing_provider.answer_attempts)
                layer3_start = len(layer3_attempts)
                capturing_provider.query_result_columns = []
                request_id = f"m2.4-real-chat-{case['case']}"
                payload = {
                    "message": case["message"],
                    "conversation_id": f"m2.4-real-conversation-{index}",
                    "request_id": request_id,
                    "semantic_model_key": settings.powerbi_local_semantic_model_key,
                }
                response = await client.post("/api/v1/chat", json=payload)
                body = response.json()
                memory = await service.pipeline.get_memory_by_request_id(
                    request_id,
                    RuntimeDataMode.REAL,
                )

                measure_match = bool(
                    memory is not None
                    and case["expected_measure"] in memory.measures
                )
                dax_measure_reference = bool(
                    memory is not None
                    and memory.last_dax
                    and f"[{case['expected_measure']}]" in memory.last_dax
                )
                expected_filter = case["expected_filter"]
                filter_match = True
                if expected_filter is not None:
                    filter_field, filter_value = expected_filter
                    filter_match = bool(
                        memory is not None
                        and any(
                            item.get("field") == filter_field
                            and item.get("value") == filter_value
                            for item in memory.filters
                        )
                        and memory.last_dax
                        and f"[{filter_field}]" in memory.last_dax
                    )

                usage = body.get("usage") or {}
                call_count = int(usage.get("call_count", 0))
                total_llm_calls += call_count
                success = all((
                    response.status_code == 200,
                    body.get("terminal_state") == "completed",
                    body.get("source_mode") == "real",
                    body.get("memory_commit") is True,
                    body.get("tool_sequence") == [
                        "get_semantic_model_schema",
                        "execute_dax",
                    ],
                    measure_match,
                    dax_measure_reference,
                    filter_match,
                    1 <= call_count <= 5,
                ))
                results.append({
                    "case": case["case"],
                    "success": success,
                    "http_status": response.status_code,
                    "terminal_state": body.get("terminal_state", ""),
                    "source_mode": body.get("source_mode", ""),
                    "measure_match": measure_match,
                    "filter_match": filter_match,
                    "dax_measure_reference": dax_measure_reference,
                    "call_count": call_count,
                    "repair_count": int(usage.get("repair_count", 0)),
                    "error_type": body.get("error_type"),
                    "request_id_hash": _safe_hash(request_id),
                })
                recovery_key = _write_local_trace(
                    request_id,
                    {
                        "request_id": request_id,
                        "case": case["case"],
                        "query_plan_attempts": capturing_provider.query_plan_attempts[
                            query_plan_start:
                        ],
                        "dax_attempts": capturing_provider.dax_attempts[dax_start:],
                        "layer3_attempts": layer3_attempts[layer3_start:],
                        "query_result": {
                            "terminal_state": body.get("terminal_state"),
                            "source_mode": body.get("source_mode"),
                            "error_type": body.get("error_type"),
                            "columns": capturing_provider.query_result_columns,
                            "tool_sequence": body.get("tool_sequence"),
                        },
                        "answer_attempts": capturing_provider.answer_attempts[
                            answer_start:
                        ],
                        "failure_stage": memory.failure_stage if memory else None,
                        "validator_failure": memory.failure_reason if memory else None,
                    },
                )
                results[-1]["local_trace_written"] = True
                results[-1]["local_trace_recovery_key"] = recovery_key

                if diagnostics:
                    schema = await service.tool_gateway.execute(
                        TOOL_NAME_SCHEMA,
                        ToolExecutionContext(
                            trace_id="m2.4-schema-diagnostic",
                            request_id=f"{request_id}-schema-diagnostic",
                            conversation_id=payload["conversation_id"],
                            runtime_mode=RuntimeDataMode.REAL,
                            intent=IntentType.DATA_QUESTION,
                            user=service._user_context,
                        ),
                        SchemaInput(
                            semantic_model_key=settings.powerbi_local_semantic_model_key
                        ),
                    )
                    total_sales_schema = [
                        {
                            "table": table.name,
                            "table_hidden": table.is_hidden,
                            "table_system_managed": table.is_system_managed,
                            "name": measure.name,
                            "data_type": measure.data_type,
                            "is_hidden": measure.is_hidden,
                            "expression_nonempty": bool(measure.expression.strip()),
                        }
                        for table in schema.tables
                        for measure in table.measures
                        if measure.name == "Total Sales"
                    ]
                    results[-1]["diagnostics"] = {
                        "query_plan_attempts": (
                            capturing_provider.query_plan_attempts
                            if capturing_provider is not None
                            else []
                        ),
                        "query_result_columns": (
                            capturing_provider.query_result_columns
                            if capturing_provider is not None
                            else []
                        ),
                        "answer_attempts": (
                            capturing_provider.answer_attempts
                            if capturing_provider is not None
                            else []
                        ),
                        "failure_stage": memory.failure_stage if memory else None,
                        "validator_failure": memory.failure_reason if memory else None,
                        "schema": {
                            "semantic_model_key": schema.key,
                            "total_sales": total_sales_schema,
                        },
                    }

                if selected_case is None and index == 1:
                    replay = await client.post("/api/v1/chat", json=payload)
                    replay_body = replay.json()
                    replay_usage = replay_body.get("usage") or {}
                    replay_success = all((
                        replay.status_code == 200,
                        replay_body.get("idempotent_replay") is True,
                        replay_body.get("source_mode") == "real",
                        replay_body.get("tool_sequence") == [],
                        not replay_usage,
                    ))
                    results.append({
                        "case": "idempotent_replay",
                        "success": replay_success,
                        "http_status": replay.status_code,
                        "terminal_state": replay_body.get("terminal_state", ""),
                        "source_mode": replay_body.get("source_mode", ""),
                        "idempotent_replay": replay_body.get("idempotent_replay", False),
                        "replay_call_count": int(replay_usage.get("call_count", 0)),
                        "error_type": replay_body.get("error_type"),
                        "request_id_hash": _safe_hash(request_id),
                    })

    overall_success = (
        health.status_code == 200
        and all(item["success"] for item in results)
    )
    print(json.dumps({
        "overall_success": overall_success,
        "health_status": health.status_code,
        "version": settings.version,
        "llm_mode": settings.llm_mode.value,
        "powerbi_mode": settings.powerbi_mode.value,
        "deepseek_call_count": total_llm_calls,
        "cases": results,
    }, ensure_ascii=False, indent=2))
    return 0 if overall_success else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=[case["case"] for case in _CASES],
        default=None,
    )
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run_smoke(args.case, args.diagnostics))


if __name__ == "__main__":
    raise SystemExit(main())
