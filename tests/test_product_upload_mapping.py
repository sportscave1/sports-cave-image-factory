"""Real isolated PostgreSQL + production mapping services, mocked provider I/O."""
from copy import deepcopy
import json
from unittest.mock import Mock
import pytest

from tests.test_product_upload_intake import database, env, product, ADMIN, PID
from tests.test_product_upload_dropbox import selected
from product_upload_mapping import Mapping, read_edition, approved_upload_source
from product_upload_identity import tag, correlation_prompt


def setup(env, *, correlated=True, limit=200):
    store, sql, provider = env
    from pathlib import Path
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261019070000_product_upload_verified_psd_mapping.sql').read_text(encoding='utf-8'))
    row, meta = selected(env)
    key = str(row['id'])
    with store.locked(key, ADMIN['id']) as (row, cur):
        row['data'].update(mockups_exported=True, mockups_context=dict(design_name='new-art', folder='/isolated/output/new-art',
                           images=[dict(role=str(n), filename=f'{n}.webp') for n in range(8)]))
    p = product(tags=([tag(key)] if correlated else []) + ([f'sc-edition-limit-{limit}'] if limit else []))
    shop = Mock()
    shop.fetch_catalog_page.return_value = dict(products=[deepcopy(p)] if correlated else [], has_next_page=False)
    shop.fetch_product_by_shopify_id.side_effect = lambda pid: deepcopy(p) if pid == PID else None
    def mirror(_):
        edition = read_edition(store.connect, PID)
        values = dict(edition_total=edition['edition_total'], edition_next_number=edition['next_edition_number'],
                      edition_sold_count=edition['sold_count'], edition_remaining=edition['remaining_count'],
                      edition_enabled='true', edition_status=edition['edition_status'], edition_label=edition['edition_name'])
        p['metafields'] = [dict(namespace='sports_cave', key=k, value=str(v)) for k,v in values.items()]
        sql.execute("UPDATE edition_products SET metafields_sync_status='Synced'")
    service = Mapping(store.connect, provider, shopify=shop, mirror=mirror)
    return service, key, meta, p


def test_new_draft_exact_identity_real_registration_no_allocation_and_idempotent(env):
    service, key, meta, p = setup(env)
    result = service.map(key, ADMIN)
    assert result['state'] == 'Mapped', result
    assert result['next_edition'] == '001' and result['edition_limit'] == 200
    store, sql, provider = env
    saved = store.read(key, ADMIN['id'])['data']['upload_operation']
    assert saved['source'] == meta and saved['product_id'] == PID and saved['binding'] == 'correlation'
    assert saved['output']['images'] and saved['run_id'] and saved['edition_id']
    assert approved_upload_source(store.connect, PID, meta, key=key, actor=ADMIN['id'])
    sql.execute('SELECT count(*) AS n FROM auto_edition_onboarding_audit'); before = sql.fetchone()['n']
    assert service.map(key, ADMIN)['state'] == 'Mapped'
    for table in ('edition_products', 'edition_runs', 'auto_edition_onboarding', 'product_psd_mappings'):
        sql.execute('SELECT count(*) AS n FROM '+table); assert sql.fetchone()['n'] == 1
    sql.execute('SELECT count(*) AS n FROM auto_edition_onboarding_audit'); assert sql.fetchone()['n'] == before
    sql.execute('SELECT count(*) AS n FROM edition_orders'); assert sql.fetchone()['n'] == 0
    assert p['status'] == 'DRAFT' and not provider.calls
    assert {c[0] for c in service.shopify.method_calls} <= {'fetch_catalog_page', 'fetch_product_by_shopify_id'}


def test_existing_numbering_preserved_and_status_is_read_only(env):
    service, key, meta, p = setup(env)
    assert service.map(key, ADMIN)['state'] == 'Mapped'
    store, sql, provider = env
    sql.execute('UPDATE edition_products SET next_edition_number=8,sold_count=7,remaining_count=193,last_assigned_edition=7')
    sql.execute('UPDATE edition_runs SET next_edition_number=8')
    service.mirror(p)
    assert service.map(key, ADMIN)['next_edition'] == '008'
    service.queue.enqueue = Mock(side_effect=AssertionError('GET must not enqueue'))
    service.register = Mock(side_effect=AssertionError('GET must not register'))
    service.mirror = Mock(side_effect=AssertionError('GET must not mirror'))
    before = store.read(key, ADMIN['id'])
    assert service.status(key, ADMIN)['state'] == 'Mapped'
    assert store.read(key, ADMIN['id']) == before


