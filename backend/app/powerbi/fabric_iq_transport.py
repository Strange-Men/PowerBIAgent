"""Official SDK Streamable HTTP; Auth alone owns delegated acquisition."""
import asyncio
import logging
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_contract import (
    VARIANT, capability_fingerprint, fail, safe_capability_evidence, validate_endpoint,
)


class FabricLogRedaction(logging.Filter):
    def filter(self, record):
        record.msg = "Fabric IQ upstream event (sensitive details redacted)"
        record.args = ()
        record.exc_info = record.exc_text = record.stack_info = None
        return True


def install_fabric_log_redaction():
    # Exact emitters: logger filters do not propagate to child loggers.
    names = {"mcp.client.streamable_http", "mcp.client.session", "mcp.shared.session",
             "httpx2", "httpx", "httpcore2", "httpcore"}
    names.update(n for n in logging.Logger.manager.loggerDict
                 if n.startswith(("mcp.", "httpx2.", "httpcore2.", "httpcore.", "httpx.")))
    for name in names:
        logger = logging.getLogger(name)
        if not any(isinstance(f, FabricLogRedaction) for f in logger.filters):
            logger.addFilter(FabricLogRedaction())


def _known_exception(error):
    if isinstance(error, (AuthFailure, PowerBIAdapterError)): return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            known = _known_exception(child)
            if known: return known
    return None


def _retry_after_seconds(headers):
    values = headers.get_list('Retry-After')
    if len(values) != 1: return None
    value = values[0].strip()
    if not value.isascii() or len(value) > 80: return None
    if re.fullmatch('[0-9]{1,10}', value): return float(value)
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None: return None
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError): return None


class _MetadataBackoffTransport(httpx2.AsyncBaseTransport):
    """One bounded retry below the same MCP SDK, for named read metadata only."""
    def __init__(self, inner, before_retry, deadline):
        self._inner, self._before_retry, self._deadline = inner, before_retry, deadline

    async def handle_async_request(self, request):
        response = await self._inner.handle_async_request(request)
        if response.status_code != 429 or request.method != 'POST': return response
        try:
            frame = json.loads(request.content)
            eligible = (frame.get('method') == 'tools/call'
                and frame.get('params', {}).get('name') in {'ResolveFabricItem', 'GetSemanticModelSchema'})
        except (ValueError, TypeError, AttributeError): eligible = False
        delay = _retry_after_seconds(response.headers) if eligible else None
        if delay is None or delay >= self._deadline - asyncio.get_running_loop().time(): return response
        await response.aclose()
        await asyncio.sleep(delay)
        # Reacquire through native Auth/Transport and recheck exact policy;
        # the product mutation and ExecuteQuery are never replayed here.
        await self._before_retry(request)
        return await self._inner.handle_async_request(request)

    async def aclose(self):
        await self._inner.aclose()


