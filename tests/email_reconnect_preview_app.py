"""Actual OS/Email UI with controllable faults, no production sockets or DB.

Run with --serve. Arm reads using .venv/email-reconnect-fault.json:
{"id":"unique", "operation":"list_headers", "failures":1, "delay":1}
Use failures=-1 for an outage and a new id/failures=0 to restore the provider.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if '--serve' in sys.argv:
    sys.argv.remove('--serve')
    import os
    os.environ['CRM_MARKETING_ENABLED'] = 'false'
    import uvicorn
    from streamlit.web.server.starlette import App
    from starlette.routing import Route
    from starlette.responses import JSONResponse, StreamingResponse
    import top_bar_api
    async def empty(request):
        return JSONResponse({'ok':True,'notifications':[],'items':[],'results':[],
                             'timer':{},'action_required_count':0,'unread_count':0})
    routes = [Route(p,empty) for p in (top_bar_api.EMAIL_STATUS_PATH,top_bar_api.ORDER_STATUS_PATH,
              top_bar_api.NOTIFICATIONS_PATH,top_bar_api.DAILY_PLANNER_STATUS_PATH,top_bar_api.REPAIR_REQUESTS_PATH)]
    async def events(request):
        import asyncio
        async def stream():
            while not await request.is_disconnected():
                yield ': local fixture\n\n'
                await asyncio.sleep(15)
        return StreamingResponse(stream(),media_type='text/event-stream')
    routes.append(Route('/api/os/top-bar/email-events',events))
    uvicorn.run(App(str(Path(__file__).resolve()),routes=routes),host='127.0.0.1',port=8511)
else:
    import runpy,time,json
    from unittest.mock import Mock
    import streamlit as st
    import requests,supabase_backend
    import support_email_page as page
    import support_email_store as store
    import support_email_provider as provider
    import support_email_smtp as smtp
    from support_email_workspace import Workspace
    from support_email_compose import default_settings
    from tests.email_v2_fixtures import MailboxFixture, CONFIG

    def forbidden(*a,**kw):raise AssertionError('Production I/O forbidden')
    requests.sessions.Session.request = forbidden
    supabase_backend.connect = forbidden
    provider.imaplib.IMAP4_SSL = forbidden
    smtp.smtplib.SMTP_SSL = forbidden
    store.load_email_settings = lambda *a:(default_settings(),None)
    store.load_metadata = lambda *a,**kw:{}
    store.load_orders = lambda *a,**kw:[]
    store.load_assignees = lambda *a,**kw:[]
    store.audit = Mock()
    user={'id':'fixture-mail','username':'fixture','display_name':'Nathan · local fixture','role':'admin',
          'is_active':True,'page_permissions':['email'],'timezone':'Australia/Sydney'}
    st.session_state.update(sports_cave_authenticated=True,sports_cave_current_user=user,
                           sports_cave_auth_checked_at=time.monotonic())
    st.session_state.setdefault('current_page','Email')
    st.session_state.setdefault('selected_page','Email')

    class FaultMailbox:
        def __init__(self):
            self.mailbox=MailboxFixture(25)
            self.mailbox.messages[0]['folder']='Archive'
            self.fault_id=None
            self.remaining=0
        def __getattr__(self,name):
            method=getattr(self.mailbox,name)
            if name not in {'discover_folders','list_headers','read_message','live_changes'}:return method
            def call(*a,**kw):
                path=Path('.venv/email-reconnect-fault.json')
                fault=json.loads(path.read_text()) if path.exists() else {}
                if fault.get('id')!=self.fault_id:
                    self.fault_id=fault.get('id');self.remaining=fault.get('failures',0)
                if name==fault.get('operation') and self.remaining:
                    if self.remaining>0:self.remaining-=1
                    time.sleep(fault.get('delay',1))
                    raise provider.MailboxError('Email connection timed out. Retry connection.',code='timeout',retryable=True)
                return method(*a,**kw)
            return call
    mailbox=st.session_state.setdefault('reconnect_fixture',FaultMailbox())
    page.load_configuration=lambda:CONFIG
    page.load_smtp_configuration=lambda:smtp.SMTPConfiguration(password='fixture')
    page.Workspace=lambda state,user,config,smtp_cfg:Workspace(state,user,config,smtp_cfg,imap=mailbox,
                                                             smtp=Mock(submit=forbidden))
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'),run_name='__main__')
