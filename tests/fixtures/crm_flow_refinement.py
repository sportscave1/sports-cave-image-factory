"""Measured Flow fixture over disposable SQL; external services are blocked."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import json
import os
import subprocess
import types
if os.environ.get('FLOW_PROFILE_BASELINE')=='1' and not getattr(sys,'_flow_baseline_loaded',False):
    baseline_ref=os.environ.get('FLOW_PROFILE_BASELINE_REF','01bc526')
    for name in ('crm_checkout_analytics','crm_automation_analytics_ui','crm_automation_toolbar','crm_flow_page'):
        source=subprocess.check_output(['git','show',baseline_ref+':'+name+'.py'],text=True,encoding='utf-8')
        module=types.ModuleType(name);module.__file__=str(Path(__file__).resolve().parents[2]/(name+'.py'))
        sys.modules[name]=module
        exec(compile(source,module.__file__,'exec'),module.__dict__)
    sys._flow_baseline_loaded=True
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
    st.html('<pre id="flow-profile" style="white-space:pre-wrap;overflow-wrap:anywhere">' + json.dumps({**metrics, 'full_runs': st.session_state['profile_full_runs'], 'tick': tick}) + '</pre>')
counters()
