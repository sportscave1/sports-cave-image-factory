"""Offline comparison of actual Orders marker fragments with 1.28s fake I/O."""
import ast
from pathlib import Path
import time
import streamlit as st

st.set_page_config(layout='wide')
mode=st.query_params.get('mode','after')
source=Path('orders_page.py').read_text(encoding='utf-8')
route=st.sidebar.radio('Workspace',['Orders','Other'])
st.session_state['current_page']=route
st.session_state['sports_cave_current_user']={'id':'offline'}
st.session_state['runs']=st.session_state.get('runs',0)+1

def marker():
    time.sleep(1.28)  # Simulated network only; never used by production.
    return 'fixture-v1'

ns=dict(st=st,_certificate_action_in_progress=lambda:False,
        _orders_supabase_visibility_marker=marker,_reload_orders_from_source=lambda:None,
        ORDERS_SUPABASE_LIVE_MARKER_KEY='marker',ORDERS_SUPABASE_LIVE_CHECK_SECONDS=30)
names={'_check_orders_supabase_live_refresh','_render_orders_supabase_live_refresh'}
nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
if mode=='before':
    # Reproduce the pre-Phase-3 synchronous scheduling, keeping the same renderer.
    for node in nodes:
        for call in ast.walk(node):
            if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='fragment':
                call.keywords=[kw for kw in call.keywords if kw.arg!='parallel']
exec(compile(ast.Module(body=nodes,type_ignores=[]),'orders_page.py','exec'),ns)
if route=='Orders':
    st.subheader('Orders fixture')
    st.dataframe([{'Order':'Synthetic 1','Product':'Fixture artwork'}],hide_index=True)
    ns['_render_orders_supabase_live_refresh']()
    st.html('<div id="ready">Orders rendering complete</div>')
else: st.write('Other page ready')
st.caption(f'Full runs: {st.session_state["runs"]}')
