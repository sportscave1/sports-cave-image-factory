"""Actual app.py shell + synthetic CRM data. Run Python --serve on localhost:8510.
Requires the isolated tests/crm_postgres_server.mjs process. No external I/O.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if '--serve' in sys.argv:
    sys.argv.remove('--serve')
    import uvicorn
    from streamlit.web.server.starlette import App
    from starlette.routing import Route
    from starlette.responses import JSONResponse,StreamingResponse
    import top_bar_api
    async def empty(request):return JSONResponse({'ok':True,'notifications':[],'items':[],'results':[],'timer':{},'action_required_count':0,'unread_count':0})
    routes=[Route(p,empty) for p in (top_bar_api.EMAIL_STATUS_PATH,top_bar_api.ORDER_STATUS_PATH,top_bar_api.NOTIFICATIONS_PATH,top_bar_api.DAILY_PLANNER_STATUS_PATH,top_bar_api.REPAIR_REQUESTS_PATH)]
    async def events(request):
        import asyncio
        async def stream():
            while not await request.is_disconnected():
                yield ': fixture heartbeat\n\n'
                await asyncio.sleep(15)
        return StreamingResponse(stream(),media_type='text/event-stream')
    routes.append(Route('/api/os/top-bar/email-events',events))
    uvicorn.run(App(str(Path(__file__).resolve()),routes=routes),host='127.0.0.1',port=8510)
else:
    import runpy
    import time
    from unittest.mock import patch
    import streamlit as st
    import requests
    import supabase_backend
    import crm_page
    import crm_service
    from crm_navigation import ROUTES,PAGES
    from crm_shopify import Shopify
    from crm_store import Store
    from crm_resend import Config
    from tests.crm_db_fixture import connect
    from tests.crm_fixtures import ShopifyFixture
    user={'id':'fixture-crm-user','username':'fixture','display_name':'Nathan · local CRM fixture','role':'worker','is_active':True,
          'page_permissions':['email',*[p[0] for p in PAGES]],'timezone':'Australia/Sydney'}
    st.session_state['sports_cave_authenticated']=True
    st.session_state['sports_cave_current_user']=user
    st.session_state['sports_cave_auth_checked_at']=time.monotonic()
    st.session_state.setdefault('current_page',ROUTES[0]);st.session_state.setdefault('selected_page',ROUTES[0])
    fixture=st.session_state.setdefault('crm_fixture_authority',ShopifyFixture())
    store=Store(connect)
    if not st.session_state.get('crm_fixture_seeded'):store.seed();st.session_state['crm_fixture_seeded']=True
    render=crm_page.render_page
    def crm_render(route,user,navigate):return render(route,user,navigate,shop=Shopify(fixture),store=store,config=Config({}))
    # Existing Email workspace/component with fabricated providers, inside the real shell.
    import support_email_page
    @st.fragment
    def email_render(_):
        import support_email_store as email_store
        import support_email_smtp as smtp
        from support_email_compose import default_settings
        from support_email_workspace import Workspace
        from tests.email_v2_fixtures import MailboxFixture,fixture_smtp,USER,WORKER,CONFIG
        mailbox=st.session_state.setdefault('crm_fixture_mailbox',MailboxFixture(25))
        registry=st.session_state.setdefault('crm_fixture_receipts',smtp.SendRegistry())
        state=st.session_state.setdefault('crm_fixture_email_state',{})
        with (patch.object(email_store,'load_email_settings',return_value=(default_settings(),None)),
              patch.object(email_store,'load_metadata',return_value={}),patch.object(email_store,'load_assignees',return_value=[USER,WORKER]),
              patch.object(email_store,'load_orders',return_value=[]),patch.object(email_store,'audit')):
            workspace=Workspace(state,USER,CONFIG,smtp.SMTPConfiguration(password='fixture-only'),imap=mailbox,smtp=fixture_smtp(),registry=registry)
            if not state.get('loaded'):workspace.load()
            support_email_page.email_shell_styles()
            with st.container(key='support-email-shell'):
                event=support_email_page.get_component()(model=workspace.model(),key='fixture-email',default=None)
                if event and workspace.handle(event):support_email_page.rerun_email()
    with (patch.object(crm_page,'render_page',side_effect=crm_render),patch.object(crm_service,'audit'),
          patch.object(requests.sessions.Session,'request',side_effect=AssertionError('External HTTP forbidden in CRM fixture')),
          patch.object(supabase_backend,'connect',side_effect=AssertionError('Production database forbidden in CRM fixture')),
          patch.object(support_email_page,'render_page',side_effect=email_render)):
        runpy.run_path(str(Path(__file__).resolve().parents[2]/'app.py'),run_name='__main__')
