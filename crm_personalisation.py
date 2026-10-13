"""Shared recipient substitution for headers and HTML; authored documents stay intact."""
from copy import deepcopy
import re
import unicodedata

VARIABLES = ('first_name','product_name','short_product_name','sport_category','edition_number','discount_code','discount_value')
TOKEN = re.compile(r'{{\s*([a-z_]+)\s*}}')
FALLBACK = {'subject':'See your selected artwork', 'preheader':'Explore your chosen artwork and current availability.'}


def present(doc):
    return any(any(t in without_system_tokens(source) for t in ('{{','}}','{%','%}')) for source in sources(doc))


def without_system_tokens(source):
    from crm_campaign_footer import DEFAULT_FOOTER,LEGACY_TOKEN,LINK_TOKENS
    for token in set(re.findall(r'{{[^}]+}}',DEFAULT_FOOTER))|LINK_TOKENS|{LEGACY_TOKEN}:
        source=source.replace(token,'')
    return source


def html_sources(doc):
    if 'middle_sections' in doc:
        yield from (s.get('html','') for s in doc['middle_sections'] if s.get('visible',True))
    else:yield doc.get('custom_html','')
    yield from doc.get('html_sections',{}).values()


def sources(doc):
    yield from (doc.get('content',{}).get(k,'') for k in FALLBACK)
    yield from html_sources(doc)


def wanted(doc):
    return {name for source in sources(doc) for name in TOKEN.findall(source)}


def safe_values(values):
    safe={k:v.strip() for k,v in values.items() if k in VARIABLES and valid_text(v) and v.strip()}
    name=safe.get('first_name','')
    if not any(c.isalpha() for c in name) or any(c.isdigit() or c in '@:/<>\\' for c in name) or len(name)>80 or name.casefold() in ('null','undefined','there'):
        safe.pop('first_name',None)
    return safe


def html_values(values):
    """Escaped text substitutions, also shared with the reactive preview."""
    from html import escape
    defaults=dict(first_name='there',product_name='your selected artwork',short_product_name='your selected artwork',
                  sport_category='your favourite sport',edition_number='Check current edition availability')
    safe=safe_values(values)
    return {k:escape(safe.get(k,default),quote=True) for k,default in defaults.items()}


def campaign_preview_values(state,store):
    """Short session cache, keyed by the existing preview customer's identity."""
    import time
    identity=state.get('_smart_preview_customer')
    if not identity or store is None:return {}
    cached=state.get('_email_personalisation_preview')
    if not cached or cached[0]!=identity or cached[1]<time.monotonic():
        row=store.q('SELECT profile FROM crm_lifecycle_customers WHERE customer_id=%s',(identity,),True)
        customer=(row or {}).get('profile') or {}
        values={'first_name':customer.get('firstName','')} if customer.get('id')==identity else {}
        cached=(identity,time.monotonic()+120,values);state['_email_personalisation_preview']=cached
    return deepcopy(cached[2])


def valid_text(value):
    return isinstance(value,str) and not any(unicodedata.category(c).startswith('C') for c in value) and not any(x in value for x in ('{{','}}','{%','%}'))


def validate(doc, trigger='abandoned', *, allow_unselected_discount=False,validate_html=True):
    for source in html_sources(doc) if validate_html else ():
        source=without_system_tokens(source)
        names=TOKEN.findall(source)
        if set(names)-set(VARIABLES) or any(x in TOKEN.sub('',source) for x in ('{{','}}','{%','%}')):
            raise ValueError('Unresolved template variable. Use only the supported personalisation variables.')
    for field in FALLBACK:
        value=doc['content'].get(field,'')
        if not isinstance(value,str) or any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('Subject and preview text must not contain control characters.')
        names=TOKEN.findall(value)
        if set(names)-set(VARIABLES) or any(x in TOKEN.sub('',value) for x in ('{{','}}','{%','%}')):
            raise ValueError('Use only the supported personalisation variables.')
        if set(names)&{'discount_code','discount_value'} and not doc.get('recovery_discount') and not allow_unselected_discount:
            raise ValueError('Select a Shopify recovery discount before using its variables.')
        if names and len(value)>250:raise ValueError('Personalised subject and preview text must be at most 250 characters.')
        if 'edition_number' in names and trigger not in ('post_purchase','fulfilled'):
            # Constrained authored wording prevents unverified reservation claims.
            if not re.fullmatch(r'Next available edition: {{\s*edition_number\s*}}',value,re.I):
                raise ValueError('Before purchase, use exactly: Next available edition: {{edition_number}}')


