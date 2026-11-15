"""Read-only Shopify discount discovery. UI cache never authorizes delivery."""
from decimal import Decimal
from crm_cache import DisplayCache

COMMON='''title status startsAt endsAt updatedAt usageLimit asyncUsageCount appliesOncePerCustomer
 combinesWith { productDiscounts orderDiscounts shippingDiscounts }
 discountClasses context { __typename }'''
VALUE='''customerGets { value { __typename ... on DiscountAmount { amount { amount currencyCode } appliesOnEachItem }
 ... on DiscountPercentage { percentage } } items { __typename } }'''
MINIMUM='''minimumRequirement { __typename ... on DiscountMinimumSubtotal { greaterThanOrEqualToSubtotal { amount currencyCode } }
 ... on DiscountMinimumQuantity { greaterThanOrEqualToQuantity } }'''
TYPES={'DiscountCodeBasic':'summary '+VALUE+' '+MINIMUM,'DiscountCodeFreeShipping':'summary '+MINIMUM,
       'DiscountCodeBxgy':'summary','DiscountCodeApp':''}


def fragments(codes=False,search_codes=False):
    return '__typename '+ ' '.join('... on '+kind+' { '+COMMON+' '+extra+
        (' codes(first:20,after:$codesAfter'+(',query:$codesQuery' if search_codes else '')+') { nodes { code } pageInfo { hasNextPage endCursor } }' if codes else '')+' }' for kind,extra in TYPES.items())


SEARCH='query RecoveryDiscountSearch($query:String,$after:String,$codesAfter:String) { discountNodes(first:15,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true) { nodes { id codeDiscount:discount { '+fragments(True)+' } } pageInfo { hasNextPage endCursor } } }'
LOOKUP='query RecoveryDiscount($code:String!) { codeDiscountNodeByCode(code:$code) { id codeDiscount { '+fragments()+' } } }'
CODES='query RecoveryDiscountCodes($id:ID!,$codesAfter:String,$codesQuery:String) { node(id:$id) { ... on DiscountCodeNode { id codeDiscount { '+fragments(True,True)+' } } } }'
CHECKOUT='''query RecoveryDiscountCheckout($id:ID!) { node(id:$id) { ... on AbandonedCheckout {
 id customer { id } abandonedCheckoutUrl completedAt discountCodes
 subtotalPriceSet { shopMoney { amount currencyCode } } totalDiscountSet { shopMoney { amount currencyCode } }
 } } }'''
AUTOMATIC='query RecoveryAutomaticDiscounts { discountNodes(first:26,query:"method:automatic status:active") { nodes { discount { __typename '+ ' '.join('... on '+kind+' { status discountClasses combinesWith { productDiscounts orderDiscounts shippingDiscounts } }' for kind in ('DiscountAutomaticBasic','DiscountAutomaticFreeShipping','DiscountAutomaticBxgy','DiscountAutomaticApp'))+' } } pageInfo { hasNextPage } } }'
SCOPES='query RecoveryDiscountScopes { currentAppInstallation { app { title } accessScopes { handle } } }'
CACHE=DisplayCache(limit=64,byte_limit=2*1024*1024)


class DiscountRemoved(ValueError):pass


def selectable(row):
    from crm_logic import date,now
    if not row.get('supported'):return 'This Shopify offer type cannot be verified for recovery links.'
    if row.get('status')!='ACTIVE':return 'This discount is '+row.get('status','inactive').lower()+'.'
    d=row.get('facts') or {};clock=now()
    if not date(d.get('startsAt')) or date(d['startsAt'])>clock or (date(d.get('endsAt')) and date(d['endsAt'])<=clock):return 'This discount is not currently active. Refresh Shopify results.'
    if d.get('usageLimit') is not None and d.get('asyncUsageCount',0)>=d['usageLimit']:return 'This discount has reached its reported usage limit.'
    return ''


def page_info(page):
    info=page.get('pageInfo')
    if not isinstance(info,dict) or type(info.get('hasNextPage')) is not bool or (info['hasNextPage'] and not info.get('endCursor')):
        raise ValueError('Shopify returned incomplete discount pagination. Refresh before selecting an offer.')
    return info


def prefix_terms(term):
    import re
    return [re.sub(r'([\\():"*])',r'\\\1',part)+'*' for part in term.strip()[:100].split()[:12]]


