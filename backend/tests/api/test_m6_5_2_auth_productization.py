"""Single-login origin regression and payload-free auth diagnostics."""
import logging

from backend.tests.api.test_auth_security import harness, login, ORIGIN  # noqa: F401


def test_login_canonicalizes_origin_before_creating_a_flow(harness):
    client, app, _ = harness
    response = client.get('http://127.0.0.1:5173/auth/login', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['location'] == ORIGIN + '/auth/login'
    assert 'set-cookie' not in response.headers
    assert not app.state.auth_service.flows._records
    # The same user click follows the canonical redirect, then one callback.
    response = client.get(response.headers['location'], follow_redirects=False)
    assert response.headers['location'].startswith('https://login.microsoftonline.com/')
    client.get(ORIGIN + '/auth/callback?state=synthetic-state&code=synthetic-code', follow_redirects=False)
    assert client.get(ORIGIN + '/auth/session').status_code == 200
    assert len(app.state.auth_service.sessions._records) == 1
    assert not app.state.auth_service.flows._records


def test_first_login_emits_safe_structured_lifecycle(harness, caplog):
    client, _, _ = harness
    caplog.set_level(logging.INFO, logger='backend.app.auth.trace')
    login(client)
    assert client.get('/auth/session').status_code == 200
    events = [r.auth_event for r in caplog.records if hasattr(r, 'auth_event')]
    for event in ('flow_created', 'callback_received', 'flow_cookie_present', 'state_match',
                  'flow_consumed', 'session_created', 'session_cookie_emitted',
                  'redirect_complete', 'session_lookup_success'):
        assert event in events
    for forbidden in ('synthetic-state', 'synthetic-code', 'synthetic-verifier',
                      'a@example.invalid', 'Test A', client.cookies.get('pbiagent_session')):
        assert forbidden not in caplog.text


def test_missing_flow_is_distinguished_without_leaking_callback(harness, caplog):
    client, app, _ = harness
    caplog.set_level(logging.INFO, logger='backend.app.auth.trace')
    client.get('/auth/callback?state=PRIVATE_STATE_MARKER&code=PRIVATE_CODE_MARKER', follow_redirects=False)
    assert client.get('/auth/session').status_code == 401
    assert not app.state.auth_service.sessions._records
    events = [r for r in caplog.records if getattr(r, 'auth_event', None) == 'flow_cookie_present']
    assert len(events) == 1 and events[0].auth_success is False
    assert 'PRIVATE_' not in caplog.text
