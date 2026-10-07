"""Active campaign dialog fixture. No external Graph or persistence access."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
import ads_meta_review_page as page
import meta_review_creative as creative
from tests.test_meta_review import history
from tests.test_meta_review_creative import inline
from tests.test_meta_review_live import CONFIG
st.set_page_config(layout='wide')
raw=inline(4);raw['asset_feed_spec']={'bodies':[{'text':'Collector story. Handcrafted for your cave.'}]}
for i,c in enumerate(raw['object_story_spec']['link_data']['child_attachments'],1):
    c['picture']=f'https://fixture.fbcdn.net/thumb/{i}.png'
value={**creative.normalize(raw),'raw':raw}
h=history();h['ads']=h['ads'][:1];h['ads'][0].update(creative_id='1234',ad_name='FOUR CARD MOCKUPS',raw={'creative':raw})
h['creatives']=[{'creative_id':'1234','raw':raw}]
campaign={'campaign_id':'cam','campaign_name':'Carousel operations preview','status':'ACTIVE',
          'metrics':{'spend':120,'purchases':6,'roas':5,'cpa':20,'cost_per_link_click':4},'benchmark':{'currency':'AUD'}}
page.meta.get_meta_config=lambda:CONFIG
page.live.load_overview=lambda *a:{'account':{'currency':'AUD'},'campaigns':[campaign]}
page.live.load_campaign=lambda *a:h
page.recency.load=lambda *a:{'available':False}
page._load_preferences=lambda *a:{'selections':[],'mapping':[]}
def resolve(*a):
    st.session_state['fixture-detail-reads']=st.session_state.get('fixture-detail-reads',0)+1
    return value
creative.resolve=resolve
def queue(package,*a):
    st.session_state['fixture-handoff-count']=len(package['carousel_cards'])
    return '?fixture=refresh'
page.handoff.queue_link=queue
st.session_state['sports_cave_current_user']={'role':'worker','is_active':True}
page.render_page()
if st.button('Open campaign fixture'):
    st.session_state['meta-review-creative-table-cam']={'selection':{'rows':[0],'columns':[]}}
    page.campaign_popup(CONFIG,campaign,'2026-09-01','2026-10-07')
