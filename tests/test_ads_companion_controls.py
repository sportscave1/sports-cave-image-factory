from uuid import uuid4
from unittest.mock import Mock
import json
import pytest
import ads_companion_controls as controls
import ads_companion_quick_add as quick
import ads_companion_queue as queue
import design_publish_ad as ads
import product_upload_staff_queue as uploads
from test_ads_companion_queue import queued_store,store,database,brief,ROW,USER,no_provider_network


def job():return queue.enqueue(USER,brief(),{'row':ROW})['id']


def test_cancel_stops_worker_and_delete_hides_without_losing_files(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda user:user==USER)
    token=uploads.pair(USER);key=job()
    controls.action(USER,key,'cancel')
    assert controls.stopped(key)
    assert ads.dashboard()['jobs'][0]['stage']=='cancelled'
    assert not ads.dashboard()['jobs'][0]['active']
    assert ads.tick(token,{'id':key})=={'stop':{'id':key}}
    assert ads.tick(token,{})=={}
    controls.action(USER,key,'delete')
    assert ads.dashboard()['jobs']==[]
    with queued_store() as conn,conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+key,))
        assert cur.fetchone()['value']['result']['master_prompt']
    with pytest.raises(PermissionError):controls.action({'id':'other'},key,'play')


def test_play_resumes_saved_chat_and_receipts_never_regenerates(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);key=job()
    with queued_store() as conn,conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+key,));value=cur.fetchone()['value']
    value.update(stage='failed',folder='/fixture',chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+str(uuid4()),artifacts={'ad_copy.csv':{'hash':'kept'}})
    ads.write(ads.PREFIX+key,value)
    controls.action(USER,key,'cancel');controls.action(USER,key,'play')
    with queued_store() as conn,conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+key,));saved=cur.fetchone()['value']
    assert saved['stage']=='generating' and saved['collect_only']
    assert saved['resume_token'] and saved['chat_url']==value['chat_url'] and saved['artifacts']==value['artifacts']
    assert not controls.stopped(key)
    saved.update(stage='failed',posting_id=str(uuid4()));ads.write(ads.PREFIX+key,saved)
    controls.action(USER,key,'play')
    assert ads.dashboard()['jobs'][0]['stage']=='posting'
    assert ads.dashboard()['jobs'][0]['posting_id']==saved['posting_id']


def test_quick_add_uses_ads_defaults_and_deduplicates_retry(queued_store,monkeypatch):
    import ads_page
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    monkeypatch.setattr(ads_page,'load_edition_ops_product_rows',lambda:[ROW])
    quick._RECORDS.invalidate()
    loader=Mock(return_value=[ROW]);monkeypatch.setattr(ads_page,'load_edition_ops_product_rows',loader)
    data=quick.catalog(USER);product=data['products'][0]
    assert product['sport']=='Baseball' and product['country']=='USA'
    body=dict(product=product['id'],sport=product['sport'],country='Canada',type='Instant Experience',request_id=str(uuid4()))
    first=quick.enqueue(USER,body);second=quick.enqueue(USER,body)
    assert first['id']==second['id']
    assert loader.call_count==1
    assert len(ads.dashboard()['jobs'])==1
    assert ads.dashboard()['jobs'][0]['country']=='Canada'
    third=quick.enqueue(USER,{**body,'request_id':str(uuid4())})
    assert third['id']!=first['id']
    assert len(ads.dashboard()['jobs'])==2
    with pytest.raises(ValueError):quick.enqueue(USER,{**body,'type':'Carousel'})
    with pytest.raises(ValueError):quick.enqueue(USER,{**body,'country':'UK'})


def test_cancel_during_lease_survives_worker_write_and_blocks_submission(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);key=job()
    with queued_store() as conn,conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+key,));value=cur.fetchone()['value']
        cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(ads.PREFIX+'lease',json.dumps('worker')))
    controls.action(USER,key,'cancel')
    value['stage']='generating';ads.write(ads.PREFIX+key,value)
    assert controls.stopped(key)
    with pytest.raises(ValueError,match='finishing'):controls.action(USER,key,'play')
    monkeypatch.setattr(ads,'_post_request',lambda value:object())
    assert ads._step(ads.PREFIX+key,value,{}, {},0)=={}


