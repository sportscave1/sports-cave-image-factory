"""Deterministic canonical catalogue resolution; no Meta or image API calls."""
import json
import re
from copy import deepcopy
from urllib.parse import urlparse,unquote

HOSTS={'sportscave.com.au','www.sportscave.com.au','sportscaveshop.com','www.sportscaveshop.com'}
STOP={'the','wall','art','edition','limited','vs','v','and','of','a','aus','au','usa','us','uk','nba','nfl','ia','carousel'}


def tokens(value):
    return {x for x in re.findall(r'[a-z]+',str(value or '').casefold()) if x not in STOP}


def product_url_handle(url):
    try:
        parsed=urlparse(str(url))
        if parsed.scheme not in ('http','https') or (parsed.hostname or '').lower() not in HOSTS: return ''
        match=re.fullmatch(r'/products/([a-z0-9-]+)/?',unquote(parsed.path),re.I)
        return match[1].lower() if match else ''
    except ValueError: return ''


def canonical(row):
    import ads_page
    handle=str(row.get('product_handle') or row.get('shopify_handle') or row.get('handle') or '').strip()
    title=str(row.get('product_title') or row.get('title') or '').strip()
    if not handle or not title: return None
    url=next((str(row[k]) for k in ('online_store_url','product_url','product_page_url') if product_url_handle(row.get(k))==handle.lower()),'')
    url=url or ads_page.canonical_shopify_product_url_from_row({**row,'product_handle':handle})
    category=''
    aliases={'basketball':'NBA','nba':'NBA','motorsport':'Motorsport','motorsport art':'Motorsport','football':'Football',
             'soccer':'Football','football/soccer':'Football','combat sports':'Combat','ufc/mma':'Combat','hockey':'Ice Hockey'}
    def category_value(value):
        value=str(value or '').strip()
        return value if value in ads_page.CATEGORY_OPTIONS and value!='Select category' else aliases.get(value.casefold(),'')
    for field in ('category','sport','product_sport','product_type'):
        category=category_value(row.get(field))
        if category: break
    if not category:
        collections=row.get('collections') or []
        if isinstance(collections,str): collections=re.split(r'[,;|]',collections)
        matches={category_value(c.get('title') if isinstance(c,dict) else c) for c in collections}
        matches.discard('')
        if len(matches)==1: category=matches.pop()
    return {'product_id':str(row.get('shopify_product_id') or row.get('product_id') or ''),
            'product_title':title,'product_handle':handle,'product_url':url,'category':category,'sport':category,
            'canonical_row':{**row,'product_handle':handle,'product_title':title,'online_store_url':url}}


