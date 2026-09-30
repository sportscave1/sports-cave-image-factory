"""Local-only shell preview; no production services, credentials, or data."""
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
source = (Path(__file__).resolve().parents[1] / 'sidebar_preview_app.py').read_text(encoding='utf-8')
# Reuse the production sidebar extraction without its demonstration content.
__file__ = str(Path(__file__).resolve().parents[1] / 'sidebar_preview_app.py')
exec(compile(source[:source.index('st.set_page_config(')], str(Path(__file__).resolve().parents[1] / 'sidebar_preview_app.py'), 'exec'))
import top_bar, home_daily_planner
st.set_page_config(layout='wide', initial_sidebar_state='expanded')
st.session_state.setdefault('route', 'Dashboard')
import sidebar_theme
inject_styles()
render_sidebar()
with patch('top_bar_security.create_top_bar_token', return_value='local-fixture-only'):
    config = top_bar.top_bar_config(current_os_user(), logo_src='data:image/webp;base64,' + __import__('base64').b64encode((Path.cwd()/'assets/sports-cave-os-app-icon.webp').read_bytes()).decode(), current_route=get_current_page())
config['userDisplayName'] = 'Nathan'
config['dailyPlannerTimerScope'] = 'home-preview-only'
config['dailyPlannerStatusUrl'] = 'http://127.0.0.1:1/unavailable'
# Deliberately unavailable local APIs exercise shell failure isolation.
seed = ""
if st.query_params.get('active') == '1':
    seed = """<script>if (!window.parent.localStorage.getItem('scSportsCavePlannerTimerState:home-preview-only')) window.parent.localStorage.setItem('scSportsCavePlannerTimerState:home-preview-only', JSON.stringify({type:'timer-state',source:'preview',scope:'home-preview-only',timer:{id:'preview-timer',task:'Review today’s work',status:'running',allocated_seconds:3600,remaining_seconds:3600,deadline_at:new Date(Date.now()+3600000).toISOString()},sent_at:Date.now()}));</script>"""
components.html(seed + top_bar.component_html(config), height=0, width=0)
with st.container(key='home-ops-dashboard'):
    home_daily_planner.render_status(st, current_os_user(), datetime.now())
    st.subheader('Active & Upcoming Events')
    st.caption('Local preview - no external calendar or storage requests.')
    st.subheader("This Week's Work")
    st.caption('Local preview - weekly summary data is not loaded.')
