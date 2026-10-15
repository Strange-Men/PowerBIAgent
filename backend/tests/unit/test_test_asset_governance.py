"""A truthful manual-cleanup disposition must not masquerade as clean governance."""
from scripts.check_test_asset_governance import validate

import json
import sys
import pytest
from scripts import run_local_validation


def receipt():
    return dict(status='PASS',sha_mismatch=0,active_old_path_reference=0,unclassified_db=0,
        unmigrated_known_synthetic_files=0,repository_touched=False,old_test_directories=0)


def test_false_clean_receipt_rejects_residual_old_directory_and_hash_difference():
    value=receipt()
    value.update(old_test_directories=1,sha_mismatch=1)
    assert set(validate(value)) == {'sha_mismatch','old_test_directories'}


def test_manual_delete_requires_explicit_paths_and_keeps_safety_requirements():
    value=receipt()
    value.update(status='MANUAL_DELETE_REQUIRED',old_test_directories=1)
    assert validate(value) == ['manual_delete_paths']
    value['manual_delete_paths']=['owned-test-copy']
    assert validate(value) == []
    value['active_old_path_reference']=1
    assert validate(value) == ['active_old_path_reference']


def test_manual_delete_complete_rejects_repository_residuals_and_pending_paths():
    value=receipt()
    value.update(status='MANUAL_DELETE_COMPLETE',repository_transient_directories=0,manual_delete_paths=[])
    assert validate(value) == []
    value.update(repository_transient_directories=1,manual_delete_paths=['remaining-copy'])
    assert set(validate(value)) == {'repository_transient_directories','manual_delete_paths'}


def test_local_runner_rejects_repository_test_root(monkeypatch):
    monkeypatch.setenv('PBIAGENT_TEST_ROOT', str(run_local_validation.REPO / 'PBIAgentTest'))
    monkeypatch.setattr(sys,'argv',['runner','--milestone','M6.4.1','--',sys.executable,'-c','pass'])
    with pytest.raises(SystemExit) as failure:
        run_local_validation.main()
    assert failure.value.code == 2


def test_local_runner_quotes_space_path_and_cleans_owned_temp_on_failure(monkeypatch,tmp_path):
    root=tmp_path/'path with spaces'/'PBIAgentTest'
    monkeypatch.setenv('PBIAGENT_TEST_ROOT',str(root))
    command=('import os,shlex,pathlib; '
             'parts=shlex.split(os.environ["PYTEST_ADDOPTS"]); '
             'base=next(p.split("=",1)[1] for p in parts if p.startswith("--basetemp=")); '
             'assert pathlib.Path(base).parent==pathlib.Path(os.environ["TEMP"]); '
             'assert pathlib.Path(base).is_relative_to(pathlib.Path(os.environ["PBIAGENT_TEST_ROOT"])); '
             'raise SystemExit(7)')
    monkeypatch.setattr(sys,'argv',['runner','--milestone','M6.4.1','--',sys.executable,'-c',command])
    assert run_local_validation.main() == 7
    receipts=list((root/'M6.4.1/Acceptance').glob('*/receipt.json'))
    assert len(receipts)==1
    value=json.loads(receipts[0].read_text(encoding='utf-8'))
    assert value['temp_cleanup'] is True and value['exit_code']==7
    assert not list((root/'M6.4.1/Cache').glob('*/T-*'))


def test_frontend_validation_routes_typescript_cache_and_avoids_vite_temp(tmp_path):
    commands = run_local_validation.frontend_commands(['npm', 'run', 'build'], tmp_path)
    assert len(commands) == 3
    for command in commands[:2]:
        assert command[-2] == '--tsBuildInfoFile'
        assert command[-1].startswith(str(tmp_path))
    assert commands[-1][-2:] == ['--configLoader', 'runner']
    assert run_local_validation.frontend_commands(['npm', 'test'], tmp_path)[0][-2:] == ['--configLoader', 'runner']
