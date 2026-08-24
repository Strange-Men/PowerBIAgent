"""Register and clean automation-owned API resources without title guessing."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.persistence.artifact_ownership import (
    ArtifactOwnershipRegistry,
    OwnedTestRun,
    OwnedTestRunHandle,
    cleanup_owned_test_run,
    probe_owned_sqlite_residuals,
)
from backend.app.config.settings import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "local_state" / "runtime" / "artifact_ownership.json",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    register = commands.add_parser("register")
    register.add_argument("--run-id", required=True)
    register.add_argument("--namespace", required=True)
    register.add_argument("--runtime-mode", choices=("mock", "real"), required=True)
    register.add_argument("--source-mode", choices=("mock", "real"), required=True)

    add = commands.add_parser("add")
    add.add_argument("--run-id", required=True)
    add.add_argument("--conversation", action="append", default=[])
    add.add_argument("--report", action="append", default=[])
    add.add_argument("--html-path", type=Path, action="append", default=[])
    add.add_argument("--sqlite-path", type=Path, action="append", default=[])

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--base-url", default="http://127.0.0.1:8000")
    return parser


async def _cleanup(
    registry: ArtifactOwnershipRegistry,
    run_id: str,
    base_url: str,
) -> None:
    run = registry.get_active(run_id)
    settings = Settings()
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:

        async def delete_conversation(conversation_id: str) -> None:
            response = await client.delete(
                f"/api/v1/conversations/{conversation_id}",
                params={"runtime_mode": run.runtime_mode},
            )
            if response.status_code not in {200, 404}:
                response.raise_for_status()

        async def delete_report(report_id: str) -> None:
            response = await client.delete(f"/api/reports/{report_id}")
            if response.status_code not in {200, 404}:
                response.raise_for_status()

        async def residual_probe(owned: OwnedTestRun) -> list[str]:
            failures: list[str] = []
            conversation_ids = set(owned.conversation_ids)
            report_ids = set(owned.report_ids)
            for archived in (False, True):
                path = (
                    "/api/v1/conversations/archived"
                    if archived
                    else "/api/v1/conversations"
                )
                found = await _collect_ids(
                    client,
                    path,
                    {"runtime_mode": owned.runtime_mode},
                    "conversation_id",
                )
                for residual in sorted(conversation_ids & found):
                    failures.append(f"conversation_metadata:{residual}")
            for status in ("active", "archived"):
                found = await _collect_ids(
                    client,
                    "/api/reports",
                    {"source_mode": owned.source_mode, "status": status},
                    "report_id",
                )
                for residual in sorted(report_ids & found):
                    failures.append(f"report_metadata:{residual}")
            for raw_path in (*owned.html_paths, *owned.sqlite_paths):
                if Path(raw_path).exists():
                    failures.append(f"filesystem:{raw_path}")
            database_path = Path(settings.persistence_database_path)
            if not database_path.is_absolute():
                database_path = ROOT / database_path
            failures.extend(probe_owned_sqlite_residuals(database_path, owned))
            return failures

        await cleanup_owned_test_run(
            registry,
            run_id,
            delete_conversation=delete_conversation,
            delete_report=delete_report,
            residual_probe=residual_probe,
        )


async def _collect_ids(
    client: httpx.AsyncClient,
    path: str,
    base_params: dict[str, str],
    id_field: str,
) -> set[str]:
    found: set[str] = set()
    cursor: str | None = None
    while True:
        params = {**base_params, "limit": "50"}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        found.update(item[id_field] for item in payload["items"])
        cursor = payload.get("next_cursor")
        if not cursor:
            return found


def main() -> int:
    args = _parser().parse_args()
    registry = ArtifactOwnershipRegistry(args.registry)
    if args.command == "register":
        registry.register_run(
            test_run_id=args.run_id,
            test_namespace=args.namespace,
            runtime_mode=args.runtime_mode,
            source_mode=args.source_mode,
        )
        print(f"registered:{args.run_id}")
        return 0
    if args.command == "add":
        registry.get_active(args.run_id)
        owned = OwnedTestRunHandle(registry, args.run_id)
        for conversation_id in args.conversation:
            owned.add_conversation(conversation_id)
        for report_id in args.report:
            owned.add_report(report_id)
        for path in args.html_path:
            registry.add_resource(args.run_id, "html_paths", str(path.resolve()))
        for path in args.sqlite_path:
            owned.add_sqlite_path(path)
        print(f"updated:{args.run_id}")
        return 0
    asyncio.run(_cleanup(registry, args.run_id, args.base_url))
    print(f"cleaned:{args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
