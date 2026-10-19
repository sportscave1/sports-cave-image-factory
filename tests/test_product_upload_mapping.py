"""Real isolated PostgreSQL and authoritative registration/mapping; provider I/O simulated."""
from copy import deepcopy
from pathlib import Path
import json
import time
from unittest.mock import Mock
import pytest
from tests.test_product_upload_intake import database, env, product, ADMIN, PID
from tests.test_product_upload_dropbox import selected
from tests.test_product_upload_package import saved_row
from product_upload_mapping import Mapping, read_edition
from product_upload_identity import tag, correlation_prompt
from product_upload_source import current_source

ROOT=Path(__file__).parents[1]
MIGRATION='supabase/migrations/20261019095933_product_upload_mapping_only_hold.sql'


def setup(env, *, correlated=True, limit=200, mode='DRAFT', live_source=False, production_grants=False):
    store,sql,provider=env
    sql.execute((ROOT/'supabase/migrations/20261019070000_product_upload_verified_psd_mapping.sql').read_text(encoding='utf-8'))
    if production_grants:
        sql.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role')
    sql.execute((ROOT/MIGRATION).read_text(encoding='utf-8'))
    from product_upload_dropbox import ROOTS
    row,meta=selected(env, **({'parent':ROOTS['live']} if live_source else {}));key=str(row['id']);receipt=saved_row()['data']
    with store.locked(key,ADMIN['id']) as (row,cur):
        row['mode']=mode
        row['data'].update(mockups_exported=True,mockup_saves=receipt['mockup_saves'],
                           mockups_context={'design_name':'fixture-art','sport':'Motorsport'})
        row['data']['upload_operation']['output']=receipt['upload_operation']['output']
    p=product(tags=([tag(key)] if correlated else [])+([f'sc-edition-limit-{limit}'] if limit else []),
              status='ACTIVE' if mode=='LIVE' else 'DRAFT',online_store_url='https://fixture/products/art' if mode=='LIVE' else '')
    shop=Mock()
    shop.fetch_catalog_page.side_effect=lambda **kw:dict(products=[deepcopy(p)] if correlated else [],has_next_page=False)
    shop.fetch_product_by_shopify_id.side_effect=lambda pid:deepcopy(p) if pid==PID else None
    return Mapping(store.connect,provider,shopify=shop),key,meta,p


def count(sql,table):
    sql.execute('SELECT count(*) AS n FROM '+table);return sql.fetchone()['n']


def test_hold_grants_remain_immutable_with_production_default_privileges(env):
    setup(env, production_grants=True)
    sql=env[1]
    for role in ('anon','authenticated','service_role'):
        for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE'):
            sql.execute("SELECT has_table_privilege(%s,'public.product_upload_mapping_holds',%s) AS allowed", (role,privilege))
            assert sql.fetchone()['allowed'] == (role=='service_role' and privilege in ('SELECT','INSERT'))


def no_jobs(env):
    for table in ('auto_edition_onboarding','auto_edition_jobs','auto_edition_discovery','auto_edition_source_inventory'):
        assert count(env[1],table)==0,table


@pytest.mark.parametrize('mode',['DRAFT','LIVE','UPDATE'])
def test_complete_real_path_from_missing_catalogue_idempotent_no_customer_allocation(env,mode):
    service,key,meta,p=setup(env,mode=mode)
    before=deepcopy(env[0].read(key,ADMIN['id']))
    assert read_edition(env[0].connect,PID) is None
    result=service.map(key,ADMIN)
    assert result['state']=='Mapped',result
    assert result['reason']=='Success — synced and PSD mapped' and result['preparation_held']
    assert result['edition_id'] and result['run_id'] and len(result['completed'])==6
    assert result['psd'].endswith('/03_DESIGNS-LIVE-ONLINE-UPLOADED/New Art.psd')
    saved=env[0].read(key,ADMIN['id'])
    op=saved['data']['upload_operation']
    assert op['source']==meta and saved['data']['source']==meta
    assert op['sync_map']['moved']['id']==meta['id'] and op['sync_map']['moved']['content_hash']==meta['content_hash']
    assert current_source(saved)==current_source(before) # exact WEBP receipt retained
    assert saved['data']['mockups_context']==before['data']['mockups_context']
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert env[2].api.move_path.call_count==1
    for table in ('edition_products','edition_runs','product_psd_mappings','product_upload_mapping_holds'):
        assert count(env[1],table)==1
    edition=read_edition(env[0].connect,PID)
    assert edition['next_edition_number']==1 and edition['sold_count']==0
    assert count(env[1],'edition_orders')==0
    no_jobs(env)
    assert {c[0] for c in service.shopify.method_calls} <= {'fetch_catalog_page','fetch_product_by_shopify_id'}
    assert not env[2].calls # no upload/download/image bytes


