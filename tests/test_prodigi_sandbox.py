from copy import deepcopy
from types import SimpleNamespace
import pytest
import requests

import prodigi_sandbox as sandbox
import prodigi_preparation as prep
from prodigi_client import Client, ProdigiError
from test_prodigi_preparation import snapshot, Provider, store
from test_auto_editions_jobs import database


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **k: pytest.fail('Live network forbidden'))
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')


def source():
    s=snapshot()
    s['recipient']={'name':'Synthetic Person','address':{'line1':'1 Example Street','townOrCity':'Sydney',
        'stateOrCounty':'NSW','postalOrZipCode':'2000','countryCode':'AU'},'state_aliases':['NSW']}
    return s


def value():
    s=source(); test=sandbox.adapted(s,'SC-SANDBOX-fixture',s['recipient'])
    return dict(id='fixture',environment='sandbox',allocation_id=1,source_snapshot=s,snapshot=test,
        fingerprint=prep.digest(test),order_id='',item_id='',status='Queued',checks={},history=[])


class SandboxProvider(Provider):
    mode='sandbox'
    def create_draft(self,body,token):
        assert body['submit'] is False and body['merchantReference'].startswith('SC-SANDBOX-')
        assert 'assets' not in body['items'][0]
        self.created=deepcopy(body)
        self.data.update(merchantReference=body['merchantReference'],recipient=body['recipient'],shippingMethod=body['shippingMethod'])
        self.data['items'][0].update(body['items'][0])
        self.data['items'][0]['assets']=[]
        return '99'


def test_sandbox_uses_separate_environment_key_never_live_fallback(monkeypatch):
    monkeypatch.setenv('PRODIGI_API_KEY','live_fixture')
    monkeypatch.delenv('PRODIGI_SANDBOX_API_KEY',raising=False)
    with pytest.raises(ProdigiError,match='separate'):
        sandbox.SandboxClient()
    with pytest.raises(ProdigiError,match='not configured'):
        Client(mode='sandbox')
    with pytest.raises(ProdigiError,match='different environment'):
        sandbox.SandboxClient('live_other')
    with pytest.raises(ProdigiError,match='separate'):
        sandbox.SandboxClient('sandbox_fixture')


def test_sandbox_create_cannot_submit_and_never_uses_browser_cookies():
    calls=[]
    transport=SimpleNamespace(request=lambda *a,**k: calls.append((a,k)) or SimpleNamespace(
        status_code=202,json=lambda:{'data':{'id':'99'}}))
    client=sandbox.SandboxClient('synthetic',transport)
    body=sandbox.payload(value()['snapshot'])
    assert client.create_draft(body,'fixture')=='99'
    assert calls[0][1]['headers']['X-API-Key']=='sandbox_synthetic'
    assert calls[0][1]['allow_redirects'] is False
    for bad in ({**body,'submit':True},{**body,'merchantReference':'live-order'}):
        with pytest.raises(ProdigiError):client.create_draft(bad,'fixture')
    assert len(calls)==1


def test_full_sandbox_upload_reuses_numbered_source_and_reports_missing_qa():
    provider=SandboxProvider(); v=value();saved=[]
    result=sandbox.run(v,provider,lambda _:source(),lambda _:('https://fixture.invalid/exact-numbered.jpg','b'*32),
                       lambda x:saved.append(deepcopy(x)))
    assert saved[0]['create_intent'] and not saved[0]['order_id']
    assert any(s.get('write_intent') and s['status']=='Uploading' for s in saved)
    assert len(provider.writes)==1 and result['sandbox_unpaid_verified']
    assert result['status']=='Needs QA' and not result['checks']['certificate']
    assert provider.data['status']=='draft' and not provider.data.get('charges')
    assert result['checks']['edition_number']
    assert result['snapshot']['number']==source()['number']
    assert result['snapshot']['output']==source()['output']
    assert result['source_snapshot']['identity']==source()['identity']


def test_live_provider_and_changed_source_never_create_or_upload():
    p=SandboxProvider();p.mode='live'
    with pytest.raises(ValueError,match='sandbox provider'):
        sandbox.run(value(),p,lambda _:source(),None,lambda _:None)
    p.mode='sandbox'
    changed=source();changed['number']=99
    with pytest.raises(ValueError,match='changed'):
        sandbox.run(value(),p,lambda _:changed,None,lambda _:None)
    assert not p.writes


def test_uncertain_creation_or_upload_never_creates_second_order_or_repatches():
    p=SandboxProvider(); v=value();v['create_intent']=True
    p.find=lambda _ : []
    with pytest.raises(ValueError,match='No second draft'):
        sandbox.run(v,p,lambda _:source(),None,lambda _:None)
    v=value();p.timeout=True
    with pytest.raises(ProdigiError,match='Acknowledgement lost'):
        sandbox.run(v,p,lambda _:source(),lambda _:('https://fixture.invalid/number.jpg','b'*32),lambda _:None)
    assert v['write_intent'] and len(p.writes)==1
    p.timeout=False
    sandbox.run(v,p,lambda _:source(),lambda _:pytest.fail('No repeat upload'),lambda _:None)
    assert len(p.writes)==1


