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


def winning_image_copy_html(data, mime, *, canonical=False):
    if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
        raise ValueError('Unsupported reference image format.')
    # Transfer the archived bytes verbatim. Conversion, if required, is clipboard-only.
    payload = {'mime': mime, 'base64': base64.b64encode(data).decode('ascii')}
    source = _source().replace('Copy winning image', 'Copy canonical product image') if canonical else _source()
    return source.replace('__WINNING_IMAGE__', json.dumps(payload))


def canonical_variant_image(product, expected_handle, *, variant_id='', frame_finish=''):
    """Exact product + variant media association; never first-product-image guessing."""
    if str(product.get('handle','')).casefold() != str(expected_handle).casefold():
        raise ValueError('Select the correct product: Shopify identity does not match the mapped edition.')
    variants = product.get('variants') or []
    if variant_id:
        candidates = [v for v in variants if str(v.get('id','')).split('/')[-1] == str(variant_id).split('/')[-1]]
    elif frame_finish:
        finish = str(frame_finish).casefold().removesuffix(' frame').strip()
        candidates = [v for v in variants if any('frame' in str(o.get('name','')).casefold() and str(o.get('value','')).casefold().removesuffix(' frame').strip()==finish for o in v.get('selected_options',[]))]
    else:
        raise ValueError('Select the matching source frame variant; it cannot be inferred from the product title.')
    urls = {m.get('url') for v in candidates for m in v.get('reference_images',[]) if m.get('url')}
    if product.get('reference_variants_incomplete') or not candidates or any(v.get('reference_images_incomplete') or not v.get('reference_images') for v in candidates) or len(urls)!=1:
        raise ValueError('Select the exact product variant: its approved canonical image is missing or ambiguous.')
    url=next(iter(urls))
    from urllib.parse import urlparse
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='cdn.shopify.com':
        raise ValueError('The canonical image must be an accessible approved Shopify CDN image.')
    return {'url':url,'variant_ids':[v['id'] for v in candidates], 'product_handle':expected_handle,
            'authority':'CANONICAL_PRODUCT','evidence':'Shopify variant-associated media'}


def load_canonical_bytes(url):
    from io import BytesIO
    from PIL import Image
    import requests
    from urllib.parse import urlparse
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='cdn.shopify.com':
        raise ValueError('Unsupported canonical image location.')
    import time
    deadline = time.monotonic() + 30
    with requests.get(url,stream=True,timeout=(5,15),allow_redirects=False) as response:
        if response.status_code!=200:raise ValueError('Canonical image is unavailable; select a verified product image.')
        data=bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data)>16*1024*1024 or time.monotonic()>deadline:raise ValueError('Canonical image exceeds the supported reference size.')
    image=Image.open(BytesIO(data));image.verify()
    return bytes(data),Image.MIME[image.format]


def render_canonical_reference(st, row, product_url):
    """Retrieve automatically; reuse the existing image clipboard for actual bytes."""
    from urllib.parse import parse_qs,urlparse
    from shopify_sync import fetch_product_by_shopify_id
    import streamlit.components.v1 as components
    source=st.session_state.get('meta-review-refresh-source') or {}
    st.session_state.pop('ads-refresh-canonical-reference',None)
    mapping=source.get('product_mapping') or {}
    pid=str(row.get('shopify_product_id') or row.get('product_id') or mapping.get('product_id') or '')
    handle=str(row.get('product_handle') or row.get('shopify_handle') or mapping.get('product_handle') or '')
    variant=str(parse_qs(urlparse(product_url).query).get('variant',[''])[0] or source.get('variant_id') or '')
    finish=str(source.get('frame_finish') or row.get('frame_finish') or '')
    if not pid or not handle:
        st.warning('Select the verified product for this winner to retrieve its canonical image.');return
    key=(pid,handle)
    cache=st.session_state.setdefault('ads-refresh-canonical-media',{})
    try:
        if cache.get('key')!=key:
            cache.clear();cache.update(key=key,product=fetch_product_by_shopify_id(pid,include_variant_media=True))
        product=cache['product']
        if not variant and not finish:
            variants={v['id']:v.get('title') or v['id'] for v in product.get('variants',[])}
            variant=st.selectbox('Match the winner’s product variant',list(variants),index=None,
                                 format_func=lambda v:variants[v],key='ads-refresh-canonical-variant::'+pid,
                                 placeholder='Select only when the source variant is not mapped')
            if not variant:return
        ref=canonical_variant_image(product,handle,variant_id=variant,frame_finish=finish)
        if cache.get('url')!=ref['url']:
            data,mime=load_canonical_bytes(ref['url']);cache.update(url=ref['url'],data=data,mime=mime)
        st.image(cache['data'],width=220,caption='CANONICAL_PRODUCT — exact mapped edition and selected variant')
        components.html(winning_image_copy_html(cache['data'],cache['mime'],canonical=True),height=100)
        st.caption('The actual image is ready to paste into the receiving conversation; no separate product upload or image search is needed.')
        st.session_state['ads-refresh-canonical-reference']={**ref,'product_id':pid,'image_sha256':__import__('hashlib').sha256(cache['data']).hexdigest()}
    except Exception as error:
        st.session_state.pop('ads-refresh-canonical-reference',None)
        st.warning(str(error) if isinstance(error,ValueError) else 'Canonical image retrieval is unavailable. Retry or select the exact product variant; no image has been guessed.')


def render_winning_image_copy(data, mime):
    import streamlit.components.v1 as components
    components.html(winning_image_copy_html(data, mime), height=100)


def render_product_image_link(st):
    from files_window_launcher import files_window_href
    st.link_button('Find product image', files_window_href(PRODUCT_IMAGES_FOLDER), icon=':material/folder_open:')
    st.caption('Opens Files → product-images')