def test_missing_tag_and_ambiguous_tag_never_auto_link(env):
    service, key, meta, p = setup(env, correlated=False)
    assert service.map(key, ADMIN)['state'] == 'Pending sync'
    assert not env[0].read(key, ADMIN['id'])['data'].get('product_gid')
    p['tags'].append(tag(key))
    service.shopify.fetch_catalog_page.return_value['products'] = [p,dict(p, shopify_product_id='gid://shopify/Product/988')]
    result = service.map(key, ADMIN)
    assert result['state'] == 'Pending sync' and 'More than one' in result['reason']
    assert not env[0].read(key, ADMIN['id'])['data'].get('product_gid')


def test_delayed_catalogue_pagination_and_retry(env):
    service, key, meta, p = setup(env, correlated=False)
    assert service.map(key, ADMIN)['state'] == 'Pending sync'
    p['tags'].append(tag(key))
    service.shopify.fetch_catalog_page.side_effect = [dict(products=[],has_next_page=True,end_cursor='next'),
                                                    dict(products=[p],has_next_page=False)]
    assert service.map(key, ADMIN)['state'] == 'Mapped'
    assert service.shopify.fetch_catalog_page.call_args.kwargs['after'] == 'next'


def test_legacy_selector_requires_explicit_saved_candidate(env):
    service, key, meta, p = setup(env, correlated=False)
    result = service.map(key, ADMIN, product_id=PID)
    assert result['state'] == 'Mapping failed'
    assert not env[0].read(key, ADMIN['id'])['data'].get('product_gid')
    assert service.candidates(key, ADMIN, PID)[0]['id'] == PID
    result = service.map(key, ADMIN, product_id=PID)
    assert result['state'] == 'Mapped', result
    assert env[0].read(key, ADMIN['id'])['data']['upload_operation']['binding'] == 'operator'


def test_unknown_limit_requires_confirmation_not_default_guess(env):
    service, key, meta, p = setup(env, limit=None)
    result = service.map(key, ADMIN)
    assert result['state'] == 'Pending sync' and result['needs_limit']
    assert read_edition(env[0].connect, PID) is None
    assert service.map(key, ADMIN, confirmed_limit=75)['edition_limit'] == 75


def test_source_revision_change_cannot_map_or_show_green(env):
    service, key, meta, p = setup(env)
    env[2].files[meta['id']]['rev'] = 'a2'
    assert service.map(key, ADMIN)['state'] == 'Mapping failed'
    assert read_edition(env[0].connect, PID) is None
    env[2].files[meta['id']]['rev'] = meta['rev']
    assert service.map(key, ADMIN)['state'] == 'Mapped'
    env[2].files[meta['id']]['content_hash'] = 'b'*64
    assert service.status(key, ADMIN)['state'] == 'Status unavailable'
    assert not approved_upload_source(env[0].connect, PID, env[2].files[meta['id']])


@pytest.mark.parametrize('step',['mirror','worker'])
def test_partial_failure_can_resume_without_reset_or_duplicate(env, step):
    service, key, meta, p = setup(env)
    original = service.mirror if step == 'mirror' else service.register_worker
    failure = Mock(side_effect=RuntimeError('isolated outage'))
    if step == 'mirror': service.mirror = failure
    else: service.register_worker = failure
    result = service.map(key, ADMIN)
    # Mapping attach atomically registers the worker. A later duplicate enqueue
    # outage may still read back as Mapped because durable registration exists.
    assert result['state'] in ('Pending sync','Mapped'), result
    if step == 'mirror':
        assert result['state'] == 'Pending sync'
        service.mirror = original
        # A later tag edit cannot make a retry rediscover a different product.
        p['tags'] = ['sc-edition-limit-200']
    else:
        env[1].execute('DELETE FROM auto_edition_onboarding')
        assert service.status(key, ADMIN)['state'] == 'Pending sync'
        service.register_worker = original
    assert service.map(key, ADMIN)['state'] == 'Mapped'


def test_no_reset_when_orphaned_history_exists(env):
    service, key, meta, p = setup(env)
    env[1].execute('INSERT INTO edition_orders(shopify_product_gid) VALUES(%s)',(PID,))
    result = service.map(key, ADMIN)
    assert result['state'] == 'Mapping failed', result
    assert read_edition(env[0].connect, PID) is None


def test_duplicate_map_lease_and_cross_account_fail_closed(env):
    service, key, meta, p = setup(env)
    from product_upload_mapping import now
    from datetime import timedelta
    with env[0].locked(key, ADMIN['id']) as (row, cur):
        row['data']['upload_operation']['lease_until'] = (now()+timedelta(minutes=1)).isoformat()
    assert service.map(key, ADMIN)['state'] == 'Mapping…'
    service.shopify.fetch_catalog_page.assert_not_called()
    assert service.status(key,dict(ADMIN,id='another-owner'))['state'] == 'Status unavailable'


