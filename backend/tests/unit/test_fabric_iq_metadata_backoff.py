"""Official MCP SDK on synthetic wire; only named read metadata may retry."""
import asyncio
import json

import httpx2
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.powerbi.base import PowerBIAdapterError
from backend.tests.unit.test_fabric_iq_transport import Peer,transport
from backend.app.powerbi.fabric_iq_transport import _retry_after_seconds


class RatePeer(Peer):
    def __init__(self,*,after='0',failures=1):
        super().__init__()
        self.after,self.failures=after,failures
        self.attempts=[]
        self.on_rate=None
        self.rated=asyncio.Event()

    async def handle(self,request):
        if request.method=='POST':
            frame=json.loads(request.content)
            if frame['method']=='tools/call':
                assert request.headers['Authorization']=='Bearer SYNTHETIC_DELEGATED_TOKEN'
                assert request.headers['X-Variants']=='Fabric.Routing.FabricIQ.V1'
                self.attempts.append(frame['params']['name'])
                if len(self.attempts)<=self.failures:
                    if self.on_rate: self.on_rate()
                    self.rated.set()
                    headers={} if self.after is None else {'Retry-After':self.after}
                    return httpx2.Response(429,headers=headers)
        return await super().handle(request)


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args',[
    ('GetSemanticModelSchema',{'artifactId':'synthetic'}),
    ('ResolveFabricItem',{'fabricItemId':'synthetic'}),
])
async def test_metadata_429_valid_retry_after_retries_once_with_same_sdk(name,args):
    peer=RatePeer()
    client,auth,record=transport(peer)
    async with client.connection() as connection:
        await connection.call(name,args)
    assert peer.attempts==[name,name] and peer.closed
    assert auth.require_session(record.session_id).principal==record.principal


@pytest.mark.asyncio
async def test_repeated_metadata_429_stops_after_one_retry_without_logout():
    peer=RatePeer(failures=10)
    client,auth,record=transport(peer)
    with pytest.raises(PowerBIAdapterError,match='^RATE_LIMITED$'):
        async with client.connection() as connection:
            await connection.call('GetSemanticModelSchema',{'artifactId':'synthetic'})
    assert peer.attempts==['GetSemanticModelSchema']*2
    assert auth.require_session(record.session_id).principal==record.principal


@pytest.mark.asyncio
@pytest.mark.parametrize('after',[None,'bad','-1','1e3','9999999999'])
async def test_invalid_missing_or_over_budget_hint_does_not_retry(after):
    peer=RatePeer(after=after)
    client,_,_=transport(peer)
    with pytest.raises(PowerBIAdapterError,match='^RATE_LIMITED$'):
        async with client.connection() as connection:
            await connection.call('GetSemanticModelSchema',{'artifactId':'synthetic'})
    assert peer.attempts==['GetSemanticModelSchema']


@pytest.mark.asyncio
async def test_execute_query_is_never_retried_even_with_zero_retry_after():
    peer=RatePeer()
    client,_,_=transport(peer)
    with pytest.raises(PowerBIAdapterError,match='^RATE_LIMITED$'):
        async with client.connection() as connection:
            await connection.call('ExecuteQuery',{'artifactId':'synthetic','daxQueries':['synthetic'],'maxRows':2})
    assert peer.attempts==['ExecuteQuery']


@pytest.mark.asyncio
async def test_logout_before_retry_prevents_second_wire_request():
    peer=RatePeer()
    client,auth,record=transport(peer)
    peer.on_rate=lambda:auth.logout(record.session_id,None)
    with pytest.raises(AuthFailure):
        async with client.connection() as connection:
            await connection.call('GetSemanticModelSchema',{'artifactId':'synthetic'})
    assert peer.attempts==['GetSemanticModelSchema']


@pytest.mark.asyncio
async def test_cancellation_during_backoff_never_retries():
    peer=RatePeer(after='1')
    client,_,_=transport(peer)
    async def request():
        async with client.connection() as connection:
            await connection.call('GetSemanticModelSchema',{'artifactId':'synthetic'})
    task=asyncio.create_task(request())
    await peer.rated.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert peer.attempts==['GetSemanticModelSchema']


def test_http_date_hint_and_ambiguous_header_are_bounded():
    from datetime import datetime,timedelta,timezone
    from email.utils import format_datetime
    future=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=20),usegmt=True)
    delay=_retry_after_seconds(httpx2.Headers({'Retry-After':future}))
    assert 18<=delay<=20
    assert _retry_after_seconds(httpx2.Headers([('Retry-After','0'),('Retry-After','10')])) is None


@pytest.mark.asyncio
async def test_retry_rechecks_exact_workspace_policy_before_wire():
    from uuid import UUID
    from backend.app.config.cloud_test_policy import CloudTestAllowlist,CloudTestPolicy
    from backend.tests.unit.test_fabric_iq_adapter import settings
    peer=RatePeer()
    client,_,_=transport(peer)
    config=settings(fabric_test_mode=True,fabric_test_allowlist=CloudTestAllowlist(
        workspaces=[{'workspace_id':UUID(int=11)}]))
    client._test_policy=CloudTestPolicy(config)
    peer.on_rate=lambda:setattr(config,'fabric_test_allowlist',None)
    with pytest.raises(PowerBIAdapterError):
        async with client.connection(resource=(str(UUID(int=11)),str(UUID(int=10)))) as connection:
            await connection.call('GetSemanticModelSchema',{'artifactId':str(UUID(int=10))})
    assert peer.attempts==['GetSemanticModelSchema']
