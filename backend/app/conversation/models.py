"""DTOs for persisted conversation history and search.

The DTOs intentionally contain no SQLAlchemy rows and no JSON payload blobs.
They expose terminal results plus explicitly stored presentation transcript
metadata.  Transcript/title fields never become Memory or factual authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.memory.models import RuntimeDataMode
from backend.app.presentation.models import PresentationEnvelope


class ConversationNotFoundError(LookupError):
    """The exact ``(runtime_mode, conversation_id)`` root does not exist."""


class ConversationHistoryCorruptionError(RuntimeError):
    """Stored row columns and structured payload disagree or are invalid."""


class ConversationSummary(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    title: str | None = None
    latest_request_id: str | None = None
    latest_terminal_state: str | None = None
    latest_response_type: str | None = None
    latest_analysis_goal: str | None = None

    model_config = ConfigDict(frozen=True)


class CommittedMemorySummary(BaseModel):
    request_id: str
    memory_version: int
    semantic_model_key: str | None = None
    report_template_key: str | None = None
    current_intent: str | None = None
    analysis_goal: str | None = None
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class SnapshotReportSummary(BaseModel):
    report_id: str
    template_key: str
    contract_version: str = ""
    view_reference: str = ""
    download_reference: str = ""
    content_type: str
    content_hash: str = ""
    display_title: str = "销售分析报告"
    availability_status: Literal["available", "deleted"] = "available"

    model_config = ConfigDict(frozen=True)


class ConversationHistoryItem(BaseModel):
    request_id: str
    created_at: datetime
    terminal_state: str
    response_type: str
    intent: str
    user_message: str | None = None
    presentation: PresentationEnvelope | None = None
    answer: str | None = None
    report: SnapshotReportSummary | None = None
    clarification_question: str | None = None
    unsupported_reason: str | None = None
    error_type: str | None = None
    memory_commit: bool
    final_memory_version: int | None = None
    memory: CommittedMemorySummary | None = None

    model_config = ConfigDict(frozen=True)


class ConversationReportItem(BaseModel):
    report_id: str
    source_mode: str = Field(pattern="^(mock|real)$")
    conversation_id: str
    request_id: str | None = None
    template_key: str
    semantic_model_key: str
    schema_fingerprint: str
    contract_version: str
    generated_at: datetime
    stored_at: datetime
    content_type: str
    content_hash: str
    view_reference: str
    download_reference: str
    verified_fact_set_ids: list[str]
    query_result_ids: list[str]
    display_title: str = "销售分析报告"
    availability_status: Literal["available"] = "available"

    model_config = ConfigDict(frozen=True)


class ConversationListPage(BaseModel):
    runtime_mode: RuntimeDataMode
    items: list[ConversationSummary]
    next_cursor: str | None = None

    model_config = ConfigDict(frozen=True)


class ConversationHistoryPage(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    archived_at: datetime | None = None
    title: str | None = None
    items: list[ConversationHistoryItem]
    next_cursor: str | None = None

    model_config = ConfigDict(frozen=True)


class ConversationReportPage(BaseModel):
    source_mode: RuntimeDataMode
    conversation_id: str
    items: list[ConversationReportItem]
    next_cursor: str | None = None

    model_config = ConfigDict(frozen=True)


class ConversationArchiveResult(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    archived_at: datetime

    model_config = ConfigDict(frozen=True)


class ConversationRestoreResult(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    restored: bool = True
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class ConversationDeleteResult(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    deleted: bool = True
    deleted_counts: dict[str, int]

    model_config = ConfigDict(frozen=True)


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    model_config = ConfigDict(extra="forbid")


class ConversationRenameResult(BaseModel):
    runtime_mode: RuntimeDataMode
    conversation_id: str
    title: str
    updated_at: datetime

    model_config = ConfigDict(frozen=True)
