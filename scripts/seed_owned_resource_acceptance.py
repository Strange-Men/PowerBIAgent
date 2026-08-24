"""Seed explicitly owned Settings acceptance fixtures through production repositories."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config.settings import Settings
from backend.app.memory.models import RuntimeDataMode
from backend.app.memory.result_snapshot import ReportResultSnapshot, TurnResultSnapshot
from backend.app.persistence.artifact_ownership import (
    ArtifactOwnershipRegistry,
    OwnedTestRunHandle,
)
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.repositories.report_artifact import (
    SQLiteReportArtifactRepository,
)
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.report.resources import LocalReportRepository
from backend.app.schemas.data_contracts import ReportSpec


async def _seed(args: argparse.Namespace) -> None:
    settings = Settings()
    registry = ArtifactOwnershipRegistry(args.registry)
    owned = registry.get_active(args.run_id)
    if owned.runtime_mode != "real" or owned.source_mode != "real":
        raise RuntimeError("acceptance_run_must_be_real_owned")
    handle = OwnedTestRunHandle(registry, args.run_id)
    engine = create_engine(settings, echo=False)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    snapshots = SQLiteSnapshotRepository(session_factory)
    metadata = SQLiteReportArtifactRepository(session_factory)
    reports = LocalReportRepository(settings.report_artifacts_path, metadata)
    try:
        for index in range(args.conversations):
            conversation_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{args.run_id}:conversation:{index}")
            )
            request_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{args.run_id}:answer:{index}")
            )
            handle.add_conversation(conversation_id)
            await snapshots.save(
                TurnResultSnapshot(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    intent="data_question",
                    response_type="answer",
                    terminal_state="completed",
                    answer=f"M5.4.1 automation-owned acceptance answer {index + 1}",
                    user_message=f"M5.4.1 验收对话 {index + 1:02d}",
                    memory_commit=False,
                    final_memory_version=None,
                    is_mock=False,
                    source_mode="real",
                    request_fingerprint_hash=hashlib.sha256(
                        request_id.encode()
                    ).hexdigest(),
                ),
                RuntimeDataMode.REAL,
            )
            if index >= args.reports:
                continue
            report_request_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{args.run_id}:report:{index}")
            )
            artifact = await reports.store(
                ReportSpec(
                    title=f"M5.4.1 验收报表 {index + 1:02d}",
                    template_key="test_report",
                    summary="automation-owned Settings lifecycle acceptance",
                    source_mode="real",
                ),
                (
                    "<!DOCTYPE html><html><body>"
                    f"M5.4.1 automation-owned report {index + 1}"
                    "</body></html>"
                ),
                conversation_id=conversation_id,
                request_id=report_request_id,
            )
            handle.add_report(
                artifact.report_id,
                html_path=reports.root / f"{artifact.report_id}.html",
            )
            await snapshots.save(
                TurnResultSnapshot(
                    request_id=report_request_id,
                    conversation_id=conversation_id,
                    intent="report_generation",
                    response_type="report",
                    terminal_state="completed",
                    report=ReportResultSnapshot(
                        report_id=artifact.report_id,
                        template_key=artifact.template_key,
                        contract_version=artifact.contract_version,
                        view_reference=artifact.view_reference,
                        download_reference=artifact.download_reference,
                        content_type=artifact.content_type,
                        content_hash=artifact.content_hash,
                    ),
                    user_message=f"生成 M5.4.1 验收报表 {index + 1:02d}",
                    memory_commit=False,
                    final_memory_version=None,
                    is_mock=False,
                    source_mode="real",
                    request_fingerprint_hash=hashlib.sha256(
                        report_request_id.encode()
                    ).hexdigest(),
                ),
                RuntimeDataMode.REAL,
            )
    finally:
        await dispose_engine(engine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--conversations", type=int, default=25)
    parser.add_argument("--reports", type=int, default=10)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "local_state" / "runtime" / "artifact_ownership.json",
    )
    args = parser.parse_args()
    if not 1 <= args.conversations <= 100:
        parser.error("conversations must be between 1 and 100")
    if not 0 <= args.reports <= args.conversations:
        parser.error("reports must be between 0 and conversations")
    asyncio.run(_seed(args))
    print(
        f"seeded:{args.run_id}:conversations={args.conversations}:reports={args.reports}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
