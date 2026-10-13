"""Recipient-only catalogue hydration. Saved authoring documents stay manual facts.

Storefront caches contain product/market data only, never customer identities.
Delivery callers freeze the resolved message in the existing receipt snapshot.
"""
from copy import deepcopy
from collections import OrderedDict
import json
import os
import re
import threading
import time
from crm_catalogue import Catalogue, product_id, product_issues

QUERY='''query SportsCaveRelated($product: ID!, $country: CountryCode!)
 @inContext(country: $country) {
 productRecommendations(productId: $product, intent: RELATED) {
 id title availableForSale onlineStoreUrl
 } }'''
FALLBACK='''query SportsCaveAvailable($country: CountryCode!) @inContext(country: $country) {
 products(first: 24, sortKey: BEST_SELLING) { nodes { id title availableForSale onlineStoreUrl } }
}'''
MARKET_PRODUCTS='''query SportsCaveMarketProducts($ids: [ID!]!, $country: CountryCode!) @inContext(country: $country) {
 nodes(ids: $ids) { ... on Product { id availableForSale onlineStoreUrl
 priceRange { minVariantPrice { amount currencyCode } }
 compareAtPriceRange { minVariantPrice { amount currencyCode } }
 } } }'''
_CACHE=OrderedDict()
_LOCK=threading.Lock()


def enabled(doc):
    return any(s.get('type')=='catalogue' and s.get('visible') and
               s.get('settings',{}).get('smart') is True for s in doc.get('middle_sections',[]))


def storefront(shop,query,variables):
    """Existing shop identity; optional existing Storefront token, no Admin token reuse."""
    namespace=str(shop.namespace)
    key=(namespace,query,json.dumps(variables,sort_keys=True))
    with _LOCK:
        hit=_CACHE.get(key)
        if hit and hit[0]>time.monotonic():
            _CACHE.move_to_end(key)
            return deepcopy(hit[1])
    try:
        adapter=getattr(shop,'storefront_query',None)
        if callable(adapter):data=adapter(query,variables)
        else:
            import requests
            from shopify_sync import get_config
            cfg=get_config();domain=cfg['store_domain']
            if not domain.endswith('.myshopify.com'):raise ValueError('Invalid shop identity')
            headers={'Content-Type':'application/json'}
            token=os.getenv('SHOPIFY_STOREFRONT_ACCESS_TOKEN','').strip()
            private=os.getenv('SHOPIFY_STOREFRONT_PRIVATE_TOKEN','').strip()
            if private:headers['Shopify-Storefront-Private-Token']=private
            elif token:headers['X-Shopify-Storefront-Access-Token']=token
            response=requests.post('https://'+domain+'/api/'+cfg['api_version']+'/graphql.json',
                json={'query':query,'variables':variables},headers=headers,timeout=(1,2),allow_redirects=False)
            response.raise_for_status();body=response.json()
            if body.get('errors'):raise ValueError('Storefront unavailable')
            data=body['data']
        if not isinstance(data,dict):data={}
    except Exception:
        # Short negative caching prevents repeated failed requests during editing.
        data={}
    with _LOCK:
        _CACHE[key]=(time.monotonic()+(300 if data else 30),deepcopy(data))
        while len(_CACHE)>256:_CACHE.popitem(last=False)
    return data


def history(store,customer):
    if not customer.get('id'):return []
    return histories(store,[customer['id']])[customer['id']]


def lines(order):
    value=order.get('lineItems') or order.get('line_items') or order.get('products') or []
    return value.get('nodes',[]) if isinstance(value,dict) else value


