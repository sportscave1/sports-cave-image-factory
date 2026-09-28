"""Default-off, untrusted browser telemetry. No customer identity or dispatch hooks."""
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from crm_logic import date,now
from crm_tracking import public_https

EVENTS={'page_viewed','product_viewed','product_added_to_cart','checkout_started','checkout_completed'}
_LOCK=threading.Lock();_BUCKETS={}


def config(env=None):
    env=os.environ if env is None else env
    enabled=env.get('CRM_WEBSITE_TRACKING_ENABLED','').lower()=='true'
    origins={v.strip() for v in env.get('CRM_WEBSITE_ALLOWED_ORIGINS','').split(',') if v.strip()}
    origins={v for v in origins if (public_https(v) and v.count('/')==2) or v=='null'}
    pixel=env.get('CRM_WEBSITE_PIXEL_ID','')
    valid=bool(re.fullmatch(r'[a-zA-Z0-9_-]{16,80}',pixel))
    return {'enabled':enabled,'origins':origins,'pixel_id':pixel if valid else '',
            'configured':bool(valid and origins),'endpoint':env.get('CRM_PUBLIC_BASE_URL','').rstrip('/')+'/crm/tracking/events'}


def allow_rate(peer,clock=time.monotonic):
    # Memory-only peer keys, no IP address logs/storage. Global cap limits spoofed IDs.
    with _LOCK:
        stamp=int(clock()//60)
        for key in list(_BUCKETS):
            if _BUCKETS[key][0]!=stamp:_BUCKETS.pop(key)
        if len(_BUCKETS)>2000:return False
        keys=('global','peer:'+str(peer))
        if any(_BUCKETS.get(k,(stamp,0))[1]>=limit for k,limit in zip(keys,(600,60))):return False
        for k in keys:_BUCKETS[k]=(stamp,_BUCKETS.get(k,(stamp,0))[1]+1)
        return True


def validate_event(payload,cfg):
    fields={'pixel_id','event_id','event_type','session_ref','campaign_key','product_ref','occurred_at','test_context','analytics_allowed','marketing_allowed'}
    if not isinstance(payload,dict) or set(payload)!=fields:raise ValueError('Invalid tracking schema.')
    if payload['pixel_id']!=cfg['pixel_id'] or not cfg['pixel_id']:raise ValueError('Unknown pixel identifier.')
    if payload['analytics_allowed'] is not True or payload['marketing_allowed'] is not True:raise ValueError('Tracking consent is required.')
    if payload['event_type'] not in EVENTS or type(payload['test_context']) is not bool:raise ValueError('Invalid event type.')
    if not isinstance(payload['event_id'],str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',payload['event_id']):raise ValueError('Invalid event ID.')
    try:session=str(uuid.UUID(payload['session_ref']))
    except (ValueError,TypeError,AttributeError):raise ValueError('Invalid session reference.') from None
    campaign=payload['campaign_key'];product=payload['product_ref']
    if not isinstance(campaign,str) or (campaign and not re.fullmatch(r'sc_[a-f0-9]{32}',campaign)):raise ValueError('Invalid campaign reference.')
    if not isinstance(product,str) or (product and not re.fullmatch(r'gid://shopify/Product/\d+',product)):raise ValueError('Invalid product reference.')
    occurred=date(payload['occurred_at'])
    if not occurred or not -300<=(now()-occurred).total_seconds()<=86400:raise ValueError('Event timestamp outside accepted window.')
    return (payload['event_id'],payload['event_type'],session,campaign or None,product or None,occurred,payload['test_context'])


def record_event(store,payload,cfg):
    if not cfg['enabled'] or not cfg['configured']:raise ValueError('Tracking is disabled.')
    fields=validate_event(payload,cfg)
    # Durable rate cap across service processes. Endpoint is intentionally untrusted.
    with store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(72634191)')
        volume=conn.execute("SELECT count(*) AS total FROM crm_website_events WHERE received_at>now()-interval '1 minute'").fetchone()['total']
        if volume>=600:raise ValueError('Tracking rate limit reached.')
        return bool(conn.execute('INSERT INTO crm_website_events(event_id,event_type,session_ref,campaign_key,product_ref,occurred_at,test_context) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id',fields).fetchone())


def pixel_code(cfg):
    if not cfg['configured'] or not public_https(cfg['endpoint']):raise ValueError('Configure the public pixel ID, allowed origins and HTTPS webhook base first.')
    source=Path(__file__).with_name('crm_customer_pixel.js').read_text(encoding='utf-8')
    return source.replace('__SC_CONFIG__',json.dumps({'endpoint':cfg['endpoint'],'pixel_id':cfg['pixel_id'],'enabled':False,'test_context':True}))
