"""API 路由 — M1.1

GET  /health           — 健康检查（Mock 200 / DeepSeek 503）
POST /api/v1/chat      — 非流式对话接口

M1.0 新增：
- 路由透传 idempotent_replay / replayed_request_id 字段

M1.0.1 新增：
- 捕获 IdempotencyConflictError → HTTP 409

M1.1 新增：
- DeepSeek 模式 Health 返回 503（pipeline_not_ready 或 api_key_missing）
- DeepSeek 模式 Chat 返回 503
- 捕获 IdempotencyCoordinationError → HTTP 503
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.app.api.dependencies import get_mock_turn_service, get_settings_dep
from backend.app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse, ReportResponse
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response, settings: Settings = Depends(get_settings_dep)):
    """健康检查 — M1.1

    Mock 模式完整可用 → 200、ready=true。
    DeepSeek 模式 Key 缺失 → 503、deepseek_api_key_missing。
    DeepSeek 模式 Key 已配置但 Pipeline 未完成 → 503、deepseek_pipeline_not_ready。
    Remote MCP 模式 → 503、powerbi_remote_mcp_not_implemented。
    不调用 LLM 或 Power BI 网络。不输出 Key 信息。
    """
    ready = settings.is_real_ready
    reasons: list[str] = []

    if not ready:
        if settings.llm_mode == LLMMode.DEEPSEEK:
            if not settings.is_deepseek_configured:
                reasons.append("deepseek_api_key_missing")
            else:
                # M1.1: Provider 已实现，但真实 Intent 链路未完成
                reasons.append("deepseek_pipeline_not_ready")
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

    M1.0: 支持幂等重放 — 重复 request_id 返回完整快照。
    M1.0.1: 相同 request_id 不同请求内容返回 HTTP 409。
    """

    # M1.1: DeepSeek 模式 Chat 仍不可用（真实 Intent 链路未完成）
    if settings.llm_mode != LLMMode.MOCK or settings.powerbi_mode != PowerBIMode.MOCK:
        if settings.llm_mode == LLMMode.DEEPSEEK:
            if not settings.is_deepseek_configured:
                error_type = "deepseek_api_key_missing"
                detail_msg = "DeepSeek API Key 未配置。请在 .env 中设置 DEEPSEEK_API_KEY。"
            else:
                error_type = "deepseek_pipeline_not_ready"
                detail_msg = "DeepSeek Provider 已就绪，但真实 Intent 链路尚未接通。请使用 Mock 模式。"
        else:
            error_type = "real_mode_unavailable"
            detail_msg = "Real mode not yet implemented. Only Mock mode is available."
        raise HTTPException(
            status_code=503,
            detail={
                "detail": detail_msg,
                "error_type": error_type,
            },
        )

    service = get_mock_turn_service(request)

    # M1.0.1: 传递可选 ID，由 Service 统一生成 UUID
    try:
        result = await service.execute(
            message=body.message,
            conversation_id=body.conversation_id,  # 可能为 None
            request_id=body.request_id,  # 可能为 None
            semantic_model_key=body.semantic_model_key,
            report_template_key=body.report_template_key,
        )
    except IdempotencyConflictError as e:
        # M1.0.1: request_id 冲突 → HTTP 409
        return JSONResponse(
            status_code=409,
            content={
                "detail": e.detail,
                "error_type": "request_id_conflict",
                "request_id": e.request_id,
            },
        )
    except IdempotencyCoordinationError as e:
        # M1.1: Owner/Waiter 协调失败 → HTTP 503
        return JSONResponse(
            status_code=503,
            content={
                "detail": e.detail,
                "error_type": "idempotency_coordination_unavailable",
                "request_id": e.request_id,
            },
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Internal server error",
                "error_type": "internal_error",
                "request_id": body.request_id or "",
            },
        )

    # 构建结构化 report 响应
    report_response: ReportResponse | None = None
    if result.get("report"):
        report_data = result["report"]
        report_response = ReportResponse(
            report_id=report_data.get("report_id", ""),
            template_key=report_data.get("template_key", ""),
            html=report_data.get("html", ""),
        )

    return ChatResponse(
        request_id=result.get("request_id", ""),
        conversation_id=result.get("conversation_id", ""),
        terminal_state=result.get("terminal_state", "completed"),
        intent=result.get("intent", ""),
        response_type=result.get("response_type", ""),
        answer=result.get("answer"),
        report=report_response,
        clarification_question=result.get("clarification_question"),
        unsupported_reason=result.get("unsupported_reason"),
        error_type=result.get("error_type"),
        tool_sequence=result.get("tool_sequence", []),
        memory_commit=result.get("memory_commit", False),
        trace_id=result.get("trace_id", ""),
        is_mock=True,
        allowed_tools=result.get("allowed_tools", []),
        idempotent_replay=result.get("idempotent_replay", False),
        replayed_request_id=result.get("replayed_request_id"),
    )
