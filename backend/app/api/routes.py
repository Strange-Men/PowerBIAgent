"""API 路由 — M1.5

GET  /health           — 配置就绪检查（Mock / DeepSeek+Mock / DeepSeek+Local）
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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from backend.app.api.dependencies import (
    get_mock_turn_service,
    get_conversation_history_service,
    get_report_repository,
    get_report_template_registry,
    get_llm_provider_registry,
    get_semantic_model_discovery_service,
    get_settings_dep,
    get_turn_service,
)
from backend.app.application.conversation_history_service import (
    ConversationHistoryService,
    InvalidConversationCursorError,
    InvalidConversationQueryError,
    MAX_PAGE_SIZE,
)
from backend.app.application.semantic_model_discovery_service import (
    SemanticModelDiscoveryService,
)
from backend.app.conversation.models import (
    ConversationArchiveResult,
    ConversationDeleteResult,
    ConversationHistoryCorruptionError,
    ConversationHistoryPage,
    ConversationListPage,
    ConversationNotFoundError,
    ConversationReportPage,
    ConversationRenameRequest,
    ConversationFailureRequest,
    ConversationFailureResult,
    ConversationRenameResult,
    ConversationRestoreResult,
    ReportResourcePage,
    ReportResourceStatus,
)
from backend.app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    ReportResponse,
)
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
)
from backend.app.llm.profiles import LLMProfileCatalogResponse
from backend.app.llm.registry import (
    LLMProfileNotFoundError,
    LLMProfileUnavailableError,
    LLMProviderRegistry,
)
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.models import SemanticModelCatalog
from backend.app.report.resources import (
    ReportArchiveResult,
    ReportDeleteResult,
    ReportNotFoundError,
    ReportRenameRequest,
    ReportRenameResult,
    ReportRepository,
    ReportRestoreResult,
    ReportStorageError,
)
from backend.app.report.registry import (
    ReportTemplateCatalogResponse,
    ReportTemplateRegistry,
)

router = APIRouter()


def _llm_error_content(
    *,
    detail: str,
    error_type: str,
    request_id: str,
    requested_profile_key: str | None,
    settings: Settings,
    registry: LLMProviderRegistry,
    error: Exception | None = None,
) -> dict[str, str]:
    """Build a credential-free provider error envelope for one frozen turn."""

    provider_key = str(getattr(error, "provider", "") or "").strip()
    profile_key = provider_key or requested_profile_key or settings.llm_default_profile
    catalog = registry.public_catalog(
        default_profile_key=settings.llm_default_profile,
        include_keys={profile_key},
    )
    item = catalog.items[0] if catalog.items else None
    category = getattr(error, "error_category", None)
    category_value = getattr(category, "value", "")
    if isinstance(error, (LLMProfileNotFoundError, LLMProfileUnavailableError)):
        category_value = "configuration"
    return {
        "detail": detail,
        "error_type": error_type,
        "request_id": request_id,
        "llm_profile_key": profile_key,
        "llm_model": item.model if item is not None else "",
        "llm_provider_protocol": (
            item.provider_protocol.value if item is not None else ""
        ),
        "llm_error_category": category_value,
        "llm_error_class": type(error).__name__ if error is not None else "",
    }


@router.get("/api/v1/llm-profiles", response_model=LLMProfileCatalogResponse)
async def list_llm_profiles(
    settings: Settings = Depends(get_settings_dep),
    registry: LLMProviderRegistry = Depends(get_llm_provider_registry),
):
    """Return safe public profile metadata; never credentials or base URLs."""
    return registry.public_catalog(default_profile_key=settings.llm_default_profile)


def _raise_conversation_query_error(exc: Exception) -> None:
    if isinstance(exc, ConversationNotFoundError):
        raise HTTPException(status_code=404, detail="conversation_not_found") from None
    if isinstance(exc, (InvalidConversationCursorError, InvalidConversationQueryError)):
        detail = "invalid_cursor" if isinstance(exc, InvalidConversationCursorError) else str(exc)
        raise HTTPException(status_code=422, detail=detail) from None
    if isinstance(exc, (ConversationHistoryCorruptionError, ReportStorageError)):
        raise HTTPException(status_code=500, detail="conversation_history_invalid") from None
    raise exc


@router.get("/api/v1/semantic-models", response_model=SemanticModelCatalog)
async def discover_semantic_models(
    service: SemanticModelDiscoveryService = Depends(
        get_semantic_model_discovery_service
    ),
):
    """Return safe models currently selectable by the frontend."""
    return await service.discover()


@router.get(
    "/api/v1/report-templates",
    response_model=ReportTemplateCatalogResponse,
)
async def discover_report_templates(
    registry: ReportTemplateRegistry = Depends(get_report_template_registry),
):
    """Return the backend-owned set of currently selectable templates."""
    return registry.public_catalog()


@router.get("/api/reports", response_model=ReportResourcePage)
async def list_managed_reports(
    source_mode: RuntimeDataMode,
    status: ReportResourceStatus = Query(default="active"),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """List all manageable reports in one explicit source namespace."""
    try:
        return await service.list_managed_reports(
            source_mode,
            status=status,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get("/api/reports/{report_id}", response_class=HTMLResponse)
async def view_report(
    report_id: str,
    repository: ReportRepository = Depends(get_report_repository),
):
    """View one repository-managed static HTML report."""
    try:
        artifact, html = await repository.read_html(report_id)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(status_code=500, detail="report_artifact_invalid") from None
    return HTMLResponse(
        content=html,
        media_type="text/html",
        headers={"ETag": f'"{artifact.content_hash}"'},
    )


@router.get("/api/reports/{report_id}/download")
async def download_report(
    report_id: str,
    repository: ReportRepository = Depends(get_report_repository),
):
    """Download one repository-managed UTF-8 HTML artifact."""
    try:
        artifact, html = await repository.read_html(report_id)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(status_code=500, detail="report_artifact_invalid") from None
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{artifact.report_id}.html"'
            ),
            "ETag": f'"{artifact.content_hash}"',
        },
    )


@router.get("/api/v1/conversations", response_model=ConversationListPage)
async def list_recent_conversations(
    runtime_mode: RuntimeDataMode,
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """List unarchived recent conversations in one explicit namespace."""
    try:
        return await service.list_recent(runtime_mode, limit=limit, cursor=cursor)
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get(
    "/api/v1/conversations/archived",
    response_model=ConversationListPage,
)
async def list_archived_conversations(
    runtime_mode: RuntimeDataMode,
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """List recoverable archived conversations in one explicit namespace."""
    try:
        return await service.list_archived(
            runtime_mode, limit=limit, cursor=cursor
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get("/api/v1/conversations/search", response_model=ConversationListPage)
async def search_conversations(
    runtime_mode: RuntimeDataMode,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Search declared persisted fields; report HTML is never searched."""
    try:
        return await service.search(
            runtime_mode, query=q, limit=limit, cursor=cursor
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get(
    "/api/v1/conversations/{conversation_id}/history",
    response_model=ConversationHistoryPage,
)
async def get_conversation_history(
    conversation_id: str,
    runtime_mode: RuntimeDataMode,
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Return presentation transcript plus persisted structured turn results."""
    try:
        return await service.get_history(
            runtime_mode, conversation_id, limit=limit, cursor=cursor
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get(
    "/api/v1/conversations/{conversation_id}/reports",
    response_model=ConversationReportPage,
)
async def list_conversation_reports(
    conversation_id: str,
    source_mode: RuntimeDataMode,
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=2048),
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """List strict report metadata in ``(source_mode, conversation_id)``."""
    try:
        return await service.list_reports(
            source_mode, conversation_id, limit=limit, cursor=cursor
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.post(
    "/api/v1/conversations/{conversation_id}/archive",
    response_model=ConversationArchiveResult,
)
async def archive_conversation(
    conversation_id: str,
    runtime_mode: RuntimeDataMode,
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Logically archive one namespace without deleting its history/reports."""
    try:
        return await service.archive(runtime_mode, conversation_id)
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.post(
    "/api/v1/conversations/{conversation_id}/restore",
    response_model=ConversationRestoreResult,
)
async def restore_conversation(
    conversation_id: str,
    runtime_mode: RuntimeDataMode,
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Restore one archived namespace without changing its history/reports."""
    try:
        return await service.restore(runtime_mode, conversation_id)
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.delete(
    "/api/reports/{report_id}",
    response_model=ReportDeleteResult,
)
async def delete_report(
    report_id: str,
    repository: ReportRepository = Depends(get_report_repository),
):
    """Delete one managed report resource; never exposed through ToolGateway."""
    try:
        return await repository.delete(report_id)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(
            status_code=500, detail="report_artifact_delete_failed"
        ) from None


@router.patch(
    "/api/reports/{report_id}",
    response_model=ReportRenameResult,
)
async def rename_report(
    report_id: str,
    body: ReportRenameRequest,
    repository: ReportRepository = Depends(get_report_repository),
):
    """Rename presentation metadata only; never exposed through ToolGateway."""
    try:
        return await repository.rename(report_id, body.display_title)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(
            status_code=500, detail="report_presentation_update_failed"
        ) from None


@router.post(
    "/api/reports/{report_id}/archive",
    response_model=ReportArchiveResult,
)
async def archive_report(
    report_id: str,
    source_mode: RuntimeDataMode,
    repository: ReportRepository = Depends(get_report_repository),
):
    """Archive one report presentation; HTML and factual metadata remain."""
    try:
        return await repository.archive(report_id, source_mode.value)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(
            status_code=500, detail="report_presentation_update_failed"
        ) from None


@router.post(
    "/api/reports/{report_id}/restore",
    response_model=ReportRestoreResult,
)
async def restore_report(
    report_id: str,
    source_mode: RuntimeDataMode,
    repository: ReportRepository = Depends(get_report_repository),
):
    """Restore one archived report without rewriting identity or HTML."""
    try:
        return await repository.restore(report_id, source_mode.value)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="report_not_found") from None
    except ReportStorageError:
        raise HTTPException(
            status_code=500, detail="report_presentation_update_failed"
        ) from None


@router.patch(
    "/api/v1/conversations/{conversation_id}",
    response_model=ConversationRenameResult,
)
async def rename_conversation(
    conversation_id: str,
    body: ConversationRenameRequest,
    runtime_mode: RuntimeDataMode,
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Update presentation-only title without changing conversation identity."""
    try:
        return await service.rename(runtime_mode, conversation_id, body.title)
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.post(
    "/api/v1/conversations/{conversation_id}/failure",
    response_model=ConversationFailureResult,
)
async def record_failed_conversation(
    conversation_id: str,
    body: ConversationFailureRequest,
    runtime_mode: RuntimeDataMode,
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Persist safe failed-resource metadata; never commits Memory or facts."""
    try:
        return await service.record_failed(
            runtime_mode,
            conversation_id,
            title=body.title,
            error_type=body.error_type,
        )
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.delete(
    "/api/v1/conversations/{conversation_id}",
    response_model=ConversationDeleteResult,
)
async def delete_conversation(
    conversation_id: str,
    runtime_mode: RuntimeDataMode,
    service: ConversationHistoryService = Depends(get_conversation_history_service),
):
    """Physically delete one namespace and its same-namespace linked resources."""
    try:
        return await service.delete(runtime_mode, conversation_id)
    except Exception as exc:
        _raise_conversation_query_error(exc)


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings_dep),
):
    """健康检查 — M1.5

    Mock 模式完整可用 → 200、ready=true。
    DeepSeek+Mock 模式 Key 已配置 → 200、ready=true。
    DeepSeek+Local 模式 Key 与只读 Local 配置完整 → 200、configuration_ready=true。
    Remote MCP 模式 → 503、powerbi_remote_mcp_not_implemented。
    ready 为兼容字段，等同 configuration_ready；不代表 Desktop 实时在线。
    不调用 LLM、启动 npx 或连接 Power BI Desktop。不输出 Key 信息。
    """
    ready = settings.is_real_ready
    reasons: list[str] = []

    if not ready:
        if settings.llm_mode in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}:
            if not settings.is_llm_profile_configured(settings.llm_default_profile):
                reasons.append("llm_default_profile_not_configured")
                if settings.llm_default_profile == "deepseek":
                    reasons.append("deepseek_api_key_missing")
        if settings.powerbi_mode == PowerBIMode.REMOTE_MCP:
            reasons.append("powerbi_remote_mcp_not_implemented")
        if (
            settings.powerbi_mode == PowerBIMode.LOCAL_MCP
            and not settings.is_powerbi_local_mcp_configured
        ):
            reasons.append("powerbi_local_mcp_configuration_incomplete")
        if (
            settings.powerbi_mode == PowerBIMode.LOCAL_MCP
            and settings.llm_mode not in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}
        ):
            reasons.append("powerbi_local_mcp_requires_openai_compatible_llm")
            reasons.append("powerbi_local_mcp_requires_deepseek")

    response.status_code = 200 if ready else 503
    status = "ok" if ready else "not_ready"

    return HealthResponse(
        status=status,
        ready=ready,
        configuration_ready=ready,
        powerbi_live_connected=False,
        reasons=reasons,
        app_name=settings.app_name,
        app_env=settings.app_env.value,
        version=settings.version,
        llm_mode=settings.llm_mode.value,
        powerbi_mode=settings.powerbi_mode.value,
        persistence_backend=settings.persistence_backend.value,
        max_tool_calls=settings.max_tool_calls,
        local_mcp_readonly=settings.powerbi_local_mcp_readonly,
        deepseek_configured=settings.is_deepseek_configured,
        kimi_configured=settings.is_kimi_configured,
        llm_default_profile=settings.llm_default_profile,
        real_mode_configuration_complete=(
            settings.is_local_real_configuration_complete
        ),
        real_mode_reasons=settings.local_real_configuration_reasons,
        harness_mode=settings.harness_mode.value,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    registry: LLMProviderRegistry = Depends(get_llm_provider_registry),
):
    """非流式对话 — M1.5

    Mock+Mock: 完整 Mock 链路。
    DeepSeek+Mock: 真实 DeepSeek LLM + Mock Power BI。
    DeepSeek+Local: 真实 DeepSeek LLM + Local MCP + Power BI Desktop。
    Remote MCP: 不可用（503）。
    """

    # ── 模式守卫 ──
    if (
        settings.llm_mode in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}
        and not settings.is_llm_profile_configured(settings.llm_default_profile)
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "默认 LLM profile 未配置。",
                "error_type": "llm_default_profile_not_configured",
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

    if settings.powerbi_mode == PowerBIMode.LOCAL_MCP:
        if settings.llm_mode not in {LLMMode.DEEPSEEK, LLMMode.OPENAI_COMPATIBLE}:
            raise HTTPException(
                status_code=503,
                detail={
                    "detail": "Local MCP Chat 需要 OpenAI-compatible LLM 模式。",
                    "error_type": "powerbi_local_mcp_requires_openai_compatible_llm",
                },
            )
        if not settings.is_powerbi_local_mcp_configured:
            raise HTTPException(
                status_code=503,
                detail={
                    "detail": "Local MCP 配置不完整或未启用只读模式。",
                    "error_type": "powerbi_local_mcp_configuration_incomplete",
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
            llm_profile_key=body.llm_profile_key,
        )
    except LLMProfileNotFoundError as e:
        return JSONResponse(
            status_code=422,
            content=_llm_error_content(
                detail="所选 LLM profile 不存在，请刷新模型目录。",
                error_type="llm_profile_unknown",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMProfileUnavailableError as e:
        return JSONResponse(
            status_code=503,
            content=_llm_error_content(
                detail="所选 LLM profile 当前不可用，请重新选择。",
                error_type="llm_profile_unavailable",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
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
            content=_llm_error_content(
                detail="LLM 鉴权失败。请检查 API Key。",
                error_type="llm_authentication_failed",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMRateLimitError as e:
        return JSONResponse(
            status_code=503,
            content=_llm_error_content(
                detail="LLM 请求频率超限，请稍后重试。",
                error_type="llm_rate_limited",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMTimeoutError as e:
        return JSONResponse(
            status_code=504,
            content=_llm_error_content(
                detail="LLM 请求超时。",
                error_type="llm_timeout",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMConnectionError as e:
        return JSONResponse(
            status_code=502,
            content=_llm_error_content(
                detail="LLM 连接失败，请稍后重试。",
                error_type="llm_connection_failed",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMServiceError as e:
        return JSONResponse(
            status_code=502 if e.status_code and e.status_code < 503 else 503,
            content=_llm_error_content(
                detail="LLM 服务暂时不可用，请稍后重试。",
                error_type="llm_service_unavailable",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMConfigurationError as e:
        # M1.6.4: 根据 error_code 区分配置错误类型
        if e.error_code == "insufficient_balance":
            return JSONResponse(
                status_code=402,
                content=_llm_error_content(
                    detail="LLM 账户余额不足，请检查所选 provider。",
                    error_type="llm_insufficient_balance",
                    request_id=body.request_id or "",
                    requested_profile_key=body.llm_profile_key,
                    settings=settings,
                    registry=registry,
                    error=e,
                ),
            )
        elif e.error_code == "invalid_base_url":
            return JSONResponse(
                status_code=503,
                content=_llm_error_content(
                    detail="LLM 配置错误：Base URL 无效。",
                    error_type="llm_invalid_base_url",
                    request_id=body.request_id or "",
                    requested_profile_key=body.llm_profile_key,
                    settings=settings,
                    registry=registry,
                    error=e,
                ),
            )
        elif e.error_code == "invalid_model":
            return JSONResponse(
                status_code=503,
                content=_llm_error_content(
                    detail="LLM 配置错误：模型名称无效。",
                    error_type="llm_invalid_model",
                    request_id=body.request_id or "",
                    requested_profile_key=body.llm_profile_key,
                    settings=settings,
                    registry=registry,
                    error=e,
                ),
            )
        elif e.error_code == "api_key_missing":
            return JSONResponse(
                status_code=503,
                content=_llm_error_content(
                    detail="LLM 配置错误：API Key 未配置。",
                    error_type="llm_api_key_missing",
                    request_id=body.request_id or "",
                    requested_profile_key=body.llm_profile_key,
                    settings=settings,
                    registry=registry,
                    error=e,
                ),
            )
        else:
            # M1.6.5: 未知配置错误返回通用脱敏 error_type，不伪装为 api_key_missing
            return JSONResponse(
                status_code=503,
                content=_llm_error_content(
                    detail="LLM 配置错误。",
                    error_type="llm_configuration_error",
                    request_id=body.request_id or "",
                    requested_profile_key=body.llm_profile_key,
                    settings=settings,
                    registry=registry,
                    error=e,
                ),
            )
    except LLMRequestError as e:
        return JSONResponse(
            status_code=502,
            content=_llm_error_content(
                detail="LLM 请求参数错误。",
                error_type="llm_request_error",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMResponseError as e:
        return JSONResponse(
            status_code=502,
            content=_llm_error_content(
                detail="LLM 响应解析失败。",
                error_type="llm_response_error",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMValidationError as e:
        return JSONResponse(
            status_code=502,
            content=_llm_error_content(
                detail="LLM 输出校验失败。",
                error_type="llm_validation_error",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except LLMProviderError as e:
        return JSONResponse(
            status_code=502,
            content=_llm_error_content(
                detail="LLM 服务异常。",
                error_type="llm_provider_error",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
                error=e,
            ),
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content=_llm_error_content(
                detail="Internal server error",
                error_type="internal_error",
                request_id=body.request_id or "",
                requested_profile_key=body.llm_profile_key,
                settings=settings,
                registry=registry,
            ),
        )

    # ── 构建结构化 report 响应 ──
    report_response: ReportResponse | None = None
    if result.get("report"):
        report_data = result["report"]
        report_response = ReportResponse(
            report_id=report_data.get("report_id", ""),
            template_key=report_data.get("template_key", ""),
            contract_version=report_data.get("contract_version", ""),
            view_reference=report_data.get("view_reference", ""),
            download_reference=report_data.get("download_reference", ""),
            content_type=report_data.get(
                "content_type", "text/html; charset=utf-8"
            ),
            content_hash=report_data.get("content_hash", ""),
            display_title=report_data.get(
                "display_title", report_data.get("title", "销售分析报告")
            ),
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
        presentation=result.get("presentation"),
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
        llm_profile_key=result.get("llm_profile_key", ""),
        llm_model=result.get("llm_model", ""),
        llm_provider_protocol=result.get("llm_provider_protocol", ""),
        powerbi_mode=settings.powerbi_mode.value,
        source_mode=result.get("source_mode", "mock"),
        usage=usage_dict,
        execution_audit=result.get("execution_audit"),
    )
