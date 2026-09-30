"""Deterministic production attribution in the existing order-association table."""
import json
import logging
import os
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
    """Exact Shopify campaign evidence outranks matching-recipient click evidence."""
    created=date(order.get('createdAt'));journey=order.get('customerJourneySummary') or {}
    if not created or order.get('test') is not False or not journey.get('ready'):return None
    window=timedelta(days=days or window_days())
    candidates={c['campaign_key']:c for c in campaigns if c.get('campaign_key') and c['status'] in ('SENDING','SENT')}
    def within(value,campaign=None):
        at=date(value)
        return bool(at and timedelta(0)<=created-at<=window and (not campaign or
            (date(campaign.get('sending_started_at')) and at>=date(campaign['sending_started_at']))))
    visits=[journey.get('firstVisit') or {},journey.get('lastVisit') or {},*((journey.get('moments') or {}).get('nodes') or [])]
    visits=[v for v in visits if within(v.get('occurredAt')) and tracking(v) is not None]
    direct=[(v,candidates[tracking(v)]) for v in visits if tracking(v) in candidates and within(v.get('occurredAt'),candidates[tracking(v)])]
    customer=(order.get('customer') or {}).get('id')
    valid_clicks=[]
    for click in clicks:
        campaign=candidates.get(click.get('campaign_key'))
        if (not customer or click.get('shopify_customer_id')!=customer or not campaign or
                not within(click.get('occurred_at'),campaign)):continue
        if tracking({'landingPage':click.get('clicked_url')})!=campaign['campaign_key']:continue
        valid_clicks.append((click,campaign))
    if direct:
        visit,campaign=max(direct,key=lambda pair:(date(pair[0]['occurredAt']),pair[1]['campaign_key']))
        times=[date(c['occurred_at']) for c,p in valid_clicks if p['id']==campaign['id']]
        return {'campaign':campaign,'method':'SHOPIFY_UTM','visit_at':date(visit['occurredAt']),'click_at':max(times) if times else None}
    # Supporting Shopify email-source evidence must correspond to the selected
    # click (or carry no campaign); an explicitly different campaign is not a match.
    eligible=[(c,p,v) for c,p in valid_clicks for v in visits if tracking(v) in ('',p['campaign_key'])
              and date(v['occurredAt'])>=date(c['occurred_at'])-timedelta(minutes=5)]
    if not eligible:return None
    click,campaign,visit=max(eligible,key=lambda triple:(date(triple[0]['occurred_at']),triple[1]['campaign_key']))
    return {'campaign':campaign,'method':'EMAIL_CLICK_PLUS_UTM','visit_at':date(visit['occurredAt']),'click_at':date(click['occurred_at'])}

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
            'title':line['title'],'quantity':line['currentQuantity'],'revenue':str(revenue) if revenue is not None else None})
    return rows

def record(store,order):
    """Idempotent single-order upsert. No marketing delivery or customer mutation."""
    prior=store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
    campaigns=store.q("SELECT id,name,campaign_key,campaign_send_id,status,sending_started_at FROM crm_campaigns WHERE campaign_key IS NOT NULL AND status IN ('SENDING','SENT')")
    clicks=store.q('''SELECT c.campaign_key,s.shopify_customer_id,e.occurred_at,e.clicked_url
      FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id JOIN crm_campaigns c ON c.id=s.campaign_id
      WHERE e.event_type='email.clicked' AND NOT s.test_send AND s.shopify_customer_id=%s
        AND e.occurred_at<=%s AND e.occurred_at>=%s''',
      ((order.get('customer') or {}).get('id'),date(order['createdAt']),date(order['createdAt'])-timedelta(days=window_days())))
    match=choose(order,campaigns,clicks)
    total,currency=amount(order['netPaymentSet'])
    eligible=order.get('fullyPaid') is True and order.get('test') is False and not order.get('cancelledAt')
    lines=products(order,currency)
    if not match:
        # Shopify can temporarily rebuild its journey. Still reconcile refunds,
        # while retaining previously established evidence until a ready response.
        ready=(order.get('customerJourneySummary') or {}).get('ready')
        if prior and prior.get('method'):
            store.q('''UPDATE crm_order_attribution SET amount=%s,currency=%s,products=%s::jsonb,
              eligible=%s,checked_at=now(),source_updated_at=%s WHERE shopify_order_id=%s
              AND (source_updated_at IS NULL OR source_updated_at<=%s)''',
              (str(max(total,0)),currency,json.dumps(lines),bool(eligible and prior['eligible'] and not ready),
               date(order.get('updatedAt') or order['createdAt']),order['id'],date(order.get('updatedAt') or order['createdAt'])))
        return None
    campaign=match['campaign']
    written=store.q('''INSERT INTO crm_order_attribution(shopify_order_id,campaign_id,campaign_key,campaign_send_id,
      order_name,customer_id,order_created_at,visit_at,click_at,amount,currency,eligible,model,method,products,source_updated_at)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
      ON CONFLICT(shopify_order_id) DO UPDATE SET campaign_id=excluded.campaign_id,campaign_key=excluded.campaign_key,
      campaign_send_id=excluded.campaign_send_id,order_name=excluded.order_name,customer_id=excluded.customer_id,
      order_created_at=excluded.order_created_at,visit_at=excluded.visit_at,click_at=excluded.click_at,
      amount=excluded.amount,currency=excluded.currency,eligible=excluded.eligible,model=excluded.model,
      method=excluded.method,products=excluded.products,checked_at=now(),source_updated_at=excluded.source_updated_at,
      mirror_status=CASE WHEN crm_order_attribution.campaign_id=excluded.campaign_id THEN crm_order_attribution.mirror_status ELSE 'NOT_REQUESTED' END
      WHERE crm_order_attribution.source_updated_at IS NULL OR crm_order_attribution.source_updated_at<=excluded.source_updated_at
      RETURNING shopify_order_id''',
      (order['id'],campaign['id'],campaign['campaign_key'],campaign['campaign_send_id'],order.get('name'),
       (order.get('customer') or {}).get('id'),date(order['createdAt']),match['visit_at'],match['click_at'],
       str(max(total,0)),currency,bool(eligible),'sports_cave_email_'+str(window_days())+'d',match['method'],json.dumps(lines),date(order.get('updatedAt') or order['createdAt'])),True)
    return match if written else None

