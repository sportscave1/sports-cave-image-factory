"""Synthetic Shopify/Dropbox identities against a disposable SQL engine only."""
import json
import os
import uuid
from pathlib import Path
from unittest.mock import Mock,patch

import pytest
import auto_editions_discovery as discovery
import psd_directory as psd
from psd_mapping_store import PostgresMappings
from tests.test_auto_editions_jobs import database as pglite_database

PID='gid://shopify/Product/987'
ROOT=Path(__file__).parents[1]


@pytest.fixture
def database(request):
    """Optional native PostgreSQL, restricted to this task's synthetic cluster."""
    port=os.getenv('AUTO_EDITIONS_NATIVE_TEST_PORT')
    if not port:return request.getfixturevalue('pglite_database')
    import psycopg
    from psycopg.rows import dict_row
    from auto_editions_jobs import Jobs
    assert port.isdigit()
    configuration=dict(host='127.0.0.1',port=int(port),user='postgres',row_factory=dict_row,connect_timeout=5)
    name='v15_test_'+uuid.uuid4().hex
    with psycopg.connect(dbname='postgres',autocommit=True,**configuration) as admin:
        with admin.cursor() as cur:
            cur.execute("SELECT current_setting('data_directory') AS path,current_setting('listen_addresses') AS address")
            identity=cur.fetchone()
            assert Path(identity['path']).resolve()==(ROOT/'output/v15-native/data').resolve()
            assert identity['address']=='127.0.0.1'
            cur.execute('CREATE DATABASE '+name)
    connect=lambda:psycopg.connect(dbname=name,**configuration)
    conn=psycopg.connect(dbname=name,autocommit=True,**configuration);sql=conn.cursor()
    sql.execute((ROOT/'migrations/20261014004209_auto_editions_v6.sql').read_text())
    request.addfinalizer(lambda:cleanup())
    def cleanup():
        sql.close();conn.close()
        with psycopg.connect(dbname='postgres',autocommit=True,**configuration) as admin:
            admin.execute('DROP DATABASE '+name)
    return Jobs(connect),sql


def asset(**changes):
    return {'.tag':'file','id':'id:original','rev':'a1','content_hash':'a'*64,
            'name':'New Art.psd','path_display':psd.ROOT+'/New Art.psd','size':123,**changes}


@pytest.fixture
def store(database,monkeypatch):
    jobs,sql=database
    for filename in ('scripts/sql/product_psd_mapping.sql',
                     'supabase/migrations/20261014053326_auto_editions_onboarding.sql',
                     'supabase/migrations/20261014234210_auto_editions_v15_discovery.sql'):
        schema='\n'.join(line for line in (ROOT/filename).read_text().splitlines() if not line.lstrip().startswith('--'))
        for statement in schema.split(';'):
            if statement.strip():sql.execute(statement)
    sql.execute('''CREATE TABLE edition_products(shopify_product_gid text,shopify_product_id text,
                product_title text,shopify_handle text,edition_total int,next_edition_number int,
                active boolean,is_active boolean)''')
    sql.execute("INSERT INTO edition_products VALUES(%s,'987','New Art','new-art',100,37,true,true)",(PID,))
    sql.execute('CREATE TABLE edition_allocations(id int,product_gid text,number int,owner text)')
    sql.execute("INSERT INTO edition_allocations VALUES(1,%s,36,'synthetic-owner')",(PID,))
    sql.execute("CREATE TABLE synthetic_certificates AS SELECT * FROM edition_allocations")
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true')
    return discovery.Discovery(jobs.connect),sql


def register(store,event='event-1',pid=PID):
    d,sql=store
    with d.connect() as conn,conn.cursor() as cur:
        discovery.register(cur,[{'shopify_product_gid':pid}],event)


def due(sql):
    sql.execute('UPDATE auto_edition_discovery_cursor SET next_poll_at=now()')


def tick(store,entries=(),more=False,cursor='cursor-1',metadata=None):
    d,sql=store;due(sql)
    listing=Mock(return_value={'entries':list(entries),'has_more':more,'cursor':cursor})
    read=Mock(return_value=metadata or asset())
    d.tick(listing,read)
    return listing,read


def rows(sql,table):
    sql.execute('SELECT * FROM '+table)
    return sql.fetchall()