def hydrate(doc,store,shop,customer,*,orders=None,checkout=None,catalogue=None,fresh=False,new_since=None):
    if not enabled(doc):return doc
    if not customer.get('id'):raise ValueError('Select a real customer for Smart recommendations.')
    from crm_collector_transport import bounded
    shop=bounded(shop,seconds=6)
    orders=history(store,customer) if orders is None else orders
    owned=set();seeds=[];titles=[]
    for order in orders:
        for item in lines(order):
            identity=product_id((item.get('product') or {}).get('id') or item.get('product_id'))
            if identity:
                owned.add(identity)
                if identity not in seeds:seeds.append(identity)
            titles.append(str(item.get('title') or ''))
    # Only a checkout with a verified matching Shopify customer can supply seeds.
    if checkout and (checkout.get('customer') or {}).get('id')==customer['id']:
        for item in lines(checkout):
            variant=item.get('variant') if isinstance(item.get('variant'),dict) else {}
            product=item.get('product') if isinstance(item.get('product'),dict) else variant.get('product') or {}
            identity=product_id(product.get('id') or item.get('product_id'))
            if identity and identity not in seeds:seeds.append(identity)
            titles.append(str(item.get('title') or ''))
    from sports_categories import detect_sport_in_text,normalize_sport_category
    sports={normalize_sport_category(detect_sport_in_text(t) or '') for t in titles[:12]}-{''}
    words=set(re.findall(r'[a-z0-9]+',' '.join(titles[:12]).casefold()))-{'art','artwork','sports','cave','edition','limited','frame','framed','wall','the','and'}
    def related(title):
        sport=normalize_sport_category(detect_sport_in_text(title or '') or '')
        return not sports or not sport or sport in sports
    country=(customer.get('defaultAddress') or {}).get('countryCodeV2')
    if not country:
        for event in ([checkout] if checkout else [])+orders:
            address=event.get('shippingAddress') or event.get('shipping_address') or event.get('billingAddress') or event.get('billing_address') or {}
            country=event.get('_country') or address.get('countryCodeV2') or address.get('country_code') or address.get('countryCode')
            if country:break
    if not country and doc['market']=='Global':
        result=deepcopy(doc)
        for s in result['middle_sections']:
            if s.get('type')=='catalogue' and s['settings'].get('smart'):s['products']=[];s['visible']=False;s['settings']['smart']=False
        return result  # No invented Australian market for an unknown global recipient.
    country=country or {
        'AU':'AU','US':'US','UK':'GB','CA':'CA','NZ':'NZ','Global':'AU'}[doc['market']]
    if not isinstance(country,str) or len(country)!=2:raise ValueError('Customer market unavailable.')
    extended_market=country not in ('AU','US','GB','CA','NZ')
    candidates=[]
    for seed in seeds[:3]:
        for p in storefront(shop,QUERY,{'product':seed,'country':country}).get('productRecommendations') or []:
            if p.get('availableForSale') is True and p.get('onlineStoreUrl') and related(p.get('title')):candidates.append(p['id'])
    if len(set(candidates)-owned)<3 and seeds:
        # Reuse the established collection integration before generic fallback.
        try:
            from crm_shopify import PRODUCTS
            from crm_collector_resolver import BESTSELLERS
            data=shop.query(PRODUCTS,{'ids':seeds[:3]},'smart catalogue interests',300)['nodes']
            options=[c for p in data if p for c in (p.get('collections') or {}).get('nodes',[])
                if c.get('handle','').lower() not in ('all','frontpage','best-sellers','new-arrivals')]
            specific=[c for c in options if normalize_sport_category(detect_sport_in_text(c.get('title','')+' '+c.get('handle','')) or '') in sports]
            collections=list(dict.fromkeys(c['id'] for c in specific or options))
            for collection in collections[:2]:
                page=shop.query(BESTSELLERS,{'id':collection},'smart collection recommendations',300).get('collection') or {}
                candidates.extend(p['id'] for p in (page.get('products') or {}).get('nodes',[]))
        except Exception:pass
    if len(set(candidates)-owned)<3:
        data=storefront(shop,FALLBACK,{'country':country})
        candidates.extend(p['id'] for p in (data.get('products') or {}).get('nodes',[])
                    if p.get('availableForSale') is True and p.get('onlineStoreUrl') and related(p.get('title')))
    # Existing local catalogue provides a bounded fallback during Storefront outages.
    if not set(candidates)-owned:
        from sports_categories import detect_sport_in_text
        sport=detect_sport_in_text(' '.join(titles)) or ''
        try:
            rows=store.q('''SELECT shopify_product_id FROM shopify_products
                WHERE upper(status)='ACTIVE' AND online_store_url IS NOT NULL AND online_store_url<>''
                ORDER BY CASE WHEN %s<>'' AND (title ILIKE %s OR product_type ILIKE %s)
                THEN 0 ELSE 1 END,shopify_product_id LIMIT 24''',(sport,'%'+sport+'%','%'+sport+'%'))
        except Exception:rows=[]
        candidates=[product_id(r['shopify_product_id']) for r in rows]
    ids=list(dict.fromkeys(i for i in candidates if product_id(i)==i and i not in owned))[:24]
    regional={}
    if ids and extended_market:
        # Global recipients outside the editor's named markets use Shopify's
        # contextual Storefront price, never the Global/Australia display fallback.
        nodes=storefront(shop,MARKET_PRODUCTS,{'ids':ids,'country':country}).get('nodes') or []
        regional={p['id']:p for p in nodes if p and p.get('availableForSale') is True and p.get('onlineStoreUrl')}
        ids=[i for i in ids if i in regional]
    products=[]
    if ids:
        from crm_lifecycle_shopify import PRODUCT_AVAILABILITY
        try:
            nodes=shop.query(PRODUCT_AVAILABILITY,{'ids':ids},'smart catalogue availability',60,fresh)['nodes']
            from crm_logic import date
            allowed={p['id'] for p in nodes if p and
                (p.get('tracksInventory') is False or isinstance(p.get('totalInventory'),int) and p['totalInventory']>0)
                and (not new_since or date(p.get('createdAt')) and date(p['createdAt'])>date(new_since))}
            # Resolve only live available candidates; one missing node cannot break the rest.
            ids=[i for i in ids if i in allowed]
            market={'GB':'UK'}.get(country,country)
            if market not in ('AU','US','UK','CA','NZ'):market=doc['market']
            products=(catalogue or Catalogue(shop,connect=store.connect)).resolve(ids,market,fresh=fresh)
            if extended_market:
                from crm_catalogue import amount
                for p in products:
                    native=regional[p['id']];price=native['priceRange']['minVariantPrice']
                    compare=native['compareAtPriceRange']['minVariantPrice']
                    p.update(price=amount(price['amount']),currency=price['currencyCode'],
                        compare_at=amount(compare['amount']) if compare['currencyCode']==price['currencyCode'] else '')
        except Exception:
            products=[]  # No fabricated or unverifiable products on an outage.
    result=deepcopy(doc)
    # Keep Shopify's order for ties; matching athlete/team words and sport
    # provide a small local ranking without inferring customer browsing history.
    products=[p for p in products if related(p['title'])]
    products.sort(key=lambda p:(-len(words & set(re.findall(r'[a-z0-9]+',p['title'].casefold()))),
        -int(normalize_sport_category(detect_sport_in_text(p['title']) or '') in sports)))
    for section in result['middle_sections']:
        if section.get('type')!='catalogue' or not section.get('visible') or not section['settings'].get('smart'):continue
        section['products']=[deepcopy(p) for p in products if
            not product_issues(p,section['settings']) and
            (p.get('edition') is not None or not any(section['settings']['display'][k] for k in ('limit','next','remaining'))) and
            (p.get('edition') is None or p['edition'].get('remaining',0)>0)][:3]
        section['settings']['smart']=False  # Resolved copy only; never saved to the draft.
        if not section['products']:section['visible']=False
    return result


