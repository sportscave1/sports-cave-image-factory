"""Deterministic customer requests. Email text is data, never executable instructions."""
import re
from datetime import datetime, timezone, timedelta

COUNTRIES={'australia':'AU','au':'AU','united states':'US','usa':'US','us':'US',
           'united kingdom':'GB','uk':'GB','gb':'GB','new zealand':'NZ','nz':'NZ','canada':'CA','ca':'CA'}
LABELS={'name':'name','recipient':'name','full name':'name','address':'line1','address line 1':'line1',
        'street address':'line1','address line 2':'line2','city':'townOrCity','town':'townOrCity',
        'town/city':'townOrCity','suburb':'townOrCity','state':'stateOrCounty','province':'stateOrCounty',
        'county':'stateOrCounty','postcode':'postalOrZipCode','postal code':'postalOrZipCode',
        'zip':'postalOrZipCode','zip code':'postalOrZipCode','country':'countryCode'}

def verified_sender(message,sender,trusted_ids):
    """Only the receiving provider's first authentication result may authorise automation.

    Configure trusted IDs only after verifying the provider strips spoofed copies
    of its own authserv-id. Missing/unrecognised metadata remains review-only.
    """
    values=message.get_all('Authentication-Results',[])
    if not values or '@' not in sender:return False
    parts=str(values[0]).split(';')
    authority=parts[0].strip().split() if parts else []
    if not authority or authority[0].casefold() not in {s.strip().casefold() for s in trusted_ids if s.strip()}:return False
    # Bind the assertion to the actual receiving hop, not a lower sender-supplied result.
    receiver=re.search(r'\bby\s+([A-Za-z0-9.-]+)',str(message.get('Received','')),re.I)
    if not receiver or receiver[1].casefold()!=authority[0].casefold():return False
    domain=sender.rsplit('@',1)[1].casefold()
    results=[p.strip() for p in parts[1:] if re.match(r'^dmarc\s*=',p.strip(),re.I)]
    if results:
        if len(results)!=1 or not re.match(r'^dmarc\s*=\s*pass(?:\s|$)',results[0],re.I):return False
        domains=re.findall(r'\bheader\.from\s*=\s*"?([A-Za-z0-9.-]+)',results[0],re.I)
        return len(domains)==1 and domains[0].casefold()==domain
    # VentraIP reports DKIM in its first backend result and SPF separately,
    # without a DMARC result. Require strict From-domain-aligned DKIM pass.
    for result in parts[1:]:
        if not re.match(r'^\s*dkim\s*=\s*pass(?:\s|$)',result,re.I):continue
        domains=re.findall(r'\bheader\.d\s*=\s*"?([A-Za-z0-9.-]+)',result,re.I)
        if len(domains)==1 and domains[0].casefold()==domain:return True
    return False

def authored(text):
    lines=[]
    for line in str(text or '').splitlines():
        if re.match(r'^\s*(>|On .+wrote:|From:|[-_]{3,}\s*(Original|Forwarded))',line,re.I):break
        lines.append(line)
    return '\n'.join(lines).strip()[:16000]

def classify(subject,text,*,is_reply=False):
    body=authored(text);value=(str(subject)+'\n'+body).lower()
    # A narrowly explicit billing-only correction does not change delivery.
    # Full-match authored text so mixed/ambiguous requests still require review.
    billing_only=re.fullmatch(r"\s*(?:(?:my|the)\s+)?billing\s+address\s+(?:(?:is|was)\s+)?(?:incorrect|wrong)[.!?\s]*",body,re.I)
    if billing_only and not re.search(r'\b(shipping|delivery|ship|deliver|cancel|cancellation|refund|hold|pause|frame|size|colour|color|product|artwork)\b',str(subject),re.I):
        return {'kind':'ignore','text':body,'reason':'billing_only'}
    # An order number in a quoted historical exchange is not a new instruction.
    product=bool(re.search(r'\b(size|frame|colour|color|cancel|cancellation|refund|hold|pause|product|artwork)\b',value))
    address=bool(re.search(r'\b(address|postcode|zip|deliver to|ship to|shipping details)\b',value))
    # Reply subjects retain old instructions. "Thanks" in that thread is not another change.
    intent=body.lower() if is_reply or re.match(r'^\s*(re|fw|fwd)\s*:',str(subject),re.I) else value
    if re.match(r'^\s*(thanks|thank you|cheers|perfect|all good)\b',body,re.I) and not re.search(r'\b(but|however|please|can you|could you|i need)\b',body,re.I):
        return {'kind':'ignore','text':body}
    change=bool(re.search(r'\b(change|cancel|cancellation|refund|amend|switch|swap|replace|upgrade|downgrade|wrong|incorrect|correction|mistake|instead|hold|pause|different)\b',intent))
    change=change or bool((address or product) and re.search(r'\b(update|correct|confirm)\b',intent))
    change=change or bool(address and re.search(r'\b(new address|updated address|(?:ship|deliver|send|post)\s+(?:it\s+|my order\s+)?to)\b',intent))
    change=change or bool(product and re.search(r'\b(?:can|could|may) i (?:get|have)\b',intent))
    if not change:return {'kind':'ignore','text':body}
    if re.search(r"\b(?:do not|don't|no need to)\s+(?:change|update|cancel)\b",value):return {'kind':'hold','text':body}
    kind='hold' if product or not address else 'address'
    return {'kind':kind,'text':body}

