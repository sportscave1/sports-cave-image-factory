"""Read-only, bounded artwork adapter for the existing lifecycle send context."""
from pathlib import Path
from datetime import timedelta
import logging

from crm_collector_images import configurations,marker,purchased
from crm_logic import date
from crm_catalogue import Catalogue,canonical_product_url
from crm_collector_sports import classifications,segment_interests,relevance,search_tags
from crm_collector_transport import bounded
from crm_shopify import CapabilityUnavailable

PRODUCTS=(Path(__file__).parent/'docs/collector-email-facts.graphql').read_text()
ORDER=(Path(__file__).parent/'docs/collector-email-order.graphql').read_text()
BESTSELLERS=(Path(__file__).parent/'docs/collector-email-bestsellers.graphql').read_text()
DISCOVERY=(Path(__file__).parent/'docs/collector-email-discovery.graphql').read_text()


def saleable(product):
    return bool(product.get('status')=='ACTIVE' and product.get('publishedInContext') is True
        and canonical_product_url({'url':product.get('onlineStoreUrl','')})
        and any(v.get('inventoryPolicy')=='CONTINUE' or (v.get('inventoryItem') or {}).get('tracked') is False
                or type(v.get('sellableOnlineQuantity')) is int and v['sellableOnlineQuantity']>0
                for v in (product.get('variants') or {}).get('nodes',[])))


def owned_ids(shop,orders,customer_id):
    """Incomplete histories suppress recommendations rather than recommend owned art."""
    result=set();budget=8
    for order in orders:
        if (order.get('customer') or {}).get('id')!=customer_id:raise ValueError('Order history recipient mismatch.')
        page=order.get('lineItems') or {};seen=set()
        while True:
            for line in page.get('nodes',[]):
                identity=(line.get('product') or {}).get('id')
                if identity:result.add(identity)
            info=page.get('pageInfo') or {}
            if info.get('hasNextPage') is False:break
            cursor=info.get('endCursor')
            if not budget or not cursor or cursor in seen:raise ValueError('Ownership history incomplete.')
            budget-=1;seen.add(cursor)
            page=shop.line_page('order',order['id'],cursor,fresh=True)
    return result


def resolve(shop,store,doc,context,customer_id,at,*,allocation_reader=None):
    from crm_shopify import CapabilityUnavailable
    try:blocks=_resolve(bounded(shop),store,doc,context,customer_id,at,allocation_reader=allocation_reader)
    except CapabilityUnavailable:
        logging.getLogger(__name__).warning('collector_artwork_omitted reason=shopify_unavailable')
        blocks={}
    return {'recipient':customer_id,'blocks':blocks}


def _resolve(shop,store,doc,context,customer_id,at,*,allocation_reader=None):
    configs=configurations(doc)
    if not configs:return {}
    customer=context.get('_customer') or {}
    if not customer_id or customer.get('id')!=customer_id:raise ValueError('Artwork recipient context mismatch.')
    result={};source=context.get('_order') or {};purchased_products=[]
    if source and (source.get('customer') or {}).get('id')!=customer_id:raise ValueError('Artwork order context mismatch.')
    for order in context.get('_lifecycle_orders',[]):
        if (order.get('customer') or {}).get('id')!=customer_id:raise ValueError('Order history recipient mismatch.')
    if any(c['source']=='Actual Purchased Product' for c in configs) and source:
        # Reverify the exact order; never choose lastOrder or a different customer.
        fresh=shop.query(ORDER,{'id':source['id']},'collector purchased artwork',0,True).get('order')
        if not fresh or fresh.get('id')!=source['id'] or (fresh.get('customer') or {}).get('id')!=customer_id:
            raise ValueError('Artwork order verification failed.')
        ids=list(dict.fromkeys((line.get('product') or {}).get('id') for line in fresh['lineItems']['nodes']))
        ids=[i for i in ids if i]
        purchased_products=shop.products(ids,fresh=True)
        if allocation_reader is None:
            from crm_personalisation_data import allocation as allocation_reader
        def optional_allocation(*args):
            try:return allocation_reader(*args)
            except Exception:return None
        rows=purchased({**source,**fresh},customer_id,purchased_products,allocation_reader=optional_allocation)
        for c in configs:
            if c['source']=='Actual Purchased Product':result[marker(c)]=rows[:min(c['count'],2)]
    recommendations=[c for c in configs if c['source'] not in ('Actual Purchased Product','No Image','Static Selected Image')]
    if not recommendations:return result
    try:
        result.update(recommend(shop,store,recommendations,context,customer_id,at,purchased_products))
    except Exception:
        logging.getLogger(__name__).warning('collector_recommendations_omitted reason=optional_unavailable')
    return result


