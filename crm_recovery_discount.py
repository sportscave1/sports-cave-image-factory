"""Frozen per-email code selection, fresh eligibility guards, original recovery URL."""
from copy import deepcopy
from decimal import Decimal
from html import escape,unescape
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,quote
from crm_logic import date,now


class DiscountHold(ValueError):pass


def selection(doc):return doc.get('recovery_discount') or None


def validate(doc,trigger=None):
    saved=selection(doc)
    if not saved:return
    if trigger is not None and trigger!='abandoned':raise ValueError('Recovery discounts require an abandoned-checkout automation with an original recovery link.')
    if not isinstance(saved,dict) or set(saved)!={'id','code','value','type'}:raise ValueError('Select an existing Shopify discount.')
    if not isinstance(saved['id'],str) or not re.fullmatch(r'gid://shopify/Discount(?:Code)?Node/\d+',saved['id']):raise ValueError('Invalid Shopify discount identity.')
    if not isinstance(saved['code'],str) or not 1<=len(saved['code'])<=255 or any(ord(c)<32 or ord(c)==127 or c in '{}<>' for c in saved['code']):raise ValueError('Discount code cannot be safely included in a checkout link.')
    if not isinstance(saved['value'],str) or len(saved['value'])>1500 or not saved['value']:raise ValueError('Verified Shopify discount value is required.')
    from crm_discount_api import TYPES
    if saved['type'] not in TYPES:raise ValueError('This discount type cannot be verified for recovery links.')


def recovery_url(url,code,existing=()):
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or not re.search(r'/checkouts?/',parts.path):raise DiscountHold('discount_invalid_recovery_url: Original Shopify recovery URL could not be verified.')
    discounts=[v for k,v in parse_qsl(parts.query,keep_blank_values=True) if k.casefold()=='discount']
    if len(discounts)>1 or any(v.casefold()!=code.casefold() for v in [*discounts,*existing]):
        raise DiscountHold('discount_existing_code_conflict: Existing checkout code retained; review the offer before retrying.')
    if discounts:return url
    # Keep existing query bytes and fragment, including signed checkout parameters.
    query=parts.query+('&' if parts.query else '')+'discount='+quote(code,safe='')
    return urlunsplit((parts.scheme,parts.netloc,parts.path,query,parts.fragment))


def prepare(shop,doc,checkout,customer_id):
    if not selection(doc):return None
    validate(doc,'abandoned')
    from crm_discount_section import validate_presentation
    try:validate_presentation(doc)
    except ValueError as exc:raise DiscountHold('discount_copy_unverified: '+str(exc)) from None
    from crm_discount_api import fresh,CHECKOUT,AUTOMATIC,DiscountRemoved
    try:
        discount=fresh(shop,selection(doc));d=discount['facts'];clock=now()
        if not discount['supported']:raise DiscountHold('discount_unsupported: Select a compatible Shopify code.')
        if d['status']!='ACTIVE' or not date(d.get('startsAt')) or date(d['startsAt'])>clock or (date(d.get('endsAt')) and date(d['endsAt'])<=clock):
            raise DiscountHold('discount_not_active: Selected code is scheduled, inactive or expired. Review the email discount.')
        if discount['value']!=selection(doc)['value'] or discount['type']!=selection(doc)['type']:
            raise DiscountHold('discount_offer_changed: Shopify changed this offer. Reselect and republish after reviewing the copy.')
        if d.get('usageLimit') is not None and d.get('asyncUsageCount',0)>=d['usageLimit']:
            raise DiscountHold('discount_usage_limit: Selected code has reached its reported usage limit.')
        check=shop.query(CHECKOUT,{'id':checkout['id']},'recovery discount checkout verification',fresh=True)['node']
        if not check or check.get('completedAt') or check['id']!=checkout['id'] or (check.get('customer') or {}).get('id')!=customer_id or check['abandonedCheckoutUrl']!=checkout['abandonedCheckoutUrl']:
            raise DiscountHold('discount_checkout_changed: Revalidate the original checkout before sending.')
        target=recovery_url(check['abandonedCheckoutUrl'],discount['code'],check.get('discountCodes',[]))
        for item in (checkout.get('lineItems') or {}).get('nodes',[]):
            variant=item.get('variant') or {}
            if variant.get('availableForSale') is False or (variant.get('product') or {}).get('status') in ('DRAFT','ARCHIVED'):
                raise DiscountHold('discount_product_unavailable: Original checkout contains an unavailable product. Review before sending an offer.')
        minimum=d.get('minimumRequirement') or {};money=check.get('subtotalPriceSet',{}).get('shopMoney') or {}
        if minimum.get('__typename')=='DiscountMinimumSubtotal':
            required=minimum['greaterThanOrEqualToSubtotal']
            if money.get('currencyCode')!=required['currencyCode'] or Decimal(money.get('amount','0'))<Decimal(required['amount']):raise DiscountHold('discount_minimum_spend: Checkout does not meet the verified minimum spend.')
        if minimum.get('__typename')=='DiscountMinimumQuantity':
            lines=checkout.get('lineItems') or {}
            if (lines.get('pageInfo') or {}).get('hasNextPage') or sum(p.get('quantity',0) for p in lines.get('nodes',[]))<int(minimum['greaterThanOrEqualToQuantity']):raise DiscountHold('discount_minimum_quantity: Complete checkout quantity could not satisfy the minimum.')
        automatic=shop.query(AUTOMATIC,{},'automatic discount conflict verification',fresh=True)['discountNodes']
        if automatic['pageInfo']['hasNextPage']:raise DiscountHold('discount_combination_unknown: Too many automatic offers to verify safely.')
        for node in automatic['nodes']:
            offer=node['discount'];kind=offer['__typename']
            # Shopify documents an exception: a product code can remove BXGY.
            if kind=='DiscountAutomaticBxgy' and 'PRODUCT' in d.get('discountClasses',[]):raise DiscountHold('discount_multibuy_conflict: A product code could replace Buy X Get Y. Existing promotion retained; review combinations.')
            if kind=='DiscountAutomaticApp' or kind not in ('DiscountAutomaticBasic','DiscountAutomaticFreeShipping','DiscountAutomaticBxgy'):
                classes={'PRODUCT':'productDiscounts','ORDER':'orderDiscounts','SHIPPING':'shippingDiscounts'}
                if not offer.get('discountClasses') or not all(d.get('combinesWith',{}).get(classes.get(c,'')) for c in offer['discountClasses']) or not all(offer.get('combinesWith',{}).get(classes.get(c,'')) for c in d.get('discountClasses',[])):
                    raise DiscountHold('discount_app_combination_unknown: App-managed promotion combinations require review.')
        return {**discount,'original_url':check['abandonedCheckoutUrl'],'url':target}
    except DiscountHold:raise
    except DiscountRemoved:
        raise DiscountHold('discount_removed: Selected code was removed or replaced. Select an existing code and review the offer.') from None
    except Exception:
        raise DiscountHold('discount_verification_unavailable: Check Shopify discount read access and retry verification; no email was sent.') from None


