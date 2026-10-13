"""Operator-owned catalog seeds, never a public request contract."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class SharedModelSeed(BaseModel):
    workspace_id: UUID
    model_id: UUID
    workspace_display_name: str = Field(min_length=1, max_length=200)
    model_config = ConfigDict(extra="forbid", frozen=True)
