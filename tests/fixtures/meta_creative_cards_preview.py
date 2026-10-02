"""Offline source viewer: generated colour tiles, no Meta/Shopify/database calls."""
import io
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
from PIL import Image, ImageDraw
import meta_review_creative as creative
import meta_review_store as store
from tests.test_meta_review_creative import inline

st.set_page_config(page_title='Offline Meta creative fixture', layout='wide')
st.title('Winner from Meta Review')
st.caption('Synthetic six-card source · no production data')
value = creative.normalize(inline(6))
images = {}
for card in value['cards']:
    image = Image.new('RGB', (300, 300), '#222222')
    ImageDraw.Draw(image).text((90, 145), f"SOURCE CARD {card['position']}", fill='#d7b865')
    out = io.BytesIO()
    image.save(out, format='PNG')
    card['image_sha256'] = f"fixture-{card['position']}"
    card['image_url'] = ''  # No external URL requests in this browser fixture.
    images[card['image_sha256']] = (out.getvalue(), 'image/png')
# Keep fixture lookup alive across real browser fragment-only arrow reruns.
store.load_media=lambda digest: images[digest]
creative.render_cards(st, value, archived=True)
