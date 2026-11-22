"""Offline supplier submission, durable fence and certificate retry coverage."""
from copy import deepcopy
import json
import pytest
import prodigi_submission as submit
import prodigi_dashboard_qa as qa
import prodigi_preparation as prep
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
from test_prodigi_dashboard_qa import fixture


def ready():
    value,snap,p,evidence=fixture()
    p.data['allowedActions'].append('submit')
    value.update(status='Ready for manual payment',qa={'policy':qa.POLICY,'checks':{k:True for k in qa.CHECKS}})
    pinned=qa.pinned_order(p.data);pinned['shippingMethod']=p.data.get('shippingMethod')
    value['dashboard_qa']=dict(verified=True,checked_at=prep.now(),validated_order_hash=prep.digest(pinned),before=deepcopy(p.data))
    p.submits=[]
    def post(key):
        p.submits.append(key);p.data['status']='paused'
    p.submit=post
    auth=dict(enabled=True,actor='owner',changed_at='2026-01-01T00:00:00+00:00')
    return value,snap,p,auth


def test_fresh_qa_draft_preempts_old_passive_countdown_poll(store,monkeypatch):
    v,s,p,auth=ready();old=deepcopy(v)
    old.update(allocation_id=2,order_id='older-countdown',status='Submitted',submission={'lease_until':'2020-01-01T00:00:00+00:00'})
    monkeypatch.setattr(prep,'resolve',lambda _:s)
    monkeypatch.setattr(prep,'Client',lambda:p)
    with prep.connect() as c,c.cursor() as q:
        prep.save(q,v);prep.save(q,old)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(auth)))
        q.execute("UPDATE app_settings SET updated_at=now()-interval '5 minutes' WHERE key='prodigi_prepare:2'")
    submit.tick()
    assert p.submits==['99'] and prep.read(1)['status']=='Submitted'
    assert prep.read(2)['order_id']=='older-countdown'


def test_authorisation_fresh_qa_and_unchanged_order_are_required():
    v,s,p,a=ready();submit.checked(v,p,lambda _:s,a)
    with pytest.raises(ValueError,match='authorisation'):submit.checked(v,p,lambda _:s,{'enabled':False})
    v['qa']['checks']['image_quality']=False
    with pytest.raises(ValueError,match='every'):submit.checked(v,p,lambda _:s,a)
    v['qa']['checks']['image_quality']=True
    p.data['shippingMethod']='Express'
    with pytest.raises(ValueError,match='changed'):submit.checked(v,p,lambda _:s,a)
    assert not p.submits


def test_exactly_one_submit_then_confirm_then_certificate():
    v,s,p,a=ready();v['submission']={'intent_at':prep.now()};events=[]
    def cert(value):
        assert value['submission']['confirmed'] and p.data['status']=='in_production'
        events.append('certificate');return 'https://cdn.shopify.com/certificate.pdf'
    result=submit.run(v,p,lambda _:s,lambda v:events.append(v['status']),cert,may_post=True,authorisation=a)
    assert result['status']=='Submitted' and events==['Submitted']
    p.data['status']='in_production';events.clear()
    result=submit.run(v,p,lambda _:s,lambda v:events.append(v['status']),cert)
    assert p.submits==['99'] and result['status']=='Complete'
    assert events==['Certificate pending','certificate','Complete']
    assert result['submission']['supplier_status']=='in_production'


def test_timeout_after_acceptance_reads_back_without_resubmitting():
    v,s,p,a=ready();v['submission']={'intent_at':prep.now()}
    def post(key):
        p.submits.append(key);p.data['status']='paused';raise ValueError('Acknowledgement lost')
    p.submit=post
    def cert(_):raise ValueError('Certificate unavailable')
    assert submit.run(v,p,lambda _:s,lambda _:None,cert,may_post=True,authorisation=a)['status']=='Submitted'
    p.data['status']='in_production'
    assert submit.run(v,p,lambda _:s,lambda _:None,cert)['status']=='Certificate pending'
    assert submit.run(v,p,lambda _:s,lambda _:None,lambda _:'https://cdn.shopify.com/cert.pdf')['status']=='Complete'
    assert p.submits==['99']


