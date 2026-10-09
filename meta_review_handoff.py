"""Persistent, certificate-independent creative reference handoff; no Meta mutations."""
from sports_categories import normalize_sport_category
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


def reference_image_bytes(url):
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
    return bytes(data), mime


def archive_image(url):
    data, mime = reference_image_bytes(url)
    return store.save_media(data, mime)


def resolve_campaign_type(source, ad=None):
    """Resolve only explicit saved/Meta format evidence; never inspect image content."""
    from meta_review_benchmarks import ad_format

    source, ad = source or {}, ad or {}
    detected = source.get('creative_format') or (ad.get('winning_creative') or {}).get('creative_format')
    if detected:
        types = {'CAROUSEL': 'Carousel', 'DYNAMIC_CAROUSEL': 'Carousel', 'INSTANT_EXPERIENCE': 'Instant Experience', 'SINGLE_IMAGE': 'Single Image / Video'}
        return {'campaign_type': types.get(detected, 'Single Image / Video'), 'confirmed': detected in types,
                'source': source.get('creative_format_source') or 'resolved_creative', 'creative_format': detected}
    aliases = {
        'SINGLE IMAGE / VIDEO': 'Single Image / Video', 'SINGLE IMAGE': 'Single Image / Video',
        'SINGLE VIDEO': 'Single Image / Video', 'IMAGE': 'Single Image / Video', 'VIDEO': 'Single Image / Video',
        'CAROUSEL': 'Carousel', 'INSTANT EXPERIENCE': 'Instant Experience', 'CANVAS': 'Instant Experience',
    }
    def known(value):
        return aliases.get(str(value or '').strip().upper().replace('_', ' ').replace('-', ' '))
    def result(value, origin, confirmed=True):
        return {'campaign_type': value, 'confirmed': confirmed, 'source': origin}
    for label, record in (('saved_source', source), ('source_ad', ad)):
        for key in ('campaign_type', 'ad_type', 'format', 'source_campaign_type'):
            value = known(record.get(key))
            if value:
                return result(value, label + '.' + key)
    # The selected ad's benchmark already derives its format from Graph metadata.
    value = known((ad.get('benchmark') or {}).get('format'))
    if value:
        return result(value, 'source_ad.benchmark.format')
    metadata = [ad.get('creative_metadata'), (ad.get('raw') or {}).get('creative'),
                source.get('creative_metadata'), source.get('creative'), source.get('raw')]
    for raw in metadata:
        if not isinstance(raw, dict):
            continue
        raw = raw.get('creative') or raw
        if not isinstance(raw, dict):
            continue
        value = known(ad_format(raw))
        spec = raw.get('object_story_spec') or {}
        formats = (raw.get('asset_feed_spec') or {}).get('ad_formats') or []
        resolved = {known(item) for item in formats}
        resolved.discard(None)
        if value == 'Instant Experience':
            return result(value, 'source_creative.metadata')
        if len(resolved) > 1:
            return result('Single Image / Video', 'ambiguous_creative_formats', False)
        if value:
            return result(value, 'source_creative.metadata')
        if len(resolved) == 1:
            return result(resolved.pop(), 'source_creative.ad_formats')
        if not formats and (spec.get('video_data') or raw.get('video_id') or raw.get('image_url') or (spec.get('link_data') or {}).get('image_hash')):
            return result('Single Image / Video', 'source_creative.single_asset')
    # Legacy handoffs retained destination metadata and carousel presence only.
    if ad_format({'url': source.get('destination_url')}) == 'INSTANT EXPERIENCE':
        return result('Instant Experience', 'source_destination')
    if source.get('carousel') or (ad.get('assets') or {}).get('carousel'):
        return result('Carousel', 'source_creative.carousel')
    for key in ('posting_mapping', 'ad_mapping', 'product_mapping'):
        mapping = source.get(key) or {}
        for field in ('campaign_type', 'ad_type', 'format'):
            value = known(mapping.get(field))
            if value:
                return result(value, key + '.' + field)
    prior = source.get('campaign_type_resolution') or {}
    if prior.get('confirmed') and known(prior.get('campaign_type')):
        return result(known(prior['campaign_type']), prior.get('source') or 'durable_handoff')
    return result('Single Image / Video', 'legacy_default', False)


