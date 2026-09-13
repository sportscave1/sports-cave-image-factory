"""Persistent, certificate-independent creative reference handoff; no Meta mutations."""
from copy import deepcopy
from io import BytesIO
import time
import uuid
from urllib.parse import urlparse
import requests
from PIL import Image
import meta_review_store as store
import meta_review_products as products

PENDING = 'meta-review-refresh-pending'
ACTIVE = 'meta-review-refresh-source'


def archive_image(url):
    parsed = urlparse(str(url))
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or not any(host.endswith('.'+domain) for domain in ('fbcdn.net','fbsbx.com')):
        raise ValueError('Select a readable Meta CDN image. Sync again to renew the reference.')
    deadline = time.monotonic()+25
    try:
        with requests.get(url,stream=True,timeout=(5,10),allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError('Meta image unavailable or expired. Sync again before handing it off.')
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>8*1024*1024 or time.monotonic()>deadline:
                    raise ValueError('Winner image exceeds the download size/time limit.')
        image=Image.open(BytesIO(data))
        image.verify()
        mime=Image.MIME.get(image.format,'image/jpeg')
    except (requests.RequestException,OSError):
        raise ValueError('Winner image could not be verified. Sync again or select another real image.') from None
    return store.save_media(bytes(data),mime)


def build_package(ad,selections,context,mode):
    if mode not in ('complete_ad','best_components'):
        raise ValueError('Unknown refresh mode.')
    for kind in ('image','primary_text','headline'):
        item=selections.get(kind)
        if not item or not item.get('value'):
            raise ValueError('Select original image, primary text and headline before refreshing.')
        if mode=='complete_ad' and str(item['ad_id'])!=str(ad['ad_id']):
            raise ValueError('Complete-ad mode must use assets from the same ad.')
    return {**deepcopy(context),'mode':mode,'ad_id':ad['ad_id'],'ad_name':ad.get('ad_name'),
            'adset_id':ad.get('adset_id'),'creative_name':ad.get('creative_name') or ((ad.get('raw') or {}).get('creative') or {}).get('name'),
            'product_destination_urls':[item['value'] for item in ad['assets']['url']],
            'creative_id':ad['assets']['creative_id'],'components':deepcopy(selections),
            'metrics':deepcopy(ad['metrics']),'decision':deepcopy(ad['decision']),
            'dynamic':ad['assets']['dynamic'],'carousel':ad['assets']['carousel'],
            'description':next(iter(ad['assets']['description']),{}).get('value',''),
            'cta':next(iter(ad['assets']['cta']),{}).get('value',''),
            'destination_url':next(iter(ad['assets']['url']),{}).get('value','')}


def queue(package,state,actor='sports_cave_os'):
    package=products.enrich(package)
    package['image_sha256']=archive_image(package['components']['image']['value'])
    package['decision_id']=store.save_selection(package,actor,'meta_review_handoff')
    state[PENDING]=package


def queue_link(package, actor='sports_cave_os'):
    """Existing image archive/action-log path; no browser-session dependency."""
    from ads_navigation import CREATIVE_REFRESH_PAGE_KEY
    from urllib.parse import urlencode
    package=deepcopy(package)
    package['handoff_token']=uuid.uuid4().hex
    state={}
    queue(package,state,actor)
    return '?'+urlencode({'page':CREATIVE_REFRESH_PAGE_KEY,'handoff_id':package['handoff_token']})


def load_link(state, params, config):
    token=params.get('handoff_id')
    if not token or state.get('meta-review-loaded-handoff')==token: return False
    package=store.load_handoff(token,config.get('ad_account_id',''))
    if not package.get('image_sha256'):
        raise ValueError('Saved winner has no archived image.')
    state[PENDING]=products.enrich(package)
    hydrate(state)
    state['meta-review-loaded-handoff']=token
    return True


def hydrate(state):
    package=state.get(PENDING)
    if not package:
        return False
    import ads_page
    state[ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY]=package['components']['primary_text']['value']
    state[ads_page.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY]=package['components']['headline']['value']
    mapping=package.get('product_mapping') or {}
    hydrate_product(state,mapping)
    # Unmapped references must not inherit an unrelated previous product/market.
    state['ads_category']=mapping.get('sport') if mapping.get('sport') in ads_page.CATEGORY_OPTIONS else 'Select category' if 'Select category' in ads_page.CATEGORY_OPTIONS else ads_page.CATEGORY_OPTIONS[0]
    state['ads_country']='Select country'
    if mapping.get('sport') in ads_page.CATEGORY_OPTIONS:
        state['ads_category']=mapping['sport']
    market={'AU':'Australia','US':'USA','GB':'UK','CA':'Canada','NZ':'New Zealand'}.get(package.get('market'),package.get('market'))
    if market in ads_page.COUNTRY_OPTIONS:
        state['ads_country']=market
    url=package.get('destination_url','')
    state['ads_campaign_type']='Instant Experience' if package.get('format')=='INSTANT EXPERIENCE' else 'Carousel' if package.get('format')=='CAROUSEL' or package.get('carousel') else 'Instant Experience' if '/canvas/' in url or 'canvas_id=' in url else 'Single Image / Video'
    state[ACTIVE]=deepcopy(package)
    state.pop(PENDING,None)
    for key in ('ads-refresh-previous-campaign','ads-refresh-winning-candidate','ads-refresh-applied-winner'):
        state.pop(key,None)
    return True


def hydrate_product(state,mapping):
    import ads_page
    row=mapping.get('canonical_row') or {}
    identity=ads_page._edition_ops_product_selector_identity(row) if row else mapping.get('product_title','')
    title=mapping.get('product_title') or ''
    url=mapping.get('product_url') or ''
    state[ads_page.ADS_PRODUCT_NAME_KEY]=title
    state[ads_page.ADS_PRODUCT_SELECTOR_KEY]=identity or None
    state[ads_page.ADS_PRODUCT_URL_KEY]=url
    state[ads_page.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY]=identity
    state[ads_page.ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY]=title
    state[ads_page.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY]=url
    state[ads_page.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY]=False
    state[ads_page.ADS_PRODUCT_URL_INITIALIZED_KEY]=bool(title)
    state['ads_category']=mapping.get('category') or mapping.get('sport') or 'Select category'


def product_selector_rows(rows,state):
    source=state.get(ACTIVE) or {}
    mapping=source.get('product_mapping') or {}
    canonical=mapping.get('canonical_row')
    if not canonical: return rows
    return [canonical if str(r.get('product_handle') or r.get('shopify_handle') or '')==mapping.get('product_handle') else r for r in rows]


def rank_product_options(options,records,state):
    source=state.get(ACTIVE) or {}
    ranked=[p['product_handle'] for p in (source.get('product_resolution') or {}).get('candidates',[])]
    def key(identity):
        row=records[identity]['row']
        handle=row.get('product_handle') or row.get('shopify_handle')
        return ranked.index(handle) if handle in ranked else len(ranked)
    return sorted(options,key=key) if ranked else options


def confirm_selected_product(state,row):
    source=state.get(ACTIVE)
    if not source or not row: return
    product=products.canonical(row)
    if not product: return
    if product['product_handle']==(source.get('product_mapping') or {}).get('product_handle'):
        hydrate_product(state,product)
        return
    try:
        actor=str((state.get('sports_cave_current_user') or {}).get('id') or 'sports_cave_os')
        enriched=store.confirm_product_mapping(source,product,actor)
        state[ACTIVE]=enriched
        hydrate_product(state,product)
        state.pop('meta-review-product-error',None)
        # Other Meta Review sessions reread on their normal short preference TTL.
    except Exception as error:
        state['meta-review-product-error']=str(error) if isinstance(error,ValueError) else 'Product confirmation could not be saved. Retry when mapping storage is available.'
        hydrate_product(state,source.get('product_mapping') or {})


def render_source(st):
    if st.query_params.get('handoff_id'):
        try:
            import meta_ads_client
            load_link(st.session_state,st.query_params,meta_ads_client.get_meta_config())
        except Exception:
            st.error('Saved winner could not be loaded. Check account access or retry from Meta Review.')
            return True  # Never present a previous winner as this failed URL's reference.
    hydrate(st.session_state)
    source=st.session_state.get(ACTIVE)
    if not source:
        return False
    with st.container(border=True):
        st.subheader('Winner from Meta Review')
        st.caption(f"{source.get('campaign_name')} · {source.get('ad_name')} · {source.get('date_range')} · {source['mode'].replace('_',' ')}")
        st.write(source['decision']['reason'])
        if st.session_state.get('meta-review-product-error'): st.warning(st.session_state['meta-review-product-error'])
        if not (source.get('product_mapping') or {}).get('canonical_row'):
            st.warning('PRODUCT CONFIRMATION REQUIRED · Select the correct canonical Product name below. Suggested matches appear first; selection saves the mapping.')
        else:
            st.caption('Product matched: '+source['product_mapping']['product_title']+' · '+str(source.get('product_match_method') or 'canonical mapping'))
        if source['mode']=='best_components':
            st.warning('Mixed components are an untested combination. Their combined performance is not proven.')
        try:
            data,mime=store.load_media(source['image_sha256'])
            if data:
                st.image(data,width=320)
                st.download_button('Download original winning image',data,file_name='meta-winning-reference.'+('png' if mime=='image/png' else 'jpg'),mime=mime)
                st.caption('Permanent original reference. Attach it with the canonical artwork in the existing ChatGPT prompt workflow.')
            else:
                st.error('Stored winner image unavailable. Repeat the handoff from Meta Review.')
        except Exception:
            st.error('Winner image could not be read from Supabase. Retry when the database is available.')
        with st.expander('Source evidence'):
            st.dataframe([{'Metric':k.replace('_',' ').title(),'Value':v} for k,v in source['metrics'].items() if v is not None],hide_index=True)
            st.caption(f"Ad {source['ad_id']} · Creative {source['creative_id']} · {source['decision']['confidence']} confidence")
        if st.button('Choose a different winner'):
            st.session_state.pop(ACTIVE,None)
            st.rerun()
    return True
