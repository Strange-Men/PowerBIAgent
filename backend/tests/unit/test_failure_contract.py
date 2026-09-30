"""M5.10.7 bounded public failure mapping tests."""

import pytest

from backend.app.application.failure_contract import (
    FailureRecoveryAction,
    FailureStage,
    PublicFailureCode,
    map_public_failure,
)


@pytest.mark.parametrize(
    ("stage", "error_type", "expected_code", "expected_action"),
    [
        (
            FailureStage.REPORT_RENDER_STORE,
            "raw_renderer_exception:secret-path",
            PublicFailureCode.REPORT_RENDER_FAILED,
            FailureRecoveryAction.RETRY,
        ),
        (
            FailureStage.TOOL_EXECUTION,
            "connection_error",
            PublicFailureCode.POWERBI_CONNECTION_LOST,
            FailureRecoveryAction.REFRESH_SEMANTIC_MODELS,
        ),
        (
            FailureStage.TOOL_EXECUTION,
            "DESKTOP_STALE_INSTANCE",
            PublicFailureCode.SEMANTIC_MODEL_STALE,
            FailureRecoveryAction.REFRESH_SEMANTIC_MODELS,
        ),
        (
            FailureStage.PROVIDER,
            "LLMConnectionError",
            PublicFailureCode.LLM_SERVICE_UNAVAILABLE,
            FailureRecoveryAction.RETRY,
        ),
        (
            FailureStage.REPORT_DAX_EXECUTION,
            "request_deadline_exceeded",
            PublicFailureCode.REQUEST_TIMEOUT,
            FailureRecoveryAction.RETRY,
        ),
    ],
)
def test_stage_and_known_category_map_to_stable_public_failure(
    stage: FailureStage,
    error_type: str,
    expected_code: PublicFailureCode,
    expected_action: FailureRecoveryAction,
) -> None:
    failure = map_public_failure(
        terminal_state="tool_failed",
        stage=stage,
        error_type=error_type,
    )

    assert failure.code == expected_code
    assert failure.stage == stage
    assert failure.recovery_action == expected_action
    assert error_type not in failure.model_dump_json()


def test_report_plan_incompatibility_is_reselection_failure() -> None:
    failure = map_public_failure(
        terminal_state="validation_failed",
        stage=FailureStage.REPORT_PLAN,
        error_type="report_no_resolved_sections",
    )
    assert failure.code == PublicFailureCode.REPORT_TEMPLATE_INCOMPATIBLE
    assert failure.recovery_action == FailureRecoveryAction.RESELECT_REPORT_TEMPLATE
