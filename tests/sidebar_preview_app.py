"""Run the actual sidebar without application startup, services or page loaders."""
import ast
from pathlib import Path
import html
import streamlit as st
import streamlit.components.v1 as components
import os_accounts, navigation_runtime, social_media
import seo_navigation as seo_nav
import ads_navigation as ads_nav
import analytics_navigation as analytics_nav
import files_window_launcher

source=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
tree=ast.parse(source)
names={'inject_styles','_sidebar_route_button','_active_sidebar_group','_toggle_sidebar_group','_render_sidebar_create_growth','_render_sidebar_create_reporting','render_sidebar'}
constants={'SIDEBAR_ICON_BY_ROUTE','SIDEBAR_NAV_LABELS','SIDEBAR_OPEN_GROUP_KEY','MENU_OPTIONS','NAVIGATION_HISTORY_ROUTE_STATE_KEY'}
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in names or isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets):
        exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'))

def get_current_page():return st.session_state.setdefault('route',st.query_params.get('page','CRM Campaigns'))
def set_current_page(route,**kwargs):st.session_state['route']=route;st.query_params['page']=route
def current_os_user():return {'id':'local-preview','role':'admin','is_active':True,'display_name':'Local preview'}
def get_components_module():return components
def page_query_param_value():return st.query_params.get('page','')
def logout_app():st.info('Local navigation preview only')

st.set_page_config(layout='wide',initial_sidebar_state='expanded')
import importlib,sidebar_theme
importlib.reload(sidebar_theme)
inject_styles()
render_sidebar()
st.title(get_current_page())
st.caption('Local sidebar verification. Actual navigation helpers; no page loaders or external services.')
st.button('Main content button')
