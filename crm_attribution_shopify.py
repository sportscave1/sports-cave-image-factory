"""Read-only order evidence through the existing Shopify transport and pagination."""
from crm_logic import date

PAGE='pageInfo { hasNextPage endCursor }'
MONEY='{ shopMoney { amount currencyCode } }'
VISIT='occurredAt landingPage source sourceDescription utmParameters { source medium campaign content }'
LINE='id title quantity currentQuantity product { id } originalTotalSet '+MONEY+' discountAllocations { allocatedAmountSet '+MONEY+' }'
REFUND_LINE='quantity lineItem { id } subtotalSet '+MONEY
ORDER='''query CrmEmailOrder($id:ID!) { order(id:$id) {
 id name createdAt updatedAt cancelledAt fullyPaid test customer { id } netPaymentSet '''+MONEY+'''
 customerJourneySummary { ready firstVisit { '''+VISIT+''' } lastVisit { '''+VISIT+''' }
 moments(first:100) { nodes { ... on CustomerVisit { '''+VISIT+' } } '+PAGE+''' } }
 lineItems(first:100) { nodes { '''+LINE+' } '+PAGE+''' }
 refunds { id refundLineItems(first:100) { nodes { '''+REFUND_LINE+' } '+PAGE+''' } }
 } }'''
LINES='query CrmEmailOrderLines($id:ID!,$after:String) { order(id:$id) { lineItems(first:100,after:$after) { nodes { '+LINE+' } '+PAGE+' } } }'
REFUNDS='query CrmEmailRefundLines($id:ID!,$after:String) { node(id:$id) { ... on Refund { refundLineItems(first:100,after:$after) { nodes { '+REFUND_LINE+' } '+PAGE+' } } } }'
MOMENTS='query CrmEmailVisits($id:ID!,$after:String) { order(id:$id) { customerJourneySummary { moments(first:100,after:$after) { nodes { ... on CustomerVisit { '+VISIT+' } } '+PAGE+' } } } }'
UPDATED='query CrmEmailUpdatedOrders($query:String!,$after:String) { orders(first:10,query:$query,sortKey:UPDATED_AT,after:$after) { nodes { id } '+PAGE+' } }'

def query(shop,document,variables):
    return shop.query(document,variables,'email order attribution (read_orders)',0,True)

def complete(connection,fetch):
    rows=list(connection.get('nodes') or []);seen=set()
    while connection['pageInfo'].get('hasNextPage'):
        cursor=connection['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Attribution pagination did not advance.')
        seen.add(cursor);connection=fetch(cursor);rows.extend(connection['nodes'])
    return rows

def order(shop,identity):
    result=query(shop,ORDER,{'id':identity}).get('order')
    if not result:return None
    result['lineItems']['nodes']=complete(result['lineItems'],lambda after:query(shop,LINES,{'id':identity,'after':after})['order']['lineItems'])
    journey=result.get('customerJourneySummary') or {}
    if journey.get('moments'):
        journey['moments']['nodes']=complete(journey['moments'],lambda after:query(shop,MOMENTS,{'id':identity,'after':after})['order']['customerJourneySummary']['moments'])
    for refund in result['refunds']:
        refund['refundLineItems']['nodes']=complete(refund['refundLineItems'],lambda after:query(shop,REFUNDS,{'id':refund['id'],'after':after})['node']['refundLineItems'])
    return result

def updated(shop,start,end,after=None):
    expression='updated_at:>='+date(start).isoformat()+' updated_at:<'+date(end).isoformat()
    return query(shop,UPDATED,{'query':expression,'after':after})['orders']
