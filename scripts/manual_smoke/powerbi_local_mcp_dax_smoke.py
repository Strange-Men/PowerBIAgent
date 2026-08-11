"""M2.3 real DAX smoke through ToolGateway and LocalMCPPowerBIAdapter.

Only fixed verification flags are printed. The script never prints model
identity, connection details, DAX payloads, or business values.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from numbers import Number
from pathlib import Path
from types import SimpleNamespace


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CASE_1_DAX = 'EVALUATE\nROW("TestValue", 1)'
_BUSINESS_DAX = """EVALUATE
ROW(
    "Total Sales",
    [Total Sales],
    "Total Quantity",
    [Total Quantity]
)"""


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


def _print_summary(
    *,
    dax_executed: bool = False,
    case_1_rows: int = 0,
    case_1_value_ok: bool = False,
    business_measure_rows: int = 0,
    business_values_present: bool = False,
    source_mode: str = "invalid",
) -> None:
    values = {
        "dax_executed": dax_executed,
        "case_1_rows": case_1_rows,
        "case_1_value_ok": case_1_value_ok,
        "business_measure_rows": business_measure_rows,
        "business_values_present": business_values_present,
        "source_mode": source_mode,
    }
    for key, value in values.items():
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}={value}")


async def _run_smoke() -> int:
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.dax.safety import DAXSafetyValidator
    from backend.app.harness.models import HarnessConfig
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import create_default_tool_gateway
    from backend.app.intent.models import IntentType
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
    from backend.app.schemas.data_contracts import DAXRequest, UserContext

    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.MOCK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    prerequisites_ready = (
        sys.platform == "win32"
        and settings.is_powerbi_local_mcp_configured
        and shutil.which(settings.powerbi_local_mcp_executable) is not None
        and _powerbi_desktop_is_running()
    )
    if not prerequisites_ready:
        _print_summary()
        return 1

    safety = DAXSafetyValidator()
    if not all(
        safety.validate(dax).is_valid
        for dax in (_CASE_1_DAX, _BUSINESS_DAX)
    ):
        _print_summary()
        return 1

    adapter = LocalMCPPowerBIAdapter(
        executable=settings.powerbi_local_mcp_executable,
        package=settings.powerbi_local_mcp_package,
        semantic_model_key=settings.powerbi_local_semantic_model_key,
        readonly=settings.powerbi_local_mcp_readonly,
        timeout=float(settings.request_timeout_seconds),
        max_retries=0,
    )

    async def _unused_renderer(_: object) -> str:
        raise RuntimeError("renderer_not_used_in_dax_smoke")

    config = HarnessConfig.from_settings(settings).model_copy(
        update={"max_powerbi_retries": 0}
    )
    gateway = create_default_tool_gateway(
        adapter,
        SimpleNamespace(render=_unused_renderer),
        config,
    )
    context = ToolExecutionContext(
        intent=IntentType.DATA_QUESTION,
        user=UserContext(
            allowed_semantic_models=[settings.powerbi_local_semantic_model_key],
            allowed_tools=["execute_dax"],
        ),
        runtime_mode=RuntimeDataMode.REAL,
    )

    async def _execute(dax: str, request_id: str):
        return await gateway.execute(
            "execute_dax",
            context,
            DAXRequest(
                semantic_model_key=settings.powerbi_local_semantic_model_key,
                dax=dax,
                max_rows=1,
                timeout_seconds=settings.powerbi_query_timeout_seconds,
                request_id=request_id,
            ),
        )

    try:
        case_1 = await _execute(_CASE_1_DAX, "m2.3-case-1")
        business = await _execute(_BUSINESS_DAX, "m2.3-business-measures")
    except Exception:
        _print_summary()
        return 1

    case_1_ok = (
        case_1.error is None
        and case_1.row_count == 1
        and len(case_1.columns) == 1
        and case_1.rows == [[1]]
    )
    business_values = business.rows[0] if business.row_count == 1 else []
    business_ok = (
        business.error is None
        and len(business.columns) == 2
        and len(business_values) == 2
        and all(
            isinstance(value, Number) and not isinstance(value, bool)
            for value in business_values
        )
    )
    source_real = case_1.source_mode == business.source_mode == "real"
    success = case_1_ok and business_ok and source_real
    _print_summary(
        dax_executed=success,
        case_1_rows=case_1.row_count,
        case_1_value_ok=case_1_ok,
        business_measure_rows=business.row_count,
        business_values_present=business_ok,
        source_mode="real" if source_real else "invalid",
    )
    return 0 if success else 1


def main() -> int:
    return asyncio.run(_run_smoke())


if __name__ == "__main__":
    raise SystemExit(main())