def test_psd_before_product_and_duplicate_events_preserve_allocations(store):
    d,sql=store
    tick(store,[asset()])
    assert not rows(sql,'product_psd_mappings')
    before=rows(sql,'edition_products'),rows(sql,'edition_allocations'),rows(sql,'synthetic_certificates')
    register(store);tick(store)
    assert rows(sql,'product_psd_mappings')[0]['dropbox_file_id']=='id:original'
    assert rows(sql,'auto_edition_onboarding')[0]['priority']==2
    assert rows(sql,'auto_edition_discovery')[0]['source_identity']['revision']=='a1'
    register(store);register(store,'event-2');tick(store)
    assert len(rows(sql,'product_psd_mapping_audit'))==1
    assert before==(rows(sql,'edition_products'),rows(sql,'edition_allocations'),rows(sql,'synthetic_certificates'))


def test_product_before_psd_waits_durably_and_incremental_change_wakes_it(store):
    d,sql=store;register(store)
    tick(store)
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Waiting for PSD'
    restarted=discovery.Discovery(d.connect)
    tick((restarted,sql),[asset()],cursor='cursor-2')
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Mapped'
    assert rows(sql,'auto_edition_onboarding')[0]['status']=='Awaiting preparation'


def test_incomplete_inventory_cannot_accept_apparently_unique_match(store):
    d,sql=store;register(store)
    _,read=tick(store,[asset()],more=True)
    read.assert_not_called()
    assert not rows(sql,'product_psd_mappings')
    tick(store,[asset(id='id:duplicate')],cursor='cursor-2')
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Needs mapping review'
    assert not rows(sql,'product_psd_mappings')


@pytest.mark.parametrize('kind',['title','handle','filename','ownership','revision','location','identity','missing-revision'])
def test_unclear_or_changed_sources_never_map(store,kind):
    d,sql=store;register(store)
    entries=[asset()];fresh=asset()
    if kind in ('title','handle'):
        sql.execute("INSERT INTO edition_products VALUES('gid://shopify/Product/988','988',%s,%s,100,1,true,true)",
                    ('New Art' if kind=='title' else 'Other','new-art' if kind=='handle' else 'other'))
    if kind=='filename':entries=[asset(name='New Art copy.psd',path_display=psd.ROOT+'/New Art copy.psd')]
    if kind=='ownership':
        sql.execute("INSERT INTO product_psd_mappings VALUES('gid://shopify/Product/988','id:original',%s,'','manual','admin',now(),now())",(asset()['path_display'],))
    if kind=='revision':fresh['rev']='a2'
    if kind=='location':fresh['path_display']=psd.ROOT+'/Prepared/Masters/New Art.psd'
    if kind=='identity':fresh['id']='id:other'
    if kind=='missing-revision':entries=[asset(rev='')]
    tick(store,entries,metadata=fresh)
    assert all(r['shopify_product_gid']!=PID for r in rows(sql,'product_psd_mappings'))
    assert not rows(sql,'auto_edition_onboarding')


def test_manual_add_and_verified_mapping_skip_discovery_and_keep_lease(store):
    d,sql=store
    with patch('os_accounts.can_attach_missing_psd',return_value=True),patch('os_accounts.is_admin',return_value=True):
        mappings=PostgresMappings(d.connect)
        mappings.attach(PID,asset(),{'id':'synthetic-admin'})
    claimed=d.queue.claim('synthetic-host')
    before=rows(sql,'product_psd_mappings'),rows(sql,'auto_edition_onboarding')
    register(store)
    _,read=tick(store,[asset(id='id:replacement')])
    read.assert_not_called()
    assert before==(rows(sql,'product_psd_mappings'),rows(sql,'auto_edition_onboarding'))
    assert rows(sql,'auto_edition_onboarding')[0]['lease_token']==claimed['lease_token']


@pytest.mark.parametrize('approved',[False,True])
def test_prepared_checkpoint_reused_and_visual_approval_not_inferred(store,approved):
    d,sql=store;source={'product_gid':PID,'file_id':'id:original','revision':'a1','content_hash':'a'*64}
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,'[]','{}','admin',now())",
                ('b'*64,json.dumps({'source':source})))
    if approved:
        sql.execute("INSERT INTO auto_edition_layouts VALUES(%s,'variant-1',%s,'{}',now())",(PID,'b'*64))
    register(store);tick(store,[asset()])
    checkpoint=rows(sql,'auto_edition_onboarding')[0]
    assert checkpoint['preparation_hash']=='b'*64
    assert checkpoint['status']==('Cloud Ready' if approved else 'Blocked')
    assert d.queue.claim('host') is None