def require_scope(shop):
    result=shop.query(SCOPES,{},'discount read permission',60)['currentAppInstallation']
    if not {'read_discounts','write_discounts'} & {s['handle'] for s in result['accessScopes']}:
        raise ValueError('The Sports Cave Shopify app needs read_discounts permission. An administrator must approve access; no permissions were changed.')


def metadata(node,code):
    d=node.get('codeDiscount') or {};kind=d.get('__typename');value=''
    if kind=='DiscountCodeBasic':
        v=(d.get('customerGets') or {}).get('value') or {}
        if v.get('__typename')=='DiscountPercentage':value=format((Decimal(str(v['percentage']))*100).normalize(),'f')+'% off'
        elif v.get('__typename')=='DiscountAmount':
            money=v['amount'];symbol={'AUD':'A$','USD':'US$','NZD':'NZ$','CAD':'C$','GBP':'£','EUR':'€'}.get(money['currencyCode'],money['currencyCode']+' ')
            value=symbol+format(Decimal(money['amount']).normalize(),'f')+' off'+(' each eligible item' if v.get('appliesOnEachItem') else '')
    elif kind=='DiscountCodeFreeShipping':value='Free shipping'
    elif kind=='DiscountCodeBxgy':value=d.get('summary') or 'Buy X Get Y — conditions apply'
    elif kind=='DiscountCodeApp':value='App-calculated offer; value determined at checkout'
    label=('Percentage' if '%' in value else 'Fixed amount') if kind=='DiscountCodeBasic' else {'DiscountCodeFreeShipping':'Free shipping','DiscountCodeBxgy':'Buy X Get Y','DiscountCodeApp':'App-managed'}.get(kind,'Unsupported')
    return {'id':node['id'],'code':code,'type':kind or 'Unsupported','label':label,'title':d.get('title',''),
            'value':value,'status':d.get('status','INACTIVE'),'summary':d.get('summary',''),
            'supported':kind in TYPES and bool(value),'facts':d}


def search(shop,term='',after=None,*,refresh=False):
    key=(shop.namespace,term,after)
    if not refresh:
        cached=CACHE.get(key)
        if cached is not None:return cached
    require_scope(shop)
    term=term.strip()[:100]
    query='method:code'+''.join(' AND (title:'+word+' OR code:'+word+')' for word in prefix_terms(term))
    data=shop.query(SEARCH,{'query':query,'after':after,'codesAfter':None},'discount search',fresh=True)
    page=data.get('discountNodes')
    if not isinstance(page,dict) or not isinstance(page.get('nodes'),list):raise ValueError('Shopify did not return discount results. Check access and retry; this is not an empty list.')
    info=page_info(page)
    rows=[];more_codes=[]
    for node in page['nodes']:
        d=node['codeDiscount'];codes=d.get('codes') or {}
        rows.extend(metadata(node,c['code']) for c in codes.get('nodes',[]))
        if codes.get('pageInfo',{}).get('hasNextPage'):more_codes.append({'id':node['id'],'title':d.get('title',''),'after':codes['pageInfo']['endCursor']})
    # Exact code lookup also reaches individual codes in very large bulk sets.
    if term.strip():
        node=shop.query(LOOKUP,{'code':term.strip()},'exact discount code',fresh=True).get('codeDiscountNodeByCode')
        if node and not any(r['code'].casefold()==term.strip().casefold() for r in rows):rows.insert(0,metadata(node,term.strip()))
    return CACHE.put(key,{'rows':rows,'pageInfo':info,'more_codes':more_codes},60)


def code_page(shop,identity,after,*,term='',refresh=False):
    require_scope(shop)
    node=shop.query(CODES,{'id':identity,'codesAfter':after,'codesQuery':' '.join(prefix_terms(term)) or None},'discount code page',60,fresh=refresh)['node']
    if not node or not node.get('codeDiscount'):raise ValueError('This Shopify discount group is unavailable. Refresh the list.')
    d=node['codeDiscount'];page=page_info(d['codes'])
    return {'rows':[metadata(node,c['code']) for c in d['codes']['nodes']],
            'pageInfo':page,'more_codes':[{'id':identity,'title':d['title'],'after':page['endCursor']}] if page['hasNextPage'] else []}


def fresh(shop,selection):
    require_scope(shop)
    node=shop.query(LOOKUP,{'code':selection['code']},'discount validation',fresh=True).get('codeDiscountNodeByCode')
    if not node or node['id'].split('/')[-1]!=selection['id'].split('/')[-1]:raise DiscountRemoved('Selected discount was removed or replaced. Choose an existing Shopify code.')
    return metadata(node,selection['code'])
