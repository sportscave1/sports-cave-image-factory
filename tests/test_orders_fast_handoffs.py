"""Offline scheduling checks; these never contact a supplier or submit an order."""
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import prodigi_preparation as prep
import prodigi_preparation_api as api


@pytest.mark.parametrize('qa_plan',[None,dict(kind='qa',key='fixture')])
def test_ready_qa_precedes_another_artwork_transfer(monkeypatch,qa_plan):
    calls=[]
    monkeypatch.setattr(prep,'enabled',lambda:True)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    monkeypatch.setattr(api,'desktop',lambda _:None)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr(prep,'tick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    monkeypatch.setattr('prodigi_dashboard_qa.claim',lambda **_:(calls.append('qa') or qa_plan))
    monkeypatch.setattr('prodigi_product_browser.claim',lambda:(calls.append('product') or None))
    monkeypatch.setattr('prodigi_browser.claim',lambda **_:(calls.append('upload') or dict(key='upload-fixture')))
    client=TestClient(Starlette(routes=[Route('/tick',api.tick,methods=['POST'])]))
    response=client.post('/tick',content='{}',headers={'Authorization':'Bearer '+'x'*43,
        'X-Sports-Cave-Orders-QA':'1','X-Sports-Cave-Orders-Browser':'1','X-Sports-Cave-Orders-Products':'1'})
    assert response.status_code==200
    assert calls==(['qa'] if qa_plan else ['qa','product','upload'])
    assert response.json()['browser']==(qa_plan or dict(key='upload-fixture'))


@pytest.mark.parametrize('status',['Ready for manual payment','Needs QA','Needs review','Handoff unavailable'])
def test_only_successful_qa_completion_wakes_existing_guarded_submission_worker(monkeypatch,status):
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda _:None)
    monkeypatch.setattr('prodigi_dashboard_qa.finish',lambda *args:dict(status=status))
    monkeypatch.setattr('prodigi_dashboard_qa.permit',lambda *args:dict(permitted=True))
    monkeypatch.setattr('prodigi_submission.kick',lambda:calls.append('guarded-submit-worker'))
    client=TestClient(Starlette(routes=[Route('/qa/finish',api.dashboard_qa_action,methods=['POST']),Route('/qa/permit',api.dashboard_qa_action,methods=['POST'])]))
    body=dict(key='prodigi_prepare:1',token='a'*43,evidence={})
    headers={'Authorization':'Bearer '+'x'*43}
    assert client.post('/qa/permit',json=body,headers=headers).status_code==200 and not calls
    assert client.post('/qa/finish',json=body,headers=headers).status_code==200
    assert calls==(['guarded-submit-worker'] if status=='Ready for manual payment' else [])