def test_stale_prepared_revision_is_retained_for_review_not_cloud_ready(store):
    d,sql=store
    source={'product_gid':PID,'file_id':'id:original','revision':'old','content_hash':'b'*64}
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,'[]','{}','admin',now())",
                ('b'*64,json.dumps({'source':source})))
    sql.execute("INSERT INTO auto_edition_layouts VALUES(%s,'variant-1',%s,'{}',now())",(PID,'b'*64))
    register(store);tick(store,[asset()])
    assert rows(sql,'auto_edition_onboarding')[0]['status']=='Blocked'
    assert rows(sql,'auto_edition_onboarding')[0]['preparation_hash']=='b'*64


def test_product_update_during_metadata_read_defers_old_request(store):
    d,sql=store;register(store);claim=d.claim()
    d.page(claim['lease_token'],{'entries':[asset()],'cursor':'c1','has_more':False})
    request=d.pending(claim['lease_token'])[0]
    assert d.reconcile(claim['lease_token'],request)['id']=='id:original'
    register(store,'new-update')
    d.reconcile(claim['lease_token'],request,asset())
    assert not rows(sql,'product_psd_mappings')
    d.reconcile(claim['lease_token'],d.pending(claim['lease_token'])[0],asset())
    assert len(rows(sql,'product_psd_mappings'))==1


def test_metadata_transfer_error_keeps_waiting_request_and_cursor_for_retry(store):
    d,sql=store;register(store)
    read=Mock(side_effect=RuntimeError('synthetic network interruption'))
    with pytest.raises(RuntimeError):
        d.tick(lambda c:{'entries':[asset()],'cursor':'c1','has_more':False},read)
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Waiting for PSD'
    assert rows(sql,'auto_edition_discovery_cursor')[0]['cursor']=='c1'
    tick(store)
    assert len(rows(sql,'product_psd_mappings'))==1


def test_historical_mapping_bootstrap_is_bounded_deferred_and_preserves_checkpoints(store):
    d,sql=store
    sql.execute("INSERT INTO product_psd_mappings VALUES(%s,'id:original',%s,'','manual','admin',now(),now())",(PID,asset()['path_display']))
    mapping=rows(sql,'product_psd_mappings')
    assert d.seed_existing(limit=1)==1
    assert rows(sql,'auto_edition_onboarding')[0]['priority']==0
    checkpoint=rows(sql,'auto_edition_onboarding')
    assert d.seed_existing(limit=1)==0
    assert rows(sql,'auto_edition_discovery_cursor')[0]['seed_finished'] is True
    assert d.seed_existing()==0
    assert rows(sql,'auto_edition_onboarding')==checkpoint
    assert rows(sql,'product_psd_mappings')==mapping


def test_bounded_priority_rotation_retains_order_urgency_and_prepare_now(store):
    from auto_editions_priority import refresh
    d,sql=store;register(store);tick(store,[asset()])
    sql.execute("CREATE TABLE shopify_order_lines(shopify_order_id text,shopify_product_id text,quantity int)")
    sql.execute("CREATE TABLE shopify_orders(shopify_order_id text,fulfillment_status text,financial_status text,cancelled_at timestamptz,created_at timestamptz,raw_json jsonb)")
    sql.execute("CREATE TABLE ads_product_mapping(ad_id text,product_handle text)")
    sql.execute("CREATE TABLE meta_ads(ad_id text,effective_status text)")
    assert refresh(d.queue,'host',limit=1)[0]['product_gid']==PID
    assert rows(sql,'auto_edition_onboarding')[0]['priority']==2
    sql.execute("INSERT INTO shopify_orders VALUES('order','unfulfilled','paid',NULL,now(),'{}')")
    sql.execute("INSERT INTO shopify_order_lines VALUES('order','987',1)")
    refresh(d.queue,'host',limit=1)
    assert rows(sql,'auto_edition_onboarding')[0]['priority']==8
    d.queue.prepare_now(PID,'admin');refresh(d.queue,'host',limit=1)
    assert rows(sql,'auto_edition_onboarding')[0]['priority']==10
    assert rows(sql,'auto_edition_onboarding')[0]['priority_checked_at'] is not None


