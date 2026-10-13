"""Shared checkout-master recipient interaction layer; never grants eligibility.

Adapters own queries, projections and guarded actions. This module owns disclosure,
widget retention and the single table event protocol for every flow.
"""
from pathlib import Path
import json
import streamlit as st


def selection(state,slot,keys,event):
    selected=set(state.get(slot+'-selected',[]))
    if not isinstance(event,dict) or event.get('sequence')==state.get(slot+'-event'):
        return sorted(selected)
    state[slot+'-event']=event.get('sequence')
    # Refresh receipts are observations, never selection commands. A delayed
    # timer must not undo a more recent checkbox interaction.
    if not event.get('refresh'):
        if event.get('clear_selection') is True:selected.clear()
        else:
            selected.difference_update(keys)
            selected.update(k for k in event.get('selected',[]) if k in keys)
        state[slot+'-selected']=sorted(selected)
        if event.get('detail') in keys:state[slot+'-detail']=event['detail']
        if event.get('close_detail') is True:state.pop(slot+'-detail',None)
        if event.get('retry') in keys:state[slot+'-retry']=event['retry']
    return sorted(selected)


def current_definition(row):
    cached=st.session_state.get('_automation_toolbar_definition')
    if cached and str(cached[0][0])==str(row['id']):return cached[1]
    return row


def table_event(slot):
    event=st.session_state.get(slot+'-table')
    if isinstance(event,dict) and event.get('context')==st.session_state.get(slot+'-table-context'):
        selection(st.session_state,slot,set(st.session_state.get(slot+'-visible',[])),event)


def retain(slot):
    """Called before collapsed widgets disappear and from table callbacks."""
    for suffix in ('search','status','filter','sort','from','through'):
        key=slot+'-'+suffix
        if key in st.session_state:st.session_state[key+'-retained']=st.session_state[key]


def restore(slot):
    for suffix in ('search','status','filter','sort','from','through'):
        key=slot+'-'+suffix
        if key+'-retained' in st.session_state:
            st.session_state[key]=st.session_state[key+'-retained']


@st.fragment
def panel(title,slot,body,*args,panel_key=None,**kwargs):
    """Only user toggles rerun this shell; reads/events rerun its child body."""
    key=panel_key or slot+'-panel'
    retained=slot+'-panel-open'
    if retained in st.session_state:st.session_state[key]=st.session_state[retained]
    def remember():
        if not st.session_state[key]:retain(slot)
        st.session_state[retained]=bool(st.session_state[key])
    with st.expander(title,key=key,on_change=remember) as disclosure:
        if disclosure.open:
            restore(slot)
            body(*args,**kwargs)
            retain(slot)


def table(slot,context,*,rows,columns,**kwargs):
    from crm_component_json import render_component
    import streamlit.components.v1 as components
    component=components.declare_component('crm_checkout_table',path=str(Path(__file__).parent/'components/crm_checkout_table'))
    st.session_state[slot+'-table-context']=json.dumps(context,default=str)
    st.session_state[slot+'-visible']=[r['key'] for r in rows]
    retain(slot)
    return render_component(component,rows=rows,columns=columns,
        selected=st.session_state.get(slot+'-selected',[]),
        selection_context=st.session_state[slot+'-table-context'],state_key=slot,
        detail_key=st.session_state.get(slot+'-detail'),
        on_change=lambda:table_event(slot),key=slot+'-table',default=None,**kwargs)


