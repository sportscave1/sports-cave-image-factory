"""Recipient-owned read verification for the existing internal Send Test boundary."""
from datetime import timedelta
import logging
import re
from time import monotonic
from crm_logic import email,date

NO_MATCH='No matching incomplete checkout was found. Create an abandoned checkout using your authorized test email, then retry.'


def contact_record(checkout):
    """GraphQL omits checkout contact email. Read its REST record using existing auth.

    No redirects, customer URL fetching, mutations, cache or response logging.
    Date/ID constraints bound this to the candidate's creation window.
    """
    import requests
    from shopify_sync import get_config,get_shopify_access_token
    cfg=get_config();created=date(checkout.get('createdAt'))
    identity=checkout.get('id','').rsplit('/',1)[-1]
    if not created or not identity.isdigit():raise ValueError('Checkout contact identity is unavailable.')
    domain=cfg.get('store_domain','');version=cfg.get('api_version','')
    if not re.fullmatch(r'[a-zA-Z0-9-]+\.myshopify\.com',domain) or not re.fullmatch(r'20\d{2}-\d{2}',version):
        raise ValueError('Shopify contact verification is not configured.')
    try:
        response=requests.get(f'https://{domain}/admin/api/{version}/checkouts.json',
            params={'limit':250,'since_id':str(int(identity)-1),'created_at_min':(created-timedelta(seconds=1)).isoformat(),
                    'created_at_max':(created+timedelta(seconds=1)).isoformat(),'status':'open'},
            headers={'X-Shopify-Access-Token':get_shopify_access_token(config=cfg)},timeout=10,allow_redirects=False)
        if response.status_code!=200:raise RuntimeError('Contact read unavailable')
        rows=response.json()['checkouts']
        matches=[r for r in rows if str(r.get('id'))==identity]
        if len(matches)!=1:raise RuntimeError('Contact record unavailable')
        return matches[0]
    except Exception as exc:
        logging.getLogger(__name__).warning('internal_checkout_contact_failed type=%s',type(exc).__name__)
        raise ValueError('Shopify could not verify the checkout contact address. Check abandoned-checkout read access and retry. No test was sent.') from None


def owned_checkout(shop,recipient,customer,*,contact_reader=None,clock=monotonic):
    contact_reader=contact_reader or contact_record
    if not isinstance(customer,dict) or not customer.get('id') or email(customer.get('email'))!=email(recipient):
        raise ValueError('The test recipient identity could not be verified.')
    address=email(recipient);after=None;seen=set();started=clock()
    # Shopify has no documented exact email/customer filter for this connection.
    # Read minimal metadata newest-first, then independently verify exact ownership.
    for _ in range(5):
        if clock()-started>30:raise ValueError('Checkout search timed out. Create a recent checkout with your test email and retry.')
        page=shop.recent_test_checkouts(after=after)
        if not isinstance(page,dict) or not isinstance(page.get('nodes'),list) or not isinstance(page.get('pageInfo'),dict):
            raise ValueError('Shopify checkout search returned an incomplete response. No test was sent.')
        for candidate in page.get('nodes',[]):
            if clock()-started>30:raise ValueError('Checkout search timed out. No test was sent; please retry.')
            owner=candidate.get('customer') or {}
            if candidate.get('completedAt') or owner.get('id')!=customer['id'] or email(owner.get('email'))!=address:continue
            cart=shop.checkout(candidate['id'],fresh=True)
            if not cart or cart.get('completedAt'):continue
            if cart.get('id')!=candidate['id'] or (cart.get('customer') or {}).get('id')!=customer['id'] or email((cart.get('customer') or {}).get('email'))!=address:
                raise ValueError('Checkout ownership changed. No test was sent.')
            evidence=contact_reader(cart)
            if evidence.get('completed_at') or evidence.get('closed_at'):continue
            if email(evidence.get('email'))!=address:continue
            if str(evidence.get('id'))!=cart['id'].rsplit('/',1)[-1] or str((evidence.get('customer') or {}).get('id'))!=customer['id'].rsplit('/',1)[-1] or evidence.get('abandoned_checkout_url')!=cart.get('abandonedCheckoutUrl'):
                raise ValueError('Checkout contact and recovery identity could not be verified. No test was sent.')
            from crm_recovery_links import destination
            from crm_tracking import store_host
            from urllib.parse import urlsplit
            url=destination({'recovery_url':cart.get('abandonedCheckoutUrl')})
            if not store_host(urlsplit(url).hostname):raise ValueError('Checkout recovery URL does not belong to the configured Shopify store.')
            # Complete, consistent variant/quantity facts, never sample substitution.
            lines=(cart.get('lineItems') or {}).get('nodes') or []
            expected=[(str(x.get('variant_id')),x.get('quantity')) for x in evidence.get('line_items',[])]
            actual=[(str((x.get('variant') or {}).get('id','')).rsplit('/',1)[-1],x.get('quantity')) for x in lines]
            if not actual or any(not v.isdigit() or type(q) is not int or q<1 for v,q in actual+expected) or sorted(actual)!=sorted(expected):
                raise ValueError('Checkout products or quantities changed. Reopen your checkout and retry.')
            from crm_abandoned_checkout import context
            context(cart,edition_reader=lambda **_:[]) # Validate facts without repeating optional edition reads.
            if any((x.get('variant') or {}).get('availableForSale') is False for x in lines):raise ValueError('A checkout product is unavailable. Review your checkout before testing.')
            return cart
        info=page.get('pageInfo') or {}
        if type(info.get('hasNextPage')) is not bool:raise ValueError('Checkout search pagination could not be verified.')
        if not info.get('hasNextPage'):raise ValueError(NO_MATCH)
        after=info.get('endCursor')
        if not after or after in seen:raise ValueError('Checkout search pagination could not be verified.')
        seen.add(after)
    raise ValueError('No matching checkout in the bounded recent search. Create a new abandoned checkout with your test address and retry.')


def document(shop,doc,recipient,customer):
    cart=owned_checkout(shop,recipient,customer)
    from crm_abandoned_checkout import publication_document,render_context,hydrate
    from crm_recovery_discount import prepare,substitute
    from crm_personalisation import present,resolve,render,TOKEN
    from crm_recovery_links import destination
    publication_document(doc,'abandoned') # Reject pasted private links before resolution.
    discount=prepare(shop,doc,cart,customer['id'])
    result=substitute(doc,discount)
    if present(result):
        wanted=set(TOKEN.findall(result['content']['subject'])+TOKEN.findall(result['content']['preheader']))
        result=render(result,resolve(cart,customer,trigger='abandoned',wanted=wanted),trigger='abandoned')
    data=render_context(cart,result);data['recovery_url']=destination(data,discount)
    return hydrate(result,data,shop=shop)
