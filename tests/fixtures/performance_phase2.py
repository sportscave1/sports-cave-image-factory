"""Offline Home/Analytics fixture: real renderers, synthetic weekly records."""
from pathlib import Path
import ast
from datetime import datetime
from types import SimpleNamespace, ModuleType
from zoneinfo import ZoneInfo
import html
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import streamlit as st
import sports_cave_dashboard as dashboard
import sports_sales_calendar
import home_daily_planner
import os_accounts
from workspace_display_cache import invalidate_home

st.set_page_config(layout='wide')
BASELINE=os.environ.get('PHASE2_BASELINE')=='1'
app_source=(ROOT/('.tmp-phase2-baseline/app.py' if BASELINE else 'app.py')).read_text(encoding='utf-8')
user={'id':'phase2-offline','role':'admin','display_name':'Offline','is_active':True,'session_version':1}
local_now=datetime(2026,10,8,10,tzinfo=ZoneInfo('Australia/Sydney'))
st.session_state.setdefault('weekly_reads',0)
st.session_state['full_runs']=st.session_state.get('full_runs',0)+1

def weekly(*_):
    st.session_state['weekly_reads']+=1
    time.sleep(.3)  # Deliberate fixture latency, not a production wait.
    return {'metrics':{'tasks_completed':st.session_state['weekly_reads'],'tasks_total':8,'completion_percentage':50},'query_count':1}

fake_dashboard=SimpleNamespace(build_home_event_rows=dashboard.build_home_event_rows,
    build_home_weekly_work_snapshot=weekly, DashboardStorageError=dashboard.DashboardStorageError)
names={'render_html_section_title','_home_duration_label','format_dashboard_timestamp',
       'render_active_upcoming_events','render_home_weekly_work'}
ns=dict(st=st,html=html,time=time,datetime=datetime,timezone_for_os_user=lambda u:ZoneInfo('Australia/Sydney'),
        current_os_user=lambda:user,safe_startup_print=lambda *a:None,sports_cave_dashboard=fake_dashboard,
        os_accounts=os_accounts,set_current_page=lambda *a,**k:None)
nodes=[n for n in ast.parse(app_source).body if isinstance(n,ast.FunctionDef) and n.name in names]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<production home>','exec'),ns)
events=dashboard.load_calendar_events()
route=st.sidebar.radio('Workspace',['Home','Analytics','Other'])
if route=='Home':
    if st.button('Refresh weekly fixture'):invalidate_home(st.session_state)
    with st.container(key='home-ops-dashboard'):
        home_daily_planner.render_status(st,user,local_now)
        ns['render_active_upcoming_events'](events,local_now.date())
        ns['render_home_weekly_work'](user,local_now)
elif route=='Analytics':
    import analytics_page
    if BASELINE:
        analytics_page=ModuleType('phase2_baseline_analytics')
        exec(compile((ROOT/'.tmp-phase2-baseline/analytics_page.py').read_text(encoding='utf-8'),'<baseline analytics>','exec'),analytics_page.__dict__)
    from workspace_display_cache import session_cache
    class Store:
        def report_for_period(self, prop,key,*_):
            st.session_state['analytics_reads']=st.session_state.get('analytics_reads',0)+1
            time.sleep(.06)
            return {'rows':[{'dimensions':{'pageTitle':'Example','country':'Australia','sessionDefaultChannelGroup':'Direct','deviceCategory':'desktop'},'metrics':{'activeUsers':10,'sessions':12}}]}
    analytics_page._overview_breakdowns(analytics_page._ReportDisplayStore(Store(),session_cache(st.session_state,'fixture-analytics',user)),
                                        'offline',{'start_date':'2026-10-01','end_date':'2026-10-07'})
else:st.write('Other page ready')

@st.fragment
def profile():
    st.button('Read profile')
    st.session_state['profile_runs']=st.session_state.get('profile_runs',0)+1
    st.html('<pre id="phase2-profile">'+json.dumps({k:st.session_state.get(k,0) for k in ('full_runs','weekly_reads','analytics_reads','profile_runs')})+'</pre>')
profile()