def histories(store,ids):
    """One indexed order read per existing 50-recipient preparation batch."""
    result={i:[] for i in ids}
    # Product facts only, for every locally recorded purchase: an older edition
    # must not become recommendable merely because it falls outside a recent page.
    rows=store.q('''SELECT shopify_customer_id,jsonb_build_object('_country',COALESCE(
        raw_json->'shipping_address'->>'country_code',raw->'shipping_address'->>'country_code',
        raw_json->'shippingAddress'->>'countryCodeV2',raw_json->'billing_address'->>'country_code'),
        'products',COALESCE(
        raw_json->'line_items',raw->'line_items',raw_json->'lineItems'->'nodes',
        raw->'lineItems'->'nodes',raw_json->'products','[]'::jsonb)) AS raw_json
        FROM shopify_orders WHERE shopify_customer_id=ANY(%s) AND cancelled_at IS NULL
        AND upper(financial_status) IN ('PAID','PARTIALLY_REFUNDED','REFUNDED')
        ORDER BY created_at DESC''',(ids,))
    for row in rows:result[row['shopify_customer_id']].append(row['raw_json'] or {})
    return result


class BatchFacts:
    """Fresh product reads shared only within one existing 50-recipient batch.

    Customer/consent/eligibility methods always delegate uncached. Different
    recipients still resolve their own seeds, exclusions and product selection.
    """
    def __init__(self,shop,connect):
        self.source=shop;self.namespace=shop.namespace;self.reads={};self.products={}
        self.shop=self
        self.catalogue=Catalogue(self,connect=connect)

    def __getattr__(self,name):return getattr(self.source,name)

    def query(self,document,variables,capability,*args):
        if capability not in ('smart catalogue availability','smart catalogue interests','smart collection recommendations','catalogue products'):
            return self.source.query(document,variables,capability,*args)
        key=(document,json.dumps(variables,sort_keys=True))
        if key not in self.reads:
            from crm_collector_transport import bounded
            self.reads[key]=bounded(self.source,seconds=3).query(document,variables,capability,*args)
        return deepcopy(self.reads[key])

    def resolve(self,ids,market,*,fresh=False):
        key=(tuple(ids),market)
        if key not in self.products:self.products[key]=self.catalogue.resolve(ids,market,fresh=fresh)
        return deepcopy(self.products[key])


