"""Explicit ownership and fail-closed cleanup for automation-created resources.

The registry contains only resources that a test run explicitly created.  Cleanup
therefore never guesses from titles, timestamps, or user-visible content.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REGISTRY_VERSION = 2
AUTOMATION_OWNER = "automation"


class ArtifactOwnershipError(RuntimeError):
    """Raised when ownership is invalid or owned cleanup is incomplete."""


@dataclass(frozen=True)
class OwnedTestRun:
    test_run_id: str
    test_owner: str
    test_namespace: str
    runtime_mode: str
    source_mode: str
    conversation_ids: tuple[str, ...]
    report_ids: tuple[str, ...]
    html_paths: tuple[str, ...]
    sqlite_paths: tuple[str, ...]


class ArtifactOwnershipRegistry:
    """Small durable registry used by pytest, smoke, and browser acceptance."""

    def __init__(self, path: Path) -> None:
        self._path = path.resolve()

    def register_run(
        self,
        *,
        test_run_id: str,
        test_namespace: str,
        runtime_mode: str,
        source_mode: str,
        test_owner: str = AUTOMATION_OWNER,
    ) -> "OwnedTestRunHandle":
        if test_owner != AUTOMATION_OWNER:
            raise ArtifactOwnershipError("test_owner_must_be_automation")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                test_run_id,
                test_namespace,
                runtime_mode,
                source_mode,
            )
        ):
            raise ArtifactOwnershipError("test_ownership_fields_required")
        payload = self._load()
        if any(
            item.get("test_run_id") == test_run_id for item in payload["active"]
        ):
            raise ArtifactOwnershipError("test_run_already_active")
        payload["active"].append(
            {
                "owner_id": f"{test_owner}:{test_run_id}",
                "test_run_id": test_run_id,
                "test_owner": test_owner,
                "test_namespace": test_namespace,
                "runtime_mode": runtime_mode,
                "source_mode": source_mode,
                "conversation_ids": [],
                "report_ids": [],
                "html_paths": [],
                "sqlite_paths": [],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        self._save(payload)
        return OwnedTestRunHandle(self, test_run_id)

    def get_active(self, test_run_id: str) -> OwnedTestRun:
        item = self._find_active(self._load(), test_run_id)
        return _parse_run(item)

    def add_resource(self, test_run_id: str, field: str, value: str) -> None:
        if field not in {
            "conversation_ids",
            "report_ids",
            "html_paths",
            "sqlite_paths",
        }:
            raise ArtifactOwnershipError("unsupported_owned_resource_field")
        if not isinstance(value, str) or not value.strip():
            raise ArtifactOwnershipError("owned_resource_value_required")
        payload = self._load()
        item = self._find_active(payload, test_run_id)
        values = item[field]
        if value not in values:
            values.append(value)
        self._save(payload)

    def complete_run(self, test_run_id: str) -> None:
        payload = self._load()
        self._find_active(payload, test_run_id)
        payload["active"] = [
            item
            for item in payload["active"]
            if item.get("test_run_id") != test_run_id
        ]
        payload["cleanup_failures"] = [
            item
            for item in payload["cleanup_failures"]
            if item.get("test_run_id") != test_run_id
        ]
        self._save(payload)

    def record_failure(self, test_run_id: str, failures: list[str]) -> None:
        payload = self._load()
        item = self._find_active(payload, test_run_id)
        payload["cleanup_failures"] = [
            failure
            for failure in payload["cleanup_failures"]
            if failure.get("test_run_id") != test_run_id
        ]
        payload["cleanup_failures"].append(
            {
                "owner_id": item["owner_id"],
                "test_run_id": test_run_id,
                "failures": failures,
                "failed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._save(payload)

    def _find_active(
        self, payload: dict[str, Any], test_run_id: str
    ) -> dict[str, Any]:
        matches = [
            item
            for item in payload["active"]
            if item.get("test_run_id") == test_run_id
        ]
        if len(matches) != 1:
            raise ArtifactOwnershipError("test_run_not_uniquely_owned")
        return matches[0]

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {
                "version": REGISTRY_VERSION,
                "active": [],
                "cleanup_failures": [],
            }
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArtifactOwnershipError("artifact_ownership_registry_invalid") from error
        if not isinstance(payload, dict):
            raise ArtifactOwnershipError("artifact_ownership_registry_invalid")
        if payload.get("version") == 1:
            if payload.get("active") or payload.get("cleanup_failures"):
                raise ArtifactOwnershipError("legacy_active_ownership_requires_review")
            payload["version"] = REGISTRY_VERSION
        if payload.get("version") != REGISTRY_VERSION:
            raise ArtifactOwnershipError("artifact_ownership_registry_invalid")
        if not isinstance(payload.get("active"), list) or not isinstance(
            payload.get("cleanup_failures"), list
        ):
            raise ArtifactOwnershipError("artifact_ownership_registry_invalid")
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._path)


class OwnedTestRunHandle:
    def __init__(
        self, registry: ArtifactOwnershipRegistry, test_run_id: str
    ) -> None:
        self._registry = registry
        self.test_run_id = test_run_id

    def add_conversation(self, conversation_id: str) -> None:
        self._registry.add_resource(
            self.test_run_id, "conversation_ids", conversation_id
        )

    def add_report(self, report_id: str, *, html_path: Path | None = None) -> None:
        self._registry.add_resource(self.test_run_id, "report_ids", report_id)
        if html_path is not None:
            self._registry.add_resource(
                self.test_run_id, "html_paths", str(html_path.resolve())
            )

    def add_report_root(self, report_root: Path) -> None:
        self._registry.add_resource(
            self.test_run_id, "html_paths", str(report_root.resolve())
        )

    def add_sqlite_path(self, sqlite_path: Path) -> None:
        self._registry.add_resource(
            self.test_run_id, "sqlite_paths", str(sqlite_path.resolve())
        )


DeleteResource = Callable[[str], Awaitable[object]]
ResidualProbe = Callable[[OwnedTestRun], Awaitable[list[str]]]


async def cleanup_owned_test_run(
    registry: ArtifactOwnershipRegistry,
    test_run_id: str,
    *,
    delete_conversation: DeleteResource,
    delete_report: DeleteResource,
    residual_probe: ResidualProbe,
) -> None:
    """Delete only registered IDs and fail if any registered resource remains."""

    run = registry.get_active(test_run_id)
    failures: list[str] = []
    for report_id in run.report_ids:
        try:
            await delete_report(report_id)
        except Exception as error:  # cleanup must aggregate every owned residual
            failures.append(f"report:{report_id}:{type(error).__name__}:{error}")
    for conversation_id in run.conversation_ids:
        try:
            await delete_conversation(conversation_id)
        except Exception as error:  # cleanup must aggregate every owned residual
            failures.append(
                f"conversation:{conversation_id}:{type(error).__name__}:{error}"
            )
    try:
        failures.extend(await residual_probe(run))
    except Exception as error:
        failures.append(f"residual_probe:{type(error).__name__}:{error}")
    if failures:
        registry.record_failure(test_run_id, failures)
        raise ArtifactOwnershipError("test_owned_cleanup_incomplete:" + ";".join(failures))
    registry.complete_run(test_run_id)


@asynccontextmanager
async def managed_test_run(
    registry: ArtifactOwnershipRegistry,
    *,
    test_run_id: str,
    test_namespace: str,
    runtime_mode: str,
    source_mode: str,
    delete_conversation: DeleteResource,
    delete_report: DeleteResource,
    residual_probe: ResidualProbe,
) -> AsyncIterator[OwnedTestRunHandle]:
    """Register a run and always execute its formal cleanup in ``finally``."""

    handle = registry.register_run(
        test_run_id=test_run_id,
        test_namespace=test_namespace,
        runtime_mode=runtime_mode,
        source_mode=source_mode,
    )
    try:
        yield handle
    finally:
        await cleanup_owned_test_run(
            registry,
            test_run_id,
            delete_conversation=delete_conversation,
            delete_report=delete_report,
            residual_probe=residual_probe,
        )


def _parse_run(item: dict[str, Any]) -> OwnedTestRun:
    required = (
        "test_run_id",
        "test_owner",
        "test_namespace",
        "runtime_mode",
        "source_mode",
    )
    if not all(isinstance(item.get(field), str) and item[field] for field in required):
        raise ArtifactOwnershipError("artifact_ownership_registry_invalid")
    list_fields = (
        "conversation_ids",
        "report_ids",
        "html_paths",
        "sqlite_paths",
    )
    if not all(
        isinstance(item.get(field), list)
        and all(isinstance(value, str) and value for value in item[field])
        for field in list_fields
    ):
        raise ArtifactOwnershipError("artifact_ownership_registry_invalid")
    return OwnedTestRun(
        test_run_id=item["test_run_id"],
        test_owner=item["test_owner"],
        test_namespace=item["test_namespace"],
        runtime_mode=item["runtime_mode"],
        source_mode=item["source_mode"],
        conversation_ids=tuple(item["conversation_ids"]),
        report_ids=tuple(item["report_ids"]),
        html_paths=tuple(item["html_paths"]),
        sqlite_paths=tuple(item["sqlite_paths"]),
    )


def probe_owned_sqlite_residuals(
    database_path: Path,
    run: OwnedTestRun,
) -> list[str]:
    """Read only exact registered IDs; never infer ownership from user content."""

    database = database_path.resolve()
    if not database.exists():
        return []
    residuals: list[str] = []
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if run.conversation_ids:
            placeholders = ",".join("?" for _ in run.conversation_ids)
            for table in (
                "conversations",
                "work_memories",
                "pending_clarifications",
                "result_snapshots",
                "conversation_delete_intents",
            ):
                if table not in tables:
                    continue
                rows = conn.execute(
                    f"SELECT DISTINCT conversation_id FROM {table} "
                    f"WHERE runtime_mode = ? AND conversation_id IN ({placeholders})",
                    (run.runtime_mode, *run.conversation_ids),
                ).fetchall()
                residuals.extend(
                    f"sqlite_namespace:{table}:{row[0]}" for row in rows
                )
        if run.report_ids:
            placeholders = ",".join("?" for _ in run.report_ids)
            for table in (
                "report_artifacts",
                "report_presentations",
                "report_delete_intents",
            ):
                if table not in tables:
                    continue
                rows = conn.execute(
                    f"SELECT DISTINCT report_id FROM {table} "
                    f"WHERE report_id IN ({placeholders})",
                    run.report_ids,
                ).fetchall()
                residuals.extend(f"sqlite_report:{table}:{row[0]}" for row in rows)
    return residuals
