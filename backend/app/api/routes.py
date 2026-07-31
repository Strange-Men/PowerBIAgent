"""API 路由 — M0.4

GET  /health           — 健康检查
POST /api/v1/chat      — 非流式对话接口
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.api.dependencies import get_mock_turn_service, get_settings_dep
from backend.app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse
from backend.app.application.mock_turn_service import MockScenarioSelection
from backend.app.config.settings import LLMMode, PowerBIMode, Settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings_dep)):
    """健康检查 — Mock 模式正常返回 200，不调用 LLM 或 Power BI"""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env.value,
        version=settings.version,
        llm_mode=settings.llm_mode.value,
        powerbi_mode=settings.powerbi_mode.value,
        harness_mode=settings.harness_mode.value,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: Settings = Depends(get_settings_dep),
):
    """非流式对话 — Mock 模式完整链路

    请求经过 MockTurnService → 意图识别 → 工具执行 → 回答/报表。
    Real 模式未实现时返回 503。
    """

    # Real 模式未实现 → 明确拒绝
    if settings.llm_mode != LLMMode.MOCK or settings.powerbi_mode != PowerBIMode.MOCK:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Real mode not yet implemented. Only Mock mode is available in M0.4.",
                "error_type": "real_mode_unavailable",
            },
        )

    service = get_mock_turn_service()

    # 生成 ID（如果未提供）
    conversation_id = body.conversation_id or str(uuid.uuid4())
    request_id = body.request_id or str(uuid.uuid4())

    # 根据是否提供 report_template_key 判断场景
    if body.report_template_key:
        scenario = MockScenarioSelection(
            intent_key="report_generation",
            query_plan_key="report_generation",
            dax_key="report_generation",
            powerbi_key="report_generation",
            response_key="report_generation",
        )
    else:
        scenario = MockScenarioSelection(
            intent_key="data_question",
            query_plan_key="data_question",
            dax_key="data_question",
            powerbi_key="data_question",
            response_key="data_question",
        )

    try:
        result = await service.execute(
            message=body.message,
            conversation_id=conversation_id,
            request_id=request_id,
            semantic_model_key=body.semantic_model_key,
            report_template_key=body.report_template_key,
            scenario=scenario,
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Internal server error",
                "error_type": "internal_error",
                "request_id": request_id,
            },
        )

    return ChatResponse(
        request_id=result.get("request_id", request_id),
        conversation_id=result.get("conversation_id", conversation_id),
        terminal_state=result.get("terminal_state", "completed"),
        intent=result.get("intent", ""),
        response_type=result.get("response_type", ""),
        answer=result.get("last_result_summary"),
        error_type=result.get("error_type"),
        tool_sequence=result.get("tool_sequence", []),
        memory_commit=result.get("memory_commit", False),
        trace_id=result.get("trace_id", ""),
        is_mock=True,
        allowed_tools=result.get("allowed_tools", []),
    )
