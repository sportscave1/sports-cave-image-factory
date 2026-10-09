"""Lightweight Creative Refresh reference actions; no Files/backend initialization."""
import base64
import json
from functools import lru_cache
from pathlib import Path

PRODUCT_IMAGES_FOLDER = '04_OUTPUT/product-images'


def load_winner_media(state, source, loader):
    """One immutable archived winner per authenticated session; never cache failures."""
    digest = source.get('image_sha256')
    user = state.get('sports_cave_current_user') or {}
    scope = (str(user.get('id') or ''), str(source.get('ad_account_id') or ''), digest)
    cached = state.get('ads-refresh-winner-media') or {}
    if cached.get('scope') == scope:
        return cached['data'], cached['mime']
    state.pop('ads-refresh-winner-media', None)
    data, mime = loader(digest)
    if data and len(data) <= 8 * 1024 * 1024:
        state['ads-refresh-winner-media'] = {'scope': scope, 'data': data, 'mime': mime}
    return data, mime


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
