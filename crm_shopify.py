"""Paginated Shopify authority plus a narrow opt-out-only write adapter."""
import json
import logging
import threading
import time
from crm_cache import CACHE

EMAIL_ADDRESS_FIELDS = 'defaultEmailAddress { emailAddress marketingState marketingUnsubscribeUrl validFormat }'
CUSTOMER_FIELDS = '''id firstName lastName email validEmailAddress createdAt updatedAt tags
 defaultAddress { countryCodeV2 country provinceCode province zip timeZone } amountSpent { amount currencyCode } numberOfOrders
 lastOrder { id name createdAt }
 emailMarketingConsent { marketingState marketingOptInLevel consentUpdatedAt } '''+EMAIL_ADDRESS_FIELDS
PAGE = 'pageInfo { hasNextPage endCursor }'
CUSTOMERS = '''query CrmCustomers($after:String,$query:String) {
 customers(first:50,after:$after,sortKey:UPDATED_AT,reverse:true,query:$query) {
 nodes { '''+CUSTOMER_FIELDS+' } '+PAGE+' } }'
# No order/profile enrichment for campaign eligibility. Keep timezone evidence for
# the same authoritative final-send calculation and scheduler.
CAMPAIGN_SUBSCRIBERS = '''query CrmCampaignSubscribers($after:String) {
 customers(first:250,after:$after,sortKey:UPDATED_AT,reverse:true) { nodes {
 id email validEmailAddress emailMarketingConsent { marketingState } '''+EMAIL_ADDRESS_FIELDS+'''
 defaultAddress { countryCodeV2 provinceCode timeZone }
 } '''+PAGE+' } }'
CUSTOMER = 'query CrmCustomer($id:ID!) { customer(id:$id) { '+CUSTOMER_FIELDS+' } }'
UNSUBSCRIBE = '''mutation CrmUnsubscribe($input:CustomerEmailMarketingConsentUpdateInput!) {
 customerEmailMarketingConsentUpdate(input:$input) {
 customer { id emailMarketingConsent { marketingState } }
 userErrors { field message }
 } }'''
