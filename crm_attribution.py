"""Shopify last recorded visit association; never claims incremental revenue."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit,parse_qs
from crm_logic import date


def association(order,campaign_key):
    journey=order.get('customerJourneySummary')
    if not journey or not journey.get('ready'):return None,'journey_unavailable'
    visit=journey.get('lastVisit') or {};utm=visit.get('utmParameters') or {}
    if (utm.get('source'),utm.get('medium'),utm.get('campaign'))!=('sports_cave','email',campaign_key):return None,'no_matching_last_visit'
    landing=visit.get('landingPage')
    # Without the landing URL we cannot reliably exclude internal test links.
    if not isinstance(landing,str):return None,'journey_unavailable'
    if parse_qs(urlsplit(landing).query).get('sc_test')==['1']:return None,'internal_test'
    created=date(order.get('createdAt'));visited=date(visit.get('occurredAt'))
    if not created or not visited or not timedelta(0)<=created-visited<=timedelta(days=30):return None,'outside_30d_window'
    money=(order.get('netPaymentSet') or {}).get('shopMoney') or {}
    try:amount=Decimal(money['amount'])
    except (KeyError,InvalidOperation,TypeError):return None,'revenue_unavailable'
    if not amount.is_finite() or amount<0 or not isinstance(money.get('currencyCode'),str):return None,'revenue_unavailable'
    eligible=order.get('fullyPaid') is True and not order.get('cancelledAt') and order.get('test') is False
    return {'order_id':order['id'],'campaign_key':campaign_key,'created_at':created,'visit_at':visited,
            'amount':str(amount),'currency':money['currencyCode'],'eligible':eligible},'associated' if eligible else 'not_paid_or_canceled'


def refresh_page(store,shop,campaign,start,end,after=None):
    # Read-only Shopify; only minimal association facts enter Sports Cave storage.
    page=shop.campaign_orders(start,end,after);reasons={}
    for order in page['nodes']:
        row,reason=association(order,campaign['document'].get('campaign_key',''))
        reasons[reason]=reasons.get(reason,0)+1
        if row:
            store.q('INSERT INTO crm_order_attribution(shopify_order_id,campaign_id,campaign_key,order_created_at,visit_at,amount,currency,eligible) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(shopify_order_id) DO UPDATE SET campaign_id=excluded.campaign_id,campaign_key=excluded.campaign_key,order_created_at=excluded.order_created_at,visit_at=excluded.visit_at,amount=excluded.amount,currency=excluded.currency,eligible=excluded.eligible,checked_at=now() WHERE crm_order_attribution.method IS NULL',
                    (row['order_id'],campaign['id'],row['campaign_key'],row['created_at'],row['visit_at'],row['amount'],row['currency'],row['eligible']))
        else:
            # An order losing its association cannot retain stale revenue.
            store.q('UPDATE crm_order_attribution SET eligible=false,checked_at=now() WHERE shopify_order_id=%s AND campaign_id=%s AND method IS NULL',(order['id'],campaign['id']))
    more=page['pageInfo'].get('hasNextPage');cursor=page['pageInfo'].get('endCursor')
    if more and (not cursor or cursor==after):raise ValueError('Order pagination did not advance.')
    return {'cursor':cursor if more else None,'complete':not more,'reasons':reasons,'scanned':len(page['nodes'])}
