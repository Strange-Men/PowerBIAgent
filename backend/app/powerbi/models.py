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
    agent_compatible: bool = False
    selectable: bool = False
    schema_drift: bool = False
    compatibility_status: Literal[
        "compatible", "incompatible", "unavailable"
    ] = "unavailable"

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticModelCatalog(BaseModel):
    """Safe discovery response plus the backend runtime namespace."""

    runtime_mode: Literal["mock", "real"]
    items: list[SemanticModelOption] = Field(default_factory=list)
    error_type: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PowerBICompatibilityProbe(BaseModel):
    """Provider diagnostic result with no connection or business payload."""

    semantic_model_key: str = Field(min_length=1, max_length=200)
    server_started: bool = False
    protocol_negotiated: bool = False
    required_tools_available: bool = False
    instance_matched: bool = False
    connected: bool = False
    schema_read: bool = False
    dax_execute: bool = False
    row_data_verified: bool = False
    compatible: bool = False
    error_type: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)
