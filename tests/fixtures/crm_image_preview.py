"""Offline real middle editor and shared renderer; no transport or external reads."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock,patch
import streamlit as st
import streamlit.components.v1 as components
from crm_section_ui import middle_editor
from crm_campaign_content import render_campaign
from tests.test_crm_image_sections import image_doc
from tests.test_crm_resend_marketing import ENV
from crm_campaign_content import settings

st.set_page_config(layout='wide')
st.title('Campaign Image — offline fixture')
doc=st.session_state.setdefault('doc',image_doc())
with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
    left,right=st.columns(2)
    with left:middle_editor(doc,'image_fixture_',Mock(),None)
    with right:
        width=st.selectbox('Preview width',[600,430,390,375,320])
        # Substitute only this fabricated fixture URL AFTER the real sanitizer/renderer.
        # This lets browser tests load local pixels without Shopify or a fake live upload.
        preview=render_campaign(doc,settings(ENV))['html'].replace('https://cdn.shopify.com/s/files/1/artwork.jpg','http://localhost:8518/app/static/crm-image-fixture.jpg')
        components.html(preview,width=width,height=600,scrolling=True)
