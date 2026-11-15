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


@pytest.fixture(autouse=True)
def restore_provider_boundaries(monkeypatch):
    monkeypatch.setenv('SHOPIFY_STORE_DOMAIN','fixture.myshopify.com')
    import shopify_sync, product_sport_tag_sync
    for module,name in ((shopify_sync,'fetch_product_by_shopify_id'),(shopify_sync,'graphql_request'),(product_sport_tag_sync,'sync_product_sport_tags')):
        monkeypatch.setattr(module,name,getattr(module,name))


def setup(env, *, correlated=True, limit=200, mode='LIVE', live_source=False, production_grants=False, arrived=True):
    store,sql,provider=env
    sql.execute((ROOT/'supabase/migrations/20261019070000_product_upload_verified_psd_mapping.sql').read_text(encoding='utf-8'))
    if production_grants:
        sql.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role')
    sql.execute((ROOT/MIGRATION).read_text(encoding='utf-8'))
    sql.execute((ROOT/'supabase/migrations/20261019221742_product_upload_coordinated_mapping.sql').read_text())
    sql.execute("""CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz);
    CREATE TABLE IF NOT EXISTS webhook_events(webhook_id text PRIMARY KEY,topic text,status text,shop_domain text,source text,payload jsonb,
      received_at timestamptz,processed_at timestamptz,error_message text,inserted_count int,skipped_count int,
      affected_handles_count int,processing_elapsed_ms int,new_order_inserted bool,shopify_order_id text,shopify_order_name text);""")
    from product_upload_dropbox import ROOTS
    row,meta=selected(env, **({'parent':ROOTS['live']} if live_source else {}));key=str(row['id']);receipt=saved_row()['data']
    with store.locked(key,ADMIN['id']) as (row,cur):
        row['mode']=mode
        row['data'].update(mockups_exported=True,mockup_saves=receipt['mockup_saves'],
                           mockups_context={'design_name':'fixture-art','sport':'Motorsport'})
        row['data']['upload_operation']['output']=receipt['upload_operation']['output']
    p=product(tags=([tag(key)] if correlated else [])+([f'sc-edition-limit-{limit}'] if limit else []),
              status='DRAFT' if mode=='DRAFT' else 'ACTIVE',online_store_url='' if mode=='DRAFT' else 'https://fixture/products/art',created_at='2026-10-19T09:28:59Z')
    shop=Mock()
    shop.fetch_catalog_page.side_effect=AssertionError('MAP must not search Shopify')
    shop.fetch_product_by_shopify_id.side_effect=AssertionError('MAP must not fetch Shopify')
    import supabase_backend as db
    import shopify_product_onboarding as onboarding
    db.shopify_sync.fetch_product_by_shopify_id=lambda *a,**kw:deepcopy(p)
    db.shopify_sync.graphql_request=lambda *a,**kw:({'orders':{'nodes':[],'pageInfo':{'hasNextPage':False}}},'2026-04')
    import product_sport_tag_sync
    product_sport_tag_sync.sync_product_sport_tags=lambda *a,**kw:dict(status='verified',review=[])
    service=Mapping(store.connect,provider,shopify=shop,shop_domain='fixture.myshopify.com',onboard=Mock(side_effect=AssertionError('MAP must not sync')))
    if arrived and limit:service.register(p,limit)  # Simulate completed webhook registration before MAP.
    return service,key,meta,p


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
    for table in ('auto_edition_jobs','auto_edition_discovery','auto_edition_source_inventory'):
        assert count(env[1],table)==0,table


@pytest.mark.parametrize('mode',['LIVE','UPDATE'])
def test_webhook_synced_product_direct_finalisation_idempotent_no_customer_allocation(env,mode):
    service,key,meta,p=setup(env,mode=mode)
    before=deepcopy(env[0].read(key,ADMIN['id']))
    assert read_edition(env[0].connect,PID) is not None
    result=service.map(key,ADMIN)
    assert result['state']=='Mapped',result
    assert result['reason']=='Success â€” PSD mapped' and not result['preparation_held']
    assert result['edition_id'] and result['run_id'] and len(result['completed'])==5
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
    assert not service.shopify.method_calls
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
    assert count(env[1],'auto_edition_onboarding')==0
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


