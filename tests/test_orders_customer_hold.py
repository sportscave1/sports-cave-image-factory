"""Customer holds stay distinct from real failures across initial and live reads."""
import json
from copy import deepcopy
import pytest
import orders_prodigi_grid as grid
import prodigi_dashboard_qa as qa
import prodigi_preparation as prep
import inbox_companion as inbox
from test_prodigi_preparation import store, snapshot, offline
from test_auto_editions_jobs import database


def held():
    return dict(status='Needs QA',order_id='99',allocation_id=1,snapshot=snapshot(),
        checks={k:True for k in qa.CHECKS},updated_at='2026-01-01T00:00:00+00:00',
        message='Paused customer request — review the Inbox Companion flag before submission.',
        _inbox=dict(blocking=True,kind='address',updated_at='2026-01-02T00:00:00+00:00',
                    label='Paused customer request · supplier draft retained for review'))


def test_verified_address_hold_is_not_failed_qa_and_never_offers_reset():
    value=held();before=deepcopy(value)
    result=grid.review(value,{'edition_order_id':1},'')
    assert result['status']=='Customer hold' and result['customer_hold'] and not result['has_error']
    assert all(item['state']=='pass' for item in result['items'])
    assert not any(result[k] for k in ('can_reset','can_restart','can_merge_restart'))
    assert result['hold_kind']=='address' and 'Reset is not needed' in result['message']
    assert result['updated_at']==value['_inbox']['updated_at'] and value==before


def test_a_real_qa_failure_remains_visible_even_while_customer_hold_blocks_resets():
    value=held();value['checks']['image_quality']=False
    value['last_failure']={'message':'Image quality is not Excellent','at':'2026-01-03T00:00:00+00:00'}
    result=grid.review(value,{'edition_order_id':1},'')
    assert result['status']=='Needs QA' and result['has_error'] and result['customer_hold']
    assert any(item['state']=='fail' for item in result['items'])
    assert not result['can_reset'] and not result['can_restart']


def test_cleared_customer_flag_is_not_kept_as_an_active_hold():
    value=held();value['_inbox'].update(blocking=False,label='Customer request reviewed')
    result=grid.review(value,{'edition_order_id':1},'')
    assert not result['customer_hold'] and result['status']!='Customer hold'
    assert result['can_reset'] # Ordinary pre-submission workflow remains unchanged.


def test_live_status_poll_keeps_current_hold_without_supplier_or_mailbox_reads(store,monkeypatch):
    value=held();flag=value.pop('_inbox')
    flag['updated_at']='2030-01-02T00:00:00+00:00'
    monkeypatch.setattr(inbox,'available',lambda:True)
    monkeypatch.setattr('orders_artwork_repair.batch',lambda *_:{})
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(inbox.FLAG+'123',json.dumps(flag)))
    saved=grid.batch_status([1])['1']
    assert saved['_inbox']['blocking'] and grid.review(saved,{'edition_order_id':1},'')['status']=='Customer hold'
    flag.update(blocking=False,updated_at='2030-01-03T00:00:00+00:00')
    with store() as c,c.cursor() as q:
        q.execute('UPDATE app_settings SET value=%s::jsonb WHERE key=%s',(json.dumps(flag),inbox.FLAG+'123'))
    fresh=grid.review(grid.batch_status([1])['1'],{'edition_order_id':1},'')
    assert not fresh['customer_hold'] and fresh['updated_at']==flag['updated_at']


def test_disabled_inbox_feature_does_not_admit_stored_flags_into_live_status(store,monkeypatch):
    value=held();flag=value.pop('_inbox')
    monkeypatch.setattr(inbox,'available',lambda:False)
    monkeypatch.setattr('orders_artwork_repair.batch',lambda *_:{})
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(inbox.FLAG+'123',json.dumps(flag)))
    assert '_inbox' not in grid.batch_status([1])['1']


def test_a_customer_request_after_submission_is_not_claimed_as_an_unsubmitted_hold():
    value=held();value.update(status='Complete',submission={'supplier_status':'in_production'})
    result=grid.review(value,{'edition_order_id':1},'')
    assert result['customer_hold'] and result['status']=='Complete'
    assert result['supplier_status']=='in_production' and not result['can_reset']


def test_reset_endpoint_cannot_bypass_unresolved_customer_request(store,monkeypatch):
    import prodigi_reset as reset
    value=held();flag=value.pop('_inbox')
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(inbox,'available',lambda:True)
    monkeypatch.setattr(prep,'resolve',lambda *_:pytest.fail('Held orders must stop before source or supplier work'))
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(inbox.FLAG+'123',json.dumps(flag)))
    before=prep.read(1)
    with pytest.raises(ValueError,match='Paused customer request'):reset.reset_order({'id':'owner'},1)
    assert prep.read(1)==before


def review_fixture(monkeypatch):
    from test_inbox_companion import fixture,persist
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr('os_accounts.can_access_page',lambda *_:True)
    job,_,_=fixture(monkeypatch);job['state']='review';persist(job)
    value=held();value.pop('_inbox')
    value.update(browser={'verified':True,'item_id':'88'},dashboard_qa={'verified':True})
    return job,value


def test_explicit_customer_review_queues_fresh_qa_without_reset_or_supplier_work(store,monkeypatch):
    job,value=review_fixture(monkeypatch)
    monkeypatch.setattr(inbox,'supplier',lambda *_:pytest.fail('Review must not touch supplier'))
    with store() as c,c.cursor() as q:prep.save(q,value)
    before=prep.read(1)
    inbox.review({'id':'owner'},job['key'])
    after=prep.read(1)
    assert after['status']=='Checking QA' and 'dashboard_qa' not in after
    assert after['browser']==before['browser'] and after['snapshot']==before['snapshot']
    assert after['order_id']==before['order_id'] and after['checks']==before['checks']
    assert after['history'][-1]['event']=='reviewed_customer_request_qa_queued'
    assert inbox.read(inbox.FLAG+'123')['blocking'] is False


@pytest.mark.parametrize('change',[
    {'checks':{}},{'browser':{'verified':False}},{'dashboard_qa':{'verified':False}},
    {'submission':{'supplier_status':'on_hold'}},{'last_failure':{'message':'Real failure'}},
    {'merge_pending':True},{'hidden':True},{'message':'Image quality failed'},
])
def test_customer_review_does_not_requeue_other_failures_or_submitted_work(store,monkeypatch,change):
    job,value=review_fixture(monkeypatch);value.update(change)
    with store() as c,c.cursor() as q:prep.save(q,value)
    before=prep.read(1)
    inbox.review({'id':'owner'},job['key'])
    assert prep.read(1)==before


def test_reviewing_old_request_cannot_clear_newer_hold_or_resume_work(store,monkeypatch):
    job,value=review_fixture(monkeypatch)
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        inbox.save(q,inbox.FLAG+'123',{'request':inbox.PREFIX+'b'*64,'blocking':True})
    before=prep.read(1)
    with pytest.raises(ValueError,match='current request'):inbox.review({'id':'owner'},job['key'])
    assert prep.read(1)==before and inbox.read(inbox.FLAG+'123')['blocking']
