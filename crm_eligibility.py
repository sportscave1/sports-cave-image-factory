"""Shared global policy for campaigns and automations. Never persists profiles."""
from crm_resend_marketing import single_email


def eligible(customer, suppressed=False, provider_suppressed=False):
    customer = customer or {}
    address = customer.get('email')
    if not isinstance(address, str) or not single_email(address.strip().casefold()) or customer.get('validEmailAddress') is False:
        return False, 'consent_invalid'
    state = (customer.get('emailMarketingConsent') or {}).get('marketingState', 'NOT_SUBSCRIBED')
    if state != 'SUBSCRIBED':
        state = state if state in ('NOT_SUBSCRIBED','PENDING','INVALID','UNSUBSCRIBED','REDACTED') else 'NOT_SUBSCRIBED'
        return False, 'consent_' + state.lower()
    if suppressed: return False, 'local_suppression'
    if provider_suppressed: return False, 'provider_suppression'
    return True, ''


def consent_evidence(customer):
    """Safe fields available for future send-time evidence, not a profile mirror."""
    consent = (customer or {}).get('emailMarketingConsent') or {}
    return {k: consent.get(k) for k in ('marketingState','marketingOptInLevel','consentUpdatedAt')}
