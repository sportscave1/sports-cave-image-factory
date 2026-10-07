"""Validate only Shopify-supplied native URLs; never fetch or synthesize a URL."""
from crm_logic import email,consent
from crm_tracking import public_https


def native_unsubscribe_url(customer, *, recovery=False):
    customer=customer or {}
    native=customer.get('defaultEmailAddress') or {}
    url=native.get('marketingUnsubscribeUrl')
    if ((not recovery and consent(customer)!='SUBSCRIBED') or native.get('validFormat') is not True
            or email(native.get('emailAddress'))!=email(customer.get('email'))
            or not isinstance(url,str) or any(ord(c)<33 for c in url)
            or '<' in url or '>' in url or not public_https(url)):
        return ''
    return url
