"""Run with Python --serve on localhost:8504. Real IMAP/SMTP/database are never used."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

if '--serve' in sys.argv:
    sys.argv.remove('--serve')  # Streamlit's script runner shares this process argv.
    import uvicorn
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from streamlit.web.server.starlette import App
    import top_bar_api
    from tests.fixtures import email_notification_runtime as fixture

    async def status(request):return JSONResponse({'ok':True,**fixture.status()})
    async def orders(request):return JSONResponse({'ok':True,'action_required_count':7,'badge_label':'7','notification':{}})
    async def events(request):
        rows=fixture.DATABASE.events+[{'event_type':'new_order_received','entity_id':'order-fixture','source':'Orders',
            'created_at':'2026-09-27T02:00:00+00:00','new_value':{'page':'Orders','message':'New order received — #SC3001'}}]
        return JSONResponse({'ok':True,'notifications':top_bar_api.build_notifications(
            {'sub':'fixture','allowed_routes':['Dashboard','Orders','Email'],'can_view_activity':True,'can_view_all_activity':True},activity_rows=rows)})
    async def empty(request):return JSONResponse({'ok':True,'timer':{},'items':[],'results':[]})
    async def search(request):return JSONResponse({'ok':True,'results':[
        {'title':name,'subtitle':'Local fixture page','group':'Pages','route_key':key,'keywords':[]}
        for key,name in [('dashboard','Dashboard'),('orders','Orders'),('email','Email')]]})
    routes=[Route(top_bar_api.EMAIL_STATUS_PATH,status),Route(top_bar_api.ORDER_STATUS_PATH,orders),
            Route(top_bar_api.NOTIFICATIONS_PATH,events),Route(top_bar_api.DAILY_PLANNER_STATUS_PATH,empty),
            Route(top_bar_api.REPAIR_REQUESTS_PATH,empty),Route(top_bar_api.SEARCH_INDEX_PATH,search)]
    uvicorn.run(App(str(Path(__file__).resolve()),routes=routes),host='127.0.0.1',port=8504)
else:
    from unittest.mock import patch
    import streamlit as st
    import streamlit.components.v1 as components
    import support_email_provider as provider
    import support_email_smtp as smtp
    import support_email_store as store
    from support_email_compose import default_settings
    from support_email_page import get_component,email_shell_styles,rerun_email
    from support_email_workspace import Workspace
    import top_bar
    import base64
    from tests.email_v2_fixtures import CONFIG,USER,WORKER,fixture_smtp
    from tests.fixtures import email_notification_runtime as fixture

    st.set_page_config(page_title='Email notifications · local mock OS',layout='wide',initial_sidebar_state='expanded')
    route=st.query_params.get('page','dashboard')
    user=WORKER if st.query_params.get('account')=='staff' else USER
    names={'dashboard':'Dashboard','orders':'Orders','email':'Email'}
    with st.sidebar:
        for key,label in names.items():
            with st.container(key='sidebar-row-'+key):
                if st.button(label,key='nav-'+key,use_container_width=True):
                    st.query_params['page']=key;st.rerun()
        st.caption('LOCAL FIXTURE · no external I/O')
    logo=Path(__file__).resolve().parents[2]/'assets/sports-cave-os-app-icon.webp'
    logo_src='data:image/webp;base64,'+base64.b64encode(logo.read_bytes()).decode('ascii')
    config=top_bar.top_bar_config(user,logo_src=logo_src,current_route=names.get(route,'Dashboard'))
    config.update(dailyPlannerEnabled=False,navigationRouteKeys={v:k for k,v in names.items()},navigationRouteLabels=names)
    components.html(top_bar.component_html(config),height=0,width=0)

    @st.fragment
    def mailbox():
        with (patch.object(provider.imaplib,'IMAP4_SSL',side_effect=AssertionError('Real IMAP forbidden')),
              patch.object(smtp.smtplib,'SMTP_SSL',side_effect=AssertionError('Real SMTP forbidden')),
              patch.object(store,'load_email_settings',return_value=(default_settings(),None)),
              patch.object(store,'load_metadata',return_value={}),patch.object(store,'load_assignees',return_value=[USER,WORKER]),
              patch.object(store,'load_orders',return_value=[]),patch.object(store,'audit')):
            state=st.session_state.setdefault('fixture_workspace',{})
            workspace=Workspace(state,user,CONFIG,smtp.SMTPConfiguration(password='fixture-only'),
                imap=fixture.MAILBOX_FIXTURE,smtp=fixture_smtp(),registry=smtp.SendRegistry())
            if not state.get('loaded'):workspace.load()
            target={key:str(st.query_params.get('email_'+key,'')) for key in ('uid','uidvalidity','message_id')}
            if target['uid'] and state.get('target')!=target:
                state['target']=target;workspace.open_notification(target)
            event=get_component()(model=workspace.model(),key='fixture-email',default=None)
            if event and workspace.handle(event):rerun_email()

    if route=='email':
        email_shell_styles()
        with st.container(key='support-email-shell'):mailbox()
    else:
        st.title(names.get(route,'Dashboard'))
        st.caption('Fabricated OS shell using the production top bar, notification panel and badge renderer.')
    top_bar.render_navigation_complete(components,current_route=names.get(route,'Dashboard'))
