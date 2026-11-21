from types import SimpleNamespace
import json
import pytest
from test_auto_editions_jobs import database
from test_prodigi_preparation import store


def test_insert_library_ids_resolve_to_exact_saved_transform_ids():
    from prodigi_dashboard_qa import insert_checks,SET
    saved=[dict(name='Round packaging sticker',asset='saved-sticker'),dict(name='Packing slip (colour)',asset='saved-slip')]
    expected=[dict(name='Round packaging sticker',asset='library-sticker'),dict(name='Packing slip (colour)',asset='library-slip')]
    proof=dict(set_name=SET,saved=saved,expected=expected,available=True)
    assert insert_checks(proof)==(False,False)
    calls=[]
    def asset(key):
        calls.append(key);return dict(id=key,url='https://live-services.pwinty.com/image-library/transform/'+key.replace('library-','saved-')+'/image?access_token=not-logged')
    assert insert_checks(proof,asset)==(True,True) and len(calls)==2
    proof['available']=False
    assert insert_checks(proof,asset)==(True,False) # Local unavailability is never waived.
    assert insert_checks(proof,lambda key:dict(id='wrong',url=asset(key)['url']))==(False,False)


def test_thumbnail_is_small_and_never_changes_the_print_file(tmp_path,monkeypatch):
    from PIL import Image
    import orders_preview as preview
    import hashlib
    monkeypatch.setattr(preview.tempfile,'gettempdir',lambda:str(tmp_path))
    source=tmp_path/'print.jpg';Image.new('RGB',(3200,2000),(190,150,80)).save(source)
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    output=preview.create(source,sha)
    with Image.open(output) as small:assert max(small.size)<=1000
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    assert preview.create(source,sha)==output and output.stat().st_size<100000
    with pytest.raises(ValueError):preview.cached('../outside')


def test_new_ready_jpg_enters_fulfilment_once_when_owner_enabled(database,monkeypatch):
    from test_orders_auto_jpg import tables
    import orders_auto_jpg as auto,auto_editions_runtime as runtime,auto_editions as ae
    import prodigi_preparation as prep,os_accounts
    jobs,sql=database;tables(sql);calls=[]
    sql.execute('INSERT INTO app_settings(key,value) VALUES(%s,to_jsonb(%s::text))',(auto.SINCE,'2020-01-01T00:00:00Z'))
    identity={'allocation_id':1};job={'id':ae.fingerprint(identity),'identity':identity}
    jobs.enqueue(job,'fixture');sql.execute("UPDATE auto_edition_jobs SET status='Ready'")
    monkeypatch.setattr(runtime,'stores',lambda:(None,jobs))
    monkeypatch.setattr('prodigi_submission.setting',lambda:dict(enabled=True,actor='owner'))
    monkeypatch.setattr(os_accounts,'DEFAULT_STORE',SimpleNamespace(get_user=lambda _:dict(id='owner')))
    monkeypatch.setattr(prep,'request',lambda owner,aid:calls.append((owner['id'],aid)))
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    assert auto.admit(jobs.connect)==1 and calls==[('owner',1)]
    sql.execute("UPDATE app_settings SET updated_at=now()-interval '1 minute'")
    assert auto.admit(jobs.connect)==0 and len(calls)==1


def test_restart_is_authenticated_and_cannot_reset_a_submission(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api,prodigi_preparation as prep,files_upload_api as files
    calls=[]
    monkeypatch.setattr(files,'_same_origin',lambda _:True)
    monkeypatch.setattr(files,'_request_user',lambda *a,**k:dict(id='owner'))
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(prep,'read',lambda _:dict(status='Submitted',submission={'intent_at':'saved'}))
    monkeypatch.setattr(prep,'reconcile',lambda *_:pytest.fail('Never clear a supplier submission fence'))
    monkeypatch.setattr('prodigi_submission.kick',lambda:calls.append('readback'))
    client=TestClient(Starlette(routes=[Route('/restart',api.restart_order,methods=['POST'])]))
    assert client.post('/restart',json={'allocation_id':1}).status_code==403 and not calls
    response=client.post('/restart',json={'allocation_id':1},headers={'Origin':'https://fixture.invalid'})
    assert response.status_code==200 and response.json()['status']=='Submitted' and calls==['readback']


def test_automatic_mirror_admission_skips_completed_invalid_and_previously_failed(store,monkeypatch):
    import orders_automatic as auto,prodigi_preparation as prep,os_accounts
    monkeypatch.setattr(auto,'_last',0)
    monkeypatch.setattr('prodigi_submission.setting',lambda:dict(enabled=True,actor='owner'))
    monkeypatch.setattr(os_accounts,'DEFAULT_STORE',SimpleNamespace(get_user=lambda _:dict(id='owner')))
    rows=[dict(edition_order_id=i,prodigi_status='Complete' if i==1 else '') for i in range(1,5)]
    monkeypatch.setattr('order_allocator.load_hybrid_orders_snapshot',lambda **_:{'rows':rows})
    monkeypatch.setattr('order_refunds.blocked',lambda _:False)
    with store() as c,c.cursor() as q:
        q.execute('CREATE TABLE edition_orders(id bigint,status text,allocation_valid bool,identity_enforced bool,invalidated_at timestamptz)')
        q.execute("INSERT INTO edition_orders VALUES(1,'assigned',true,true,NULL),(2,'assigned',true,true,NULL),(3,'assigned',false,true,NULL),(4,'assigned',true,true,NULL)")
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(prep.FAILURE_PREFIX+'4',json.dumps({'active':True})))
    calls=[]
    def request(owner,aid):
        calls.append(aid)
        with store() as c,c.cursor() as q:prep.save(q,dict(allocation_id=aid,status='Queued'))
    monkeypatch.setattr(prep,'request',request)
    assert auto.admit()==1 and calls==[2]
    monkeypatch.setattr(auto,'_last',0)
    assert auto.admit()==0 and calls==[2]
