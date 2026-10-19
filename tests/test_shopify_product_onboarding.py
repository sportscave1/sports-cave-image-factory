"""Isolated PostgreSQL onboarding: public Brock identity, simulated history/orders only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
from unittest.mock import Mock
import pytest
from tests.test_auto_editions_jobs import database
import supabase_backend as db
import shopify_product_onboarding as onboarding

ROOT = Path(__file__).resolve().parents[1]
PID = 'gid://shopify/Product/15428753948979'

@pytest.fixture
def state(database, monkeypatch):
    jobs, sql = database
    jobs.connect.commit = lambda self: None
    type(sql).rowcount = 1
    sql.execute((ROOT/'tests/fixtures/edition_base.sql').read_text().replace('CREATE ROLE anon; CREATE ROLE authenticated;', ''))
    for name in ('create_edition_runs_phase2.sql','20260825_atomic_edition_allocation_ledger.sql','20260912045939_independent_edition_cursor.sql','20261008041452_edition_version_transitions.sql','20261008045733_edition_version_guard_hardening.sql','20261008065000_explicit_edition_cursor_override.sql','20261008090000_edition_admin_cursor_repair.sql'):
        sql.execute((ROOT/'migrations'/name).read_text().replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;', ''))
    sql.execute('''ALTER TABLE edition_orders ADD COLUMN product_handle text;
      ALTER TABLE edition_products ADD COLUMN raw jsonb, ADD COLUMN synced_at timestamptz;
      ALTER TABLE shopify_products ADD UNIQUE(shopify_product_id), ADD COLUMN legacy_resource_id text,
      ADD COLUMN title text, ADD COLUMN vendor text, ADD COLUMN product_type text, ADD COLUMN raw_json jsonb,
      ADD COLUMN raw jsonb, ADD COLUMN synced_at timestamptz, ADD COLUMN updated_at timestamptz;
      CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz);
      CREATE TABLE webhook_events(webhook_id text PRIMARY KEY,topic text,status text,shop_domain text,source text,payload jsonb,
      received_at timestamptz,processed_at timestamptz,error_message text,inserted_count int,skipped_count int,
      affected_handles_count int,processing_elapsed_ms int,new_order_inserted bool,shopify_order_id text,shopify_order_name text);''')
    monkeypatch.setattr(db,'connect',jobs.connect)
    monkeypatch.setattr(db,'is_configured',lambda:True)
    monkeypatch.setattr(db,'_mirror_pending_registered_product',lambda *a,**k:False)
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    monkeypatch.setattr('product_sport_tag_sync.sync_product_sport_tags',lambda *a,**k:dict(status='verified',review=[]))
    product=dict(shopify_product_id=PID,legacy_resource_id=PID.rsplit('/',1)[-1],title='Peter Brock — King of the Mountain',
        handle='peter-brock-king-of-the-mountain-wall-art',status='ACTIVE',vendor='Sports Cave',product_type='Framed Art',
        created_at='2026-10-19T09:28:59Z',metafields=[],tags=['sc-upload-2f31a872ebc54dcb8e9ea83bcf31bc11','sc-edition-limit-100'],
        online_store_url='https://fixture.invalid/brock',_edition_registration_canonical=True)
    monkeypatch.setattr(db.shopify_sync,'fetch_product_by_shopify_id',lambda *a,**k:deepcopy(product))
    history=Mock(return_value=({'orders':{'nodes':[],'pageInfo':{'hasNextPage':False}}},'2026-04'))
    monkeypatch.setattr(db.shopify_sync,'graphql_request',history)
    return sql,product,history


def deliver(event='local-create'):
    claim=db.claim_product_create_webhook_receipt({'id':PID.rsplit('/',1)[-1]},event,'products/create',shop_domain='fixture.myshopify.com')
    onboarding.drain(db)
    return claim


def rows(sql,table):
    sql.execute('SELECT * FROM '+table)
    return deepcopy(sql.fetchall())


def test_brock_targeted_import_duplicates_out_of_order_and_first_order(state):
    sql,p,history=state
    assert not deliver()['duplicate']
    before=rows(sql,'edition_products')
    assert len(before)==1
    row=before[0]
    assert row['shopify_product_gid']==PID
    assert (row['next_edition_number'],row['sold_count'],row['remaining_count'],row['edition_total'])==(1,0,100,100)
    assert len(rows(sql,'edition_runs'))==1
    assert not rows(sql,'edition_orders') and not rows(sql,'certificates')
    assert deliver()['duplicate']
    # Real existing SQL allocator; two retries of the same concurrent first order.
    def allocate(_):
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT allocate_edition_line_units_atomic(%s,%s,%s,%s,%s,%s,%s,%s) AS result',
                ('shopify','local-order','local-line',PID,1,'local-order','#LOCAL','local-line'))
            return cur.fetchone()['result']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(allocate, i) for i in range(2)]
        futures.append(pool.submit(deliver,'out-of-order-old-event'))
        for future in futures:future.result()
    allocated=rows(sql,'edition_orders')
    assert len(allocated)==1 and allocated[0]['edition_number']==1
    assert len(rows(sql,'edition_runs'))==1
    assert rows(sql,'edition_products')[0]['next_edition_number']==2
    assert not rows(sql,'certificates')


def test_late_metadata_and_retry_survive_worker_recreation(state):
    sql,p,history=state
    p['tags']=p['tags'][:1]
    deliver()
    assert not rows(sql,'edition_products')
    assert rows(sql,'webhook_events')[0]['status']=='pending'
    p['tags'].append('sc-edition-limit-100')
    sql.execute("UPDATE webhook_events SET processed_at=now()-interval '2 hours'")
    history.side_effect=ConnectionError('simulated Shopify outage')
    onboarding.drain(db)
    assert rows(sql,'webhook_events')[0]['status']=='failed'
    assert not rows(sql,'edition_products')
    history.side_effect=None
    sql.execute("UPDATE webhook_events SET processed_at=now()-interval '2 hours'")
    onboarding.drain(db)
    assert len(rows(sql,'edition_products'))==1
    assert rows(sql,'webhook_events')[0]['status']=='processed'


def test_recovery_checkpoint_and_pagination_only_after_success(state):
    sql,p,history=state
    def api(query,variables=None,**kwargs):
        if query==onboarding.PRODUCT_PAGE:
            assert 'updated_at:>=' in variables['query']
            return {'products':{'nodes':[{'id':PID,'updatedAt':'2026-10-19T21:30:22Z'}],
                                'pageInfo':{'hasNextPage':False,'endCursor':None}}},'2026-04'
        return {'orders':{'nodes':[],'pageInfo':{'hasNextPage':False}}},'2026-04'
    history.side_effect=api
    onboarding.reconcile(db)
    assert len(rows(sql,'edition_products'))==1
    checkpoint=db.get_app_setting(onboarding.CHECKPOINT,{},ensure_schema_first=False)
    assert checkpoint.get('checkpoint')
    history.side_effect=ConnectionError('page unavailable')
    with pytest.raises(ConnectionError):onboarding.reconcile(db)
    assert db.get_app_setting(onboarding.CHECKPOINT,{},ensure_schema_first=False)==checkpoint


def test_history_and_existing_manual_counters_never_reset(state):
    sql,p,history=state
    history.return_value=({'orders':{'nodes':[{'id':'prior','lineItems':{'nodes':[{'product':{'id':PID}}],'pageInfo':{'hasNextPage':False}}}],
                                     'pageInfo':{'hasNextPage':False}}},'2026-04')
    deliver()
    assert not rows(sql,'edition_products')
    assert rows(sql,'webhook_events')[0]['status']=='pending'
    history.return_value=({'orders':{'nodes':[],'pageInfo':{'hasNextPage':False}}},'2026-04')
    deliver('new-update')
    sql.execute("SELECT set_config('sports_cave.edition_version_action','activate',false)")
    sql.execute('UPDATE edition_products SET next_edition_number=53,sold_count=52,remaining_count=48,allow_counter_history_override=true')
    before=rows(sql,'edition_products')
    deliver('stale-event')
    after=rows(sql,'edition_products')
    for key in ('next_edition_number','sold_count','remaining_count','active_edition_run_id','allow_counter_history_override'):
        assert before[0][key]==after[0][key]

def test_signed_wrong_shop_and_failed_receipt_never_acknowledged(monkeypatch):
    import base64, hashlib, hmac
    from fastapi.testclient import TestClient
    import webhook_server
    monkeypatch.setenv('SHOPIFY_STORE_DOMAIN','fixture.myshopify.com')
    monkeypatch.setenv('SHOPIFY_WEBHOOK_SECRET','local-only-secret')
    monkeypatch.setattr(db,'is_configured',lambda:True)
    claim=Mock(side_effect=ConnectionError('disposable receipt database offline'))
    monkeypatch.setattr(db,'claim_product_create_webhook_receipt',claim)
    body=json.dumps({'id':15428753948979}).encode()
    sig=base64.b64encode(hmac.new(b'local-only-secret',body,hashlib.sha256).digest()).decode()
    client=TestClient(webhook_server.app)
    headers={'X-Shopify-Shop-Domain':'wrong.myshopify.com','X-Shopify-Hmac-Sha256':sig}
    assert client.post('/webhooks/shopify/products-create',content=body,headers=headers).status_code==401
    claim.assert_not_called()
    headers['X-Shopify-Shop-Domain']='fixture.myshopify.com'
    assert client.post('/webhooks/shopify/products-create',content=body+b' ',headers=headers).status_code==401
    claim.assert_not_called()
    assert client.post('/webhooks/shopify/products-create',content=body,headers=headers).status_code==500
    claim.assert_called_once()


def test_bounded_page_resume_and_overlap(state):
    sql,p,api=state
    calls=[]
    def page(query,variables=None,**kw):
        calls.append(variables)
        if variables['after'] is None:
            return {'products':{'nodes':[], 'pageInfo':{'hasNextPage':True,'endCursor':'second'}}},'2026-04'
        return {'products':{'nodes':[], 'pageInfo':{'hasNextPage':False}}},'2026-04'
    api.side_effect=page
    onboarding.reconcile(db,max_pages=1)
    continuation=db.get_app_setting(onboarding.CHECKPOINT,{},ensure_schema_first=False)
    assert continuation['after']=='second' and not continuation['checkpoint']
    onboarding.reconcile(db,max_pages=1)
    checkpoint=db.get_app_setting(onboarding.CHECKPOINT,{},ensure_schema_first=False)
    assert checkpoint=={'checkpoint':continuation['until']}
    assert calls[1]['query']==calls[0]['query'] and calls[1]['after']=='second'
    onboarding.reconcile(db,max_pages=1)
    assert calls[2]['after'] is None
    assert (datetime.fromisoformat(checkpoint['checkpoint'])-__import__('datetime').timedelta(minutes=10)).isoformat() in calls[2]['query']


def test_unknown_or_expired_history_fails_closed(state):
    sql,p,api=state
    p['metafields']=[{'namespace':'sports_cave','key':'edition_status','value':'expired'}]
    deliver()
    assert not rows(sql,'edition_products')
    p['metafields']=[]
    api.return_value=({'orders':{'nodes':[{'id':'long-order','lineItems':{'nodes':[],'pageInfo':{'hasNextPage':True}}}], 'pageInfo':{'hasNextPage':False}}},'2026-04')
    deliver('uncertain-history')
    assert not rows(sql,'edition_products')
    assert all(r['status']=='pending' for r in rows(sql,'webhook_events'))


def test_durable_lease_excludes_other_consumers_and_recovers_after_expiry(state, monkeypatch):
    sql,p,history=state
    calls=[]
    def drain(*args, **kwargs):
        calls.append(1)
        kwargs['renew']()
        onboarding.tick(db=db)  # competing instance must not enter drain
    monkeypatch.setattr(onboarding,'drain',drain)
    onboarding.tick(db=db)
    assert calls == [1]
    onboarding.tick(db=db)
    assert calls == [1,1]  # normal release permits the next cycle
    db.set_app_setting(onboarding.LEASE, {'owner':'crashed','expires_at':'2000-01-01T00:00:00Z'}, ensure_schema_first=False)
    onboarding.tick(db=db)
    assert calls == [1,1,1]


def test_classification_review_is_pending_and_other_errors_remain_retryable(state, monkeypatch):
    sql,p,history=state
    db.claim_product_create_webhook_receipt({'id':PID.rsplit('/',1)[-1]},'review','products/update')
    result={'errors':['Sport classification review required: missing sport']}
    monkeypatch.setattr(db,'process_product_create_webhook',lambda *a,**k:result)
    row={'payload':{'id':PID},'webhook_id':'review','topic':'products/update'}
    assert onboarding.process_receipt(row,db)['status']=='pending'
    result['errors']=['database mirror unavailable']
    with pytest.raises(RuntimeError):onboarding.process_receipt(row,db)
    assert rows(sql,'webhook_events')[0]['status']=='failed'


def test_reused_catalog_handle_is_pending_without_overwriting_previous_identity(state):
    sql,p,history=state
    sql.execute("INSERT INTO shopify_products(shopify_product_id,handle) VALUES(%s,%s)",('gid://shopify/Product/15428059398451',p['handle']))
    deliver('reused-handle')
    assert rows(sql,'webhook_events')[0]['status']=='pending'
    assert 'another Shopify product' in rows(sql,'webhook_events')[0]['error_message']
    assert not rows(sql,'edition_products') and not rows(sql,'edition_runs')
    assert rows(sql,'shopify_products')[0]['shopify_product_id']=='gid://shopify/Product/15428059398451'
