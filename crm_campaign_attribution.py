"""Deterministic production attribution in the existing order-association table."""
import json
import logging
import os
import re
from datetime import timedelta
from decimal import Decimal,InvalidOperation
from urllib.parse import parse_qs,urlsplit
from crm_logic import date,now

SOURCE='sports_cave_os'

def window_days():
    try:return max(1,min(90,int(os.getenv('EMAIL_ATTRIBUTION_WINDOW_DAYS','7'))))
    except ValueError:return 7

def tracking(visit):
    landing=visit.get('landingPage') or ''
    try:query=parse_qs(urlsplit(landing).query)
    except ValueError:return None
    # A landing URL is required to distinguish internal-test links reliably.
    if not landing or query.get('sc_test')==['1']:return None
    utm=visit.get('utmParameters') or {}
    source=utm.get('source') or (query.get('utm_source') or [''])[0]
    medium=utm.get('medium') or (query.get('utm_medium') or [''])[0]
    if (source,medium)!=(SOURCE,'email'):return None
    return utm.get('campaign') or (query.get('utm_campaign') or query.get('sc_campaign_id') or [''])[0]

def choose(order,campaigns,clicks,days=None):
    """Shopify exact UTM first; otherwise real recipient clicks only, never opens."""
    created=date(order.get('createdAt'));journey=order.get('customerJourneySummary')
    if not created or order.get('test') is not False:return None
    # Explicitly delayed is pending, not privacy loss. Wait for Shopify first.
    if journey and journey.get('ready') is False:return None
    journey=journey or {};window=timedelta(days=days or window_days())
    candidates={};by_key={}
    from crm_tracking import send_identity
    for c in campaigns:
        if c['status'] not in ('SENDING','SENT'):continue
        key=str(c.get('campaign_send_id') or c.get('campaign_key') or '')
        if key:candidates[key]=c
        by_key[c.get('campaign_key')]=c
        # Read compatibility for emails sent before send-ID tracking was deployed.
        try:legacy=str(c.get('campaign_send_id'))!=send_identity(c['id'])
        except (ValueError,TypeError):legacy=True
        if legacy and c.get('campaign_key'):candidates[c['campaign_key']]=c
    def within(value,campaign=None):
        at=date(value)
        return bool(at and timedelta(0)<=created-at<=window and (not campaign or
            (date(campaign.get('sending_started_at')) and at>=date(campaign['sending_started_at']))))
    visits=[journey.get('firstVisit') or {},journey.get('lastVisit') or {},*((journey.get('moments') or {}).get('nodes') or [])]
    visits=[v for v in visits if within(v.get('occurredAt'))]
    direct=[(v,candidates[tracking(v)]) for v in visits if tracking(v) in candidates and within(v.get('occurredAt'),candidates[tracking(v)])]
    customer=(order.get('customer') or {}).get('id');valid=[]
    for click in clicks:
        campaign=by_key.get(click.get('campaign_key'))
        if not customer or click.get('shopify_customer_id')!=customer or not campaign or not within(click.get('occurred_at'),campaign):continue
        url=click.get('clicked_url') or '';key=tracking({'landingPage':url})
        if not key or candidates.get(key,{}).get('id')!=campaign['id']:continue
        params=parse_qs(urlsplit(url).query)
        if key==str(campaign.get('campaign_send_id')) and (params.get('sc_campaign_id')!=[str(campaign['id'])] or params.get('sc_campaign_send_id')!=[key]):continue
        valid.append((click,campaign))
    if direct:
        visit,campaign=max(direct,key=lambda pair:(date(pair[0]['occurredAt']),str(pair[1]['id'])))
        related=[c for c,p in valid if p['id']==campaign['id']]
        click=max(related,key=lambda c:date(c['occurred_at'])) if related else None
        return {'campaign':campaign,'method':'SHOPIFY_UTM_EXACT','confidence':'CONFIRMED','visit':visit,
                'visit_at':date(visit['occurredAt']),'click_at':date(click['occurred_at']) if click else None,
                'first_click_at':min((date(c['occurred_at']) for c in related),default=None),'click':click}
    # A complete journey with another identified campaign is contradictory evidence.
    # Empty/missing UTM visits are incomplete attribution evidence, not proof of no click.
    if any((v.get('utmParameters') or {}).get('campaign') or tracking(v) for v in visits):return None
    if not valid:return None
    click,campaign=max(valid,key=lambda pair:(date(pair[0]['occurred_at']),str(pair[1]['id'])))
    related=[c for c,p in valid if p['id']==campaign['id']]
    return {'campaign':campaign,'method':'RESEND_CLICK_MATCH','confidence':'SUPPORTED','visit':{},'visit_at':None,
            'click_at':date(click['occurred_at']),'first_click_at':min(date(c['occurred_at']) for c in related),'click':click}


