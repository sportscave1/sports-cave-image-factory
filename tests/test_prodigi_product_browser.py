from copy import deepcopy
import json
import pytest
import requests
import prodigi_preparation as prep
import prodigi_product_browser as product
import prodigi_browser as browser
from test_prodigi_preparation import store, Provider, snapshot, value
from test_auto_editions_jobs import database

KEY='prodigi_prepare:1'

@pytest.fixture
def blank(store,monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network forbidden'))
    monkeypatch.setattr(prep,'connect',store)
    provider=Provider();provider.mode='live'
    provider.data['items'][0].update(sku=None,attributes={})
    v=value();v.update(status=product.WAITING,browser_requested=True)
    with store() as c,c.cursor() as q:prep.save(q,v)
    monkeypatch.setattr(browser,'context',lambda _: (provider,lambda _:snapshot(),None,False))
    return provider

def saved():return prep.read(1)

def test_blank_product_is_queued_before_artwork(blank):
    v=value();v['browser_requested']=True
    result=prep.run(v,blank,lambda _:snapshot(),lambda _:pytest.fail('No artwork before product'),lambda _:None)
    assert result['status']==product.WAITING and not blank.writes

def test_permitted_selection_continues_once_to_normal_artwork(blank):
    plan=product.claim();assert plan['sku']=='GLOBAL-CFP-A2' and plan['colour']=='Natural'
    assert product.claim() is None
    with pytest.raises(PermissionError):product.permit(plan['key'],'wrong',plan['sha256'])
    assert product.permit(plan['key'],plan['token'],plan['sha256'])=={'permitted':True}
    with pytest.raises(ValueError):product.permit(plan['key'],plan['token'],plan['sha256'])
    blank.data['items'][0].update(sku=plan['sku'],attributes={'color':'natural'},unitPrice={'amount':'1'})
    assert product.finish(plan['key'],plan['token'])['status']==browser.WAITING
    assert saved()['product_browser']['verified']
    v=saved()
    prep.run(v,blank,lambda _:snapshot(),lambda _:pytest.fail('No API artwork writes'),lambda _:None)
    assert v['status']=='Awaiting browser upload' and not blank.writes
    assert product.finish(plan['key'],plan['token'])['status']==browser.WAITING # persisted stage remains one-time

def test_verified_empty_product_handoff_can_clear_only_its_worker_editor(blank,monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    blank.data['items'][0].update(sku=p['sku'],attributes={'color':'natural'})
    product.finish(p['key'],p['token'])
    monkeypatch.setattr(browser,'context',lambda _: (blank,lambda _:snapshot(),lambda _:('https://fixture.invalid/art','fixture'),False))
    plan=browser.claim(exact_item_supported=True)
    assert plan['selected_empty_product'] is True and plan['item_id']=='88'
    assert saved()['browser']['started'] is False and not blank.writes
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}

@pytest.mark.parametrize('changed',['none','assets','address','started','submission','different_error'])
def test_known_auto_editor_recovery_rechecks_before_retrying(blank,monkeypatch,changed):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    blank.data['items'][0].update(sku=p['sku'],attributes={'color':'natural'})
    product.finish(p['key'],p['token'])
    monkeypatch.setattr(browser,'context',lambda _: (blank,lambda _:snapshot(),lambda _:('https://fixture.invalid/art','fixture'),False))
    plan=browser.claim(exact_item_supported=True)
    assert browser.finish(KEY,plan['token'],'page',error='An existing editor requires manual review.')['status']=='Needs review'
    v=saved()
    if changed=='assets':blank.data['items'][0]['assets']=[{'url':'https://fixture.invalid/new','printArea':'default'}]
    if changed=='address':blank.data['recipient']={'name':'Different destination'}
    if changed=='started':v['browser']['started']=True
    if changed=='submission':v['submission']={'status':'submitted'}
    if changed=='different_error':v['browser']['client_error']='A different error'
    if changed in ('started','submission','different_error'):
        with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    assert browser.recover_selected_empty_editors({'id':'fixture'})==(1 if changed=='none' else 0)
    assert saved()['status']==(browser.WAITING if changed=='none' else 'Needs review')
    assert not blank.writes

@pytest.mark.parametrize('change',[
    lambda o:o.update(status='paused'),lambda o:o.update(charges=[{'amount':1}]),
    lambda o:o['items'][0].update(sku='GLOBAL-CFP-A1'),
    lambda o:o['items'][0].update(quantity=2),
    lambda o:o['items'][0].update(assets=[{'url':'https://fixture.invalid/art','printArea':'default'}]),
])
def test_unsafe_claims_do_not_issue_browser_plan(blank,change):
    change(blank.data)
    assert product.claim() is None
    assert saved()['status']=='Needs review' and not blank.writes

def test_concurrent_customer_or_item_change_blocks_permit(blank):
    p=product.claim();blank.data['recipient']={'name':'Changed'}
    with pytest.raises(ValueError,match='changed'):product.permit(p['key'],p['token'],p['sha256'])
    assert not saved()['product_browser']['started']

@pytest.mark.parametrize('change',[
    lambda o:o['items'][0].update(sku='GLOBAL-CFP-A2-BACKLOADER'),
    lambda o:o['items'][0].update(attributes={'color':'black'}),
    lambda o:o.update(shippingMethod='Express'),
    lambda o:o.update(recipient={'name':'Changed'}),
])
def test_readback_never_accepts_wrong_product_frame_or_business(blank,change):
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    blank.data['items'][0].update(sku=p['sku'],attributes={'color':'natural'})
    change(blank.data)
    assert product.finish(p['key'],p['token'])['status']=='Needs review'
    assert not saved()['product_browser'].get('verified') and not blank.writes

def test_uncertain_selection_is_not_repeated_and_can_be_read_back(blank,monkeypatch):
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    assert product.finish(p['key'],p['token'])['status']=='Needs review'
    assert product.claim() is None
    blank.data['items'][0].update(sku=p['sku'],attributes={'color':'natural'})
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    assert product.recheck({'id':'fixture'},KEY)['status']==browser.WAITING
    assert saved()['product_browser']['verified'] and not blank.writes

def test_preselect_client_error_is_preserved_without_overriding_supplier_truth(blank):
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    assert product.finish(p['key'],p['token'],'product-select',error='Catalogue card unavailable after permit')['status']=='Needs review'
    receipt=saved()['product_browser']
    assert receipt['client_stage']=='product-select' and receipt['client_error']=='Catalogue card unavailable after permit'
    assert 'Companion: Catalogue card unavailable after permit' in saved()['message']
    assert product.claim() is None and not receipt.get('verified') and not blank.writes

@pytest.mark.parametrize('case',['expired','young','changed','ordinary','after_click'])
def test_only_owner_reset_can_retire_an_expired_unchanged_preclick_blank(blank,monkeypatch,case):
    p=product.claim();product.permit(p['key'],p['token'],p['sha256'])
    product.finish(p['key'],p['token'],'product-select' if case!='after_click' else 'product-readback')
    v=saved()
    if case!='young':v['product_browser']['permitted_at']='2020-01-01T00:00:00+00:00'
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    if case=='changed':blank.data['recipient']={'name':'Changed'}
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    try:product.recheck({'id':'fixture'},KEY,allow_expired_blank=case!='ordinary')
    except ValueError:
        assert case=='changed'
    assert ('product_browser' not in saved())==(case=='expired')
    assert not blank.writes

def test_owner_full_reset_requeues_the_proven_expired_blank_without_a_supplier_write(blank,monkeypatch):
    import prodigi_reset
    p=product.claim();product.permit(p['key'],p['token'],p['sha256']);product.finish(p['key'],p['token'],'product-select')
    v=saved();v['product_browser']['permitted_at']='2020-01-01T00:00:00+00:00'
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    monkeypatch.setattr(prep,'require_user',lambda _:None);monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(prep,'preparation_snapshot',lambda *_:(snapshot(),False))
    monkeypatch.setattr(prep,'Client',lambda:blank)
    result=prodigi_reset.reset_order({'id':'fixture'},1)
    assert result['status']=='Queued' and result['reset_generation'] and not result.get('product_browser')
    assert not blank.writes and not blank.data['items'][0]['sku']
import os_pages

@pytest.mark.parametrize('reference',os_pages.PRODIGI_REFERENCE_MAPPINGS)
def test_all_16_original_mappings_select_and_verify(blank,reference,monkeypatch):
    snap=snapshot()
    snap['mapping']=os_pages.prodigi_mapping_for_variant(reference['sports_cave_variant'])
    v=value();v.update(snapshot=snap,fingerprint=prep.digest(snap),status=product.WAITING,browser_requested=True)
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    monkeypatch.setattr(browser,'context',lambda _: (blank,lambda _:deepcopy(snap),None,False))
    plan=product.claim()
    assert plan['sku']==reference['prodigi_code']
    assert plan['colour']==('' if reference['sports_cave_frame']=='Unframed' else reference['prodigi_frame_colour'])
    product.permit(plan['key'],plan['token'],plan['sha256'])
    blank.data['items'][0].update(sku=plan['sku'],attributes={'color':plan['colour'].lower()} if plan['colour'] else {})
    assert product.finish(plan['key'],plan['token'])['status']==browser.WAITING
    assert saved()['product_browser']['verified']
def test_multiple_blank_items_are_targeted_by_id_and_serialised(blank):
    blank.data['items'].append(dict(id='89',merchantReference='other-line',sku=None,quantity=1,assets=[]))
    p=product.claim();assert p['item_id']=='88'
    v=value();v.update(allocation_id=2,item_id='89',status=product.WAITING,browser_requested=True)
    v['snapshot']['identity']['line_id']='other-line';v['fingerprint']=prep.digest(v['snapshot'])
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    assert product.claim() is None
    product.permit(p['key'],p['token'],p['sha256'])
    blank.data['items'][0].update(sku=p['sku'],attributes={'color':'natural'})
    assert product.finish(p['key'],p['token'])['status']==browser.WAITING
    assert blank.data['items'][1]['sku'] is None