def test_new_routes_require_admin_and_same_origin(monkeypatch):
    import files_upload_api
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    actor={'id':'fixture'}
    monkeypatch.setattr(files_upload_api,'_request_user',lambda *args,**kw:actor)
    monkeypatch.setattr(uploads,'can_control_queues',lambda user:bool(user.get('admin')))
    monkeypatch.setattr(quick,'catalog',lambda *args,**kwargs:{'products':[]})
    client=TestClient(Starlette(routes=[Route(path,endpoint,methods=methods) for path,endpoint,methods in uploads.ROUTES]))
    base='/api/staff-product-uploads/'
    assert client.get(base+'ad-quick-add').status_code==403
    assert client.post(base+'ad-control',json={'id':str(uuid4()),'action':'cancel'},headers={'origin':'http://testserver'}).status_code==403
    actor['admin']=True
    assert client.get(base+'ad-quick-add').status_code==200
    for endpoint in ('ad-quick-add','ad-control'):
        assert client.post(base+endpoint,json={}).status_code==403
        assert client.post(base+endpoint,json={},headers={'origin':'https://untrusted.test'}).status_code==403


def test_deleted_job_cannot_be_restored_by_late_cancel_or_play(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);key=job()
    assert controls.action(USER,key,'delete')['job'] is None
    assert controls.action(USER,key,'cancel')['action']=='delete'
    assert controls.action(USER,key,'delete')['action']=='delete'
    with pytest.raises(ValueError,match='removed'):
        controls.action(USER,key,'play')
    assert ads.dashboard()['jobs']==[]


def test_control_returns_exact_receipt_and_cached_status_can_confirm_it(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);first=job()
    second=queue.enqueue(USER,brief(),{'row':ROW},request_key=str(uuid4()))['id']
    receipt=controls.action(USER,first,'cancel')['job']
    assert receipt['id']==first and receipt['stage']=='cancelled'
    assert receipt['control_action']=='cancel' and not receipt['can_cancel']
    assert [r['id'] for r in ads.dashboard(job_id=second)['jobs']]==[second]


def test_product_records_empty_retry_refresh_and_account_scope(monkeypatch):
    import ads_page
    quick._RECORDS.invalidate()
    loader=Mock(side_effect=[[],[ROW],[ROW],[ROW]])
    monkeypatch.setattr(ads_page,'load_edition_ops_product_rows',loader)
    assert not quick.catalog(USER)['products']
    data=quick.catalog(USER)
    assert data['products'] and loader.call_count==2
    data['products'][0]['name']='changed by client'
    assert quick.catalog(USER)['products'][0]['name']!='changed by client'
    assert loader.call_count==2
    quick.catalog(USER,refresh=True)
    assert loader.call_count==3
    quick.catalog({**USER,'session_version':2})
    assert loader.call_count==4


def test_committed_stop_is_success_even_if_status_receipt_read_fails(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);key=job()
    def unavailable(**kwargs):raise RuntimeError('Synthetic status read outage')
    monkeypatch.setattr(ads,'dashboard',unavailable)
    assert controls.action(USER,key,'cancel')==dict(id=key,action='cancel',job=None)
    assert controls.stopped(key)
    assert controls.action(USER,key,'delete')==dict(id=key,action='delete',job=None)


def test_transient_catalog_database_error_is_not_cached(monkeypatch):
    from unittest.mock import MagicMock
    import ads_product_catalog as catalog
    import supabase_backend
    conn=MagicMock();conn.__enter__.return_value=conn
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value=[ROW]
    connect=Mock(side_effect=[OSError('Synthetic transient read failure'),conn])
    monkeypatch.setattr(supabase_backend,'is_configured',lambda:True)
    monkeypatch.setattr(supabase_backend,'connect',connect)
    catalog.load_live_edition_product_rows.clear()
    try:
        assert catalog.load_live_edition_product_rows()==[]
        assert catalog.load_live_edition_product_rows()==[ROW]
        assert catalog.load_live_edition_product_rows()==[ROW]
        assert connect.call_count==2
    finally:catalog.load_live_edition_product_rows.clear()


def test_late_stop_keeps_completed_posting_receipt_truthful(queued_store,monkeypatch):
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    uploads.pair(USER);key=job()
    with queued_store() as conn,conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+key,))
        value=cur.fetchone()['value']
    value.update(stage='complete',posting_id=str(uuid4()))
    ads.write(ads.PREFIX+key,value)
    receipt=controls.action(USER,key,'cancel')['job']
    assert receipt['stage']=='complete' and receipt['posting_id']==value['posting_id']
    assert not controls.stopped(key)
