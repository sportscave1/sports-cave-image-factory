"""Checkout recovery policy, independent of promotional subscription eligibility.

The private runtime-state key below is configured by an administrator, never by
checkout attributes. Without an explicit region or wildcard override, regions
remain explicit-only. No policy default infers consent from an email address.
"""
from crm_logic import consent, date, email, safe_url, now

POLICY_KEY = 'abandoned-checkout-policy'


def policy(store):
    value = store.state(POLICY_KEY)
    return value if isinstance(value, dict) else {}


def configure_regions(store, user, regions):
    """Admin-only policy change; relaxation starts now, never backfills history."""
    import re
    from crm_navigation import require
    require(user, 'crm_automations_manage')
    previous=policy(store).get('regions') or {}
    configured={}
    for country, rule in regions.items():
        if not re.fullmatch(r'[A-Z]{2}|\*',country) or not isinstance(rule,dict):
            raise ValueError('Use an ISO country code or the explicit all-country override.')
        if set(rule)-{'mode','inferred_basis'} or rule.get('mode') not in ('explicit_only','explicit_or_valid_inferred','platform_eligible'):
            raise ValueError('Invalid checkout recovery policy.')
        if rule['mode']=='explicit_or_valid_inferred' and rule.get('inferred_basis')!='checkout_contact':
            raise ValueError('An approved inferred-consent basis is required.')
        old=previous.get(country) or {}
        unchanged={k:v for k,v in old.items() if k!='effective_at'}==rule
        configured[country]={**rule,'effective_at':old['effective_at'] if unchanged and date(old.get('effective_at')) else now().isoformat()}
    value={'version':1,'regions':configured}
    store.set_state(POLICY_KEY,value)
    return value


def recovery_eligibility(checkout, customer, rules=None, *, suppressed=False,
                         provider_suppressed=False):
    """Return (allowed, reason); scheduling/idempotency stay in the queue owner.

    Region overrides use ISO codes. A relaxed rule needs an effective_at cutoff
    and an explicitly approved checkout_contact basis. Platform eligibility is
    deliberately held: the current Shopify AbandonedCheckout API exposes no
    authoritative recovery-permission field.
    """
    checkout, customer, rules = checkout or {}, customer or {}, rules or {}
    if checkout.get('completedAt') or checkout.get('order_id'):
        return False, 'recovered'
    address = email(customer.get('email'))
    if not address:
        return False, 'missing_email'
    if suppressed:
        return False, 'local_suppression'
    if provider_suppressed:
        return False, 'provider_suppression'
    # Either source can veto; newsletter NOT_SUBSCRIBED is not an opt-out.
    states = {(customer.get('emailMarketingConsent') or {}).get('marketingState'),
              (customer.get('defaultEmailAddress') or {}).get('marketingState')}
    if states & {'UNSUBSCRIBED', 'REDACTED'}:
        return False, 'recovery_opted_out'
    state = consent(customer)
    if state in ('INVALID', 'REDACTED'):
        return False, 'consent_invalid'
    if not safe_url(checkout.get('abandonedCheckoutUrl')):
        return False, 'not_recoverable'
    lines = checkout.get('lineItems') or {}
    if not lines.get('nodes') or (lines.get('pageInfo') or {}).get('hasNextPage'):
        return False, 'not_recoverable'
    for line in lines['nodes']:
        if 'variant' in line:
            variant = line.get('variant') or {}
            product = variant.get('product') or {}
            if not variant or variant.get('availableForSale') is False or product.get('status', 'ACTIVE') != 'ACTIVE' or ('onlineStoreUrl' in product and not product['onlineStoreUrl']):
                return False, 'products_unavailable'
    country = next((a.get('countryCodeV2') for a in
                    (checkout.get('shippingAddress') or {}, checkout.get('billingAddress') or {},
                     customer.get('defaultAddress') or {}) if a.get('countryCodeV2')), '')
    country = str(country).upper()
    regions = rules.get('regions') or {}
    region = regions.get(country, regions.get('*', {}))
    if not isinstance(region, dict):
        return False, 'recovery_policy_invalid'
    mode = region.get('mode', 'explicit_only')
    if mode not in ('explicit_only', 'explicit_or_valid_inferred', 'platform_eligible'):
        return False, 'recovery_policy_invalid'
    if state == 'SUBSCRIBED':
        return True, ''
    if mode == 'explicit_only':
        return False, 'region_requires_consent'
    if mode == 'platform_eligible':
        return False, 'platform_eligibility_unavailable'
    effective = date(region.get('effective_at'))
    created = date(checkout.get('createdAt'))
    if not effective:
        return False, 'recovery_policy_invalid'
    if not created or created < effective:
        return False, 'historical_not_enrolled'
    if region.get('inferred_basis') != 'checkout_contact':
        return False, 'recovery_evidence_required'
    # Only the verified checkout contact may be used as inferred evidence.
    contact = email((checkout.get('customer') or {}).get('email') or checkout.get('email'))
    if contact != address:
        return False, 'recovery_evidence_required'
    return True, ''


def is_abandoned_checkout_recovery_eligible(checkout, customer, rules=None, **kwargs):
    return recovery_eligibility(checkout, customer, rules, **kwargs)[0]