def match_order(header,text,orders,now=None):
    sender=str(header.get('sender',{}).get('email','')).strip().casefold()
    if not sender or header.get('error') or header.get('automated'):return None
    if any(p.get('email','').strip().casefold()!=sender for p in header.get('reply_to',[])):return None
    numbers=set(re.findall(r'\bSC\s*(\d{3,12})\b',str(header.get('subject',''))+'\n'+authored(text),re.I))
    if len(numbers)>1:return None
    now=now or datetime.now(timezone.utc)
    candidates=[]
    for order in orders:
        if str(order.get('customer_email','')).strip().casefold()!=sender:continue
        number=re.sub(r'^#?SC','',str(order.get('order_name','')),flags=re.I)
        if numbers and number not in numbers:continue
        try:stamp=datetime.fromisoformat(str(order['created_at']).replace('Z','+00:00'))
        except (ValueError,KeyError):continue
        if stamp.tzinfo is None or not now-timedelta(days=14)<=stamp<=now+timedelta(minutes=5):continue
        if order.get('fulfillment_status') in ('fulfilled','cancelled'):continue
        candidates.append(order)
    return candidates[0] if len(candidates)==1 else None

def address(text,old):
    """Only a complete explicit replacement, never compose old/new address fragments."""
    body=authored(text);fields={}
    for line in body.splitlines():
        m=re.fullmatch(r'\s*([A-Za-z /0-9]+)\s*:\s*(.*?)\s*',line)
        if not m:continue
        key=LABELS.get(m[1].lower())
        if key:
            if key in fields:return None
            fields[key]=m[2]
    # Common Australian / NZ / US address blocks: street, optional unit, city STATE ZIP, country.
    if not fields:
        lines=[s.strip(' ,') for s in body.splitlines() if s.strip()]
        blocks=[]
        for i,line in enumerate(lines):
            country=COUNTRIES.get(line.casefold())
            if not country or i<2:continue
            states=r'NSW|VIC|QLD|SA|WA|TAS|ACT|NT|New South Wales|Victoria|Queensland|South Australia|Western Australia|Tasmania|Australian Capital Territory|Northern Territory' if country=='AU' else r'[A-Za-z]{2}'
            match=re.fullmatch(r'(.+?)\s*,?\s+('+states+r')\s+(\d{4,5}(?:-\d{4})?)',lines[i-1],re.I)
            if not match:continue
            street=lines[i-2]
            if not re.match(r'^(?:\d+[A-Za-z]?(?:/\d+)?\s|(?:Unit|Apartment|Apt|Suite|PO Box)\s+\d)',street,re.I):continue
            blocks.append(dict(line1=street,line2='',townOrCity=match[1],stateOrCounty=match[2],postalOrZipCode=match[3],countryCode=country))
        if len(blocks)!=1:return None
        fields=blocks[0]
    required={'line1','townOrCity','stateOrCounty','postalOrZipCode','countryCode'}
    if not required<=fields.keys():return None
    country=COUNTRIES.get(fields['countryCode'].casefold(),fields['countryCode'].upper())
    if country not in set(COUNTRIES.values()) or country!=old.get('address',{}).get('countryCode'):return None
    postcode=fields['postalOrZipCode']
    patterns={'AU':r'\d{4}','NZ':r'\d{4}','US':r'\d{5}(?:-\d{4})?','CA':r'[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d','GB':r'[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}'}
    if not re.fullmatch(patterns[country],postcode):return None
    if any(not value or len(value)>150 or any(ord(c)<32 for c in value) for key,value in fields.items() if key!='line2'):return None
    if not re.search(r'\d',fields['line1']):return None
    result={**old,'name':fields.get('name') or old.get('name',''),
            'address':{key:fields.get(key,'') for key in ('line1','line2','townOrCity','stateOrCounty','postalOrZipCode')}}
    result['address']['countryCode']=country
    return result if result['name'] else None

def proposed_address(text):
    """Retain only structured delivery fields, never the email body in job metadata."""
    body=authored(text)
    countries=[]
    for line in body.splitlines():
        candidate=re.sub(r'^\s*Country\s*:\s*','',line,flags=re.I).strip().casefold()
        if candidate in COUNTRIES:countries.append(COUNTRIES[candidate])
    if len(countries)!=1:return None
    result=address(body,{'name':'__existing_recipient__','address':{'countryCode':countries[0]}})
    if result and result['name']=='__existing_recipient__':result['name']=''
    return result

def unchanged_order(before,after):
    """Address is the sole permitted business change; preserve every item and price."""
    from prodigi_browser import business
    a=business(before,'');b=business(after,'')
    for record in (a,b):record.pop('recipient',None)
    return a==b

def same_address(left,right):
    def normal(v):return re.sub(r'\s+',' ',str(v or '')).strip().casefold()
    if normal(left.get('name'))!=normal(right.get('name')):return False
    return all(normal(left.get('address',{}).get(k))==normal(right.get('address',{}).get(k))
               for k in ('line1','line2','townOrCity','stateOrCounty','postalOrZipCode','countryCode'))
