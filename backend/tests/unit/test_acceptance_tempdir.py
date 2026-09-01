"""Acceptance-only filesystem cleanup must be safe and truthful."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from scripts.acceptance_tempdir import MARKER, owned_acceptance_tempdir


@pytest.mark.asyncio
async def test_default_sqlite_settings_cannot_point_pytest_at_developer_database(tmp_path):
    from backend.app.config.settings import Settings, PersistenceBackend
    from backend.app.persistence.database import create_engine
    from backend.app.persistence.models import Base

    settings = Settings(_env_file=None, persistence_backend=PersistenceBackend.SQLITE)
    database = Path(settings.persistence_database_path).resolve()
    assert database.is_relative_to(tmp_path.resolve())
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        assert database.is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_negative_gate_rejects_swallowed_provider_failure_and_restores_observer():
    from scripts.manual_smoke.cross_language_real_acceptance import (
        ACCEPTANCE_REQUEST, observe_provider_failures, negative_outcome_verified,
    )
    from backend.app.llm.base import LLMProviderError, LLMRequest, LLMTask, LLMErrorCategory

    class Provider:
        async def generate(self, request, output_type):
            raise LLMProviderError("secret raw payload", error_category=LLMErrorCategory.CONNECTION)

    original = Provider.generate
    failures = {}
    token = ACCEPTANCE_REQUEST.set("owned-request")
    try:
        with observe_provider_failures(failures, provider_type=Provider):
            with pytest.raises(LLMProviderError):
                await Provider().generate(LLMRequest(task=LLMTask.INTENT_RECOGNITION), dict)
        assert Provider.generate is original
        assert failures == {"owned-request": [{"task": "intent_recognition", "category": "connection"}]}
        audit = {"member_grounding_status": [{"status": "UNRESOLVED", "method": "bounded_member_llm_abstained"}]}
        assert negative_outcome_verified(audit, [], "unknown")
        assert not negative_outcome_verified(audit, failures["owned-request"], "unknown")
        assert not negative_outcome_verified({}, [], "unknown")
    finally:
        ACCEPTANCE_REQUEST.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("task_name,repaired", [("intent_recognition", True), ("semantic_selection", False)])
async def test_format_repair_success_is_distinguished_from_unrecovered_selector_failure(task_name, repaired):
    from scripts.manual_smoke.cross_language_real_acceptance import ACCEPTANCE_REQUEST, observe_provider_failures, negative_outcome_verified
    from backend.app.llm.base import LLMProviderError, LLMErrorCategory, LLMRequest, LLMTask, LLMResponse

    class Provider:
        calls = 0
        async def generate(self, request, output_type):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError("private payload", error_category=LLMErrorCategory.RESPONSE_VALIDATION)
            return LLMResponse(content="{}")

    failures = {}
    token = ACCEPTANCE_REQUEST.set("owned-request")
    try:
        with observe_provider_failures(failures, provider_type=Provider):
            provider = Provider()
            request = LLMRequest(task=LLMTask(task_name))
            with pytest.raises(LLMProviderError):
                await provider.generate(request, dict)
            await provider.generate(request, dict)
        assert failures["owned-request"][0].get("repaired", False) is repaired
        audit = {"member_grounding_status": [{"status": "UNRESOLVED", "method": "bounded_member_llm_abstained"}]}
        assert negative_outcome_verified(audit, failures["owned-request"], "unknown") is repaired
    finally:
        ACCEPTANCE_REQUEST.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_pending", [False, True])
async def test_real_http_failure_drains_owned_turn_before_resource_cleanup(tmp_path, cancel_pending):
    from types import SimpleNamespace
    from scripts.manual_smoke.cross_language_real_acceptance import tracked_acceptance_turns

    started, release = asyncio.Event(), asyncio.Event()
    conversations, reports, finished = [], [], []

    async def execute(**kwargs):
        started.set()
        try:
            await release.wait()
            return {"report": {"report_id": "owned-report"}}
        finally:
            finished.append(True)

    service = SimpleNamespace(execute=execute)
    owner = SimpleNamespace(add_conversation=conversations.append,
        add_report=lambda identity, **kwargs: reports.append(identity))
    with pytest.raises(RuntimeError, match="observer_disconnected"):
        async with tracked_acceptance_turns(service, owner, tmp_path,
                drain_seconds=0 if cancel_pending else 1):
            task = asyncio.create_task(service.execute(conversation_id="owned-conversation"))
            await started.wait()
            if not cancel_pending:
                release.set()
            raise RuntimeError("observer_disconnected")
    # Resource teardown may now run: no turn can resurrect a deleted resource.
    assert task.done() and finished == [True]
    assert conversations == ["owned-conversation"]
    assert reports == ([] if cancel_pending else ["owned-report"])
    assert task.cancelled() == cancel_pending
    assert service.execute is execute


@pytest.fixture
def acceptance_parent(tmp_path):
    # The outer fixture owns simulated-denial leftovers and removes them after
    # assertions; tests never require user/manual cleanup.
    with tempfile.TemporaryDirectory(prefix="cleanup-test-", dir=tmp_path) as parent:
        yield Path(parent)
    assert not Path(parent).exists()


@pytest.mark.parametrize("prefix", ["powerbiagent-context-real-", "powerbiagent-m583-validation-",
    "powerbiagent-context-audit-", "powerbiagent-semantic-comparison-"])
def test_pass_removes_owned_tempdir(acceptance_parent, capsys, prefix):
    with owned_acceptance_tempdir(prefix=prefix, parent=acceptance_parent) as root:
        marker = json.loads((root / MARKER).read_text())
        assert marker["project"] == "PowerBIAgent" and marker["milestone"] == "M5.8.3"
        assert marker["path"] == str(root)
        (root / "nested").mkdir()
        (root / "nested" / "artifact.txt").write_text("owned")
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["temporary_residual"] == 0


def test_validation_exception_still_cleans(acceptance_parent, capsys):
    with pytest.raises(RuntimeError, match="validation"):
        with owned_acceptance_tempdir(prefix="powerbiagent-context-real-", parent=acceptance_parent) as root:
            (root / "validation.txt").write_text("owned")
            raise RuntimeError("validation")
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["temporary_residual"] == 0


def test_stale_mutation_override_failure_cleans(acceptance_parent, capsys):
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    from backend.app.query_plan.semantic_catalog import GlossaryCatalogError, SemanticCatalogBuilder
    from backend.tests.fixtures.semantic_context_domains import domains

    schema = domains()[0].schema
    context = ModelSemanticContextBuilder().build(schema)
    stale = {"version":2, "semantic_model_key":context.semantic_model_key,
        "runtime_identity":context.runtime_identity, "schema_fingerprint":context.schema_fingerprint, "objects":{}}
    with pytest.raises(GlossaryCatalogError, match="override_schema_fingerprint_mismatch"):
        with owned_acceptance_tempdir(prefix="powerbiagent-m583-validation-", parent=acceptance_parent) as root:
            (root / "mutation.json").write_text(json.dumps(stale))
            schema.tables[0].measures[0].name = "RenamedRuntimeMeasure"
            SemanticCatalogBuilder().build_from_context(ModelSemanticContextBuilder().build(schema), stale)
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["temporary_residual"] == 0


@pytest.mark.asyncio
async def test_real_entrypoint_cleans_after_a_b_a_middle_failure(acceptance_parent, monkeypatch, capsys):
    from scripts.manual_smoke import semantic_context_real_acceptance as entry

    roots, visited = [], []

    async def interrupted_switch(args, root):
        roots.append(root)
        for model in ("A", "B", "A"):
            visited.append(model)
            (root / "switch.txt").write_text(model)
            if model == "B":
                raise RuntimeError("switch_validation_failed")

    monkeypatch.setattr(entry, "run", interrupted_switch)
    monkeypatch.setattr(entry, "owned_acceptance_tempdir", lambda **kwargs: owned_acceptance_tempdir(parent=acceptance_parent, **kwargs))
    monkeypatch.setattr(entry.sys, "argv", ["acceptance", "--rich-model", "A", "--other-model", "B", "--phase", "members"])
    with pytest.raises(SystemExit) as error:
        await entry.main()
    assert error.value.code == 1 and visited == ["A", "B"]
    assert not roots[0].exists()
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert reports[-1]["temporary_residual"] == 0


@pytest.mark.asyncio
async def test_task_cancellation_cleans_before_propagating(acceptance_parent, capsys):
    ready = asyncio.Event()
    roots = []

    async def run():
        with owned_acceptance_tempdir(prefix="powerbiagent-context-real-", parent=acceptance_parent) as root:
            roots.append(root)
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(run())
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not roots[0].exists()
    assert json.loads(capsys.readouterr().out)["temporary_residual"] == 0


@pytest.mark.parametrize("body_fails", [False, True])
def test_cleanup_denied_warns_without_hiding_failure_or_touching_neighbor(acceptance_parent, monkeypatch, capsys, body_fails):
    import scripts.acceptance_tempdir as helper

    neighbor = acceptance_parent / "powerbiagent-context-real-neighbor"
    neighbor.mkdir()
    (neighbor / "user.txt").write_text("keep")
    targets = []

    def denied(path):
        targets.append(Path(path))
        raise PermissionError("simulated executor policy refusal")

    monkeypatch.setattr(helper, "_delete_owned_tree", denied)
    try:
        with owned_acceptance_tempdir(prefix="powerbiagent-context-real-", parent=acceptance_parent) as root:
            if body_fails:
                raise ValueError("original failure")
    except ValueError as error:
        assert body_fails and str(error) == "original failure"
    else:
        assert not body_fails
    output = capsys.readouterr()
    warning = json.loads(output.err)
    assert warning["cleanup_warning"] == "PermissionError"
    assert warning["path"] == str(root)
    assert warning["temporary_residual"] == 1
    assert json.loads(output.out)["temporary_residual"] == 1
    assert targets == [root] and root.exists()
    assert (neighbor / "user.txt").read_text() == "keep"


@pytest.mark.parametrize("mismatch", ["marker_token", "marker_path", "marker_missing"])
def test_ownership_mismatch_never_deletes(acceptance_parent, monkeypatch, capsys, mismatch):
    import scripts.acceptance_tempdir as helper

    monkeypatch.setattr(helper, "_delete_owned_tree", lambda path: pytest.fail("must not delete unproven ownership"))
    with owned_acceptance_tempdir(prefix="powerbiagent-context-real-", parent=acceptance_parent) as root:
        marker_path = root / MARKER
        if mismatch == "marker_missing":
            marker_path.unlink()
        else:
            marker = json.loads(marker_path.read_text())
            marker["run_id" if mismatch == "marker_token" else "path"] = "foreign"
            marker_path.write_text(json.dumps(marker))
    assert root.exists()
    output = capsys.readouterr()
    assert json.loads(output.err)["cleanup_warning"] == "ownership_mismatch"
    assert json.loads(output.out)["temporary_residual"] == 1


def test_arbitrary_prefix_is_rejected_before_directory_creation(acceptance_parent):
    with pytest.raises(ValueError, match="acceptance_prefix_not_allowed"):
        with owned_acceptance_tempdir(prefix="other-project-", parent=acceptance_parent):
            pytest.fail("must reject first")
    assert not list(acceptance_parent.iterdir())


def test_uninspectable_root_never_reports_absent(acceptance_parent, monkeypatch, capsys):
    original_lstat = Path.lstat
    with monkeypatch.context() as patch:
        with owned_acceptance_tempdir(prefix="powerbiagent-context-real-", parent=acceptance_parent) as root:
            def denied(path, *args, **kwargs):
                if path == root:
                    raise PermissionError("cannot inspect owned directory")
                return original_lstat(path, *args, **kwargs)
            patch.setattr(Path, "lstat", denied)
    output = capsys.readouterr()
    assert root.exists()
    assert json.loads(output.err)["cleanup_warning"] == "PermissionError"
    assert json.loads(output.out)["temporary_residual"] == 1