def read_page(store,slot,key,load,ttl):
    """One bounded read/stale-state policy for every recipient adapter.

    Keys include source, definition version and filter/page identity. Background
    receipts reuse them; only explicit retries create a new generation.
    """
    from crm_automation_analytics_ui import read,state
    from crm_automation_home import arm_section
    from crm_logic import now
    from datetime import timedelta
    from time import monotonic
    records,phase=read(store,key,load,ttl,wait_budget=.15)
    pages=st.session_state.setdefault(slot+'-snapshots',{})
    identity=(store.connect,key)
    previous=pages.get(identity)
    if records is not None and phase=='READY':
        entry=state().get('campaign_home_cache',{}).get(identity)
        completed=entry[0] if entry else None
        at=now()-timedelta(seconds=max(0,monotonic()-completed)) if completed is not None else now()
        pages[identity]=(records,at)
        while len(pages)>8:pages.pop(next(iter(pages)))
    elif previous is not None:
        records,at=previous
    else:at=now()
    # Keep the table's delta path fixed when a pending read settles.
    with st.container(key=slot+'-settle-host'):
        if phase in ('LOADING','REFRESHING','NOT_STARTED'):arm_section(slot+'-settle',.25,dialog=True)
    return records,phase,at


def retry_read(slot,phase,label='Retry recipients'):
    """Shared compact recovery, including terminal timeouts."""
    if phase in ('ERROR','TIMED_OUT') and st.button(label,key=slot+'-retry-read'):
        st.session_state[slot+'-refresh']=st.session_state.get(slot+'-refresh',0)+1
        st.rerun(scope='fragment')


def close_details(slot):
    st.button('Close details',key=slot+'-close-details',
        on_click=lambda:st.session_state.pop(slot+'-detail',None))


def pagination(slot,page,count,more,previous,next_page,*,labels=('Previous','Next'),noun='records'):
    """One native event per page change; no second fragment rerun."""
    with st.container(horizontal=True,key=slot+'-pagination'):
        st.button(labels[0],disabled=page==0,key=slot+'-previous',on_click=previous)
        st.caption('Page '+str(page+1)+' · '+str(count)+' '+noun)
        st.button(labels[1],disabled=not more,key=slot+'-next',on_click=next_page)


STYLE='''<style>
    div[role="dialog"]:has(.st-key-checkout-compact)>div:first-child{padding:12px 24px 4px!important}
    div[role="dialog"]:has(.st-key-checkout-compact)>div:nth-child(2){padding:4px 24px 16px!important}
    div[role="dialog"]:has(.st-key-checkout-compact) [data-testid="stVerticalBlock"]{gap:.5rem}
    .st-key-checkout-compact [data-testid="stVerticalBlock"]{gap:.5rem}
    .st-key-checkout-compact h3{padding:0;font-size:1.2rem;line-height:2rem}
    .st-key-checkout-compact [data-testid="stHorizontalBlock"]{gap:.5rem;align-items:center}
    .st-key-checkout-compact [data-baseweb="select"]>div{min-height:32px;height:32px}
    .st-key-checkout-compact [data-baseweb="input"]{height:32px;min-height:32px}
    .st-key-checkout-compact [data-testid="stButton"] button{min-height:32px;padding:.2rem .65rem}
    .st-key-checkout-compact [data-testid="stButton"] button p{font-size:13px}
    .st-key-checkout-compact [data-testid="stCustomComponentV1"]{min-width:0;max-width:100%}
    .st-key-checkout-compact iframe{width:100%!important;max-width:100%;min-width:0}
    .st-key-checkout-compact :is([data-testid="stTextInputRootElement"],.react-aria-ComboBox>[role="group"]){height:32px;min-height:32px;background:#fffefa;border:1px solid #e4e2da;border-radius:4px}
    .st-key-checkout-compact :is([data-testid="stTextInputField"],[role="combobox"]){height:30px;min-height:0;padding:.2rem .55rem;font-size:13px}
    .st-key-flow-recipient-toolbar [data-testid="stPopover"] button{height:32px;min-height:32px}
    .st-key-checkout-compact [class*="-pagination"]{align-items:center;gap:.5rem}
    .st-key-checkout-compact [class*="-pagination"] p{margin:0;font-size:12px;font-variant-numeric:tabular-nums}
    .st-key-checkout-compact button:focus-visible{outline:2px solid #9a7937;outline-offset:2px}
    .st-key-flow-recipient-toolbar [data-testid="stPopover"] button [data-testid="stMarkdownContainer"]{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
    </style>'''
