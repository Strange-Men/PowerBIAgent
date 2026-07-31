"""API 路由 — M0.4.1

GET  /health           — 健康检查（Mock 200 / Real 503）
POST /api/v1/chat      — 非流式对话接口
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.app.api.dependencies import get_mock_turn_service, get_settings_dep
from backend.app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse, ReportResponse
from backend.app.config.settings import LLMMode, PowerBIMode, Settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response, settings: Settings = Depends(get_settings_dep)):
    """健康检查

    Mock 模式完整可用 → 200、ready=true。
    Real 模式（DeepSeek / Remote MCP）尚未实现 → 503、ready=false。
    不调用 LLM 或 Power BI 网络。
    """
    ready = settings.is_real_ready
    reasons: list[str] = []

    if not ready:
        if settings.llm_mode == LLMMode.DEEPSEEK:
            reasons.append("deepseek_not_implemented")
        if settings.powerbi_mode == PowerBIMode.REMOTE_MCP:
            reasons.append("powerbi_remote_mcp_not_implemented")

    response.status_code = 200 if ready else 503
    status = "ok" if ready else "not_ready"

    return HealthResponse(
        status=status,
        ready=ready,
        reasons=reasons,
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
    request: Request,
    settings: Settings = Depends(get_settings_dep),
):
    """非流式对话 — Mock 模式完整链路

    请求经过 MockTurnService → 意图识别 → 工具执行 → 回答/报表。
    Mock 场景由 Application 层内部确定，客户端不可控制。
    Real 模式未实现时返回 503。
    """

    # Real 模式未实现 → 明确拒绝
    if settings.llm_mode != LLMMode.MOCK or settings.powerbi_mode != PowerBIMode.MOCK:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Real mode not yet implemented. Only Mock mode is available in M0.4.1.",
                "error_type": "real_mode_unavailable",
            },
        )

    service = get_mock_turn_service(request)

    # 生成 ID（如果未提供）
    conversation_id = body.conversation_id or str(uuid.uuid4())
    request_id = body.request_id or str(uuid.uuid4())

    # M0.4.1: 路由不构造 MockScenarioSelection
    # Mock 场景由 MockTurnService 内部使用 MockScenarioResolver 确定
    try:
        result = await service.execute(
            message=body.message,
            conversation_id=conversation_id,
            request_id=request_id,
            semantic_model_key=body.semantic_model_key,
            report_template_key=body.report_template_key,
            # M0.4.1: 不传入 scenario — 由 MockScenarioResolver 接管
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

    # M0.4.1: 构建结构化 report 响应
    report_response: ReportResponse | None = None
    if result.get("report"):
        report_data = result["report"]
        report_response = ReportResponse(
            report_id=report_data.get("report_id", ""),
            template_key=report_data.get("template_key", ""),
            html=report_data.get("html", ""),
        )

    return ChatResponse(
        request_id=result.get("request_id", request_id),
        conversation_id=result.get("conversation_id", conversation_id),
        terminal_state=result.get("terminal_state", "completed"),
        intent=result.get("intent", ""),
        response_type=result.get("response_type", ""),
        # M0.4.1: 返回真实 Answer（不是 "1 rows" 摘要）
        answer=result.get("answer"),
        report=report_response,
        # M0.4.1: clarification / unsupported 真实可达
        clarification_question=result.get("clarification_question"),
        unsupported_reason=result.get("unsupported_reason"),
        error_type=result.get("error_type"),
        tool_sequence=result.get("tool_sequence", []),
        memory_commit=result.get("memory_commit", False),
        trace_id=result.get("trace_id", ""),
        is_mock=True,
        allowed_tools=result.get("allowed_tools", []),
    )
