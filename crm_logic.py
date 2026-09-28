"""Pure CRM eligibility, live rule evaluation and safe identity helpers."""
import hashlib
import re
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SPORTS = ('Motorsport','NBA','NFL','MLB','NRL','Cricket','Horse Racing')
FIELDS = {'country','consent','orders','spend','last_order_days','subscribed_days','created_days',
          'product','collection','interest','edition','abandoned'}

def now():return datetime.now(timezone.utc)
def date(value):
    if isinstance(value,datetime):return value.astimezone(timezone.utc)
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def email(value):
    value=str(value or '').strip().casefold()
    return value if len(value)<=254 and re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',value) else ''

def recipient_hash(value):return hashlib.sha256(email(value).encode()).hexdigest()
def consent(customer):
    if not customer:return 'REDACTED'
    if not email(customer.get('email')) or customer.get('validEmailAddress') is False:return 'INVALID'
    state=(customer.get('emailMarketingConsent') or {}).get('marketingState','NOT_SUBSCRIBED')
    return state if state in {'SUBSCRIBED','UNSUBSCRIBED','PENDING','NOT_SUBSCRIBED','REDACTED','INVALID'} else 'NOT_SUBSCRIBED'

def eligibility(customer, suppressed=False, provider_suppressed=False):
    from crm_eligibility import eligible
    return eligible(customer, suppressed, provider_suppressed)

def safe_url(value):
    parsed=urlsplit(str(value or ''))
    return str(value) if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password else ''

def utm(url,key):
    url=safe_url(url)
    if not url:return ''
    p=urlsplit(url);q=dict(parse_qsl(p.query,keep_blank_values=True))
    q.update(utm_source='sportscave',utm_medium='email',utm_campaign=str(key)[:100])
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),p.fragment))

def validate_rules(rules,depth=0):
    if depth>4 or not isinstance(rules,dict):raise ValueError('Invalid segment rule.')
    if 'all' in rules or 'any' in rules:
        if len(rules)!=1:raise ValueError('Use one AND/OR group.')
        children=rules.get('all',rules.get('any'))
        if not isinstance(children,list) or not 1<=len(children)<=12:raise ValueError('Use 1–12 rules per group.')
        for child in children:validate_rules(child,depth+1)
    else:
        if set(rules)!={'field','op','value'} or rules['field'] not in FIELDS:raise ValueError('Unknown segment field.')
        if rules['op'] not in ('eq','gte','lte','contains'):raise ValueError('Unknown comparison.')
        if not isinstance(rules['value'],(str,int,float,bool)) or len(str(rules['value']))>200:raise ValueError('Invalid rule value.')
        if rules['field'] in {'orders','spend','last_order_days','subscribed_days','created_days'}:
            try:
                number=Decimal(str(rules['value']))
                if rules['op'] not in ('eq','gte','lte') or not number.is_finite() or number<0:raise ValueError('Use a non-negative numeric rule.')
            except InvalidOperation:raise ValueError('Use a non-negative numeric rule.') from None
        elif rules['field'] in {'product','collection','interest','edition'}:
            if rules['op']!='contains':raise ValueError('Use contains for purchase and edition rules.')
        elif rules['op']!='eq':raise ValueError('Use equals for country, consent and abandonment.')
    return rules

def rule(field,value,op='eq'):return {'field':field,'op':op,'value':value}

def segment_seeds():
    entries=[('all_subscribed','All Subscribed',rule('consent','SUBSCRIBED')),
      ('new_subscribers','New Subscribers — 30 Days',{'all':[rule('consent','SUBSCRIBED'),rule('subscribed_days',30,'lte')]}),
      ('au','Australia',rule('country','AU')),('us','United States',rule('country','US')),('uk','United Kingdom',rule('country','GB')),
      ('repeat','Repeat Buyers',rule('orders',2,'gte')),('vip','VIP Collectors',rule('spend',1000,'gte'))]
    entries += [(s.lower().replace(' ','_'),s+' Collectors',rule('interest',s,'contains')) for s in SPORTS]
    entries += [('recent','Recent Buyers — 30 Days',rule('last_order_days',30,'lte')),
      ('lapsed','No Purchase — 180 Days',{'all':[rule('orders',1,'gte'),rule('last_order_days',180,'gte')]}),
      ('abandoned','Abandoned Checkout Eligible',{'all':[rule('consent','SUBSCRIBED'),rule('abandoned',True)]})]
    return [{'system_key':k,'name':n,'rules':r} for k,n,r in entries]