def recommend(shop,store,recommendations,context,customer_id,at,purchased_products):
    result={};customer=context['_customer']
    country=(customer.get('defaultAddress') or {}).get('countryCodeV2')
    if not country or len(country)!=2:return result
    if '_lifecycle_orders' not in context:return result
    try:owned=owned_ids(shop,context['_lifecycle_orders'],customer_id)
    except ValueError:
        logging.getLogger(__name__).warning('collector_recommendations_omitted reason=incomplete_ownership')
        return result
    interests,authority=segment_interests(shop,store,customer_id,at)
    from crm_lifecycle_policy import qualifying
    paid_ids={(line.get('product') or {}).get('id') for order in context['_lifecycle_orders']
              if qualifying(order) and order.get('displayFinancialStatus')!='PARTIALLY_REFUNDED'
              for line in order.get('lineItems',{}).get('nodes',[])}
    # Reuse exact products already fetched for ownership cards. At most 50 others;
    # a subset supplies positive sport evidence, never proof of complete ownership.
    historical={p['id']:p for p in purchased_products if p and p.get('id') in paid_ids}
    missing=sorted(paid_ids-set(historical)-{None})[:50]
    if missing:
        historical.update({p['id']:p for p in shop.products(missing,fresh=True) if p and p.get('id') in missing})
    for p in historical.values():interests.update(classifications(p))
    if owned and not interests:return result
    logging.getLogger(__name__).info('collector_sport_authority source=%s sports=%s',authority,','.join(sorted(interests)))
    catalogue=Catalogue(shop,connect=store.connect,edition_reader=lambda **_:[])
    selections={};candidates=[]
    # A maximum of four distinct selection sets keeps Shopify calls bounded.
    selection_keys=list(dict.fromkeys((tuple(c['product_ids']),c['collection_id'],c['source']=='Verified Bestsellers') for c in recommendations))
    if len(selection_keys)>4:raise ValueError('Use at most four product selections per email.')
    discovered=None
    for ids,collection,bestsellers in selection_keys:
        selection=list(ids)
        if bestsellers:
            ranked=shop.query(BESTSELLERS,{'id':collection},'collector sales ranking',0,True).get('collection') if collection else None
            selection=[p['id'] for p in (ranked.get('products') or {}).get('nodes',[])] if ranked and ranked.get('id')==collection else []
        elif not selection and collection:
            selection=[p['id'] for p in catalogue.search(collection=collection)['rows']]
        if not selection and interests and not bestsellers and not ids and not collection:
            if discovered is None:
                tags=search_tags(interests)
                variables={f'q{i}':"status:active AND tag:"+(tags[i] if i<len(tags) else 'SC_UNASSIGNED_DO_NOT_USE') for i in range(4)}
                # Cache discovery IDs only, store/query-scoped. Every candidate's
                # sport, publication, inventory and image is verified fresh below.
                pages=shop.query(DISCOVERY,variables,'collector sport discovery',180,False)
                discovered=list(dict.fromkeys(p['id'] for i in range(len(tags)) for p in pages.get(f's{i}',{}).get('nodes',[])))
            selection=discovered
        selection=[i for i in selection if i and i not in owned][:48]
        selections[(ids,collection,bestsellers)]=selection;candidates.extend(selection)
    candidates=list(dict.fromkeys(candidates))[:48]
    if not candidates:return result
    nodes=shop.query(PRODUCTS,{'ids':candidates,'country':country},'collector recommendation availability',0,True)['nodes']
    products={p['id']:p for p in nodes if p and p.get('id') in candidates and saleable(p)}
    used=set();resolved=set()
    for c in recommendations:
        if marker(c) in resolved:continue
        resolved.add(marker(c))
        selected=[]
        ids=selections[(tuple(c['product_ids']),c['collection_id'],c['source']=='Verified Bestsellers')]
        ranked=sorted(enumerate(ids),key=lambda pair:(relevance(interests,products.get(pair[1],{})) if relevance(interests,products.get(pair[1],{})) is not None else 99,pair[0]))
        for _,identity in ranked:
            p=products.get(identity)
            if not p or identity in used:continue
            if interests and relevance(interests,p) is None:continue
            if not interests and not c['product_ids'] and not c['collection_id']:continue
            if c['source']=='Verified New Releases':
                created=date(p.get('createdAt'))
                if not created or not date(at)-timedelta(days=30)<=created<=date(at):continue
            from crm_collector_images import durable_image
            image=durable_image((p.get('featuredImage') or {}).get('url',''))
            if not image:continue
            selected.append(dict(id=identity,title=p['title'],image=image,url=p['onlineStoreUrl']))
            used.add(identity)
            if len(selected)>=c['count']:break
        result[marker(c)]=selected
    return result
