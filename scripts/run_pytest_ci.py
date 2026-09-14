"""Run pytest while publishing bounded GitHub Actions failure annotations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _escape_command_data(value: object) -> str:
    return (
        str(value)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _escape_command_property(value: object) -> str:
    return (
        _escape_command_data(value)
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


class _GitHubFailureAnnotations:
    """Emit only failing reports; pytest remains the sole exit-code authority."""

    @staticmethod
    def _emit(phase: str, report: Any) -> None:
        nodeid = getattr(report, "nodeid", "pytest")
        detail = getattr(report, "longreprtext", None) or str(
            getattr(report, "longrepr", "pytest failure")
        )
        # Keep annotations useful and bounded; the complete traceback remains in logs.
        message = detail[-3500:]
        title = _escape_command_property(f"pytest {phase}: {nodeid}")
        print(f"::error title={title}::{_escape_command_data(message)}", flush=True)

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self._emit("collection", report)

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.failed:
            self._emit(getattr(report, "when", "test"), report)


def main() -> int:
    args = sys.argv[1:] or ["backend/tests", "-q"]
    return int(pytest.main(args, plugins=[_GitHubFailureAnnotations()]))


if __name__ == "__main__":
    raise SystemExit(main())
