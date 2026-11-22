from types import SimpleNamespace
import json
import pytest
from test_auto_editions_jobs import database
from test_prodigi_preparation import store


def test_observed_insert_names_reach_the_drawer_without_asset_lookup():
    from prodigi_dashboard_qa import insert_checks
    from orders_prodigi_grid import review
    proof=dict(saved=[dict(name='New slip',asset=None),dict(name='New sticker',asset=None)],available=False)
    assert insert_checks(proof,lambda _:pytest.fail('No image-library lookup'))==(True,True)
    result=review(dict(qa=dict(inserts=dict(names=['New slip','New sticker']))),dict(edition_order_id=1),'')
    assert result['insert_names']==['New slip','New sticker']


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


@pytest.mark.parametrize('enabled',[True,False])
def test_new_ready_jpg_enters_fulfilment_once_for_authorised_owner(database,monkeypatch,enabled):
    from test_orders_auto_jpg import tables
    import orders_auto_jpg as auto,auto_editions_runtime as runtime,auto_editions as ae
    import prodigi_preparation as prep,os_accounts
    jobs,sql=database;tables(sql);calls=[]
    sql.execute('INSERT INTO app_settings(key,value) VALUES(%s,to_jsonb(%s::text))',(auto.SINCE,'2020-01-01T00:00:00Z'))
    identity={'allocation_id':1};job={'id':ae.fingerprint(identity),'identity':identity}
    jobs.enqueue(job,'fixture');sql.execute("UPDATE auto_edition_jobs SET status='Ready'")
    monkeypatch.setattr(runtime,'stores',lambda:(None,jobs))
    monkeypatch.setattr('prodigi_submission.setting',lambda:dict(enabled=enabled,actor='owner'))
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
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(prep,'reconcile',lambda *_:pytest.fail('Never clear a supplier submission fence'))
    monkeypatch.setattr('prodigi_submission.kick',lambda:calls.append('readback'))
    client=TestClient(Starlette(routes=[Route('/restart',api.restart_order,methods=['POST'])]))
    assert client.post('/restart',json={'allocation_id':1}).status_code==403 and not calls
    response=client.post('/restart',json={'allocation_id':1},headers={'Origin':'https://fixture.invalid'})
    assert response.status_code==409 and not calls and 'submission' in response.json()['error'].lower()


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


def test_progress_endpoint_is_bounded_authenticated_and_only_returns_review_fields(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api,prodigi_preparation as prep,files_upload_api as files,orders_prodigi_grid as grid
    monkeypatch.setattr(files,'_request_user',lambda *a,**k:dict(id='owner'))
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    calls=[]
    def statuses(ids):
        calls.append(ids)
        return {'1':dict(status='Checking QA',checks={},snapshot={'recipient':'private-not-for-browser'})}
    monkeypatch.setattr(grid,'batch_status',statuses)
    client=TestClient(Starlette(routes=[Route('/status',api.order_status)]))
    response=client.get('/status?allocations=1,2')
    assert response.status_code==200 and response.json()['orders']['1']['status']=='Checking QA'
    assert 'private-not-for-browser' not in response.text
    assert client.get('/status?allocations='+','.join(str(i) for i in range(1,202))).status_code!=200
    assert len(calls)==1
    def denied(*a,**k):raise PermissionError('Orders access required')
    monkeypatch.setattr(files,'_request_user',denied)
    assert client.get('/status?allocations=1').status_code==403 and len(calls)==1


def test_waiting_jpg_yields_to_other_orders_qa(store,monkeypatch):
    import prodigi_preparation as prep,auto_editions_runtime as runtime,prodigi_full_qa as full
    from test_prodigi_preparation import value,Provider
    first=value();first['status']='Preparing JPG'
    second=value();second.update(allocation_id=2,status='Checking QA')
    with store() as c,c.cursor() as q:
        prep.save(q,first);prep.save(q,second)
        q.execute("UPDATE app_settings SET updated_at=now()-interval '2 minutes' WHERE key='prodigi_prepare:1'")
        q.execute("UPDATE app_settings SET updated_at=now()-interval '1 minute' WHERE key='prodigi_prepare:2'")
    monkeypatch.setattr(runtime,'stores',lambda:(None,SimpleNamespace(read=lambda _:dict(status='Queued'))))
    monkeypatch.setattr(runtime,'start_worker',lambda:None)
    monkeypatch.setattr(prep,'Client',Provider)
    calls=[]
    def check(value,provider,resolver,persist):
        calls.append(value['allocation_id']);value['status']='Awaiting dashboard QA';persist(value);return value
    monkeypatch.setattr(full,'run',check)
    assert prep.tick()['allocation_id']==1
    assert prep.tick()['allocation_id']==2 and calls==[2]


def test_customer_jpg_runs_before_background_catalogue_acceptance(monkeypatch):
    import auto_editions_runtime as runtime
    enabled=iter([True,False]);calls=[]
    jobs=SimpleNamespace(expired=lambda:[],connect=lambda:None)
    monkeypatch.setattr(runtime,'enabled',lambda:next(enabled,False))
    monkeypatch.setattr(runtime,'stores',lambda:(None,jobs))
    monkeypatch.setattr('orders_auto_jpg.admit',lambda _:None)
    monkeypatch.setattr('orders_automatic.admit',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('auto_editions_repair.admit',lambda _:None)
    monkeypatch.setattr('auto_editions_repair.run_one',lambda _:None)
    monkeypatch.setattr('companion_acceptance.run_one',lambda:True)
    monkeypatch.setattr(runtime,'run_one',lambda _:calls.append('customer-jpg') or True)
    runtime._loop()
    assert calls==['customer-jpg']


def test_selected_shipping_quote_uses_saved_verified_evidence_only():
    from orders_prodigi_grid import shipping_summary
    saved=dict(checks=dict(shipping=True),dashboard_qa=dict(verified=True,shipping=dict(target='standard',options=[dict(service='budget',cents=2730,currency='$'),dict(service='standard',cents=2730,currency='$')])) )
    assert shipping_summary(saved)=='Standard · $27.30'
    saved['dashboard_qa']['evidence']=dict(shipping=dict(selected='express',options=[dict(service='express',cents=3810,currency='$')]))
    assert shipping_summary(saved)=='Express · $38.10'
    saved['dashboard_qa']['verified']=False
    assert shipping_summary(saved)==''
