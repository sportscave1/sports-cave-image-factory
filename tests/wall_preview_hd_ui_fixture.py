"""Local fabricated Inbox only. No Shopify, Dropbox, SQL or email transport calls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import wall_preview_inbox as inbox

st.set_page_config(layout='wide')
rows=[{'id':str(i),'marketing_permission':i==0,'customer_name':'Nathan Baker',
       'customer_email':'collector@example.com','product_title':'Sports Cave collector edition on a real customer wall',
       'frame_label':'Premium Black Frame','size_label':'Large','dropbox_path':'/fixture.jpg',
       'market_country_code':'AU','market_country_name':'Australia',
       'email_marketing_state':'SUBSCRIBED' if i==1 else 'UNKNOWN',
       'email_requested_at':'2026-10-05T00:00:00Z','email_job_state':'queued'} for i in range(3)]
inbox.wall_preview_store.summary=lambda **kwargs:{'total':3,'confirmed':3,'email_captured':3}
inbox.wall_preview_store.list_previews=lambda **kwargs:rows
inbox._temporary_link=lambda *args:''
inbox.render({'id':'admin','role':'admin','is_active':True,'page_permissions':[]})
