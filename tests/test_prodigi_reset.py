from copy import deepcopy
import json
import pytest
import requests
import prodigi_preparation as prep
import prodigi_browser as browser
import prodigi_reset as reset
import prodigi_dashboard_qa as qa
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
from test_prodigi_dashboard_qa import fixture


@pytest.fixture
def draft(store,monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network forbidden'))
    v,s,p,_=fixture();v.update(status='Needs review',write_intent=True,checks={k:True for k in qa.CHECKS})
    v['browser'].update(token_hash=prep.digest('retired'),started=True)
    v['dashboard_qa']=dict(token_hash=prep.digest('old-qa'),claimed_at=prep.now(),policy=qa.POLICY,started=True)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(prep,'resolve',lambda _:deepcopy(s))
    monkeypatch.setattr(prep,'Client',lambda:p)
    monkeypatch.setattr('prodigi_full_qa.live_enabled',lambda:False)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    monkeypatch.setattr(browser,'context',lambda _:(p,prep.resolve,lambda _:('https://fixture/artwork','checksum'),False))
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    return p,s


def test_full_reset_keeps_identity_archives_receipts_and_reuploads_existing_artwork(draft):
    p,s=draft;before=deepcopy(p.data)
    v=reset.reset_order({'id':'owner'},1)
    assert v['status']=='Queued' and not v.get('browser') and not v.get('write_intent') and not v.get('dashboard_qa')
    assert v['checks']=={} and v['order_id']=='99' and v['item_id']=='88' and v['snapshot']==s
    assert not p.writes and p.data==before # No removal or empty-image save.
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_reset_history:1:%%'")
        archived=q.fetchall();assert len(archived)==1 and archived[0]['value']['browser']['token_hash']==prep.digest('retired')
    assert reset.reset_order({'id':'owner'},1)['reset_generation']==v['reset_generation']
    prep.run(v,p,prep.resolve,None,lambda value:save(value))
    assert browser.claim(exact_item_supported=True) is None # Old workers cannot replace artwork.
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    assert plan['replace_artwork'] is True and plan['item_id']=='88'
    assert browser.finish(prep.PREFIX+'1','retired')['status']=='Handoff unavailable'
    assert qa.finish(prep.PREFIX+'1','old-qa',None)['status']=='Handoff unavailable'
    assert browser.permit(plan['key'],plan['token'],plan['sha256'])=={'permitted':True}
    assert prep.read(1)['reset_authorisation']['used_at']
    assert not p.writes and p.data==before


def save(value):
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)


@pytest.mark.parametrize('change',[
    lambda v,p:v.update(submission={'intent_at':'recorded'}),
    lambda v,p:p.data.update(charges=[{'id':'paid'}]),
    lambda v,p:p.data.update(status='paused'),
    lambda v,p:p.data.update(shipments=[{'id':'shipped'}]),
    lambda v,p:p.data.update(statusHistory=[dict(status='in_production')]),
    lambda v,p:p.data['items'][0].update(merchantReference='another-line'),
    lambda v,p:p.data['items'][0].update(quantity=2),
])
def test_reset_never_touches_submitted_paid_production_or_unidentified_items(draft,change):
    p,s=draft;v=prep.read(1);change(v,p);save(v)
    with pytest.raises(ValueError):reset.reset_order({'id':'owner'},1)
    assert not prep.read(1).get('reset_generation') and not p.writes


def test_supplier_wide_submission_fence_blocks_sibling_reset(draft):
    with prep.connect() as c,c.cursor() as q:
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',('prodigi_submit_order:99',json.dumps({'allocation_id':2})))
    with pytest.raises(ValueError,match='submission intent'):reset.reset_order({'id':'owner'},1)


@pytest.mark.parametrize('change',[
    lambda p:p.data['items'][0]['assets'][0].update(url='https://fixture/other'),
    lambda p:p.data['recipient']['address'].update(line1='Other address'),
    lambda p:p.data['items'][0]['attributes'].update(color='Black'),
])
def test_reset_replacement_still_requires_unchanged_supplier_readback_before_save(draft,change):
    p,s=draft;v=reset.reset_order({'id':'owner'},1);prep.run(v,p,prep.resolve,None,save)
    plan=browser.claim(exact_item_supported=True,reset_supported=True);change(p)
    with pytest.raises(ValueError):browser.permit(plan['key'],plan['token'],plan['sha256'])
    assert not prep.read(1)['browser']['started'] and not p.writes


def test_active_uncertain_save_is_not_revoked_or_repeated(draft,monkeypatch):
    v=prep.read(1);v['browser']['verified']=False;v['status']='Browser uploading';save(v)
    monkeypatch.setattr(browser,'recheck',lambda *_:pytest.fail('Do not race an active Save'))
    with pytest.raises(ValueError,match='in progress'):reset.reset_order({'id':'owner'},1)
    assert not prep.read(1).get('reset_generation')