def resolve(package,catalogue,mappings=(),postings=()):
    products=[p for row in catalogue if (p:=canonical(row))]
    def matched(source):
        pid=str(source.get('product_id') or source.get('shopify_product_id') or '')
        handle=str(source.get('product_handle') or source.get('shopify_handle') or product_url_handle(source.get('destination_url')) or '')
        if pid: return [p for p in products if p['product_id'] and p['product_id']==pid]
        if handle: return [p for p in products if p['product_handle'].casefold()==handle.casefold()]
        title=str(source.get('product_title') or '')
        return [p for p in products if title and p['product_title'].casefold()==title.casefold()]
    def result(items,method,confidence='EXACT'):
        unique={p['product_handle']:p for p in items}
        values=list(unique.values())
        return {'product':values[0] if len(values)==1 else None,'confidence':confidence if len(values)==1 else 'AMBIGUOUS',
                'method':method,'candidates':values}
    expanded=[]
    for mapping in mappings:
        if mapping.get('mapping_status') in ('suggested','needs_review'): continue
        try: meta=json.loads(mapping.get('notes') or '{}')
        except (ValueError,TypeError): meta={}
        expanded.append({**(meta if isinstance(meta,dict) else {}),**{k:v for k,v in mapping.items() if v is not None}})
    existing=package.get('product_mapping') or {}
    if existing.get('product_handle'): expanded.insert(0,{**existing,'ad_id':package.get('ad_id')})
    for key in ('ad_id','creative_id','campaign_id','adset_id'):
        sources=[m for m in expanded if package.get(key) and str(m.get(key) or '')==str(package[key]) and (m.get('product_handle') or m.get('product_title'))]
        if sources:
            hits=[p for m in sources for p in matched(m)]
            if not hits or any(not matched(m) for m in sources):
                return {'product':None,'confidence':'AMBIGUOUS','method':'Unresolved existing '+key+' mapping','candidates':hits}
            return result(hits,'existing '+key+' mapping')
    for key in ('ad_id','creative_id','campaign_id','adset_id'):
        sources=[m for m in postings if package.get(key) and str(m.get(key) or m.get('meta_'+key) or '')==str(package[key])]
        hits=[p for m in sources for p in matched(m)]
        if hits:
            if any((m.get('product_id') or m.get('product_handle') or m.get('product_title')) and not matched(m) for m in sources):
                return {'product':None,'confidence':'AMBIGUOUS','method':'unresolved Posting products','candidates':hits}
            return result(hits,'Sports Cave Posting '+key)
    urls=list(package.get('product_destination_urls') or [])
    urls.extend([package.get('destination_url','')])
    handles={product_url_handle(url) for url in urls}; handles.discard('')
    if handles:
        hits=[p for p in products if p['product_handle'].lower() in handles]
        if len(handles)>1 or len({p['product_handle'].lower() for p in hits})!=len(handles):
            return {'product':None,'confidence':'AMBIGUOUS','method':'multiple/unresolved product destinations','candidates':hits}
        return result(hits,'exact product destination')
    evidence=' '.join(str(package.get(k) or '') for k in ('campaign_name','ad_name','creative_name'))
    for key in ('primary_text','headline'):
        evidence+=' '+str((package.get('components',{}).get(key) or {}).get('value') or '')
    words=tokens(evidence)
    compact=''.join(re.findall(r'[a-z]+',evidence.casefold()))
    # Rank compact campaign names such as ATHLETEvATHLETE without treating that
    # athlete overlap as enough evidence for automatic selection.
    vocabulary={word for p in products for word in tokens(p['product_title']) if len(word)>=4}
    words.update(word for word in vocabulary if word in compact)
    ranked=sorted(products,key=lambda p:(-len(tokens(p['product_title']) & words)/max(1,len(tokens(p['product_title']))),p['product_title']))
    candidates=[p for p in ranked if len(tokens(p['product_title']) & words)>=2]
    # HIGH requires the complete distinctive product title, not athlete pairs.
    full=[p for p in candidates if len(tokens(p['product_title']))>=4 and tokens(p['product_title'])<=words]
    if len(full)==1 and not any(len(tokens(p['product_title']) & words)/max(1,len(tokens(p['product_title'])))>=.75 for p in candidates if p!=full[0]):
        return result(full,'unique full-title match','HIGH')
    return {'product':None,'confidence':'AMBIGUOUS' if candidates else 'NO MATCH','method':'name suggestions only','candidates':candidates[:10]}


def enrich(package):
    """One entry point for queue and fresh-tab loading, reusing the live catalogue."""
    from ads_product_catalog import load_live_edition_product_rows
    import meta_review_store as store
    package=deepcopy(package)
    catalogue=load_live_edition_product_rows()
    if not catalogue:
        package.setdefault('product_resolution',{'confidence':'NO MATCH','method':'Catalogue unavailable','candidates':[]})
        return package
    try:
        mappings=store.product_mapping_context(package)
        outcome=resolve(package,catalogue,mappings)
        if not outcome['method'].startswith(('existing','Unresolved existing')):
            outcome=resolve(package,catalogue,mappings,store.product_posting_context(package))
    except Exception:
        # A failed exact lookup must not fall through to weaker automatic guesses.
        outcome={'product':None,'confidence':'NO MATCH','method':'Product mapping storage unavailable','candidates':[]}
    package['product_resolution']={k:v for k,v in outcome.items() if k!='product'}
    if outcome['product']:
        package['product_mapping']=outcome['product']
        package.update({k:v for k,v in outcome['product'].items() if k!='canonical_row'})
        package.update(product_match_method=outcome['method'],product_match_confidence=outcome['confidence'])
    else: package['product_mapping']={}
    return package
