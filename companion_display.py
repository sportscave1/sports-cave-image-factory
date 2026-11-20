"""Account-scoped, nonblocking queue displays. Actions always use live validation."""
from datetime import datetime, timezone
from uuid import uuid4
from display_snapshot import Snapshots

CACHE = Snapshots(workers=2, limit=32, ttl=10, retry=5, max_age=120, byte_limit=16000000)

def invalidate():
    CACHE.invalidate_matching(lambda key: True)

def read(name, loader):
    import streamlit as st
    scope = st.session_state.get('companion-display-scope') or st.session_state.setdefault('companion-display-session', str(uuid4()))
    result = CACHE.read((scope, name), loader)
    if result['checked_at']:
        checked = datetime.fromtimestamp(result['checked_at'], timezone.utc).strftime('%H:%M:%S UTC')
        st.caption('Last verified '+checked+' | '+('Live' if result['state']=='ready' else 'Refreshing; showing saved status'))
    if result['value'] is None:
        st.info('Loading '+name+' status. This panel retries automatically; your jobs continue in the background.')
    elif result['state'] != 'ready':
        st.warning('Status is refreshing. Saved information remains visible; actions are revalidated when submitted.')
    return result['value']


def visible():
    import streamlit as st
    from pathlib import Path
    from streamlit.components.v1 import declare_component
    component = declare_component('companion_visibility', path=str(Path(__file__).parent/'components'/'companion_visibility'))
    return component(key='companion-visible', default=True) is not False


def page_rows(rows, key, size=10):
    import streamlit as st
    if len(rows)<=size: return rows
    pages = (len(rows)+size-1)//size
    if st.session_state.get(key,1)>pages: st.session_state[key]=1
    page = st.number_input('Page', min_value=1, max_value=pages, step=1, key=key)
    start = (page-1)*size
    st.caption(f'{start+1}-{min(start+size,len(rows))} of {len(rows)} loaded jobs')
    return rows[start:start+size]