class FabricIQTransport:
    def __init__(self, settings, auth, session_id, principal, *, http_transport=None):
        self._endpoint = validate_endpoint(settings.fabric_iq_endpoint)
        if settings.fabric_iq_variant != VARIANT: raise fail("CONTRACT_DRIFT")
        self._timeout = settings.fabric_iq_timeout_seconds
        self._auth, self._sid, self._principal = auth, session_id, principal
        self._http_transport = http_transport  # synthetic SDK-on-wire tests only
        self._closed = False
        self._test_policy = CloudTestPolicy(settings)
        self.capability_evidence = None
        self.wire_evidence = {"initialize": 0, "tools/list": 0, "tools/call": 0,
                              "selector_verified": True, "authorization_injected": True}
        install_fabric_log_redaction()

    def validate_principal(self):
        if self._closed: raise fail("UPSTREAM_UNAVAILABLE")
        if self._auth.require_session(self._sid).principal != self._principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    @asynccontextmanager
    async def connection(self, *, resource=None):
        self.validate_principal()
        if resource is not None: self._test_policy.model(*resource)
        upstream_error = None
        primary_error = None

        async def inject(request):
            nonlocal upstream_error
            try:
                # Validate actual outbound destination before obtaining any token.
                validate_endpoint(str(request.url))
                self.validate_principal()
                if request.method == 'POST':
                    import json
                    message = json.loads(request.content)
                    if message.get('method') == 'tools/call':
                        params = message.get('params', {})
                        self._test_policy.iq_call(params.get('name'), params.get('arguments', {}), resource=resource)
                token = await asyncio.to_thread(self._auth.get_delegated_token, self._sid, self._principal)
                if not isinstance(token, str) or not token.strip() or any(c.isspace() for c in token):
                    raise AuthFailure("AUTH_EXPIRED")
                request.headers["Authorization"] = "Bearer " + token
                request.headers["X-Variants"] = VARIANT
                token = None
                # Retain only method counts, never body/header values.
                if request.method == "POST":
                    import json
                    method = json.loads(request.content).get("method")
                    if method in self.wire_evidence: self.wire_evidence[method] += 1
            except (AuthFailure, PowerBIAdapterError) as error:
                upstream_error = upstream_error or error
                raise
            except Exception:
                upstream_error = upstream_error or fail("CONTRACT_DRIFT")
                raise upstream_error from None

        async def check_response(response):
            nonlocal upstream_error
            status = response.status_code
            if status >= 300 and status != 405:
                code = {401: "AUTH_EXPIRED", 403: "RESOURCE_NOT_ACCESSIBLE", 404: "RESOURCE_NOT_ACCESSIBLE",
                    408: "QUERY_TIMEOUT", 429: "RATE_LIMITED", 504: "QUERY_TIMEOUT"}.get(status, "UPSTREAM_UNAVAILABLE")
                upstream_error = upstream_error or (AuthFailure(code) if code == "AUTH_EXPIRED" else fail(code))
                if status == 401:
                    await asyncio.to_thread(self._auth.logout, self._sid, None)
                raise upstream_error

        try:
            # Owned by the caller task, including cancellation and all teardown.
            async with asyncio.timeout(self._timeout):
                retry_transport = _MetadataBackoffTransport(
                    self._http_transport or httpx2.AsyncHTTPTransport(trust_env=False), inject,
                    asyncio.get_running_loop().time() + self._timeout)
                async with httpx2.AsyncClient(timeout=self._timeout, follow_redirects=False, trust_env=False,
                    transport=retry_transport, event_hooks={"request": [inject], "response": [check_response]}) as http:
                    async with streamable_http_client(self._endpoint, http_client=http) as streams:
                        async with ClientSession(*streams, read_timeout_seconds=self._timeout) as session:
                            await session.initialize()
                            inventory, seen = [], set()
                            cursor = None
                            for _ in range(20):
                                from mcp.types import PaginatedRequestParams
                                listing = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
                                inventory.extend(t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listing.tools)
                                cursor = listing.next_cursor
                                if cursor is None: break
                                if cursor in seen: raise fail("CONTRACT_DRIFT")
                                seen.add(cursor)
                            else: raise fail("CONTRACT_DRIFT")
                            fingerprint = capability_fingerprint(inventory)
                            self.capability_evidence = safe_capability_evidence(fingerprint, self._endpoint)
                            self.validate_principal()
                            try:
                                yield FabricIQConnection(session, inventory, self.validate_principal, self._test_policy, resource=resource)
                            except BaseException as error:
                                primary_error = error
                                raise
                            self.validate_principal()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            known = _known_exception(primary_error) or upstream_error or _known_exception(error)
            if known: raise known from None
            if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
                raise fail("QUERY_TIMEOUT") from None
            raise fail("UPSTREAM_UNAVAILABLE") from None

    async def aclose(self):
        self._closed = True


class FabricIQConnection:
    def __init__(self, session, inventory, validate, test_policy=None, *, resource=None):
        self._session, self._validate = session, validate
        self._test_policy = test_policy
        self._resource = resource
        self._inventory = {t["name"]: t for t in inventory}

    def validate_report_metadata_capability(self):
        from backend.app.powerbi.fabric_iq_contract import validate_report_metadata_capability
        validate_report_metadata_capability(self._inventory.get('GetReportMetadata'))

    async def call(self, name, arguments):
        self._validate()
        if self._test_policy is not None: self._test_policy.iq_call(name, arguments, resource=self._resource)
        props = self._inventory[name]["inputSchema"]["properties"]
        # Runtime restrictions are authoritative; never silently clamp maxRows.
        for key, value in arguments.items():
            spec = props.get(key, {})
            if isinstance(value, int):
                if value < spec.get("minimum", value) or value > spec.get("maximum", value):
                    raise fail("QUERY_REJECTED")
            if isinstance(value, list):
                if len(value) < spec.get("minItems", 0) or len(value) > spec.get("maxItems", len(value)):
                    raise fail("CONTRACT_DRIFT")
        result = await self._session.call_tool(name, arguments)
        self._validate()
        if self._test_policy is not None: self._test_policy.iq_call(name, arguments, resource=self._resource)
        return result