def test_lease_recovery_rejects_old_worker_and_keeps_cursor(store):
    d,sql=store;register(store)
    first=d.claim();d.page(first['lease_token'],{'entries':[asset()],'cursor':'c1','has_more':True})
    assert d.claim() is None
    sql.execute("UPDATE auto_edition_discovery_cursor SET lease_until=now()-interval '1 second'")
    replacement=discovery.Discovery(d.connect);second=replacement.claim()
    assert second['cursor']=='c1'
    with pytest.raises(ValueError,match='lease'):d.page(first['lease_token'],{'entries':[],'cursor':'bad','has_more':False})
    replacement.page(second['lease_token'],{'entries':[],'cursor':'c2','has_more':False})
    request=replacement.pending(second['lease_token'])[0]
    replacement.reconcile(second['lease_token'],request,asset())
    assert len(rows(sql,'product_psd_mappings'))==1


def test_transaction_failure_rolls_back_mapping_audit_and_queue(store):
    d,sql=store;register(store);claim=d.claim()
    d.page(claim['lease_token'],{'entries':[asset()],'cursor':'c1','has_more':False})
    request=d.pending(claim['lease_token'])[0]
    with patch.object(d.queue,'enqueue_cursor',side_effect=RuntimeError('synthetic interruption')):
        with pytest.raises(RuntimeError):d.reconcile(claim['lease_token'],request,asset())
    assert not rows(sql,'product_psd_mappings') and not rows(sql,'product_psd_mapping_audit')
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Waiting for PSD'
    d.reconcile(claim['lease_token'],request,asset())
    assert len(rows(sql,'product_psd_mapping_audit'))==1


def test_deleted_source_and_cursor_reset_only_remove_cached_metadata(store):
    d,sql=store;register(store);tick(store,[asset()])
    mapping=rows(sql,'product_psd_mappings')
    tick(store,[{'.tag':'deleted','path_lower':asset()['path_display'].lower()}])
    assert not rows(sql,'auto_edition_source_inventory')
    assert rows(sql,'product_psd_mappings')==mapping
    due(sql);claim=d.claim();d.reset_inventory(claim['lease_token'])
    assert rows(sql,'product_psd_mappings')==mapping
    assert rows(sql,'auto_edition_discovery_cursor')[0]['complete'] is False


def test_prepared_folders_are_excluded_and_receipt_inspection_is_read_only(store):
    d,sql=store;register(store)
    tick(store,[asset(name='New Art.png',path_display=psd.ROOT+'/Prepared/Masters/New Art.png'),
                asset(path_display=psd.ROOT+'/Prepared/New Art.psd')])
    assert not rows(sql,'product_psd_mappings')
    from auto_editions_cloud import DropboxAssets
    read=Mock(return_value={'id':'id:master','rev':'a1','size':123,'name':'master.png',
                           'path_display':DropboxAssets.path('b'*64,'master.png')})
    record={'hash':'b'*64,'mapped':False,'receipts':{'assets':[
        {'file_id':'id:master','revision':'a1','bytes':123,'name':'master.png'}]*25}}
    report=discovery.inspect_prepared_receipts([record],read)
    assert report['next_offset']==20 and read.call_count==20
    assert report['issues']==[{'preparation_hash':'b'*64,'reason':'Orphan preparation; review required'}]
    read.return_value['rev']='a2'
    assert 'differs' in discovery.inspect_prepared_receipts([record],read,offset=20)['issues'][1]['reason']
    assert not rows(sql,'auto_edition_layouts')


def test_database_client_roles_cannot_access_discovery(store):
    import psycopg
    d,sql=store
    for role in ('anon','authenticated'):
        sql.execute('SET ROLE '+role)
        try:
            for table in ('auto_edition_discovery','auto_edition_source_inventory','auto_edition_discovery_cursor'):
                with pytest.raises((RuntimeError,psycopg.errors.InsufficientPrivilege),match='permission denied'):
                    sql.execute('SELECT * FROM '+table)
        finally:sql.execute('RESET ROLE')