def test_prompt_correlates_exact_operation_and_source_changes_rejected(env):
    service, key, meta, p = setup(env)
    row = env[0].read(key, ADMIN['id'])
    text = correlation_prompt(row)
    assert text.count(tag(key)) == 1 and 'initial create call' in text
    assert 'sc-edition-limit-N' in text and 'including drafts' in text
    row['data']['source']['id'] = 'id:other'
    with pytest.raises(ValueError,match='source has changed'):
        correlation_prompt(row)


def test_catalogue_sync_defers_correlated_new_runs_to_map():
    import supabase_backend as db
    import uuid
    p=product(status='ACTIVE',online_store_url='https://fixture/product',tags=[tag(uuid.uuid4())])
    plan=db._plan_edition_product_incremental_sync([p],[])
    assert plan[0]['action']=='skip' and plan[0]['reason']=='awaiting_upload_mapping'
    assert db._plan_edition_product_incremental_sync([p],[],upload_mapping=True)[0]['action']=='insert'
    assert db._plan_edition_product_incremental_sync([dict(p,tags=[])],[])[0]['action']=='insert'


def test_review_mapping_database_guard_rejects_unproven_link(env):
    service,key,meta,p=setup(env)
    sql=env[1]
    with pytest.raises(RuntimeError,match='verified saved upload'):
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual',%s)",
                    (PID,meta['id'],meta['path_display'],ADMIN['id']))
    assert not approved_upload_source(env[0].connect,PID,meta)


def test_double_click_during_provider_call_starts_only_one_attempt(env):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    service,key,meta,p=setup(env)
    entered,release=threading.Event(),threading.Event()
    def catalogue(**kw):
        entered.set();assert release.wait(5)
        return dict(products=[p],has_next_page=False)
    service.shopify.fetch_catalog_page.side_effect=catalogue
    with ThreadPoolExecutor() as pool:
        future=pool.submit(service.map,key,ADMIN)
        assert entered.wait(5)
        second=service.map(key,ADMIN)
        release.set()
        assert second['state']=='Mapping…'
        assert future.result()['state']=='Mapped'
    assert service.shopify.fetch_catalog_page.call_count==1


def test_worker_uses_pinned_review_source_and_rejects_changed_revision(env,monkeypatch):
    from types import SimpleNamespace
    import uuid
    import auto_editions_onboarding_api as api
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    lease=str(uuid.uuid4())
    env[1].execute("UPDATE auto_edition_onboarding SET status='Preparing',lease_token=%s,lease_until=now()+interval '1 hour'",(lease,))
    monkeypatch.setattr(api,'queue',lambda:service.queue)
    integration=SimpleNamespace(psd_open_metadata=lambda *a,**kw:deepcopy(env[2].files[meta['id']]))
    monkeypatch.setattr(api.runtime,'storage',lambda:SimpleNamespace(integration=integration,token='fixture'))
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true')
    context=api.product_context(PID,lease)
    assert context['source']['file_id']==meta['id'] and context['number']==1
    import files_upload_api as files
    manager=files.NativeTransferManager()
    with pytest.raises(files.FilesUploadError,match='outside the approved'):
        manager.create_psd(access_token='fixture',root_path='/Sportscave Team Folder',user=ADMIN,metadata=meta)
    grant=manager.create_psd(access_token='fixture',root_path='/Sportscave Team Folder',user=ADMIN,metadata=meta,
                             product_upload=approved_upload_source(env[0].connect,PID,meta))
    assert grant.items[0]['revision']==meta['rev']
    env[2].files[meta['id']]['rev']='a2'
    with pytest.raises(ValueError,match='approved original|Source revision changed'):
        api.product_context(PID,lease)


