"""New Ads entry point into the existing Publish + Ad companion queue."""
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import design_publish_ad as companion


def enqueue(user, result, selection, *, request_key=None):
    """Freeze the submitted brief; retries of this draft return the same job."""
    import ads_page

    companion.check_request(user, result.get('category'), result.get('country'))
    if (result.get('campaign_type') != 'Instant Experience'
            or result.get('workflow_mode') == ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
            or result.get('platform', 'meta').lower() != 'meta'):
        raise ValueError('The companion queue supports New Ads Meta Instant Experience campaigns.')
    issue = ads_page.validate_ads_inputs(result.get('product_name'), result.get('category'),
        result.get('country'), result.get('campaign_type'), product_url=result.get('product_url'))
    issue = issue or ads_page.validate_campaign_moment(result.get('campaign_moment'), selected_country=result.get('country'))
    if issue:
        raise ValueError(issue)
    row = (selection or {}).get('row') or {}
    pid = str(row.get('shopify_product_id') or '')
    handle = ads_page._edition_ops_product_handle_from_row(row)
    if (not re.fullmatch(r'(?:gid://shopify/Product/)?[0-9]+', pid)
            or not handle or urlsplit(result['product_url']).path.rstrip('/') != '/products/' + handle
            or not result.get('master_prompt')):
        raise ValueError('Select a catalog product and its matching product page before adding it to the queue.')
    payload = dict(source='new_ads', requester=str(user['id']), sport=result['category'],
        country=result['country'], stage='waiting', result=result,
        product_gid='gid://shopify/Product/' + pid.rsplit('/', 1)[-1], handle=handle)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    key = str(uuid5(NAMESPACE_URL, 'sports-cave-new-ads:' + (
        str(user['id'])+':request:'+request_key if request_key else fingerprint)))
    payload['upload'] = key  # Existing companion protocol uses this as the ad job ID.
    with companion.connect() as conn, conn.cursor() as cur:
        cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
            ON CONFLICT DO NOTHING''', (companion.PREFIX + key, json.dumps(payload)))
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (companion.PREFIX + key,))
        saved = cur.fetchone()['value']
        if request_key and any(saved.get(field)!=payload.get(field) for field in ('product_gid','country','sport')):
            raise ValueError('This request already queued different selections. Choose the product again for a new request.')
    return dict(id=key, **companion.public(saved))


def prepare(value):
    """Verify the selected product, then use the shared generation/posting flow."""
    from ads_auto_post import destination
    from ads_product_catalog import verify_live_black_frame_variant
    from product_upload_mapping import read_edition
    from product_upload_services import Dropbox
    from shopify_sync import fetch_product_by_shopify_id

    result = value['result']
    pid = value['product_gid']
    if not read_edition(companion.connect, pid):
        raise ValueError('This product must be mapped in Edition Ops before automated ads can run.')
    product = fetch_product_by_shopify_id(pid)
    if (not product or str(product.get('shopify_product_id', '')).rsplit('/', 1)[-1] != pid.rsplit('/', 1)[-1]
            or product.get('status') != 'ACTIVE' or product.get('handle') != value['handle']
            or not product.get('online_store_url')
            or urlsplit(product['online_store_url']).path.rstrip('/') != '/products/' + value['handle']):
        raise ValueError('The selected product no longer matches an active Shopify listing.')
    black = verify_live_black_frame_variant(pid, value['handle'])
    image = black.get('original_black_image_url')
    if not image:
        raise ValueError('No verified original Black-frame image is available for this product.')
    reference = f"""Retrieve the original Black-frame product image at this exact verified Shopify image URL:
{json.dumps(image)}
Product: {json.dumps(result['product_name'])}; Shopify ID: {pid}.
Black variant: {black['variant_id']}; verification page: {black['variant_url']}.
Use the full-resolution image itself as the reference for all three covers. Inspect it
before generating and preserve its exact artwork and Black frame. Do not substitute
a page screenshot, thumbnail, another product or another frame. If this image cannot
be retrieved or verified, report SC_AD_BLOCKED and do not invent replacement artwork."""
    dbx = Dropbox()
    root = dbx.context['root_path']
    folder = destination(dbx.api, root, result) + '/new-ads-' + value['upload']
    dbx.api.ensure_folder_path(dbx.token, folder, root_path=root)
    return dict(stage='opening', folder=folder, reference=black,
                prompt=companion.delivery_prompt(result, reference, folder, value['upload']))
