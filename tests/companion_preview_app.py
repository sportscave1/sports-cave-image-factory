"""Synthetic companion UI only. Never imports or starts the application server."""
from pathlib import Path
import sys, json, time
from threading import Lock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import os_accounts, upload_companion_page, morning_design_queue, product_upload_staff_queue
import design_publish_ad, ads_companion_quick_add, companion_display
st.set_page_config(layout='wide')
@st.cache_resource
def fixture():return {'fail':False,'calls':{},'lock':Lock(),'enabled':True}
state=fixture()
companion_display.CACHE.ttl=.4
companion_display.CACHE.retry=.5
os_accounts.can_access_page=lambda *args:True

def load(name, value):
    with state['lock']:
        state['calls'][name]=state['calls'].get(name,0)+1
        target=Path('output/companion-phases');target.mkdir(parents=True,exist_ok=True)
        (target/'fixture-reads.json').write_text(json.dumps(state['calls']))
    time.sleep(.15)
    if state['fail']:raise RuntimeError('Synthetic unavailable backend')
    return value

def control(enabled=None):
    if enabled is not None:state['enabled']=enabled
    return {'enabled':state['enabled']}
morning_design_queue.settings=control
product_upload_staff_queue.settings=control
morning_design_queue.list_jobs=lambda **kw:load('design',[dict(id='fixture',title='Fixture design',stage=2,label='Generating',updated_at='2026-11-18T00:00:00+00:00')])
product_upload_staff_queue.list_jobs=lambda **kw:load('upload',dict(online=True,jobs=[]))
product_upload_staff_queue.desktop_online=lambda:True
design_publish_ad.dashboard=lambda:load('ads',dict(online=True,enabled=True,jobs=[]))
ads_companion_quick_add.catalog=lambda:load('catalog',dict(products=[]))
if st.button('Simulate outage'):state['fail']=True
if st.button('Recover backend'):state['fail']=False
upload_companion_page.render_page({'id':'synthetic','role':'admin','is_active':True})
