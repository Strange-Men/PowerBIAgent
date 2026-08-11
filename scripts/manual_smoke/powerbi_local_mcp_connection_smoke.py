"""M2.1 Power BI Local MCP minimum real-connection manual smoke.

Only validates stdio startup, MCP negotiation, tool discovery, Desktop instance
discovery, and Desktop connection. It never reads model schema or executes DAX.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _powerbi_desktop_is_running() -> bool:
    if sys.platform != "win32":
        return False
    check = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "if (Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue) "
                "{ exit 0 } else { exit 1 }"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return check.returncode == 0


def _failure(category: str, error_type: str) -> dict[str, object]:
    return {
        "result": "FAIL",
        "desktop_detected": False,
        "connection": False,
        "protocol": None,
        "tool_count": 0,
        "schema_capability": False,
        "dax_capability": False,
        "readonly": True,
        "error_category": category,
        "error_type": error_type,
        "schema_read": False,
        "dax_executed": False,
        "deepseek_calls": 0,
    }


async def _run_smoke() -> int:
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    if sys.platform != "win32":
        result = _failure("LOCAL_PREREQUISITE", "windows_required")
    elif not settings.is_powerbi_local_mcp_configured:
        result = _failure("LOCAL_PREREQUISITE", "invalid_local_mcp_configuration")
    elif shutil.which(settings.powerbi_local_mcp_executable) is None:
        result = _failure("LOCAL_PREREQUISITE", "local_mcp_executable_missing")
    elif not _powerbi_desktop_is_running():
        result = _failure("LOCAL_PREREQUISITE", "powerbi_desktop_not_running")
    else:
        adapter = LocalMCPPowerBIAdapter(
            executable=settings.powerbi_local_mcp_executable,
            package=settings.powerbi_local_mcp_package,
            readonly=settings.powerbi_local_mcp_readonly,
            timeout=float(settings.request_timeout_seconds),
            max_retries=1,
        )
        success = await adapter.health_check()
        result = adapter.last_diagnostics.safe_dict()
        result.update(
            {
                "result": "PASS" if success else "FAIL",
                "schema_read": False,
                "dax_executed": False,
                "deepseek_calls": 0,
            }
        )

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


def main() -> int:
    return asyncio.run(_run_smoke())


if __name__ == "__main__":
    raise SystemExit(main())
