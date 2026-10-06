"""Fabricated Social Media analytics. Blocks external HTTP; no database connections."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock
import streamlit as st
import requests
import wall_preview_analytics_ui as analytics
import wall_preview_inbox as inbox
import social_media_page as page
st.set_page_config(layout='wide')
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
DATA={'summary':dict(opens=100,sessions=90,photo_ready=80,confirmed=60,atc=20,purchased=8,atc_percent=20.,purchase_percent=8.,revenue=[{'currency':'AUD','revenue':1200}]),
'funnel':[dict(stage=s,events=n,journeys=n,next_stage_percent=75.,drop_off_percent=25.) for s,n in [('Opened',100),('Photo Ready',80),('Interacted / Dragged',70),('Confirmed',60),('Added to Cart',20),('Checkout',12),('Purchased',8)]],
'products':[dict(product='Collector artwork',product_id='123',opens=100,photo_ready=80,confirmed=60,atc=20,purchased=8,revenue=[{'currency':'AUD','revenue':1200}],purchase_percent=8.)],
'insights':[dict(insight='Camera vs Upload',value='camera',journeys=60)]}
analytics.snapshot=lambda *a,**k:DATA
analytics.snapshot.clear=lambda:None
inbox.wall_preview_store.summary=lambda **kwargs:{'total':1,'confirmed':1}
inbox.wall_preview_store.list_previews=lambda **kwargs:[dict(id='00000000-0000-4000-8000-000000000001',client_preview_id='00000000-0000-4000-8000-000000000002',product_title='Collector artwork',dropbox_path='/fixture',status='new',marketing_permission=False)]
inbox._temporary_link=lambda *a:''
inbox.wall_preview_crm_store.timeline=lambda *a:[{'event_name':'WallPreviewStarted','occurred_at':'2026-10-06T01:00:00Z'},{'event_name':'WallPreviewSizeChanged','size':'XL','occurred_at':'2026-10-06T01:02:00Z'}]
page._admin_staff_selector=lambda user,*a:user
page._render_today=lambda *a:st.caption('Existing overview content')
store=Mock();store.schema_status.return_value={'ready':True};store.authorised_social_staff.return_value=[]
page.render_page({'id':'admin','role':'admin','is_active':True},store=store)
