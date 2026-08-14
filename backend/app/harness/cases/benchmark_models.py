"""Strict Known-answer and multi-turn benchmark specifications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.data_contracts import StructuredFilter


class KnownAnswerCaseSpec(BaseModel):
    id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    expected_measure: str = Field(min_length=1)
    expected_dimensions: list[str] = Field(default_factory=list)
    expected_filters: list[StructuredFilter] = Field(default_factory=list)
    expected_sort: Literal["asc", "desc"] | None = None
    expected_top_n: int | None = Field(default=None, ge=1)
    oracle_key: str = Field(min_length=1)
    holdout: bool = False

    model_config = ConfigDict(extra="forbid")


class MultiTurnExpectedSpec(BaseModel):
    expected_intent: Literal[
        "data_question", "report_generation", "clarification", "unsupported"
    ]
    expected_terminal_state: str = Field(min_length=1)
    expected_measure: str | None = None
    expected_dimensions: list[str] = Field(default_factory=list)
    expected_filters: list[StructuredFilter] = Field(default_factory=list)
    expected_sort: Literal["asc", "desc"] | None = None
    expected_top_n: int | None = Field(default=None, ge=1)
    expected_memory_commit: bool
    expected_inheritance: str = Field(min_length=1)
    oracle_key: str | None = None
    expected_tool_sequence: list[str] = Field(default_factory=list)
    expected_source_mode: Literal["real"] | None = None
    expected_failure_stage: str | None = None
    expected_pending_missing_slots: list[
        Literal["measure", "dimension", "filter", "time", "analysis", "template"]
    ] = Field(default_factory=list)
    expected_pending_measures: list[str] = Field(default_factory=list)
    expected_pending_dimensions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_success_contract(self) -> "MultiTurnExpectedSpec":
        is_data_success = (
            self.expected_intent == "data_question"
            and self.expected_terminal_state == "completed"
        )
        if is_data_success:
            if self.expected_measure is None or self.oracle_key is None:
                raise ValueError(
                    "completed data turn requires expected_measure and oracle_key"
                )
            if self.expected_source_mode != "real":
                raise ValueError(
                    "formal completed data turn must target source_mode=real"
                )
        if self.expected_intent in {"clarification", "unsupported"}:
            if self.oracle_key is not None:
                raise ValueError("clarification/unsupported cannot define oracle_key")
            if self.expected_memory_commit:
                raise ValueError("clarification/unsupported cannot commit memory")
        if self.expected_pending_missing_slots and (
            self.expected_terminal_state != "clarification_required"
        ):
            raise ValueError(
                "pending clarification slots require clarification_required"
            )
        if self.expected_failure_stage and self.expected_memory_commit:
            raise ValueError("failure turn cannot commit memory")
        return self


class MultiTurnSpec(BaseModel):
    turn_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    fixture_key: str = Field(min_length=1)
    expected: MultiTurnExpectedSpec

    model_config = ConfigDict(extra="forbid")


class ConversationSpec(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    turns: list[MultiTurnSpec] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_turn_ids(self) -> "ConversationSpec":
        turn_ids = [turn.turn_id for turn in self.turns]
        request_ids = [turn.request_id for turn in self.turns]
        if len(set(turn_ids)) != len(turn_ids):
            raise ValueError("turn_id must be unique within a conversation")
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("request_id must be unique within a conversation")
        return self
