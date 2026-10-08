"""Measured Flow fixture over disposable SQL; external services are blocked."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import json
import runpy
import threading
import streamlit as st
from crm_automation_store import AutomationStore


@st.cache_resource
def instrumentation():
    metrics = {'queries': 0, 'reports': 0, 'activity': 0, 'checkouts': 0, 'flow_renders': 0}
    lock = threading.Lock()
    original = AutomationStore.q
    def query(self, sql, *args, **kwargs):
        with lock:
            metrics['queries'] += 1
            if 'AS history' in sql: metrics['reports'] += 1
            if 'FROM crm_automation_events' in sql: metrics['activity'] += 1
            if 'WITH selected AS MATERIALIZED' in sql: metrics['checkouts'] += 1
        return original(self, sql, *args, **kwargs)
    AutomationStore.q = query
    import crm_flow_page
    original_page = crm_flow_page.flow_page
    def flow_page(*args, **kwargs):
        metrics['flow_renders'] += 1
        return original_page(*args, **kwargs)
    crm_flow_page.flow_page = flow_page
    return metrics


metrics = instrumentation()
st.session_state['profile_full_runs'] = st.session_state.get('profile_full_runs', 0) + 1
runpy.run_path(str(Path(__file__).with_name('crm_automation_preview.py')))


@st.fragment
def counters():
    st.button('Profile snapshot')
    tick = st.session_state.get('profile_tick', 0) + 1
    st.session_state['profile_tick'] = tick
    st.html('<pre id="flow-profile">' + json.dumps({**metrics, 'full_runs': st.session_state['profile_full_runs'], 'tick': tick}) + '</pre>')
counters()
