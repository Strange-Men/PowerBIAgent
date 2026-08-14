"""Known-answer / multi-turn acceptance entrypoint.

``offline`` preserves the M2.6.1 Fake/Mock regression. ``real`` is the M2.6.3
production gate: formal Chat API, DeepSeek, Local MCP, production Memory,
deterministic DAX, independent Layer3, VerifiedFactSet, and exact real oracle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from backend.app.harness.cases.multi_turn_runner import MultiTurnBenchmarkRunner
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.cases.production_e2e_runner import ProductionE2ERunner

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "real"), default="offline")
    parser.add_argument("--historical-repeats", type=int, default=10)
    args = parser.parse_args()
    if args.historical_repeats < 1:
        parser.error("--historical-repeats must be >= 1")
    runner = MultiTurnBenchmarkRunner()

    # Always validate committed specifications before running either mode.
    conversations = runner.load_conversations()
    known_answers = runner.load_known_answer_cases()

    if args.mode == "real":
        settings = Settings(
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
        )
        ready = all((
            sys.platform == "win32",
            settings.is_deepseek_configured,
            settings.is_powerbi_local_mcp_configured,
            shutil.which(settings.powerbi_local_mcp_executable) is not None,
            _desktop_running(),
        ))
        if not ready:
            print(json.dumps({
                "passed": False,
                "status": "local_prerequisite_missing",
                "known_exact_executed": 0,
                "fallback_count": 0,
                "state_pollution_count": 0,
            }, ensure_ascii=False, indent=2))
            return 1
        payload = asyncio.run(
            ProductionE2ERunner(settings).run(
                historical_repeats=args.historical_repeats
            )
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("passed") else 1

    summary = asyncio.run(runner.run_offline())
    payload = summary.model_dump(mode="json")
    payload["known_answer_case_count"] = len(known_answers)
    payload["holdout_case_count"] = sum(item.holdout for item in known_answers)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary.passed else 1


def _desktop_running() -> bool:
    if sys.platform != "win32":
        return False
    result = subprocess.run(
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
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
