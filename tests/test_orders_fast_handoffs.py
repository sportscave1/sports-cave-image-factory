"""Offline scheduling checks; these never contact a supplier or submit an order."""
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import prodigi_preparation as prep
import prodigi_preparation_api as api

def test_critical_qa_auth_is_not_blocked_by_the_poll_auth_slot(monkeypatch):
    seen=[]
    def authenticate(token,*,slots):
        assert slots is not api._orders_auth_slots
        assert slots.acquire(blocking=False)
        slots.release();seen.append(token)
    monkeypatch.setattr(api,'desktop',authenticate)
    monkeypatch.setattr('prodigi_dashboard_qa.permit',lambda *a:{'permitted':True})
    client=TestClient(Starlette(routes=[Route('/qa/permit',api.dashboard_qa_action,methods=['POST'])]))
    assert api._orders_auth_slots.acquire(blocking=False)
    try:
        response=client.post('/qa/permit',json=dict(key='prodigi_prepare:1',token='a'*43,evidence={}),headers={'Authorization':'Bearer '+'x'*43})
        assert response.status_code==200 and response.json()['permitted'] and seen==['x'*43]
    finally:api._orders_auth_slots.release()

def test_product_finish_keeps_the_native_preselect_error(monkeypatch):
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda _,**kw:None)
    monkeypatch.setattr('prodigi_product_browser.finish',lambda key,token,stage,**kw:(calls.append((stage,kw)) or {'status':'Needs review'}))
    client=TestClient(Starlette(routes=[Route('/browser/finish',api.browser_action,methods=['POST'])]))
    response=client.post('/browser/finish',json=dict(key='product:prodigi_prepare:1',token='a'*43,stage='product-select',error='Catalogue changed'),headers={'Authorization':'Bearer '+'x'*43})
    assert response.status_code==200 and calls==[('product-select',{'error':'Catalogue changed'})]


@pytest.mark.parametrize('qa_plan',[None,dict(kind='qa',key='fixture')])
def test_ready_qa_precedes_another_artwork_transfer(monkeypatch,qa_plan):
    calls=[]
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    monkeypatch.setattr(api,'desktop',lambda _,**kw:None)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr(prep,'tick',lambda:pytest.fail('A ready handoff must not wait for preparation'))
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_dashboard_qa.claim',lambda **_:(calls.append('qa') or qa_plan))
    monkeypatch.setattr('prodigi_product_browser.claim',lambda:(calls.append('product') or None))
    monkeypatch.setattr('prodigi_browser.claim',lambda **_:(calls.append('upload') or dict(key='upload-fixture')))
    client=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])]))
    response=client.post('/tick',content='{}',headers={'Authorization':'Bearer '+'x'*43,
        'X-Sports-Cave-Orders-QA':'1','X-Sports-Cave-Orders-Browser':'1','X-Sports-Cave-Orders-Products':'1'})
    assert response.status_code==200
    assert calls==(['qa'] if qa_plan else ['qa','upload'])
    assert response.json()['browser']==(qa_plan or dict(key='upload-fixture'))


def test_idle_poll_prepares_once_then_claims_the_new_handoff(monkeypatch):
    calls=[]
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(api,'desktop',lambda _,**kw:None)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_status_sync.kick',lambda:None)
    async def ready(*_):
        calls.append('claim')
        return dict(key='new-plan') if 'prepare' in calls else None
    monkeypatch.setattr(api,'ready_handoff',ready)
    monkeypatch.setattr(prep,'tick',lambda:(calls.append('prepare') or dict(allocation_id=1,status='Awaiting browser upload')))
    client=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])]))
    response=client.post('/tick',content='{}',headers={'Authorization':'Bearer '+'x'*43})
    assert response.status_code==200 and response.json()['browser']==dict(key='new-plan')
    assert calls==['claim','prepare','claim']

