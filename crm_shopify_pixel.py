"""Untrusted app-pixel telemetry. This module deliberately has no journey hooks."""
import hashlib
import json
import re
from crm_logic import date, now
from crm_tracking import public_https

EVENTS = frozenset(('product_viewed','product_added_to_cart','product_removed_from_cart','cart_viewed','checkout_started','checkout_completed'))


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)!={'endpoint','shop','ingestionId'}:raise ValueError('Invalid app pixel settings.')
    if not public_https(settings['endpoint']) or not settings['endpoint'].endswith('/shopify/customer-events'):raise ValueError('Use the deployed HTTPS customer-events endpoint.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',settings['shop']):raise ValueError('Invalid Shopify store.')
    if not re.fullmatch('[a-f0-9]{32}',settings['ingestionId']):raise ValueError('Invalid public ingestion identifier.')
    return settings


def record(store,payload,state=None):
    state=store.state('shopify_automation_pixel') if state is None else state
    if not state.get('id') or not state.get('activated_at'):raise ValueError('App pixel is not activated.')
    settings=validate_settings(state['settings'])
    fields={'event_id','event_name','client_id','product_id','occurred_at','shop','ingestionId','analytics_allowed','marketing_allowed'}
    if not isinstance(payload,dict) or set(payload)!=fields:raise ValueError('Invalid pixel envelope.')
    if payload['shop']!=settings['shop'] or payload['ingestionId']!=settings['ingestionId']:raise ValueError('Unknown app context.')
    if payload['analytics_allowed'] is not True or payload['marketing_allowed'] is not True:raise ValueError('Consent required.')
    if payload['event_name'] not in EVENTS:raise ValueError('Unsupported event.')
    for field in ('event_id','client_id'):
        if not isinstance(payload[field],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',payload[field]):raise ValueError('Invalid event identity.')
    product=payload['product_id']
    if not isinstance(product,str) or (product and not re.fullmatch(r'gid://shopify/Product/\d+',product)):raise ValueError('Invalid product identity.')
    at=date(payload['occurred_at'])
    if not at or at<date(state['activated_at']) or not -300<=(now()-at).total_seconds()<=86400:raise ValueError('Invalid event timestamp.')
    client=hashlib.sha256((settings['shop']+':'+payload['client_id']).encode()).hexdigest()
    identity=hashlib.sha256((settings['shop']+':'+payload['event_id']).encode()).hexdigest()
    with store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(72634192)')
        volume=conn.execute("SELECT count(*) AS n FROM crm_shopify_pixel_events WHERE received_at>now()-interval '1 minute'").fetchone()['n']
        if volume>=600:raise ValueError('Pixel rate limit reached.')
        row=conn.execute('''INSERT INTO crm_shopify_pixel_events(event_id,shop,event_name,client_hash,product_id,occurred_at)
          VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id''',
          (identity,settings['shop'],payload['event_name'],client,product or None,at)).fetchone()
    if row:
        import logging
        logging.getLogger(__name__).info('shopify_pixel event_name=%s client_hash=%s',payload['event_name'],client)
    # Public settings/Origin are context and abuse controls, NOT authenticated
    # Shopify identity. Even checkout_completed cannot recover or trigger email.
    return bool(row)
