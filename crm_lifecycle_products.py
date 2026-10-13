"""Real catalogue recommendations; existing cards, picker and Shopify transport."""
from copy import deepcopy
from datetime import timedelta
from crm_logic import date
from crm_catalogue import Catalogue,product_id,product_issues
from crm_lifecycle_shopify import PRODUCT_AVAILABILITY

SECTION_ID='lifecycle-recommendations'

def selected(doc):
    return next((s for s in doc.get('middle_sections',[]) if s['id']==SECTION_ID and s.get('visible') and not s.get('settings',{}).get('smart')),None)

def recommend(store,shop,doc,orders,at,*,new_since=None):
    section=selected(doc)
    if not section:return []
    purchased=set();titles=[]
    for order in orders:
        for item in (order.get('lineItems') or {}).get('nodes',order.get('products',[])):
            identity=product_id((item.get('product') or {}).get('id') or item.get('product_id'))
            if identity:purchased.add(identity)
            titles.append(item.get('title',''))
    if section['products']:
        ids=[p['id'] for p in section['products']]
    else:
        from sports_categories import detect_sport_in_text
        sport=detect_sport_in_text(' '.join(titles)) or ''
        rows=store.q('''SELECT shopify_product_id FROM shopify_products
          WHERE upper(status)='ACTIVE' AND online_store_url IS NOT NULL AND online_store_url<>''
          ORDER BY CASE WHEN %s<>'' AND (product_type ILIKE %s OR title ILIKE %s) THEN 0 ELSE 1 END,
          raw_json->>'createdAt' DESC NULLS LAST,shopify_product_id LIMIT 24''',(sport,'%'+sport+'%','%'+sport+'%'))
        ids=[product_id(r['shopify_product_id']) for r in rows if product_id(r['shopify_product_id']) not in purchased]
    ids=[i for i in ids if i]
    if not ids:raise ValueError('No verified product recommendations are available')
    nodes=shop.query(PRODUCT_AVAILABILITY,{'ids':ids},'lifecycle product availability',0,True)['nodes']
    available={n['id'] for n in nodes if n and n.get('id') in ids and
               (n.get('tracksInventory') is False or type(n.get('totalInventory')) is int and n['totalInventory']>0)
               and (not new_since or date(n.get('createdAt')) and date(n['createdAt'])>date(new_since))}
    ids=[i for i in ids if i in available][:4]
    if not ids:raise ValueError('No available recommendations satisfy this email’s criteria')
    # Edition counters and prices are not needed for these promotional cards.
    products=Catalogue(shop,connect=store.connect,edition_reader=lambda **_:[]).resolve(ids,doc['market'],fresh=True)
    products=[p for p in products if not product_issues(p,section['settings'])]
    if not products:raise ValueError('Recommendations are not published or lack valid product content')
    return products

def hydrate(doc,products):
    result=deepcopy(doc);section=selected(result)
    if section:
        if not products:raise ValueError('Required lifecycle recommendations are missing')
        section['products']=deepcopy(products)
    return result