def test_orders_has_visible_action_and_separate_removable_test_rows():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert "key='orders-prepare-prodigi'" in (root/'orders_page.py').read_text(encoding='utf8')
    text=(root/'prodigi_sandbox_ui.py').read_text(encoding='utf8')
    assert 'Remove sandbox row from app' in text and 'SANDBOX' in text
    assert 'st.json(snap' in text


def test_durable_test_queue_and_cleanup_never_touch_live_preparation_records(store,monkeypatch):
    import uuid
    p=SandboxProvider(); v=value();v['id']=str(uuid.uuid4())
    monkeypatch.setattr(sandbox,'resolve',lambda _:source())
    monkeypatch.setattr(sandbox,'artwork_link',lambda *_:('https://fixture.invalid/number.jpg','b'*32))
    monkeypatch.setattr(sandbox,'SandboxClient',lambda:p)
    with store() as c,c.cursor() as q:
        sandbox.save(q,v)
        q.execute("INSERT INTO app_settings(key,value) VALUES('prodigi_prepare:777','{\"status\":\"Ready for manual payment\"}'::jsonb)")
    with pytest.raises(ValueError,match='finish'):
        sandbox.remove({'id':'fixture'},v['id'])
    result=sandbox.tick()
    assert result['status']=='Needs QA' and result['sandbox_unpaid_verified']
    assert sandbox.tick() is None
    sandbox.remove({'id':'fixture'},v['id'])
    assert sandbox.list_tests()[0]['hidden']
    with store() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key='prodigi_prepare:777'")
        assert q.fetchone()['value']=={'status':'Ready for manual payment'}


def test_duplicate_request_is_rejected_without_creating_a_supplier_order(store,monkeypatch):
    p=Provider();p.data.update(recipient=source()['recipient'],shippingMethod='Standard')
    monkeypatch.setattr(sandbox,'SandboxClient',lambda:SimpleNamespace())
    monkeypatch.setattr(sandbox,'Client',lambda:p)
    monkeypatch.setattr(sandbox,'resolve',lambda _:source())
    first=sandbox.request({'id':'fixture'},1)
    with pytest.raises(ValueError,match='already has'):
        sandbox.request({'id':'fixture'},1)
    assert first['source_order_id']=='99' and len(sandbox.list_tests())==1
    assert not p.writes


def test_sandbox_copies_supplier_shipping_enum_instead_of_shopify_display_label():
    s=source();s['shipping']='US Standard Tracked Shipping'
    test=sandbox.adapted(s,'SC-SANDBOX-fixture',s['recipient'],'Standard')
    assert sandbox.payload(test)['shippingMethod']=='Standard'
    assert s['shipping']=='US Standard Tracked Shipping'


def test_prepare_action_is_visible_before_selection_and_opens_selected_unit(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import orders_page, os_accounts, prodigi_preparation_ui
    selected=[]
    monkeypatch.setattr(orders_page,'_selected_rows_from_state',lambda _:selected)
    monkeypatch.setattr(orders_page,'_configured_supabase_backend',lambda:None)
    monkeypatch.setattr(orders_page,'_render_manual_edition_entry',lambda *a:None)
    monkeypatch.setattr(os_accounts,'is_admin',lambda _:True)
    def render(row,actor):
        import streamlit as st
        st.write('Selected sandbox fixture allocation '+str(row['edition_order_id']))
    monkeypatch.setattr(prodigi_preparation_ui,'render',render)
    app=AppTest.from_string('import orders_page\norders_page._render_top_actions([])').run()
    assert not app.exception and app.button(key='orders-prepare-prodigi').disabled
    selected.append({'edition_order_id':1,'order':'#SC123','edition_number':12})
    app.run()
    assert not app.button(key='orders-prepare-prodigi').disabled
    app.button(key='orders-prepare-prodigi').click().run()
    assert not app.exception
    assert any('Selected sandbox fixture allocation 1' in m.value for m in app.markdown)


def test_sandbox_row_displays_customer_and_can_be_removed_from_orders(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import os_accounts
    monkeypatch.setattr(os_accounts,'is_admin',lambda _:True)
    monkeypatch.setenv('PRODIGI_SANDBOX_API_KEY','synthetic-only')
    v=value(); v.update(status='Needs QA',source_order_id='99',sandbox_unpaid_verified=True,
                        message='SANDBOX test',hidden=False)
    rows=[v]
    monkeypatch.setattr(sandbox,'list_tests',lambda:rows)
    monkeypatch.setattr(sandbox,'remove',lambda user,key:rows.clear())
    app=AppTest.from_string('from prodigi_sandbox_ui import render\nrender([], {"id":"fixture"})').run()
    assert not app.exception and len(app.dataframe)==1
    assert app.dataframe[0].value.iloc[0]['Customer']=='Synthetic Person'
    app.button(key='sandbox-remove-fixture').click().run()
    assert not app.exception and not app.dataframe