def amount(bag,currency=None):
    money=(bag or {}).get('shopMoney') or {};value=Decimal(money['amount'])
    if not value.is_finite() or (currency and money['currencyCode']!=currency):raise ValueError('Inconsistent Shopify revenue evidence.')
    return value,money['currencyCode']

def products(order,currency):
    refunds={}
    for refund in order.get('refunds') or []:
        for line in refund['refundLineItems']['nodes']:
            identity=line['lineItem']['id'];total,qty=refunds.get(identity,(Decimal(0),0))
            refunds[identity]=(total+amount(line['subtotalSet'],currency)[0],qty+line['quantity'])
    rows=[]
    for line in (order.get('lineItems') or {}).get('nodes') or []:
        refunded,returned=refunds.get(line['id'],(Decimal(0),0))
        gross=amount(line['originalTotalSet'],currency)[0]
        discounts=sum((amount(d['allocatedAmountSet'],currency)[0] for d in line['discountAllocations']),Decimal(0))
        # Removed order-edit quantities lack an exact remaining line total here.
        # Keep units, but never invent a proportional revenue allocation.
        revenue=max(Decimal(0),gross-discounts-refunded) if line['currentQuantity']==line['quantity']-returned else None
        rows.append({'product_id':(line.get('product') or {}).get('id') or line['id'],
            'title':line['title'],'quantity':line['currentQuantity'],'purchased_quantity':line['quantity'],
            'refunded_quantity':returned,'revenue':str(revenue) if revenue is not None else None})
    return rows

def schedule_order(store,identity):
    """Durable work marker. Webhook retries cannot create duplicate conversions."""
    store.q("""INSERT INTO crm_order_attribution(shopify_order_id,attribution_status,retry_at)
      VALUES(%s,'UNCHECKED',now()) ON CONFLICT(shopify_order_id) DO UPDATE SET retry_at=now()""",(identity,))


def evidence(order,match):
    from crm_tracking import event_link
    visit=match.get('visit') or {};click=match.get('click') or {};campaign=match['campaign']
    landing=event_link(visit.get('landingPage')) or event_link(click.get('clicked_url'))
    params=parse_qs(urlsplit(landing or '').query);utm=visit.get('utmParameters') or {}
    clicked=match.get('click_at');ordered=date(order['createdAt'])
    return {'campaign_name':campaign['name'],'confidence':match.get('confidence','CONFIRMED'),
      'recipient_send_id':str(click['send_id']) if click.get('send_id') else None,
      'resend_message_id':click.get('provider_email_id'),
      'first_click_at':match['first_click_at'].isoformat() if match.get('first_click_at') else None,
      'last_qualifying_click_at':clicked.isoformat() if clicked else None,
      'shopify_visit_id':visit.get('id'),'shopify_visit_occurred_at':visit.get('occurredAt'),
      'journey_ready':(order.get('customerJourneySummary') or {}).get('ready'),
      'landing_page':landing,'source':visit.get('source'),'source_description':visit.get('sourceDescription'),
      **{'utm_'+k:utm.get(k) or (params.get('utm_'+k) or [None])[0] for k in ('source','medium','campaign','content','term')},
      'time_to_purchase_seconds':int((ordered-clicked).total_seconds()) if clicked else None,
      'attribution_window_days':window_days()}


