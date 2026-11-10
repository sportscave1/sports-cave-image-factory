"""Pure quiz contracts and conservative classification. No provider transports."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

ROUTE = 'Product Quiz'
PREFIX = 'product_quiz/'
TITLE = 'Find your next edition'
SPORT_PROMPT = 'What sports do you support?'
SPORT_COLLECTIONS = {
    'Baseball': ('MLB', 'Major League Baseball'),
    'Combat': ('UFC', 'MMA', 'boxing', 'kickboxing', 'wrestling'),
    'Cricket': ('IPL', 'BBL', 'Big Bash', 'The Ashes', 'Test cricket'),
    'Darts': ('PDC', 'World Darts Championship'),
    'Football': ('soccer', 'EPL', 'Premier League', 'A League', 'Champions League', 'FIFA'),
    'Formula One': ('F1', 'Formula 1', 'Grand Prix'),
    'Horse Racing': ('racing horses', 'Melbourne Cup', 'thoroughbreds'),
    'Ice Hockey': ('NHL', 'hockey', 'National Hockey League'),
    'MotoGP': ('Moto GP', 'motorcycle grand prix', '500cc'),
    'NASCAR': ('stock car', 'Cup Series', 'Daytona 500'),
    'Basketball': ('NBA', 'WNBA', 'NBL', 'National Basketball Association'),
    'NFL': ('American football', 'gridiron', 'Super Bowl', 'National Football League'),
    'Rugby League': ('NRL', 'National Rugby League', 'State of Origin', 'Super League'),
    'Tennis': ('ATP', 'WTA', 'Wimbledon', 'Australian Open', 'Grand Slam'),
    'V8 Supercars': ('V8', 'Supercars', 'Bathurst', 'Bathurst 1000', 'ATCC'),
}
DEFAULT = {
    'questions': [
        {'id': 'sport', 'label': SPORT_PROMPT, 'enabled': True, 'answers': []},
        {'id': 'subject', 'label': 'Who do you support?', 'enabled': True, 'answers': []},
        {'id': 'preference', 'label': 'Which story speaks to you?', 'enabled': True, 'answers': []},
    ],
    'appearance': {'title': TITLE, 'intro': '',
                   'accent': '#c6a76b', 'background': '#0b0b0c', 'text': '#f5f0e6'},
    'rules': {'max_results': 1, 'allow_broader': True},
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
        if not isinstance(c['appearance'][name],str) or len(c['appearance'][name]) > 160: raise ValueError('Invalid appearance copy.')
    for name in ('accent','background','text'):
        if not re.fullmatch('#[0-9a-fA-F]{6}', c['appearance'][name]): raise ValueError('Use six-digit hex colours.')
    if set(c['appearance']) != set(DEFAULT['appearance']): raise ValueError('Unknown appearance setting.')
    if set(c['rules']) != {'max_results','allow_broader'} or type(c['rules']['max_results']) is not int or not 1 <= c['rules']['max_results'] <= 3 or type(c['rules']['allow_broader']) is not bool:
        raise ValueError('Invalid matching rules.')
    for mapping in ('aliases','collections'):
        if not isinstance(c[mapping],dict) or len(c[mapping]) > 1000 or any(not isinstance(k,str) or not isinstance(v,str) or not 1<=len(k)<=120 or not 1<=len(v)<=120 for k,v in c[mapping].items()): raise ValueError('Invalid mapping.')
    if any(not re.fullmatch('[a-z0-9-]+',handle) for handle in c['collections']): raise ValueError('Use exact collection handles.')
    return c


def verified_collections(rows, *, exact_sport=False):
    from product_sport_tags import collection_sports
    found={}
    for row in rows:
        raw=row.get('raw_json') or row.get('raw') or row
        if isinstance(raw,str): raw=json.loads(raw)
        for collection in raw.get('collections') or []:
            if not isinstance(collection,dict) or not collection.get('handle'): continue
            explicit,subjects=collection_sports(collection)
            if any(key(collection.get(field)) in {'darts', 'darts wall art'} for field in ('handle','title')):
                explicit.add('Darts')
            found.setdefault(collection['handle'],set()).update(explicit or (set() if exact_sport else subjects))
    return {handle:next(iter(sports)) for handle,sports in found.items() if len(sports)==1}


def sport_options(sports=(), aliases=None):
    from product_sport_tags import ALIASES
    return {
        sport: names([*ALIASES.get(sport, ()), *SPORT_COLLECTIONS.get(sport, ()),
                      *(alias for alias, target in (aliases or {}).items() if key(target)==key(sport))], {})
        for sport in sorted(set(SPORT_COLLECTIONS) | set(sports), key=key)
    }


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
    from product_sport_tags import classify_product, TAGS, ATHLETES, ALIASES, tag_list
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
    labels = {key(label): sport for sport in ALIASES.keys() | SPORT_COLLECTIONS.keys()
              for label in (sport, *ALIASES.get(sport, ()), *SPORT_COLLECTIONS.get(sport, ()), TAGS.get(sport, sport))}
    tagged_sports, tagged_subjects, tagged_preferences, keywords = set(), [], [], []
    story_tags = {'legacy', 'rivalry', 'defining moment', 'championship', 'championship moment',
                  'record breaker', 'retro', 'vintage', 'modern'}
    for tag in tag_list(raw.get('tags')):
        match = re.fullmatch(r'(?:sc[ _-]+)?(sport|league|team|athlete|player|driver|rider|fighter|jockey|horse|subject|moment|era|style|preference|theme)\s*[:=_-]\s*(.+)', tag, re.I)
        value = match[2].replace('_', ' ').strip() if match else tag
        if len(value)>80 or not all(c.isalnum() or c in " '-.&’" for c in value):
            continue
        kind = match[1].lower() if match else ''
        if kind in {'','sport','league'} and key(value) in labels and (kind or key(value) != 'grand prix'):
            tagged_sports.add(labels[key(value)])
        elif kind == 'sport' and key(value):
            tagged_sports.add(value.title())
        elif kind in {'moment','era','style','preference','theme'} or (not match and key(value) in story_tags):
            tagged_preferences.append(value)
        elif kind and kind != 'league':
            tagged_subjects.append(value)
        elif not match and not tag.upper().startswith(('SC-', 'SC_', 'INTERNAL', 'SYSTEM', 'GID', 'SKU')):
            keywords.append(value)
    facts['sports'] = [labels[key(sport)] for sport in names(facts.get('sport',[]),aliases) if key(sport) in labels]
    classification = classify_product(raw, verified_facts=facts)
    sports = tagged_sports | set(verified_collections([row],exact_sport=True).values()) | set(facts['sports'])
    if not sports:
        sports = {sport for sport,tag in TAGS.items() if tag in classification.required_tags and sport != 'Apparel'}
    sports.discard('Apparel')
    if sports - {'Motorsport','Combat'}: sports.discard('Motorsport')
    if 'WWE' in sports and 'Combat' not in tagged_sports: sports.discard('Combat')
    sports = sorted(sports,key=key)
    if 'sports' in override: sports=names(override['sports'],aliases)
    subjects = names(facts.get('athletes',[]),aliases)+names(facts.get('teams',[]),aliases)+tagged_subjects
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
    preferences=names(override.get('preferences',tagged_preferences+[v for n in ('moment','era','style') for v in names(facts.get(n,[]),aliases)]),aliases)
    handle=str(row.get('handle') or raw.get('handle') or '')
    image=str(row.get('image_url') or row.get('featured_image_url') or next((m.get('url','') for m in raw.get('images') or [] if isinstance(m,dict)),''))
    url=str(row.get('online_store_url') or raw.get('online_store_url') or raw.get('onlineStoreUrl') or '')
    status='Eligible'; reason=''
    edition=row.get('edition') or {}
    if override.get('excluded'): status,reason='Excluded',str(override.get('reason') or 'Manually excluded')
    elif row.get('edition_identity_count',0)>1: status,reason='Needs details','Ambiguous edition ledger identity'
    elif edition.get('deleted'): status,reason='Excluded','Removed from Shopify'
    elif str(row.get('status') or raw.get('status') or '').upper() != 'ACTIVE' or not url: status,reason='Excluded','Not published to the online store'
    elif edition.get('closed') or edition.get('exhausted'): status,reason='Excluded','Edition closed or exhausted'
    elif edition.get('blocked'): status,reason='Needs details','Edition Ops allocation requires review'
    elif raw.get('quiz_sellable') is False: status,reason='Excluded','No sellable variant under Shopify selling policy'
    elif not re.fullmatch('[a-zA-Z0-9_-]+',handle) or urlsplit(url).scheme != 'https': status,reason='Needs details','Missing verified storefront URL'
    elif not sports: reason='No sport classification yet'
    if urlsplit(image).hostname != 'cdn.shopify.com': image=''
    return {'id':pid,'handle':handle,'title':short_name(title),'image':image,'sports':sports,'subjects':subjects,
            'preferences':preferences,'keywords':names(keywords,aliases)[:64],
            'next_number':edition.get('next_number'), 'edition_total':edition.get('total'),
            'featured':max(0,min(3,int(override.get('featured',0)))), 'status':status,'reason':reason}


def public_product(row):
    fields=('id','handle','title','image','sports','subjects','preferences','featured',
            'keywords','next_number','edition_total')
    return {k:row[k] for k in fields if k in row}
