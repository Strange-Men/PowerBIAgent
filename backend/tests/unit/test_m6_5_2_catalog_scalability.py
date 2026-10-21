"""Large control-plane catalogs have zero IQ work before explicit selection."""
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.tests.unit.test_fabric_iq_adapter import harness  # noqa: F401


def rows(count, kind='SemanticModel'):
    return [{'id': str(UUID(int=100+i)), 'workspaceId': str(UUID(int=11)),
             'type': kind, 'displayName': f'Resource {i:04}'} for i in range(count)]


class REST:
    def __init__(self): self.calls = []
    async def catalog_page(self, path, continuation=None):
        self.calls.append((path, continuation))
        if path == '/workspaces':
            return [{'id': str(UUID(int=11)), 'displayName': 'Workspace'}], None
        return rows(1500, 'Report' if path.endswith('/reports') else 'SemanticModel'), None


@pytest.mark.asyncio
async def test_1500_metadata_first_page_bounded_search_pagination_zero_iq(harness):
    from backend.app.application.cloud_catalog_pages import CurrentPrincipalCatalog
    auth, session, transport, _ = harness
    pager, rest = CurrentPrincipalCatalog(), REST()
    first = await pager.workspaces(rest)
    workspace = first.items[0].key
    page = await pager.resources(rest, workspace, kind='SemanticModel')
    assert len(page.items) == 50 and page.next_cursor and page.partial
    seen = {item.key for item in page.items}
    assert len(rest.calls) == 2
    for _ in range(29):
        page = await pager.resources(rest, workspace, kind='SemanticModel', cursor=page.next_cursor)
        assert len(page.items) == 50
        assert not seen.intersection(item.key for item in page.items)
        seen.update(item.key for item in page.items)
    assert not page.next_cursor and len(seen) == 1500
    assert len(rest.calls) == 2  # Buffered Microsoft page, no extra fanout.
    search = await pager.resources(rest, workspace, kind='SemanticModel', query='1499')
    assert [item.display_name for item in search.items] == ['Resource 1499']
    assert transport.calls == []  # Schema = 0, IQ Resolve/Execute = 0.


@pytest.mark.asyncio
async def test_cursor_and_candidates_are_scoped_to_one_session_and_search(harness):
    from backend.app.application.cloud_catalog_pages import CurrentPrincipalCatalog
    from backend.app.auth.models import AuthFailure
    a, b, rest = CurrentPrincipalCatalog(), CurrentPrincipalCatalog(), REST()
    workspace = (await a.workspaces(rest)).items[0].key
    page = await a.resources(rest, workspace, kind='Report')
    for pager, ws, query in ((b, workspace, ''), (a, workspace, 'different')):
        with pytest.raises(AuthFailure):
            await pager.resources(rest, ws, kind='Report', query=query, cursor=page.next_cursor)
    with pytest.raises(AuthFailure): b.candidate(page.items[0].key)
    with pytest.raises(AuthFailure): a.candidate(str(UUID(int=100)))


@pytest.mark.asyncio
async def test_search_scanning_has_bounded_network_work_and_can_continue():
    from backend.app.application.cloud_catalog_pages import CurrentPrincipalCatalog
    class ManyPages(REST):
        async def catalog_page(self, path, continuation=None):
            if path == '/workspaces': return await super().catalog_page(path, continuation)
            self.calls.append((path, continuation))
            n = int(continuation or '0')
            return rows(1), str(n+1) if n < 100 else None
    pager, rest = CurrentPrincipalCatalog(), ManyPages()
    workspace = (await pager.workspaces(rest)).items[0].key
    page = await pager.resources(rest, workspace, kind='SemanticModel', query='absent')
    assert page.items == [] and page.partial and page.next_cursor
    assert len(rest.calls) <= 3


@pytest.mark.asyncio
async def test_cancelled_metadata_is_not_published():
    import asyncio
    from backend.app.application.cloud_catalog_pages import CurrentPrincipalCatalog
    started = asyncio.Event()
    class Delayed(REST):
        async def catalog_page(self, *args, **kwargs):
            started.set()
            await asyncio.Event().wait()
    pager = CurrentPrincipalCatalog()
    task = asyncio.create_task(pager.workspaces(Delayed()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not pager._workspaces and not pager._candidates
