"""Deployment readiness and explicit migration use synthetic databases only."""
import sqlite3
from contextlib import closing
from unittest.mock import Mock, AsyncMock

import pytest
from alembic import command
from fastapi.testclient import TestClient

from backend.tests.api.test_auth_security import config, FakeIdentity, login, ORIGIN
from backend.tests.unit.persistence.test_m63_migration import config as migration_config
from backend.app.main import create_app


def settings(tmp_path, **changes):
    return config(powerbi_mode='fabric_iq', allow_business_persistence=True,
        persistence_backend='sqlite', persistence_database_path=str(tmp_path/'custom.db'),
        report_artifacts_path=str(tmp_path/'reports'), **changes)


@pytest.mark.parametrize('revision', ['c2e4f6a8b130', None, 'empty', 'head'])
def test_native_startup_reports_readiness_without_migrating(tmp_path, revision):
    s = settings(tmp_path)
    if revision == 'empty':
        (tmp_path/'custom.db').touch()
    elif revision:
        command.upgrade(migration_config(tmp_path/'custom.db'), revision)
    before = (tmp_path/'custom.db').read_bytes() if revision else None
    with TestClient(create_app(s, identity_client=FakeIdentity()), base_url=ORIGIN) as client:
        health = client.get('/health').json()
        assert health['persistence_ready'] is (revision == 'head')
        assert health['configuration_ready'] is True
        login(client)
        status = client.get('/api/v1/cloud/status').json()
        assert status['persistence_ready'] is (revision == 'head')
        # Selection is a control-plane operation, not a storage repair. Its
        # response must retain the startup gate rather than enabling the UI.
        from backend.app.application.cloud_workspace_service import CloudWorkspaceStatus
        selected = CloudWorkspaceStatus(selected_model_key='synthetic', conversation_id='synthetic',
            generation=1, execution_ready=True, blockers=())
        client.app.state.cloud_workspace_service.select_with_templates = AsyncMock(return_value=selected)
        csrf = client.get('/auth/session').json()['csrf_token']
        selected_response = client.post('/api/v1/cloud/selection',
            headers={'Origin':ORIGIN, 'X-CSRF-Token':csrf},
            json={'key':'synthetic','expected_generation':0})
        assert selected_response.json()['persistence_ready'] is (revision == 'head')
        if revision != 'head':
            assert status['persistence_reason'] == 'PERSISTENCE_SCHEMA_OUTDATED'
            assert status['expected_revision'] == 'ab64d10e7f20'
            assert status['current_revision'] == (None if revision == 'empty' else revision)
            spy = Mock(side_effect=AssertionError('no business execution'))
            client.app.state.cloud_product_services.chat = spy
            csrf = client.get('/auth/session').json()['csrf_token']
            response = client.post('/api/v1/cloud/chat', headers={'Origin':ORIGIN, 'X-CSRF-Token':csrf},
                json={'message':'What is the total sales?', 'request_id':'synthetic', 'expected_generation':0})
            assert response.status_code == 503
            assert response.json()['detail']['failure']['code'] == 'PERSISTENCE_SCHEMA_OUTDATED'
            spy.assert_not_called()
            for route in ('history', 'reports'):
                assert client.get('/api/v1/cloud/'+route).json()['detail']['failure']['code'] == 'PERSISTENCE_SCHEMA_OUTDATED'
    if before is None:
        assert not (tmp_path/'custom.db').exists()
    else:
        assert (tmp_path/'custom.db').read_bytes() == before


def test_explicit_helper_migrates_exact_settings_path(tmp_path, monkeypatch):
    from scripts.prepare_persistence import prepare
    default = tmp_path/'local_state/persistence/powerbiagent.db'
    default.parent.mkdir(parents=True)
    default.write_bytes(b'untouched sentinel')
    monkeypatch.chdir(tmp_path)
    s = settings(tmp_path)
    result = prepare(s, upgrade=True)
    assert result.ready
    assert result.current_revision == result.expected_revision == 'ab64d10e7f20'
    assert default.read_bytes() == b'untouched sentinel'


