"""Secret-safe startup diagnostics for the local PowerBIAgent runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.config.settings import Settings


_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


@dataclass(frozen=True)
class DotenvFormatDiagnostic:
    path: Path
    exists: bool
    valid: bool
    invalid_line_numbers: tuple[int, ...]


def inspect_dotenv_format(path: Path) -> DotenvFormatDiagnostic:
    """Validate the project-specific one-line ``KEY=value`` contract.

    Values are never returned, logged, or included in an exception.  The
    validator only reports line numbers whose shape is neither an assignment,
    a comment, nor a blank line.
    """
    env_path = Path(path)
    if not env_path.exists():
        return DotenvFormatDiagnostic(
            path=env_path,
            exists=False,
            valid=True,
            invalid_line_numbers=(),
        )
    invalid: list[int] = []
    with env_path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not _ENV_ASSIGNMENT.fullmatch(stripped):
                invalid.append(line_number)
    return DotenvFormatDiagnostic(
        path=env_path,
        exists=True,
        valid=not invalid,
        invalid_line_numbers=tuple(invalid),
    )


def safe_startup_summary(settings: Settings) -> dict[str, object]:
    """Build the exact safe fields shown by the CLI and health endpoint."""
    return {
        "llm_mode": settings.llm_mode.value,
        "powerbi_mode": settings.powerbi_mode.value,
        "persistence_backend": settings.persistence_backend.value,
        "max_tool_calls": settings.max_tool_calls,
        "local_mcp_readonly": settings.powerbi_local_mcp_readonly,
        "deepseek_configured": settings.is_deepseek_configured,
        "real_mode_configuration_complete": (
            settings.is_local_real_configuration_complete
        ),
        "real_mode_reasons": settings.local_real_configuration_reasons,
    }
