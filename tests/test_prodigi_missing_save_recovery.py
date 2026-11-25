"""Consumed Save recovery uses independent empty reads and verified originals."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import pytest
import prodigi_browser as browser
import prodigi_preparation as prep
from test_prodigi_upload_recovery import waiting, write, KEY
from test_prodigi_browser import handoff, offline, render_url
from test_prodigi_preparation import store
from test_auto_editions_jobs import database


def ago(seconds):
    return (datetime.now(timezone.utc)-timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def missing(waiting,monkeypatch):
    store,provider,plan,resolver=waiting
    import inbox_companion
    monkeypatch.setattr(inbox_companion,'submission_guard',lambda _:None)
    value=prep.read(1);value.update(status='Browser uploading')
    value['browser'].pop('client_error',None);write(store,value)
    browser.permit(KEY,plan['token'],plan['sha256'])
    assert browser.finish(KEY,plan['token'],'save')['status']=='Needs review'
    value=prep.read(1);value['browser']['save_permitted_at']=ago(120);write(store,value)
    return store,provider,plan,resolver


def observe_twice(store):
    assert browser.recover_saved_uploads({'id':'owner'})==0
    value=prep.read(1)
    assert value['missing_save_recovery']['attempts']==0
    value['missing_save_recovery'].update(observed_at=ago(31),next_check_at=ago(1));write(store,value)


def test_consumed_empty_save_requires_two_stable_reads_then_fresh_single_use_permit(missing):
    store,provider,old,_=missing
    observe_twice(store)
    assert browser.recover_saved_uploads({'id':'owner'})==1
    value=prep.read(1)
    assert value['missing_save_recovery']['attempts']==1 and not value.get('browser')
    assert browser.finish(KEY,old['token'])['status']=='Handoff unavailable'
    with pytest.raises(PermissionError):browser.permit(KEY,old['token'],old['sha256'])
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    assert plan['token']!=old['token'] and plan['filename']==old['filename']
    assert plan['fresh_empty_item'] and plan['library_asset_id']=='asset-id'
    assert browser.permit(KEY,plan['token'],plan['sha256'])=={'permitted':True}
    with pytest.raises(ValueError):browser.permit(KEY,plan['token'],plan['sha256'])
    browser.finish(KEY,plan['token'],'save')
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert not provider.writes


def test_recent_or_single_empty_read_never_repeats_save(missing):
    store,provider,_,_=missing;value=prep.read(1)
    value['browser']['save_permitted_at']=ago(10);write(store,value)
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert not prep.read(1).get('missing_save_recovery')
    value=prep.read(1);value['browser']['save_permitted_at']=ago(120);write(store,value)
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert prep.read(1)['browser']['started'] and not provider.writes


@pytest.mark.parametrize('change',['address','quantity','shipping','source','artwork','slots',
    'submission','intent','hidden','unknown','checksum','original_artwork','repeat','customer_hold','library'])
def test_uncertain_or_changed_work_never_gets_new_authority(missing,monkeypatch,change):
    store,p,_,_=missing;observe_twice(store);value=prep.read(1)
    if change=='address':p.data['recipient']={'name':'Changed synthetic recipient'}
    if change=='quantity':p.data['items'][0]['quantity']=2
    if change=='shipping':p.data['shippingMethod']='Express'
    if change=='source':value['snapshot']['output']['sha256']='f'*64
    if change=='artwork':p.data['items'][0]['assets']=[{'printArea':'default','url':'unexpected.jpg'}]
    if change=='slots':p.data['items'][0]['assets']=[dict(id='new-slot',printArea='default',status='NotYetDownloaded',required=True,pageCount=0)]
    if change=='submission':value['submission']={'intent_at':prep.now()}
    if change=='intent':value['write_intent']=True
    if change=='hidden':value['hidden']=True
    if change=='unknown':value['browser']['client_error']='Unknown failure'
    if change=='checksum':value['browser']['companion_sha256']='f'*64
    if change=='original_artwork':value['browser']['empty_slots']=[{'url':'original.jpg','printArea':'default'}]
    if change=='repeat':value['missing_save_recovery']['attempts']=1
    if change=='customer_hold':
        import inbox_companion
        def held(_):raise ValueError('Paused customer request')
        monkeypatch.setattr(inbox_companion,'submission_guard',held)
    if change=='library':p.assets=lambda:[]
    write(store,value)
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert prep.read(1).get('browser') and not p.writes


def test_delayed_saved_asset_is_verified_without_another_permit(missing,monkeypatch):
    _,p,plan,_=missing
    p.data['items'][0]['assets']=[dict(printArea='default',url=render_url(),status='complete')]
    p.asset=lambda _:dict(url='https://live-services.pwinty.com/synthetic-original')
    monkeypatch.setattr(browser,'verify_original',lambda *a:('asset-id',True))
    assert browser.recover_saved_uploads({'id':'owner'})==1
    value=prep.read(1)
    assert value['browser']['verified'] and not value.get('missing_save_recovery')
    assert value['browser']['filename']==plan['filename'] and not p.writes


def test_late_attachment_between_recovery_and_new_permit_stops_save(missing):
    store,p,_,_=missing;observe_twice(store)
    assert browser.recover_saved_uploads({'id':'owner'})==1
    plan=browser.claim(exact_item_supported=True,upload_recovery_supported=True)
    p.data['items'][0]['assets']=[dict(printArea='default',url='late.jpg')]
    with pytest.raises(ValueError):browser.permit(KEY,plan['token'],plan['sha256'])
    assert not p.writes


def test_placeholder_print_area_stays_recoverable(missing):
    store,p,plan,_=missing
    slot=dict(id='original-slot',printArea='default',status='NotYetDownloaded',required=True,pageCount=0)
    p.data['items'][0]['assets']=[slot]
    value=prep.read(1);value['browser']['empty_slots']=[deepcopy(slot)];write(store,value)
    assert browser.finish(KEY,plan['token'],'save')['status']=='Needs review'
    observe_twice(store)
    assert browser.recover_saved_uploads({'id':'owner'})==1 and not p.writes


def test_dependency_failure_preserves_receipt_without_stalling_poll(missing,monkeypatch):
    store,p,_,_=missing;observe_twice(store)
    def unavailable():raise RuntimeError('Synthetic asset library unavailable')
    p.assets=unavailable
    assert browser.recover_saved_uploads({'id':'owner'})==0
    assert prep.read(1)['browser']['started'] and not p.writes
    p.order=lambda *_:pytest.fail('A deferred library failure must not re-read on every poll')
    assert browser.recover_saved_uploads({'id':'owner'})==0
