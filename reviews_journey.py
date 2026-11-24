"""Order review slots for the existing Post Checkout lifecycle, never a sender."""
from decimal import Decimal
from crm_tracking import public_https

def validate_request(request,trigger):
    from reviews_model import product_gid
    if not isinstance(request,dict) or not public_https(request.get('base_url','')):
        raise ValueError('Use a secure review collection URL.')
    if set(request)=={'product_id','base_url'} and trigger=='fulfilled' and product_gid(request['product_id']):return
    if set(request)=={'base_url','product_index'} and trigger=='post_purchase' and type(request['product_index']) is int and 0<=request['product_index']<3:return
    raise ValueError('Review requests require a verified purchased product or Post Checkout product slot.')

def products(lines):
    """Stable most-expensive-first product order; repeated variants share one slot."""
    result={}
    for line in lines:
        identity=(line.get('product') or {}).get('id')
        if not identity:continue
        amount=Decimal(((line.get('originalTotalSet') or {}).get('shopMoney') or {}).get('amount','0'))
        if identity not in result or amount>result[identity]:result[identity]=amount
    return sorted(result,key=lambda identity:(-result[identity],identity))[:3]

def order_products(shop,order):
    lines=list((order.get('lineItems') or {}).get('nodes',[]));page=(order.get('lineItems') or {}).get('pageInfo',{});seen=set()
    while page.get('hasNextPage'):
        cursor=page.get('endCursor')
        if not cursor or cursor in seen or len(seen)>=20:raise ValueError('Order products are incomplete.')
        seen.add(cursor);connection=shop.line_page(order['id'],cursor,fresh=True)
        lines.extend(connection['nodes']);page=connection.get('pageInfo',{})
    return products(lines)

def preview_document(doc):
    """Readable editor sample, without issuing a buyer token or performing I/O."""
    import json
    return json.loads(json.dumps(doc).replace('SC_REVIEW_PRODUCT_TITLE','Your Sports Cave edition'))
