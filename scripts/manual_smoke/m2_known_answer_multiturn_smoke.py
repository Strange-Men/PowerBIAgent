"""M2.6.1 Known-answer / multi-turn acceptance entrypoint.

Default mode is fully offline and uses fictional Fake/Mock values. ``real``
only validates that the local-only baseline is configured; actual DeepSeek,
Local MCP and Desktop execution remains deliberately reserved for M2.6.2.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from backend.app.harness.cases.multi_turn_runner import MultiTurnBenchmarkRunner
    from backend.app.harness.oracles import BaselineSource

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "real"), default="offline")
    args = parser.parse_args()
    runner = MultiTurnBenchmarkRunner()

    # Always validate committed specifications before running either mode.
    conversations = runner.load_conversations()
    known_answers = runner.load_known_answer_cases()

    if args.mode == "real":
        required_keys = {case.oracle_key for case in known_answers}
        required_keys.update(
            turn.expected.oracle_key
            for conversation in conversations
            for turn in conversation.turns
            if turn.expected.oracle_key is not None
        )
        configured, code, count = runner.oracle.validate_keys(
            BaselineSource.REAL_LOCAL, required_keys
        )
        print(json.dumps({
            "mode": "real",
            "ready": False,
            "status": code if not configured else "m2_6_2_execution_required",
            "configured_baseline_count": count,
            "conversation_count": len(conversations),
            "known_answer_case_count": len(known_answers),
            "deepseek_real_calls": 0,
            "local_mcp_real_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 2

    summary = asyncio.run(runner.run_offline())
    payload = summary.model_dump(mode="json")
    payload["known_answer_case_count"] = len(known_answers)
    payload["holdout_case_count"] = sum(item.holdout for item in known_answers)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
