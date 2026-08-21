"""Safe semantic-model discovery contracts for M5.2.

These models deliberately exclude Desktop ports, connection strings, process
identifiers, filesystem paths, MCP payloads, and semantic schema details.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SemanticModelOption(BaseModel):
    """One backend-confirmed model that the frontend may select."""

    key: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    source: Literal["mock", "local_desktop"]
    type: Literal["semantic_model"] = "semantic_model"
    available: bool
    connected: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticModelCatalog(BaseModel):
    """Safe discovery response plus the backend runtime namespace."""

    runtime_mode: Literal["mock", "real"]
    items: list[SemanticModelOption] = Field(default_factory=list)
    error_type: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)
