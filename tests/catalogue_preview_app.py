"""Isolated browser harness: actual OS/Campaign UI, fake catalogue, disposable SQL.

Run the existing crm_postgres_server.mjs first, then this file with --serve.
No production database, mail or Shopify I/O is permitted.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if '--serve' in sys.argv:
    sys.argv.remove('--serve')
    import os
    if '--polish' in sys.argv:
        sys.argv.remove('--polish')
        os.environ['CRM_CATALOGUE_POLISH_FIXTURE']='1'
    os.environ['CRM_MARKETING_ENABLED']='false'
    import uvicorn
    from streamlit.web.server.starlette import App
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    import top_bar_api
    async def empty(request):return JSONResponse({'ok':True,'notifications':[],'items':[],'results':[],'timer':{},'action_required_count':0,'unread_count':0})
    routes=[Route(p,empty) for p in (top_bar_api.EMAIL_STATUS_PATH,top_bar_api.ORDER_STATUS_PATH,top_bar_api.NOTIFICATIONS_PATH,top_bar_api.DAILY_PLANNER_STATUS_PATH,top_bar_api.REPAIR_REQUESTS_PATH)]
    uvicorn.run(App(str(Path(__file__).resolve()),routes=routes),host='127.0.0.1',port=8514)
else:
    import runpy,time,os
    from unittest.mock import Mock
    import streamlit as st
    import requests,supabase_backend,crm_page,crm_service,crm_catalogue,smtplib,imaplib
    from crm_navigation import PAGES
    from crm_store import Store
    from crm_shopify import Shopify
    from tests.crm_db_fixture import connect
    from tests.crm_fixtures import ShopifyFixture
    from tests.test_crm_modular_catalogue import service
    def forbidden(*a,**kw):raise AssertionError('Production I/O forbidden in local verification')
    requests.sessions.Session.request=forbidden
    supabase_backend.connect=forbidden
    smtplib.SMTP=smtplib.SMTP_SSL=imaplib.IMAP4_SSL=forbidden
    crm_service.audit=Mock()
    user={'id':'fixture-crm-user','username':'fixture','display_name':'Nathan · local fixture','role':'admin','is_active':True,
          'page_permissions':['email',*[p[0] for p in PAGES]],'timezone':'Australia/Sydney'}
    st.session_state.update(sports_cave_authenticated=True,sports_cave_current_user=user,sports_cave_auth_checked_at=time.monotonic())
    st.session_state.setdefault('current_page','CRM Campaigns');st.session_state.setdefault('selected_page','CRM Campaigns')
    fixture=st.session_state.setdefault('crm_fixture_authority',ShopifyFixture())
    crm_page.Store=lambda:Store(connect)
    crm_page.Shopify=lambda:Shopify(fixture)
    if not st.session_state.get('seeded'):Store(connect).seed();st.session_state['seeded']=True
    catalogue=service()
    facts=catalogue.resolve(['gid://shopify/Product/'+str(i) for i in range(1,5)])
    names=['Peter Brock Tribute','Shane Warne Tribute','Federer vs Nadal','Motorsport Legends']
    for p,name in zip(facts,names):
        p['title']=name
        p['image']='https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-logo-landscape-gold-transparent-optimised_1.webp?v=1779715351'
    if os.getenv('CRM_CATALOGUE_POLISH_FIXTURE')=='1':
        from tests.catalogue_polish_fixture import products,document
        from crm_campaign_page import open_editor
        facts=products()
        if not st.session_state.get('polish_fixture_loaded'):
            open_editor({'id':None,'name':'Collector catalogue · local fixture','document':document(),
                         'version':0,'status':'DRAFT','archived_at':None})
            st.session_state['polish_fixture_loaded']=True
    catalogue.resolve=lambda ids,*a,**kw:[p.copy() for identity in ids for p in facts if p['id']==identity]
    catalogue.search=lambda query='',offset=0,active=True:{'rows':[p for p in facts if query.lower() in p['title'].lower()][offset:offset+12],'more':False}
    crm_catalogue.Catalogue=lambda *a,**kw:catalogue
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'),run_name='__main__')
