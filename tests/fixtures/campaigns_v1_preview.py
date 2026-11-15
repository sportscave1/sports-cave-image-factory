"""LOCAL synthetic preview. Provider sends blocked, database is loopback fixture only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch,Mock
import uuid
import streamlit as st
from crm_campaign_page import campaign_workspace
from crm_campaign_store import CampaignStore
from crm_service import Actions
from crm_resend import Config
from crm_shopify import Shopify
from tests.crm_fixtures import ShopifyFixture
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_resend_marketing import ENV
from crm_page import render_page
from crm_navigation import SIDEBAR_ROUTES,LABELS

st.set_page_config(page_title='Sports Cave · Campaigns V1 fixture',layout='wide')
st.html('''<style>.stApp{background:#faf8f2;color:#171717} .stMainBlockContainer{padding-top:1.2rem;padding-bottom:1rem}
button[kind="primary"]{background:#d6a548;color:#171717;border:0}h3{font-size:1.3rem}div[data-testid="stVerticalBlock"]{gap:.65rem}</style>''')
st.sidebar.caption('LOCAL SYNTHETIC FIXTURE · no external I/O')
route=st.sidebar.radio('CRM & Marketing',SIDEBAR_ROUTES,format_func=lambda r:LABELS[r])
store=CampaignStore(connect)
wire=st.session_state.setdefault('fixture_shopify',ShopifyFixture())
original_test=CampaignStore.test_campaign
def synthetic_test(self,*args,**kwargs):
    session=Mock();session.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
    kwargs['session']=session
    with patch('crm_resend_marketing._audit',return_value=True):return original_test(self,*args,**kwargs)
with patch.dict('os.environ',ENV),patch('requests.sessions.Session.request',side_effect=AssertionError('Real HTTP forbidden')),patch.object(CampaignStore,'test_campaign',synthetic_test),patch('crm_service.audit'):
    render_page(route,ADMIN,shop=Shopify(wire),store=store,config=Config(ENV))
