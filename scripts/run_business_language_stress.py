"""Run the deterministic M5.9.4 language stress suite and print safe JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.tests.stress.business_language_stress import (
    DEFAULT_CASES_PER_DOMAIN_SHAPE,
    DEFAULT_SEED,
    BusinessLanguageStressHarness,
    coverage_matrix,
    generate_cases,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--cases-per-domain-shape",
        type=int,
        default=DEFAULT_CASES_PER_DOMAIN_SHAPE,
    )
    parser.add_argument("--failure-limit", type=int, default=20)
    args = parser.parse_args()
    if args.cases_per_domain_shape < 1:
        parser.error("--cases-per-domain-shape must be positive")

    cases = list(
        generate_cases(
            seed=args.seed,
            cases_per_domain_shape=args.cases_per_domain_shape,
        )
    )
    summary = BusinessLanguageStressHarness(seed=args.seed).run(
        cases_per_domain_shape=args.cases_per_domain_shape
    )
    payload = summary.as_dict(failure_limit=args.failure_limit)
    payload["coverage"] = coverage_matrix(cases)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