def build_package(ad,selections,context,mode):
    if mode not in ('complete_ad','best_components'):
        raise ValueError('Unknown refresh mode.')
    for kind in ('image','primary_text','headline'):
        item=selections.get(kind)
        if not item or not item.get('value'):
            raise ValueError('Select original image, primary text and headline before refreshing.')
        if mode=='complete_ad' and str(item['ad_id'])!=str(ad['ad_id']):
            raise ValueError('Complete-ad mode must use assets from the same ad.')
    package = {**deepcopy(context),'mode':mode,'ad_id':ad['ad_id'],'ad_name':ad.get('ad_name'),
            'adset_id':ad.get('adset_id'),'creative_name':ad.get('creative_name') or ((ad.get('raw') or {}).get('creative') or {}).get('name'),
            'product_destination_urls':[item['value'] for item in ad['assets']['url']],
            'creative_id':ad['assets']['creative_id'],'components':deepcopy(selections),
            'metrics':deepcopy(ad['metrics']),'decision':deepcopy(ad['decision']),
            'dynamic':ad['assets']['dynamic'],'carousel':ad['assets']['carousel'],
            'description':next(iter(ad['assets']['description']),{}).get('value',''),
            'cta':next(iter(ad['assets']['cta']),{}).get('value',''),
            'destination_url':next(iter(ad['assets']['url']),{}).get('value','')}
    import meta_review_creative as creative
    raw = (ad.get('raw') or {}).get('creative') or ad.get('creative_metadata') or {}
    resolved = deepcopy(ad.get('winning_creative') or creative.normalize(raw))
    if resolved.get('carousel_resolution_incomplete'):
        raise ValueError('Reload the complete ordered carousel before applying Creative Refresh.')
    if mode == 'best_components' and str(selections['image']['ad_id']) != str(ad['ad_id']):
        resolved = {**resolved, 'creative_format': 'UNKNOWN', 'cards': [],
                    'creative_format_source': 'mixed_ad_components'}
    # The existing handoff itself is the normalized winning creative. Retain
    # carousel_cards for downstream compatibility, without duplicating raw Graph
    # payloads or a second copy of the complete creative in persistence/prompts.
    package.update({key: deepcopy(value) for key, value in resolved.items() if key not in ('raw', 'cards')})
    package['carousel_cards'] = deepcopy(resolved.get('cards') or [])
    package['carousel'] = resolved.get('creative_format') in creative.CAROUSEL_FORMATS
    if package['carousel']:
        require_complete_carousel(package)
        for card in package['carousel_cards']: card['source_ad_id']=str(ad['ad_id'])
        package['diagnostic'] = creative.diagnostic(package, ad_id=ad['ad_id'],
            handoff_count=len(package['carousel_cards']))
        creative.log_resolution(package,str(ad['ad_id']),len(package['carousel_cards']))
    package['source_fingerprint'] = creative.fingerprint(package)
    package['campaign_type_resolution'] = resolve_campaign_type(package, ad)
    if package['campaign_type_resolution']['confirmed']:
        package['source_campaign_type'] = package['campaign_type_resolution']['campaign_type']
    return package


def require_complete_carousel(package):
    cards=package.get('carousel_cards') or []
    if len(cards)<2 or [c.get('position') for c in cards]!=list(range(1,len(cards)+1)):
        raise ValueError('Reload the complete ordered carousel before applying Creative Refresh.')
    expected = package.get('source_card_count')
    if package.get('carousel_resolution_incomplete') or (expected is not None and len(cards) != expected - package.get('excluded_end_card_count', 0)):
        raise ValueError('Source carousel card count changed. Reload the complete ordered carousel before refreshing.')
    missing=[str(c['position']) for c in cards if c.get('image_unavailable') or not c.get('image_url')]
    if missing: raise ValueError('Missing source carousel cards: '+', '.join(missing)+'. Reload from Meta before refreshing.')


