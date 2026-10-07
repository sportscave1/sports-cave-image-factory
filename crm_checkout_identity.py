"""Verified checkout presentation and recovery evidence; no network or sends."""
import re
from crm_logic import email, date


def usable_name(value):
    value=' '.join(str(value or '').split())[:200]
    return '' if re.fullmatch(r'(?:Customer\s+)?\d+|gid://shopify/.*',value,re.I) else value


def identity(checkout):
    customer=checkout.get('customer') or {}
    name=''
    for source in (customer,checkout,checkout.get('shippingAddress') or {},checkout.get('billingAddress') or {}):
        name=usable_name(' '.join(str(source.get(k) or '') for k in ('firstName','lastName')))
        if not name and source is not checkout:name=usable_name(source.get('name'))
        if name:break
    raw_address=customer.get('email') or (customer.get('defaultEmailAddress') or {}).get('emailAddress') or checkout.get('email')
    address=email(raw_address)
    region=next((a for a in (checkout.get('shippingAddress') or {},checkout.get('billingAddress') or {}) if a.get('countryCodeV2') or a.get('country')), {})
    return {'name':name,'email':address,'email_state':'invalid' if raw_address and not address else 'present' if address else 'missing','country':region.get('countryCodeV2',''),
            'region':region.get('country',''),'reference':str(checkout.get('name') or '')[:100]}


def display_name(row):
    data=row.get('analytics') or {}
    return usable_name(data.get('name')) or email(data.get('email')) or 'Guest'


def recovered(row):
    return bool(row.get('order_id') or date((row.get('analytics') or {}).get('completed_at')) or row.get('completion_verified'))


def recovery_status(row):
    if recovered(row):return 'Recovered'
    if any(s.get('status')=='ACCEPTED' and s.get('provider_id') for s in row.get('sends',[])):return 'Not recovered'
    return 'Not sent'


def reference(row):
    value=(row.get('analytics') or {}).get('reference')
    if value:return value
    value=str(row.get('admin_checkout_id') or '').rsplit('/',1)[-1]
    return '#'+value if value else 'Unavailable'


def block_label(reason):
    return {'local_suppression':'Suppressed','provider_suppression':'Suppressed',
            'consent_not_subscribed':'Marketing consent required','consent_unsubscribed':'Unsubscribed','consent_invalid':'Invalid email',
            'missing_email':'Missing email','recovered':'Recovered',
            'already_enrolled':'Already in flow'}.get(reason,'Not eligible')


def recipient(shop,store,checkout,ledger):
    """Guest account state is irrelevant; verified consent and opt-out still apply."""
    customer_id=(checkout.get('customer') or {}).get('id')
    if customer_id:return shop.customer(customer_id,fresh=True)
    address=email((ledger.get('analytics') or {}).get('email'))
    if not address:raise ValueError('Missing email')
    candidates=[c for c in shop.campaign_email_profiles([address]) if email(c.get('email'))==address]
    if len(candidates)!=1:raise ValueError('Not eligible: verified consent identity unavailable')
    return candidates[0]


def retry_send(store,user,send_id):
    """Explicit retry of a confirmed rejection only; unknown submissions stay held."""
    from crm_navigation import require
    require(user,'crm_automations_manage')
    return store.q("""UPDATE crm_marketing_sends s SET status='PENDING',due_at=now(),lease_until=NULL
      FROM crm_automation_enrollments j JOIN crm_automations a ON a.id=j.automation_id
      WHERE s.id=%s AND s.enrollment_id=j.id AND j.checkout_key IS NOT NULL
      AND s.status='FAILED' AND s.error_code='provider_rejected' AND s.provider_email_id IS NULL
      AND a.status='ACTIVE' AND j.status='ACTIVE'
      AND NOT EXISTS(SELECT 1 FROM crm_shopify_checkouts c WHERE c.checkout_key=j.checkout_key AND c.status='RECOVERED')
      RETURNING s.id""",(send_id,),True)
