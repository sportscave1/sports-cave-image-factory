from copy import deepcopy
import pytest
import orders_prodigi_grid as grid


@pytest.fixture
def screen(monkeypatch):
    import streamlit as st
    import streamlit.components.v1 as components
    import prodigi_preparation as queue
    import os_accounts
    state={};calls=[];view={};reply={}
    monkeypatch.setattr(st,'session_state',state)
    monkeypatch.setattr(st,'rerun',lambda **kw:calls.append(('rerun',kw)))
    monkeypatch.setattr(st,'toast',lambda *_:None)
    monkeypatch.setattr(st,'error',lambda *_:None)
    def component(**args):view.update(args);return reply.get('event')
    monkeypatch.setattr(components,'declare_component',lambda *a,**k:component)
    monkeypatch.setattr(queue,'enabled',lambda:True)
    monkeypatch.setattr(queue,'request',lambda user,aid:calls.append(('prepare',aid)))
    monkeypatch.setattr(os_accounts,'is_admin',lambda _:True)
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *a:True)
    monkeypatch.setattr(grid,'batch_status',lambda _: {})
    return state,calls,view,reply


def test_send_uses_current_exact_unit_and_replay_is_ignored(screen):
    state,calls,view,reply=screen
    rows=[{'edition_order_id':2},{'edition_order_id':1}]
    reply['event']={'event':'nonce','type':'send','id':grid.row_identity(rows[1])}
    for _ in range(2):grid.render(rows,[{},{}],grid_key='selection',selected=[],actor={'id':'staff'})
    assert [c for c in calls if c[0]=='prepare']==[('prepare',1)]
    assert view['rows'][1]['state']['label']=='Send'


def test_stale_or_unlisted_unit_cannot_be_sent(screen):
    state,calls,view,reply=screen
    reply['event']={'event':'nonce','type':'send','id':'allocation:1'}
    grid.render([{'edition_order_id':2}],[{}],grid_key='selection',selected=[],actor={'id':'staff'})
    assert not calls


def test_selection_survives_reordering_by_stable_unit_identity(screen):
    state,calls,view,reply=screen
    state['orders-prodigi-review']='allocation:2'
    rows=[{'edition_order_id':2},{'edition_order_id':1}]
    reply['event']={'event':'nonce','type':'select','ids':['allocation:1']}
    grid.render(rows,[{},{}],grid_key='selection',selected=[],actor={'id':'staff'})
    assert state['orders-grid-selected-ids']==['allocation:1'] and state['selection']['selection']['rows']==[1]
    assert 'orders-prodigi-review' not in state
    assert grid.row_identity({'shopify_order_id':'a','shopify_line_item_id':'one'})!=grid.row_identity({'shopify_order_id':'a','shopify_line_item_id':'two'})


def test_no_supplier_io_or_writes_when_table_refreshes(screen):
    state,calls,view,reply=screen
    reply['event']={'event':'nonce','type':'refresh'}
    grid.render([{'edition_order_id':2}],[{'product':'Untrusted <script>text</script>'}],grid_key='selection',selected=[],actor={'id':'staff'})
    assert not calls and view['rows'][0]['cells']['product']=='Untrusted <script>text</script>'