CUSTOMER_BATCH = 'query CrmCustomerBatch($ids:[ID!]!) { nodes(ids:$ids) { ... on Customer { '+CUSTOMER_FIELDS+' } } }'
CAMPAIGN_CUSTOMER_BATCH = 'query CrmCustomerBatch($ids:[ID!]!) { nodes(ids:$ids) { ... on Customer { id email validEmailAddress emailMarketingConsent { marketingState } '+EMAIL_ADDRESS_FIELDS+' defaultAddress { countryCodeV2 provinceCode zip timeZone } } } }'
ORDER_FIELDS = '''id name createdAt cancelledAt fullyPaid displayFinancialStatus displayFulfillmentStatus
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
PRODUCT_PUBLIC_CONTEXT = PRODUCTS.replace('CrmProducts(', 'CrmProductPublicContext(').replace('productType tags','description productType tags')
CAMPAIGN_CONNECTION='''query CrmCampaignConnection {
 shop { id } currentAppInstallation { accessScopes { handle } }
}'''
CAMPAIGN_PRODUCTS='''query CrmCampaignProducts($query:String,$after:String) {
 products(first:12,query:$query,after:$after) { nodes { id title onlineStoreUrl
 media(first:12) { nodes { ... on MediaImage { image { id url emailUrl:url(transform:{maxWidth:1000,preferredContentType:JPG}) altText width height } } } '''+PAGE+''' }
 } '''+PAGE+''' } }'''
CAMPAIGN_IMAGES='''query CrmCampaignImages($id:ID!,$after:String) { product(id:$id) {
 media(first:24,after:$after) { nodes { ... on MediaImage { image { id url emailUrl:url(transform:{maxWidth:1000,preferredContentType:JPG}) altText width height } } } '''+PAGE+''' } } }'''
CAMPAIGN_VARIANTS='''query CrmCampaignVariants($id:ID!,$after:String) { product(id:$id) {
 variants(first:25,after:$after) { nodes { id title } '''+PAGE+''' } } }'''
CAMPAIGN_PRICE='''query CrmCampaignPrice($id:ID!,$country:CountryCode!) {
 productVariant(id:$id) { id contextualPricing(context:{country:$country}) { price { amount currencyCode } } } }'''
CAMPAIGN_ORDERS='''query CrmCampaignAttribution($query:String!,$after:String) {
 orders(first:25,query:$query,after:$after,sortKey:CREATED_AT) { nodes {
 id createdAt cancelledAt fullyPaid test netPaymentSet { shopMoney { amount currencyCode } }
 customerJourneySummary { ready lastVisit { occurredAt landingPage utmParameters { source medium campaign content } } }
 } '''+PAGE+''' } }'''
COLLECTIONS = '''query CrmCollections($id:ID!,$after:String) { product(id:$id) {
 collections(first:100,after:$after) { nodes { id title handle } '''+PAGE+' } } }'
SEGMENTS = 'query CrmSegments($after:String) { segments(first:50,after:$after) { nodes { id name query lastEditDate } '+PAGE+' } }'
SEGMENT = 'query CrmSegment($id:ID!) { segment(id:$id) { id name query lastEditDate } }'
MEMBERS = '''query CrmMembers($id:ID,$query:String,$after:String) {
 customerSegmentMembers(segmentId:$id,query:$query,first:50,after:$after) {
 edges { node { id } } totalCount '''+PAGE+' } }'
COUNT = 'query CrmCount($query:String) { customerSegmentMembers(query:$query,first:1) { totalCount } }'
CAMPAIGN_MEMBER_IDS = MEMBERS.replace('CrmMembers','CrmCampaignMemberIds').replace('first:50','first:250')
MEMBERSHIPS = 'query CrmMemberships($id:ID!,$segments:[ID!]!) { customerSegmentMembership(customerId:$id,segmentIds:$segments) { memberships { segmentId isMember } } }'
TOTAL = 'query CrmTotal { customersCount { count precision } }'
CHECKOUT_LINES_FIELDS = '''id title quantity variant { id product { id } } image { url }
 originalUnitPriceSet { shopMoney { amount currencyCode } }'''
CHECKOUT_LINES_FIELDS += ''' variantTitle discountedTotalPriceWithCodeDiscount { shopMoney { amount currencyCode } presentmentMoney { amount currencyCode } }'''
CHECKOUT_FIELDS = '''id createdAt updatedAt completedAt abandonedCheckoutUrl customer { id }
 shippingAddress { countryCodeV2 } billingAddress { countryCodeV2 }
 totalPriceSet { shopMoney { amount currencyCode } }
 lineItems(first:50) { nodes { '''+CHECKOUT_LINES_FIELDS+' } '+PAGE+' }'
CHECKOUTS = '''query CrmCheckouts($after:String,$query:String) {
 abandonedCheckouts(first:25,after:$after,sortKey:CREATED_AT,query:$query) {
 nodes { id createdAt updatedAt completedAt abandonedCheckoutUrl customer { id } shippingAddress { countryCodeV2 } billingAddress { countryCodeV2 } } '''+PAGE+' } }'
CHECKOUT = 'query CrmCheckout($id:ID!) { node(id:$id) { ... on AbandonedCheckout { '+CHECKOUT_FIELDS+' } } }'
CHECKOUT_PREVIEW_FIELDS=CHECKOUT_FIELDS.replace('customer { id }','customer { id firstName lastName email }')
CHECKOUT_PREVIEW='''query CrmAbandonedPreview($after:String) { abandonedCheckouts(first:5,after:$after,sortKey:CREATED_AT,reverse:true,query:"recovery_state:not_recovered") { nodes { '''+CHECKOUT_PREVIEW_FIELDS+' } '+PAGE+' } }'
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

    def campaign_subscribers(self, after=None):
        return self.query(CAMPAIGN_SUBSCRIBERS,{'after':after},'campaign subscribers',0,True)['customers']

    def campaign_email_profiles(self, addresses):
        """Fresh, paginated OR searches for relevant email identities only.

        No consent filter: unsubscribed duplicates must remain visible. Shopify
        phrase search can return broader matches; compare normalized emails locally.
        """
        from crm_logic import email
        addresses = sorted({email(value) for value in addresses} - {''})
        document = CAMPAIGN_SUBSCRIBERS.replace('CrmCampaignSubscribers($after:String)',
            'CrmCampaignEmailProfiles($after:String,$query:String!)').replace(
            'sortKey:UPDATED_AT,reverse:true', 'sortKey:ID,query:$query')
        result = {}
        deadline = time.monotonic() + 30
        for start in range(0, len(addresses), 25):
            wanted = set(addresses[start:start + 25])
            quoted = lambda value: '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
            query = ' OR '.join('email:' + quoted(value) for value in sorted(wanted))
            cursor = None; seen = set(); page_ids = set()
            while True:
                if time.monotonic() > deadline:
                    raise ValueError('Email identity verification timed out. Review again.')
                page = self.query(document, {'after':cursor,'query':query}, 'campaign email identity verification', 0, True)['customers']
                if page.get('complete') is False:
                    raise ValueError('Email identity verification is incomplete.')
                if type(page['pageInfo'].get('hasNextPage')) is not bool:
                    raise ValueError('Email identity pagination is incomplete.')
                for customer in page['nodes']:
                    identity = customer['id']
                    if identity in page_ids:
                        raise ValueError('Email identity pagination changed. Review again.')
                    page_ids.add(identity)
                    if email(customer.get('email')) in wanted:result[identity] = customer
                if len(page_ids) > 20000:
                    raise ValueError('Email identity verification limit reached.')
                if not page['pageInfo'].get('hasNextPage'):break
                cursor = page['pageInfo'].get('endCursor')
                if not cursor or cursor in seen:
                    raise ValueError('Email identity pagination did not advance.')
                seen.add(cursor)
        return list(result.values())

    def customers(self, after=None, query=None, fresh=False):
        return self.query(CUSTOMERS, {'after':after, 'query':query}, 'customers', 45, fresh)['customers']
    def customer(self, customer_id, fresh=False):
        return self.query(CUSTOMER, {'id':gid(customer_id)}, 'customers', 45, fresh).get('customer')
    def unsubscribe_only(self, customer_id, email=None):
        identity=gid(customer_id)
        if not identity:raise ValueError('Customer identity unavailable for consent synchronization.')
        result=self.query(UNSUBSCRIBE,{'input':{'customerId':identity,
            'emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}}},'email marketing opt-out',0,True)
        payload=result.get('customerEmailMarketingConsentUpdate') or {}
        customer=payload.get('customer') or {}
        if payload.get('userErrors') or customer.get('id')!=identity or (customer.get('emailMarketingConsent') or {}).get('marketingState')!='UNSUBSCRIBED':
            raise CapabilityUnavailable('email marketing opt-out')
        self.cache.invalidate()
        return True
    def customer_batch(self, ids, fresh=False):
        if not ids:return []
        return [n for n in self.query(CUSTOMER_BATCH, {'ids':[gid(i) for i in ids[:50]]}, 'customers', 45, fresh)['nodes'] if n]
    def campaign_customer_batch(self, ids):
        if len(ids)>50:raise ValueError('Campaign profile batch exceeds the safe limit.')
        if not ids:return []
        return [n for n in self.query(CAMPAIGN_CUSTOMER_BATCH,{'ids':[gid(i) for i in ids]},'campaign profiles',0,True)['nodes'] if n]
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
    def products(self, ids, fresh=False, *, public_context=False):
        if not ids:return []
        return [p for p in self.query(PRODUCT_PUBLIC_CONTEXT if public_context else PRODUCTS, {'ids':sorted(set(ids))[:50]}, 'products', 180, fresh)['nodes'] if p]
    def collections(self, product_id, after=None, fresh=False):
        data = self.query(COLLECTIONS, {'id':product_id, 'after':after}, 'products', 180, fresh).get('product')
        return data['collections'] if data else {'nodes':[], 'pageInfo':{}}
    def segments(self, after=None, fresh=False):
        return self.query(SEGMENTS, {'after':after}, 'segments', 90, fresh)['segments']
    def campaign_segment_counts(self, definitions):
        # One logical batch, no customer nodes, body enrichment or profile scan.
        keys=list(definitions)
        variables={f'q{i}':definitions[m]['query'] for i,m in enumerate(keys)}
        declarations=','.join(f'$q{i}:String!' for i in range(len(keys)))
        fields=' '.join(f'm{i}:customerSegmentMembers(query:$q{i},first:1) {{ totalCount }}' for i in range(len(keys)))
        data=self.query('query CrmCampaignCounts('+declarations+') {'+fields+'}',variables,'campaign segment counts',0,True)
        counts={m:data[f'm{i}']['totalCount'] for i,m in enumerate(keys)}
        if any(type(n) is not int or n<0 for n in counts.values()):raise ValueError('Incomplete Shopify counts.')
        return counts
    def campaign_member_ids(self, query):
        """Full native membership only for explicit audience review/send."""
        cursor=None;seen=set();ids=set();total=None
        while True:
            data=self.query(CAMPAIGN_MEMBER_IDS,{'id':None,'query':query,'after':cursor},'campaign membership',0,True)['customerSegmentMembers']
            if type(data['totalCount']) is not int or data['totalCount'] < 0 or (total is not None and total != data['totalCount']):
                raise ValueError('Shopify membership changed during calculation; review again.')
            total=data['totalCount']
            for edge in data['edges']:
                identity=gid(edge['node']['id'].rsplit('/',1)[-1])
                if not identity:raise ValueError('Invalid Shopify member identity.')
                if identity in ids:raise ValueError('Shopify membership pagination changed; review again.')
                ids.add(identity)
            if len(ids)>20000:raise ValueError('Audience calculation limit reached.')
            if not data['pageInfo'].get('hasNextPage'):break
            cursor=data['pageInfo'].get('endCursor')
            if not cursor or cursor in seen:raise ValueError('Member pagination did not advance.')
            seen.add(cursor)
        if len(ids)!=data['totalCount']:raise ValueError('Shopify membership changed during calculation; review again.')
        return ids
    def segment(self, segment_id, fresh=False):
        return self.query(SEGMENT, {'id':segment_id}, 'segments', 90, fresh).get('segment')
    def members(self, segment_id=None, query=None, after=None, fresh=False):
        data = self.query(MEMBERS, {'id':segment_id, 'query':query, 'after':after}, 'segments', 45, fresh)['customerSegmentMembers']
        ids = [gid(e['node']['id'].rsplit('/', 1)[-1]) for e in data['edges']]
        nodes=self.customer_batch(ids,fresh)
        return {'nodes':nodes, 'pageInfo':data['pageInfo'], 'totalCount':data['totalCount'], 'complete':len(nodes)==len(ids)}
    def count(self, query=None):
        if query is None:
            data = self.query(TOTAL, {}, 'customer counts', 45)['customersCount']
            return str(data['count']) + ('+' if data.get('precision') != 'EXACT' else '')
        return self.query(COUNT, {'query':query}, 'segment counts', 45)['customerSegmentMembers']['totalCount']
    def checkouts(self, after=None, query=None, fresh=False):
        return self.query(CHECKOUTS, {'after':after, 'query':query}, 'abandoned checkouts', 20, fresh)['abandonedCheckouts']
    def checkout(self, checkout_id, fresh=False):
        return self.query(CHECKOUT, {'id':gid(checkout_id, 'AbandonedCheckout')}, 'abandoned checkouts', 20, fresh).get('node')
    def checkout_lines(self,checkout_id,after,fresh=False):
        node=self.query(CHECKOUT_LINES,{'id':gid(checkout_id,'AbandonedCheckout'),'after':after},'abandoned checkouts',20,fresh).get('node')
        return (node or {}).get('lineItems')
    def abandoned_preview(self,after=None,fresh=False):
        return self.query(CHECKOUT_PREVIEW,{'after':after},'abandoned checkout preview',45,fresh)['abandonedCheckouts']


    def memberships(self, customer_id, segments):
        if not segments:return set()
        data=self.query(MEMBERSHIPS,{'id':customer_id,'segments':segments[:50]},'segments',45)
        return {r['segmentId'] for r in data['customerSegmentMembership']['memberships'] if r['isMember']}

    def campaign_products(self,query,after=None,fresh=False):
        from copy import deepcopy
        page=deepcopy(self.query(CAMPAIGN_PRODUCTS,{'query':str(query)[:200],'after':after},'campaign products',60,fresh)['products'])
        for p in page['nodes']:
            media=p.pop('media',{'nodes':[],'pageInfo':{}})
            p['images']={'nodes':[self.email_image(m['image']) for m in media['nodes'] if m.get('image')],'pageInfo':media['pageInfo']}
        return page

    def campaign_connection(self):
        data=self.query(CAMPAIGN_CONNECTION,{},'connection / granted read scopes',0,True)
        installation=data.get('currentAppInstallation') or {}
        return {'connected':bool((data.get('shop') or {}).get('id')),
                'scopes':[s['handle'] for s in installation.get('accessScopes',[])]}

    def campaign_images(self,product_id,after=None):
        media=self.query(CAMPAIGN_IMAGES,{'id':product_id,'after':after},'product images',60)['product']['media']
        return {'nodes':[self.email_image(m['image']) for m in media['nodes'] if m.get('image')],'pageInfo':media['pageInfo']}

    @staticmethod
    def email_image(image):
        from crm_tracking import asset_url
        result=dict(image)
        # Shopify performs a bounded-width proportional derivative. No server fetch,
        # credentials in URLs, new asset host, or destructive crop is involved.
        derivative=result.pop('emailUrl',None)
        if asset_url(derivative):result['url']=derivative
        return result

    def campaign_variants(self,product_id,after=None):
        return self.query(CAMPAIGN_VARIANTS,{'id':product_id,'after':after},'product variants',60)['product']['variants']

    def campaign_price(self,variant_id,market):
        country={'AU':'AU','US':'US','UK':'GB','CA':'CA','NZ':'NZ'}.get(market)
        if not country:return None
        data=self.query(CAMPAIGN_PRICE,{'id':variant_id,'country':country},'market product price',60,True).get('productVariant')
        price=((data or {}).get('contextualPricing') or {}).get('price')
        # Missing market pricing may fall back to shop currency. Never show that fallback.
        return price if price and price.get('currencyCode')=={'AU':'AUD','US':'USD','UK':'GBP','CA':'CAD','NZ':'NZD'}[market] else None

    def campaign_orders(self,start,end,after=None):
        from crm_logic import date
        if not date(start) or not date(end):raise ValueError('Use valid UTC order dates.')
        query='created_at:>='+date(start).isoformat()+' created_at:<'+date(end).isoformat()
        return self.query(CAMPAIGN_ORDERS,{'query':query,'after':after},'order attribution (read_orders)',0,True)['orders']
