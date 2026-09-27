"""Read-only, paginated Shopify authority. No connection at import time."""
import json
import logging
import threading
import time
from crm_cache import CACHE

CUSTOMER_FIELDS = '''id firstName lastName email validEmailAddress createdAt updatedAt tags
 defaultAddress { countryCodeV2 } amountSpent { amount currencyCode } numberOfOrders
 lastOrder { id name createdAt }
 emailMarketingConsent { marketingState marketingOptInLevel consentUpdatedAt }'''
PAGE = 'pageInfo { hasNextPage endCursor }'
CUSTOMERS = '''query CrmCustomers($after:String,$query:String) {
 customers(first:50,after:$after,sortKey:UPDATED_AT,reverse:true,query:$query) {
 nodes { '''+CUSTOMER_FIELDS+' } '+PAGE+' } }'
CUSTOMER = 'query CrmCustomer($id:ID!) { customer(id:$id) { '+CUSTOMER_FIELDS+' } }'
CUSTOMER_BATCH = 'query CrmCustomerBatch($ids:[ID!]!) { nodes(ids:$ids) { ... on Customer { '+CUSTOMER_FIELDS+' } } }'
ORDER_FIELDS = '''id name createdAt cancelledAt fullyPaid displayFinancialStatus
 customer { id } totalPriceSet { shopMoney { amount currencyCode } }
 lineItems(first:10) { nodes { id title variantTitle quantity product { id } }
 '''+PAGE+' }'
ORDERS = '''query CrmOrders($id:ID!,$after:String) { customer(id:$id) {
 orders(first:20,after:$after,sortKey:CREATED_AT,reverse:true) { nodes { '''+ORDER_FIELDS+' } '+PAGE+' } } }'
ORDER = 'query CrmOrder($id:ID!) { order(id:$id) { '+ORDER_FIELDS+' } }'
ORDER_LINES = '''query CrmOrderLines($id:ID!,$after:String) { order(id:$id) {
 lineItems(first:100,after:$after) { nodes { id title variantTitle quantity product { id } } '''+PAGE+' } } }'
FIRST_ORDER = '''query CrmFirstOrder($id:ID!) { customer(id:$id) {
 orders(first:1,sortKey:CREATED_AT) { nodes { id name createdAt } } } }'''
PRODUCT_FIELDS = '''id title productType tags onlineStoreUrl featuredImage { url }
 collections(first:5) { nodes { id title handle } '''+PAGE+' }'
PRODUCTS = 'query CrmProducts($ids:[ID!]!) { nodes(ids:$ids) { ... on Product { '+PRODUCT_FIELDS+' } } }'
COLLECTIONS = '''query CrmCollections($id:ID!,$after:String) { product(id:$id) {
 collections(first:100,after:$after) { nodes { id title handle } '''+PAGE+' } } }'
SEGMENTS = 'query CrmSegments($after:String) { segments(first:50,after:$after) { nodes { id name query lastEditDate } '+PAGE+' } }'
SEGMENT = 'query CrmSegment($id:ID!) { segment(id:$id) { id name query lastEditDate } }'
MEMBERS = '''query CrmMembers($id:ID,$query:String,$after:String) {
 customerSegmentMembers(segmentId:$id,query:$query,first:50,after:$after) {
 edges { node { id } } totalCount '''+PAGE+' } }'
COUNT = 'query CrmCount($query:String) { customerSegmentMembers(query:$query,first:1) { totalCount } }'
MEMBERSHIPS = 'query CrmMemberships($id:ID!,$segments:[ID!]!) { customerSegmentMembership(customerId:$id,segmentIds:$segments) { memberships { segmentId isMember } } }'
TOTAL = 'query CrmTotal { customersCount { count precision } }'
CHECKOUT_LINES_FIELDS = '''id title quantity variant { id product { id } } image { url }
 originalUnitPriceSet { shopMoney { amount currencyCode } }'''
