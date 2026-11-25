"""Unpaid editable pauses are repaired without resubmission or release."""
import json
import pytest
import prodigi_preparation as prep
import prodigi_dashboard_qa as qa
import prodigi_submission as submit
from prodigi_client import ProdigiError
from test_prodigi_preparation import snapshot, order, store, offline
from test_auto_editions_jobs import database
from test_prodigi_dashboard_qa import fixture, options
from test_prodigi_submission import ready
from test_prodigi_reset import draft


def test_unpaid_editable_pause_keeps_exact_item_validation():
    value=order();value.update(status='paused',allowedActions=['update','resume'])
    assert prep.validate_order(value,snapshot(),'99','88')['id']=='88'
    value['items'][0]['sku']='wrong'
    with pytest.raises(ProdigiError,match='SKU'):prep.validate_order(value,snapshot(),'99','88')


@pytest.mark.parametrize('state',['paused','on_hold'])
def test_explicit_recovery_preserves_paused_order_and_scopes_original_artwork_replacement(draft,state):
    import prodigi_reset as reset
    import prodigi_browser as browser
    from copy import deepcopy
    p,s=draft;p.data.update(status=state,allowedActions=['update','resume'])
    before=deepcopy(p.data)
    value=reset.reset_order({'id':'owner'},1)
    assert value['reset_authorisation']['assets']==before['items'][0]['assets']
    prep.run(value,p,prep.resolve,None,lambda v:save(v))
    plan=browser.claim(exact_item_supported=True,reset_supported=True)
    assert plan['replace_artwork'] and plan['order_id']=='99' and plan['item_id']=='88'
    assert browser.permit(plan['key'],plan['token'],plan['sha256'])=={'permitted':True}
    assert p.data==before and not p.writes


def save(value):
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)


@pytest.mark.parametrize('change',[
    {'charges':[{'amount':'1.00'}]}, {'shipments':[{'id':'shipment'}]}, {'issues':[{'code':'hold'}]},
    {'status':'on_hold'}, {'status':'in_production'}, {'status':'completed'}, {'allowedActions':['cancel']},
    {'statusHistory':[{'status':'in_production'}]}, {'statusHistory':[{'fromStatus':'shipped'}]},
    {'statusHistory':['unknown']},
])
def test_noneditable_or_production_history_never_admits_artwork(change):
    value=order();value['status']='paused';value.update(change)
    with pytest.raises(ProdigiError,match='unpaid editable'):prep.validate_order(value,snapshot(),'99','88')


@pytest.mark.parametrize('state',['paused','on_hold'])
def test_paused_order_still_requires_every_dashboard_check(state):
    value,snap,p,evidence=fixture();p.data.update(status=state,allowedActions=['update','resume'],shippingMethod='Budget')
    value['dashboard_qa']={'shipping':dict(options=options(),current='standard',target='budget')}
    result=qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)
    assert all(result['checks'].values()) and not result['blockers']
    evidence['quality']='Poor'
    assert not qa.evaluate(value,snap,p.data,p.data['items'][0],evidence,identity_verified=True)['checks']['image_quality']


def test_paused_resume_permission_allows_browser_edit_without_api_update_or_release():
    value=order();value.update(status='paused',allowedActions=['cancel','resume'])
    assert prep.validate_order(value,snapshot(),'99','88')['id']=='88'
    value.update(status='draft')
    with pytest.raises(ProdigiError):prep.validate_order(value,snapshot(),'99','88')


@pytest.mark.parametrize('state',['paused','on_hold'])
def test_verified_paused_order_adopted_with_durable_fence_and_zero_submit_or_resume(store,monkeypatch,state):
    value,snap,p,auth=ready();p.data.update(status=state,allowedActions=['update','resume'])
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',lambda _:snap)
    p.resume=lambda *_:pytest.fail('An existing pause must never be released')
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(auth)))
    submit.tick();submit.tick()
    saved=prep.read(1)
    assert saved['status']=='Submitted' and saved['submission']['adopted_paused']
    assert saved['submission']['confirmed'] and saved['submission']['supplier_status']==state
    assert ('pause preserved' if state=='paused' else 'on hold') in saved['message']
    assert not p.submits and p.data['status']==state
    with store() as c,c.cursor() as q:
        q.execute("SELECT count(*) n FROM app_settings WHERE key LIKE 'prodigi_submit_order:%%'")
        assert q.fetchone()['n']==1


@pytest.mark.parametrize('state',['paused','on_hold'])
def test_supplier_pause_after_initial_intent_never_gets_a_duplicate_submit(state):
    value,snap,p,auth=ready();p.data.update(status=state,allowedActions=['update','resume'])
    value['submission']={'intent_at':prep.now(),'adopted_paused':False}
    result=submit.run(value,p,lambda _:snap,lambda _:None,may_post=True,authorisation=auth)
    assert result['status']=='Submitted' and result['submission']['adopted_paused']
    assert not p.submits and p.data['status']==state


@pytest.mark.parametrize('change',['owner','qa','customer','image','charges'])
@pytest.mark.parametrize('state',['paused','on_hold'])
def test_paused_adoption_never_bypasses_owner_qa_customer_or_artwork_guards(store,monkeypatch,change,state):
    value,snap,p,auth=ready();p.data.update(status=state,allowedActions=['update','resume'])
    monkeypatch.setattr(prep,'Client',lambda:p);monkeypatch.setattr(prep,'resolve',lambda _:snap)
    if change=='owner':auth['enabled']=False
    if change=='qa':value['qa']['checks']['image_quality']=False
    if change=='image':p.data['items'][0]['assets'][0]['url']='https://fixture/wrong'
    if change=='charges':p.data['charges']=[{'amount':'1.00'}]
    if change=='customer':
        import inbox_companion
        monkeypatch.setattr(inbox_companion,'blocked',lambda _:True)
    with store() as c,c.cursor() as q:
        prep.save(q,value)
        q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(auth)))
    submit.tick()
    assert not prep.read(1).get('submission') and not p.submits


@pytest.mark.parametrize('change',[{'allowedActions':['resume']},{'allowedActions':['update']},
    {'issues':[{'code':'payment_required'}]},{'charges':[{'amount':'1'}]},
    {'shipments':[{'id':'shipped'}]},{'statusHistory':[{'status':'in_production'}]}])
def test_hold_requires_both_edit_permissions_and_no_payment_or_production_problem(change):
    value=order();value.update(status='on_hold',allowedActions=['update','resume']);value.update(change)
    assert not prep.editable_order(value)
