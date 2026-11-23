from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime
import pytest
import prodigi_client as provider


def transport(statuses,headers=None):
    calls=[]
    def request(method,url,**kwargs):
        calls.append(method)
        return SimpleNamespace(status_code=statuses[min(len(calls)-1,len(statuses)-1)],headers=headers or {},json=lambda:{'data':{'id':'99'}})
    return SimpleNamespace(request=request),calls


def test_safe_get_retries_429_and_honours_supplier_delay(monkeypatch):
    t,calls=transport([429,429,200],{'Retry-After':'2'});waits=[]
    monkeypatch.setattr(provider.time,'sleep',waits.append)
    assert provider.Client('fixture',t).order('99')=={'id':'99'}
    assert calls==['GET']*3 and waits==[2,2]


@pytest.mark.parametrize('retry_after',['120',format_datetime(datetime.now(timezone.utc)+timedelta(minutes=2))])
def test_long_supplier_cooldown_is_not_retried_early(monkeypatch,retry_after):
    t,calls=transport([429,200],{'Retry-After':retry_after});waits=[]
    monkeypatch.setattr(provider.time,'sleep',waits.append)
    with pytest.raises(provider.ProdigiError,match='HTTP 429'):provider.Client('fixture',t).order('99')
    assert calls==['GET'] and waits==[]


@pytest.mark.parametrize('method',['PATCH','POST'])
def test_writes_never_retry_rate_limits(monkeypatch,method):
    t,calls=transport([429,200]);waits=[]
    monkeypatch.setattr(provider.time,'sleep',waits.append)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true');monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    client=provider.Client('fixture',t,mode='sandbox')
    with pytest.raises(provider.ProdigiError,match='HTTP 429'):
        client.request(method,'/orders/99/items/88' if method=='PATCH' else '/assets/asset/validate',
                       {} if method=='PATCH' else dict(catalogueVariantId='variant',printArea='default'))
    assert calls==[method] and waits==[]


def test_repeated_get_429_has_a_bounded_attempt_count(monkeypatch):
    t,calls=transport([429]);waits=[];monkeypatch.setattr(provider.time,'sleep',waits.append)
    with pytest.raises(provider.ProdigiError,match='HTTP 429'):provider.Client('fixture',t).order('99')
    assert calls==['GET']*3 and waits==[1,2]


def test_current_readiness_stage_is_accepted_by_real_receipt_endpoint(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api
    import prodigi_browser as browser
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda *a,**k:{'id':'fixture'})
    monkeypatch.setattr(browser,'finish',lambda key,token,stage,**kw:calls.append((stage,kw)) or {'status':'Needs review'})
    client=TestClient(Starlette(routes=[Route('/browser/finish',api.browser_action,methods=['POST'])]))
    result=client.post('/browser/finish',headers={'Authorization':'Bearer '+'b'*43},json=dict(key='prodigi_prepare:1',token='a'*43,stage='readiness',error='The exact Prodigi order page did not become ready; check its loading or sign-in state.'))
    assert result.status_code==200 and calls[0][0]=='readiness'