def test_already_synced_or_mapped_preserves_history_and_reads_exact_record(env):
    service,key,meta,p=setup(env)
    service.register(p,200)
    env[1].execute('UPDATE edition_products SET next_edition_number=8,sold_count=7,remaining_count=193,last_assigned_edition=7')
    env[1].execute('UPDATE edition_runs SET next_edition_number=8')
    assert service.map(key,ADMIN)['state']=='Mapped'
    env[1].execute('SELECT count(*) AS n FROM product_psd_mapping_audit');n=env[1].fetchone()['n']
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert count(env[1],'product_psd_mapping_audit')==n
    assert read_edition(env[0].connect,PID)['next_edition_number']==8
    no_jobs(env)


def test_preexisting_exact_live_mapping_is_reused_without_moving(env):
    service,key,meta,p=setup(env,mode='UPDATE',live_source=True)
    service.register(p,200)
    env[1].execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual',%s)",
                   (PID,meta['id'],meta['path_display'],ADMIN['id']))
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert not env[2].api.move_path.called
    assert service.mappings.read_one(PID)['file_path']==meta['path_display']
    no_jobs(env)


def test_existing_legacy_companion_handoff_is_not_taken_over(env):
    service,key,meta,p=setup(env)
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        row['data']['lifecycle']={'state':'Queued','expected_source':meta}
    with pytest.raises(ValueError,match='existing Companion handoff'):service.map(key,ADMIN)
    assert not service.shopify.method_calls and not env[2].api.move_path.called


@pytest.mark.parametrize('target',['product','run'])
def test_conflicting_edition_shopify_identifiers_stop_before_move(env,target):
    service,key,meta,p=setup(env)
    service.register(p,200)
    env[1].execute("UPDATE "+('edition_products' if target=='product' else 'edition_runs')+" SET shopify_product_id='gid://shopify/Product/998'")
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    assert not env[2].api.move_path.called


@pytest.mark.parametrize('kind',['none','multiple','saved-id','changed-tag','archived'])
def test_exact_correlation_conflicts_never_guess(env,kind):
    service,key,meta,p=setup(env)
    if kind=='none':service.shopify.fetch_catalog_page.side_effect=lambda **kw:dict(products=[],has_next_page=False)
    if kind=='multiple':service.shopify.fetch_catalog_page.side_effect=lambda **kw:dict(products=[p,dict(p,shopify_product_id='gid://shopify/Product/988')],has_next_page=False)
    if kind=='saved-id':
        with env[0].locked(key,ADMIN['id']) as (row,cur):
            row['data']['upload_operation']['product_id']='gid://shopify/Product/988'
    if kind=='changed-tag':service.shopify.fetch_product_by_shopify_id.side_effect=lambda pid:dict(p,tags=[])
    if kind=='archived':p['status']='ARCHIVED'
    result=service.map(key,ADMIN)
    assert result['state']!='Mapped' and result['reason']
    if kind=='none':assert result['reason']=='Product not found in Shopify yet'
    assert not env[2].api.move_path.called and not read_edition(env[0].connect,PID)
    no_jobs(env)


def test_unknown_edition_choice_resumes_without_recreating_product(env):
    service,key,meta,p=setup(env,limit=None)
    result=service.map(key,ADMIN)
    assert result['needs_limit'] and result['state']=='Pending sync'
    assert read_edition(env[0].connect,PID) is None
    assert service.map(key,ADMIN,confirmed_limit=75)['state']=='Mapped'
    assert read_edition(env[0].connect,PID)['edition_total']==75
    no_jobs(env)


@pytest.mark.parametrize('kind',['revision','destination','mapping','run','history','partial','missing-guards','existing-job'])
def test_conflicts_fail_closed_and_never_move_or_show_green(env,kind):
    service,key,meta,p=setup(env)
    if kind=='revision':env[2].files[meta['id']]['rev']='b2'
    if kind=='destination':
        from product_upload_dropbox import ROOTS
        path=ROOTS['live']+'/New Art.psd';env[2].files[path]=dict(meta,id='id:other',path_display=path)
    if kind=='mapping':
        env[1].execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,'id:other',%s,'manual','fixture')",(PID,meta['path_display'].replace('/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE','')))
    if kind=='run':
        service.register(p,200);env[1].execute("UPDATE edition_runs SET status='archived'")
    if kind=='history':env[1].execute('INSERT INTO edition_orders(shopify_product_gid) VALUES(%s)',(PID,))
    if kind=='partial':
        with env[0].locked(key,ADMIN['id']) as (row,cur):row['data']['mockup_saves']['saved']['receipt']['failures']=['incomplete']
        with pytest.raises(ValueError):service.map(key,ADMIN)
        return
    if kind=='missing-guards':env[1].execute('DROP TRIGGER upload_hold_onboarding ON auto_edition_onboarding')
    if kind=='existing-job':env[1].execute('INSERT INTO auto_edition_onboarding(product_gid,file_id) VALUES(%s,%s)',(PID,meta['id']))
    result=service.map(key,ADMIN)
    assert result['state']!='Mapped',result
    assert not env[2].api.move_path.called
    assert service.status(key,ADMIN)['state']!='Mapped'