def substitute(doc,discount=None):
    """Only the two discount tokens, on a render copy; never evaluates Liquid."""
    from crm_discount_section import validate_presentation
    validate_presentation(doc)
    result=deepcopy(doc);saved=selection(doc)
    values=discount or saved or {}
    tokens={'discount_code':values.get('code'),'discount_value':values.get('value')}
    def replace(text,html=False):
        if html and re.search(r'(?:href|src)\s*=\s*["\'][^"\']*{{\s*discount_',text,re.I):
            raise DiscountHold('discount_variable_in_url: Use discount variables in text. The recovery button applies its code automatically.')
        def one(match):
            value=tokens[match[1]]
            if not value:raise DiscountHold('discount_not_selected: Select a verified discount before using discount variables.')
            return escape(str(value),quote=True) if html else str(value)
        return re.sub(r'{{\s*(discount_code|discount_value)\s*}}',one,text)
    for key,value in result['content'].items():
        if ('url' in key or 'link' in key) and re.search(r'{{\s*discount_',value):raise DiscountHold('discount_variable_in_url: Discount variables belong in offer text, not URLs.')
        result['content'][key]=replace(value)
    import unicodedata
    for field in ('subject','preheader'):
        value=result['content'][field]
        if any(unicodedata.category(c).startswith('C') for c in value):raise DiscountHold('discount_invalid_header: Offer text contains control characters.')
        if len(value)>250 and re.search(r'{{\s*discount_',doc['content'][field]):raise DiscountHold('discount_header_too_long: Shorten the personalised subject or preview.')
    def block_values(value):
        if isinstance(value,str):return replace(value)
        if isinstance(value,list):return [block_values(v) for v in value]
        if isinstance(value,dict):
            for key,v in value.items():
                if isinstance(v,str) and ('url' in key or 'link' in key) and re.search(r'{{\s*discount_',v):raise DiscountHold('discount_variable_in_url: Discount variables belong in offer text, not URLs.')
            return {k:block_values(v) for k,v in value.items()}
        return value
    if 'blocks' in result:result['blocks']=block_values(result['blocks'])
    for field in ('custom_html',):
        if field in result:result[field]=replace(result[field],True)
    if 'html_sections' in result:result['html_sections']={k:replace(v,True) for k,v in result['html_sections'].items()}
    for section in result.get('middle_sections',[]):
        if section.get('type')=='discount':
            # Render-only lowering reuses every existing HTML recovery/link and
            # safety transform. The saved editable offer remains bound to Shopify.
            section['type']='image';section.pop('offer',None)
        if not section.get('visible',True):continue
        if 'html' in section:section['html']=replace(section['html'],True)
        if section.get('type')=='checkout_element':section['settings']=block_values(section['settings'])
    return result


def apply_links(message,discount):
    if not discount:return message
    original=urlsplit(discount['original_url']);required=parse_qsl(original.query,keep_blank_values=True);count=0
    def link(url):
        nonlocal count
        p=urlsplit(url)
        if (p.scheme,p.netloc,p.path)!=(original.scheme,original.netloc,original.path):return url
        if not all(pair in parse_qsl(p.query,keep_blank_values=True) for pair in required):return url
        count+=1;return recovery_url(url,discount['code'])
    result=dict(message)
    result['html']=re.sub(r'href="([^"]*)"',lambda m:'href="'+escape(link(unescape(m[1])),quote=True)+'"',message['html'])
    result['text']=re.sub(r'https://[^\s<>]+',lambda m:link(m[0]),message['text'])
    if not count:raise DiscountHold('discount_recovery_cta_missing: This email has no verified original-checkout CTA.')
    return result
