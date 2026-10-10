"""Real Campaigns editor and shared app CSS; synthetic Shopify and loopback SQL only."""
import sys, ast, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('CRM_FIXTURE_SQL_PORT','8897')
from unittest.mock import Mock, patch
from copy import deepcopy
import streamlit as st
from crm_campaign_store import CampaignStore
from crm_campaign_page import campaign_workspace
from crm_campaign_content import settings
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_modular_catalogue import catalogue_doc, service
from crm_middle_sections import commit_middle, middle_sections
st.set_page_config(layout='wide')
fn=next(n for n in ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name=='inject_styles')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'app-styles','exec'))
inject_styles()
@st.cache_resource
def setup():
    guards=[patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')),patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden')),patch('crm_service.audit')]
    for g in guards:g.start()
    cat=service()
    cat.collections=lambda:{'rows':[{'id':'gid://shopify/Collection/1','title':'Motorsport'},{'id':'gid://shopify/Collection/2','title':'Tennis'}, {'id':'gid://shopify/Collection/3','title':'Empty'}, {'id':'gid://shopify/Collection/4','title':'Unavailable'}, {'id':'gid://shopify/Collection/5','title':'Gift edit'}, {'id':'gid://shopify/Collection/6','title':'Gift edit'}]}
    allfacts=cat.resolve(['gid://shopify/Product/'+str(i) for i in range(1,17)])
    allfacts[-1]['status']='DRAFT'
    def search(q='',offset=0,active=True,collection=''):
        if collection.endswith('/4'):raise ValueError('Fixture collection unavailable')
        rows=[] if collection.endswith('/3') else allfacts[:2] if collection.endswith(('/1','/5')) else allfacts[2:] if collection else allfacts
        rows=[p for p in rows if q.lower() in p['title'].lower() and (not active or p['status']=='ACTIVE')]
        return {'rows':rows[offset:offset+12], 'more':len(rows)>offset+12}
    cat.search=search
    import crm_section_ui
    crm_section_ui.Catalogue=lambda shop:cat
    store=CampaignStore(connect);store.seed()
    doc=catalogue_doc()
    sections=middle_sections(doc);sections[-1]['products']=[];commit_middle(doc,sections)
    row=store.save(ADMIN,'Collection picker fixture',doc)
    return guards,row
guards,row=setup()
shop=Mock(namespace='offline-collection-picker')
shop.campaign_segment_counts.return_value={'AU':0,'Global':0}
shop.campaign_members.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
shop.segment_members.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
campaign_workspace(shop,CampaignStore(connect),Mock(user=ADMIN))
