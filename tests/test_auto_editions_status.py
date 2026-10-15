"""Authoritative status, scoped SQL, permissions and recovery contracts."""
import asyncio
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import statistics
import time
from unittest.mock import Mock,patch
import pytest

import auto_editions_status as status
import edition_auto_status_ui as ui
from tests.test_auto_editions_discovery import database,store,pglite_database,PID,asset,tick,register,rows
from tests.test_auto_editions_api import request,ADMIN,VA

SOURCE={'product_gid':PID,'file_id':'id:original','revision':'a1','content_hash':'a'*64}
HASH='b'*64


def record(**changes):
    return dict(product_gid=PID,dropbox_file_id='id:original',file_id='id:original',status='Cloud Ready',
                priority=2,preparation_hash=HASH,source=SOURCE,prepared_source=SOURCE,
                prepared_total=100,product_total=100,stored_hash=HASH,pixel_exact=True,outside_exact=True,bound=True,
                approved=True,hash_count=1,observed_source=SOURCE,lease_until=datetime.now(timezone.utc)+timedelta(minutes=5),
                checkpoint='visual_quality_approved',checkpoint_at='2026-10-15T00:00:00Z',**changes)


@pytest.mark.parametrize('state,changes',[
    ('Not Connected',{'dropbox_file_id':None}),('Connect',{'file_id':None}),
    ('Queued',{'status':'Awaiting preparation'}),('Deferred',{'status':'Awaiting preparation','priority':0}),
    ('Preparing',{'status':'Preparing'}),('Review',{'status':'Blocked','approved':False}),
    ('Cloud Ready',{}),('Needs Repair',{'status':'Needs PSD Repair','preparation_hash':None}),
    ('Failed',{'status':'Blocked','preparation_hash':None,'reason':'Photoshop unavailable'})])
def test_all_authoritative_stages(state,changes):
    value=status.project({**record(),**changes},writable=True)
    assert value['status']==state
    assert status.project({**record(),**changes},writable=False)['actions']==[]


@pytest.mark.parametrize('changes',[
    {'source':{**SOURCE,'revision':'a2'}},{'observed_source':{**SOURCE,'revision':'a2'}},
    {'observed_source':{'missing':True}},{'prepared_total':99},{'bound':False},
    {'approved':False},{'hash_count':2},{'file_id':'id:changed'},{'stored_hash':'c'*64},
    {'prepared_source':{**SOURCE,'revision':''}}, {'product_total':None},
])
def test_stale_or_unverified_preparation_is_never_ready(changes):
    value=status.project({**record(),**changes},writable=True)
    assert value['status']=='Failed' and value['actions']==[]


def test_expired_lease_does_not_offer_destructive_retry():
    value=status.project({**record(),'status':'Preparing','lease_until':datetime.now(timezone.utc)-timedelta(seconds=1)},writable=True)
    assert value['status']=='Failed' and value['actions']==[] and 'recovery' in value['reason']


@pytest.mark.parametrize('malformed',[['legacy-source'],'legacy-source',42,True])
def test_malformed_source_fails_closed_without_breaking_other_products(malformed):
    value=status.project({**record(),'source':malformed,'prepared_source':malformed},writable=True)
    assert value['status']=='Failed' and value['actions']==[]


def test_failure_reasons_and_checkpoints_do_not_expose_credentials():
    value=status.project({**record(),'status':'Blocked','preparation_hash':None,
        'reason':'Bearer secret-token at C:\\private\\source.psd','checkpoint':'raw-secret-event'},writable=True)
    assert 'private' not in json.dumps(value) and 'secret-token' not in json.dumps(value)
    assert value['checkpoint']=='Checkpoint recorded'
    assert value['actions']==['retry']


def test_batched_query_fences_current_source_and_approval(store):
    d,sql=store;register(store);tick(store,[asset()])
    result=status.batch(d.connect,[PID],writable=True)
    assert result['query_count']==1 and result['rows'][0]['status']=='Queued'
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,'{}','admin',now())",
        (HASH,json.dumps({'source':SOURCE,'edition_total':100}),json.dumps([
            {'preparation_hash':HASH,'pixel_exact':True},{'preparation_hash':HASH,'outside_number_exact':True}])))
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',preparation_hash=%s,source=%s::jsonb WHERE product_gid=%s",(HASH,json.dumps(SOURCE),PID))
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Review'
    approval={'actor_id':'synthetic-admin','preparation_hash':HASH,'visual_approved':True,'pixel_exact':True,'test_only':True}
    sql.execute("INSERT INTO auto_edition_layouts VALUES(%s,'*',%s,%s::jsonb,now())",(PID,HASH,json.dumps(approval)))
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready'")
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Cloud Ready'
    sql.execute("UPDATE auto_edition_source_inventory SET metadata=jsonb_set(metadata,'{rev}','\"a2\"')")
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Failed'
    assert rows(sql,'edition_products')[0]['next_edition_number']==37


