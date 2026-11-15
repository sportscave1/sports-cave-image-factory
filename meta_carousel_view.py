"""Presentation only: consume resolved cards without Meta reads or card mutation."""
from functools import lru_cache
from html import escape
import json
import time
from pathlib import Path
from urllib.parse import urlparse


def image_url(value):
    value = str(value or '')
    return value if urlparse(value).scheme in ('https', 'http') or value.startswith('/media/') else ''


def card_views(value):
    return [{'number': i, 'preview': image_url(c.get('preview_image_url') or c.get('thumbnail_url') or c.get('image_url')),
             'full': image_url(c.get('high_resolution_image_url') or c.get('image_url') or c.get('thumbnail_url'))}
            for i, c in enumerate(value.get('cards') or value.get('carousel_cards') or [], 1)]


@lru_cache(maxsize=1)
def template():
    return (Path(__file__).parent / 'components/meta_carousel_strip/index.html').read_text(encoding='utf-8')


def strip_html(cards, *, refresh=False):
    payload = json.dumps({'cards': cards, 'refresh': refresh}).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return template().replace('__CAROUSEL_DATA__', payload)


def render_copy(st, value):
    cards = value.get('cards') or value.get('carousel_cards') or []
    items = ''.join('<li><strong>'+escape(str(c.get('headline') or 'Untitled'))+'</strong>'
                    + ('<p>'+escape(str(c['description']))+'</p>' if c.get('description') else '')+'</li>' for c in cards)
    details = ''.join('<li>'+escape(str(c.get('destination_url') or c.get('link') or ''))+' · '
                      +escape(str(c.get('cta') or ''))+'</li>' for c in cards)
    note = '<p>Meta may optimize carousel delivery order; the authored source order is shown here.</p>' if value.get('multi_share_optimized') else ''
    st.html('<style>.sc-source-copy{font:13px system-ui,sans-serif;color:#292929}.sc-source-copy h4{font-size:.75rem;letter-spacing:.08em;margin:8px 0}'
            '.sc-source-copy ol{padding-left:22px;margin:4px 0;columns:2;column-gap:28px}.sc-source-copy li{break-inside:avoid;margin:0 0 8px;padding-left:3px}'
            '.sc-source-copy p{font-size:inherit;white-space:pre-wrap;margin:2px 0;color:var(--text-color,#555)}'
            '.sc-source-copy details{font-size:.75rem;overflow-wrap:anywhere}.sc-source-copy summary{cursor:pointer}'
            '@media(max-width:600px){.sc-source-copy ol{columns:1}}</style>'
            '<section class="sc-source-copy" aria-label="Card copy"><h4>CARD COPY</h4><ol>'+items+'</ol>'
            '<details><summary>Details</summary>'+note+'<ol>'+details+'</ol></details></section>')


def render_primary(st, value):
    texts = value.get('shared_primary_texts') or ([value['shared_primary_text']] if value.get('shared_primary_text') else [])
    if texts:
        st.html('<section class="sc-source-copy" aria-label="Primary text" style="font:13px system-ui,sans-serif;color:#292929"><h4 style="font-size:12px;letter-spacing:.08em;margin:8px 0">PRIMARY TEXT</h4><div style="max-height:220px;overflow:auto">'
                + ''.join('<p style="white-space:pre-wrap;margin:4px 0 10px"><strong>Variation '+str(i)+'</strong><br>'+escape(str(t))+'</p>' for i,t in enumerate(texts,1))+'</div></section>')


def render(st, value, *, archived=False, key_prefix='source'):
    from meta_review_creative import label
    cards = value.get('cards') or value.get('carousel_cards') or []
    st.caption(label({**value, 'cards': cards}))
    if not cards:
        st.warning('Source cards were not retained in this legacy handoff. Reload the winner from Meta Review.')
        return
    views = card_views(value)
    missing = sum(not (v['preview'] or (archived and c.get('image_sha256'))) for v,c in zip(views,cards))
    if missing:
        st.warning(f'{missing} of {len(cards)} source cards could not be retrieved.')
    # Durable Refresh archives must keep working after Meta URLs expire. Cache
    # within this authenticated session; serve small previews, never base64 HTML.
    failures=st.session_state.setdefault('meta-carousel-preview-failures',{}) if archived else {}
    failed_positions=[]
    for view, card in zip(views, cards):
        if archived and card.get('image_sha256'):
            digest=card['image_sha256']
            if failures.get(digest,0)>time.monotonic():
                failed_positions.append(view['number'])
                continue
            try:
                import io
                import meta_review_store
                from PIL import Image, ImageOps
                from streamlit.runtime import get_instance
                cache = st.session_state.setdefault('meta-carousel-preview-media', {})
                digest = card['image_sha256']
                if digest not in cache:
                    data, mime = meta_review_store.load_media(digest)
                    if data:
                        with Image.open(io.BytesIO(data)) as source:
                            small = ImageOps.exif_transpose(source).convert('RGB')
                            small.thumbnail((440, 440))
                            out = io.BytesIO(); small.save(out, format='JPEG', quality=85)
                        if len(cache) >= 20:
                            cache.pop(next(iter(cache)))
                        cache[digest] = (data, mime, out.getvalue())
                data, mime, preview = cache.get(digest, (None, None, None))
                if data:
                    manager = get_instance().media_file_mgr
                    url = manager.add(data, mime, 'carousel-full-'+digest)
                    thumbnail = manager.add(preview, 'image/jpeg', 'carousel-preview-'+digest)
                    view.update(preview=thumbnail, full=url)
                    failures.pop(digest,None)
                else:
                    raise ValueError('Archived source image unavailable')
            except Exception as error:
                import logging
                logging.getLogger(__name__).warning('creative_refresh_archive_unavailable card=%s exception=%s',view['number'],type(error).__name__)
                if len(failures)>=20:failures.pop(next(iter(failures)))
                failures[digest]=time.monotonic()+30
                failed_positions.append(view['number'])
    if failed_positions:
        st.caption('Archived source images unavailable for cards '+', '.join(map(str,failed_positions))+'. Your edits are retained; original source URLs are shown where available.')
        st.button('Retry source images',key='carousel-media-retry-'+key_prefix,on_click=failures.clear)
    html = strip_html(views, refresh=archived)
    if hasattr(st, 'iframe'):
        st.iframe(html, height='content')
    else:
        import streamlit.components.v1 as components
        components.html(html, height=278 if archived else 248, scrolling=False)
    render_copy(st, value)