@pytest.mark.parametrize('kind',['none','multiple','saved-id','changed-tag'])
def test_exact_correlation_conflicts_never_guess(env,kind):
    service,key,meta,p=setup(env, correlated=kind not in ('none','changed-tag'))
    if kind=='multiple':service.register(dict(p,shopify_product_id='gid://shopify/Product/988',legacy_resource_id='988',handle='other',title='Other Art'),200)
    if kind=='saved-id':
        with env[0].locked(key,ADMIN['id']) as (row,cur):
            row['data']['upload_operation']['product_id']='gid://shopify/Product/988'
    result=service.map(key,ADMIN)
    assert result['state']!='Mapped' and result['reason']
    if kind=='none':assert result['reason'].startswith('Waiting for product in Edition Ops') and result['needs_product']
    assert not env[2].api.move_path.called and not service.shopify.method_calls
    no_jobs(env)


def test_unknown_edition_choice_resumes_without_recreating_product(env):
    service,key,meta,p=setup(env,limit=None)
    result=service.map(key,ADMIN)
    assert 'Waiting for product in Edition Ops' in result['reason'] and result['state']=='Waiting for product in Edition Ops'
    service.onboard.assert_not_called()
    assert count(env[1],'webhook_events')==0
    assert read_edition(env[0].connect,PID) is None
    p['tags'].append('sc-edition-limit-75')
    service.register(p,75)  # The webhook arrives between explicit retries.
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert read_edition(env[0].connect,PID)['edition_total']==75
    no_jobs(env)


@pytest.mark.parametrize('kind',['revision','destination','mapping','run','history','partial','missing-guards','existing-job'])
def test_conflicts_fail_closed_and_never_move_or_show_green(env,kind):
    service,key,meta,p=setup(env,arrived=kind!='history')
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
    original=service._local_candidates
    def lookup(marker):
        entered.set();assert release.wait(8)
        return original(marker)
    service._local_candidates=lookup
    with ThreadPoolExecutor() as pool:
        first=pool.submit(service.map,key,ADMIN);assert entered.wait(8)
        try:assert service.map(key,ADMIN)['state']=='Mappingâ€¦'
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


def test_background_queue_rejected_until_finalisation_then_admitted_once(env):
    from auto_editions_onboarding_store import Queue
    service,key,meta,p=setup(env)
    original=service._verify_database
    def fail_after_attach(*a,**kw):
        raise ConnectionError('finalisation not committed')
    service._verify_database=fail_after_attach
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    Queue(env[0].connect).enqueue(PID,meta['id'],'fixture')
    env[1].execute("INSERT INTO auto_edition_onboarding(product_gid,file_id) VALUES(%s,%s)",(PID,meta['id']))
    assert count(env[1],'auto_edition_onboarding')==0
    assert not service.mappings.read_one(PID)['verified']
    service._verify_database=original
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert service.mappings.read_one(PID)['verified']
    Queue(env[0].connect).enqueue(PID,meta['id'],'fixture')
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert count(env[1],'auto_edition_onboarding')==1
    env[1].execute('SELECT source FROM auto_edition_onboarding')
    assert env[1].fetchone()['source']['file_id']==meta['id']
    assert env[2].api.move_path.call_count==1
    no_jobs(env)


