"""Golden Case Runner 入口 — M0.3.2

运行:
    D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

每个 Case 使用独立的 MockTurnService 和 MemoryRepository。
"""

import asyncio
import sys
from pathlib import Path

from backend.app.application.mock_turn_service import MockTurnService
from backend.app.harness.cases.case_runner import GoldenCaseRunner

CASES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "harness" / "cases"


def main():
    """主入口"""
    # factory 为每个 Case 创建独立 Service
    def service_factory():
        return MockTurnService()

    runner = GoldenCaseRunner(CASES_DIR, service_factory=service_factory)

    summary = asyncio.run(runner.run_all_async())

    print("=" * 60)
    print("Golden Cases 运行结果")
    print("=" * 60)

    status_icons = {"passed": "[PASS]", "failed": "[FAIL]", "error": "[ERR!]", "skipped": "[SKIP]"}

    for result in summary.results:
        icon = status_icons.get(result.status, "[????]")
        print(f"\n{icon} [{result.case_id}] -- {result.status}")
        if result.mismatches:
            for m in result.mismatches:
                print(f"    MISMATCH: {m}")
        if result.errors:
            for e in result.errors:
                print(f"    ERROR: {e}")
        if result.duration_ms:
            print(f"    TIME: {result.duration_ms:.0f}ms")

    print("\n" + "=" * 60)
    print("摘要")
    print("=" * 60)
    print(f"  定义: {summary.defined}")
    print(f"  可运行: {summary.runnable}")
    print(f"  [PASS] 通过: {summary.passed}")
    print(f"  [FAIL] 失败: {summary.failed}")
    print(f"  [SKIP] 跳过: {summary.skipped}")
    print(f"  [ERR!] 错误: {summary.errors}")

    if summary.all_runnable_passed:
        print("\n>>> 全部可运行 Case 通过！")
    else:
        print("\n>>> 有 Case 未通过，请检查上方输出。")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
