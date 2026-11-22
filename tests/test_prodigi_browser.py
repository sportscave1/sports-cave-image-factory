from copy import deepcopy
from urllib.parse import urlencode
import json
import pytest
import requests

import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_sandbox as sandbox
from test_prodigi_sandbox import source,SandboxProvider
from test_prodigi_preparation import store
from test_auto_editions_jobs import database

KEY=sandbox.PREFIX+'00000000-0000-4000-8000-000000000001'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','true')
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_FULL_QA_ENABLED','false')
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network forbidden'))


def render_url(**changes):
    params=dict(product_id='edit',variant='cover:4200x5940',print_image='true',format='png',debug='false',
        image='https://live-services.pwinty.com/synthetic-original',scale='1',rotate='0',translate='0,0',border='0px',tile='false')
    params.update(changes)
    return 'https://productimagegenerator.services.prodigi.com/render/?'+urlencode(params)


@pytest.fixture
def handoff(store,monkeypatch):
    monkeypatch.setattr(prep,'connect',store)
    original=source()
    snap=sandbox.adapted(original,'SC-SANDBOX-fixture',original['recipient']); snap['dimensions']=[4200,5940]
    provider=SandboxProvider();provider.created={}
    provider.create_draft(sandbox.payload(snap),'fixture')
    provider.assets=lambda:[{'id':'asset-id','name':sandbox.list_tests()[0]['browser']['filename'].removesuffix('.jpg'),
        'sizeBytes':snap['output']['bytes'],'mimeType':'image/jpeg',
        'dimensions':{'widthPx':4200,'heightPx':5940},'url':'https://synthetic.blob.core.windows.net/original'}]
    provider.asset=lambda _: {'url':'https://live-services.pwinty.com/synthetic-original'}
    value=dict(id=KEY.split(':')[1],allocation_id=1,source_snapshot=snap,snapshot=snap,
        fingerprint=prep.digest(snap),status=browser.WAITING,checks={},history=[],
        order_id='99',item_id='88',environment='sandbox',hidden=False)
    with store() as c,c.cursor() as q:sandbox.save(q,value)
    monkeypatch.setattr(browser,'context',lambda _: (provider,lambda _:deepcopy(snap),lambda _:('https://fixture.invalid/source','a'*32),True))
    return store,provider,value