@pytest.mark.parametrize('change',['source','run','inactive'])
def test_late_source_change_and_run_replacement_after_move_rejected(env,change):
    service,key,meta,p=setup(env)
    original=service.mappings.attach
    def corrupt(*a,**kw):
        original(*a,**kw)
        if change=='source':env[2].files[meta['id']]['rev']='b2'
        elif change=='run':env[1].execute("UPDATE edition_runs SET status='archived'")
        else:env[1].execute('UPDATE edition_products SET active=false')
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
    assert db._plan_edition_product_incremental_sync([p],[])[0]['action']=='insert'
    assert db._plan_edition_product_incremental_sync([p],[],upload_mapping=True)[0]['action']=='insert'


def test_api_mapping_only_navigates_and_never_starts_worker(env,monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api, files_upload_api as files
    from product_upload_jobs import JOBS
    service,key,meta,p=setup(env)
    monkeypatch.setattr(api,'connect',env[0].connect)
    factory=Mock(side_effect=AssertionError('Mapping must not access Dropbox'))
    monkeypatch.setattr(api,'Dropbox',factory)
    monkeypatch.setattr(files,'_request_user',lambda *a,**kw:ADMIN)
    submit=Mock(side_effect=AssertionError('Mapping must not start a worker'))
    monkeypatch.setattr(JOBS,'submit',submit)
    # setup() simulates an imported product and saved correlation tag.
    with TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])) as client:
        url='/api/product-uploads/';headers={'Origin':'http://testserver'}
        before=read_edition(service.connect,PID)
        assert client.post(url+'map',json={'id':key}).status_code==403
        for response in (client.get(url+'mapping-status?id='+key),
                         client.post(url+'map',json={'id':key},headers=headers)):
            assert response.status_code==200,response.text
            result=response.json()['mapping']
            assert 'page=edition_ops' in result['url']
            assert result['state']=='Available in Edition Ops'
        assert read_edition(service.connect,PID)==before
        factory.assert_not_called();submit.assert_not_called()
        assert count(env[1],'product_upload_mapping_holds')==0
        assert count(env[1],'product_psd_mappings')==0
        env[1].execute('DELETE FROM edition_products')
        result=client.get(url+'mapping-status?id='+key).json()['mapping']
        assert result['state']=='Pending / not found in Edition Ops'
        assert 'No PSD was attached' in result['reason']


def test_other_operation_cannot_take_hold_and_changed_run_cannot_reuse_success(env):
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    from product_upload_mapping_hold import acquire
    import uuid
    with pytest.raises(ValueError,match='earlier saved mapping attempt') as conflict:
        acquire(env[0].connect,str(uuid.uuid4()),ADMIN['id'],PID,meta['id'])
    assert conflict.value.resume_upload_id==key
    env[1].execute('UPDATE edition_products SET active_edition_run_id=NULL')
    assert service.status(key,ADMIN)['state']!='Mapped'
    with pytest.raises(ValueError,match='replacement workflow'):service.map(key,ADMIN)


def test_expired_attempt_and_late_owner_are_fenced(env):
    from datetime import timedelta
    from product_upload_mapping import now
    service,key,meta,p=setup(env)
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        row['data']['upload_operation']['sync_map']=dict(state='Mappingâ€¦',lease='expired',
            lease_until=(now()-timedelta(minutes=1)).isoformat(),source_version=current_source(row)['version'],mode='LIVE')
    assert service.status(key,ADMIN)['state']=='Mapping incomplete'
    assert service.map(key,ADMIN)['state']=='Mapped'
    with pytest.raises(ValueError,match='Another attempt'):
        with service._guard(key,ADMIN,'expired'):raise AssertionError('Stale attempt must not mutate')
    assert env[2].api.move_path.call_count==1


def test_ambiguous_correlation_requires_explicit_selector_confirmation(env):
    service,key,meta,p=setup(env)
    service.register(dict(p,shopify_product_id='gid://shopify/Product/988',legacy_resource_id='988',handle='other',title='Other Art'),200)
    result=service.map(key,ADMIN)
    assert result['needs_product'] and len(result['candidates'])==2
    assert not env[2].api.move_path.called
    assert service.map(key,ADMIN,product_id=PID)['state']!='Mapped'
    assert service.map(key,ADMIN,product_id=PID,confirm_product=True)['state']=='Mapped'
    op=env[0].read(key,ADMIN['id'])['data']['upload_operation']
    assert op['publication_binding']['product_id']==PID and op['publication_binding']['source']==meta