def test_registration_handoff_failure_preserves_webhook_retry_and_rolls_back():
    from tests.test_product_activation_sync import ActivationTests
    test=ActivationTests();test.setUp()
    try:
        with patch.object(discovery,'register',side_effect=RuntimeError('handoff unavailable')) as handoff:
            with pytest.raises(RuntimeError):test.webhook()
            assert test.db.rows==[]
            test.mirror.assert_not_called()
            assert handoff.call_count==1
    finally:test.doCleanups()


def test_host_claim_does_not_refresh_catalogue_with_v15_enabled(monkeypatch):
    import asyncio
    import auto_editions_onboarding_api as api
    from tests.test_auto_editions_api import request,ADMIN
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true')
    queue=Mock();queue.claim.return_value=None
    async def check():
        with patch.object(api,'preparation_actor',return_value=ADMIN),patch.object(api,'queue',return_value=queue),\
                patch('auto_editions_priority.refresh',side_effect=AssertionError('Catalogue scan on claim')):
            response=await api.claim(request('POST',body={}))
            assert response.status_code==200 and json.loads(response.body)=={'grant':None}
    asyncio.run(check())


def test_summary_shows_durable_waiting_status_without_dropbox_io(store):
    import asyncio
    import auto_editions_onboarding_api as api
    from tests.test_auto_editions_api import request,ADMIN
    d,sql=store;register(store)
    async def check():
        with patch.object(api.api,'actor',return_value=ADMIN),patch.object(api,'queue',return_value=d.queue),\
                patch('files_upload_api._dropbox_context',side_effect=AssertionError('Network on page load')):
            response=await api.summary(request('GET'))
            assert response.status_code==200
            row=json.loads(response.body)['rows'][0]
            assert row['status']=='Waiting for PSD' and row['product_title']=='New Art'
            assert 'lease_token' not in row
    asyncio.run(check())


def test_worker_reuses_existing_service_thread_and_honours_rollout_gate():
    import sports_cave_worker as worker
    for enabled in (False,True):
        supervisor=worker.Supervisor();supervisor.stop.set()
        with patch.object(discovery,'enabled',return_value=enabled),patch.object(worker.threading,'Thread') as thread:
            supervisor.run()
            assert thread.call_count==int(enabled)
            if enabled:
                thread.return_value.start.assert_called_once()
                thread.return_value.join.assert_called_once()


@pytest.mark.skipif(not os.getenv('AUTO_EDITIONS_NATIVE_TEST_PORT'),reason='Independent connections require isolated native PostgreSQL')
def test_concurrent_registration_and_mapping_use_consistent_lock_order(store):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    d,sql=store;register(store);claim=d.claim()
    d.page(claim['lease_token'],{'entries':[asset()],'cursor':'c1','has_more':False})
    original=d.pending(claim['lease_token'])[0]
    barrier=threading.Barrier(2)
    def registration():
        barrier.wait(timeout=5)
        with d.connect() as conn,conn.cursor() as cur:
            cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
            discovery.register(cur,[{'shopify_product_gid':PID}],'event-2')
    def mapping():
        barrier.wait(timeout=5)
        return d.reconcile(claim['lease_token'],original,asset())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(fn) for fn in (registration,mapping)]
        for future in futures:future.result(timeout=10)
    current=rows(sql,'auto_edition_discovery')[0]
    d.reconcile(claim['lease_token'],current,asset())
    assert len(rows(sql,'product_psd_mapping_audit'))==1
    assert len(rows(sql,'auto_edition_onboarding'))==1


@pytest.mark.skipif(not os.getenv('AUTO_EDITIONS_NATIVE_TEST_PORT'),reason='Independent connections require isolated native PostgreSQL')
def test_concurrent_duplicate_mapping_and_preparation_claim_have_single_winners(store):
    from concurrent.futures import ThreadPoolExecutor
    d,sql=store;register(store);claim=d.claim()
    d.page(claim['lease_token'],{'entries':[asset()],'cursor':'c1','has_more':False})
    request=d.pending(claim['lease_token'])[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(d.reconcile,claim['lease_token'],request,asset()) for _ in range(2)]
        for future in futures:future.result(timeout=10)
        claims=[pool.submit(d.queue.claim,'host-'+str(i)) for i in range(2)]
        winners=[future.result(timeout=10) for future in claims]
    assert sum(row is not None for row in winners)==1
    assert len(rows(sql,'product_psd_mapping_audit'))==1
    assert len(rows(sql,'auto_edition_onboarding'))==1
