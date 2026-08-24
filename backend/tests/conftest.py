"""Repository-wide test artifact lifecycle isolation.

Every application instance created by pytest receives a per-test managed report
root outside the source tree.  The fixture owns that root, tears it down after
the test, and verifies cleanup so tests cannot leak HTML into real local_state.
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

    test_root = (tmp_path / "owned_test_artifacts" / "reports").resolve()
    owner_root = tmp_path.resolve()
    if not test_root.is_relative_to(owner_root):
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

    monkeypatch.setenv("REPORT_ARTIFACTS_PATH", str(test_root))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

    try:
        if test_root.exists():
            shutil.rmtree(test_root)
        if test_root.exists():
            raise AssertionError("test report artifact cleanup failed")
    except Exception as error:
        registry.record_failure(test_run_id, [f"report_root:{error}"])
        raise
    else:
        registry.complete_run(test_run_id)
