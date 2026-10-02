"""Durable Creative Refresh workspace around the existing saved Ads contract.

Only explicit Save/Open uses this module. No provider or publishing calls.
"""
import base64
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json

import ads_posting_handoff as handoff

FILENAME = 'creative-refresh-workspace.json'


def dumps(result, workflow):
    blobs = {}
    def encode(value):
        if isinstance(value, bytes):
            digest = hashlib.sha256(value).hexdigest()
            blobs[digest] = base64.b64encode(value).decode('ascii')
            return {'$bytes': digest}
        if isinstance(value, (date, datetime)):
            return {'$date': value.isoformat(), '$type': type(value).__name__}
        if isinstance(value, dict):
            return {str(k): encode(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(v) for v in value]
        return value
    payload = {'version': 1, 'workspace': encode({'result': result, 'workflow': {
        **{k:v for k,v in workflow.items() if k != 'refresh_workspace_export'},
        'saving': False, 'save_open': False}}), 'blobs': blobs}
    payload['hash'] = handoff.content_hash(payload)
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def loads(data):
    if len(data) > 100 * 1024 * 1024:
        raise ValueError('Saved refresh is too large to reopen.')
    try:
        payload = json.loads(data)
        if payload['version'] != 1 or payload.pop('hash') != handoff.content_hash(payload):
            raise ValueError()
        blobs = {}
        for digest, value in payload['blobs'].items():
            raw = base64.b64decode(value, validate=True)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError()
            blobs[digest] = raw
        def decode(value):
            if isinstance(value, dict):
                if set(value) == {'$bytes'}:
                    return blobs[value['$bytes']]
                if set(value) == {'$date', '$type'}:
                    return (datetime if value['$type'] == 'datetime' else date).fromisoformat(value['$date'])
                return {k: decode(v) for k, v in value.items()}
            if isinstance(value, list):
                return [decode(v) for v in value]
            return value
        restored = decode(payload['workspace'])
        result, workflow = restored['result'], restored['workflow']
        if result['workflow_mode'] != 'creative_refresh' or result['context_key'] != workflow['context_key']:
            raise ValueError()
        package = workflow.get(handoff.SAVED_PACKAGE_KEY)
        if package:
            handoff.validate_saved_package(package)
            import ads_page
            if package['source_signature'] != ads_page._ads_saved_source_signature(result, workflow):
                raise ValueError()
        return result, workflow
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ValueError('Saved refresh is invalid or incomplete. Open the original saved workspace.') from error


def restore(data, state):
    import ads_page as ads
    result, workflow = loads(data)
    workflow['refresh_workspace_export'] = bytes(data)
    context = result.get('creative_refresh_context') or {}
    state.pop('meta-review-refresh-pending', None)
    source = deepcopy(context.get('source_winner') or {})
    if source:
        state['meta-review-refresh-source'] = source
    else:
        state.pop('meta-review-refresh-source', None)
    state[ads.ADS_ACTIVE_WORKFLOW_MODE_KEY] = ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
    state[ads._ads_result_state_key(ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH)] = result
    state[ads._ads_image_state_key(ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH)] = workflow
    state[ads.ADS_PRODUCT_NAME_KEY] = result['product_name']
    mapping = source.get('product_mapping') or {}
    if mapping:
        from meta_review_handoff import hydrate_product
        hydrate_product(state, mapping)
    else:
        state[ads.ADS_PRODUCT_SELECTOR_KEY] = result['product_name']
    state[ads.ADS_PRODUCT_URL_KEY] = result['product_url']
    state[ads.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY] = context.get('winning_primary_text', '')
    state[ads.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY] = context.get('winning_headline', '')
    for key, field in (('ads_category', 'category'), ('ads_country', 'country'), ('ads_campaign_type', 'campaign_type')):
        state[key] = result[field]
    moment = result.get('campaign_moment') or {}
    for field in ('type', 'name', 'market', 'date', 'promotion', 'strength'):
        state['ads_campaign_moment_' + field] = moment.get(field) or (None if field == 'date' else '')
    state['ads_campaign_moment_market'] = moment.get('market') or 'Use selected ad country'
    state['ads_campaign_moment_strength'] = moment.get('strength') or 'Subtle'
    state['ads_campaign_moment_include_images'] = bool(moment.get('include_in_image_prompts'))
    if isinstance(state['ads_campaign_moment_date'], str):
        state['ads_campaign_moment_date'] = date.fromisoformat(state['ads_campaign_moment_date'])
    return result


def restore_folder(ads, folder, state):
    """Reopen a saved route using normal server-side Files authorization."""
    import dropbox_integration as dropbox
    if not ads.os_accounts.can_access_page(ads.current_ads_user(), 'Files'):
        raise ValueError('Files access is required to open this saved refresh.')
    token, root = ads._ads_dropbox_connection()
    if not dropbox.path_is_within_root(folder, root):
        raise ValueError('Saved refresh is outside the approved Files folder.')
    _, data = dropbox.get_file_bytes(token, dropbox.join_upload_path(folder, FILENAME))
    return restore(data, state)
