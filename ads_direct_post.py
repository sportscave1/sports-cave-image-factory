"""Direct Ads submission reusing Posting's imports, smart targeting and job service."""
from copy import deepcopy
from uuid import uuid4
import streamlit as st
import ads_posting_page as posting
import ads_posting_handoff as handoff
from meta_posting_jobs import JOBS
from ads_posting_progress import track


def references(ad_type):
    overview, refs, overview_error, refs_error = posting._meta_state(ad_type=ad_type)
    if overview_error or refs_error or not overview.get('posting_ready'):
        raise ValueError(overview_error or refs_error or 'Meta setup is unavailable. Refresh Meta in Posting.')
    if not (refs.get('dataset_resolution') or {}).get('resolved'):
        raise ValueError('The configured Meta dataset could not be resolved. Check Posting.')
    if ad_type == posting.AD_TYPE and not (refs.get('catalog_resolution') or {}).get('resolved'):
        raise ValueError('The Shopify catalog could not be resolved. Check Posting.')
    return refs


@st.cache_data(ttl=60, show_spinner=False)
def refresh_destination(ad_id, ad_type):
    """Read the original ad's current Ad Set; never reconstruct its targeting."""
    client = posting.MetaPostingClient()
    ad = client.ad(ad_id)
    adset_id = str(ad.get('adset_id') or '')
    if not adset_id:
        raise ValueError('The original ad has no readable Ad Set. Open Posting to review it.')
    adset = (client.configured_carousel_adset(adset_id) if ad_type == posting.CAROUSEL_AD_TYPE
             else client.configured_adset(adset_id))
    if not adset.get('campaign_id'):
        raise ValueError('The original campaign could not be resolved. Open Posting to review it.')
    product_set_id = str((adset.get('promoted_object') or {}).get('product_set_id') or '')
    if ad_type == posting.AD_TYPE:
        creative_id = str((ad.get('creative') or {}).get('id') or '')
        if creative_id:
            product_set_id = str(client.creative(creative_id).get('product_set_id') or product_set_id)
    return {'posting_mode': posting.POSTING_MODE_EXISTING,
            'target_campaign_id': str(adset['campaign_id']), 'target_adset_id': adset_id,
            'product_set_id': product_set_id,
            'audience': {'type': 'inherited', 'id': '', 'key': 'inherited'}}


def render_settings(result, workflow):
    """Use the exact same ranking and Show more behavior as the Posting form."""
    kind = result.get('campaign_type')
    if kind not in (posting.AD_TYPE, posting.CAROUSEL_AD_TYPE):
        return {}, ['This ad format needs manual review in Posting.']
    try:
        refs = references(kind)
        catalog = str((refs.get('catalog_resolution') or {}).get('id') or '') if kind == posting.AD_TYPE else ''
        if result.get('workflow_mode') == 'creative_refresh':
            source = (result.get('creative_refresh_context') or {}).get('source_winner') or {}
            ad_id = str(source.get('ad_id') or '')
            if not ad_id:
                raise ValueError('The original Meta ad is not linked. Open Posting to choose its destination safely.')
            settings = refresh_destination(ad_id, kind)
            if kind == posting.AD_TYPE and not settings['product_set_id']:
                raise ValueError('The original Product set could not be verified. Open Posting to review it.')
            settings['source_ad_id'] = ad_id
        else:
            prefix = 'ads-targeting::' + str(result['context_key'])
            saved = workflow.get('posting_settings') or {}
            columns = st.columns(2) if kind == posting.AD_TYPE else (st.container(),)
            product_set = ''
            if kind == posting.AD_TYPE:
                with columns[0]:
                    key = prefix + '::product_set'
                    rows = {str(row['id']): row for row in refs.get('product_sets') or () if row.get('id')}
                    if key not in st.session_state and saved.get('product_set_id') in rows:
                        st.session_state[key] = saved['product_set_id']
                    if st.session_state.get(key) not in rows:
                        st.session_state.pop(key, None)
                    options = posting._relevant_target_options(tuple(rows.values()),
                        product_title=result.get('product_name'), sport=result.get('category'), key=key)
                    product_set = st.selectbox('Product set', options, index=None,
                        placeholder='Select a Meta product set', format_func=lambda value: rows[value].get('name') or value,
                        key=key, disabled=not rows) or ''
            with columns[-1]:
                key = prefix + '::audience'
                audiences = posting._audience_options(refs)
                by_key = {row['key']: row for row in audiences}
                if key not in st.session_state:
                    st.session_state[key] = (saved.get('audience') or {}).get('key', 'broad')
                if st.session_state[key] not in by_key:
                    st.session_state[key] = 'broad'
                options = posting._relevant_target_options(audiences, product_title=result.get('product_name'),
                    sport=result.get('category'), key=key, id_key='key', default_selection='broad')
                selected = st.selectbox('Audience', options, key=key,
                    format_func=lambda value: 'Broad — Sports Cave Default' if value == 'broad'
                    else f"{by_key[value]['label_type']} — {by_key[value]['name']}")
                audience = by_key[selected]
            settings = {'posting_mode': posting.POSTING_MODE_NEW, 'product_set_id': product_set, 'audience': audience}
        settings['submission_id'] = workflow.setdefault('direct_post_id', str(uuid4()))
        settings['catalog_id'] = catalog
        settings['customer_lifecycle_strategy'] = posting.CUSTOMER_LIFECYCLE_ALL_AUDIENCES
        workflow['posting_settings'] = deepcopy(settings)
        result['posting_settings'] = deepcopy(settings)
        return settings, ([] if kind != posting.AD_TYPE or settings['product_set_id'] else ['Select a Product set before posting.'])
    except Exception as error:
        return {}, [str(error)]