@pytest.mark.parametrize('hint,expected',[('99',{'preferred_order':'99'}),('not/a/detail',{})])
def test_continuation_hint_only_changes_priority_of_existing_guarded_claim(monkeypatch,hint,expected):
    calls=[]
    monkeypatch.setattr('prodigi_browser.claim',lambda **kw:calls.append(kw) or {'key':'fixture'})
    request=type('Request',(),{'headers':{'x-sports-cave-orders-browser':'1','x-sports-cave-orders-continue':hint}})()
    import asyncio
    result=asyncio.run(api.ready_handoff(request,False))
    assert result=={'key':'fixture'} and calls==[dict(exact_item_supported=False,reset_supported=False,**expected)]

@pytest.mark.parametrize('capable',[False,True])
def test_only_fixed_companion_can_recover_known_empty_editor_failure(monkeypatch,capable):
    calls=[];actor={'id':'fixture'}
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(api,'desktop',lambda _,**kw:actor)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_status_sync.kick',lambda:None)
    monkeypatch.setattr('prodigi_browser.recover_selected_empty_editors',lambda user:calls.append(user))
    monkeypatch.setattr('prodigi_product_browser.recover_readbacks',lambda user:0)
    async def ready(*_):return {'key':'fixture'}
    monkeypatch.setattr(api,'ready_handoff',ready)
    headers={'Authorization':'Bearer '+'x'*43}
    if capable:headers['X-Sports-Cave-Orders-Empty-Editor']='1'
    response=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])])).post('/tick',content='{}',headers=headers)
    assert response.status_code==200 and calls==([actor] if capable else [])

@pytest.mark.parametrize('capable',[False,True])
def test_only_item_qa_companion_can_recover_the_old_shared_control_wait(monkeypatch,capable):
    calls=[];actor={'id':'fixture'}
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(api,'desktop',lambda _,**kw:actor)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_status_sync.kick',lambda:None)
    monkeypatch.setattr('prodigi_dashboard_qa.recover_waiting_item_qa',lambda user:calls.append(user))
    async def ready(*_):return {'key':'fixture'}
    monkeypatch.setattr(api,'ready_handoff',ready)
    headers={'Authorization':'Bearer '+'x'*43}
    if capable:headers['X-Sports-Cave-Orders-Item-QA']='1'
    response=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])])).post('/tick',content='{}',headers=headers)
    assert response.status_code==200 and calls==([actor] if capable else [])


@pytest.mark.parametrize('status',['Ready for manual payment','Needs QA','Needs review','Handoff unavailable'])
def test_only_successful_qa_completion_wakes_existing_guarded_submission_worker(monkeypatch,status):
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda _,**kw:None)
    monkeypatch.setattr('prodigi_dashboard_qa.finish',lambda *args:dict(status=status))
    monkeypatch.setattr('prodigi_dashboard_qa.permit',lambda *args:dict(permitted=True))
    monkeypatch.setattr('prodigi_submission.kick',lambda:calls.append('guarded-submit-worker'))
    client=TestClient(Starlette(routes=[Route('/qa/finish',api.dashboard_qa_action,methods=['POST']),Route('/qa/permit',api.dashboard_qa_action,methods=['POST'])]))
    body=dict(key='prodigi_prepare:1',token='a'*43,evidence={})
    headers={'Authorization':'Bearer '+'x'*43}
    assert client.post('/qa/permit',json=body,headers=headers).status_code==200 and not calls
    assert client.post('/qa/finish',json=body,headers=headers).status_code==200
    assert calls==(['guarded-submit-worker'] if status=='Ready for manual payment' else [])



def test_fixed_page_ready_capability_reaches_qa_recovery(monkeypatch):
    calls=[];actor={'id':'fixture'}
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setattr(api,'desktop',lambda _,**kw:actor)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_status_sync.kick',lambda:None)
    monkeypatch.setattr('prodigi_dashboard_qa.recover_waiting_item_qa',lambda user,**kw:calls.append((user,kw)))
    async def ready(*_):return {'key':'fixture'}
    monkeypatch.setattr(api,'ready_handoff',ready)
    headers={'Authorization':'Bearer '+'x'*43,'X-Sports-Cave-Orders-Item-QA':'1','X-Sports-Cave-Orders-Page-Ready':'1'}
    response=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])])).post('/tick',content='{}',headers=headers)
    assert response.status_code==200 and calls==[(actor,dict(page_supported=True))]
