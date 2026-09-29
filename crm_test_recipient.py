"""Fresh, single-customer verification for manual campaign tests only."""
import json
import logging

from crm_logic import consent, email, recipient_hash
from crm_native_unsubscribe import native_unsubscribe_url
from crm_resend_marketing import single_email
from crm_shopify import Shopify


def test_recipient_url(store, recipient, *, shop=None):
    if not single_email(recipient):
        raise ValueError('Enter one valid email address.')
    address=email(recipient)
    try:
        # Quote the tokenized Shopify email search, then independently match it.
        # No segment, cached consent, customer mirror, or per-customer follow-up.
        page=(shop or Shopify()).customers(query='email:'+json.dumps(address),fresh=True)
    except Exception as exc:
        logging.getLogger(__name__).warning('crm_test_customer_lookup_failed type=%s',type(exc).__name__)
        raise ValueError('Shopify customer lookup unavailable. Please try again.') from None
    if page.get('pageInfo',{}).get('hasNextPage'):
        raise ValueError('Shopify customer match could not be verified.')
    matches=[c for c in page.get('nodes',[]) if email(c.get('email'))==address]
    if not matches:
        raise ValueError('Shopify customer not found.')
    if len(matches)!=1 or not matches[0].get('id'):
        raise ValueError('Shopify customer match could not be verified.')
    customer=matches[0]
    native=customer.get('defaultEmailAddress') or {}
    if email(native.get('emailAddress'))!=address or native.get('validFormat') is not True:
        raise ValueError('Email does not match a valid Shopify default email address.')
    if consent(customer)!='SUBSCRIBED':
        raise ValueError('Customer is not subscribed to marketing.')
    if store.suppressed(customer['id'],recipient_hash(address)):
        raise ValueError('Customer is locally suppressed.')
    url=native_unsubscribe_url(customer)
    if not url:
        raise ValueError('Shopify unsubscribe URL unavailable.')
    return url
