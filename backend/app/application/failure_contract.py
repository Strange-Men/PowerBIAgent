"""Bounded public failure contract and the single backend mapping authority."""

from __future__ import annotations

from backend.app.schemas.failure_contracts import (
    FailureInfo,
    FailureRecoveryAction,
    FailureStage,
    PublicFailureCode,
)


_STAGE_ALIASES: dict[str, FailureStage] = {
    "semantic_frame_projection": FailureStage.UNDERSTANDING,
    "semantic_interpretation": FailureStage.UNDERSTANDING,
    "template_grounding": FailureStage.GROUNDING,
    "semantic_grounding": FailureStage.GROUNDING,
    "inheritance_policy": FailureStage.GROUNDING,
    "semantic_catalog": FailureStage.GROUNDING,
    "member_grounding": FailureStage.GROUNDING,
    "canonical_shape_completeness": FailureStage.GROUNDING,
    "answer_validation": FailureStage.ANSWER_GENERATION,
    "schema_fetch": FailureStage.TOOL_EXECUTION,
    "query_plan_validation": FailureStage.TOOL_EXECUTION,
    "dax_generation": FailureStage.TOOL_EXECUTION,
    "dax_safety": FailureStage.TOOL_EXECUTION,
    "dax_semantic_consistency": FailureStage.TOOL_EXECUTION,
    "dax_execution": FailureStage.TOOL_EXECUTION,
    "query_result_error": FailureStage.TOOL_EXECUTION,
    "result_validation": FailureStage.TOOL_EXECUTION,
    "result_semantic_inspection": FailureStage.TOOL_EXECUTION,
    "verified_fact_set": FailureStage.TOOL_EXECUTION,
    "report_generation": FailureStage.SALES_REPORT_SPEC,
    "report_validation": FailureStage.SALES_REPORT_SPEC,
    "report_render": FailureStage.REPORT_RENDER_STORE,
}

_TIMEOUT_ERRORS = frozenset({
    "timeout",
    "request_deadline_exceeded",
    "ToolTimeoutError",
    "LLMTimeoutError",
    "llm_timeout",
})
_STALE_ERRORS = frozenset({
    "stale_instance",
    "DESKTOP_STALE_INSTANCE",
    "powerbi_stale_instance",
})
_CONNECTION_ERRORS = frozenset({
    "connection_error",
    "powerbi_desktop_not_connected",
    "powerbi_connection_failed",
    "desktop_instance_not_found",
})
_PROVIDER_ERRORS = frozenset({
    "LLMAuthenticationError",
    "LLMConfigurationError",
    "LLMConnectionError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMRequestError",
    "LLMResponseError",
    "LLMServiceError",
    "LLMValidationError",
    "llm_authentication_failed",
    "llm_api_key_missing",
    "llm_insufficient_balance",
    "llm_invalid_base_url",
    "llm_invalid_model",
    "llm_configuration_error",
    "llm_request_error",
    "llm_response_error",
    "llm_validation_error",
    "llm_connection_failed",
    "llm_rate_limited",
    "llm_service_unavailable",
    "llm_provider_error",
    "llm_profile_unknown",
    "llm_profile_unavailable",
    "llm_default_profile_not_configured",
})
_TEMPLATE_UNAVAILABLE_ERRORS = frozenset({
    "report_template_unknown",
    "report_template_not_available",
    "report_template_unavailable",
    "report_template_contract_missing",
    "report_renderer_unavailable",
})
_TEMPLATE_INCOMPATIBLE_ERRORS = frozenset({
    "report_no_resolved_sections",
    "report_contract_semantic_model_mismatch",
    "report_scope_model_mismatch",
    "report_requirement_unavailable",
})


def coerce_failure_stage(stage: FailureStage | str | None) -> FailureStage:
    if isinstance(stage, FailureStage):
        return stage
    if stage:
        try:
            return FailureStage(stage)
        except ValueError:
            return _STAGE_ALIASES.get(stage, FailureStage.INTERNAL)
    return FailureStage.INTERNAL


def _failure(
    code: PublicFailureCode,
    stage: FailureStage,
    action: FailureRecoveryAction,
    *,
    retryable: bool,
) -> FailureInfo:
    return FailureInfo(
        code=code,
        stage=stage,
        retryable=retryable,
        recovery_action=action,
    )


