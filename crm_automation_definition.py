"""Native automation definitions around the shared email document contract."""
from copy import deepcopy
import uuid
from crm_campaign_content import new_document, validate_document

FORMAT = 'automation_flow_v1'
# Only sources already supported by the signed event / Shopify read pipeline.
TRIGGERS = {
    'welcome': ('Welcome series', 'Customer subscribes to email', 'customers_email_marketing_consent/update'),
    'post_purchase': ('Post-purchase', 'Order paid', 'orders/paid'),
    'abandoned': ('Abandoned checkout', 'Checkout abandoned', 'checkouts/create + checkouts/update'),
    'fulfilled': ('Fulfilment follow-up', 'Order fulfilled', 'orders/fulfilled'),
    'win_back': ('Win Back', 'Customer inactive', 'Shopify customer / last order polling'),
}
MARKETS = ('Any', 'AU', 'NZ', 'US', 'UK', 'CA')
RULE_FIELDS={'market':'Market','customer_country':'Customer country','checkout_country':'Checkout country','product_purchased':'Product purchased','order_value':'Order value'}


def email_step(document=None, delay_seconds=0):
    return {'step_id': str(uuid.uuid4()), 'delay_seconds': delay_seconds,
            'document': deepcopy(document or new_document())}


def new_flow(trigger='welcome'):
    if trigger not in TRIGGERS: raise ValueError('Choose a supported trigger.')
    return {'trigger': trigger, 'rules': [], 'reentry_days': 0, 'emails': [email_step()], 'timing_version': 2}


def validate(flow):
    if not isinstance(flow, dict) or set(flow)-{'trigger','rules','reentry_days','emails','abandonment_seconds','review_request','timing_version','inactive_days','exit_on_purchase'} or not {'trigger','rules','reentry_days','emails'}.issubset(flow):
        raise ValueError('Invalid automation definition.')
    if flow.get('timing_version',1) not in (1,2) or (flow.get('timing_version')==2 and 'abandonment_seconds' in flow):
        raise ValueError('Use the single Delay setting for this flow.')
    if 'review_request' in flow:
        from reviews_model import product_gid
        from crm_tracking import public_https
        request=flow['review_request']
        if flow['trigger']!='fulfilled' or not isinstance(request,dict) or set(request)!={'product_id','base_url'} or not product_gid(request['product_id']) or not public_https(request['base_url']):
            raise ValueError('Review requests require an exact product and fulfilment trigger.')
    if type(flow.get('abandonment_seconds',3600)) is not int or not 60<=flow.get('abandonment_seconds',3600)<=7*86400:
        raise ValueError('Abandonment qualification must be between one minute and seven days.')
    if flow['trigger'] not in TRIGGERS: raise ValueError('Choose a supported trigger.')
    if type(flow.get('inactive_days',180)) is not int or not 1<=flow.get('inactive_days',180)<=3650:raise ValueError('Inactivity must be 1–3650 days.')
    if type(flow.get('exit_on_purchase',True)) is not bool:raise ValueError('Invalid purchase exit.')
    if flow['trigger'] in ('abandoned','win_back') and not flow.get('exit_on_purchase',True):raise ValueError('Recovery flows must exit on purchase.')
    if type(flow['reentry_days']) is not int or flow['reentry_days'] not in (0,7,30,90):
        raise ValueError('Choose once ever or a 7, 30 or 90 day re-entry cooldown.')
    if not isinstance(flow['rules'], list) or len(flow['rules']) > 12:
        raise ValueError('Use at most twelve simple AND rules.')
    for rule in flow['rules']:
        if not isinstance(rule,dict) or set(rule) != {'field','condition','value'} or rule['field'] not in RULE_FIELDS or rule['condition'] != ('at_least' if rule['field']=='order_value' else 'is'):
            raise ValueError('Use a supported exact AND rule.')
        if rule['field']=='market' and rule['value'] not in MARKETS[1:]:raise ValueError('Choose a supported market.')
        if rule['field'] in ('customer_country','checkout_country'):
            import re
            if not isinstance(rule['value'],str) or not re.fullmatch('[A-Z]{2}',rule['value']):raise ValueError('Use an ISO country code.')
        if rule['field']=='checkout_country' and flow['trigger']!='abandoned':raise ValueError('Checkout country requires a checkout trigger.')
        if rule['field'] in ('product_purchased','order_value'):
            import re
            if flow['trigger'] not in ('post_purchase','fulfilled'):raise ValueError('Order rules require a paid/fulfilled order trigger.')
            pattern=r'gid://shopify/Product/\d+' if rule['field']=='product_purchased' else r'[A-Z]{3} [0-9]{1,9}(?:\.[0-9]{1,2})?'
            if not isinstance(rule['value'],str) or not re.fullmatch(pattern,rule['value']):raise ValueError('Use a product GID or currency and amount (for example AUD 100).')
    if not isinstance(flow['emails'],list) or not flow['emails']: raise ValueError('Add an email.')
    seen=set()
    for step in flow['emails']:
        if not isinstance(step,dict) or set(step)-{'step_id','delay_seconds','document','name','enabled'} or not {'step_id','delay_seconds','document'}.issubset(step): raise ValueError('Invalid email step.')
        if type(step.get('enabled',True)) is not bool:raise ValueError('Invalid email enabled state.')
        if not isinstance(step.get('name',''),str) or len(step.get('name',''))>150:raise ValueError('Email names must be at most 150 characters.')
        try:identity=str(uuid.UUID(step['step_id']))
        except (ValueError,TypeError,AttributeError):raise ValueError('Invalid email step identity.') from None
        if identity in seen: raise ValueError('Duplicate email step identity.')
        seen.add(identity)
        if type(step['delay_seconds']) is not int or not 0 <= step['delay_seconds'] <= 365*86400:
            raise ValueError('Email delay must be between immediately and one year.')
        validate_document(step['document'])
        from crm_recovery_discount import validate as validate_discount
        validate_discount(step['document'],flow['trigger'])
        from crm_personalisation import validate as validate_personalisation
        validate_personalisation(step['document'],flow['trigger'])
    return flow


def qualifies(flow, customer, event_facts=None):
    from crm_campaign_markets import country, COUNTRIES
    from decimal import Decimal,InvalidOperation
    facts=event_facts or {}
    for r in flow['rules']:
        field,value=r['field'],r['value']
        if field in ('market','customer_country'):
            if country(customer)!=(COUNTRIES[value] if field=='market' else value):return False
        elif field=='checkout_country':
            if facts.get(field)!=value:return False
        elif field=='product_purchased':
            if value not in facts.get(field,set()):return False
        elif field=='order_value':
            money=facts.get(field) or {};currency,amount=value.split(' ')
            try:
                measured=Decimal(money.get('amount',''))
                if money.get('currencyCode')!=currency or not measured.is_finite() or measured<Decimal(amount):return False
            except (InvalidOperation,TypeError):return False
        else:return False
    return True


def production_document(doc):
    """Recipient counts are runtime authority, never a bulk audience calculation."""
    from crm_logic import now
    result=deepcopy(doc)
    result.pop('market_audience',None)
    result.pop('send_timing',None)
    result['counts']={'members':1,'eligible':1,'excluded':{},'complete':True,'checked_at':now().isoformat()}
    return result


def status(row):
    cfg=row.get('config') or {}
    return 'ARCHIVED' if cfg.get('archived_at') else row['status']


def native(row):
    return (row.get('config') or {}).get('format') == FORMAT