@pytest.mark.parametrize('loss',['move-ack','map-failure','map-ack'])
def test_lost_responses_and_partial_success_resume_exact_destination(env,loss):
    service,key,meta,p=setup(env)
    original=env[2].api.move_path.side_effect if loss=='move-ack' else service.mappings.attach
    def fail(*a,**kw):
        if loss!='map-failure':original(*a,**kw)
        raise ConnectionError('isolated lost response')
    if loss=='move-ack':env[2].api.move_path.side_effect=fail
    else:service.mappings.attach=fail
    result=service.map(key,ADMIN)
    assert result['state']=='Mapping failed',result
    saved=env[0].read(key,ADMIN['id'])['data']['upload_operation']['sync_map']
    assert saved['move_intent'] and env[2].files[meta['id']]['path_display']==saved['move_intent']['to']
    if loss=='move-ack':env[2].api.move_path.side_effect=original
    else:service.mappings.attach=original
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert env[2].api.move_path.call_count==1
    assert count(env[1],'edition_runs')==1 and count(env[1],'product_psd_mappings')==1
    no_jobs(env)


def test_double_click_during_lookup_uses_one_durable_attempt(env):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    service,key,meta,p=setup(env)
    entered,release=threading.Event(),threading.Event()
    def lookup(**kw):
        entered.set();assert release.wait(8)
        return dict(products=[p],has_next_page=False)
    service.shopify.fetch_catalog_page.side_effect=lookup
    with ThreadPoolExecutor() as pool:
        first=pool.submit(service.map,key,ADMIN);assert entered.wait(8)
        try:assert service.map(key,ADMIN)['state']=='Mapping…'
        finally:release.set()
        assert first.result()['state']=='Mapped'
    assert env[2].api.move_path.call_count==1
    no_jobs(env)


def test_status_polling_never_contacts_providers_and_stale_save_never_green(env):
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    service.shopify=Mock(side_effect=AssertionError('no provider calls'))
    service.provider=None
    assert service.status(key,ADMIN)['state']=='Mapped'
    assert not service.shopify.method_calls
    from product_upload_source import invalidate
    with env[0].locked(key,ADMIN['id']) as (row,cur):invalidate(row)
    assert service.status(key,ADMIN)['state']=='Status unavailable'


def test_background_discovery_queue_and_older_direct_sql_cannot_admit_held_source(env,monkeypatch):
    from auto_editions_discovery import Discovery,register
    from auto_editions_onboarding_store import Queue
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    moved=env[2].files[meta['id']]
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true')
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true')
    discovery=Discovery(env[0].connect);sql=env[1]
    with env[0].connect() as conn,conn.cursor() as cur:register(cur,[p],'fixture')
    token=discovery.claim()['lease_token']
    discovery.page(token,dict(entries=[moved],cursor='fixture',has_more=False))
    discovery.seed_existing();Queue(env[0].connect).enqueue(PID,meta['id'],'fixture')
    # Database guards protect old deployed callers and direct SQL admission too.
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) VALUES(%s,%s,9)",(PID,meta['id']))
    sql.execute("INSERT INTO auto_edition_discovery(product_gid,event_id) VALUES(%s,'old-worker')",(PID,))
    sql.execute("INSERT INTO auto_edition_source_inventory(file_id,name_key,path_lower,metadata) VALUES(%s,'newart',%s,%s::jsonb)",(meta['id'],moved['path_display'].lower(),json.dumps(moved)))
    payload=dict(identity=dict(source=dict(product_gid=PID,file_id=meta['id'])))
    sql.execute("INSERT INTO auto_edition_jobs(id,payload,actor_id) VALUES(%s,%s::jsonb,'fixture')",('a'*64,json.dumps(payload)))
    with pytest.raises(RuntimeError,match='held for verified'):
        sql.execute("UPDATE product_psd_mappings SET source='automatic' WHERE shopify_product_gid=%s",(PID,))
    no_jobs(env)
    assert service.status(key,ADMIN)['state']=='Mapped'
    # Unrelated work still admits normally.
    other='gid://shopify/Product/988'
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id) VALUES(%s,'id:unrelated')",(other,))
    assert count(sql,'auto_edition_onboarding')==1


