"""Auth-owned immutable identity and safe public account projection."""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PrincipalContext(BaseModel):
    tenant_id: str
    principal_id: str
    subject: str
    issuer: str
    display_name: str
    preferred_username: str | None
    auth_source: Literal["entra"] = "entra"
    session_epoch: int
    authorization_epoch: int
    model_config = ConfigDict(frozen=True)


class SessionDTO(BaseModel):
    identity_mode: Literal["LOCAL_DEV", "ENTRA_BFF"]
    authenticated: bool
    display_name: str | None = None
    preferred_username: str | None = None
    state: str
    csrf_token: str | None = None
    expires_in: int = 0


@dataclass(repr=False)
class AuthFailure(Exception):
    code: str = "AUTH_REQUIRED"
    status: int = 401

    def __str__(self):
        return self.code
