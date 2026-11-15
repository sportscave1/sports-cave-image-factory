"""Bounded commerce rule facts, only fetched when a selected rule needs them."""


def order_facts(shop,order,rules):
    result={'order_value':(order.get('totalPriceSet') or {}).get('shopMoney')}
    if not any(r['field']=='product_purchased' for r in rules):return result
    page=order.get('lineItems')
    if not page:raise ValueError('Order products unavailable.')
    products=set();seen=set()
    for _ in range(20):
        products.update((p.get('product') or {}).get('id') for p in page['nodes'])
        if not page['pageInfo'].get('hasNextPage'):
            result['product_purchased']=products-{None};return result
        cursor=page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Order product pagination incomplete.')
        seen.add(cursor);page=shop.line_page('order',order['id'],cursor,fresh=True)
    raise ValueError('Order product rule limit reached.')


def checkout_facts(checkout):
    return {'checkout_country':(checkout.get('shippingAddress') or checkout.get('billingAddress') or {}).get('countryCodeV2')}