def stage_request(package, settings, *, state=None, product_records=None):
    """Load the same verified package into the recovery form, without rendering it."""
    state = st.session_state if state is None else state
    if state.get('posting_tracked_job') or st.query_params.get('meta_posting_job'):
        raise ValueError('A posting job needs to finish or be reviewed before posting another package.')
    if package.get('ad_type') not in (posting.AD_TYPE, posting.CAROUSEL_AD_TYPE):
        raise ValueError('This ad format needs manual review in Posting.')
    if product_records is None:
        product_records, _ = posting._product_selector_state(posting._product_rows_state())
    staging = dict(state)
    handoff.queue_saved_package(package, state=staging)
    posting.consume_saved_posting_package(product_records, state=staging)
    saved_identity = (package.get('posting_settings') or {}).get('submission_id')
    if saved_identity:
        staging[posting.SUBMISSION_ID_KEY] = str(saved_identity)
    batch = package['batch']
    matched = posting.match_posting_import_product(batch, product_records)
    kind = package['ad_type']
    count = int(staging.get(posting.CAROUSEL_COUNT_KEY, 5)) if kind == posting.CAROUSEL_AD_TYPE else 3
    image_keys = posting.CAROUSEL_IMAGE_STATE_KEYS if kind == posting.CAROUSEL_AD_TYPE else posting.IMAGE_STATE_KEYS
    headline_keys = posting.CAROUSEL_HEADLINE_KEYS if kind == posting.CAROUSEL_AD_TYPE else posting.HEADLINE_KEYS
    description_keys = posting.CAROUSEL_DESCRIPTION_KEYS if kind == posting.CAROUSEL_AD_TYPE else posting.DESCRIPTION_KEYS
    creatives = [{'image': staging.get(image_keys[i]) or {}, 'headline': staging.get(headline_keys[i], ''),
                  'description': staging.get(description_keys[i], ''),
                  'primary_text': staging.get(posting.PRIMARY_TEXT_KEYS[i], '') if kind == posting.AD_TYPE else ''}
                 for i in range(count)]
    primary = [staging.get(key, '') for key in posting.CAROUSEL_PRIMARY_TEXT_KEYS]
    refs = references(kind)
    settings = deepcopy(settings)
    if package.get('creative_refresh'):
        # Re-read current source on submission; never substitute a broad/default audience.
        ad_id = str(((package.get('source_provenance') or {}).get('source_winner') or {}).get('ad_id') or '')
        if not ad_id:
            raise ValueError('The original Meta ad is not linked. Review its destination in Posting.')
        settings.update(refresh_destination.__wrapped__(ad_id, kind))
    elif settings.get('posting_mode') != posting.POSTING_MODE_NEW:
        raise ValueError('New Ads requires a new-campaign destination.')
    catalog_id = str((refs.get('catalog_resolution') or {}).get('id') or '') if kind == posting.AD_TYPE else ''
    product_set_id = str(settings.get('product_set_id') or '')
    if kind == posting.AD_TYPE and product_set_id not in {str(row.get('id')) for row in refs.get('product_sets') or ()}:
        raise ValueError('The selected Product set is no longer available in the configured catalog.')
    audience = settings.get('audience') or {}
    if not package.get('creative_refresh') and audience.get('key') not in {row['key'] for row in posting._audience_options(refs)}:
        raise ValueError('The selected Audience is no longer available. Select it again.')
    common = dict(product_title=batch['product_name'], product_url=batch['product_url'],
                  country=batch['country'], sport=batch['sport_category'],
                  dataset_id=str(refs['dataset_resolution']['id']), identities_ready=bool(refs.get('page') and refs.get('instagram')))
    ready = (posting._carousel_form_ready(**common, cards=creatives, primary_texts=primary, card_count=count)
             if kind == posting.CAROUSEL_AD_TYPE else
             posting._posting_form_ready(**common, creatives=creatives, catalog_id=catalog_id, product_set_id=product_set_id))
    if not ready:
        raise ValueError('The saved ad is incomplete. Open Posting to review the images, copy and settings.')
    if any(not item['image'].get('valid') for item in creatives):
        raise ValueError('The saved images have not passed Posting validation.')
    staging[posting.PRODUCT_SET_KEY] = product_set_id
    staging[posting.AUDIENCE_KEY] = audience.get('key') or 'broad'
    staging[posting.CUSTOMER_LIFECYCLE_KEY] = posting.CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    staging[posting.POSTING_MODE_KEY] = posting.POSTING_MODE_LABELS[settings['posting_mode']]
    staging[posting.EXISTING_CAMPAIGN_KEY] = settings.get('target_campaign_id', '')
    staging[posting.EXISTING_ADSET_KEY] = settings.get('target_adset_id', '')
    request = posting._build_posting_request(submission_id=staging[posting.SUBMISSION_ID_KEY],
        product_id=str((matched.get('row') or {}).get('shopify_product_id') or batch.get('product_id') or ''),
        product_title=batch['product_name'], product_handle=batch.get('product_handle', ''), product_url=batch['product_url'],
        country=batch['country'], sport=batch['sport_category'], catalog_id=catalog_id,
        product_set_id=product_set_id, audience=audience, creatives=creatives if kind == posting.AD_TYPE else (),
        posting_mode=settings['posting_mode'], target_campaign_id=settings.get('target_campaign_id', ''),
        target_adset_id=settings.get('target_adset_id', ''), ad_type=kind,
        carousel_cards=creatives if kind == posting.CAROUSEL_AD_TYPE else (), carousel_primary_texts=primary)
    for key in set(state) | set(staging):
        if key.startswith(posting.STATE_PREFIX) or key in (handoff.PENDING_KEY, handoff.LOADED_KEY, handoff.CONSUMED_KEY):
            if key in staging:
                state[key] = staging[key]
            else:
                state.pop(key, None)
    state.pop(handoff.PENDING_KEY, None)
    return request


def submit_saved(package, settings, workflow):
    if workflow.get('direct_post_submission_id'):
        raise ValueError('This package has already been submitted. Review its saved job in Posting.')
    request = stage_request(package, settings)
    # Bind before dispatch, including uncertain reservation responses. Never resubmit on rerun.
    workflow['direct_post_submission_id'] = request.submission_id
    st.session_state[posting.PROCESSING_KEY] = True
    st.session_state[posting.RUN_STATE_KEY] = posting.RUN_STATE_ACTIVE
    track(request.submission_id)
    try:
        JOBS.submit(request)
    except Exception:
        try:
            row = JOBS.snapshot(request.submission_id)
        except Exception:
            row = None
        if row is not None and not row.get('submission_id'):
            # A confirmed absent reservation is safe to retry with this same ID.
            from ads_posting_progress import clear
            clear()
            workflow.pop('direct_post_submission_id', None)
            st.session_state[posting.PROCESSING_KEY] = False
            st.session_state[posting.RUN_STATE_KEY] = posting.RUN_STATE_DRAFT
        raise
    posting._load_recent_posts.clear()
    return request.submission_id
