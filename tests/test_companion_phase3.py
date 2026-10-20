"""Durable SQL/provider faults and real HTTP receiver tests; no live capability."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
import requests
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn
import auto_editions as ae
from companion_package_identity import describe,CHUNK
from companion_package_store import Sessions
from tests.test_auto_editions_jobs import database
from tests.test_auto_editions_package import archive as small_archive

MIGRATION=Path(__file__).parents[1]/'supabase/migrations/20261020002955_companion_resumable_packages.sql'
HOST='a'*64


class DiskProvider:
    """A fresh adapter instance sees fsynced provider bytes after every restart."""
    def __init__(self,root):self.root=Path(root);self.root.mkdir(exist_ok=True);self.sent=0;self.finishes=0;self.downloads=0;self.lose_append=False;self.lose_finish=False
    def start(self):
        key=uuid.uuid4().hex;(self.root/(key+'.part')).write_bytes(b'');return key
    def destination(self,key):return str(self.root/(key+'.zip'))
    def append(self,key,offset,content):
        path=self.root/(key+'.part');actual=path.stat().st_size
        if actual!=offset:
            error=requests.ConnectionError('Provider offset');error.correct_offset=actual;raise error
        with path.open('ab') as output:output.write(content);output.flush();os.fsync(output.fileno())
        self.sent+=len(content)
        if self.lose_append:self.lose_append=False;raise requests.ConnectionError('Lost provider ACK')
    def finish(self,key,size,destination):
        source=self.root/(key+'.part');assert source.stat().st_size==size
        source.replace(destination);self.finishes+=1
        if self.lose_finish:self.lose_finish=False;raise requests.ConnectionError('Lost finish ACK')
    def metadata_if_present(self,path):
        path=Path(path)
        if not path.exists():return None
        return dict(id=str(path),rev=ae.file_hash(path),size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True))
    def download(self,receipt,destination):
        assert self.metadata_if_present(receipt['id'])==receipt
        shutil.copyfile(receipt['id'],destination);self.downloads+=1
    def discard(self,path,receipt):
        assert Path(path).resolve().parent==self.root.resolve()
        assert self.metadata_if_present(path)==receipt
        Path(path).unlink()


@pytest.fixture
def env(database,tmp_path,monkeypatch):
    jobs,sql=database;sql.execute(MIGRATION.read_text(encoding='utf-8'))
    provider=DiskProvider(tmp_path/'provider');store=Sessions(jobs.connect,provider)
    (tmp_path/'fixture').mkdir()
    path,_,manifest=small_archive(tmp_path/'fixture')
    context=dict(source=manifest['source'],total=manifest['edition_total'],number=2,product_gid=manifest['source']['product_gid'],lease_token='fixture-lease',automatic=True)
    descriptor=describe(path)
    monkeypatch.setenv('SPORTS_CAVE_COMPANION_SOURCE_CACHE',str(tmp_path/'source-cache'))
    return SimpleNamespace(store=store,provider=provider,sql=sql,context=context,path=path,descriptor=descriptor,manifest=manifest,root=tmp_path,connect=jobs.connect)


def create(e):return e.store.create('owner',HOST,'https://shop.fixture',e.context,e.descriptor)


def send(e,state):
    with e.path.open('rb') as source:
        for offset in range(state['offset'],e.descriptor['bytes'],CHUNK):
            source.seek(offset);data=source.read(CHUNK)
            state=e.store.chunk(state['id'],'owner',HOST,offset,data,hashlib.sha256(data).hexdigest())
    return state


def verify(e,row,path):
    from auto_editions_package import unpack
    root=path.parent/'assets';root.mkdir()
    manifest,proofs=unpack(path,root,row['context']['source'],row['context']['number'],row['context']['total'])
    assert manifest==e.manifest and all(p.get('pixel_exact') or p.get('outside_number_exact') for p in proofs)
    return dict(preparation_hash=ae.fingerprint(manifest),status='Cloud Ready',synthetic_provider_verification=True)


def test_complete_duplicate_finalize_and_restart(env):
    e=env;state=create(e);assert state==create(e)
    state=send(e,state);queued=e.store.finalize(state['id'],'owner',HOST)
    assert queued['state']=='Queued' and not queued['result']
    assert e.store.finalize(state['id'],'owner',HOST)==queued
    restarted=Sessions(e.connect,DiskProvider(e.provider.root))
    assert restarted.run_one(lambda row,path:verify(e,row,path))
    completed=restarted.status(state['id'],'owner',HOST)
    assert completed['state']=='Complete' and completed['result']['status']=='Cloud Ready'
    assert not restarted.run_one(lambda *a:pytest.fail('Duplicate finalisation'))
    assert e.provider.finishes==1


def test_lost_provider_ack_and_conflicting_or_incomplete_chunks(env):
    e=env;state=create(e);payload=e.path.read_bytes();digest=hashlib.sha256(payload).hexdigest()
    e.provider.lose_append=True
    with pytest.raises(requests.ConnectionError):e.store.chunk(state['id'],'owner',HOST,0,payload,digest)
    assert e.store.status(state['id'],'owner',HOST)['offset']==0
    state=e.store.chunk(state['id'],'owner',HOST,0,payload,digest)
    assert e.provider.sent==len(payload)
    assert e.store.chunk(state['id'],'owner',HOST,0,payload,digest)==state
    with pytest.raises(ValueError):e.store.chunk(state['id'],'owner',HOST,0,payload+b'bad',hashlib.sha256(payload+b'bad').hexdigest())
    with pytest.raises(ValueError):e.store.chunk(state['id'],'owner',HOST,1,payload,digest)
    with pytest.raises(PermissionError):e.store.status(state['id'],'owner','b'*64)
    e.provider.lose_finish=True
    with pytest.raises(requests.ConnectionError):e.store.finalize(state['id'],'owner',HOST)
    assert e.store.finalize(state['id'],'owner',HOST)['state']=='Queued' and e.provider.finishes==1


def test_binding_change_expiry_cleanup_and_private_rls(env):
    e=env;state=create(e)
    with pytest.raises(ValueError):e.store.finalize(state['id'],'owner',HOST)
    changed=deepcopy(e.descriptor);changed['manifest']['source']['revision']='other'
    changed['preparation_hash']=ae.fingerprint(changed['manifest'])
    with pytest.raises(ValueError):e.store.create('owner',HOST,'https://shop.fixture',e.context,changed)
    with pytest.raises(ValueError):e.store.create('owner',HOST,'https://shop.fixture',e.context,{**e.descriptor,'generation':'0'*64})
    with pytest.raises(ValueError):e.store.create('owner',HOST,'https://shop.fixture',e.context,{**e.descriptor,'sha256':'f'*64})
    send(e,state);e.store.finalize(state['id'],'owner',HOST)
    e.sql.execute("UPDATE companion_package_uploads SET expires_at=now()-interval '1 second'")
    with pytest.raises(ValueError):create(e)
    assert e.store.cleanup()==1 and not Path(e.provider.destination(state['id'])).exists()
    with pytest.raises(ValueError):e.store.status(state['id'],'owner',HOST)
    e.sql.execute("SELECT relrowsecurity AS rls,has_table_privilege('anon','companion_package_uploads','SELECT') AS public_read,has_table_privilege('authenticated','companion_package_uploads','INSERT') AS client_write FROM pg_class WHERE relname='companion_package_uploads'")
    permissions=e.sql.fetchone();assert permissions['rls'] and not permissions['public_read'] and not permissions['client_write']


def test_corrupt_complete_package_and_partial_publication_recovery(env):
    e=env;desc={**e.descriptor,'sha256':'0'*64};e.descriptor=desc
    state=create(e);send(e,state);e.store.finalize(state['id'],'owner',HOST)
    assert e.store.run_one(lambda *a:pytest.fail('Corrupt package reached publication'))
    assert e.store.status(state['id'],'owner',HOST)['state']=='Blocked'


def test_partial_publication_and_post_checkpoint_crash(env):
    e=env;state=create(e);send(e,state);e.store.finalize(state['id'],'owner',HOST)
    # Model existing immutable publication receipts outside the worker process.
    published=set();writes=[]
    def processing(row,path):
        for name in ('master','patch-1','patch-2'):
            if name in published:continue
            published.add(name);writes.append(name)
            if len(writes)==1:raise requests.ConnectionError('Provider interrupted after master receipt')
        return verify(e,row,path)
    assert e.store.run_one(processing)
    assert e.store.status(state['id'],'owner',HOST)['state']=='Queued'
    e.sql.execute("UPDATE companion_package_uploads SET retry_at=now()")
    restarted=Sessions(e.connect,DiskProvider(e.provider.root));assert restarted.run_one(processing)
    assert writes==['master','patch-1','patch-2']
    assert restarted.status(state['id'],'owner',HOST)['state']=='Complete'
    # A durable technical checkpoint can recover the same result without even
    # fetching/revalidating the same completed immutable packet a second time.
    e.sql.execute("UPDATE companion_package_uploads SET state='Queued',result=NULL")
    result=dict(preparation_hash=e.descriptor['preparation_hash'],status='Cloud Ready')
    before=restarted.provider.downloads
    assert restarted.run_one(lambda *a:pytest.fail('Duplicate publication'),recover=lambda _:result)
    assert restarted.provider.downloads==before


def test_concurrent_finalize_and_crash_rollback_cannot_strand_job(env):
    e=env;state=create(e);send(e,state)
    with ThreadPoolExecutor(6) as pool:
        results=list(pool.map(lambda _:e.store.finalize(state['id'],'owner',HOST),range(6)))
    assert all(r['state']=='Queued' for r in results) and e.provider.finishes==1
    class ProcessCrash(BaseException):pass
    def crash(*args):raise ProcessCrash()
    with pytest.raises(ProcessCrash):e.store.run_one(crash)
    assert e.store.status(state['id'],'owner',HOST)['state']=='Queued'
    assert Sessions(e.connect,DiskProvider(e.provider.root)).run_one(lambda row,path:verify(e,row,path))


def test_corrupt_or_incomplete_zip_never_reaches_ready(env):
    e=env
    # A correctly transferred but invalid package still fails independent unpack.
    e.path.write_bytes(b'not a ZIP')
    e.descriptor={**e.descriptor,'bytes':e.path.stat().st_size,'sha256':ae.file_hash(e.path),'chunks':[ae.file_hash(e.path)]}
    state=create(e);send(e,state);e.store.finalize(state['id'],'owner',HOST)
    assert e.store.run_one(lambda row,path:verify(e,row,path))
    assert e.store.status(state['id'],'owner',HOST)['state']=='Queued' # Retry budget, never Ready.
    e.sql.execute("UPDATE companion_package_uploads SET retry_at=now(),attempts=2")
    e.store.run_one(lambda row,path:verify(e,row,path))
    assert e.store.status(state['id'],'owner',HOST)['state']=='Blocked'


def test_resumable_api_requires_existing_host_auth_before_any_storage(monkeypatch):
    import companion_package_api as api
    from starlette.requests import Request
    from unittest.mock import Mock
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','true')
    storage=Mock(side_effect=AssertionError('Unauthorized provider access'))
    monkeypatch.setattr(api,'service',storage)
    request=Request(dict(type='http',method='POST',path='/api/auto-editions/uploads/create',path_params={'upload_action':'create'},headers=[],query_string=b''))
    assert asyncio.run(api.host(request)).status_code==403
    storage.assert_not_called()


@contextmanager
def http_receiver(e,monkeypatch,*,lose_chunk_ack=False,port=0):
    import companion_package_api as api
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','true')
    token='fixture-host';host=hashlib.sha256(token.encode()).hexdigest()
    monkeypatch.setenv('SPORTS_CAVE_AUTO_EDITIONS_V6','true')
    monkeypatch.setattr(api,'service',lambda:e.store)
    monkeypatch.setattr(onboarding,'preparation_actor',AsyncMock(return_value={'id':'owner'}))
    monkeypatch.setattr(setup,'grant_context',lambda _:dict(context=e.context,actor_id='owner',host_token_hash=host))
    monkeypatch.setattr(api,'current',lambda row:None)
    # This fixture authenticates only synthetic identities. Separate tests below
    # exercise rejection by the real authorization boundary.
    lost=[lose_chunk_ack];seen=[]
    class Observe:
        def __init__(self,app):self.app=app
        async def __call__(self,scope,receive,send):
            count=0;started=time.monotonic()
            async def counted():
                nonlocal count
                event=await receive();count+=len(event.get('body',b''));return event
            async def observed(event):
                if scope['path'].endswith('/chunk') and lost[0]:
                    if event['type']=='http.response.start':
                        lost[0]=False;event={**event,'status':503}
                await send(event)
            await self.app(scope,counted,observed)
            seen.append(dict(path=scope['path'],bytes=count,seconds=time.monotonic()-started))
    app=Observe(Starlette(routes=[Route(p,f,methods=list(m)) for p,f,m in api.ROUTES]))
    sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',port));base='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started:
            assert time.monotonic()<deadline;time.sleep(.01)
        yield base,token,seen
    finally:server.should_exit=True;thread.join(5);sock.close()


def padded(e):
    # Fault fixture only: a legal ZIP preamble provides several protocol chunks
    # without regenerating PSDs/images. Never used for performance/package savings.
    data=e.path.read_bytes()
    with e.path.open('wb') as output:
        output.write(b'F'*(2*CHUNK));output.write(data)
    e.descriptor=describe(e.path)


def test_http_lost_ack_companion_restart_and_server_confirmed_resume(env,monkeypatch):
    from companion_transfer import Controller
    from companion_package_client import upload
    e=env;padded(e);controller=Controller();controller.configure({'mode':'Maximum speed'})
    journal=e.root/'session.json'
    with http_receiver(e,monkeypatch,lose_chunk_ack=True) as (base,token,seen):
        grant=dict(base_url=base,ticket='fixture',secret='fixture-secret');host=dict(base_url=base,token=token)
        with pytest.raises(requests.HTTPError):upload(controller,e.path,grant,host,journal,correlation='c'*32,poll_interval=.02)
        saved=json.loads(journal.read_text());status=e.store.status(saved['id'],'owner',hashlib.sha256(token.encode()).hexdigest())
        assert status['offset']==CHUNK and saved['confirmed_bytes']==0
        assert token not in journal.read_text() and grant['secret'] not in journal.read_text()
        old_seen=list(seen);port=int(base.rsplit(':',1)[1]);previous_sent=e.provider.sent
    e.provider=DiskProvider(e.provider.root);e.store=Sessions(e.connect,e.provider)
    with http_receiver(e,monkeypatch,port=port) as (base,token,seen):
        original=e.store.finalize
        def finalise(*a):
            result=original(*a)
            threading.Thread(target=lambda:e.store.run_one(lambda row,path:verify(e,row,path)),daemon=True).start()
            return result
        monkeypatch.setattr(e.store,'finalize',finalise)
        restarted=Controller();restarted.configure({'mode':'Maximum speed'})
        result=upload(restarted,e.path,grant,host,journal,correlation='c'*32,poll_interval=.02)
        assert result['status']=='Cloud Ready' and restarted.last['resumed_bytes']==CHUNK
        assert sum(row['bytes'] for row in old_seen+seen if row['path'].endswith('/chunk'))==e.path.stat().st_size
        assert previous_sent+e.provider.sent==e.path.stat().st_size


def test_chunk_boundary_pause_responsive_controls_and_budget(env,monkeypatch):
    from companion_transfer import Controller
    from companion_package_client import upload
    e=env;padded(e);c=Controller();c.configure({'mode':'Manual','manual_mbps':32})
    with http_receiver(e,monkeypatch) as (base,token,seen),ThreadPoolExecutor(2) as pool:
        grant=dict(base_url=base,ticket='fixture',secret='fixture');host=dict(base_url=base,token=token)
        done=e.store.finalize
        def finalise(*a):
            result=done(*a);threading.Thread(target=lambda:e.store.run_one(lambda row,path:verify(e,row,path)),daemon=True).start();return result
        monkeypatch.setattr(e.store,'finalize',finalise)
        started=time.monotonic();future=pool.submit(upload,c,e.path,grant,host,e.root/'session.json',correlation='d'*32,poll_interval=.02)
        deadline=time.monotonic()+5
        while c.active is None or c.active['transport_bytes']<65536:
            assert time.monotonic()<deadline;time.sleep(.01)
        c.configure({**c.value,'paused':True},'pause')
        deadline=time.monotonic()+8
        while c.active['state']!='Paused':
            assert time.monotonic()<deadline;time.sleep(.02)
        received=e.provider.sent;assert received==CHUNK
        saved=json.loads((e.root/'session.json').read_text());assert saved['confirmed_bytes']==CHUNK
        start=time.monotonic();response=requests.post(base+'/api/auto-editions/uploads/status?id='+saved['id'],json={},headers={'X-Sports-Cave-Preparation-Host':token},timeout=2)
        assert response.status_code==200 and time.monotonic()-start<.5
        time.sleep(.15);assert e.provider.sent==received and not future.done()
        c.configure({**c.value,'paused':False},'resume')
        assert future.result(12)['status']=='Cloud Ready'
        assert time.monotonic()-started>=e.path.stat().st_size*8/32e6-.2
        assert c.last['pause_wait_seconds']>=.1


def test_source_cache_identity_revision_hash_and_bounded_cleanup(tmp_path,monkeypatch):
    import companion_source_cache as cache
    source=tmp_path/'original.psd';source.write_bytes(b'authoritative source bytes')
    original=source.read_bytes();identity=dict(file_id='id:source',revision='rev1',content_hash=ae.file_hash(source,dropbox=True))
    root=tmp_path/'cache';assert cache.remember(source,identity,len(original),cache=root)
    output=tmp_path/'reused.psd';assert cache.reuse(output,identity,len(original),cache=root)
    assert output.read_bytes()==original and source.read_bytes()==original
    assert cache.reuse(tmp_path/'wrong.psd',{**identity,'revision':'rev2'},len(original),cache=root) is None
    next(root.glob('*/input.psd')).write_bytes(b'corrupt'+original[7:])
    assert cache.reuse(tmp_path/'corrupt.psd',identity,len(original),cache=root) is None


def test_finish_commit_lost_before_sql_receipt_cleanup(env):
    e=env;state=send(e,create(e));e.provider.lose_finish=True
    with pytest.raises(requests.ConnectionError):e.store.finalize(state['id'],'owner',HOST)
    assert list(e.provider.root.glob('*.zip'))
    e.sql.execute("UPDATE companion_package_uploads SET expires_at=now()-interval '1 second'")
    assert e.store.cleanup()==1 and not list(e.provider.root.glob('*.zip'))


def test_verification_only_resume_ignores_bulk_pause_and_missing_calibration(env,monkeypatch):
    from companion_transfer import Controller
    from companion_package_client import upload
    e=env
    with http_receiver(e,monkeypatch) as (base,token,seen):
        host=hashlib.sha256(token.encode()).hexdigest()
        state=e.store.create('owner',host,base,e.context,e.descriptor)
        payload=e.path.read_bytes()
        e.store.chunk(state['id'],'owner',host,0,payload,hashlib.sha256(payload).hexdigest())
        e.store.finalize(state['id'],'owner',host)
        e.store.run_one(lambda row,path:verify(e,row,path))
        c=Controller();c.configure({**c.value,'paused':True})
        assert c.snapshot()['protection']=='Calibration needed'
        result=upload(c,e.path,dict(base_url=base,ticket='fixture',secret='fixture'),dict(base_url=base,token=token),e.root/'recovered.json',correlation='a'*32,poll_interval=.02)
        assert result['status']=='Cloud Ready'
        assert sum(r['bytes'] for r in seen if r['path'].endswith('/chunk'))==0


def test_package_reuse_requires_generation_preparation_and_actual_package_hash(env,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    from companion_package_identity import generation
    e=env;folder=e.root/'retained';folder.mkdir();target=folder/'prepared.zip';shutil.copyfile(e.path,target)
    monkeypatch.setattr(local,'HOST_FILE',e.root/'host.dpapi')
    # This tiny fixture has no production colour attestation; reuse still must
    # reject missing/mismatched provenance before reaching its colour gates.
    assert local.find_reusable_package(e.context,generation=generation()) is None
    provenance=dict(generation=generation(),preparation_hash=e.descriptor['preparation_hash'],sha256='0'*64)
    (folder/'package-identity.json').write_text(json.dumps(provenance))
    assert local.find_reusable_package(e.context,generation=generation()) is None
    row=dict(folder=e.root,upload_protocol=1,generation='0'*64)
    assert local.package_finished(row,e.context) is None


def test_real_immutable_publisher_resumes_partial_receipts(env):
    from auto_editions_cloud import DropboxAssets
    from auto_editions_package import unpack
    e=env;state=send(e,create(e));e.store.finalize(state['id'],'owner',HOST)
    records={};writes=[];failed=[False]
    class Integration:
        def ensure_folder_path(self,*a,**kw):pass
        def list_folder_page(self,*a,**kw):return dict(entries=list(records.values()),has_more=False)
        def get_metadata_if_exists(self,token,path):return records.get(path)
        def upload_local_file(self,token,path,local,conflict):
            assert conflict=='cancel'
            if local.name=='number-2.png' and not failed[0]:
                failed[0]=True;raise requests.ConnectionError('Synthetic provider fault')
            assert path not in records
            writes.append(local.name)
            row=dict(name=local.name,path_lower=path.lower(),id='id:'+local.stem,rev='fixture',size=local.stat().st_size,content_hash=ae.file_hash(local,dropbox=True))
            records[path]=row;return row
    assets=DropboxAssets('synthetic',Integration())
    def process(row,path):
        expanded=path.parent/'assets';expanded.mkdir()
        manifest,_=unpack(path,expanded,row['context']['source'],2,2)
        receipts=assets.publish_preparation(manifest,expanded)
        assert len(receipts['assets'])==3
        return dict(preparation_hash=ae.fingerprint(manifest),status='Cloud Ready',synthetic_provider_verification=True)
    e.store.run_one(process)
    assert e.store.status(state['id'],'owner',HOST)['state']=='Queued' and len(records)==2
    e.sql.execute("UPDATE companion_package_uploads SET retry_at=now()")
    Sessions(e.connect,DiskProvider(e.provider.root)).run_one(process)
    assert e.store.status(state['id'],'owner',HOST)['state']=='Complete'
    assert sorted(writes)==['master.png','number-1.png','number-2.png']
    assert assets.timings['prepared_reused_assets']==2 and assets.timings['prepared_upload_requests']==1


def test_source_cache_budget_evicts_only_owned_regular_files(tmp_path,monkeypatch):
    import companion_source_cache as cache
    monkeypatch.setattr(cache,'BUDGET',12);root=tmp_path/'cache'
    originals=[]
    for n in range(2):
        path=tmp_path/f'original-{n}.psd';path.write_bytes(bytes([n])*8);originals.append(path)
        identity=dict(file_id=f'id:{n}',revision='r',content_hash=ae.file_hash(path,dropbox=True))
        assert cache.remember(path,identity,8,cache=root)
    assert len(list(root.glob('*/input.psd')))==1
    assert all(p.read_bytes()==bytes([n])*8 for n,p in enumerate(originals))
    retained=next(root.iterdir());(retained/'unexpected.txt').write_text('preserve')
    third=tmp_path/'third.psd';third.write_bytes(b't'*8)
    identity=dict(file_id='id:third',revision='r',content_hash=ae.file_hash(third,dropbox=True))
    assert cache.remember(third,identity,8,cache=root) is False
    assert (retained/'unexpected.txt').read_text()=='preserve'


def test_completed_resume_rejects_changed_generation_before_provider_access(env,monkeypatch):
    import companion_package_api as api
    import auto_editions_onboarding_api as onboarding
    from unittest.mock import Mock
    store=Mock();monkeypatch.setattr(onboarding,'queue',lambda:store)
    row=dict(context=env.context,descriptor={**env.descriptor,'generation':'0'*64})
    with pytest.raises(ValueError,match='fingerprint changed'):api.current(row)
    store.connect.assert_not_called();store.completed_receipt.assert_not_called()


def test_protocol_negotiation_requires_existing_durable_worker(monkeypatch):
    import companion_package_api as api
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','true')
    monkeypatch.setenv('SPORTS_CAVE_AUTO_EDITIONS_V6','false');assert api.capability()==0
    monkeypatch.setenv('SPORTS_CAVE_AUTO_EDITIONS_V6','true');assert api.capability()==1
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','false');assert api.capability()==0