def record(store,order):
    """Idempotent single-order ledger: evidence survives outages and refunds."""
    prior=store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
    updated=date(order.get('updatedAt') or order['createdAt'])
    if prior and date(prior.get('source_updated_at')) and date(prior['source_updated_at'])>updated:return None
    campaigns=store.q("SELECT id,name,campaign_key,campaign_send_id,status,sending_started_at FROM crm_campaigns WHERE campaign_key IS NOT NULL AND status IN ('SENDING','SENT')")
    clicks=store.q("""SELECT c.campaign_key,s.id AS send_id,s.provider_email_id,s.shopify_customer_id,e.occurred_at,e.clicked_url
      FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id JOIN crm_campaigns c ON c.id=s.campaign_id
      WHERE e.event_type='email.clicked' AND NOT s.test_send AND s.shopify_customer_id=%s
        AND e.occurred_at<=%s AND e.occurred_at>=%s""",
      ((order.get('customer') or {}).get('id'),date(order['createdAt']),date(order['createdAt'])-timedelta(days=window_days())))
    match=choose(order,campaigns,clicks)
    total,currency=amount(order['netPaymentSet'])
    gross=amount(order['totalReceivedSet'],currency)[0] if order.get('totalReceivedSet') else None
    refunded=amount(order['totalRefundedSet'],currency)[0] if order.get('totalRefundedSet') else None
    pending=(order.get('customerJourneySummary') or {}).get('ready') is False
    eligible=order.get('test') is False and not order.get('cancelledAt') and (order.get('fullyPaid') is True or bool(prior and prior.get('eligible')))
    if prior and prior.get('campaign_id') and not prior.get('method') and not match:
        # Older workspace associations retain their own model; this worker must
        # not erase them merely because they predate Campaigns V2 send receipts.
        store.q('''UPDATE crm_order_attribution SET amount=%s,currency=%s,products=%s::jsonb,
          eligible=%s,source_updated_at=%s,checked_at=now(),updated_at=now(),retry_at=NULL
          WHERE shopify_order_id=%s''',(str(max(total,0)),currency,json.dumps(products(order,currency)),
          bool(eligible and prior['eligible']),updated,order['id']))
        return None
    # Never downgrade established Shopify proof when Shopify temporarily omits it.
    if prior and prior.get('method') and (not match or (prior['method'] in ('SHOPIFY_UTM','SHOPIFY_UTM_EXACT') and match['method']=='RESEND_CLICK_MATCH')):
        campaign=next((c for c in campaigns if c['id']==prior['campaign_id']),None)
        if campaign:
            match={'campaign':campaign,'method':prior['method'],'visit_at':date(prior['visit_at']),
                   'click_at':date(prior['click_at']),'stored_evidence':prior.get('evidence') or {}}
    campaign=match['campaign'] if match else {}
    proof=match.get('stored_evidence') if match and 'stored_evidence' in match else evidence(order,match) if match else {'journey_ready':False if pending else (order.get('customerJourneySummary') or {}).get('ready')}
    status='PENDING_JOURNEY' if pending else 'ATTRIBUTED' if match else 'NO_MATCH'
    attempts=(prior or {}).get('attempts',0)+1
    # Short initial retry, then five/fifteen minutes; old unresolved rows get hourly checks.
    delay=60 if attempts==1 else 300 if attempts<4 else 900 if attempts<96 else 3600
    retry=now()+timedelta(seconds=delay) if pending else None
    if not match and not pending and date(order['createdAt'])>=now()-timedelta(days=window_days()+1):retry=now()+timedelta(minutes=15)
    previous_mirror=(prior or {}).get('mirror_status','PENDING')
    mirror_status=previous_mirror if prior and prior.get('campaign_id')==campaign.get('id') and prior.get('evidence')==proof else 'PENDING'
    store.q("""INSERT INTO crm_order_attribution(shopify_order_id,campaign_id,campaign_key,campaign_send_id,
      order_name,customer_id,order_created_at,visit_at,click_at,amount,currency,eligible,model,method,products,source_updated_at,
      attribution_status,evidence,gross_revenue,refund_amount,retry_at,attempts,mirror_status)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
      ON CONFLICT(shopify_order_id) DO UPDATE SET campaign_id=excluded.campaign_id,campaign_key=excluded.campaign_key,
      campaign_send_id=excluded.campaign_send_id,order_name=excluded.order_name,customer_id=excluded.customer_id,
      order_created_at=excluded.order_created_at,visit_at=excluded.visit_at,click_at=excluded.click_at,
      amount=excluded.amount,currency=excluded.currency,eligible=excluded.eligible,model=excluded.model,
      method=excluded.method,products=excluded.products,checked_at=now(),source_updated_at=excluded.source_updated_at,
      attribution_status=excluded.attribution_status,evidence=excluded.evidence,gross_revenue=excluded.gross_revenue,
      refund_amount=excluded.refund_amount,retry_at=excluded.retry_at,attempts=excluded.attempts,
      mirror_status=excluded.mirror_status,updated_at=now()
      WHERE crm_order_attribution.source_updated_at IS NULL OR crm_order_attribution.source_updated_at<=excluded.source_updated_at""",
      (order['id'],campaign.get('id'),campaign.get('campaign_key'),campaign.get('campaign_send_id'),order.get('name'),
       (order.get('customer') or {}).get('id'),date(order['createdAt']),match.get('visit_at') if match else None,match.get('click_at') if match else None,
       str(max(total,0)),currency,bool(eligible and match),'sports_cave_email_'+str(window_days())+'d',match['method'] if match else None,
       json.dumps(products(order,currency)),updated,status,json.dumps(proof),str(gross) if gross is not None else None,
       str(refunded) if refunded is not None else None,retry,attempts,mirror_status))
    return match


