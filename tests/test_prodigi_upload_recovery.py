"""Synthetic ordinary preconfigured-item upload waits, with real durable fencing."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import pytest
import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_upload_recovery as recovery
from test_prodigi_browser import handoff, offline, KEY as SANDBOX_KEY
from test_prodigi_preparation import store
from test_auto_editions_jobs import database

KEY='prodigi_prepare:1'


@pytest.fixture
def waiting(handoff, monkeypatch):
    store, provider, value = handoff
    _, resolver, link, _ = browser.context(SANDBOX_KEY)
    provider.mode='live'
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(browser,'context',lambda _: (provider,resolver,link,False))
    monkeypatch.setattr(browser,'verify_file',lambda *_:True)
    value.update(browser_requested=True)
    with store() as c,c.cursor() as q:
        q.execute('DELETE FROM app_settings WHERE key=%s',(SANDBOX_KEY,))
        prep.save(q,value)
    plan=browser.claim(exact_item_supported=True)
    provider.assets=lambda:[dict(id='asset-id',name=plan['filename'].removesuffix('.jpg'),
        sizeBytes=value['snapshot']['output']['bytes'],mimeType='image/jpeg',
        dimensions=dict(widthPx=4200,heightPx=5940),url='https://synthetic.blob.core.windows.net/original')]
    browser.finish(KEY,plan['token'],'uploaded',error='The expected Prodigi control did not finish loading.')
    return store,provider,plan,resolver


def write(store,value):
    with store() as c,c.cursor() as q:prep.save(q,value)


def test_existing_product_recovers_original_asset_without_reset_or_repeating_save(waiting):
    _,provider,old,_=waiting
    assert not prep.read(1).get('product_browser') and not prep.read(1).get('reset_authorisation')
    assert recovery.recover({'id':'owner'})==1
    assert recovery.recover({'id':'owner'})==0
    assert recovery.recover({'id':'owner'})==0 # deferred candidate does not monopolise later polls
    assert browser.claim(exact_item_supported=True) is None # old desktop cannot claim new authority
    assert browser.finish(KEY,old['token'])['status']=='Handoff unavailable'
    with pytest.raises(PermissionError):browser.permit(KEY,old['token'],old['sha256'])
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assert plan['fresh_empty_item'] is True and plan['library_asset_id']=='asset-id'
    assert plan['filename']==old['filename'] and plan['token']!=old['token']
    assert not plan.get('replace_artwork') and not plan.get('selected_empty_product')
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}
    with pytest.raises(ValueError):browser.permit(KEY,plan['token'],plan['sha256'])
    assert not provider.writes


def test_missing_library_original_uses_fresh_same_item_upload(waiting):
    _,provider,old,_=waiting;provider.assets=lambda:[]
    assert recovery.recover({'id':'owner'})==1
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assert plan['fresh_empty_item'] and not plan.get('library_asset_id')
    assert plan['filename']!=old['filename'] and plan['order_id']==old['order_id']


@pytest.mark.parametrize('stage,error',[
    ('download','The pinned JPG is unavailable.'),
    ('open','Failed to fetch'),
    ('open','The woken order page did not expose its identity.'),
    ('signin','Prodigi sign-in expired. Sign into Prodigi in Edge, then recheck this same order to resume. No supplier action was repeated.'),
    ('readiness','The exact Prodigi order page did not become ready; check its loading or sign-in state.'),
    ('picker','The expected Prodigi control did not finish loading.'),
    ('uploaded','Prodigi image upload did not finish within the allowed time.'),
    ('uploaded','Prodigi image library stayed busy after the uploaded image became available.'),
    ('uploaded','Prodigi image selection did not finish after the verified library image became ready.'),
    ('transfer','Pinned artwork transfer interrupted.'),
    ('permit','The draft changed before Save.'),
])
def test_known_temporary_prepermit_failures_keep_ordinary_orders_recoverable(waiting,stage,error):
    store,provider,_,_=waiting;value=prep.read(1)
    value['browser'].update(last_stage=stage,client_error=error);write(store,value)
    assert recovery.recover({'id':'owner'})==1
    assert not prep.read(1).get('browser') and not provider.writes


@pytest.mark.parametrize('change',['recipient','quantity','artwork','shipping','source','save','submission','intent','hidden','unknown'])
def test_changed_or_consumed_work_is_never_recovered(waiting,change):
    store,provider,_,resolver=waiting;value=prep.read(1)
    if change=='recipient':provider.data['recipient']={'name':'Changed synthetic recipient'}
    if change=='quantity':provider.data['items'][0]['quantity']=2
    if change=='artwork':provider.data['items'][0]['assets']=[{'url':'unexpected.jpg'}]
    if change=='shipping':provider.data['shippingMethod']='Express'
    if change=='source':value['snapshot']['output']['sha256']='f'*64
    if change=='save':value['browser']['started']=True
    if change=='submission':value['submission']={'status':'submitted'}
    if change=='intent':value['write_intent']=True
    if change=='hidden':value['hidden']=True
    if change=='unknown':value['browser']['client_error']='Unknown error'
    write(store,value)
    assert recovery.recover({'id':'owner'})==0
    assert prep.read(1).get('browser') and not provider.writes


@pytest.mark.parametrize('change',['recipient','quantity','artwork','shipping','source','save','submission'])
def test_legacy_missing_page_identity_never_bypasses_saved_order_guards(waiting,change):
    store,provider,_,_=waiting;value=prep.read(1)
    value['browser'].update(last_stage='open',client_error='The woken order page did not expose its identity.')
    if change=='recipient':provider.data['recipient']={'name':'Changed synthetic recipient'}
    if change=='quantity':provider.data['items'][0]['quantity']=2
    if change=='artwork':provider.data['items'][0]['assets']=[{'url':'unexpected.jpg'}]
    if change=='shipping':provider.data['shippingMethod']='Express'
    if change=='source':value['snapshot']['output']['sha256']='f'*64
    if change=='save':value['browser']['started']=True
    if change=='submission':value['submission']={'status':'submitted'}
    write(store,value)
    assert recovery.recover({'id':'owner'})==0
    assert prep.read(1).get('browser') and not provider.writes


def test_repeated_transient_wait_backs_off_and_keeps_original_receipt(waiting):
    store,provider,old,_=waiting
    assert recovery.recover({'id':'owner'})==1
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    browser.finish(KEY,plan['token'],'uploaded',error='The expected Prodigi control did not finish loading.')
    assert recovery.recover({'id':'owner'})==0
    value=prep.read(1);value['upload_recovery']['retry_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    value['upload_recovery']['attempts']=30;write(store,value)
    assert recovery.recover({'id':'owner'})==1
    value=prep.read(1);assert value['upload_recovery']['attempts']==31
    wait=(datetime.fromisoformat(value['upload_recovery']['retry_at'])-datetime.now(timezone.utc)).total_seconds()
    assert 890<wait<=900 and not provider.writes


@pytest.mark.parametrize('change',['duplicate','bytes','dimensions','id','hash','unavailable'])
def test_library_reuse_requires_unique_verified_original(waiting,monkeypatch,change):
    _,provider,_,_=waiting;assets=provider.assets()
    if change=='duplicate':assets.append(deepcopy(assets[0]))
    if change=='bytes':assets[0]['sizeBytes']+=1
    if change=='dimensions':assets[0]['dimensions']['widthPx']+=1
    if change=='id':assets[0]['id']='invalid/id'
    if change=='hash':monkeypatch.setattr(browser,'verify_file',lambda *_: (_ for _ in ()).throw(ValueError('Checksum mismatch')))
    if change=='unavailable':monkeypatch.setattr(browser,'verify_file',lambda *_:False)
    provider.assets=lambda:assets
    assert recovery.recover({'id':'owner'})==int(change=='unavailable')
    if change=='unavailable':assert prep.read(1)['upload_recovery']['asset_id'] is None
    else:assert prep.read(1)['browser']['started'] is False
    assert not provider.writes


def test_changed_library_asset_between_claim_and_permit_stays_unconsumed(waiting):
    _,provider,_,_=waiting
    assert recovery.recover({'id':'owner'})==1
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assets=provider.assets();assets[0]['id']='another-asset';provider.assets=lambda:assets
    with pytest.raises(ValueError,match='changed before Save'):browser.permit(KEY,plan['token'],plan['sha256'])
    assert prep.read(1)['browser']['started'] is False and not provider.writes


def test_one_bad_recovery_does_not_cancel_other_ready_orders(waiting,monkeypatch):
    monkeypatch.setattr(recovery,'recover_one',lambda _:(_ for _ in ()).throw(RuntimeError('Synthetic dependency unavailable')))
    assert recovery.recover({'id':'owner'})==0


@pytest.fixture
def page_retry(waiting):
    store,provider,original,resolver=waiting
    original_assets=deepcopy(provider.assets());provider.assets=lambda:[]
    assert recovery.recover({'id':'owner'})==1
    second=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assert second['filename']!=original['filename']
    browser.finish(KEY,second['token'],'open',error='The woken order page did not expose its identity.')
    value=prep.read(1)
    # Reproduce the legacy recovery losing the older filename after a page-only
    # attempt. The completed original now exists only in the retained history.
    value['upload_recovery'].update(filename=second['filename'],
        retry_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    write(store,value);provider.assets=lambda:deepcopy(original_assets)
    return store,provider,original,second,original_assets


@pytest.mark.parametrize('legacy',[False,True])
def test_late_original_upload_survives_intervening_page_failure_without_reset(page_retry,legacy):
    store,provider,original,second,assets=page_retry
    if legacy:
        value=prep.read(1);value['browser_history'][0].pop('source_sha256',None);write(store,value)
    reads=[];provider.assets=lambda:reads.append('assets') or deepcopy(assets)
    assert recovery.recover({'id':'owner'})==1
    assert reads==['assets'] # One listing covers the bounded receipt history.
    assert prep.read(1)['upload_recovery']['filename']==original['filename']
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assert plan['filename']==original['filename'] and plan['library_asset_id']=='asset-id'
    assert plan['fresh_empty_item'] is True and plan['token'] not in (original['token'],second['token'])
    assert browser.finish(KEY,second['token'])['status']=='Handoff unavailable'
    with pytest.raises(PermissionError):browser.permit(KEY,second['token'],second['sha256'])
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}
    with pytest.raises(ValueError):browser.permit(KEY,plan['token'],plan['sha256'])
    assert not provider.writes


@pytest.mark.parametrize('change',['allocation','job','source','consumed'])
def test_upload_history_cannot_claim_another_source_or_consumed_receipt(page_retry,change):
    store,provider,_,_,assets=page_retry;value=prep.read(1);row=value['browser_history'][0]
    if change=='allocation':row['filename']=row['filename'].replace('SC-1-','SC-2-')
    if change=='job':row['filename']='SC-1-another-source-aaaaaaaa.jpg'
    if change=='source':row['source_sha256']='f'*64
    if change=='consumed':row['started']=True
    write(store,value)
    assert recovery.recover({'id':'owner'})==1
    assert prep.read(1)['upload_recovery']['asset_id'] is None and not provider.writes


@pytest.mark.parametrize('change',['duplicate','bytes','dimensions','hash'])
def test_historical_original_still_requires_unique_metadata_and_full_checksum(page_retry,monkeypatch,change):
    _,provider,_,_,assets=page_retry
    if change=='duplicate':assets.append(deepcopy(assets[0]))
    if change=='bytes':assets[0]['sizeBytes']+=1
    if change=='dimensions':assets[0]['dimensions']['widthPx']+=1
    if change=='hash':monkeypatch.setattr(browser,'verify_file',lambda *_:(_ for _ in ()).throw(ValueError('Checksum mismatch')))
    provider.assets=lambda:deepcopy(assets)
    assert recovery.recover({'id':'owner'})==0
    assert prep.read(1)['browser']['started'] is False and not provider.writes
