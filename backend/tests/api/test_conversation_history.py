"""M4.3 Conversation History/Search API contract tests."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_report_repository
from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.main import create_app
from backend.app.memory.models import MemoryStatus, RuntimeDataMode, StructuredWorkMemory
from backend.app.memory.result_snapshot import TurnResultSnapshot
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import (
    Base,
    ConversationModel,
    ResultSnapshotModel,
    WorkMemoryModel,
)
from backend.app.persistence.serialization import domain_to_json
from backend.app.report.resources import InMemoryReportRepository, ReportSpec


async def _prepare_database(db_path: Path) -> None:
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    created_at = datetime(2026, 8, 20, 11, 0, 0)
    async with session_factory() as session:
        async with session.begin():
            for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
                conversation_id = "shared-api-conversation"
                request_id = f"req-api-{mode.value}"
                session.add(
                    ConversationModel(
                        conversation_id=conversation_id,
                        runtime_mode=mode.value,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
                snapshot = TurnResultSnapshot(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    intent="data_question",
                    response_type="answer",
                    terminal_state="completed",
                    answer=f"{mode.value} API answer",
                    memory_commit=True,
                    final_memory_version=1,
                    is_mock=mode == RuntimeDataMode.MOCK,
                    source_mode=mode.value,
                    request_fingerprint_hash=hashlib.sha256(
                        request_id.encode()
                    ).hexdigest(),
                )
                session.add(
                    ResultSnapshotModel(
                        request_id=request_id,
                        runtime_mode=mode.value,
                        conversation_id=conversation_id,
                        request_fingerprint_hash=snapshot.request_fingerprint_hash,
                        terminal_state="completed",
                        response_type="answer",
                        payload_json=domain_to_json(snapshot),
                        created_at=created_at,
                    )
                )
                memory = StructuredWorkMemory(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    semantic_model_key="stored_model",
                    current_intent="data_question",
                    analysis_goal=f"用户提问: {mode.value} API question",
                    state_status=MemoryStatus.COMMITTED,
                    runtime_mode=mode,
                    memory_version=1,
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(
                    WorkMemoryModel(
                        request_id=request_id,
                        conversation_id=conversation_id,
                        runtime_mode=mode.value,
                        state_status="committed",
                        base_memory_version=0,
                        memory_version=1,
                        semantic_model_key="stored_model",
                        current_intent="data_question",
                        analysis_goal=memory.analysis_goal,
                        payload_json=domain_to_json(memory),
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
    await dispose_engine(engine)


def _sqlite_app(tmp_path: Path):
    db_path = tmp_path / "api-history.db"
    asyncio.run(_prepare_database(db_path))
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    return create_app(settings=settings)


def test_history_api_requires_explicit_namespace_and_never_exposes_payload_or_html(
    tmp_path: Path,
) -> None:
    app = _sqlite_app(tmp_path)
    with TestClient(app) as client:
        missing_namespace = client.get("/api/v1/conversations")
        assert missing_namespace.status_code == 422

        mock = client.get(
            "/api/v1/conversations/shared-api-conversation/history",
            params={"runtime_mode": "mock", "limit": 20},
        )
        real = client.get(
            "/api/v1/conversations/shared-api-conversation/history",
            params={"runtime_mode": "real", "limit": 20},
        )

    assert mock.status_code == 200
    assert real.status_code == 200
    assert [item["answer"] for item in mock.json()["items"]] == ["mock API answer"]
    assert [item["answer"] for item in real.json()["items"]] == ["real API answer"]
    assert [item["user_message"] for item in mock.json()["items"]] == [
        "mock API question"
    ]
    serialized = mock.text
    assert "payload_json" not in serialized
    assert "<!DOCTYPE html>" not in serialized


def test_title_rename_is_presentation_only_and_searchable(tmp_path: Path) -> None:
    app = _sqlite_app(tmp_path)
    with TestClient(app) as client:
        renamed = client.patch(
            "/api/v1/conversations/shared-api-conversation",
            params={"runtime_mode": "real"},
            json={"title": "  八月销售复盘  "},
        )
        recent = client.get(
            "/api/v1/conversations",
            params={"runtime_mode": "real", "limit": 20},
        )
        history = client.get(
            "/api/v1/conversations/shared-api-conversation/history",
            params={"runtime_mode": "real", "limit": 20},
        )
        search = client.get(
            "/api/v1/conversations/search",
            params={"runtime_mode": "real", "q": "八月销售", "limit": 20},
        )

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "八月销售复盘"
    assert recent.json()["items"][0]["title"] == "八月销售复盘"
    assert history.json()["title"] == "八月销售复盘"
    assert search.json()["items"][0]["conversation_id"] == "shared-api-conversation"


def test_search_api_namespace_and_declared_content_contract(tmp_path: Path) -> None:
    app = _sqlite_app(tmp_path)
    with TestClient(app) as client:
        mock = client.get(
            "/api/v1/conversations/search",
            params={"runtime_mode": "mock", "q": "API question", "limit": 20},
        )
        real = client.get(
            "/api/v1/conversations/search",
            params={"runtime_mode": "real", "q": "API question", "limit": 20},
        )
    assert mock.status_code == 200
    assert real.status_code == 200
    assert [(x["runtime_mode"], x["conversation_id"]) for x in mock.json()["items"]] == [
        ("mock", "shared-api-conversation")
    ]
    assert [(x["runtime_mode"], x["conversation_id"]) for x in real.json()["items"]] == [
        ("real", "shared-api-conversation")
    ]


def test_invalid_limits_cursors_and_unknown_conversations_fail_explicitly(
    tmp_path: Path,
) -> None:
    app = _sqlite_app(tmp_path)
    with TestClient(app) as client:
        assert client.get(
            "/api/v1/conversations",
            params={"runtime_mode": "mock", "limit": 0},
        ).status_code == 422
        invalid_cursor = client.get(
            "/api/v1/conversations",
            params={
                "runtime_mode": "mock",
                "limit": 20,
                "cursor": "not-valid-base64",
            },
        )
        assert invalid_cursor.status_code == 422
        assert invalid_cursor.json()["detail"] == "invalid_cursor"

        for method, path in (
            ("get", "/api/v1/conversations/missing/history"),
            ("get", "/api/v1/conversations/missing/reports"),
            ("post", "/api/v1/conversations/missing/archive"),
            ("delete", "/api/v1/conversations/missing"),
        ):
            namespace_key = "source_mode" if path.endswith("/reports") else "runtime_mode"
            response = getattr(client, method)(
                path, params={namespace_key: "mock", "limit": 20}
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "conversation_not_found"


def test_archive_has_a_visible_restore_path_and_keeps_history(tmp_path: Path) -> None:
    app = _sqlite_app(tmp_path)
    with TestClient(app) as client:
        archived = client.post(
            "/api/v1/conversations/shared-api-conversation/archive",
            params={"runtime_mode": "real"},
        )
        recent = client.get(
            "/api/v1/conversations", params={"runtime_mode": "real"}
        )
        archive_page = client.get(
            "/api/v1/conversations/archived",
            params={"runtime_mode": "real"},
        )
        history = client.get(
            "/api/v1/conversations/shared-api-conversation/history",
            params={"runtime_mode": "real"},
        )
        restored = client.post(
            "/api/v1/conversations/shared-api-conversation/restore",
            params={"runtime_mode": "real"},
        )
        recent_after = client.get(
            "/api/v1/conversations", params={"runtime_mode": "real"}
        )

    assert archived.status_code == 200
    assert recent.json()["items"] == []
    assert archive_page.json()["items"][0]["conversation_id"] == (
        "shared-api-conversation"
    )
    assert history.json()["items"][0]["answer"] == "real API answer"
    assert restored.status_code == 200 and restored.json()["restored"] is True
    assert recent_after.json()["items"][0]["conversation_id"] == (
        "shared-api-conversation"
    )


def test_report_delete_api_is_explicit_and_not_a_toolgateway_capability() -> None:
    repository = InMemoryReportRepository()
    artifact = asyncio.run(repository.store(
        ReportSpec(title="resource", template_key="test_report", source_mode="mock"),
        "<!DOCTYPE html><html><body>resource</body></html>",
        conversation_id="conversation-kept",
        request_id="request-report",
    ))
    app = create_app(settings=Settings(_env_file=None))
    app.dependency_overrides[get_report_repository] = lambda: repository
    with TestClient(app) as client:
        deleted = client.delete(f"/api/reports/{artifact.report_id}")
        missing = client.get(f"/api/reports/{artifact.report_id}")
        allowed_tools = app.state.mock_turn_service.tool_gateway.list_tools()

    assert deleted.status_code == 200
    assert deleted.json()["conversation_id"] == "conversation-kept"
    assert deleted.json()["deleted"] is True
    assert missing.status_code == 404
    assert all("delete" not in name for name in allowed_tools)
