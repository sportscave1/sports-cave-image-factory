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
    assert product.finish(plan['key'],plan['token'])['status']=='Queued'
    assert saved()['product_browser']['verified']
    v=saved()
    prep.run(v,blank,lambda _:snapshot(),lambda _:pytest.fail('No API artwork writes'),lambda _:None)
    assert v['status']=='Awaiting browser upload' and not blank.writes
    assert product.finish(plan['key'],plan['token'])['status']=='Queued' # persisted stage remains one-time

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
    assert product.recheck({'id':'fixture'},KEY)['status']=='Queued'
    assert saved()['product_browser']['verified'] and not blank.writes
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
    assert product.finish(plan['key'],plan['token'])['status']=='Queued'
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
    assert product.finish(p['key'],p['token'])['status']=='Queued'
    assert blank.data['items'][1]['sku'] is None