def test_duplicate_product_identity_and_missing_database_are_unavailable(store):
    d,sql=store
    sql.execute('INSERT INTO edition_products SELECT * FROM edition_products')
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Unavailable'
    fake=Mock(session_state={})
    backend=Mock();backend.connect.side_effect=RuntimeError('synthetic database offline')
    values=ui.snapshot(fake,backend,[{'shopify_product_gid':PID}])
    assert values[PID]['status']=='Unavailable'


def test_connect_only_recovers_missing_checkpoint_without_remapping_or_approval(store):
    d,sql=store
    sql.execute("INSERT INTO product_psd_mappings VALUES(%s,'id:original',%s,'','manual','admin',now(),now())",(PID,asset()['path_display']))
    mapping=rows(sql,'product_psd_mappings');allocations=rows(sql,'edition_allocations')
    status.connect_existing(d.connect,PID,'admin')
    claimed=d.queue.claim('host');checkpoint=rows(sql,'auto_edition_onboarding')
    status.connect_existing(d.connect,PID,'admin')
    assert rows(sql,'auto_edition_onboarding')==checkpoint
    assert rows(sql,'product_psd_mappings')==mapping and rows(sql,'edition_allocations')==allocations
    assert not rows(sql,'auto_edition_layouts')
    sql.execute("UPDATE auto_edition_onboarding SET file_id='id:different'")
    with pytest.raises(ValueError,match='review'):status.connect_existing(d.connect,PID,'admin')


def test_status_access_and_connect_origin_admin_permissions(store):
    d,sql=store
    async def check():
        with patch('files_upload_api._request_user',return_value={**VA,'page_permissions':['edition_ops']}),\
                patch('supabase_backend.connect',d.connect):
            response=await status.statuses(request('POST',body={'product_gids':[PID]}))
            assert response.status_code==200 and json.loads(response.body)['rows'][0]['actions']==[]
            with patch.object(status.runtime,'enabled',return_value=True):
                assert (await status.connect_action(request('POST',body={'product_gid':PID}))).status_code==403
        with patch('files_upload_api._request_user',return_value={**VA,'page_permissions':[]}):
            assert (await status.statuses(request('POST',body={'product_gids':[PID]}))).status_code==403
        with patch('files_upload_api._request_user',return_value=ADMIN),patch.object(status.runtime,'enabled',return_value=True):
            for origin in ('','https://evil.test'):
                assert (await status.connect_action(request('POST',origin=origin,body={'product_gid':PID}))).status_code==403
    asyncio.run(check())


def test_signed_refresh_preserves_editor_rows_filters_and_selection():
    user={'id':'admin'};row={'shopify_product_gid':PID,'edition_next_number':37}
    state={'sports_cave_current_user':user,'edition_ops_rows':[deepcopy(row)],'edition_ops_editor_v3':{'edited_rows':{'0':{'edition_next_number':42}}},
        'edition-auto-filter':'Queued','edition-status-filter':'Active','edition_ops_editor_product_selection':PID}
    protected=deepcopy(state)
    data=status.signed({'rows':[status.project(record())]},user)
    state['edition-auto-live']={**data,'nonce':1}
    fake=Mock(session_state=state);backend=Mock()
    values=ui.snapshot(fake,backend,[row])
    assert values[PID]['status']=='Cloud Ready';backend.connect.assert_not_called()
    for key,value in protected.items():assert state[key]==value
    data['rows'][0]['status']='Not Connected'
    assert status.verify_snapshot(data,user,[PID]) is None
    state['edition-auto-live']={**data,'nonce':2}
    assert ui.snapshot(fake,backend,[row])[PID]['status']=='Unavailable'
    state['edition-auto-live']={'unavailable':True,'nonce':3}
    assert ui.snapshot(fake,backend,[row])[PID]['status']=='Unavailable'


