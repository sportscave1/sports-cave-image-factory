"""Admin/worker diagnostics use the Sports Cave credentials, not connector scopes."""
import json
from datetime import timedelta
from pathlib import Path
import tomllib
from crm_logic import date, now

EXPECTED_SCOPES = ('read_customers','read_orders','write_pixels','read_customer_events','write_marketing_events')
TOPICS = {'welcome':('CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE',),
          'abandoned':('CHECKOUTS_CREATE','CHECKOUTS_UPDATE','ORDERS_CREATE','ORDERS_PAID'),
          'post_purchase':('ORDERS_PAID',), 'fulfilled':('ORDERS_FULFILLED',)}
CONNECTION = '''query AutomationCapabilities { shop { id primaryDomain { url } } currentAppInstallation { app { apiKey } accessScopes { handle } } }'''
PIXEL = 'query AutomationPixel { webPixel { id settings } }'
CREATE_PIXEL = '''mutation AutomationPixelCreate($pixel:WebPixelInput!) {
 webPixelCreate(webPixel:$pixel) { webPixel { id settings } userErrors { field message } } }'''


def verify(shop, store, env=None,*,persist=True):
    import os
    from crm_tracking_health import callbacks, subscriptions
    env=os.environ if env is None else env
    result={'scopes':[],'triggers':{},'pixel':'UNVERIFIED','checks':{},'webhooks':{},'webhook_details':{}}
    checks=result['checks'];identity=False;scopes=[];scopes_read=False
    try:
        data=shop.query(CONNECTION,{},'automation installed scopes',0,True)
        canonical=tomllib.loads((Path(__file__).parent/'shopify_customer_account/shopify.app.toml').read_text())['client_id']
        identity=data['currentAppInstallation']['app']['apiKey']==canonical
        checks['App identity']='VERIFIED' if identity else 'MISMATCH'
        scopes=result['scopes']=sorted(s['handle'] for s in data['currentAppInstallation']['accessScopes'])
        scopes_read=True;checks['Shopify API']='VERIFIED'
        from crm_tracking import public_https
        from urllib.parse import urlsplit
        website=(data['shop'].get('primaryDomain') or {}).get('url')
        if public_https(website):
            parsed=urlsplit(website);result['storefront_origin']=parsed.scheme+'://'+parsed.netloc
    except Exception as exc:
        checks['Shopify API']='UNAVAILABLE ('+type(exc).__name__+')'
        checks.setdefault('App identity','UNVERIFIED')
    for scope in ('read_customers','read_orders'):
        checks[scope]='VERIFIED' if scope in scopes else 'MISSING' if scopes_read else 'UNVERIFIED'
    from webhook_server import SHOPIFY_WEBHOOK_SECRET_ENV_NAMES,SHOPIFY_ADMIN_TOKEN_PREFIXES
    secrets=[env.get(k,'').strip() for k in SHOPIFY_WEBHOOK_SECRET_ENV_NAMES if env.get(k,'').strip()]
    result['webhook_hmac_configured']=any(not value.startswith(SHOPIFY_ADMIN_TOKEN_PREFIXES) for value in secrets)
    checks['Webhook HMAC']='CONFIGURED' if result['webhook_hmac_configured'] else 'MALFORMED — Admin API token is not a webhook secret' if secrets else 'MISSING'
    target=callbacks(env)
    from crm_tracking import public_https
    checks['Callback configuration']='VERIFIED' if all(public_https(url) for url in target.values()) else 'MISSING / INVALID HTTPS BASE URL'
    rows=None
    try:rows=subscriptions(shop)
    except Exception as exc:checks['Webhook API']='UNAVAILABLE ('+type(exc).__name__+')'
    for topic in sorted({t for ts in TOPICS.values() for t in ts}):
        allowed={target['crm']} | ({target['paid']} if topic=='ORDERS_PAID' else set())
        same=[r for r in (rows or []) if r.get('topic')==topic]
        callback=[r for r in same if (r.get('endpoint') or {}).get('callbackUrl','').rstrip('/') in allowed]
        good=checks['Callback configuration']=='VERIFIED' and any((r.get('apiVersion') or {}).get('handle')=='2026-04' for r in callback)
        status='VERIFIED' if good else 'UNAVAILABLE' if rows is None else 'MISSING' if not same else 'CALLBACK MISMATCH' if not callback else 'API VERSION MISMATCH — requires 2026-04'
        result['webhooks'][topic]=good;checks[topic]=status
        # Public diagnostics never persist query strings or arbitrary endpoint credentials.
        from urllib.parse import urlsplit,urlunsplit
        def public_callback(row):
            value=(row.get('endpoint') or {}).get('callbackUrl','')
            if not public_https(value):return 'Invalid HTTPS callback'
            parsed=urlsplit(value)
            return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
        result['webhook_details'][topic]={'status':status,'subscriptions':[
          {'callback':public_callback(r),'api_version':str((r.get('apiVersion') or {}).get('handle') or 'Unknown')[:30]} for r in same[:20]]}
    result['reasons']={}
    for kind,topics in TOPICS.items():
        required=('App identity','Shopify API','read_customers',*(() if kind=='welcome' else ('read_orders',)),'Webhook HMAC','Callback configuration',*topics)
        failures=[name+': '+checks[name] for name in required if checks[name] not in ('VERIFIED','CONFIGURED')]
        result['reasons'][kind]=failures
        result['triggers'][kind]='AVAILABLE' if not failures else 'UNVERIFIED' if not scopes_read or rows is None else 'UNAVAILABLE'
    if identity and {'write_pixels','read_customer_events'}.issubset(scopes):
        try:
            pixel=shop.query(PIXEL,{},'automation app pixel',0,True).get('webPixel')
            if pixel:result.update(pixel='INSTALLED — CUSTOMER EVENTS VERIFICATION REQUIRED',pixel_id=pixel['id'])
            else:result['pixel']='NOT INSTALLED'
        except Exception:result['pixel']='NOT VERIFIED'
    result['scope_checks']={s:'VERIFIED' if s in result['scopes'] else 'MISSING / UNVERIFIED' for s in EXPECTED_SCOPES}
    result['checked_at']=now().isoformat()
    if persist:store.set_state('shopify_automation_capabilities',result)
    return result


def require(store, kind):
    failures=blocking_reasons(store.state('shopify_automation_capabilities'),kind)
    if failures:raise ValueError('Shopify '+kind.replace('_',' ')+' trigger is not ready: '+'; '.join(failures)+'. Run diagnostic in the automation editor.')


def blocking_reasons(state,kind):
    checked=date(state.get('checked_at'));at=now()
    if not checked:return ['Diagnostic missing']
    if checked>at+timedelta(minutes=1):return ['Diagnostic timestamp is invalid']
    if at-checked>timedelta(minutes=10):return ['Diagnostic expired (older than 10 minutes)']
    if state.get('triggers',{}).get(kind)!='AVAILABLE':
        return state.get('reasons',{}).get(kind) or ['Trigger verification unavailable']
    return []


def refresh_due(state,at):
    checked=date(state.get('checked_at'))
    return not checked or checked>at+timedelta(minutes=1) or at-checked>=timedelta(minutes=5)


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
