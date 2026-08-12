"""M2.5 Business Golden smoke through the formal Chat API.

The script uses create_app -> /api/v1/chat -> DeepSeekTurnService ->
TurnPipeline -> ToolGateway -> LocalMCPPowerBIAdapter. Standard output is a
sanitized JSON list and never contains DAX, business values, prompts, raw LLM
responses, model identity, connection details, PBIX paths, or secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


BUSINESS_GOLDEN_CASES: tuple[dict[str, Any], ...] = (
    {
        "case": "total_sales",
        "message": "总销售额是多少？",
        "measure": "Total Sales",
        "dimensions": [],
        "filters": [],
        "sort": None,
        "top_n": None,
        "generalization": False,
    },
    {
        "case": "total_quantity",
        "message": "总共卖了多少件商品？",
        "measure": "Total Quantity",
        "dimensions": [],
        "filters": [],
        "sort": None,
        "top_n": None,
        "generalization": False,
    },
    {
        "case": "category_sales_filter",
        "message": "Electronics 类别的销售额是多少？",
        "measure": "Total Sales",
        "dimensions": [],
        "filters": [("Category", "Electronics")],
        "sort": None,
        "top_n": None,
        "generalization": False,
    },
    {
        "case": "sales_by_category",
        "message": "按类别看销售额。",
        "measure": "Total Sales",
        "dimensions": ["Category"],
        "filters": [],
        "sort": None,
        "top_n": None,
        "generalization": False,
    },
    {
        "case": "top3_products_by_sales",
        "message": "销售额最高的前3个产品是什么？",
        "measure": "Total Sales",
        "dimensions": ["Product"],
        "filters": [],
        "sort": "desc",
        "top_n": 3,
        "generalization": True,
    },
    {
        "case": "quantity_by_product",
        "message": "按产品看总数量。",
        "measure": "Total Quantity",
        "dimensions": ["Product"],
        "filters": [],
        "sort": None,
        "top_n": None,
        "generalization": True,
    },
    {
        "case": "top3_categories_by_quantity",
        "message": "总数量最高的前3个类别是什么？",
        "measure": "Total Quantity",
        "dimensions": ["Category"],
        "filters": [],
        "sort": "desc",
        "top_n": 3,
        "generalization": True,
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


def _filters_match(actual: Any, expected: list[tuple[str, str]]) -> bool:
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    expected_pairs = {(field, value) for field, value in expected}
    actual_pairs = {
        (str(item.get("field")), str(item.get("value")))
        for item in actual
        if isinstance(item, dict) and item.get("operator") == "eq"
    }
    return actual_pairs == expected_pairs


def _dax_shape_matches(dax: str, case: dict[str, Any]) -> bool:
    if f"[{case['measure']}]" not in dax:
        return False
    for dimension in case["dimensions"]:
        if f"[{dimension}]" not in dax:
            return False
    for field, _ in case["filters"]:
        if f"[{field}]" not in dax:
            return False
    top_n = case["top_n"]
    if top_n is not None and re.search(
        rf"\bTOPN\s*\(\s*{top_n}\b", dax, re.IGNORECASE
    ) is None:
        return False
    if case["sort"] == "desc" and re.search(r"\bDESC\b", dax, re.IGNORECASE) is None:
        return False
    if case["sort"] is not None:
        order_pattern = (
            rf"\bORDER\s+BY\s+\[{re.escape(case['measure'])}\]\s+"
            rf"{case['sort']}\s*$"
        )
        if re.search(order_pattern, dax, re.IGNORECASE) is None:
            return False
    return True


async def _run_smoke(selected_case: str | None = None) -> int:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.validators.validation_service import ValidationService
    from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
    from backend.app.main import create_app
    from backend.app.memory.models import MemoryStatus, RuntimeDataMode
    from backend.app.schemas.data_contracts import QueryResult

    class _CapturingProvider(LLMProvider):
        def __init__(self, inner: LLMProvider):
            self._inner = inner
            self.structured_by_task: dict[LLMTask, list[Any]] = {
                task: [] for task in LLMTask
            }

        @property
        def provider_name(self) -> str:
            return self._inner.provider_name

        @property
        def is_mock(self) -> bool:
            return self._inner.is_mock

        async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
            response = await self._inner.generate(request, output_type)
            if response.structured is not None:
                self.structured_by_task[request.task].append(response.structured)
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
        print(json.dumps([{
            "case": "local_prerequisite",
            "passed": False,
            "intent": "",
            "measure_match": False,
            "dimension_match": False,
            "filter_match": False,
            "layer3_pass": False,
            "source_mode": "",
            "answer_provenance_pass": False,
            "call_count": 0,
            "repair_count": 0,
        }], ensure_ascii=False, indent=2))
        return 1

    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    results: list[dict[str, Any]] = []

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        if service is None:
            return 1

        provider = _CapturingProvider(service.llm_provider)
        service.llm_provider = provider

        layer2_results: list[Any] = []
        layer3_results: list[Any] = []
        query_results: list[QueryResult] = []
        validate_layer2 = service.validator.validate_query_plan
        validate_layer3 = service.validator.validate_dax_query_plan_consistency
        gateway_execute = service.tool_gateway.execute

        def _capture_layer2(*args: Any, **kwargs: Any) -> Any:
            result = validate_layer2(*args, **kwargs)
            layer2_results.append(result)
            return result

        def _capture_layer3(*args: Any, **kwargs: Any) -> Any:
            result = validate_layer3(*args, **kwargs)
            layer3_results.append(result)
            return result

        async def _capture_tool(*args: Any, **kwargs: Any) -> Any:
            result = await gateway_execute(*args, **kwargs)
            if isinstance(result, QueryResult):
                query_results.append(result)
            return result

        service.validator.validate_query_plan = _capture_layer2
        service.validator.validate_dax_query_plan_consistency = _capture_layer3
        service.tool_gateway.execute = _capture_tool

        cases = tuple(
            case for case in BUSINESS_GOLDEN_CASES
            if selected_case is None or case["case"] == selected_case
        )

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for index, case in enumerate(cases, start=1):
                starts = {
                    task: len(provider.structured_by_task[task]) for task in LLMTask
                }
                layer2_start = len(layer2_results)
                layer3_start = len(layer3_results)
                result_start = len(query_results)
                request_id = f"m2.5-business-golden-{case['case']}"
                response = await client.post("/api/v1/chat", json={
                    "message": case["message"],
                    "conversation_id": f"m2.5-business-golden-{index}",
                    "request_id": request_id,
                    "semantic_model_key": settings.powerbi_local_semantic_model_key,
                })
                body = response.json()
                memory = await service.pipeline.get_memory_by_request_id(
                    request_id,
                    RuntimeDataMode.REAL,
                )

                plans = provider.structured_by_task[LLMTask.QUERY_PLAN][
                    starts[LLMTask.QUERY_PLAN]:
                ]
                dax_requests = provider.structured_by_task[LLMTask.DAX][
                    starts[LLMTask.DAX]:
                ]
                answers = provider.structured_by_task[LLMTask.ANSWER][
                    starts[LLMTask.ANSWER]:
                ]
                case_query_results = query_results[result_start:]
                plan = plans[-1] if plans else None
                dax_request = dax_requests[-1] if dax_requests else None
                answer = answers[-1] if answers else None
                query_result = case_query_results[-1] if case_query_results else None

                measure_match = bool(
                    plan is not None
                    and plan.semantic_model_key
                    == settings.powerbi_local_semantic_model_key
                    and plan.measures == [case["measure"]]
                )
                dimension_match = bool(
                    plan is not None
                    and plan.dimensions == case["dimensions"]
                    and plan.sort == case["sort"]
                    and plan.top_n == case["top_n"]
                )
                filter_match = bool(
                    plan is not None
                    and _filters_match(
                        [item.model_dump(mode="json") for item in plan.filters],
                        case["filters"],
                    )
                )
                layer2_pass = bool(
                    layer2_results[layer2_start:]
                    and layer2_results[-1].is_valid
                )
                layer3_pass = bool(
                    layer3_results[layer3_start:]
                    and layer3_results[-1].is_valid
                    and dax_request is not None
                    and _dax_shape_matches(dax_request.dax, case)
                )
                query_result_pass = bool(
                    query_result is not None
                    and query_result.source_mode == "real"
                    and query_result.error is None
                )
                answer_provenance_pass = bool(
                    answer is not None
                    and query_result is not None
                    and ValidationService().validate_answer_strict(
                        answer, query_result
                    ).is_valid
                )
                usage = body.get("usage") or {}
                passed = all((
                    response.status_code == 200,
                    body.get("terminal_state") == "completed",
                    body.get("intent") == "data_question",
                    body.get("source_mode") == "real",
                    body.get("tool_sequence") == [
                        "get_semantic_model_schema",
                        "execute_dax",
                    ],
                    body.get("memory_commit") is True,
                    memory is not None,
                    memory is not None
                    and memory.state_status == MemoryStatus.COMMITTED,
                    measure_match,
                    dimension_match,
                    filter_match,
                    layer2_pass,
                    layer3_pass,
                    query_result_pass,
                    answer_provenance_pass,
                ))
                results.append({
                    "case": case["case"],
                    "passed": passed,
                    "intent": body.get("intent", ""),
                    "measure_match": measure_match,
                    "dimension_match": dimension_match,
                    "filter_match": filter_match,
                    "layer3_pass": layer3_pass,
                    "source_mode": body.get("source_mode", ""),
                    "answer_provenance_pass": answer_provenance_pass,
                    "call_count": int(usage.get("call_count", 0)),
                    "repair_count": int(usage.get("repair_count", 0)),
                })

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results and all(item["passed"] for item in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=[case["case"] for case in BUSINESS_GOLDEN_CASES],
        default=None,
    )
    args = parser.parse_args()
    return asyncio.run(_run_smoke(args.case))


if __name__ == "__main__":
    raise SystemExit(main())