def test_helper_preserves_legacy_rows_and_enables_owner_binding_tables(tmp_path):
    from scripts.prepare_persistence import prepare
    s = settings(tmp_path)
    command.upgrade(migration_config(tmp_path/'custom.db'), 'c2e4f6a8b130')
    with closing(sqlite3.connect(s.persistence_database_path)) as conn:
        conn.execute("INSERT INTO conversations(conversation_id,runtime_mode,title) VALUES ('legacy','real','synthetic')")
        conn.execute("INSERT INTO work_memories(request_id,conversation_id,runtime_mode,state_status,base_memory_version,memory_version,payload_json) VALUES ('r','legacy','real','pending',0,0,'{}')")
        conn.execute("INSERT INTO result_snapshots(request_id,conversation_id,runtime_mode,request_fingerprint_hash,terminal_state,response_type,payload_json) VALUES ('r','legacy','real','synthetic','completed','answer','{}')")
        conn.execute("INSERT INTO report_artifacts(report_id,conversation_id,request_id,template_key,semantic_model_key,schema_fingerprint,source_mode,content_hash,relative_path,payload_json) VALUES ('rpt_synthetic','legacy','r','synthetic','synthetic','synthetic','real','synthetic','synthetic.html','{}')")
        conn.commit()
        tables = ('conversations','work_memories','result_snapshots','report_artifacts')
        before = {t:conn.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
    assert prepare(s, upgrade=True).ready
    with closing(sqlite3.connect(s.persistence_database_path)) as conn:
        for table in tables:
            assert [row[:-1] for row in conn.execute(f'SELECT * FROM {table}')] == before[table]
        conn.execute("INSERT INTO cloud_conversation_bindings VALUES ('local:legacy','legacy','synthetic','synthetic','synthetic','synthetic','real')")
        assert conn.execute('SELECT count(*) FROM resource_owners').fetchone() == (1,)
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


def test_helper_cli_uses_environment_custom_path(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from backend.app.persistence.readiness import REPOSITORY
    custom = tmp_path/'custom path %25.db'
    default = tmp_path/'local_state/persistence/powerbiagent.db'
    default.parent.mkdir(parents=True)
    default.write_bytes(b'untouched')
    result = subprocess.run([sys.executable, str(REPOSITORY/'scripts/prepare_persistence.py'), '--upgrade'],
        cwd=tmp_path, env=os.environ | {'PERSISTENCE_BACKEND':'sqlite',
            'PERSISTENCE_DATABASE_PATH':str(custom), 'REPORT_ARTIFACTS_PATH':str(tmp_path/'reports')},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    with closing(sqlite3.connect(custom)) as conn:
        assert conn.execute('SELECT version_num FROM alembic_version').fetchone() == ('ab64d10e7f20',)
    assert default.read_bytes() == b'untouched'


def test_head_stamp_with_missing_tables_is_not_ready(tmp_path):
    from backend.app.persistence.readiness import check_persistence
    s = settings(tmp_path)
    with closing(sqlite3.connect(s.persistence_database_path)) as conn:
        conn.execute('CREATE TABLE alembic_version (version_num TEXT)')
        conn.execute("INSERT INTO alembic_version VALUES ('ab64d10e7f20')")
        conn.commit()
    assert check_persistence(s).reason == 'PERSISTENCE_SCHEMA_OUTDATED'


def test_artifact_root_must_be_writable(tmp_path):
    from backend.app.persistence.readiness import check_persistence
    s = settings(tmp_path)
    command.upgrade(migration_config(tmp_path/'custom.db'), 'head')
    (tmp_path/'reports').write_text('not a directory')
    result = check_persistence(s)
    assert not result.ready and result.reason == 'PERSISTENCE_UNAVAILABLE'