def test_status_query_is_single_scoped_batch_and_has_no_remote_calls(store):
    d,sql=store
    with patch('dropbox_integration.psd_open_metadata',side_effect=AssertionError('No Dropbox')),\
         patch('shopify_sync.fetch_product_by_shopify_id',side_effect=AssertionError('No Shopify')):
        result=status.batch(d.connect,[PID]*1000)
    assert result['query_count']==1 and len(result['rows'])==1
    assert len(json.dumps(result))<600
    with pytest.raises(ValueError):status.batch(d.connect,['not-a-product'])


def test_status_only_table_refresh_reuses_mapping_and_retains_unsaved_edit():
    import edition_ops as ops
    from tests.test_edition_ops_stability import _FakeStreamlit,_product
    row=_product(987);row['edition_next_number']=37;old=deepcopy(row);row['edition_next_number']=42
    user={'id':'admin'}
    data=status.signed({'rows':[status.project(record())]},user)
    fake=_FakeStreamlit({ops.SNAPSHOT_LOADED_KEY:True,ops.ROWS_KEY:[row],ops.ORIGINAL_ROWS_KEY:[old],
        'sports_cave_current_user':user,'edition-auto-live':{**data,'nonce':1},
        'edition-auto-file-mapping':{PID:{'verified':True,'state':'Linked','dropbox_file_id':'id:original'}}})
    with patch.object(ops,'st',fake),patch.object(ops,'_configured_supabase_backend',return_value=Mock()),\
            patch.object(ops,'_hydrate_from_snapshot_once',side_effect=AssertionError('No catalogue hydration on status-only refresh')),\
            patch.object(ops.psd_directory,'page_directory',side_effect=AssertionError('No second mapping query')),\
            patch('edition_version_ui.advanced'):
        ops._render_table()
    assert fake.session_state[ops.ROWS_KEY][0]['edition_next_number']==42
    assert fake.session_state[ops.ORIGINAL_ROWS_KEY][0]['edition_next_number']==37
    assert 'Cloud Ready' in fake.editor_payloads[0][0]['auto_editions']


@pytest.mark.skipif(not os.getenv('AUTO_EDITIONS_NATIVE_TEST_PORT'),reason='Native PostgreSQL performance fixture only')
def test_native_334_product_snapshot_performance(store):
    d,sql=store
    sql.execute('DELETE FROM edition_products')
    sql.execute("""INSERT INTO edition_products SELECT 'gid://shopify/Product/'||n,n::text,
        'Synthetic Art '||n,'art-'||n,100,37,true,true FROM generate_series(1,334) n""")
    sql.execute("""INSERT INTO product_psd_mappings SELECT shopify_product_gid,'id:'||shopify_product_id,
        %s||'/Art '||shopify_product_id||'.psd','','manual','synthetic-admin',now(),now() FROM edition_products""",(asset()['path_display'].rsplit('/',1)[0],))
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) SELECT shopify_product_gid,dropbox_file_id,2 FROM product_psd_mappings")
    sql.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event) SELECT product_gid,'synthetic-admin','queued' FROM auto_edition_onboarding CROSS JOIN generate_series(1,20)")
    # Existing production identity indexes, reproduced in this minimal fixture.
    sql.execute('CREATE INDEX fixture_product_gid ON edition_products(shopify_product_gid)')
    sql.execute('CREATE INDEX fixture_product_id ON edition_products(shopify_product_id)')
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261015000124_auto_editions_status_audit_index.sql').read_text())
    ids=['gid://shopify/Product/'+str(i) for i in range(1,335)]
    baseline=[];timings=[]
    for _ in range(7):
        started=time.perf_counter()
        with d.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM edition_products ORDER BY product_title');cur.fetchall()
        baseline.append((time.perf_counter()-started)*1000)
        result=status.batch(d.connect,ids);timings.append(result['duration_ms'])
    public=status.signed(result,{'id':'synthetic-reader'})
    report={'products':334,'audit_rows':6680,'query_count_per_status_poll':result['query_count'],
        'baseline_synthetic_listing_median_ms':round(statistics.median(baseline),2),
        'status_batch_median_ms':round(statistics.median(timings),2),
        'status_response_bytes':len(json.dumps(public,separators=(',',':')).encode()),
        'dropbox_calls':0,'catalogue_api_calls':0}
    output=Path(__file__).parents[1]/'output/v15-phase3/performance.json'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
    assert result['query_count']==1 and len(result['rows'])==334
    assert report['status_response_bytes']<180_000
