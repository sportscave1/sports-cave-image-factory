"""Editable offer presentation; Shopify selection remains the authority."""
from copy import deepcopy
from html import unescape
import re
import uuid

class DiscountPresentationError(ValueError):
    """Safe, actionable offer-copy validation message for the editor."""


def offer_sections(doc):
    return [s for s in doc.get('middle_sections',[]) if s.get('type')=='discount']


def default_html():
    return '''<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="background-color:#171717;color:#ffffff;border:1px solid #b49450;padding:18px 22px;font-family:Arial,Helvetica,sans-serif;text-align:center">
<p style="margin:0 0 8px;font-size:11px;letter-spacing:1px;color:#dfc986">AN EXCLUSIVE COLLECTOR OFFER</p>
<h2 style="margin:0 0 8px;font-size:24px;font-weight:700">{{discount_value}}</h2>
<p style="margin:0;font-size:14px;line-height:1.5">Use code <strong>{{discount_code}}</strong> when you complete your order.</p>
<p style="margin:8px 0 0;font-size:11px;color:#cccccc">Eligibility and combinations are confirmed by Shopify at checkout.</p>
</td></tr></table>'''


def section(offer=None, *, identity=None):
    return {'id':identity or uuid.uuid4().hex,'type':'discount','visible':True,
            'offer':deepcopy(offer),'html':default_html()}


def migrate_editor(doc):
    """Editor copy only; callers establish their clean baseline afterwards."""
    result=deepcopy(doc)
    if result.get('recovery_discount') and not offer_sections(result) and result.get('discount_association_version')!=1:
        from crm_middle_sections import middle_sections
        result['middle_sections']=middle_sections(result)+[section(result['recovery_discount'],identity='legacy-recovery-discount')]
    return result


def sync(doc, sections, *, managed=False):
    # Presentation changes never attach or detach a checkout offer. Existing
    # snapshots retain their original selection; explicit picker actions own it.
    offers=[s['offer'] for s in sections if s.get('type')=='discount' and s.get('offer')]
    if any(o!=offers[0] for o in offers[1:]):
        raise ValueError('Use one Shopify offer per email. Change the discount on all appearances before showing this section.')
    if managed or offers or doc.get('recovery_discount'):doc['discount_association_version']=1


def disconnect(doc):
    doc.pop('recovery_discount',None)
    doc['discount_association_version']=1
    for s in offer_sections(doc):s['offer']=None


def insert(doc, row, event, *, trigger):
    if trigger!='abandoned':raise ValueError('Recovery discounts require an abandoned-checkout email with its original recovery link.')
    from crm_discount_api import selectable
    reason=selectable(row)
    if reason:raise ValueError(reason)
    from crm_middle_sections import apply_event, middle_sections, commit_middle
    updated=deepcopy(doc)
    # Capture pending HTML in the same transaction; never trust an offer supplied
    # by the browser. The caller passes the selected server-side Shopify row.
    apply_event(updated,{**event,'type':'order','ids':event.get('base')})
    sections=middle_sections(updated)
    offer={k:row[k] for k in ('id','code','value','type')}
    from crm_recovery_discount import validate
    validate({'recovery_discount':offer},trigger)
    existing=[s for s in sections if s['type']=='discount']
    if existing:
        for s in existing:s['offer']=deepcopy(offer)
        target=next((s for s in existing if s['id']==event.get('section_id')),existing[0])
        target['visible']=True
    else:sections.append(section(offer))
    updated['recovery_discount']=deepcopy(offer)
    commit_middle(updated,sections)
    doc.clear();doc.update(updated)


def validate_presentation(doc):
    """Hold misleading numeric offer claims; preserve invalid draft text for repair."""
    selected=doc.get('recovery_discount')
    for s in offer_sections(doc):
        if not s['visible']:continue
        if s.get('offer') and s['offer']!=selected:raise DiscountPresentationError('Discount section does not match this email’s selected Shopify offer.')
        source=s['html']
        # Check customer-visible text, not CSS dimensions or colours.
        from html.parser import HTMLParser
        class Text(HTMLParser):
            def __init__(self):super().__init__();self.parts=[];self.skip=0
            def handle_starttag(self,tag,attrs):
                if tag in ('style','script'):self.skip+=1
            def handle_endtag(self,tag):
                if tag in ('style','script'):self.skip=max(0,self.skip-1)
            def handle_data(self,data):
                if not self.skip:self.parts.append(data)
        parser=Text();parser.feed(source);text=' '.join(parser.parts)
        # Presentation may omit the amount; the verified offer remains in offer /
        # recovery_discount, independently of layout and token placement.
        plain=re.sub(r'{{\s*discount_(?:code|value)\s*}}','[verified]',unescape(text))
        # Code/amount placeholders are optional. A literal promotional claim
        # must still be tied to a verified selection at publication/delivery.
        for code in re.findall(r'\b(?:use\s+code|promo\s+code|coupon\s+code|code\s*:)\s*([A-Za-z0-9_-]+)',plain,re.I):
            if not selected or code.casefold()!=selected['code'].casefold():
                raise DiscountPresentationError('The written discount code does not match the selected Shopify offer.')
        if not selected and re.search(r'\b(?:discount|offer|coupon|courtesy code|save|free shipping|free gift)\b',plain,re.I):
            raise DiscountPresentationError('Connect a verified Shopify offer or remove unverified promotional claims before publishing.')
        if re.search(r'(?:[$£€]\s*\d|\d[\d.,]*\s*(?:%|percent|dollars?|pounds?|euros?)|\b(?:one|two|five|ten|twenty|fifty|hundred)\s+(?:percent|dollars?|pounds?)|\bhalf[ -]price\b)',plain,re.I):
            raise DiscountPresentationError('Use {{discount_value}} for the offer amount. Manually entered amounts or percentages cannot be verified against Shopify.')
        if re.search(r'\b(?:free shipping|buy\s+\d+\s+get\s+\d+)\b',plain,re.I):
            raise DiscountPresentationError('Use {{discount_value}} for the offer type and conditions, rather than an unverified promotion claim.')
