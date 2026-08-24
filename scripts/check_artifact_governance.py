"""Artifact Governance Gate — read-only, never cleans user data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.persistence.artifact_governance import audit_artifacts


def main() -> int:
    result = audit_artifacts(ROOT)
    if result.passed:
        print("Artifact Governance Gate: PASS")
        return 0
    print("Artifact Governance Gate: FAIL")
    for violation in result.violations:
        print(f"- {violation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
