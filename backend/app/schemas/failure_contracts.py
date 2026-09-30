"""Stable public failure DTOs shared by API, snapshots, and presentation."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class PublicFailureCode(str, Enum):
    REPORT_TEMPLATE_INCOMPATIBLE = "REPORT_TEMPLATE_INCOMPATIBLE"
    REPORT_TEMPLATE_UNAVAILABLE = "REPORT_TEMPLATE_UNAVAILABLE"
    REPORT_DATA_UNAVAILABLE = "REPORT_DATA_UNAVAILABLE"
    REPORT_EXECUTION_FAILED = "REPORT_EXECUTION_FAILED"
    REPORT_RENDER_FAILED = "REPORT_RENDER_FAILED"
    POWERBI_CONNECTION_LOST = "POWERBI_CONNECTION_LOST"
    SEMANTIC_MODEL_STALE = "SEMANTIC_MODEL_STALE"
    LLM_SERVICE_UNAVAILABLE = "LLM_SERVICE_UNAVAILABLE"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class FailureStage(str, Enum):
    REPORT_SCOPE = "report_scope"
    REPORT_PLAN = "report_plan"
    REPORT_QUERY_VALIDATION = "report_query_validation"
    REPORT_DAX_EXECUTION = "report_dax_execution"
    SALES_REPORT_DATA_ASSEMBLY = "sales_report_data_assembly"
    SALES_REPORT_SPEC = "sales_report_spec"
    REPORT_RENDER_STORE = "report_render_store"
    MEMORY_COMMIT = "memory_commit"
    UNDERSTANDING = "understanding"
    GROUNDING = "grounding"
    ANSWER_GENERATION = "answer_generation"
    TOOL_EXECUTION = "tool_execution"
    PROVIDER = "provider"
    INTERNAL = "internal"


class FailureRecoveryAction(str, Enum):
    RETRY = "retry"
    REFRESH_SEMANTIC_MODELS = "refresh_semantic_models"
    RESELECT_SEMANTIC_MODEL = "reselect_semantic_model"
    RESELECT_REPORT_TEMPLATE = "reselect_report_template"
    EDIT_REQUEST = "edit_request"
    NONE = "none"


class FailureInfo(BaseModel):
    code: PublicFailureCode
    stage: FailureStage
    retryable: bool
    recovery_action: FailureRecoveryAction

    model_config = ConfigDict(frozen=True)