def test_draft_or_pending_is_not_completion_and_no_second_post():
    v,s,p,a=ready();v['submission']={'intent_at':prep.now()}
    p.submit=lambda key:p.submits.append(key)
    cert=lambda _:pytest.fail('No certificate before confirmed acceptance')
    assert submit.run(v,p,lambda _:s,lambda _:None,cert,may_post=True,authorisation=a)['status']=='Submission uncertain'
    assert submit.run(v,p,lambda _:s,lambda _:None,cert)['status']=='Submission uncertain'
    assert p.submits==['99']


def test_supplier_hold_after_submission_waits_without_resubmission_or_certificate():
    v,s,p,a=ready();v['submission']={'intent_at':prep.now()}
    p.data.update(status='on_hold',issues=[{'code':'payment_required'}])
    cert=lambda _:pytest.fail('A supplier hold never confirms payment/production')
    result=submit.run(v,p,lambda _:s,lambda _:None,cert)
    assert result['status']=='Submitted' and 'on hold' in result['message']
    assert result['submission']['supplier_status']=='on_hold'
    assert not result['submission'].get('finalised') and not p.submits
    p.data.update(status='in_production',issues=[])
    result=submit.run(v,p,lambda _:s,lambda _:None,lambda _:'https://cdn.shopify.com/cert.pdf')
    assert result['status']=='Complete' and not p.submits


def test_database_fence_and_pause_survive_repeated_ticks(store,monkeypatch):
    v,s,p,a=ready()
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',lambda _:s)
    with store() as c,c.cursor() as q:prep.save(q,v)
    # Defaults off, including existing ready orders.
    submit.tick();assert not p.submits and prep.read(1)['status']=='Ready for manual payment'
    with store() as c,c.cursor() as q:
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(a)))
    monkeypatch.setattr(submit,'run',lambda value,*args,**kw: value)
    submit.tick();submit.tick()
    assert prep.read(1)['status']=='Submitting'
    with store() as c,c.cursor() as q:
        q.execute("SELECT count(*) n FROM app_settings WHERE key LIKE 'prodigi_submit_order:%%'")
        assert q.fetchone()['n']==1
    with pytest.raises(ValueError,match='already recorded'):prep.reconcile({'id':'owner'},1)
    assert prep.request({'id':'owner'},1)['submission']
    assert not p.submits


def test_api_submit_exact_endpoint_owner_gate_and_202(monkeypatch):
    from prodigi_client import Client,ProdigiError
    from types import SimpleNamespace
    class Transport:
        def __init__(self):self.calls=[]
        def request(self,*args,**kwargs):self.calls.append((args,kwargs));return SimpleNamespace(status_code=202)
    transport=Transport();client=Client('fixture',transport)
    monkeypatch.setattr(submit,'setting',lambda:{'enabled':False})
    with pytest.raises(ProdigiError,match='activated'):client.submit('99')
    assert not transport.calls
    monkeypatch.setattr(submit,'setting',lambda:{'enabled':True})
    assert client.submit('99') is None
    assert transport.calls[0][0]==('POST','https://api.prodigi.com/v5/orders/99:submit')
    assert transport.calls[0][1]['json']=={}


def test_us_submission_refreshes_legacy_qa_and_requires_saved_tax_declaration():
    v,s,p,a=ready();s['recipient']['address']['countryCode']='US';p.data['recipient']['address']['countryCode']='US'
    with pytest.raises(submit.StaleQA,match='sales-tax'):submit.checked(v,p,lambda _:s,a)
    v['dashboard_qa'].update(tax_policy=qa.TAX_POLICY,tax_collected=True)
    pinned=qa.pinned_order(p.data);pinned['shippingMethod']=p.data.get('shippingMethod');v['dashboard_qa']['validated_order_hash']=prep.digest(pinned)
    p.data['usSalesTaxAlreadyCollected']=False
    with pytest.raises(submit.StaleQA):submit.checked(v,p,lambda _:s,a)
    p.data['usSalesTaxAlreadyCollected']=True
    submit.checked(v,p,lambda _:s,a)
    assert not p.submits
