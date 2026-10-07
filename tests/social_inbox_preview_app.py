"""Synthetic browser fixture: real rendering, no external calls or customer data."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import base64,io
from PIL import Image
from datetime import datetime,timezone,timedelta
import wall_preview_inbox as inbox
import wall_preview_analytics_ui as analytics
st.set_page_config(layout='wide')
user={'id':'fixture-admin','role':'admin','is_active':True}
image=io.BytesIO();Image.new('RGB',(640,480),'#c5b99e').save(image,'JPEG');blob=image.getvalue()
rows=[dict(id=str(i),product_title='Artwork '+str(i),product_handle='artwork-'+str(i),customer_email='collector@example.test',received_at=datetime(2026,10,6,tzinfo=timezone.utc)-timedelta(minutes=i),status='new',dropbox_path='/fixture/'+str(i),dropbox_file_id='id:'+str(i),marketing_permission=True,content_type='image/jpeg') for i in range(60)]
st.session_state.setdefault('fixture-deleted',[])
def page(**filters):
    start=int(filters['cursor'][1])+1 if filters.get('cursor') else 0
    result=[r for r in rows[start:] if r['id'] not in st.session_state['fixture-deleted']]
    if filters.get('customer_search'):result=[r for r in result if filters['customer_search'].lower() in r['product_title'].lower()]
    return result[:25]
page.clear=lambda:None
inbox._page=page
inbox._thumbnails=lambda assets:{i:'data:image/jpeg;base64,'+base64.b64encode(blob).decode() for i,_,_ in assets}
inbox._thumbnails.clear=lambda:None
inbox._image=lambda row:blob
inbox.wall_preview_store.get_preview=lambda pid,**kw: next((r for r in rows if r['id']==pid and pid not in st.session_state['fixture-deleted']),{})
inbox.wall_preview_store.delete_preview=lambda pid,**kw:st.session_state['fixture-deleted'].append(pid)
inbox.wall_preview_crm_store.timeline=lambda pid:[]
analytics.snapshot=lambda *a:dict(engagement=dict(cta_clicks=20,unique_clickers=14,opens=16,click_open_percent=80,avg_active_seconds=34.5,median_active_seconds=28,photo_ready=15,confirmed=12,placement_percent=75,atc=3,cart_percent=18.75),summary=dict(opens=16,sessions=5,photo_ready=15,confirmed=12,atc=3,purchased=1,atc_percent=18.75,purchase_percent=6.25,revenue=[]),funnel=[],products=[],insights=[])
analytics.snapshot.clear=lambda:None
inbox.render(user)
