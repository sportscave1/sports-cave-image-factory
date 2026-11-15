"""Local full-shell browser verification. Fake providers; disposable SQL only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if '--serve' in sys.argv:
    sys.argv.remove('--serve')
    import os
    os.environ['CRM_MARKETING_ENABLED']='false'
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
    import runpy,time,json
    from unittest.mock import Mock
    import streamlit as st
    import requests,supabase_backend,crm_page,crm_service,crm_preview_cache
    from crm_navigation import PAGES
    from crm_store import Store
    from crm_shopify import Shopify
    from tests.crm_db_fixture import connect
    from tests.crm_fixtures import ShopifyFixture
    def forbidden(*a,**kw):raise AssertionError('Production I/O forbidden in local verification')
    requests.sessions.Session.request=forbidden
    supabase_backend.connect=forbidden
    crm_service.audit=Mock()
    user={'id':'fixture-crm-user','username':'fixture','display_name':'Nathan · local fixture','role':'admin','is_active':True,
          'page_permissions':['email',*[p[0] for p in PAGES]],'timezone':'Australia/Sydney'}
    st.session_state.update(sports_cave_authenticated=True,sports_cave_current_user=user,sports_cave_auth_checked_at=time.monotonic())
    st.session_state.setdefault('current_page','CRM Campaigns');st.session_state.setdefault('selected_page','CRM Campaigns')
    fixture=st.session_state.setdefault('crm_fixture_authority',ShopifyFixture())
    crm_page.Store=lambda:Store(connect)
    crm_page.Shopify=lambda:Shopify(fixture)
    if not st.session_state.get('seeded'):Store(connect).seed();st.session_state['seeded']=True
    def metric(name):
        values=st.session_state.setdefault('profile_counts',{})
        values[name]=values.get(name,0)+1
        Path('.venv/communications-browser-metrics.json').write_text(json.dumps(values),encoding='utf-8')
    if not hasattr(Store,'_profile_q'):
        Store._profile_q=Store.q
        def query(self,*a,**kw):metric('db_reads');return self._profile_q(*a,**kw)
        Store.q=query
    if not hasattr(crm_preview_cache,'_profile_render'):
        crm_preview_cache._profile_render=crm_preview_cache.render_campaign
        def render(*a,**kw):metric('preview_regenerations');return crm_preview_cache._profile_render(*a,**kw)
        crm_preview_cache.render_campaign=render
    metric('full_page_runs')
    import support_email_page,support_email_store,support_email_smtp,support_email_provider
    from support_email_workspace import Workspace
    from support_email_compose import default_settings
    from tests.email_v2_fixtures import MailboxFixture,fixture_smtp,CONFIG
    mailbox=st.session_state.setdefault('fixture_mailbox',MailboxFixture(25))
    support_email_page.load_configuration=lambda:CONFIG
    support_email_page.load_smtp_configuration=lambda:support_email_smtp.SMTPConfiguration(password='fixture-only')
    support_email_store.load_email_settings=lambda *a:(default_settings(),None)
    support_email_store.load_metadata=lambda *a,**kw:{}
    support_email_store.load_orders=lambda *a,**kw:[]
    support_email_store.load_assignees=lambda *a,**kw:[]
    support_email_store.audit=Mock()
    support_email_provider.imaplib.IMAP4_SSL=forbidden
    support_email_smtp.smtplib.SMTP_SSL=forbidden
    def workspace(state,user,config,smtp):
        return Workspace(state,user,config,smtp,imap=mailbox,smtp=fixture_smtp())
    support_email_page.Workspace=workspace
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'),run_name='__main__')
