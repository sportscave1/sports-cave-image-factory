"""Offline toolbar fixture with canonical URL keys and history-safe route updates."""
from pathlib import Path
source = (Path(__file__).with_name('home_shell_preview.py')).read_text(encoding='utf-8')
bridge = '''
def get_current_page():
    history = st.session_state.get(NAVIGATION_HISTORY_ROUTE_STATE_KEY) or {}
    value = history.get('route') or st.query_params.get('page', 'dashboard')
    return next((page['route'] for page in os_accounts.PAGE_REGISTRY if page['key'] == value or page['route'] == value), 'Dashboard')
def set_current_page(route, *, source='sidebar', sync_query=True, **kwargs):
    if source != 'browser-history':
        st.session_state.pop(NAVIGATION_HISTORY_ROUTE_STATE_KEY, None)
    if sync_query:
        st.query_params['page'] = os_accounts.page_key_for_route(route)
    return route
'''
source = source.replace("st.set_page_config(layout='wide'", bridge + "\nst.set_page_config(layout='wide'")
exec(compile(source, __file__, 'exec'))