CHECKOUT_FIELDS = '''id createdAt updatedAt completedAt abandonedCheckoutUrl customer { id }
 totalPriceSet { shopMoney { amount currencyCode } }
 lineItems(first:50) { nodes { '''+CHECKOUT_LINES_FIELDS+' } '+PAGE+' }'
CHECKOUTS = '''query CrmCheckouts($after:String,$query:String) {
 abandonedCheckouts(first:25,after:$after,sortKey:CREATED_AT,query:$query) {
 nodes { id createdAt updatedAt completedAt customer { id } } '''+PAGE+' } }'
CHECKOUT = 'query CrmCheckout($id:ID!) { node(id:$id) { ... on AbandonedCheckout { '+CHECKOUT_FIELDS+' } } }'
CHECKOUT_LINES = '''query CrmCheckoutLines($id:ID!,$after:String) { node(id:$id) {
 ... on AbandonedCheckout { lineItems(first:100,after:$after) { nodes { '''+CHECKOUT_LINES_FIELDS+' } '+PAGE+' } } } }'
_LIMIT = threading.BoundedSemaphore(2)
_COST_LOCK = threading.Lock()
_NEXT_REQUEST = 0.0

class CapabilityUnavailable(RuntimeError):
    def __init__(self, capability):
        self.capability = capability
        super().__init__(f'Shopify {capability} is temporarily unavailable. Other CRM sections remain available.')

def gid(value, kind='Customer'):
    value = str(value or '')
    if value.startswith(f'gid://shopify/{kind}/') and value.rsplit('/', 1)[-1].isdigit():
        return value
    return f'gid://shopify/{kind}/{value}' if value.isdigit() else ''

