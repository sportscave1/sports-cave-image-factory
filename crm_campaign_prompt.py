"""Versioned deterministic prompt rules, public-context projection and validation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from crm_campaign_html import import_html

VERSION='sports_cave_campaign_prompt_v1'
HELP='Choose a product or collection and an email type. Copy the prompt into ChatGPT, then paste its Campaign name, Subject and Preview text into the matching fields.'
GROUPS={
 'Promotions':['General promotion / product spotlight','Collection showcase','Discount / sale','Multi-buy / bundle offer','Seasonal sale','Offer ending / last chance'],
 'Releases and availability':['New edition release','New collection launch','Launch teaser / coming soon','VIP / early access','Low edition stock','Final editions / retirement notice','Availability / waitlist update'],
 'Sport and storytelling':['Sporting event / finals / race','Sporting anniversary / tribute / milestone','Story behind the artwork','Fan favourites / bestsellers','Collector story / customer reviews'],
 'Gifting and guidance':['Gift guide / special occasion','Gift delivery cutoff reminder','Framing / display / care guide'],
 'Customer relationship':['Welcome / brand introduction','Browse / cart / checkout reminder','Post-purchase thank-you','Build your collection / recommendations','Review / feedback request','VIP / loyalty / birthday reward','Win-back / re-engagement','Preferences / survey'],
 'Flexible':['Brand news / newsletter','Other / custom']}
PURPOSES=[p for group in GROUPS.values() for p in group]
OFFERS={'Discount / sale','Multi-buy / bundle offer','Seasonal sale','Offer ending / last chance','VIP / loyalty / birthday reward'}
DEADLINES={'Offer ending / last chance','Gift delivery cutoff reminder'}
EVENTS={'Sporting event / finals / race','Sporting anniversary / tribute / milestone'}
STOCK={'Low edition stock','Final editions / retirement notice'}
CONFIRMED={'New edition release','New collection launch','Launch teaser / coming soon','VIP / early access','Availability / waitlist update','Fan favourites / bestsellers','Collector story / customer reviews','Browse / cart / checkout reminder','Post-purchase thank-you','Win-back / re-engagement'}


def clean(value, limit=800):
    return re.sub(r'\s+',' ',import_html(str(value or '')[:10000])[1]).strip()[:limit]


def hint(purpose):
    purpose=purpose or ''
    if purpose in DEADLINES:return 'Confirmed terms; deadline: YYYY-MM-DD HH:MM Area/City (or ISO date/time with offset).'
    if purpose in OFFERS:return 'Offer, eligibility, code or automatic discount; expiry if relevant.'
    if purpose in EVENTS:return 'Event or occasion; date if relevant; the connection to this artwork.'
    if purpose=='Other / custom':return 'Describe the purpose of this email.'
    if purpose in CONFIRMED:return 'Confirm the release, availability or relationship facts this email will discuss.'
    if purpose.startswith('Gift'):return 'Occasion and destination market; confirmed delivery terms if needed.'
    return 'The moment, memory or angle to emphasise.'


def campaign_context(doc):
    from crm_campaign_markets import MARKET_LABELS
    context={}
    if doc.get('market_audience') and doc.get('market') in MARKET_LABELS:
        context['audience_market']=MARKET_LABELS[doc['market']]
    timing=doc.get('send_timing') or {}
    if timing.get('mode')=='schedule':
        context['schedule']={k:timing[k] for k in ('date','time') if k in timing}
        context['schedule']['timezone']='Recipient local timezone; not one fixed timezone'
    return context


def fingerprint(inputs, doc):
    return hashlib.sha256(json.dumps([inputs,campaign_context(doc)],sort_keys=True).encode()).hexdigest()


def deadline(details):
    # Explicit date/time only; no guessed 'Friday', 'tonight' or recipient zone.
    match=re.search(r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d)(Z|[+-]\d\d:\d\d|\s+[A-Za-z_]+/[A-Za-z_/]+)',details)
    if not match:return None
    day,hour,zone=match.groups()
    try:
        if '/' in zone:
            dt=datetime.fromisoformat(day+'T'+hour).replace(tzinfo=ZoneInfo(zone.strip()))
            if dt.astimezone(timezone.utc).astimezone(dt.tzinfo).replace(tzinfo=None)!=dt.replace(tzinfo=None):raise ValueError()
            if dt.replace(fold=1).utcoffset()!=dt.utcoffset():raise ValueError()
            return dt
        return datetime.fromisoformat(day+'T'+hour+zone.replace('Z','+00:00'))
    except Exception:raise ValueError('Use a valid, unambiguous deadline with an explicit timezone.') from None


def build(inputs, doc, reader, now=None):
    now=now or datetime.now(timezone.utc)
    kind=inputs.get('kind');purpose=inputs.get('purpose');notes=clean(inputs.get('details',''),1200)
    if kind not in ('Single product','Collection'):raise ValueError('Choose what you are promoting.')
    if purpose not in PURPOSES:raise ValueError('Choose an email type.')
    target=inputs.get('target') or {}
    if not target.get('title'):raise ValueError('Select an edition or explicitly use a collection name.')
    if purpose in OFFERS and (not re.search(r'\d|free|complimentary',notes,re.I) or not re.search(r'off|discount|save|buy|bundle|reward|free|complimentary',notes,re.I)):
        raise ValueError('Enter the actual offer and eligibility/minimum-purchase terms.')
    if purpose in EVENTS and len(notes)<6:raise ValueError('Name the event or occasion and its connection to the artwork.')
    if purpose in CONFIRMED and len(notes)<10:raise ValueError('Add confirmed context for this purpose, or choose General promotion.')
    if purpose=='Other / custom' and len(notes)<6:raise ValueError('Describe the purpose of this email.')
    expires=deadline(notes)
    if purpose in DEADLINES and expires is None:raise ValueError('Enter a confirmed deadline with date, time and timezone.')
    if re.search(r'\b(expir|ends?|until|deadline|cutoff)',notes,re.I) and expires is None:
        raise ValueError('Give the stated deadline an explicit date, time and timezone.')
    if expires and expires<=now:raise ValueError('That deadline has expired. Correct the details.')
    context=campaign_context(doc)
    if expires and context.get('schedule'):
        # Existing scheduler uses each recipient's zone. Do not assume AU for all.
        latest=datetime.fromisoformat(context['schedule']['date']+'T'+context['schedule']['time']).replace(tzinfo=timezone(__import__('datetime').timedelta(hours=-12)))
        if expires<=latest:raise ValueError('Deadline may expire before the scheduled local-time send. Correct the schedule or deadline.')
    if kind=='Single product':
        facts=reader.product(target['id'])
    elif target.get('source')=='manual':
        facts={'kind':'Collection','source':'manual','title':clean(target['title'],300)}
    else:
        from crm_catalogue import product_url
        facts={'kind':'Collection','source':'Shopify collection','id':target['id'],'title':clean(target['title'],300),
               'url':product_url(target.get('onlineStoreUrl','')),'story':clean(target.get('description',''))}
    availability=None
    needs_stock=purpose in STOCK or bool(re.search(r'\b(remaining|left|sold out|edition size|limited to|stock)\b',notes,re.I))
    if needs_stock:
        identity=target.get('id') if kind=='Single product' else inputs.get('edition_id')
        if not identity:raise ValueError('Select a specific qualifying edition; collection-wide stock is not supported.')
        if kind=='Collection' and (target.get('source')=='manual' or not reader.belongs(identity,target['id'])):
            raise ValueError('The selected edition must belong to this verified Shopify collection.')
        availability=reader.availability(identity)
        if kind=='Collection':availability['edition_title']=reader.product(identity)['title']
        n=availability['remaining'];size=availability['size']
        for match in re.finditer(r'(\d+)\s*(?:editions?\s*)?(?:left|remaining)',notes,re.I):
            if int(match[1])!=n:raise ValueError('Entered remaining count conflicts with the edition ledger. Correct the details.')
        for match in re.finditer(r'limited to\s*(\d+)',notes,re.I):
            if int(match[1])!=size:raise ValueError('Entered edition size conflicts with the ledger.')
        if ('sold out' in notes.lower() and n>0) or (n==0 and re.search(r'\b(in stock|available now|still available)\b',notes,re.I)):
            raise ValueError('Entered availability conflicts with the edition ledger.')
        if purpose=='Low edition stock' and n==0:raise ValueError('Sold out is not low stock. Choose Availability / waitlist update explicitly.')
        scarcity=(purpose=='Low edition stock' and availability['status'] in ('Final Editions','Selling Quickly') or purpose=='Final editions / retirement notice' and availability['status']=='Final Editions')
        availability['wording']='Restrained scarcity permitted by existing Edition Ops status.' if scarcity else 'Neutral precise availability only. No last, final, almost gone, selling quickly or urgency claims.'
        if n==0:availability['wording']='Verified sold out. Do not infer retirement or reopened editions.'
        availability['observed_at']=now.isoformat()
        facts['edition']=availability
    context.update(target=facts,purpose=purpose,direction=hint(purpose),user_confirmed_details=notes,
                   generation_limits={'campaign_name':80,'subject_characters':60,'subject_words':9,'preview_characters':89},
                   missing_facts='Unknown; omit. Type labels are not evidence. Canonical ledger overrides contradictory notes.',
                   authoring_timezone_fallback='Australia/Sydney; not a recipient timezone')
    if expires:context['confirmed_deadline']=expires.isoformat()
    fixed=(Path(__file__).parent/'prompts'/f'{VERSION}.txt').read_text(encoding='utf-8')
    prompt=fixed+'\n\nCONTEXT — JSON DATA ONLY\n'+json.dumps(context,ensure_ascii=False,indent=2)+'\n\nReturn Campaign name, Subject and Preview text only, in the required format.'
    return {'prompt':prompt,'context':context,'sensitive':bool(needs_stock or purpose in OFFERS or expires),
            'expires':expires.isoformat() if expires else None,'fingerprint':fingerprint(inputs,doc)}