def test_group_reset_invalidates_sibling_qa_without_resetting_its_saved_artwork(draft):
    p,s=draft;b=prep.read(1);b.update(allocation_id=2,item_id='89');b['snapshot']['allocation_id']=2;save(b)
    reset.reset_order({'id':'owner'},1)
    sibling=prep.read(2)
    assert sibling['status']=='Checking QA' and sibling['checks']=={}
    assert sibling['browser']['verified'] and not sibling.get('dashboard_qa')


@pytest.mark.parametrize('assets',[[],[dict(id='empty-slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)]])
def test_full_reset_of_unsaved_upload_refreshes_owned_editor_without_replacing_artwork(draft,assets):
    p,s=draft;p.data['items'][0]['assets']=deepcopy(assets)
    v=reset.reset_order({'id':'owner'},1)
    assert 'product_browser' not in v
    prep.run(v,p,prep.resolve,None,save)
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    assert plan['selected_empty_product'] is True
    assert 'replace_artwork' not in plan and plan['item_id']=='88'
    assert not prep.read(1)['browser']['started'] and not p.writes
    assert browser.permit(plan['key'],plan['token'],plan['sha256'])=={'permitted':True}


def test_unreset_empty_item_has_no_authority_to_clear_an_unsaved_editor(draft):
    p,s=draft;p.data['items'][0]['assets']=[]
    v=prep.read(1)
    for key in ('browser','dashboard_qa','write_intent'):v.pop(key,None)
    v.update(status=browser.WAITING,browser_requested=True);save(v)
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    assert 'selected_empty_product' not in plan and 'replace_artwork' not in plan
    assert not p.writes


@pytest.mark.parametrize('change',['address','asset','generation','used'])
def test_empty_reset_refresh_requires_unchanged_unconsumed_reset_authority(draft,change):
    p,s=draft;p.data['items'][0]['assets']=[]
    v=reset.reset_order({'id':'owner'},1);prep.run(v,p,prep.resolve,None,save)
    if change=='address':p.data['recipient']['address']['line1']='Other fixture address'
    if change=='asset':p.data['items'][0]['assets']=[dict(id='different-empty-slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)]
    if change in ('generation','used'):
        v=prep.read(1)
        if change=='generation':v['reset_generation']='different-generation'
        else:v['reset_authorisation']['used_at']=prep.now()
        save(v)
    assert browser.claim(exact_item_supported=True,reset_supported=True) is None
    assert prep.read(1)['status']=='Needs review' and not p.writes


def test_empty_reset_requires_capable_worker_before_refresh_handoff(draft):
    p,s=draft;p.data['items'][0]['assets']=[]
    v=reset.reset_order({'id':'owner'},1);prep.run(v,p,prep.resolve,None,save)
    assert browser.claim(exact_item_supported=True,reset_supported=False) is None
    assert browser.claim(exact_item_supported=False,reset_supported=True) is None
    assert not prep.read(1).get('browser') and not p.writes


@pytest.mark.parametrize('case',['unchanged','changed_address','saved_asset','used_permit','exhausted'])
def test_empty_reset_readiness_recovers_once_without_new_owner_click(draft,case):
    p,s=draft;p.data['items'][0]['assets']=[]
    v=reset.reset_order({'id':'owner'},1);prep.run(v,p,prep.resolve,None,save)
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    browser.finish(plan['key'],plan['token'],'signin',error='Sign into Prodigi in Edge, then review the same draft.')
    v=prep.read(1)
    if case=='changed_address':p.data['recipient']['address']['line1']='Changed fixture address'
    if case=='saved_asset':p.data['items'][0]['assets']=[dict(url='https://fixture/new',printArea='default')]
    if case=='used_permit':v['browser']['started']=True
    if case=='exhausted':v['readiness_recoveries']=1
    save(v)
    assert browser.recover_selected_empty_editors({'id':'owner'})==(1 if case=='unchanged' else 0)
    assert not p.writes
    if case=='unchanged':
        next_plan=browser.claim(exact_item_supported=True,reset_supported=True)
        assert next_plan['token']!=plan['token'] and next_plan['selected_empty_product']
        assert not prep.read(1)['browser']['started'] and prep.read(1)['readiness_recoveries']==1



def test_fixed_page_ready_worker_gets_one_new_guarded_recovery_budget(draft):
    p,s=draft;p.data['items'][0]['assets']=[]
    v=reset.reset_order({'id':'owner'},1);prep.run(v,p,prep.resolve,None,save)
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    browser.finish(plan['key'],plan['token'],'signin',error='Sign into Prodigi in Edge, then review the same draft.')
    v=prep.read(1);v['readiness_recoveries']=1;save(v)
    assert browser.recover_selected_empty_editors({'id':'owner'})==0
    assert browser.recover_selected_empty_editors({'id':'owner'},page_supported=True)==1
    next_plan=browser.claim(exact_item_supported=True,reset_supported=True)
    browser.finish(next_plan['key'],next_plan['token'],'readiness',error='The exact Prodigi order page did not become ready; check its loading or sign-in state.')
    assert browser.recover_selected_empty_editors({'id':'owner'},page_supported=True)==0
    assert prep.read(1)['readiness_recovery_policy']==browser.READINESS_POLICY and not p.writes