def short_name(title):
    # Preserve defining names/events/years; do not guess which identity words matter.
    result=re.sub(r"\s+(?:(?:Collector['’]s|Limited Edition)\s+)?Wall Art\s*$",'',title,flags=re.I)
    return result.strip() or title


def render(doc, values, *, trigger='abandoned'):
    from crm_recovery_discount import substitute
    doc=substitute(doc)
    if not present(doc):return deepcopy(doc)
    validate(doc,trigger)
    result=deepcopy(doc)
    safe=safe_values(values)
    for field,fallback in FALLBACK.items():
        source=doc['content'][field];names=TOKEN.findall(source)
        if not names:continue
        if 'first_name' in names and 'first_name' not in safe:
            source=re.sub(r'^\s*{{\s*first_name\s*}}\s*[,!:—-]\s*','',source)
            if source:source=source[0].upper()+source[1:]
        if any(k not in safe for k in TOKEN.findall(source)):
            result['content'][field]=('Check current edition availability' if 'edition_number' in names else fallback)
            continue
        text=TOKEN.sub(lambda m:safe[m[1]],source)
        # A field-level fallback preserves meaning instead of cutting an identity.
        result['content'][field]=text if text.strip() and len(text)<=250 and valid_text(text) else fallback
    escaped=html_values(values)
    def replace(source):
        return TOKEN.sub(lambda m:escaped.get(m[1],m[0]),source)
    if 'middle_sections' in result:
        for section in result['middle_sections']:
            if section.get('visible',True) and 'html' in section:section['html']=replace(section['html'])
        result['custom_html']=next((s.get('html','') for s in result['middle_sections'] if s.get('html_number')==1),'')
    elif 'custom_html' in result:result['custom_html']=replace(result['custom_html'])
    if 'html_sections' in result:result['html_sections']={k:replace(v) for k,v in result['html_sections'].items()}
    return result


def values_from_preview(data):
    if not data or data.get('preview_only'):
        return dict(first_name='Nathan',product_name="Dick Johnson Crash – Bathurst 1980 Collector's Wall Art",
                    short_product_name='Dick Johnson Crash – Bathurst 1980',sport_category='Motorsport',edition_number='#078/100')
    if 'personalisation' not in data:
        source=data.get('personalisation_source') or {}
        data['personalisation']=resolve(source,source.get('customer') or {})
    return data['personalisation']


def resolve(source, customer, *, trigger='abandoned', edition_reader=None, metadata_reader=None, allocation_reader=None, wanted=None):
    """Only call after recipient/source verification. First API-ordered line wins."""
    values={'first_name':customer.get('firstName') or ''}
    wanted=set(VARIABLES if wanted is None else wanted)
    if not wanted-{'first_name'}:return values
    nodes=(source.get('lineItems') or {}).get('nodes') or []
    if not nodes:return values
    line=nodes[0];product=(line.get('variant') or {}).get('product') or line.get('product') or {}
    title=line.get('title') or product.get('title')
    if valid_text(title) and title.strip():values.update(product_name=title,short_product_name=short_name(title))
    from crm_catalogue import product_id,edition_for
    pid=product_id(product.get('id'))
    if not pid:return values
    from crm_personalisation_data import metadata,allocation
    try:
        info=((metadata_reader or metadata)(pid) or {}) if 'sport_category' in wanted else {}
        from sports_categories import infer_sport_category
        category=infer_sport_category(info.get('classifications',[]))
        if category:values['sport_category']=category
    except Exception as error:
        import logging
        logging.getLogger(__name__).warning('email_personalisation_category_unavailable class=%s',type(error).__name__)
    try:
        if 'edition_number' not in wanted:return values
        if trigger in ('post_purchase','fulfilled'):
            fact=(allocation_reader or allocation)(source.get('id'),customer.get('id'),pid,line.get('id'))
            if fact:values['edition_number']=fact
        else:
            if edition_reader is None:
                from supabase_backend import list_edition_products_read_only
                edition_reader=list_edition_products_read_only
            rows=edition_reader(product_ids=[pid],handles=[],limit=2)
            edition=edition_for({'id':pid,'handle':''},rows)
            from crm_catalogue import edition_available
            if edition_available(edition) and not any(r.get('sold_out') for r in rows) and edition.get('status')!='superseded':
                values['edition_number']=f"#{edition['next']:03d}/{edition['limit']}"
    except Exception as error:
        import logging
        logging.getLogger(__name__).warning('email_personalisation_facts_unavailable class=%s',type(error).__name__)
    return values
