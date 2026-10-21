"""Bounded session-local metadata paging; candidates confer no query authority."""
from dataclasses import dataclass
from secrets import token_urlsafe
from time import monotonic
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.application.cloud_catalog_service import _display, _unique
from backend.app.auth.models import AuthFailure
from backend.app.powerbi.fabric_iq_contract import fail


class CatalogEntry(BaseModel):
    key: str
    display_name: str
    kind: Literal['Workspace', 'SemanticModel', 'Report']
    model_config = ConfigDict(extra='forbid', frozen=True)


class CatalogPage(BaseModel):
    items: list[CatalogEntry]
    next_cursor: str | None = None
    partial: bool = False
    coverage: Literal['workspace_membership_only'] = 'workspace_membership_only'
    model_config = ConfigDict(extra='forbid', frozen=True)


@dataclass(frozen=True)
class CatalogCandidate:
    workspace_id: str
    item_id: str
    kind: str
    display_name: str
    expires_at: float


@dataclass(frozen=True)
class _PageState:
    scope: tuple
    remaining: tuple
    continuation: str | None
    seen: frozenset
    expires_at: float


class CurrentPrincipalCatalog:
    """Owned by one validated session context; no global/distributed cache.

    At most two Microsoft page requests per operation, 50 visible rows, four
    continuations and 2,000 expiring candidate keys. Microsoft controls upstream
    page size; reject malformed/oversized pages rather than truncate silently.
    """
    def __init__(self):
        self._workspaces, self._candidates, self._cursors = {}, {}, {}

    def _prune(self):
        now = monotonic()
        self._workspaces = {k: v for k, v in self._workspaces.items() if v.expires_at > now}
        self._candidates = {k: v for k, v in self._candidates.items() if v.expires_at > now}
        self._cursors = {k: v for k, v in self._cursors.items() if v.expires_at > now}

    def workspace(self, key):
        self._prune()
        value = self._workspaces.get(key)
        if value is None: raise AuthFailure('AUTH_FORBIDDEN', 403)
        return value.workspace_id

    def candidate(self, key):
        self._prune()
        value = self._candidates.get(key)
        if value is None: raise AuthFailure('AUTH_FORBIDDEN', 403)
        return value

    def resource_selector(self,workspace_id,item_id,kind):
        """Parsed selector only; selection still requires Microsoft proof."""
        self._prune()
        if len(self._candidates)>=2000: raise fail('UPSTREAM_UNAVAILABLE')
        key=token_urlsafe(32)
        self._candidates[key]=CatalogCandidate(workspace_id,item_id,kind,'',monotonic()+300)
        return key

    async def workspaces(self, rest, *, query='', cursor=None):
        return await self._page(rest, '/workspaces', 'Workspace', None, query, cursor)

    async def resources(self, rest, workspace, *, kind, query='', cursor=None):
        if kind not in {'SemanticModel', 'Report'}: raise AuthFailure('AUTH_FORBIDDEN', 403)
        workspace_id = self.workspace(workspace)
        collection = 'semanticModels' if kind == 'SemanticModel' else 'reports'
        return await self._page(rest, f'/workspaces/{workspace_id}/{collection}', kind,
                                workspace_id, query, cursor)

    async def _page(self, rest, path, kind, workspace_id, query, cursor):
        self._prune()
        if not isinstance(query, str) or len(query) > 100: raise AuthFailure('AUTH_FORBIDDEN', 403)
        scope = path, kind, query.casefold().strip()
        state = self._cursors.get(cursor) if cursor else None
        if cursor and (state is None or state.scope != scope): raise AuthFailure('AUTH_FORBIDDEN', 403)
        remaining, continuation, seen = (list(state.remaining), state.continuation, set(state.seen)) if state else ([], None, set())
        output, requests = [], 0
        first = state is None
        while len(output) < 50:
            if not remaining:
                if not first and continuation is None: break
                if requests == 2: break
                rows, next_token = await rest.catalog_page(path, continuation)
                requests += 1
                first = False
                if len(rows) > 5000: raise fail('CONTRACT_DRIFT')
                if next_token is not None:
                    if next_token in seen: raise fail('CONTRACT_DRIFT')
                    seen.add(next_token)
                if len(seen) > 100: raise fail('CONTRACT_DRIFT')
                unique = _unique(rows, workspace_id=workspace_id,
                                 item_type=kind if workspace_id else None)
                remaining = [row for row in unique.values() if scope[2] in _display(row['displayName']).casefold()]
                continuation = next_token
            needed = 50 - len(output)
            output.extend(remaining[:needed])
            remaining = remaining[needed:]
        # Publish only after all awaited metadata succeeds; cancellation/late
        # session validation is handled by the enclosing Workspace Service.
        items, expires = [], monotonic() + 300
        target = self._workspaces if kind == 'Workspace' else self._candidates
        for row in output:
            key = token_urlsafe(32)
            ws = row['id'] if kind == 'Workspace' else workspace_id
            target[key] = CatalogCandidate(ws, row['id'], kind, _display(row['displayName']), expires)
            items.append(CatalogEntry(key=key, display_name=_display(row['displayName']), kind=kind))
        while len(target) > 2000: target.pop(next(iter(target)))
        next_cursor = None
        if remaining or continuation is not None:
            next_cursor = token_urlsafe(32)
            self._cursors[next_cursor] = _PageState(scope, tuple(remaining), continuation, frozenset(seen), expires)
        if cursor: self._cursors.pop(cursor, None)
        while len(self._cursors) > 4: self._cursors.pop(next(iter(self._cursors)))
        return CatalogPage(items=items, next_cursor=next_cursor, partial=next_cursor is not None)