def test_late_source_change_and_run_replacement_after_move_rejected(env):
    service,key,meta,p=setup(env)
    original=service.mappings.attach
    def corrupt(*a,**kw):
        original(*a,**kw);env[2].files[meta['id']]['rev']='b2'
    service.mappings.attach=corrupt
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    assert service.status(key,ADMIN)['state']!='Mapped'
    no_jobs(env)


def test_prompt_identity_and_catalogue_registration_policy_preserved():
    import uuid
    import supabase_backend as db
    row=saved_row();text=correlation_prompt(row)
    assert text.count(tag(row['id']))==1 and 'initial create call' in text
    p=product(status='ACTIVE',online_store_url='https://fixture/art',tags=[tag(uuid.uuid4())])
    assert db._plan_edition_product_incremental_sync([p],[])[0]['reason']=='awaiting_upload_mapping'
    assert db._plan_edition_product_incremental_sync([p],[],upload_mapping=True)[0]['action']=='insert'


def test_api_starts_background_once_and_status_is_metadata_only(env,monkeypatch):
    import threading
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api, product_upload_mapping as module, files_upload_api as files
    from product_upload_jobs import JOBS
    service,key,meta,p=setup(env)
    monkeypatch.setattr(api,'connect',env[0].connect)
    factory=Mock(return_value=env[2]);monkeypatch.setattr(api,'Dropbox',factory)
    monkeypatch.setattr(module,'Mapping',lambda *a,**kw:service)
    monkeypatch.setattr(files,'_request_user',lambda *a,**kw:ADMIN)
    entered,release=threading.Event(),threading.Event()
    original=service.shopify.fetch_catalog_page.side_effect
    def lookup(**kw):
        entered.set();assert release.wait(10);return original(**kw)
    service.shopify.fetch_catalog_page.side_effect=lookup
    version=current_source(env[0].read(key,ADMIN['id']))['version']
    with TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])) as client:
        url='/api/product-uploads/';headers={'Origin':'http://testserver'}
        assert client.get(url+'state?id='+key).status_code==200
        assert client.get(url+'mapping-status?id='+key).json()['mapping']['state']=='Unmapped'
        factory.assert_not_called();assert not service.shopify.method_calls
        assert client.post(url+'map',json={'id':key,'source_version':version}).status_code==403
        assert client.post(url+'map',json={'id':key},headers=headers).status_code==409
        payload={'id':key,'source_version':version}
        try:
            start=time.monotonic()
            assert client.post(url+'map',json=payload,headers=headers).status_code==200
            assert time.monotonic()-start<2 and entered.wait(5)
            assert client.post(url+'map',json=payload,headers=headers).status_code==200
            assert factory.call_count==1
            assert client.get(url+'mapping-status?id='+key).json()['mapping']['state']=='Mapping…'
            # Starting another upload must not cancel an already admitted mapping.
            JOBS.cancel(key,ADMIN['id'])
        finally:release.set()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=client.get(url+'mapping-status?id='+key).json()['mapping']
            if result['state']!='Mapping…':break
            time.sleep(.02)
        assert result['state']=='Mapped',result
        assert env[2].api.move_path.call_count==1
        no_jobs(env)


def test_other_operation_cannot_take_hold_and_changed_run_cannot_reuse_success(env):
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    from product_upload_mapping_hold import acquire
    import uuid
    with pytest.raises(ValueError,match='Another upload'):
        acquire(env[0].connect,str(uuid.uuid4()),ADMIN['id'],PID,meta['id'])
    env[1].execute('UPDATE edition_products SET active_edition_run_id=NULL')
    assert service.status(key,ADMIN)['state']!='Mapped'
    assert service.map(key,ADMIN)['state']!='Mapped'


def test_expired_attempt_and_late_owner_are_fenced(env):
    from datetime import timedelta
    from product_upload_mapping import now
    service,key,meta,p=setup(env)
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        row['data']['upload_operation']['sync_map']=dict(state='Mapping…',lease='expired',
            lease_until=(now()-timedelta(minutes=1)).isoformat(),source_version=current_source(row)['version'],mode='DRAFT')
    assert service.status(key,ADMIN)['state']=='Pending sync'
    assert service.map(key,ADMIN)['state']=='Mapped'
    with pytest.raises(ValueError,match='Another attempt'):
        with service._guard(key,ADMIN,'expired'):raise AssertionError('Stale attempt must not mutate')
    assert env[2].api.move_path.call_count==1