def test_saved_publication_id_avoids_search_and_onboarded_run_avoids_enqueue(env):
    service,key,meta,p=setup(env)
    service.register(p,200)
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        row['data']['upload_operation'].update(product_id=PID,binding='operator',shop_domain='fixture.myshopify.com')
    service.shopify.fetch_catalog_page.side_effect=AssertionError('No search when publication ID exists')
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert count(env[1],'webhook_events')==0


def test_move_failure_is_retryable_and_never_ready(env):
    service,key,meta,p=setup(env)
    original=env[2].api.move_path.side_effect
    env[2].api.move_path.side_effect=ConnectionError('Storage unavailable')
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    assert count(env[1],'product_psd_mappings')==0 and count(env[1],'auto_edition_onboarding')==0
    assert env[2].files[meta['id']]['path_display']==meta['path_display']
    env[2].api.move_path.side_effect=original
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert count(env[1],'product_psd_mappings')==1 and count(env[1],'auto_edition_onboarding')==1


def test_explicit_replacement_workflow_remains_available_after_mapping(env):
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    before=read_edition(env[0].connect,PID)
    replacement=dict(env[2].files[meta['id']],id='id:replacement',rev='new-revision')
    service.mappings.attach(PID,replacement,ADMIN,expected_file_id=meta['id'],confirm_replace=True,confirm_mismatch=True)
    assert service.mappings.read_one(PID)['dropbox_file_id']=='id:replacement'
    assert read_edition(env[0].connect,PID)==before
    env[1].execute('SELECT file_id FROM auto_edition_onboarding')
    assert env[1].fetchone()['file_id']=='id:replacement'
    assert service.status(key,ADMIN)['state']!='Mapped'


def test_identical_existing_prepared_mapping_reuses_without_reprocessing(env):
    import auto_editions as ae
    service,key,meta,p=setup(env,mode='UPDATE',live_source=True)
    service.register(p,200)
    env[1].execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual',%s)",(PID,meta['id'],meta['path_display'],ADMIN['id']))
    env[1].execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,source) VALUES(%s,%s,'Cloud Ready',%s::jsonb)",(PID,meta['id'],json.dumps(ae.source_identity(PID,meta))))
    env[1].execute('SELECT * FROM auto_edition_onboarding');before=env[1].fetchall()
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert not env[2].api.move_path.called
    env[1].execute('SELECT * FROM auto_edition_onboarding');assert env[1].fetchall()==before
    assert count(env[1],'product_upload_mapping_holds')==0


def test_finalisation_transaction_failure_rolls_back_readiness_and_queue(env):
    service,key,meta,p=setup(env)
    original=service.mappings._audit
    def fail(cur,pid,action,actor,before,after):
        if after.get('ready'):raise ConnectionError('Commit unavailable after queue admission')
        return original(cur,pid,action,actor,before,after)
    service.mappings._audit=fail
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    assert count(env[1],'product_psd_mappings')==1
    assert count(env[1],'auto_edition_onboarding')==0
    assert not service.mappings.read_one(PID)['verified']
    service.mappings._audit=original
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert count(env[1],'auto_edition_onboarding')==1
    assert env[2].api.move_path.call_count==1


def test_verified_saved_identity_survives_removal_of_mutable_correlation_tag(env):
    service,key,meta,p=setup(env)
    original=env[2].api.move_path.side_effect
    env[2].api.move_path.side_effect=ConnectionError('Temporary storage outage')
    assert service.map(key,ADMIN)['state']=='Mapping failed'
    p['tags']=[t for t in p['tags'] if not t.startswith('sc-upload-')]
    service.shopify.fetch_catalog_page.side_effect=AssertionError('Persisted publication ID is authoritative')
    env[2].api.move_path.side_effect=original
    assert service.map(key,ADMIN)['state']=='Mapped'