def mirror_payload(row):
    proof=row.get('evidence') or {}
    return {'source':'Sports Cave OS Email','campaign_id':str(row['campaign_id']),
      'campaign_send_id':str(row['campaign_send_id']),'campaign_name':proof.get('campaign_name'),
      'utm_source':'sports_cave_os','utm_medium':'email','utm_campaign':str(row['campaign_send_id']),
      'utm_content':proof.get('utm_content'),'attribution_method':row['method'],'confidence':proof.get('confidence'),
      'clicked_at':date(row['click_at']).isoformat() if row.get('click_at') else None,
      'ordered_at':date(row['order_created_at']).isoformat(),
      'seconds_click_to_purchase':proof.get('time_to_purchase_seconds')}


def mirror(store,order,match):
    """Compare-and-set non-PII mirror; never overwrite a conflicting attribution."""
    if not match:return
    row=store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
    if not row or not row.get('method'):return
    if os.getenv('CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED','').lower()!='true':
        if row.get('mirror_status')!='UPDATED':
            store.q("UPDATE crm_order_attribution SET retry_at=COALESCE(retry_at,now()+interval '1 hour') WHERE shopify_order_id=%s",(order['id'],))
        return
    payload=mirror_payload(row);error=None
    try:
        from shopify_sync import fetch_metafields,metafields_set
        existing=fetch_metafields(order['id'],namespace='sports_cave_os')
        found=next((m for m in existing['metafields'] if m['key']=='email_attribution'),None)
        old=json.loads(found['value']) if found else None
        if old==payload:status='UPDATED'
        elif old is not None and (not isinstance(old,dict) or any(old.get(k)!=payload[k] for k in ('source','campaign_id','campaign_send_id'))):
            status='FAILED';error='attribution_conflict_admin_review'
        else:
            result=metafields_set([{'ownerId':order['id'],'namespace':'sports_cave_os','key':'email_attribution',
                'type':'json','value':json.dumps(payload),'compareDigest':found.get('compareDigest') if found else None}])
            status='UPDATED' if result['count']==1 else 'FAILED'
            if status=='FAILED':error='mirror_write_not_confirmed'
    except Exception:
        status='FAILED';error='mirror_unavailable'
        logging.getLogger(__name__).warning('crm_attribution_mirror_unavailable')
    store.q("""UPDATE crm_order_attribution SET mirror_status=%s,mirror_error=%s,updated_at=now(),
      retry_at=CASE WHEN %s='FAILED' AND %s!='attribution_conflict_admin_review' THEN now()+interval '15 minutes' ELSE retry_at END
      WHERE shopify_order_id=%s""",(status,error,status,error or '',order['id']))


