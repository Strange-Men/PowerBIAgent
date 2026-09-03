"""Repository-wide test artifact lifecycle isolation.

Every application instance created by pytest receives per-test default report
and SQLite paths outside the source tree. The fixture owns those paths and
verifies cleanup so developer dotenv configuration cannot target user storage.

All backend tests run in LLM_MODE=mock + POWERBI_MODE=mock + memory persistence
regardless of the local .env file, so create_app() always initializes with
MockTurnService and mock PowerBI adapter.
"""

from __future__ import annotations

import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from backend.app.config.settings import get_settings
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry


@pytest.fixture(autouse=True)
def isolate_managed_report_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    """Register, isolate, tear down, and verify each test's report root."""

    # Force mock modes so create_app().lifespan always produces MockTurnService
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("POWERBI_MODE", "mock")
    monkeypatch.setenv("PERSISTENCE_BACKEND", "memory")

    test_root = (tmp_path / "owned_test_artifacts" / "reports").resolve()
    persistence_root = (tmp_path / "owned_test_artifacts" / "persistence").resolve()
    database_path = persistence_root / "test.db"
    persistence_root = (tmp_path / "owned_test_artifacts" / "persistence").resolve()
    database_path = persistence_root / "test.db"
    owner_root = tmp_path.resolve()
    if not all(path.is_relative_to(owner_root) for path in (test_root, persistence_root)):
        raise AssertionError("test artifact root escaped pytest ownership")

    registry = ArtifactOwnershipRegistry(
        tmp_path / "owned_test_artifacts" / "runtime" / "artifact_ownership.json"
    )
    test_run_id = "pytest-" + sha256(request.node.nodeid.encode()).hexdigest()[:16]
    ownership = registry.register_run(
        test_run_id=test_run_id,
        test_namespace=request.node.nodeid,
        runtime_mode="isolated",
        source_mode="isolated",
    )
    ownership.add_report_root(test_root)
    ownership.add_sqlite_path(database_path)

    monkeypatch.setenv("REPORT_ARTIFACTS_PATH", str(test_root))
    monkeypatch.setenv("PERSISTENCE_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

    try:
        for owned_root in (test_root, persistence_root):
            if owned_root.exists():
                shutil.rmtree(owned_root)
            if owned_root.exists():
                raise AssertionError("test artifact cleanup failed")
    except Exception as error:
        registry.record_failure(test_run_id, [f"owned_root:{error}"])
        raise
    else:
        registry.complete_run(test_run_id)
