import asyncio,json,hashlib
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from tests.test_auto_editions_jobs import database
from tests.test_companion_phase3 import DiskProvider
from companion_package_store import Sessions
from companion_package_identity import describe,CHUNK
import companion_acceptance as acceptance
from companion_acceptance_fixture import build,validate_fixture

RUN='b'*32

def test_fixture_has_100_assets_icc_and_independent_proofs(tmp_path):
    from auto_editions_package import unpack
    path=build(tmp_path/'packet',RUN);d=describe(path)
    assert CHUNK<d['bytes']<12*1024**2 and len(d['chunks'])==2
    root=tmp_path/'unpack';root.mkdir()
    m,proofs=unpack(path,root,d['manifest']['source'],100,100)
    validate_fixture(m,RUN)
    assert len(m['patches'])==100 and len(proofs)==3
    assert all(p.get('pixel_exact') or p.get('outside_number_exact') for p in proofs)
    with pytest.raises(ValueError):validate_fixture(m,'c'*32)

def test_disabled_or_unregistered_acceptance_never_uses_storage(monkeypatch):
    monkeypatch.delenv('COMPANION_ACCEPTANCE_RUN',raising=False)
    monkeypatch.setattr(acceptance,'service',lambda:pytest.fail('Storage reached'))
    app=Starlette(routes=[Route(p,h,methods=list(m)) for p,h,m in acceptance.ROUTES])
    with TestClient(app) as client:
        assert client.post('/api/auto-editions/acceptance/create',json={}).status_code==409
        monkeypatch.setenv('COMPANION_ACCEPTANCE_RUN',RUN)
        assert client.post('/api/auto-editions/acceptance/create',json={}).status_code==403

