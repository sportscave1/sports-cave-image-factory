"""Lightweight Creative Refresh reference actions; no Files/backend initialization."""
import base64
import json
from functools import lru_cache
from pathlib import Path

PRODUCT_IMAGES_FOLDER = '04_OUTPUT/product-images'


@lru_cache(maxsize=1)
def _source():
    return (Path(__file__).resolve().parent / 'components/ads_refresh_reference/index.html').read_text(encoding='utf-8')


def winning_image_copy_html(data, mime):
    if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
        raise ValueError('Unsupported reference image format.')
    # Transfer the archived bytes verbatim. Conversion, if required, is clipboard-only.
    payload = {'mime': mime, 'base64': base64.b64encode(data).decode('ascii')}
    return _source().replace('__WINNING_IMAGE__', json.dumps(payload))


def render_winning_image_copy(data, mime):
    import streamlit.components.v1 as components
    components.html(winning_image_copy_html(data, mime), height=100)


def render_product_image_link(st):
    from files_window_launcher import files_window_href
    st.link_button('Find product image', files_window_href(PRODUCT_IMAGES_FOLDER), icon=':material/folder_open:')
    st.caption('Opens Files → product-images')
