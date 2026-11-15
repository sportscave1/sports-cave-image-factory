"""Offline Post Ad fixture; refuses all network traffic and persistent writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
import streamlit as st
import ads_posting_page as page
from tests.test_meta_posting import FakePostingClient
from meta_posting_service import load_posting_reference_snapshot

st.set_page_config(layout='wide')
rows = ({'shopify_product_id': '42', 'product_title': 'Motorsport Legends',
         'product_handle': 'motorsport-legends'},)
references = load_posting_reference_snapshot(FakePostingClient())
with patch('requests.sessions.Session.request', side_effect=AssertionError('Offline fixture')), \
     patch.object(page, '_meta_state', return_value=({'posting_ready': True}, references, '', '')), \
     patch.object(page, 'load_live_edition_product_rows', return_value=rows), \
     patch.object(page, '_existing_targets_state', return_value=({'campaigns': (), 'adsets': ()}, '')), \
     patch.object(page, '_load_recent_posts', return_value=()), \
     patch.object(page.MetaPostingService, 'create_paused_campaign', side_effect=AssertionError('No writes')):
    page.render_page()