def map_public_failure(
    *,
    terminal_state: str,
    stage: FailureStage | str | None,
    error_type: str | None,
) -> FailureInfo:
    """Project internal failure metadata without copying diagnostic text."""

    public_stage = coerce_failure_stage(stage)
    known_error = error_type or ""
    auth_actions = {
        "AUTH_REQUIRED": FailureRecoveryAction.LOGIN,
        "AUTH_EXPIRED": FailureRecoveryAction.RELOGIN,
        "AUTH_CONSENT_REQUIRED": FailureRecoveryAction.CONSENT_OR_CONTACT_ADMIN,
        "AUTH_FORBIDDEN": FailureRecoveryAction.SWITCH_ACCOUNT_OR_CONTACT_ADMIN,
    }
    if known_error in auth_actions:
        return _failure(PublicFailureCode(known_error), FailureStage.AUTH,
                        auth_actions[known_error], retryable=False)
    if known_error in _TIMEOUT_ERRORS:
        return _failure(
            PublicFailureCode.REQUEST_TIMEOUT,
            public_stage,
            FailureRecoveryAction.RETRY,
            retryable=True,
        )
    if known_error in _STALE_ERRORS:
        return _failure(
            PublicFailureCode.SEMANTIC_MODEL_STALE,
            public_stage,
            FailureRecoveryAction.REFRESH_SEMANTIC_MODELS,
            retryable=False,
        )
    if known_error in _CONNECTION_ERRORS:
        return _failure(
            PublicFailureCode.POWERBI_CONNECTION_LOST,
            public_stage,
            FailureRecoveryAction.REFRESH_SEMANTIC_MODELS,
            retryable=True,
        )
    if public_stage == FailureStage.PROVIDER or known_error in _PROVIDER_ERRORS:
        return _failure(
            PublicFailureCode.LLM_SERVICE_UNAVAILABLE,
            public_stage,
            FailureRecoveryAction.RETRY,
            retryable=True,
        )
    if known_error in _TEMPLATE_UNAVAILABLE_ERRORS:
        return _failure(
            PublicFailureCode.REPORT_TEMPLATE_UNAVAILABLE,
            public_stage,
            FailureRecoveryAction.RESELECT_REPORT_TEMPLATE,
            retryable=False,
        )
    if (
        known_error in _TEMPLATE_INCOMPATIBLE_ERRORS
        or public_stage in {FailureStage.REPORT_SCOPE, FailureStage.REPORT_PLAN}
    ):
        return _failure(
            PublicFailureCode.REPORT_TEMPLATE_INCOMPATIBLE,
            public_stage,
            FailureRecoveryAction.RESELECT_REPORT_TEMPLATE,
            retryable=False,
        )
    if public_stage == FailureStage.REPORT_DAX_EXECUTION:
        return _failure(
            PublicFailureCode.REPORT_EXECUTION_FAILED,
            public_stage,
            FailureRecoveryAction.RETRY,
            retryable=True,
        )
    if public_stage == FailureStage.SALES_REPORT_DATA_ASSEMBLY:
        return _failure(
            PublicFailureCode.REPORT_DATA_UNAVAILABLE,
            public_stage,
            FailureRecoveryAction.EDIT_REQUEST,
            retryable=False,
        )
    if public_stage in {
        FailureStage.SALES_REPORT_SPEC,
        FailureStage.REPORT_RENDER_STORE,
    }:
        return _failure(
            PublicFailureCode.REPORT_RENDER_FAILED,
            public_stage,
            FailureRecoveryAction.RETRY,
            retryable=True,
        )
    if (
        terminal_state == "validation_failed"
        or public_stage
        in {
            FailureStage.UNDERSTANDING,
            FailureStage.GROUNDING,
            FailureStage.ANSWER_GENERATION,
            FailureStage.REPORT_QUERY_VALIDATION,
        }
    ):
        return _failure(
            PublicFailureCode.VALIDATION_FAILED,
            public_stage,
            FailureRecoveryAction.EDIT_REQUEST,
            retryable=False,
        )
    return _failure(
        PublicFailureCode.INTERNAL_FAILURE,
        public_stage,
        FailureRecoveryAction.RETRY,
        retryable=True,
    )
