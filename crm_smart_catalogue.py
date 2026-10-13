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

FALLBACK='''query SportsCaveAvailable($country: CountryCode!, $after:String) @inContext(country: $country) {
 products(first: 100, after:$after, sortKey: BEST_SELLING) { nodes { id title availableForSale onlineStoreUrl } pageInfo { hasNextPage endCursor } }
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


def storefront(shop,query,variables,*,fresh=False):
    """Existing shop identity; optional existing Storefront token, no Admin token reuse."""
    namespace=str(shop.namespace)
    key=(namespace,query,json.dumps(variables,sort_keys=True))
    with _LOCK:
        hit=_CACHE.get(key)
        if not fresh and hit and hit[0]>time.monotonic():
            _CACHE.move_to_end(key)
            return deepcopy(hit[1])
    deadline=getattr(shop,'optional_deadline',None)
    if isinstance(deadline,(int,float)) and time.monotonic()>deadline:return {}
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


def hydrate(doc,store,shop,customer,*,orders=None,checkout=None,catalogue=None,fresh=False,new_since=None,
            orders_complete=False,behaviour_data=None):
    if not enabled(doc):return doc
    if not customer.get('id'):raise ValueError('Select a real customer for Smart recommendations.')
    from crm_collector_transport import bounded
    from crm_smart_candidates import memberships,collection_products,behaviour,signal_ids,balanced
    shop=bounded(shop,seconds=8)
    # Flow context often contains just the triggering order. Merge the complete
    # local ledger; campaign preparation already supplies its single batch read.
    orders=list(orders or [])+(history(store,customer) if not orders_complete else [])
    owned=set()
    def identities(event):
        result=[]
        for item in lines(event):
            variant=item.get('variant') if isinstance(item.get('variant'),dict) else {}
            product=item.get('product') if isinstance(item.get('product'),dict) else variant.get('product') or {}
            identity=product_id(product.get('id') or item.get('product_id'))
            if identity:result.append(identity)
        return result
    for order in orders:owned.update(identities(order))
    # An order without surviving product IDs is still purchase history. Never
    # relax the restriction just because its product was deleted from Shopify.
    purchased=bool(orders) or int(customer.get('numberOfOrders') or 0)>0
    country=(customer.get('defaultAddress') or {}).get('countryCodeV2')
    if not country:
        for event in ([checkout] if checkout else [])+orders:
            address=event.get('shippingAddress') or event.get('shipping_address') or event.get('billingAddress') or event.get('billing_address') or {}
            country=event.get('_country') or address.get('countryCodeV2') or address.get('country_code') or address.get('countryCode')
            if country:break
    country=country or {'AU':'AU','US':'US','UK':'GB','CA':'CA','NZ':'NZ','Global':None}[doc['market']]
    result=deepcopy(doc);groups=[];tiers=[];popular=False;products={}
    if country and re.fullmatch('[A-Z]{2}',country):
        try:
            if purchased:
                collections=memberships(shop,sorted(owned))
                groups=[collection_products(shop,c) for c in collections]
            else:
                signals=behaviour_data if behaviour_data is not None else behaviour(store,customer)
                if signals.get('unavailable'):raise ValueError('Customer signals unavailable')
                viewed=signal_ids(signals,customer['id'],'viewed')
                carts=signal_ids(signals,customer['id'],'checkout')
                if checkout and (checkout.get('customer') or {}).get('id')==customer['id']:
                    carts=identities(checkout)+carts
                engaged=signal_ids(signals,customer['id'],'engaged')
                # Each tier has its own collection expansion, in priority order.
                # Meaningful signals never fall back to unrelated random stock.
                for seeds in (viewed,carts,engaged):
                    if not seeds:continue
                    peers=[collection_products(shop,c) for c in memberships(shop,seeds)]
                    tiers.append((seeds,peers))
                    groups.extend([seeds,*peers])
                if not groups:
                    popular=True
                    groups=[[]]
            def batches():
                if not popular:
                    ids=list(dict.fromkeys(i for group in groups for i in group if product_id(i)==i and i not in owned))
                    for start in range(0,len(ids),50):yield ids[start:start+50]
                    return
                cursor=None;seen=set();seen_ids=set()
                while True:
                    page=storefront(shop,FALLBACK,{'country':country,'after':cursor},fresh=fresh).get('products') or {}
                    ids=[]
                    for p in page.get('nodes',[]):
                        i=p.get('id')
                        if product_id(i)==i and i not in seen_ids and p.get('availableForSale') is True and p.get('onlineStoreUrl'):
                            ids.append(i);seen_ids.add(i)
                    groups[0].extend(ids)
                    for start in range(0,len(ids),50):yield ids[start:start+50]
                    info=page.get('pageInfo') or {}
                    if not info.get('hasNextPage'):return
                    cursor=info.get('endCursor')
                    if not cursor or cursor in seen:return
                    seen.add(cursor)
            market={'GB':'UK'}.get(country,country)
            if market not in ('AU','US','UK','CA','NZ'):market=doc['market']
            from crm_lifecycle_shopify import PRODUCT_AVAILABILITY
            from crm_logic import date
            from crm_catalogue import amount,edition_available
            resolver=catalogue or Catalogue(shop,connect=store.connect)
            for batch in batches():
                # Contextual Storefront publication/availability applies to EVERY
                # recipient country, including AU/US/GB, not only extended markets.
                native=storefront(shop,MARKET_PRODUCTS,{'ids':batch,'country':country},fresh=fresh).get('nodes') or []
                regional={p['id']:p for p in native if p and p.get('availableForSale') is True and p.get('onlineStoreUrl')}
                batch=[i for i in batch if i in regional]
                if new_since and batch:
                    nodes=shop.query(PRODUCT_AVAILABILITY,{'ids':batch},'smart catalogue availability',60,fresh)['nodes']
                    allowed={p['id'] for p in nodes if p and date(p.get('createdAt')) and date(p['createdAt'])>date(new_since)}
                    batch=[i for i in batch if i in allowed]
                if not batch:continue
                for p in resolver.resolve(batch,market,fresh=fresh,allow_missing=True):
                    if not edition_available(p.get('edition')):continue
                    if popular and not (p['edition'].get('sold') or 0)>0:continue
                    # Contextual prices also avoid mismatches between market
                    # availability and the prices rendered in tests/live emails.
                    native=regional[p['id']]
                    price=(native.get('priceRange') or {}).get('minVariantPrice') or {}
                    compare=(native.get('compareAtPriceRange') or {}).get('minVariantPrice') or {}
                    if price:
                        p.update(price=amount(price.get('amount')),currency=price.get('currencyCode') or '',
                                 compare_at=amount(compare.get('amount')) if compare.get('currencyCode')==price.get('currencyCode') else '')
                    elif country not in ('AU','US','GB','CA','NZ'):continue
                    products[p['id']]=p
                if popular and all(sum(not product_issues(p,s['settings']) for p in products.values())>=s['settings'].get('smart_count',4)
                        for s in doc['middle_sections'] if s.get('type')=='catalogue' and s.get('visible') and s['settings'].get('smart')):break
        except Exception:
            products={}  # Optional section fails closed; never invent fallback facts.
    for section in result['middle_sections']:
        if section.get('type')!='catalogue' or not section.get('visible') or not section['settings'].get('smart'):continue
        count=section['settings'].get('smart_count',4)
        if type(count) is not int or not 1<=count<=12:raise ValueError('Choose 1 to 12 smart products.')
        valid={i:p for i,p in products.items() if not product_issues(p,section['settings'])}
        if purchased:
            chosen=balanced(groups,valid,count)
        else:
            # Viewed/checkout products before their collection peers. Preserve
            # tier and Shopify bestseller order; no title-based guesswork.
            ranked=[]
            for seeds,peers in tiers:
                ranked.extend(valid[i] for i in seeds if i in valid)
                ranked.extend(balanced(peers,valid,len(valid)))
            if popular:ranked=[valid[i] for i in groups[0] if i in valid]
            chosen=[];seen=set()
            for p in ranked:
                if p['id'] not in seen:chosen.append(p);seen.add(p['id'])
            chosen=chosen[:count]
        section['products']=deepcopy(chosen)
        section['settings']['smart']=False
        if not chosen:section['visible']=False
    return result


def histories(store,ids):
    """One indexed order read per existing 50-recipient preparation batch."""
    result={i:[] for i in ids}
    # Product facts only, for every locally recorded purchase: an older edition
    # must not become recommendable merely because it falls outside a recent page.
    rows=store.q('''SELECT COALESCE(NULLIF(shopify_customer_id,''),customer_id) AS shopify_customer_id,jsonb_build_object('_country',COALESCE(
        raw_json->'shipping_address'->>'country_code',raw->'shipping_address'->>'country_code',
        raw_json->'shippingAddress'->>'countryCodeV2',raw_json->'billing_address'->>'country_code'),
        'products',COALESCE(
        raw_json->'line_items',raw->'line_items',raw_json->'lineItems'->'nodes',
        raw->'lineItems'->'nodes',raw_json->'products','[]'::jsonb)) AS raw_json
        FROM shopify_orders WHERE COALESCE(NULLIF(shopify_customer_id,''),customer_id)=ANY(%s) AND cancelled_at IS NULL
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

    def storefront_query(self,document,variables):
        key=('storefront',document,json.dumps(variables,sort_keys=True))
        if key not in self.reads:self.reads[key]=storefront(self.source,document,variables,fresh=True)
        return deepcopy(self.reads[key])

    def query(self,document,variables,capability,*args):
        if capability not in ('smart catalogue availability','smart catalogue interests','smart collection recommendations','catalogue products'):
            return self.source.query(document,variables,capability,*args)
        key=(document,json.dumps(variables,sort_keys=True))
        if key not in self.reads:
            from crm_collector_transport import bounded
            self.reads[key]=bounded(self.source,seconds=3).query(document,variables,capability,*args)
        return deepcopy(self.reads[key])

    def resolve(self,ids,market,*,fresh=False,allow_missing=False):
        missing=[i for i in ids if (i,market) not in self.products]
        if missing:
            found={p['id']:p for p in self.catalogue.resolve(missing,market,fresh=fresh,allow_missing=True)}
            for i in missing:self.products[i,market]=found.get(i)
        if not allow_missing and any(self.products[i,market] is None for i in ids):raise ValueError('Product unavailable')
        return deepcopy([self.products[i,market] for i in ids if self.products[i,market] is not None])


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
    settings=[(s['id'],s['settings']['display'],s['settings'].get('smart_count',4)) for s in doc['middle_sections'] if s.get('type')=='catalogue' and s['settings'].get('smart')]
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
