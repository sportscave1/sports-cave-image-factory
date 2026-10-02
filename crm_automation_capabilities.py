"""Admin/worker diagnostics use the Sports Cave credentials, not connector scopes."""
import json
from datetime import timedelta
from pathlib import Path
import tomllib
from crm_logic import date, now

EXPECTED_SCOPES = ('write_pixels','read_customer_events','write_marketing_events')
TOPICS = {'welcome':('CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE',),
          'abandoned':('CHECKOUTS_CREATE','CHECKOUTS_UPDATE','ORDERS_CREATE','ORDERS_PAID'),
          'post_purchase':('ORDERS_PAID',), 'fulfilled':('ORDERS_FULFILLED',)}
CONNECTION = '''query AutomationCapabilities { shop { id primaryDomain { url } } currentAppInstallation { app { apiKey } accessScopes { handle } } }'''
PIXEL = 'query AutomationPixel { webPixel { id settings } }'
CREATE_PIXEL = '''mutation AutomationPixelCreate($pixel:WebPixelInput!) {
 webPixelCreate(webPixel:$pixel) { webPixel { id settings } userErrors { field message } } }'''


def verify(shop, store, env=None):
    import os
    from crm_tracking_health import callbacks, subscriptions
    env=os.environ if env is None else env
    result={'checked_at':now().isoformat(),'scopes':[],'triggers':{},'pixel':'UNVERIFIED'}
    try:
        data=shop.query(CONNECTION,{},'automation installed scopes',0,True)
        canonical=tomllib.loads((Path(__file__).parent/'shopify_customer_account/shopify.app.toml').read_text())['client_id']
        if data['currentAppInstallation']['app']['apiKey']!=canonical:raise ValueError('Wrong installed app.')
        scopes=result['scopes']=sorted(s['handle'] for s in data['currentAppInstallation']['accessScopes'])
        from crm_tracking import public_https
        from urllib.parse import urlsplit
        website=(data['shop'].get('primaryDomain') or {}).get('url')
        if public_https(website):
            parsed=urlsplit(website);result['storefront_origin']=parsed.scheme+'://'+parsed.netloc
        rows=subscriptions(shop);target=callbacks(env)
        from webhook_server import SHOPIFY_WEBHOOK_SECRET_ENV_NAMES,SHOPIFY_ADMIN_TOKEN_PREFIXES
        result['webhook_hmac_configured']=any(env.get(k,'').strip() and not env[k].strip().startswith(SHOPIFY_ADMIN_TOKEN_PREFIXES) for k in SHOPIFY_WEBHOOK_SECRET_ENV_NAMES)
        def connected(topic):
            allowed={target['crm']}
            if topic=='ORDERS_PAID':allowed.add(target['paid'])
            return any(r['topic']==topic and (r.get('apiVersion') or {}).get('handle')=='2026-04' and
                       (r.get('endpoint') or {}).get('callbackUrl','').rstrip('/') in allowed for r in rows)
        result['webhooks']={t:connected(t) for ts in TOPICS.values() for t in ts}
        for kind,topics in TOPICS.items():
            required={'read_customers'} | ({'read_orders'} if kind!='welcome' else set())
            result['triggers'][kind]='AVAILABLE' if result['webhook_hmac_configured'] and required.issubset(scopes) and all(connected(t) for t in topics) else 'UNAVAILABLE'
        if {'write_pixels','read_customer_events'}.issubset(scopes):
            try:
                pixel=shop.query(PIXEL,{},'automation app pixel',0,True).get('webPixel')
                if pixel:result.update(pixel='INSTALLED — CUSTOMER EVENTS VERIFICATION REQUIRED',pixel_id=pixel['id'])
                else:result['pixel']='NOT INSTALLED'
            except Exception:result['pixel']='NOT VERIFIED'
    except Exception:
        result['triggers']={k:'UNVERIFIED' for k in TOPICS}
    result['scope_checks']={s:'VERIFIED' if s in result['scopes'] else 'MISSING / UNVERIFIED' for s in EXPECTED_SCOPES}
    store.set_state('shopify_automation_capabilities',result)
    return result


def require(store, kind):
    state=store.state('shopify_automation_capabilities');checked=date(state.get('checked_at'))
    if not checked or now()-checked>timedelta(minutes=10) or state.get('triggers',{}).get(kind)!='AVAILABLE':
        raise ValueError('Shopify trigger is not verified. Run the automation admin diagnostic.')


def activate_pixel(shop,store,settings):
    """Explicit admin operation only, after extension and endpoint are deployed."""
    from crm_shopify_pixel import validate_settings
    validate_settings(settings)
    state=verify(shop,store)
    if not {'write_pixels','read_customer_events'}.issubset(state['scopes']):raise ValueError('Pixel scopes are unavailable.')
    # Persist intent before the remote operation so an interrupted create can
    # be recovered using the identical public configuration, never a new pixel.
    store.set_state('shopify_automation_pixel_setup',{'settings':settings})
    # Shopify's no-ID lookup is scoped to the calling app. An unavailable lookup
    # fails closed; it is never treated as proof that creation is safe.
    existing=shop.query(PIXEL,{},'automation app pixel',0,True).get('webPixel')
    if existing:
        old=existing['settings'];old=json.loads(old) if isinstance(old,str) else old
        if old!=settings:raise ValueError('Existing app pixel settings differ. Review before updating.')
        pixel=existing
    else:
        data=shop.query(CREATE_PIXEL,{'pixel':{'settings':json.dumps(settings)}},'activate automation app pixel',0,True)['webPixelCreate']
        if data.get('userErrors') or not data.get('webPixel'):raise ValueError('Shopify rejected pixel activation.')
        pixel=data['webPixel']
    store.set_state('shopify_automation_pixel',{'id':pixel['id'],'settings':settings,'activated_at':now().isoformat(),'customer_events_verified':False,'origins':list(filter(None,('null','https://'+settings['shop'],state.get('storefront_origin'))))})
    return pixel