def preview(state,store,shop,doc,*,customer=None,orders=None,revision=None,new_since=None):
    """Session-scoped visual facts, not consent or delivery authority."""
    if not enabled(doc):return doc
    pin=(state.get('_automation_checkout_pin') or {}).get('last_good') or {}
    customer_id=customer.get('id') if customer else pin.get('customer_id') if getattr(store,'email_mode',None)=='automation' else state.get('_smart_preview_customer')
    contexts=state.setdefault('_smart_preview_contexts',{})
    cached=contexts.get(customer_id)
    if customer is not None and (not cached or cached[0]<time.monotonic() or len(cached)<4 or cached[3]!=revision):
        contexts[customer_id]=(time.monotonic()+120,deepcopy(customer),deepcopy(orders) if orders is not None else history(store,customer),revision)
        cached=contexts[customer_id]
    if not cached or cached[0]<time.monotonic():
        if customer_id:
            row=store.q('SELECT profile FROM crm_lifecycle_customers WHERE customer_id=%s',(customer_id,),True)
        else:
            row=store.q('SELECT profile FROM crm_lifecycle_customers ORDER BY verified_at DESC LIMIT 1',one=True)
        if not row and customer_id and getattr(store,'email_mode',None)=='automation':
            profile=shop.customer(customer_id)
            row={'profile':profile} if profile and profile.get('id')==customer_id else None
        if not row:raise ValueError('No customer example is available for Smart recommendations.')
        customer=row['profile']
        if customer_id and customer.get('id')!=customer_id:raise ValueError('Customer example identity changed. Refresh the preview.')
        customer_id=customer['id']
        if '_smart_preview_customer' not in state:state['_smart_preview_customer']=customer_id
        contexts[customer_id]=(time.monotonic()+120,customer,history(store,customer))
        while len(contexts)>8:contexts.pop(next(iter(contexts)))
    else:customer=cached[1]
    while len(contexts)>8:contexts.pop(next(iter(contexts)))
    cache=state.setdefault('_smart_preview_products',{})
    settings=[(s['id'],s['settings']['display']) for s in doc['middle_sections'] if s.get('type')=='catalogue' and s['settings'].get('smart')]
    key=json.dumps([str(shop.namespace),customer_id,contexts[customer_id][0],doc['market'],settings,pin.get('checkout_id'),new_since],sort_keys=True,default=str)
    if key not in cache:
        checkout={'customer':{'id':customer_id},'products':pin.get('items',[])} if pin.get('customer_id')==customer_id else None
        if getattr(store,'email_mode',None)!='automation':
            from crm_campaign_home_cache import job
            from crm_flow_preview import NoPreviewCustomer
            source=deepcopy(doc);profile=deepcopy(customer);order_data=deepcopy(contexts[customer_id][2])
            future=job(state,store,('smart-catalogue',key),lambda:hydrate(source,store,shop,profile,orders=order_data,checkout=checkout,new_since=new_since),ttl=120)
            if future is None or not future.done():raise NoPreviewCustomer('Loading customer recommendations…')
            result=future.result()
        else:result=hydrate(doc,store,shop,customer,orders=contexts[customer_id][2],checkout=checkout,new_since=new_since)
        smart_ids={s['id'] for s in doc['middle_sections'] if s.get('type')=='catalogue' and s['settings'].get('smart')}
        cache[key]={s['id']:s['products'] for s in result['middle_sections'] if s['id'] in smart_ids}
        while len(cache)>16:cache.pop(next(iter(cache)))
        state['_smart_preview_revision']=state.get('_smart_preview_revision',0)+1
    result=deepcopy(doc)
    for s in result['middle_sections']:
        if s['id'] in cache[key]:
            s['products']=deepcopy(cache[key][s['id']]);s['settings']['smart']=False
            if not s['products']:s['visible']=False
    return result


def control(state,store):
    import streamlit as st
    rows=state.get('_smart_preview_options')
    if not rows or rows[0]<time.monotonic():
        rows=(time.monotonic()+120,store.q('SELECT customer_id,name FROM crm_lifecycle_customers ORDER BY verified_at DESC LIMIT 30'))
        state['_smart_preview_options']=rows
    labels={r['customer_id']:r.get('name') or 'Customer' for r in rows[1]}
    ids=list(labels)
    if not ids:
        st.caption('No customer example available.');return
    chosen=state.get('_smart_preview_customer')
    if chosen not in ids:state['_smart_preview_customer']=ids[0]
    def changed():state['_smart_preview_customer']=state['_smart_preview_customer_widget']
    with st.popover('Preview customer',help='Visual example only; sending always checks consent.'):
        st.selectbox('Customer',ids,index=ids.index(state['_smart_preview_customer']),
            format_func=lambda i:labels[i],key='_smart_preview_customer_widget',on_change=changed)