def test_edition_ops_display_name_used_for_move_not_edition_label(env):
    service,key,meta,p=setup(env)
    env[1].execute("UPDATE edition_products SET product_title=%s,edition_name='Numbered Edition'", ('CON: Hero / Star?.PSD',))
    before=read_edition(env[0].connect,PID)
    result=service.map(key,ADMIN)
    assert result['state']=='Mapped',result
    assert result['psd'].endswith('/CON_ Hero _ Star_.psd')
    assert read_edition(env[0].connect,PID)==before
    assert service.mappings.read_one(PID)['dropbox_file_id']==meta['id']
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert env[2].api.move_path.call_count==1
    service.onboard.assert_not_called()
    assert count(env[1],'webhook_events')==0


def test_not_found_lookup_retry_does_not_move_or_sync(env):
    service,key,meta,p=setup(env,arrived=False)
    result=service.map(key,ADMIN)
    assert result['state']=='Waiting for product in Edition Ops' and result['needs_product']
    assert not env[2].api.move_path.called
    service.register(p,200)
    result=service.map(key,ADMIN)
    assert result['state']=='Mapped',result
    assert 'Syncing Edition Ops' not in result['completed']
    assert 'Checking edition setup' not in result['completed']
    service.onboard.assert_not_called()


@pytest.mark.parametrize('status',['DRAFT','ARCHIVED','ACTIVE'])
def test_saved_local_id_needs_no_fresh_tag_or_publication_filter(env,status):
    service,key,meta,p=setup(env,correlated=False)
    env[1].execute("UPDATE edition_products SET raw=jsonb_build_object('status',%s::text)",(status,))
    env[1].execute("DELETE FROM shopify_products")
    with env[0].locked(key,ADMIN['id']) as (row,cur):
        row['data']['upload_operation']['product_id']=PID
    before=read_edition(env[0].connect,PID)
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert read_edition(env[0].connect,PID)==before
    assert not service.shopify.method_calls
    service.onboard.assert_not_called()
    assert count(env[1],'edition_runs')==1 and count(env[1],'webhook_events')==0


def test_new_operation_reuses_authoritative_psd_link_without_new_tag(env):
    import uuid
    from product_upload_dropbox import select
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    prior=env[0].read(key,ADMIN['id'])
    moved=env[2].metadata_if_present(meta['id'])
    new_key=str(uuid.uuid4())
    select(env[0].connect,env[2],new_key,ADMIN['id'],'UPDATE',moved['id'],moved['rev'])
    with env[0].locked(new_key,ADMIN['id']) as (row,cur):
        row['data'].update(mockups_exported=True,mockup_saves=deepcopy(prior['data']['mockup_saves']))
        row['data']['upload_operation']['output']=deepcopy(prior['data']['upload_operation']['output'])
    before=read_edition(env[0].connect,PID)
    result=service.map(new_key,ADMIN)
    assert result['state']=='Mapped',result
    assert env[2].api.move_path.call_count==1
    assert read_edition(env[0].connect,PID)==before
    assert count(env[1],'product_psd_mappings')==1
    assert not service.shopify.method_calls


def test_local_cached_string_tag_and_same_title_not_identity(env):
    service,key,meta,p=setup(env,correlated=False)
    assert service.map(key,ADMIN)['state']=='Waiting for product in Edition Ops'
    env[1].execute("UPDATE shopify_products SET raw_json=jsonb_build_object('tags',%s::text)",('other, '+tag(key)+', final',))
    assert service.map(key,ADMIN)['state']=='Mapped'
    assert not service.shopify.method_calls