def test_claim_save_permit_and_independent_source_verification(handoff,monkeypatch):
    store,provider,value=handoff
    plan=browser.claim()
    assert plan['order_url']=='https://sandbox-beta-dashboard.pwinty.com/orders/99/detail'
    assert browser.claim() is None
    with pytest.raises(PermissionError):browser.permit(KEY,'wrong',plan['sha256'])
    with pytest.raises(ValueError,match='exact numbered'):browser.permit(KEY,plan['token'],'wrong')
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}
    with pytest.raises(ValueError,match='already'):browser.permit(KEY,plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    provider.data['items'][0].update(unitPrice={'amount':'52.00','currency':'USD'},
        lineTotal={'amount':'52.00','currency':'USD'})
    verified=[]
    monkeypatch.setattr(browser,'verify_file',lambda url,output:verified.append((url,output)))
    assert browser.finish(KEY,plan['token'])['status']=='Needs QA'
    assert len(verified)==1 and verified[0][0]=='https://synthetic.blob.core.windows.net/original'
    assert browser.finish(KEY,plan['token'])['status']=='Needs QA'
    assert len(verified)==1  # Replayed completion never repeats work.
    saved=sandbox.list_tests()[0]
    assert saved['browser']['verified'] and saved['browser']['full_image_fit_verified']
    assert saved['sandbox_unpaid_verified'] and saved['artwork_readback_verified']
    assert len(provider.writes)==1 and provider.data['status']=='draft'


@pytest.mark.parametrize('change',[
    lambda p:p.data.update(status='in_production'),
    lambda p:p.data['items'][0].update(sku='different'),
    lambda p:p.data['items'][0].update(quantity=2),
    lambda p:p.data['items'][0].update(unitPrice={'amount':'52.00','currency':'USD'}),
])
def test_changed_supplier_order_blocks_save_before_browser_mutation(handoff,change):
    _,provider,_=handoff;plan=browser.claim();change(provider)
    with pytest.raises(ValueError):browser.permit(KEY,plan['token'],plan['sha256'])
    assert not provider.writes


@pytest.mark.parametrize('field,value',[('sku','changed'),('quantity',2),('attributes',{'color':'Black'})])
def test_after_save_price_calculation_does_not_hide_product_changes(handoff,monkeypatch,field,value):
    _,provider,_=handoff;plan=browser.claim();browser.permit(KEY,plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    provider.data['items'][0].update(unitPrice={'amount':'52.00','currency':'USD'},**{field:value})
    monkeypatch.setattr(browser,'verify_file',lambda *_:True)
    assert browser.finish(KEY,plan['token'])['status']=='Needs review'
    assert not sandbox.list_tests()[0]['browser'].get('verified')


def test_interrupted_upload_is_reviewed_without_another_browser_claim(handoff):
    _,provider,_=handoff;plan=browser.claim()
    assert browser.finish(KEY,plan['token'])['status']=='Needs review'
    assert browser.claim() is None and not provider.writes


def test_removed_or_superseded_receipt_cannot_block_the_next_desktop_tick(handoff):
    store,provider,_=handoff;plan=browser.claim()
    assert browser.finish(KEY,'superseded')['status']=='Handoff unavailable'
    assert sandbox.list_tests()[0]['status']=='Browser uploading'
    with store() as c,c.cursor() as q:
        q.execute("UPDATE app_settings SET value=jsonb_set(value,'{hidden}','true'::jsonb) WHERE key=%s",(KEY,))
    assert browser.finish(KEY,plan['token'])['status']=='Handoff unavailable'
    assert sandbox.list_tests()[0]['hidden'] is True and not provider.writes


def test_checksum_mismatch_cannot_become_ready(handoff,monkeypatch):
    _,provider,_=handoff;plan=browser.claim();browser.permit(KEY,plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    def mismatch(*_):raise ValueError('Supplier artwork does not match the exact archive.')
    monkeypatch.setattr(browser,'verify_file',mismatch)
    assert browser.finish(KEY,plan['token'])['status']=='Needs review'
    assert not sandbox.list_tests()[0]['browser'].get('verified')


def test_staff_recheck_reads_uncertain_save_without_another_upload_or_permit(handoff,monkeypatch):
    _,provider,_=handoff;plan=browser.claim()
    allowed=[]
    monkeypatch.setattr(prep,'require_user',lambda user:allowed.append(user))
    assert browser.recheck({'id':'staff'},KEY)['status']=='Handoff unavailable'
    browser.permit(KEY,plan['token'],plan['sha256'])
    assert browser.finish(KEY,plan['token'])['status']=='Needs review'
    provider.artwork('99','88',render_url(),'a'*32)
    provider.data['items'][0].update(unitPrice={'amount':'52.00','currency':'USD'})
    monkeypatch.setattr(browser,'verify_file',lambda *_:True)
    assert browser.recheck({'id':'staff'},KEY)['status']=='Needs QA'
    assert len(provider.writes)==1 and len(allowed)==2
    assert browser.claim() is None
    with pytest.raises(ValueError,match='already'):
        browser.permit(KEY,plan['token'],plan['sha256'])


@pytest.mark.parametrize('changes',[
    {'rotate':'90'},{'translate':'1,0'},{'border':'1px'},{'tile':'true'},
    {'scale':'2'},{'scale':'NaN'},{'variant':'cover:5940x4200'},
    {'image':'http://127.0.0.1/private'},{'extra':'unknown'},
])
def test_unverified_crop_and_external_original_sources_are_rejected(changes):
    with pytest.raises(ValueError):browser.original_file(render_url(**changes),[4200,5940])


def test_exact_full_fit_geometry_and_source_are_required():
    assert browser.original_file(render_url(),[4200,5940]).startswith('https://live-services.pwinty.com/')
    with pytest.raises(ValueError,match='full-image'):browser.original_file(render_url(),[4000,5940])


def test_one_click_send_queues_only_the_selected_allocation(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import os_accounts
    calls=[]
    monkeypatch.setattr(os_accounts,'is_admin',lambda _:True)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(prep,'request',lambda actor,allocation: calls.append(allocation) or {'message':'Waiting for companion'})
    app=AppTest.from_string('import orders_page\norders_page._render_send_artwork({"edition_order_id":123},"test")').run()
    app.button(key='orders-send-test-123').click().run()
    assert not app.exception and calls==[123]


def test_required_empty_slot_is_not_an_artwork_file_and_is_pinned_until_save(handoff):
    _,provider,_=handoff
    slot=dict(id='print-area-slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)
    provider.data['items'][0]['assets']=[slot]
    assert not browser.has_existing_artwork(provider.data['items'][0])
    plan=browser.claim();assert plan and plan['sku']==provider.data['items'][0]['sku']
    provider.data['items'][0]['assets'][0]['id']='another-slot'
    with pytest.raises(ValueError,match='changed'):browser.permit(KEY,plan['token'],plan['sha256'])
    provider.data['items'][0]['assets'][0]['id']='print-area-slot'
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}
    assert not provider.writes


@pytest.mark.parametrize('change',[
    dict(url='https://fixture.invalid/existing.jpg'),dict(assetId='real-asset'),dict(status='Complete'),
    dict(pageCount=1),dict(pageCount=False),dict(required=False),dict(printArea='back')])
def test_unknown_or_real_assets_are_never_treated_as_empty_slots(change):
    slot=dict(id='slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)
    slot.update(change)
    assert browser.has_existing_artwork(dict(assets=[slot]))

def test_updated_companion_can_pin_one_of_two_identical_product_rows(handoff):
    _,provider,_=handoff
    second=deepcopy(provider.data['items'][0]);second.update(id='89',merchantReference='other-line')
    provider.data['items'].append(second)
    plan=browser.claim(exact_item_supported=True)
    assert plan['item_id']=='88' and plan['exact_item'] is True
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}

def test_restart_before_save_retires_old_token_only_after_untouched_readback(handoff,monkeypatch):
    _,provider,_=handoff;old=browser.claim()
    browser.finish(KEY,old['token'],'readback')
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    assert browser.resume_unstarted({'id':'owner'},KEY)['status']==browser.WAITING
    new=browser.claim();assert new['token']!=old['token']
    assert browser.finish(KEY,old['token'])['status']=='Handoff unavailable'
    assert not provider.writes

@pytest.mark.parametrize('change',[
    lambda p:p.data['items'][0].update(assets=[dict(url='https://fixture/art',printArea='default')]),
    lambda p:p.data.update(recipient={'name':'Changed'}),
])
def test_restart_never_overwrites_artwork_or_business_changes(handoff,monkeypatch,change):
    _,provider,_=handoff;old=browser.claim();browser.finish(KEY,old['token'])
    monkeypatch.setattr(prep,'require_user',lambda _:None);change(provider)
    with pytest.raises(ValueError,match='changed'):browser.resume_unstarted({'id':'owner'},KEY)
    assert not provider.writes
