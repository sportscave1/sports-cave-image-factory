"""Synthetic browser fixture: real rendering, no external calls or customer data."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import base64,io,uuid
from PIL import Image
from datetime import datetime,timezone,timedelta
import wall_preview_notifications
wall_preview_notifications.mark_seen=lambda pid,user: st.session_state.setdefault("fixture-seen",[]).append(pid)
import wall_preview_inbox as inbox
import wall_preview_analytics_ui as analytics
st.set_page_config(layout='wide')
user={'id':'fixture-admin','role':'admin','is_active':True}
image=io.BytesIO();Image.new('RGB',(640,480),'#c5b99e').save(image,'JPEG');blob=image.getvalue()
rows=[dict(id=str(uuid.UUID(int=i+1)),product_title='Artwork '+str(i),product_handle='artwork-'+str(i),customer_email='collector@example.test',received_at=datetime(2026,10,6,tzinfo=timezone.utc)-timedelta(minutes=i),status='new',dropbox_path='/fixture/'+str(i),dropbox_file_id='id:'+str(i),marketing_permission=True,content_type='image/jpeg') for i in range(60)]
st.session_state.setdefault('fixture-deleted',[])
def page(**filters):
    start=uuid.UUID(filters['cursor'][1]).int if filters.get('cursor') else 0
    result=[r for r in rows[start:] if r['id'] not in st.session_state['fixture-deleted']]
    if filters.get('customer_search'):result=[r for r in result if filters['customer_search'].lower() in r['product_title'].lower()]
    return result[:25]
page.clear=lambda:None
inbox._page=page
inbox._thumbnails=lambda assets:{i:'data:image/jpeg;base64,'+base64.b64encode(blob).decode() for i,_,_ in assets}
inbox._thumbnails.clear=lambda:None
inbox._image=lambda row:blob
inbox.wall_preview_store.get_preview=lambda pid,**kw: next((r for r in rows if r['id']==pid and pid not in st.session_state['fixture-deleted']),{})
def bulk_delete(ids, *, user, progress=None):
    if len(ids)>1 and not st.session_state.get('fixture-busy-tested'):
        st.session_state['fixture-busy-tested']=True
        raise inbox.wall_preview_store.WallPreviewStoreError('Another deletion is running. Please retry shortly.')
    result=[]
    for index,pid in enumerate(ids):
        st.session_state['fixture-deleted'].append(pid)
        result.append({'id':pid,'status':'deleted'})
        if progress:progress(index+1,len(ids))
    return result
inbox.wall_preview_deletion.bulk_delete=bulk_delete
inbox.wall_preview_crm_store.timeline=lambda pid:[]
analytics.snapshot=lambda *a:dict(engagement=dict(cta_clicks=20,unique_clickers=14,opens=16,click_open_percent=80,avg_active_seconds=34.5,median_active_seconds=28,photo_ready=15,confirmed=12,placement_percent=75,atc=3,cart_percent=18.75),summary=dict(opens=16,sessions=5,photo_ready=15,confirmed=12,atc=3,purchased=1,atc_percent=18.75,purchase_percent=6.25,revenue=[]),funnel=[],products=[],insights=[])
analytics.snapshot.clear=lambda:None
if st.query_params.get('notifications_fixture'):
    import top_bar
    import streamlit.components.v1 as components
    with st.sidebar:
        for key,label in [('orders','Orders'),('email','Email')]:
            with st.container(key='sidebar-row-'+key):st.button(label,key='fixture-nav-'+key)
        expanded=st.session_state.get('fixture-social-expanded',False)
        with st.container(key='sidebar-disclosure-social-'+('open' if expanded else 'closed')):
            if st.button('Social Media',key='fixture-social-toggle'):
                st.session_state['fixture-social-expanded']=not expanded
                st.rerun()
        if expanded:
            with st.container(key='sidebar-row-social_media_wall_previews'):
                st.button('Wall Preview Inbox',key='fixture-nav-social_media_wall_previews')
    config=top_bar.top_bar_config(user,logo_src='',current_route='Wall Preview Inbox')
    config.update(dailyPlannerEnabled=False,ordersEnabled=True,emailEnabled=False,wallInboxEnabled=True)
    components.html(top_bar.component_html(config),height=0,width=0)
inbox.render(user)
