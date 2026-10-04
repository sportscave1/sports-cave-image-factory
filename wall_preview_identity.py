"""Read-only customer matching for Wall Preview archives, never marketing signup."""

import logging
import re

import crm_shopify
from crm_logic import email, marketing_state


MARKETING_STATES = {'SUBSCRIBED', 'UNSUBSCRIBED', 'PENDING', 'NOT_SUBSCRIBED',
                    'REDACTED', 'INVALID', 'UNKNOWN'}


def normalize_email(value):
    value = str(value or '').strip().lower()
    if not email(value) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('A valid customer email is required to archive a preview.')
    return value


def customer_folder_name(value):
    """Encode path-unsafe characters without merging distinct email identities."""
    value = normalize_email(value)
    return ''.join('%%%02X' % ord(char) if char in '/\\:*?"<>|%' else char for char in value)


def resolve(email_value, name_value, source):
    address = normalize_email(email_value)
    name = ' '.join(str(name_value or '').split())
    if not name or len(name) > 200:
        raise ValueError('A customer contact name of up to 200 characters is required.')
    if source not in {'logged_in', 'guest'}:
        raise ValueError('Choose a valid preview identity source.')
    identity = {'customer_email': address, 'customer_name': name,
                'shopify_customer_id': '', 'identity_source': 'guest',
                'email_marketing_state': 'UNKNOWN'}
    # The posted customer ID is deliberately never consulted. Phrase search can
    # be broad, so independently compare exact normalized emails on every page.
    try:
        shop = crm_shopify.Shopify()
        query = 'email:"' + address.replace('\\', '\\\\').replace('"', '\\"') + '"'
        matches = {}
        cursor = None
        seen = set()
        for _ in range(3):
            page = shop.customers(query=query, fresh=True, after=cursor)
            if page.get('complete') is False:
                raise ValueError('Incomplete customer lookup')
            for customer in page['nodes']:
                if email(customer.get('email')) == address:
                    customer_id = crm_shopify.gid(customer.get('id'))
                    if customer_id:
                        matches[customer_id] = customer
            info = page['pageInfo']
            if type(info.get('hasNextPage')) is not bool:
                raise ValueError('Incomplete customer pagination')
            if not info['hasNextPage']:
                break
            cursor = info.get('endCursor')
            if not cursor or cursor in seen:
                raise ValueError('Incomplete customer pagination')
            seen.add(cursor)
        else:
            raise ValueError('Customer lookup bound reached')
        if len(matches) == 1:
            customer_id, customer = next(iter(matches.items()))
            canonical_name = ' '.join(str(customer.get(key) or '').strip()
                                      for key in ('firstName', 'lastName')).strip()
            identity.update(customer_email=normalize_email(customer['email']),
                            customer_name=(canonical_name or name)[:200],
                            shopify_customer_id=customer_id,
                            identity_source=source,
                            email_marketing_state=marketing_state(customer)
                            if 'emailMarketingConsent' in customer or 'defaultEmailAddress' in customer else 'UNKNOWN')
    except Exception as error:
        logging.getLogger(__name__).warning('wall_preview_identity_lookup_unavailable error_type=%s', type(error).__name__)
    return identity


def customer_admin_url(customer_id):
    from shopify_sync import get_config
    identity = crm_shopify.gid(customer_id)
    domain = str(get_config().get('store_domain') or '').lower()
    if not identity or not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com', domain):
        return ''
    return f"https://admin.shopify.com/store/{domain.split('.')[0]}/customers/{identity.rsplit('/', 1)[-1]}"
