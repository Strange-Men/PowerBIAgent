"""Delegated, read-only Fabric REST catalog; no arbitrary URLs or data queries."""
import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx2

from backend.app.auth.identity import CATALOG_SCOPES, DELEGATED_SCOPES
from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import guid
from backend.app.powerbi.fabric_iq_transport import install_fabric_log_redaction
from backend.app.application.cloud_operation import cloud_stage

BASE = "https://api.fabric.microsoft.com/v1"


class FabricCatalogTransport:
    def __init__(self, auth, session_id, principal, *, http_transport=None,
                 timeout=20, max_pages=100, max_items=2000, sleep=asyncio.sleep):
        self._auth, self._sid, self._principal = auth, session_id, principal
        self._max_pages, self._max_items, self._sleep = max_pages, max_items, sleep
        self._closed = False
        self.inaccessible_count = 0
        self.test_scope_complete = True
        self._test_policy = CloudTestPolicy(auth.settings)
        self.validate()
        install_fabric_log_redaction()
        self._http = httpx2.AsyncClient(timeout=timeout, follow_redirects=False,
            trust_env=False, transport=http_transport)

    def validate(self):
        if self._closed: raise fail("UPSTREAM_UNAVAILABLE")
        if self._auth.require_session(self._sid).principal != self._principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    def assert_session_binding(self, auth, session_id, principal):
        self.validate()
        if self._auth is not auth or self._sid != session_id or self._principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    async def __aenter__(self):
        self.validate()
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        self._closed = True
        await self._http.aclose()

    async def list_workspaces(self):
        if self._test_policy.enabled:
            return await self._approved_items([
                '/workspaces/' + str(w.workspace_id) for w in self._test_policy.scope.workspaces])
        return await self._pages("/workspaces")

    async def list_models(self, workspace_id):
        self._test_policy.workspace(workspace_id)
        return await self._pages(f"/workspaces/{guid(workspace_id)}/semanticModels", recursive=True)

    async def list_reports(self, workspace_id):
        self._test_policy.workspace(workspace_id)
        return await self._pages(f"/workspaces/{guid(workspace_id)}/reports", recursive=True)

    async def catalog_page(self, path, continuation=None):
        """One current-principal metadata page, never an IQ/schema operation."""
        import re
        if (self._test_policy.enabled or not re.fullmatch(
                r'/workspaces(?:/[0-9a-f-]{36}/(?:semanticModels|reports))?', path)):
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        params = {} if path == '/workspaces' else {'recursive': 'true'}
        if continuation is not None:
            if not isinstance(continuation, str) or not 1 <= len(continuation) <= 8192:
                raise fail('CONTRACT_DRIFT')
            params['continuationToken'] = continuation
        body = await self._get(path, params)
        if (not isinstance(body, dict) or not isinstance(body.get('value'), list)
                or any(not isinstance(row, dict) for row in body['value'])
                or len(body['value']) > 5000 or body.get('error') or body.get('errors')):
            raise fail('CONTRACT_DRIFT')
        token, uri = body.get('continuationToken'), body.get('continuationUri')
        if token is None:
            if uri is not None: raise fail('CONTRACT_DRIFT')
        elif not isinstance(token, str) or not 1 <= len(token) <= 8192 or token == continuation:
            raise fail('CONTRACT_DRIFT')
        if uri is not None:
            try:
                parsed = urlsplit(uri)
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=3)
            except (ValueError, TypeError): raise fail('CONTRACT_DRIFT') from None
            if (parsed.scheme != 'https' or parsed.netloc != 'api.fabric.microsoft.com'
                    or parsed.path != '/v1' + path or parsed.fragment
                    or query.get('continuationToken') != [token]
                    or any(k not in {'continuationToken', 'recursive'} for k in query)
                    or ('recursive' in query and query['recursive'] != ['true'])):
                raise fail('CONTRACT_DRIFT')
        self.validate()
        return [{k: row[k] for k in ('id', 'displayName', 'workspaceId', 'type') if k in row}
                for row in body['value']], token

    @cloud_stage('resource_verify','microsoft_rest')
    async def verify_resource(self, workspace_id, item_id=None, kind=None):
        """Exact Microsoft GET; client identifiers are only untrusted selectors."""
        workspace_id = guid(workspace_id)
        path = '/workspaces/' + workspace_id
        if item_id is not None:
            if kind not in {'SemanticModel', 'Report'}: raise fail('RESOURCE_NOT_ACCESSIBLE')
            item_id = guid(item_id)
            path += ('/semanticModels/' if kind == 'SemanticModel' else '/reports/') + item_id
        body = await self._get(path, {})
        if (not isinstance(body, dict) or guid(body.get('id')) != (item_id or workspace_id)
                or (item_id is not None and (guid(body.get('workspaceId')) != workspace_id or body.get('type') != kind))):
            raise fail('CONTRACT_DRIFT')
        self.validate()
        return {k: body[k] for k in ('id', 'displayName', 'workspaceId', 'type') if k in body}

    async def _approved_items(self, paths):
        rows = []
        for path in paths:
            try: rows.append(await self._get(path, {}))
            except PowerBIAdapterError as error:
                if error.error_type != 'RESOURCE_NOT_ACCESSIBLE': raise
                self.validate()
                self.inaccessible_count += 1
                self.test_scope_complete = False
        return rows

    @cloud_stage('catalog_rest','microsoft_rest')
    async def _get(self, path, params):
        for attempt in range(3):
            self.validate()
            self._test_policy.rest_path(path)
            # Exact item GET requires Item.Read.All in either mode; workspace
            # enumeration requires Workspace.Read.All. Both are existing grants.
            scopes = DELEGATED_SCOPES if len(path.split('/')) == 5 else CATALOG_SCOPES
            token = await asyncio.to_thread(self._auth.get_delegated_token,
                self._sid, self._principal, scopes)
            self.validate()
            self._test_policy.rest_path(path)
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                raise AuthFailure("AUTH_EXPIRED")
            try:
                response = await self._http.get(BASE + path, params=params,
                    headers={"Authorization": "Bearer " + token})
            except httpx2.TimeoutException:
                raise fail("QUERY_TIMEOUT") from None
            except httpx2.HTTPError:
                raise fail("UPSTREAM_UNAVAILABLE") from None
            finally:
                token = None
            self.validate()
            status = response.status_code
            if status == 200:
                try: body = response.json()
                except (ValueError, UnicodeError): raise fail("CONTRACT_DRIFT") from None
                self._test_policy.rest_path(path)
                if self._test_policy.enabled and len(path.split('/')) in {3, 5}:
                    parts = path.split('/')
                    if (not isinstance(body, dict) or guid(body.get('id')) != parts[-1]
                            or body.get('error') or body.get('errors')
                            or (len(parts) == 5 and (guid(body.get('workspaceId')) != parts[2]
                                or body.get('type') != {'semanticModels':'SemanticModel','reports':'Report'}[parts[3]]))):
                        raise fail('CONTRACT_DRIFT')
                    # Project only approved resource display fields, not
                    # descriptions, sensitivity labels or unrelated metadata.
                    return {key:body[key] for key in ('id','displayName','workspaceId','type') if key in body}
                return body
            if status == 401:
                self._auth.logout(self._sid, None)
                raise AuthFailure("AUTH_EXPIRED")
            if status in {403, 404}: raise fail("RESOURCE_NOT_ACCESSIBLE")
            if status == 429:
                retry = response.headers.get("Retry-After", "1")
                if not retry.isascii() or not retry.isdecimal() or len(retry) > 2:
                    raise fail("RATE_LIMITED")
                delay = int(retry)
                if delay > 30 or attempt == 2: raise fail("RATE_LIMITED")
                await self._sleep(delay)
                self.validate()
                continue
            if status in {408, 504}: raise fail("QUERY_TIMEOUT")
            if 300 <= status < 400: raise fail("CONTRACT_DRIFT")
            raise fail("UPSTREAM_UNAVAILABLE")

    async def _pages(self, path, *, recursive=False):
        params = {"recursive": "true"} if recursive else {}
        rows, seen = [], set()
        for _ in range(self._max_pages):
            body = await self._get(path, params)
            if (not isinstance(body, dict) or not isinstance(body.get("value"), list)
                    or any(not isinstance(row, dict) for row in body["value"])
                    or any(body.get(key) for key in ("error", "errors"))):
                raise fail("CONTRACT_DRIFT")
            if self._test_policy.enabled:
                parts = path.split('/')
                expected_type = {'semanticModels': 'SemanticModel', 'reports': 'Report'}.get(parts[-1])
                if expected_type is None: raise fail('CONTRACT_DRIFT')
                projected = []
                for row in body['value']:
                    if guid(row.get('workspaceId')) != parts[2] or row.get('type') != expected_type:
                        raise fail('CONTRACT_DRIFT')
                    guid(row.get('id'))
                    projected.append({key: row[key] for key in ('id', 'displayName', 'workspaceId', 'type') if key in row})
                rows.extend(projected)
            else:
                rows.extend(body['value'])
            if len(rows) > self._max_items: raise fail("CONTRACT_DRIFT")
            token, uri = body.get("continuationToken"), body.get("continuationUri")
            if token is None:
                if uri is not None: raise fail("CONTRACT_DRIFT")
                self.validate()
                return rows
            if not isinstance(token, str) or not token or len(token) > 8192 or token in seen:
                raise fail("CONTRACT_DRIFT")
            seen.add(token)
            if uri is not None:
                if not isinstance(uri, str): raise fail("CONTRACT_DRIFT")
                try:
                    parsed = urlsplit(uri)
                    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=3)
                except ValueError: raise fail("CONTRACT_DRIFT") from None
                if (parsed.scheme != "https" or parsed.netloc != "api.fabric.microsoft.com"
                        or parsed.path != "/v1" + path or parsed.fragment
                        or query.get("continuationToken") != [token]
                        or any(k not in {"continuationToken", "recursive"} for k in query)
                        or ("recursive" in query and query["recursive"] != ["true"])):
                    raise fail("CONTRACT_DRIFT")
            params = dict(params, continuationToken=token)
        raise fail("CONTRACT_DRIFT")