def test_http_map_status_prompt_and_access_boundaries(env,monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api,files_upload_api as files,product_upload_mapping as mapping,prompt_store
    service,key,meta,p=setup(env)
    monkeypatch.setattr(api,'connect',env[0].connect)
    monkeypatch.setattr(api,'Dropbox',lambda:env[2])
    monkeypatch.setattr(files,'_request_user',lambda *a,**kw:ADMIN)
    monkeypatch.setattr(mapping,'Mapping',lambda *a,**kw:service)
    monkeypatch.setattr(prompt_store,'get_prompt',lambda key,default,**kw:default)
    client=TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]))
    headers={'Origin':'http://testserver'}
    assert client.post('/api/product-uploads/map',json={'id':key}).status_code==403
    assert client.get('/api/product-uploads/mapping-status?id='+key).json()['mapping']['state']=='Unmapped'
    prompt=client.post('/api/product-uploads/prompt',json={'id':key,'mode':'DRAFT'},headers=headers).json()['prompt']
    assert prompt.startswith('UPLOAD OPERATION CORRELATION') and prompt.count(tag(key))==1
    assert 'clicks MAP' in prompt and 'paste the exact Shopify product name' not in prompt
    assert client.post('/api/product-uploads/map',json={'id':key},headers=headers).json()['mapping']['state']=='Mapped'
    service.map=Mock(side_effect=AssertionError('Refresh cannot map'))
    service.mirror=Mock(side_effect=AssertionError('Refresh cannot sync'))
    service.register_worker=Mock(side_effect=AssertionError('Refresh cannot register'))
    before=env[0].read(key,ADMIN['id'])
    assert client.get('/api/product-uploads/mapping-status?id='+key).json()['mapping']['state']=='Mapped'
    assert env[0].read(key,ADMIN['id'])==before
    assert client.get('/product-upload-mapping.js').status_code==200
    def denied(*a,**kw): raise PermissionError('Sign in again.')
    monkeypatch.setattr(files,'_request_user',denied)
    assert client.get('/api/product-uploads/mapping-status?id='+key).status_code==403
    assert client.post('/api/product-uploads/map',json={'id':key},headers=headers).status_code==403


def test_conflicting_psd_mapping_is_not_replaced(env):
    import uuid
    from product_upload_dropbox import select
    from tests.test_product_upload_dropbox import provider_fixture
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    store,sql,provider=env
    other=provider_fixture(provider)('id:other','Another.psd')
    next_row=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',other['id'],other['rev'])
    next_key=str(next_row['id'])
    with store.locked(next_key,ADMIN['id']) as (row,cur):row['data']['mockups_exported']=True
    p['tags']=[tag(next_key),'sc-edition-limit-200']
    service.shopify.fetch_catalog_page.return_value=dict(products=[p],has_next_page=False)
    result=service.map(next_key,ADMIN)
    assert result['state']=='Mapping failed' and 'another PSD' in result['reason']
    assert service.mappings.read()[PID]['dropbox_file_id']==meta['id']
    assert read_edition(store.connect,PID)['next_edition_number']==1


def test_reused_psd_does_not_redirect_a_new_upload_to_the_old_product(env):
    import uuid
    from product_upload_dropbox import select
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    store,sql,provider=env
    second=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],meta['rev'])
    other_key=str(second['id'])
    with store.locked(other_key,ADMIN['id']) as (row,cur):row['data']['mockups_exported']=True
    service.shopify.fetch_catalog_page.return_value=dict(products=[],has_next_page=False)
    result=service.map(other_key,ADMIN)
    assert result['state']=='Pending sync' and not result.get('product')
    assert not store.read(other_key,ADMIN['id'])['data'].get('product_gid')
    # A correlated different product conflicts with the existing PSD binding;
    # it cannot silently become the old product or replace its mapping.
    other=product(shopify_product_id='gid://shopify/Product/999',tags=[tag(other_key),'sc-edition-limit-200'])
    service.shopify.fetch_catalog_page.return_value=dict(products=[other],has_next_page=False)
    service.shopify.fetch_product_by_shopify_id.side_effect=lambda pid:deepcopy(other)
    result=service.map(other_key,ADMIN)
    assert result['state']=='Mapping failed' and 'different Shopify product' in result['reason']
    assert service.mappings.read()[PID]['dropbox_file_id']==meta['id']


def test_legacy_saved_upload_recovers_through_an_existing_exact_mapping(env):
    import uuid
    service,key,meta,p=setup(env)
    assert service.map(key,ADMIN)['state']=='Mapped'
    old_key=str(uuid.uuid4())
    old=dict(source=meta,mockups_exported=True,mockups_context=dict(folder='/legacy/output'))
    env[1].execute('INSERT INTO product_upload_intakes(id,actor_id,mode,data) VALUES(%s,%s,%s,%s::jsonb)',
                   (old_key,ADMIN['id'],'DRAFT',json.dumps(old)))
    service.shopify.fetch_catalog_page.return_value=dict(products=[],has_next_page=False)
    assert service.map(old_key,ADMIN)['state']=='Mapped'
    assert env[0].read(old_key,ADMIN['id'])['data']['upload_operation']['binding']=='existing_mapping'
