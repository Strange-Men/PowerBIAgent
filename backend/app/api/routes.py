"""API 路由 — M1.5

GET  /health           — 健康检查（Mock 200 / DeepSeek+Mock 200 / Remote MCP 503）
POST /api/v1/chat      — 非流式对话接口

M1.5 更新：
- DeepSeek+Mock 模式 Chat 正式可用
- 新增 LLM Provider 错误映射（502/503/504）
- ChatResponse 增加 llm_mode/powerbi_mode/source_mode/usage 字段
- is_mock 动态反映 LLM 层（Mock=True, DeepSeek=False）
- 移除 "仅 Mock 可用" 硬守卫
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.app.api.dependencies import get_mock_turn_service, get_turn_service, get_settings_dep
from backend.app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse, ReportResponse
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
)
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response, settings: Settings = Depends(get_settings_dep)):
    """健康检查 — M1.5

    Mock 模式完整可用 → 200、ready=true。
    DeepSeek+Mock 模式 Key 已配置 → 200、ready=true。
    DeepSeek+Mock 模式 Key 未配置 → 503、deepseek_api_key_missing。
    Remote MCP 模式 → 503、powerbi_remote_mcp_not_implemented。
    不调用 LLM 或 Power BI 网络。不输出 Key 信息。
    """
    ready = settings.is_real_ready
    reasons: list[str] = []

    if not ready:
        if settings.llm_mode == LLMMode.DEEPSEEK:
            if not settings.is_deepseek_configured:
                reasons.append("deepseek_api_key_missing")
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
    """非流式对话 — M1.5

    Mock+Mock: 完整 Mock 链路。
    DeepSeek+Mock: 真实 DeepSeek LLM + Mock Power BI。
    Remote MCP: 不可用（503）。
    """

    # ── 模式守卫 ──
    if settings.llm_mode == LLMMode.DEEPSEEK and not settings.is_deepseek_configured:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "DeepSeek API Key 未配置。请在 .env 中设置 DEEPSEEK_API_KEY。",
                "error_type": "deepseek_api_key_missing",
            },
        )

    if settings.powerbi_mode == PowerBIMode.REMOTE_MCP:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Remote MCP Power BI 尚未实现（M2）。请使用 Mock 模式。",
                "error_type": "powerbi_remote_mcp_not_implemented",
            },
        )

    # ── 获取 Service ──
    if settings.llm_mode == LLMMode.MOCK and settings.powerbi_mode == PowerBIMode.MOCK:
        service = get_mock_turn_service(request)
    else:
        service = get_turn_service(request)

    # ── 执行 ──
    try:
        result = await service.execute(
            message=body.message,
            conversation_id=body.conversation_id,
            request_id=body.request_id,
            semantic_model_key=body.semantic_model_key,
            report_template_key=body.report_template_key,
        )
    except IdempotencyConflictError as e:
        return JSONResponse(
            status_code=409,
            content={
                "detail": e.detail,
                "error_type": "request_id_conflict",
                "request_id": e.request_id,
            },
        )
    except IdempotencyCoordinationError as e:
        return JSONResponse(
            status_code=503,
            content={
                "detail": e.detail,
                "error_type": "idempotency_coordination_unavailable",
                "request_id": e.request_id,
            },
        )
    except LLMAuthenticationError as e:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "LLM 鉴权失败。请检查 API Key。",
                "error_type": "deepseek_authentication_failed",
                "request_id": body.request_id or "",
            },
        )
    except LLMRateLimitError as e:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "LLM 请求频率超限，请稍后重试。",
                "error_type": "deepseek_rate_limited",
                "request_id": body.request_id or "",
            },
        )
    except LLMTimeoutError as e:
        return JSONResponse(
            status_code=504,
            content={
                "detail": "LLM 请求超时。",
                "error_type": "deepseek_timeout",
                "request_id": body.request_id or "",
            },
        )
    except LLMConnectionError as e:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "LLM 连接失败，请稍后重试。",
                "error_type": "deepseek_connection_failed",
                "request_id": body.request_id or "",
            },
        )
    except LLMServiceError as e:
        return JSONResponse(
            status_code=502 if e.status_code and e.status_code < 503 else 503,
            content={
                "detail": "LLM 服务暂时不可用，请稍后重试。",
                "error_type": "deepseek_service_unavailable",
                "request_id": body.request_id or "",
            },
        )
    except LLMConfigurationError as e:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "LLM 配置错误。",
                "error_type": "deepseek_api_key_missing",
                "request_id": body.request_id or "",
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

    # ── 构建结构化 report 响应 ──
    report_response: ReportResponse | None = None
    if result.get("report"):
        report_data = result["report"]
        report_response = ReportResponse(
            report_id=report_data.get("report_id", ""),
            template_key=report_data.get("template_key", ""),
            html=report_data.get("html", ""),
        )

    # ── usage 摘要 ──
    usage_data = result.get("usage")
    if usage_data is not None and hasattr(usage_data, "to_dict"):
        usage_dict = usage_data.to_dict()
    elif isinstance(usage_data, dict):
        usage_dict = usage_data
    else:
        usage_dict = None

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
        is_mock=result.get("is_mock", False),
        allowed_tools=result.get("allowed_tools", []),
        idempotent_replay=result.get("idempotent_replay", False),
        replayed_request_id=result.get("replayed_request_id"),
        llm_mode=settings.llm_mode.value,
        powerbi_mode=settings.powerbi_mode.value,
        source_mode=result.get("source_mode", "mock"),
        usage=usage_dict,
    )
