"""Offline four-card source UI; all external image reads are intercepted by the browser test."""
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
st.caption('Synthetic four-card source · no production data')
value = creative.normalize(inline(4))
value['creative_format']='DYNAMIC_CAROUSEL'
value['shared_primary_texts']=['Shared primary text one', 'Shared primary text two']
refresh=st.radio('Screen',['Meta Review','Creative Refresh'],horizontal=True)=='Creative Refresh'
images = {}
for card in value['cards']:
    image = Image.new('RGB', (300, 300), ['#222222','#344145','#433830','#373547'][card['position']-1])
    ImageDraw.Draw(image).text((90, 145), f"SOURCE CARD {card['position']}", fill='#d7b865')
    out = io.BytesIO()
    image.save(out, format='PNG')
    Path('.tmp-meta-carousel').mkdir(exist_ok=True)
    Path(f".tmp-meta-carousel/card{card['position']}.png").write_bytes(out.getvalue())
    card['image_sha256'] = f"fixture-{card['position']}"
    card['image_url'] = f"http://127.0.0.1:8532/full/{card['position']}.png"
    card['high_resolution_image_url'] = card['image_url']
    card['thumbnail_url'] = f"http://127.0.0.1:8532/thumb/{card['position']}.png"
    images[card['image_sha256']] = (out.getvalue(), 'image/png')
# Keep fixture lookup alive across real browser fragment-only arrow reruns.
store.load_media=lambda digest: images[digest]
if refresh:
    import meta_review_handoff as handoff
    st.session_state[handoff.ACTIVE]={**value,'carousel_cards':value['cards']}
    with patch.object(handoff,'hydrate'):
        handoff.render_source(st)
else:
    creative.render_cards(st, value)
    creative.render_shared_primary_text(st,value)
