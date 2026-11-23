from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import hashlib,json
import pytest
import prodigi_preparation as prep
import prodigi_documents as docs
from prodigi_client import Client,ProdigiError
from test_auto_editions_jobs import database
from test_prodigi_preparation import store,order,snapshot


def test_packing_slip_sends_only_scoped_document_to_unpaid_draft(monkeypatch):
    calls=[];draft=order()
    def request(method,url,**kw):
        calls.append((method,url,kw.get('json')))
        return SimpleNamespace(status_code=200,json=lambda:{'data':deepcopy(draft)})
    client=Client('live_fixture',SimpleNamespace(request=request))
    url=docs.URL+'a'*43
    with pytest.raises(ProdigiError,match='disabled'):client.packing_slip('99',url)
    assert not calls
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_FULL_QA_ACCEPTED','true')
    client.packing_slip('99',url)
    assert [c[0] for c in calls]==['GET','PATCH']
    assert calls[-1][2]=={'packingSlip':{'url':url}}
    assert calls[-1][1]=='https://api.prodigi.com/v5/orders/99'
    for changed in [dict(status='in_production'),dict(charges=[{'amount':1}]),dict(allowedActions=[])]:
        draft.update(order());draft.update(changed);calls.clear()
        with pytest.raises(ProdigiError,match='unpaid'):client.packing_slip('99',url)
        assert len(calls)==1
    with pytest.raises(ProdigiError,match='verified'):client.packing_slip('99','https://other.example/document.pdf')


def test_existing_different_packing_slip_is_never_replaced(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_FULL_QA_ACCEPTED','true')
    calls=[];draft=order();draft['packingSlip']={'url':'https://fixture/existing.pdf'}
    client=Client('live_fixture',SimpleNamespace(request=lambda method,*a,**k:calls.append(method) or SimpleNamespace(status_code=200,json=lambda:{'data':draft})))
    with pytest.raises(ProdigiError,match='preservation'):client.packing_slip('99',docs.URL+'a'*43)
    assert calls==['GET']


@pytest.fixture
def document(store,monkeypatch):
    token='a'*43;snap=snapshot();subject='prodigi_sandbox_test:00000000-0000-4000-8000-000000000001'
    value=dict(subject=subject,allocation_id=1,job_id=snap['job_id'],source_output=snap['output'],output={'bytes':8,'sha256':'b'*64},
        expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    request={'snapshot':snap,'source_snapshot':snap,'hidden':False}
    with store() as c,c.cursor() as q:
        for key,v in [(docs.PREFIX+hashlib.sha256(token.encode()).hexdigest(),value),(subject,request)]:
            q.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(key,json.dumps(v)))
    monkeypatch.setattr('auto_editions_jobs.Jobs.read_bound',lambda *_:({'status':'Ready','payload':{'identity':{}},'result':{'output':snap['output']}},{}))
    monkeypatch.setattr('auto_editions_api.same_allocation',lambda *_:True)
    return token,value,request,store


def test_certificate_capability_revokes_with_removed_sandbox_row(document):
    token,value,request,connect=document
    assert docs.bound(token)['output']==value['output']
    request['hidden']=True
    with connect() as c,c.cursor() as q:q.execute('UPDATE app_settings SET value=%s::jsonb WHERE key=%s',(json.dumps(request),value['subject']))
    with pytest.raises(ValueError,match='Unavailable'):docs.bound(token)


def test_certificate_capability_rejects_changed_source_or_expiry(document):
    token,value,request,connect=document
    request['source_snapshot']['output']['sha256']='changed'
    with connect() as c,c.cursor() as q:q.execute('UPDATE app_settings SET value=%s::jsonb WHERE key=%s',(json.dumps(request),value['subject']))
    with pytest.raises(ValueError):docs.bound(token)
    with pytest.raises(ValueError):docs.bound('not-a-capability')
