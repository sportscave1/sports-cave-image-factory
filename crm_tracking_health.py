"""Read-only setup verification with the OS Shopify transport, never a connector app."""
import os
from datetime import timedelta
from crm_logic import date,now
from crm_attribution_shopify import query,VISIT,complete
from scripts.register_crm_webhooks import QUERY as WEBHOOKS

SCOPES='query CrmTrackingScopes { currentAppInstallation { accessScopes { handle } } }'
DEFINITION='''query CrmAttributionDefinition { metafieldDefinitions(first:10,ownerType:ORDER,
 namespace:"sports_cave_os",key:"email_attribution") { nodes { namespace key ownerType type { name } } } }'''
JOURNEY='''query CrmTrackingJourneyCheck { orders(first:1,sortKey:CREATED_AT,reverse:true,query:"source_name:web test:false") {
 nodes { customerJourneySummary { ready firstVisit { '''+VISIT+' } lastVisit { '+VISIT+''' }
 moments(first:1) { nodes { ... on CustomerVisit { '''+VISIT+''' } } pageInfo { hasNextPage endCursor } } } } } }'''
REQUIRED=('ORDERS_CREATE','ORDERS_UPDATED','ORDERS_PAID')


def callbacks(env=None):
    env=os.environ if env is None else env
    base=(env.get('SPORTS_CAVE_WEBHOOK_BASE_URL') or env.get('CRM_PUBLIC_BASE_URL','')).rstrip('/')
    return {'crm':base+'/webhooks/shopify/crm','paid':base+'/webhooks/shopify/orders-paid'}


def subscriptions(shop):
    return complete(query(shop,WEBHOOKS,{'after':None})['webhookSubscriptions'],
                    lambda after:query(shop,WEBHOOKS,{'after':after})['webhookSubscriptions'])


def webhook_status(rows,env=None):
    target=callbacks(env);result={}
    for topic in REQUIRED:
        allowed={target['crm']}
        if topic=='ORDERS_PAID':allowed.add(target['paid'])
        same=[r for r in rows if r['topic']==topic]
        result[topic]=any((r.get('endpoint') or {}).get('callbackUrl','').rstrip('/') in allowed for r in same)
    return result


def verify(shop,store=None,env=None):
    """No mutation, registration, email, order update or database write."""
    env=os.environ if env is None else env;checks={};scopes=[];hooks=[]
    def check(name,operation):
        try:checks[name]='VERIFIED' if operation() else 'FAILED'
        except Exception:checks[name]='UNAVAILABLE'
    try:
        scopes=sorted(s['handle'] for s in query(shop,SCOPES,{})['currentAppInstallation']['accessScopes'])
        checks['Shopify credentials']='VERIFIED'
    except Exception:checks['Shopify credentials']='UNAVAILABLE'
    for scope in ('read_orders','write_orders'):checks[scope]='VERIFIED' if scope in scopes else 'MISSING' if checks['Shopify credentials']=='VERIFIED' else 'UNVERIFIED'
    checks['read_all_orders (historical)']='VERIFIED' if 'read_all_orders' in scopes else 'NOT AVAILABLE — recent window only' if checks['Shopify credentials']=='VERIFIED' else 'UNVERIFIED'
    check('Shopify Journey API',lambda:bool(query(shop,JOURNEY,{})['orders']['nodes']))
    check('Order attribution field',lambda:any(d['ownerType']=='ORDER' and d['type']['name']=='json' and d['namespace']=='sports_cave_os' and d['key']=='email_attribution'
        for d in query(shop,DEFINITION,{})['metafieldDefinitions']['nodes']))
    try:
        hooks=subscriptions(shop)
        checks.update({topic:'VERIFIED' if valid else 'MISSING / WRONG CALLBACK' for topic,valid in webhook_status(hooks,env).items()})
    except Exception:checks.update({topic:'UNAVAILABLE' for topic in REQUIRED})
    checks['Resend webhook configuration']='CONFIGURED — event proof required' if env.get('CRM_RESEND_WEBHOOK_SECRET') else 'MISSING'
    from crm_tracking import campaign_link,validate_links,send_identity
    identity='00000000-0000-0000-0000-000000000001';sid=send_identity(identity)
    link=campaign_link('https://www.sportscaveshop.com/products/check','check','check',test=False,campaign_id=identity,send_id=sid)
    checks['Tracking URL decorator']='VERIFIED' if not validate_links('<a href="'+link+'">Check</a>',identity,sid) else 'FAILED'
    health=observations(store) if store else {}
    checks['Attribution reconcile']=health.get('Attribution reconcile','UNVERIFIED')
    checks['Resend webhook']=health.get('Resend webhook','UNVERIFIED')
    checks['Shopify order webhook']=health.get('Shopify order webhook','UNVERIFIED')
    checks['Shopify mirror enabled']='CONFIGURED' if env.get('CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED','').lower()=='true' else 'DISABLED'
    blocking=[v for k,v in checks.items() if k!='read_all_orders (historical)']
    ready=all(v.startswith(('VERIFIED','RECENT','CONFIGURED')) for v in blocking)
    return {'status':'READY' if ready else 'NOT READY','checked_at':now().isoformat(),'checks':checks,'scopes':scopes,
            'webhooks':[{'topic':r['topic'],'callback':(r.get('endpoint') or {}).get('callbackUrl')} for r in hooks if r['topic'] in REQUIRED]}


def observations(store):
    """Configuration never implies healthy delivery; use real persisted events."""
    if not store:return {}
    try:
        events=store.q("""SELECT (SELECT max(received_at) FROM crm_webhook_events WHERE provider='shopify' AND topic IN ('orders/create','orders/updated','orders/paid')) AS shopify,
          (SELECT max(received_at) FROM crm_delivery_events) AS resend""",one=True)
        def freshness(value,minutes):
            stamp=date(value)
            if not stamp:return 'NEVER RECEIVED'
            return ('RECENT · ' if now()-timedelta(minutes=minutes)<=stamp<=now()+timedelta(minutes=1) else 'STALE · ')+stamp.isoformat()
        journey=store.state('email_journey_health');scan=store.state('email_attribution_scan')
        return {'Resend webhook':freshness(events['resend'],1440),'Shopify order webhook':freshness(events['shopify'],1440),
                'Shopify Journey API':'ERROR' if journey.get('error') else freshness(journey.get('verified_at'),1440),
                'Attribution reconcile':'ERROR' if scan.get('error') else freshness(store.state('email_reconcile_health').get('last_run'),10)}
    except Exception:return {'Attribution reconcile':'UNAVAILABLE — database check failed'}


def control(shop,store,user):
    import os_accounts
    if not os_accounts.is_admin(user):return
    import streamlit as st
    with st.popover('Tracking health',help='Read-only tracking setup and service evidence'):
        # Work executes only on explicit opening, never while composing a campaign.
        if st.button('Verify tracking setup',key='verify_email_tracking'):
            st.session_state['email_tracking_verification']=verify(shop,store)
        report=st.session_state.get('email_tracking_verification')
        if report:
            st.caption(report['status']+' · '+report['checked_at'])
            for label,value in report['checks'].items():st.caption(label+' · '+value)
        else:st.caption('Verify checks the OS Shopify connection and persisted service evidence. It sends nothing.')
