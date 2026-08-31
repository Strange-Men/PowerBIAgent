"""Acceptance-only filesystem cleanup must be safe and truthful."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from scripts.acceptance_tempdir import MARKER, owned_acceptance_tempdir


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
