"""Ordered, bounded relay and durable failure recovery. No remote storage calls."""
from contextlib import contextmanager
from copy import deepcopy
import threading
from time import perf_counter
import uuid
import anyio
import pytest
from starlette.requests import ClientDisconnect
from product_upload_relay import transfer, lease, RelayBusy, GLOBAL_LOCK, MAX_RELAYS
from product_upload_intake import Intakes, CHUNK
from tests.test_product_upload_intake import env, database, psd, digest


class Request:
    def __init__(self, data, boundary=None, disconnect=False):
        self.data=data;self.headers={'content-length':str(len(data))}
        self.boundary=boundary;self.disconnect=disconnect
    async def stream(self):
        yield memoryview(self.data)[:CHUNK]
        if self.boundary:
            assert await anyio.to_thread.run_sync(self.boundary.wait, 3), 'writer did not start while receiving'
        if self.disconnect:raise ClientDisconnect()
        yield memoryview(self.data)[CHUNK:]


def run(store,key,data,provider,request=None,offset=0):
    async def call():
        return await transfer(request or Request(data),store,key,'admin',offset,provider,{},perf_counter)
    return anyio.run(call)


def create(env,data):
    store,sql,provider=env;key=str(uuid.uuid4())
    store.create(key,'admin','DRAFT','relay.psd',len(data),provider,digest(data))
    return store,key,provider


def test_reception_overlaps_one_ordered_writer_and_finishes_exact_bytes(env):
    data=psd(2*CHUNK);store,key,provider=create(env,data)
    started=threading.Event();received_next=threading.Event();append=provider.append;active=[0,0]
    def write(session,offset,content):
        active[0]+=1;active[1]=max(active)
        if offset==0:
            started.set();assert received_next.wait(3), 'second frame was not received during storage'
        append(session,offset,content);active[0]-=1
    provider.append=write
    class Overlap(Request):
        async def stream(self):
            yield memoryview(data)[:CHUNK]
            assert await anyio.to_thread.run_sync(started.wait,3)
            received_next.set()
            yield memoryview(data)[CHUNK:]
    result=run(store,key,data,provider,Overlap(data))
    assert result['data']['offset']==len(data) and active[1]==1
    assert provider.calls==[('append',CHUNK),('append',CHUNK)]
    assert store.finish(key,'admin',provider)['data']['source']['content_hash']==digest(data)


def test_disconnect_settles_active_append_then_restarts_from_durable_checkpoint(env):
    data=psd(2*CHUNK);store,key,provider=create(env,data);started=threading.Event();append=provider.append
    def write(*args):
        started.set();append(*args)
    provider.append=write
    with pytest.raises(ClientDisconnect):run(store,key,data,provider,Request(data,started,True))
    assert store.read(key,'admin')['data']['offset']==CHUNK
    # New service object, no in-memory queue/state. A complete legacy retry body
    # rechecks its first confirmed block and appends only the missing block.
    restarted=Intakes(store.connect)
    assert run(restarted,key,data,provider)['data']['offset']==2*CHUNK
    assert provider.calls==[('append',CHUNK),('append',CHUNK)]
    assert restarted.finish(key,'admin',provider)['data']['source']['content_hash']==digest(data)


def test_checkpoint_commit_failure_retries_without_duplicate_provider_bytes(env):
    data=psd(2*CHUNK);store,key,provider=create(env,data);original=store.locked;fail=[True]
    @contextmanager
    def failed_checkpoint(key,actor,**kwargs):
        with original(key,actor,**kwargs) as pair:
            yield pair
            if fail[0]:
                fail[0]=False
                raise RuntimeError('synthetic checkpoint commit failure')
    store.locked=failed_checkpoint
    with pytest.raises(RuntimeError,match='checkpoint commit'):run(store,key,data,provider)
    assert store.read(key,'admin')['data']['offset']==0
    assert provider.calls==[('append',CHUNK)]
    store=Intakes(store.connect)
    assert run(store,key,data,provider)['data']['offset']==2*CHUNK
    assert provider.calls==[('append',CHUNK),('append',CHUNK)]
    store.finish(key,'admin',provider);store.finish(key,'admin',provider)
    assert sum(k=='finish' for k,n in provider.calls)==1


def test_legacy_eight_mib_provider_commit_survives_new_four_mib_checkpoint_recovery(env):
    data=psd(2*CHUNK);store,key,provider=create(env,data)
    row=store.read(key,'admin')
    # Phase2 provider succeeded, process/DB commit failed before saving any offset.
    provider.append(row['data']['session'],0,data)
    assert run(Intakes(store.connect),key,data,provider)['data']['offset']==2*CHUNK
    assert sum(k=='append' for k,n in provider.calls)==1
    assert store.finish(key,'admin',provider)['data']['source']['content_hash']==digest(data)


def test_distributed_admission_bounds_distinct_uploads_and_reconcile_waits_for_writer():
    # Separate simulated connections share a database lock table, as separate
    # server workers do. This tests SQL lock identities/lifetime, not native PG IPC.
    locks={};rows={str(uuid.uuid4()):{} for _ in range(MAX_RELAYS+1)};keys=list(rows)
    class Cursor:
        def __init__(self,connection):self.connection=connection
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,args):
            if sql.startswith('SET LOCAL'):
                assert '20min' in sql;self.row={}
            elif 'pg_try_advisory' in sql:
                lock=tuple(args);owner=locks.get(lock);ok=owner in (None,self.connection)
                if ok:locks[lock]=self.connection
                self.row={'acquired':ok}
            else:self.row={'id':args[0],'actor_id':args[1],'data':rows[args[0]]}
        def fetchone(self):return deepcopy(self.row)
    class Connection:
        def __enter__(self):return self
        def cursor(self):return Cursor(self)
        def __exit__(self,*a):
            for key in list(locks):
                if locks[key] is self:del locks[key]
    with lease(Connection,keys[0],'admin'):
        with pytest.raises(RelayBusy):
            with lease(Connection,keys[0],'admin',capacity=False):pass
        with lease(Connection,keys[1],'admin'):
            assert sum(k[0]==GLOBAL_LOCK for k in locks)==MAX_RELAYS
            with pytest.raises(RelayBusy):
                with lease(Connection,keys[2],'admin'):pass
    assert not locks
    with lease(Connection,keys[2],'admin'):pass
    assert not locks