class Shopify:
    def __init__(self, transport=None, cache=CACHE, namespace=None, sleeper=time.sleep):
        self.transport, self.cache, self.sleeper = transport, cache, sleeper
        if namespace is None:
            if transport:
                namespace = f'fixture:{id(transport)}'
            else:
                from shopify_sync import get_config
                config = get_config()
                namespace = str(config.get('store_domain', config.get('shop_domain', 'configured-shop')))
        self.namespace = namespace

    def query(self, document, variables, capability, ttl=0, fresh=False):
        key = (self.namespace, document, json.dumps(variables, sort_keys=True))
        if ttl and not fresh:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        try:
            with _LIMIT:
                data = self.transport(document, variables) if self.transport else self._request(document, variables)
            return self.cache.put(key, data, ttl) if ttl and not fresh else data
        except CapabilityUnavailable:
            raise
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_shopify_unavailable capability=%s type=%s', capability, type(exc).__name__)
            raise CapabilityUnavailable(capability) from None

    def _request(self, document, variables):
        import requests
        from shopify_sync import graphql_request
        global _NEXT_REQUEST
        for attempt in range(3):
            with _COST_LOCK:
                delay = max(0, _NEXT_REQUEST-time.monotonic())
            if delay > 10:
                raise CapabilityUnavailable('rate limit; retry shortly')
            self.sleeper(delay)
            transient = False
            def post(*args, **kwargs):
                nonlocal transient
                global _NEXT_REQUEST
                response = requests.post(*args, **kwargs)
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                errors = payload.get('errors') or []
                transient = response.status_code in (429, 502, 503, 504) or any(
                    isinstance(e, dict) and e.get('extensions', {}).get('code') == 'THROTTLED' for e in errors)
                cost = payload.get('extensions', {}).get('cost', {})
                status = cost.get('throttleStatus', {})
                wait = max(0, (float(cost.get('requestedQueryCost', 0))-float(status.get('currentlyAvailable', 1000))) / max(1, float(status.get('restoreRate', 50))))
                if transient:
                    try:
                        wait = max(wait, float(response.headers.get('Retry-After', 2**attempt)))
                    except ValueError:
                        wait = max(wait, 2**attempt)
                with _COST_LOCK:
                    _NEXT_REQUEST = max(_NEXT_REQUEST, time.monotonic()+wait)
                return response
            try:
                return graphql_request(document, variables=variables, timeout=20, request_post=post)[0]
            except Exception:
                if not transient or attempt == 2:
                    raise

    def customers(self, after=None, query=None, fresh=False):
        return self.query(CUSTOMERS, {'after':after, 'query':query}, 'customers', 45, fresh)['customers']
    def customer(self, customer_id, fresh=False):
        return self.query(CUSTOMER, {'id':gid(customer_id)}, 'customers', 45, fresh).get('customer')
    def customer_batch(self, ids, fresh=False):
        if not ids:return []
        return [n for n in self.query(CUSTOMER_BATCH, {'ids':[gid(i) for i in ids[:50]]}, 'customers', 45, fresh)['nodes'] if n]
    def orders(self, customer_id, after=None, fresh=False):
        data = self.query(ORDERS, {'id':gid(customer_id), 'after':after}, 'orders', 45, fresh).get('customer')
        return data['orders'] if data else {'nodes':[], 'pageInfo':{}}
    def first_order(self, customer_id):
        data = self.query(FIRST_ORDER, {'id':gid(customer_id)}, 'orders', 45).get('customer') or {}
        return next(iter(data.get('orders', {}).get('nodes', [])), None)
    def order(self, order_id, fresh=False):
        return self.query(ORDER, {'id':gid(order_id, 'Order')}, 'orders', 45, fresh).get('order')
    def line_page(self, kind, object_id, after, fresh=False):
        doc, root = (ORDER_LINES, 'order') if kind == 'order' else (CHECKOUT_LINES, 'node')
        data = self.query(doc, {'id':object_id, 'after':after}, kind, 30, fresh).get(root)
        return data['lineItems'] if data else {'nodes':[], 'pageInfo':{}}
    def products(self, ids, fresh=False):
        if not ids:return []
        return [p for p in self.query(PRODUCTS, {'ids':sorted(set(ids))[:50]}, 'products', 180, fresh)['nodes'] if p]
    def collections(self, product_id, after=None, fresh=False):
        data = self.query(COLLECTIONS, {'id':product_id, 'after':after}, 'products', 180, fresh).get('product')
        return data['collections'] if data else {'nodes':[], 'pageInfo':{}}
    def segments(self, after=None):
        return self.query(SEGMENTS, {'after':after}, 'segments', 90)['segments']
    def segment(self, segment_id, fresh=False):
        return self.query(SEGMENT, {'id':segment_id}, 'segments', 90, fresh).get('segment')
    def members(self, segment_id=None, query=None, after=None, fresh=False):
        data = self.query(MEMBERS, {'id':segment_id, 'query':query, 'after':after}, 'segments', 45, fresh)['customerSegmentMembers']
        ids = [gid(e['node']['id'].rsplit('/', 1)[-1]) for e in data['edges']]
        return {'nodes':self.customer_batch(ids, fresh), 'pageInfo':data['pageInfo'], 'totalCount':data['totalCount']}
    def count(self, query=None):
        if query is None:
            data = self.query(TOTAL, {}, 'customer counts', 45)['customersCount']
            return str(data['count']) + ('+' if data.get('precision') != 'EXACT' else '')
        return self.query(COUNT, {'query':query}, 'segment counts', 45)['customerSegmentMembers']['totalCount']
    def checkouts(self, after=None, query=None, fresh=False):
        return self.query(CHECKOUTS, {'after':after, 'query':query}, 'abandoned checkouts', 20, fresh)['abandonedCheckouts']
    def checkout(self, checkout_id, fresh=False):
        return self.query(CHECKOUT, {'id':gid(checkout_id, 'AbandonedCheckout')}, 'abandoned checkouts', 20, fresh).get('node')


    def memberships(self, customer_id, segments):
        if not segments:return set()
        data=self.query(MEMBERSHIPS,{'id':customer_id,'segments':segments[:50]},'segments',45)
        return {r['segmentId'] for r in data['customerSegmentMembership']['memberships'] if r['isMember']}