def mirror(store,order,match):
    """Optional scoped metadata mirror. Local attribution never depends on it."""
    if not match or os.getenv('CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED','').lower()!='true':return
    campaign=match['campaign'];payload={'source':'Sports Cave OS Email','campaign_id':str(campaign['id']),
        'campaign_name':campaign['name'],'campaign_send_id':str(campaign['campaign_send_id']),'attribution_method':match['method']}
    try:
        from shopify_sync import fetch_metafields,metafields_set
        existing=fetch_metafields(order['id'],namespace='sports_cave_os')
        found=next((m for m in existing['metafields'] if m['key']=='email_attribution'),None)
        if found and json.loads(found['value'])==payload:status='SYNCED'
        else:
            # Write only this namespace/key; compareDigest protects concurrent edits.
            if found and json.loads(found['value']).get('source')!='Sports Cave OS Email':raise ValueError('Metafield belongs to another source.')
            result=metafields_set([{'ownerId':order['id'],'namespace':'sports_cave_os','key':'email_attribution',
                'type':'json','value':json.dumps(payload),'compareDigest':found.get('compareDigest') if found else None}])
            status='SYNCED' if result['count']==1 else 'UNAVAILABLE'
    except Exception:
        status='UNAVAILABLE'
        logging.getLogger(__name__).warning('crm_attribution_mirror_unavailable')
    store.q('UPDATE crm_order_attribution SET mirror_status=%s WHERE shopify_order_id=%s',(status,order['id']))

def reconcile(store,shop,clock=now):
    """Bounded background work; retries recent journeys/clicks and all updated orders.

    One logical scan every 15 minutes, two full orders per tick. A rolling window
    catches late journeys/webhooks. Persisted watermark also catches older refunds.
    """
    active=store.q("SELECT min(sending_started_at) AS first FROM crm_campaigns WHERE campaign_key IS NOT NULL AND status IN ('SENDING','SENT')",one=True)['first']
    if not active:return
    key='email_attribution_scan';state=store.state(key);at=clock()
    if date(state.get('next_at')) and at<date(state['next_at']):return
    state.pop('error',None)
    from crm_attribution_shopify import updated,order as fetch_order
    if not state.get('end'):
        start=max(date(active),min(date(state.get('watermark')) or date(active),at-timedelta(days=window_days()+1)))
        state.update(start=start.isoformat(),end=at.isoformat(),cursor=None,pending=[])
    if not state.get('pending'):
        page=updated(shop,state['start'],state['end'],state.get('cursor'))
        cursor=page['pageInfo'].get('endCursor');more=page['pageInfo'].get('hasNextPage')
        if more and (not cursor or cursor==state.get('cursor')):raise ValueError('Attribution order pagination did not advance.')
        state.update(pending=[o['id'] for o in page['nodes']],cursor=cursor,more=more)
    for identity in state['pending'][:2]:
        value=fetch_order(shop,identity)
        try:
            if value:mirror(store,value,record(store,value))
        except (ValueError,KeyError,TypeError,InvalidOperation) as exc:
            # One malformed order cannot starve all later orders. The rolling
            # reconciliation window retries it without logging customer content.
            logging.getLogger(__name__).warning('crm_attribution_evidence_incomplete type=%s',type(exc).__name__)
        state['pending'].remove(identity)
        store.set_state(key,state)
    if not state['pending'] and not state['more']:
        state={'watermark':state['end'],'next_at':(at+timedelta(minutes=15)).isoformat()}
    store.set_state(key,state)
