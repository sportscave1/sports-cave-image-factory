"""Pure quiz contracts and conservative classification. No provider transports."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

ROUTE = 'Product Quiz'
PREFIX = 'product_quiz/'
DEFAULT = {
    'questions': [
        {'id': 'sport', 'label': 'Which sport?', 'enabled': True, 'answers': []},
        {'id': 'subject', 'label': 'Who belongs on your wall?', 'enabled': True, 'answers': []},
        {'id': 'preference', 'label': 'Which story speaks to you?', 'enabled': True, 'answers': []},
    ],
    'appearance': {'title': 'Find your edition', 'intro': 'Your sport. Your icons. Your edition.',
                   'accent': '#c6a76b', 'background': '#0b0b0c', 'text': '#f5f0e6'},
    'rules': {'max_results': 3, 'allow_broader': True},
    'aliases': {}, 'collections': {},
}


def key(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in value if not unicodedata.combining(c)).casefold()))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()[:24]


def validate(config):
    if not isinstance(config,dict): raise ValueError('Quiz settings must be an object.')
    c = deepcopy(config)
    if set(c) != set(DEFAULT): raise ValueError('Unknown or missing quiz setting.')
    questions = c['questions']
    if len(questions) != 3 or {q['id'] for q in questions} != {'sport', 'subject', 'preference'}:
        raise ValueError('Keep one sport, subject and preference question.')
    enabled = [q['id'] for q in questions if q['enabled']]
    if not enabled or enabled[0] != 'sport': raise ValueError('Sport must be the first enabled question.')
    for q in questions:
        if set(q) != {'id', 'label', 'enabled', 'answers'} or type(q['enabled']) is not bool or not isinstance(q['label'], str) or not 1 <= len(q['label']) <= 120:
            raise ValueError('Invalid question.')
        if not isinstance(q['answers'], list) or len(q['answers']) > 500: raise ValueError('Invalid answer choices.')
        seen = set()
        for a in q['answers']:
            if set(a) != {'value', 'label', 'enabled'} or type(a['enabled']) is not bool or any(not isinstance(a[k],str) or not 1 <= len(a[k]) <= 120 for k in ('value','label')) or key(a['value']) in seen:
                raise ValueError('Answer overrides need unique values, labels and enabled flags.')
            seen.add(key(a['value']))
    for name in ('title','intro'):
        if not isinstance(c['appearance'][name],str) or not 1 <= len(c['appearance'][name]) <= 160: raise ValueError('Invalid appearance copy.')
    for name in ('accent','background','text'):
        if not re.fullmatch('#[0-9a-fA-F]{6}', c['appearance'][name]): raise ValueError('Use six-digit hex colours.')
    if set(c['appearance']) != set(DEFAULT['appearance']): raise ValueError('Unknown appearance setting.')
    if set(c['rules']) != {'max_results','allow_broader'} or type(c['rules']['max_results']) is not int or not 1 <= c['rules']['max_results'] <= 3 or type(c['rules']['allow_broader']) is not bool:
        raise ValueError('Invalid matching rules.')
    for mapping in ('aliases','collections'):
        if not isinstance(c[mapping],dict) or len(c[mapping]) > 1000 or any(not isinstance(k,str) or not isinstance(v,str) or not 1<=len(k)<=120 or not 1<=len(v)<=120 for k,v in c[mapping].items()): raise ValueError('Invalid mapping.')
    if any(not re.fullmatch('[a-z0-9-]+',handle) for handle in c['collections']): raise ValueError('Use exact collection handles.')
    return c


def verified_collections(rows):
    from product_sport_tags import collection_sports
    found={}
    for row in rows:
        raw=row.get('raw_json') or row.get('raw') or row
        if isinstance(raw,str): raw=json.loads(raw)
        for collection in raw.get('collections') or []:
            if not isinstance(collection,dict) or not collection.get('handle'): continue
            explicit,subjects=collection_sports(collection)
            found.setdefault(collection['handle'],set()).update(explicit or subjects)
    return {handle:next(iter(sports)) for handle,sports in found.items() if len(sports)==1}


def names(values, aliases):
    if isinstance(values, str):
        try: values = json.loads(values) if values.startswith('[') else re.split(r'[,;|]',values)
        except ValueError: values = []
    if not isinstance(values,(tuple,list)): return []
    result = {}
    lookup = {key(k):v for k,v in aliases.items()}
    for value in values:
        if not isinstance(value,str): continue
        value = value.strip()[:120]
        if value: result[key(lookup.get(key(value),value))] = lookup.get(key(value),value)
    return sorted(result.values(),key=key)


def classify(row, override=None, aliases=None):
    """Only structured facts/exact collection mappings; ambiguity is reviewable."""
    from product_sport_tags import classify_product, TAGS, ATHLETES
    from product_upload_collections import SUBJECTS
    from crm_personalisation import short_name
    override, aliases = override or {}, aliases or {}
    raw = row.get('raw_json') or row.get('raw') or row
    if isinstance(raw,str): raw=json.loads(raw)
    pid = str(row.get('shopify_product_id') or raw.get('shopify_product_id') or raw.get('id') or '')
    number = pid.rsplit('/',1)[-1]
    if not number.isdigit(): raise ValueError('Invalid Shopify product ID.')
    pid = 'gid://shopify/Product/'+number
    title = str(row.get('title') or raw.get('title') or '')
    fields = {str(m.get('key')): m.get('value') for m in raw.get('metafields',[]) if isinstance(m,dict) and m.get('namespace') in {'custom','sports_cave'}}
    facts = {name:fields.get(name,[]) for name in ('athletes','teams','sport','moment','era','style')}
    # Stored OS facts can enrich the classification; file paths never leave this function.
    facts.update(raw.get('quiz_facts') or {})
    facts['athletes']=names(facts.get('athletes',[]),aliases)
    facts['sports']=names(facts.get('sport',[]),aliases)
    classification = classify_product(raw, verified_facts=facts)
    sports = [sport for sport,tag in TAGS.items() if tag in classification.required_tags and sport != 'Apparel']
    if len(sports)>1: sports=[s for s in sports if s not in {'Motorsport','Combat'}]
    if 'sports' in override: sports=names(override['sports'],aliases)
    subjects = names(facts.get('athletes',[]),aliases)+names(facts.get('teams',[]),aliases)
    # Exact curated subject collection identities already audited by the OS.
    known = {key(n): n.title() for n in ATHLETES}
    for identity,label in known.items():
        if ' '+identity+' ' in ' '+key(title)+' ': subjects.append(label)
    handles = {h:(n.title()) for n,(_,h) in SUBJECTS.items()}
    for collection in raw.get('collections') or []:
        if not isinstance(collection,dict): continue
        label = key(re.sub(r'\s+(wall art|collection|tribute)$','',str(collection.get('title') or ''),flags=re.I))
        if label in known: subjects.append(known[label])
        if collection.get('handle') in handles: subjects.append(handles[collection['handle']])
    subjects=names(override.get('subjects',subjects),aliases)
    preferences=names(override.get('preferences',[v for n in ('moment','era','style') for v in names(facts.get(n,[]),aliases)]),aliases)
    handle=str(row.get('handle') or raw.get('handle') or '')
    image=str(row.get('image_url') or row.get('featured_image_url') or next((m.get('url','') for m in raw.get('images') or [] if isinstance(m,dict)),''))
    url=str(row.get('online_store_url') or raw.get('online_store_url') or raw.get('onlineStoreUrl') or '')
    status='Eligible'; reason=''
    edition=row.get('edition') or {}
    if override.get('excluded'): status,reason='Excluded',str(override.get('reason') or 'Manually excluded')
    elif str(row.get('status') or raw.get('status') or '').upper() != 'ACTIVE' or not url: status,reason='Excluded','Not published to the online store'
    elif edition.get('closed') or edition.get('exhausted'): status,reason='Excluded','Edition closed or exhausted'
    elif raw.get('quiz_sellable') is False: status,reason='Excluded','No sellable variant under Shopify selling policy'
    elif 'quiz_sellable' in raw and raw['quiz_sellable'] is None: status,reason='Needs details','Selling policy could not be verified'
    elif row.get('edition_identity_count',0)>1: status,reason='Needs details','Ambiguous edition ledger identity'
    elif classification.review and 'sports' not in override: status,reason='Needs details','; '.join(classification.review)
    elif not sports or not subjects: status,reason='Needs details','Verify sport and athlete/team classification'
    elif not re.fullmatch('[a-zA-Z0-9_-]+',handle) or urlsplit(url).scheme != 'https' or urlsplit(image).hostname != 'cdn.shopify.com': status,reason='Needs details','Missing verified storefront URL or Shopify image'
    return {'id':pid,'handle':handle,'title':short_name(title),'image':image,'sports':sports,'subjects':subjects,
            'preferences':preferences,'featured':max(0,min(3,int(override.get('featured',0)))), 'status':status,'reason':reason}


def public_product(row):
    return {k:row[k] for k in ('id','handle','title','image','sports','subjects','preferences','featured')}
