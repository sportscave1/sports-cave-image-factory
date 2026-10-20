"""Offline UI fixture. Synthetic data only; never a live connection."""
from pathlib import Path
import sys
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
import seo_phase1_ui as ui
import seo_phase1 as model
import seo_navigation as nav
import seo_workspace
from google_direct_reporting import MemoryReports

class FixtureReports:
    cache=MemoryReports()
    def connection(self):
        return {'gsc_site_url':'sc-domain:fixture.invalid','ga4_property_id':'fixture','ga4_property_currency':'AUD'}
    def gsc(self,start,end,dimensions,filters):
        if st.session_state.get('fixture-fail-gsc'):raise RuntimeError('synthetic unavailable')
        row={'clicks':4,'impressions':1000,'ctr':.004,'average_position':12}
        if 'date' in dimensions:row['date']=str(end)
        if 'query' in dimensions:row['query']='sports wall art'
        if 'page' in dimensions:row['page']='https://fixture.invalid/products/art?variant=1'
        return [row]
    def ga4(self,property_id,contract,start,end,filters=()):
        if st.session_state.get('fixture-fail-ga4'):raise RuntimeError('synthetic unavailable')
        dims={d: ('20261017' if d=='date' else '/products/art?variant=1' if d=='landingPagePlusQueryString' else 'fixture') for d in contract.dimensions}
        return {'rows':[{'dimensions':dims,'metrics':{metric:12 for metric in contract.metrics}}], 'metadata':{'timezone':'Australia/Sydney','currency':'AUD','fixture':True}}

st.set_page_config(layout='wide')
st.caption('OFFLINE TEST FIXTURE — synthetic reports; no production connections')
route=st.selectbox('Workspace',nav.SEO_MENU_ROUTES,format_func=lambda r:nav.SEO_NAV_LABELS[r],key='fixture-route')
user={'id':'fixture','role':'admin','display_name':'Offline test'}
root=Path(os.environ.get('SEO_PHASE1_FIXTURE_DIR',str(Path(__file__).resolve().parents[2]/'.local'/'fixture')))
store=seo_workspace.LocalSEOStore(root/'workspace.json')
ui.render(user,route,store=store,reports=FixtureReports())