def test_private_schema_real_transactions_lost_ack_and_safe_cleanup(database,tmp_path,monkeypatch):
    import supabase_backend,auto_editions_onboarding_api,os_accounts
    jobs,sql=database
    migrations=Path(__file__).parents[1]/'supabase/migrations'
    sql.execute((migrations/'20261020002955_companion_resumable_packages.sql').read_text())
    sql.execute((migrations/'20261020050926_companion_isolated_acceptance.sql').read_text())
    monkeypatch.setattr(supabase_backend,'connect',jobs.connect)
    monkeypatch.setenv('COMPANION_ACCEPTANCE_RUN',RUN)
    monkeypatch.setattr(auto_editions_onboarding_api,'preparation_actor',AsyncMock(return_value={'id':'fixture-admin','role':os_accounts.ROLE_ADMIN}))
    provider=DiskProvider(tmp_path/'provider')
    monkeypatch.setattr(acceptance,'provider',lambda run:provider)
    app=Starlette(routes=[Route(p,h,methods=list(m)) for p,h,m in acceptance.ROUTES])
    path=build(tmp_path/'packet',RUN);d=describe(path)
    host='acceptance-host-fixture';headers={'x-sports-cave-preparation-host':host}
    digest=hashlib.sha256(host.encode()).hexdigest()
    with TestClient(app) as client:
        response=client.post('/api/auto-editions/acceptance/create',headers=headers,json=d)
        assert response.status_code==200,response.text
        state=response.json();key=state['id']
        first=path.read_bytes()[:CHUNK]
        h={**headers,'content-type':'application/octet-stream','x-sc-chunk-offset':'0','x-sc-chunk-sha256':d['chunks'][0]}
        assert client.post('/api/auto-editions/acceptance/chunk?id='+key,headers=h,content=first).status_code==503
        resumed=client.post('/api/auto-editions/acceptance/status?id='+key,headers=headers,json={}).json()
        assert resumed['offset']==CHUNK
        assert client.post('/api/auto-editions/acceptance/chunk?id='+key,headers=h,content=first).status_code==200
        assert provider.sent==CHUNK
        rest=path.read_bytes()[CHUNK:];h.update({'x-sc-chunk-offset':str(CHUNK),'x-sc-chunk-sha256':d['chunks'][1]})
        assert client.post('/api/auto-editions/acceptance/chunk?id='+key,headers=h,content=rest).status_code==200
        assert client.post('/api/auto-editions/acceptance/finalize?id='+key,headers=headers,json={}).status_code==503
        assert client.post('/api/auto-editions/acceptance/finalize?id='+key,headers=headers,json={}).json()['state']=='Queued'
    with acceptance.connect() as conn,conn.cursor() as cursor:
        cursor.execute('SELECT * FROM companion_package_uploads WHERE id=%s',(key,));row=cursor.fetchone()
    result=acceptance.cleanup_probe(acceptance.service(),'fixture-admin',digest,row['context'],d)
    assert result['expired_sessions']==1
    assert acceptance.service().status(key,'fixture-admin',digest)['state']=='Queued'
    # Same real validation/publication code, with a private file adapter locally.
    import auto_editions as ae,dropbox_integration as integration,files_upload_api
    from types import SimpleNamespace
    files={};uploads={}
    monkeypatch.setattr(files_upload_api,'_dropbox_context',lambda:{'access_token':'synthetic-fixture-only'})
    monkeypatch.setattr(integration,'ensure_folder_path',lambda *a,**kw:None)
    def metadata(path):
        if path not in files:return None
        content=files[path]
        block_hashes=b''.join(hashlib.sha256(content[i:i+4*1024**2]).digest() for i in range(0,len(content),4*1024**2))
        return dict(id=path,rev=hashlib.sha256(content).hexdigest(),size=len(content),content_hash=hashlib.sha256(block_hashes).hexdigest(),name=path.rsplit('/',1)[1],path_display=path)
    def upload(token,destination,path,**kwargs):
        assert destination not in files
        files[destination]=Path(path).read_bytes();uploads[destination]=uploads.get(destination,0)+1
        return metadata(destination)
    def response(token,path):
        content=files[path]
        return metadata(path),SimpleNamespace(iter_content=lambda **kw:iter([content]),close=lambda:None)
    monkeypatch.setattr(integration,'get_metadata_if_exists',lambda token,path:metadata(path))
    monkeypatch.setattr(integration,'upload_local_file',upload)
    monkeypatch.setattr(integration,'get_file_response',response)
    monkeypatch.setattr(integration,'list_folder_page',lambda token,path,**kw:{'entries':[metadata(p) for p in files if p.rsplit('/',1)[0]==path],'has_more':False})
    assert acceptance.service().run_one(acceptance.process)
    assert acceptance.service().status(key,'fixture-admin',digest)['state']=='Queued'
    with acceptance.connect() as conn,conn.cursor() as cursor:cursor.execute('UPDATE companion_package_uploads SET retry_at=now() WHERE id=%s',(key,))
    assert acceptance.service().run_one(acceptance.process)
    finished=acceptance.service().status(key,'fixture-admin',digest)
    assert finished['state']=='Complete',finished
    assert finished['result']['status']=='Cloud Ready' and finished['result']['verified_assets']==101
    assert len(uploads)==101 and max(uploads.values())==1
    sql.execute('SELECT count(*) AS n FROM public.companion_package_uploads');assert sql.fetchone()['n']==0
    sql.execute("SELECT has_schema_privilege('anon','companion_acceptance_v1','USAGE') AS allowed")
    assert not sql.fetchone()['allowed']

def test_native_acceptance_refuses_busy_companion(tmp_path):
    import threading
    from types import SimpleNamespace
    from scripts.studio import companion_acceptance_local as local
    busy=threading.Event();busy.set()
    host=SimpleNamespace(LOCK=threading.Lock(),HOST_BUSY=busy,JOBS={})
    with pytest.raises(ValueError,match='idle'):local.start(host,RUN)

def test_client_refuses_arbitrary_protocol_paths(tmp_path):
    from companion_package_client import upload
    from companion_transfer import Controller
    path=build(tmp_path/'packet',RUN)
    with pytest.raises(ValueError,match='Unsupported upload route'):
        upload(Controller(),path,{'base_url':'https://example.test','upload_path':'/arbitrary/'},{'base_url':'https://example.test'},tmp_path/'journal',correlation=RUN)