def queue(package,state,actor='sports_cave_os'):
    if package.get('carousel'): require_complete_carousel(package)
    package=products.enrich(package)
    package['image_sha256']=archive_image(package['components']['image']['value'])
    archived = {package['components']['image']['value']: package['image_sha256']}
    for card in (package.get('carousel_cards') or []):
        if card.get('image_url'):
            url = card['image_url']
            if url not in archived:
                try:
                    archived[url] = archive_image(url)
                except ValueError:
                    raise ValueError('Source carousel card '+str(card['position'])+' could not be archived. No complete handoff was saved.') from None
            card['image_sha256'] = archived[url]
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
    # A callback/link replay is not a new editing session. Compare the same
    # representation on both sides before touching product fields or drafts.
    comparable=lambda value:{k:v for k,v in (value or {}).items() if k!='campaign_type_resolution'}
    if comparable(package)==comparable(state.get(ACTIVE)):
        state.pop(PENDING,None)
        import logging
        logging.getLogger(__name__).info('creative_refresh_handoff_replayed draft_preserved=true')
        return False
    import ads_page
    state[ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY]=package['components']['primary_text']['value']
    state[ads_page.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY]=package['components']['headline']['value']
    mapping=package.get('product_mapping') or {}
    hydrate_product(state,mapping)
    # Unmapped references must not inherit an unrelated previous product/market.
    state['ads_country']='Select country'
    market={'AU':'Australia','US':'USA','GB':'UK','CA':'Canada','NZ':'New Zealand'}.get(package.get('market'),package.get('market'))
    if market in ads_page.COUNTRY_OPTIONS:
        state['ads_country']=market
    resolution = resolve_campaign_type(package)
    state['ads_campaign_type'] = resolution['campaign_type']
    if resolution['campaign_type'] == 'Carousel':
        state.pop(ads_page.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY, None)
        state.pop(ads_page.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY, None)
    state[ACTIVE] = {**deepcopy(package), 'campaign_type_resolution': resolution}
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
    category = normalize_sport_category(mapping.get('category') or mapping.get('sport'))
    state['ads_category']=category if category in ads_page.CATEGORY_OPTIONS else 'Select category'


def product_selector_rows(rows,state):
    source=state.get(ACTIVE) or {}
    mapping=source.get('product_mapping') or {}
    canonical=mapping.get('canonical_row')
    if not canonical:
        # Resolve authoritative identities only; fuzzy suggestions stay manual.
        identity = mapping.get('product_id') or source.get('product_id')
        handle = mapping.get('product_handle') or products.product_url_handle(mapping.get('product_url') or source.get('product_url'))
        exact = [r for r in rows if (str(r.get('shopify_product_id') or r.get('product_id') or '') == str(identity) if identity else bool(handle) and str(r.get('product_handle') or r.get('shopify_handle') or '').lower() == handle.lower())]
        if len(exact) == 1:
            resolved = products.canonical(exact[0])
            if resolved:
                mapping = resolved
                source['product_mapping'] = mapping
                hydrate_product(state, mapping)
                canonical = mapping['canonical_row']
    if not canonical: return rows
    result = [r for r in rows if str(r.get('product_handle') or r.get('shopify_handle') or '') != mapping.get('product_handle')]
    return [canonical, *result]


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
    with st.container(border=True, key='ads-refresh-winner'):
        st.markdown('**WINNER FROM META REVIEW**')
        if st.session_state.get('meta-review-product-error'): st.warning(st.session_state['meta-review-product-error'])
        if source.get('mode')=='best_components':
            st.warning('Mixed components are an untested combination. Their combined performance is not proven.')
        resolution = resolve_campaign_type(source)
        if not resolution['confirmed']:
            st.warning('Creative format could not be confirmed from Meta. Choose a supported refresh type manually.')
        if source.get('creative_format') in ('DYNAMIC', 'VIDEO'):
            st.warning('This source format has no deterministic fixed-card refresh mapping.')
        if resolution['campaign_type'] == 'Carousel':
            from meta_review_creative import render_cards, render_shared_primary_text
            render_cards(st, source, archived=True)
            render_shared_primary_text(st, source)
            return True
        try:
            from ads_refresh_reference import load_winner_media
            data,mime=load_winner_media(st.session_state, source, store.load_media)
            if data:
                preview, actions = st.columns([1, 3])
                with preview:
                    st.image(data,width=200)
                with actions:
                    st.markdown('**Winning advertisement · creative reference**')
                    if source.get('ad_name'):
                        st.caption(source['ad_name'])
                    st.caption('Use this winner for creative direction. The canonical product image, when supplied, defines the exact artwork and frame.')
                    from ads_refresh_reference import render_winning_image_copy
                    render_winning_image_copy(data, mime)
            else:
                st.error('Stored winner image unavailable. Repeat the handoff from Meta Review.')
        except Exception:
            st.error('Winner image could not be read from Supabase. Retry when the database is available.')
    return True