class LiveFacts:
    """Transient, per-evaluation memo. No profile persistence; pages are bounded."""
    def __init__(self, shop, customer, editions=lambda *_: [], fresh=False):
        self.shop,self.customer,self.editions,self.fresh=shop,customer,editions,fresh
        self.memo={};self.deadline=time.monotonic()+30
    def check_budget(self):
        if time.monotonic()>self.deadline:raise ValueError('Live evaluation is taking too long. Narrow the segment and try again.')
    def purchases(self):
        if 'purchases' in self.memo:return self.memo['purchases']
        key=('purchase-facts',self.shop.namespace,self.customer['id'])
        if not self.fresh:
            cached=self.shop.cache.get(key)
            if cached is not None:self.memo['purchases']=cached;return cached
        products=set();after=None
        for _ in range(100):
            self.check_budget()
            page=self.shop.orders(self.customer['id'],after,self.fresh)
            for order in page['nodes']:
                if order.get('cancelledAt'):continue
                lines=order['lineItems'];seen=set()
                while True:
                    self.check_budget()
                    products.update(n['product']['id'] for n in lines['nodes'] if n.get('product'))
                    if not lines['pageInfo'].get('hasNextPage'):break
                    cursor=lines['pageInfo']['endCursor']
                    if cursor in seen:raise ValueError('Shopify pagination did not advance.')
                    seen.add(cursor);lines=self.shop.line_page('order',order['id'],cursor,self.fresh)
            if not page['pageInfo'].get('hasNextPage'):break
            after=page['pageInfo']['endCursor']
        else:raise ValueError('Purchase history exceeds interactive evaluation limit; narrow this segment.')
        collections=set();labels=set();ids=sorted(products)
        for i in range(0,len(ids),50):
            self.check_budget()
            for product in self.shop.products(ids[i:i+50],self.fresh):
                labels.update(str(v).casefold() for v in product.get('tags',[]))
                labels.add(str(product.get('productType','')).casefold())
                page=product['collections'];seen=set()
                while True:
                    self.check_budget()
                    for c in page['nodes']:
                        collections.add(c['id']);labels.update([c['title'].casefold(),c['handle'].replace('-',' ').casefold()])
                    if not page['pageInfo'].get('hasNextPage'):break
                    cursor=page['pageInfo']['endCursor']
                    if cursor in seen:raise ValueError('Shopify pagination did not advance.')
                    seen.add(cursor);page=self.shop.collections(product['id'],cursor,self.fresh)
        interests={sport for sport in SPORTS if any(re.search(r'\b'+re.escape(sport.casefold())+r'\b',x) for x in labels)}
        self.memo['purchases']={'product':products,'collection':collections,'interest':interests}
        if not self.fresh:self.shop.cache.put(key,self.memo['purchases'],45)
        return self.memo['purchases']
    def value(self,field,at):
        c=self.customer
        if field=='country':return (c.get('defaultAddress') or {}).get('countryCodeV2','')
        if field=='consent':return consent(c)
        if field=='orders':return int(c.get('numberOfOrders') or 0)
        if field=='spend':return Decimal((c.get('amountSpent') or {}).get('amount','0'))
        if field.endswith('_days'):
            timestamp={'last_order_days':(c.get('lastOrder') or {}).get('createdAt'),
                'subscribed_days':(c.get('emailMarketingConsent') or {}).get('consentUpdatedAt'),
                'created_days':c.get('createdAt')}[field]
            dt=date(timestamp)
            return (at-dt).total_seconds()/86400 if dt else None
        if field in ('product','collection','interest'):return self.purchases()[field]
        if field=='edition':
            if 'edition' not in self.memo:self.memo['edition']={str(x['edition_number']) for x in self.editions(c['id'],c.get('email',''))}
            return self.memo['edition']
        if field=='abandoned':
            after=None
            for _ in range(100):
                self.check_budget()
                page=self.shop.checkouts(after, fresh=self.fresh)
                if any((x.get('customer') or {}).get('id')==c['id'] and not x.get('completedAt') and date(x['updatedAt'])<=at-timedelta(hours=1) for x in page['nodes']):return True
                if not page['pageInfo'].get('hasNextPage'):return False
                after=page['pageInfo']['endCursor']
            raise ValueError('Checkout evaluation limit reached; narrow the source.')

def matches(rules,facts,at=None):
    validate_rules(rules);at=at or now()
    if 'all' in rules:return all(matches(r,facts,at) for r in rules['all'])
    if 'any' in rules:return any(matches(r,facts,at) for r in rules['any'])
    value=facts.value(rules['field'],at);expected=rules['value'];op=rules['op']
    if value is None:return False
    if op=='contains':return str(expected).casefold() in {str(v).casefold() for v in value}
    if op in ('gte','lte'):
        a,b=Decimal(str(value)),Decimal(str(expected));return a>=b if op=='gte' else a<=b
    return str(value).casefold()==str(expected).casefold()

def validate_steps(steps):
    if not isinstance(steps,list) or not 1<=len(steps)<=30:raise ValueError('Use 1–30 workflow steps.')
    for step in steps:
        if step.get('type') not in ('delay','revalidate','send','stop'):raise ValueError('Unknown workflow step.')
        if step['type']=='delay' and not 0<=float(step.get('hours',-1))<=8760:raise ValueError('Invalid delay.')
        if step['type']=='send' and not re.fullmatch(r'[a-z0-9_]{1,80}',step.get('template','')):raise ValueError('Choose a valid template.')
    return steps

def automation_seeds():
    def flow(prefix,hours):
        result=[]
        for i,h in enumerate(hours,1):result += [{'type':'delay','hours':h},{'type':'revalidate'},{'type':'send','template':prefix+(str(i) if len(hours)>1 else '')}]
        return result+[{'type':'stop'}]
    return [dict(automation_key=k,name=n,trigger_type=k,config=c,steps=flow(p,hs)) for k,n,p,hs,c in [
      ('abandoned','Abandoned Checkout','abandoned_', [1,23,48],{}),
      ('welcome','Welcome Series','welcome_', [0,48,60],{}),
      ('post_purchase','Post Purchase','post_purchase',[168],{}),
      ('win_back','Win Back','win_back',[0],{'days':180})]]
