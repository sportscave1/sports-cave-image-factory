"""Exercise pending component events inside a real full-run fragment context."""
from copy import deepcopy
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize('kind',['feed','select'])
def test_pending_grid_event_during_full_app_run_never_requests_fragment_rerun(monkeypatch,kind):
    import streamlit.components.v1 as components
    import orders_feed
    import orders_prodigi_grid as grid
    import prodigi_preparation
    import os_accounts
    view={};reply={}
    def component(**args):
        view.update(args)
        return reply.get('event')
    monkeypatch.setattr(components,'declare_component',lambda *a,**kw:component)
    monkeypatch.setattr(prodigi_preparation,'enabled',lambda:True)
    monkeypatch.setattr(os_accounts,'is_admin',lambda _:True)
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    app=AppTest.from_string('''
import streamlit as st
import orders_prodigi_grid as grid
@st.fragment
def workspace():
    grid.render([{'edition_order_id':1}],[{}],grid_key='fixture-selection',selected=[],actor={'id':'fixture'},statuses={})
workspace()
st.caption('Page render completed')
''').run()
    assert not app.exception
    raw=[{'edition_order_id':2}]
    snapshot=dict(version='fixture-version',raw=raw,rows=grid.payload_rows(raw,[{}],{},allowed=True))
    monkeypatch.setattr(orders_feed,'recalled',lambda *_:deepcopy(snapshot))
    reply['event']=dict(event='pending-'+kind,type=kind,scope=view['feed']['scope'],version='fixture-version',ids=['allocation:2'])
    # This is a full app render, even though render() runs within @st.fragment.
    app.run()
    assert not app.exception and app.caption[-1].value=='Page render completed'
    assert app.session_state['orders_allocation_rows']==[{'edition_order_id':2}]
    if kind=='select':assert app.session_state['orders-grid-selected-ids']==['allocation:2']
    app.run()
    assert not app.exception and [r['id'] for r in view['rows']]==['allocation:2']
    if kind=='select':assert view['selected']==['allocation:2']


def test_real_fragment_context_still_uses_only_fragment_rerun(monkeypatch):
    from types import SimpleNamespace
    import streamlit.runtime.scriptrunner as runner
    import orders_prodigi_grid as grid
    calls=[]
    monkeypatch.setattr(runner,'get_script_run_ctx',lambda **_:SimpleNamespace(fragment_ids_this_run=['fixture']))
    grid._rerun_active_fragment(SimpleNamespace(rerun=lambda **kw:calls.append(kw)))
    assert calls==[{'scope':'fragment'}]