def reconcile(store,shop,clock=now):
    """Bounded background work; retries recent journeys/clicks and all updated orders.

    One scan every 15 minutes, at most two retries plus two scanned orders per tick.
    A bounded updated-at window includes recent changes to older refunded orders.
    """
    from crm_attribution_shopify import updated,order as fetch_order
    from crm_shopify import CapabilityUnavailable
    from crm_store import StoreUnavailable
    from psycopg import Error as DatabaseError
    at=clock()
    # Retry ledger work independently of the incremental account scan watermark.
    due=store.q('SELECT shopify_order_id FROM crm_order_attribution WHERE retry_at<=%s ORDER BY retry_at LIMIT 2',(at,))
    processed=set()
    def process(identity):
        stage='record_evidence';attempt=1;database_setup=True
        try:
            store.q("""INSERT INTO crm_order_attribution(shopify_order_id,attribution_status,retry_at)
              VALUES(%s,'UNCHECKED',now()) ON CONFLICT(shopify_order_id) DO NOTHING""",(identity,))
            prior=store.q('SELECT attempts FROM crm_order_attribution WHERE shopify_order_id=%s',(identity,),True)
            attempt=int((prior or {}).get('attempts',0))+1
            database_setup=False
            stage='fetch_order'
            value=fetch_order(shop,identity)
            if value:
                stage='record_evidence'
                match=record(store,value)
                stage='mirror'
                mirror(store,value,match)
                stage='record_evidence'
                store.set_state('email_journey_health',{'verified_at':at.isoformat()})
            else:
                stage='record_evidence'
                store.q("UPDATE crm_order_attribution SET retry_at=now()+interval '1 hour' WHERE shopify_order_id=%s",(identity,))
        except Exception as exc:
            # Only explicit evidence/parsing errors are order-local. Unknown
            # failures fail closed; source and database errors always propagate.
            individual=(not database_setup and
                        isinstance(exc,(ValueError,KeyError,TypeError,AttributeError,InvalidOperation)) and
                        not isinstance(exc,(CapabilityUnavailable,StoreUnavailable,DatabaseError)))
            safe_identity=str(identity)
            if not re.fullmatch(r'(?:gid://shopify/Order/)?[0-9]+',safe_identity):safe_identity='invalid_order_id'
            logging.getLogger(__name__).warning(
                'crm_attribution_order_failed order_id=%s stage=%s exception_type=%s retry_attempt=%s',
                safe_identity,stage,type(exc).__name__,attempt)
            store.q("UPDATE crm_order_attribution SET retry_at=now()+interval '15 minutes',attempts=attempts+1 WHERE shopify_order_id=%s",(identity,))
            if individual:return
            store.set_state('email_journey_health',{'error':'source_unavailable','checked_at':at.isoformat()})
            raise
    for row in due:
        process(row['shopify_order_id']);processed.add(row['shopify_order_id'])
    def completed():
        # Clear only after all work for this bounded pass has succeeded, including
        # due-order retries when no incremental scan is needed yet.
        scan=store.state('email_attribution_scan')
        if 'error' in scan:
            scan.pop('error')
            store.set_state('email_attribution_scan',scan)
        store.set_state('email_reconcile_health',{'last_run':at.isoformat()})
    active=store.q("SELECT min(sending_started_at) AS first FROM crm_campaigns WHERE campaign_key IS NOT NULL AND status IN ('SENDING','SENT')",one=True)['first']
    if not active:
        completed();return
    key='email_attribution_scan';state=store.state(key)
    if date(state.get('next_at')) and at<date(state['next_at']):
        # An idle backoff tick has not verified recovery from a scan outage.
        if processed or not state.get('error'):completed()
        return
    if not state.get('end'):
        start=max(date(active),at-timedelta(days=window_days()+1))
        state.update(start=start.isoformat(),end=at.isoformat(),cursor=None,pending=[])
    if not state.get('pending'):
        page=updated(shop,state['start'],state['end'],state.get('cursor'))
        cursor=page['pageInfo'].get('endCursor');more=page['pageInfo'].get('hasNextPage')
        if more and (not cursor or cursor==state.get('cursor')):raise ValueError('Attribution order pagination did not advance.')
        state.update(pending=[o['id'] for o in page['nodes']],cursor=cursor,more=more)
    for identity in state['pending'][:2]:
        if identity not in processed:process(identity)
        state['pending'].remove(identity)
        store.set_state(key,state)
    if not state['pending'] and not state['more']:
        error=state.get('error')
        state={'watermark':state['end'],'next_at':(at+timedelta(minutes=15)).isoformat()}
        if error:state['error']=error
    store.set_state(key,state)
    completed()
