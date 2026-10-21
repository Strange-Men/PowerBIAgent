"""Low-cardinality Auth lifecycle. Never accepts protocol or identity values."""
import logging

_EVENTS = frozenset({
    'flow_created', 'callback_received', 'flow_cookie_present', 'state_match',
    'flow_consumed', 'token_exchange_success', 'id_token_verified',
    'session_created', 'session_cookie_emitted', 'redirect_complete',
    'session_lookup_success', 'canonical_origin', 'account_resolved',
})


def auth_trace(event, success=True):
    if event not in _EVENTS or type(success) is not bool:
        raise ValueError('invalid_auth_trace')
    logging.getLogger(__name__).info('auth_trace event=%s success=%s', event, success,
        extra={'auth_event': event, 'auth_success': success})
