"""Synthetic Shopify GraphQL authority used only by local acceptance tests."""
from copy import deepcopy
from datetime import timedelta
from crm_logic import now
import crm_shopify as q

def page(nodes,after=None,size=50):
    offset=int(after or 0);end=min(len(nodes),offset+size)
    return {'nodes':deepcopy(nodes[offset:end]),'pageInfo':{'hasNextPage':end<len(nodes),'endCursor':str(end)}}

class ShopifyFixture:
    def __init__(self,count=73):
        at=now();self.calls=[];self.fail=None
        self.customers=[{'id':q.gid(i),'firstName':['Alex','Jordan','Taylor','Sam'][i%4],'lastName':'Collector '+str(i),
          'email':f'collector{i}@example.test','validEmailAddress':True,'createdAt':(at-timedelta(days=i)).isoformat(),'updatedAt':at.isoformat(),'tags':[],
          'defaultAddress':{'countryCodeV2':['AU','US','GB'][i%3]},'amountSpent':{'amount':str(i*249),'currencyCode':'AUD'},'numberOfOrders':str(i%5),
          'lastOrder':{'id':q.gid(i,'Order'),'name':f'#SC{i:04}','createdAt':(at-timedelta(days=i*4)).isoformat()} if i%5 else None,
          'emailMarketingConsent':{'marketingState':['SUBSCRIBED','SUBSCRIBED','PENDING','UNSUBSCRIBED'][i%4],'marketingOptInLevel':'CONFIRMED_OPT_IN','consentUpdatedAt':(at-timedelta(days=i)).isoformat()}} for i in range(1,count+1)]
        self.segments=[{'id':q.gid(1,'Segment'),'name':'Subscribed collectors','query':"email_subscription_status = 'SUBSCRIBED'",'lastEditDate':at.isoformat()},
          {'id':q.gid(2,'Segment'),'name':'Repeat customers','query':'number_of_orders >= 2','lastEditDate':at.isoformat()}]
        self.orders={c['id']:[{'id':q.gid(i*100+int(c['id'].rsplit('/',1)[-1]),'Order'),'name':f'#SC{i:04}','createdAt':c['lastOrder']['createdAt'],
            'cancelledAt':None,'fullyPaid':True,'displayFinancialStatus':'PAID','customer':{'id':c['id']},'totalPriceSet':{'shopMoney':{'amount':'249.00','currencyCode':'AUD'}},
            'lineItems':page([{'id':q.gid(i,'LineItem'),'title':'Collectors sports art','variantTitle':'Framed / A2','quantity':1,'product':{'id':q.gid(1,'Product')}}])} for i in range(int(c['numberOfOrders']))] for c in self.customers}
        self.products=[{'id':q.gid(1,'Product'),'title':'Collector sports art','productType':'Motorsport','tags':['Motorsport'],'onlineStoreUrl':'https://example.test/product',
            'featuredImage':None,'collections':page([{'id':q.gid(1,'Collection'),'title':'Motorsport','handle':'motorsport'}])}]
        self.checkouts=[{'id':q.gid(1,'AbandonedCheckout'),'createdAt':(at-timedelta(hours=3)).isoformat(),'updatedAt':(at-timedelta(hours=2)).isoformat(),
            'completedAt':None,'abandonedCheckoutUrl':'https://example.test/recover/1','customer':{'id':q.gid(1)},'totalPriceSet':{'shopMoney':{'amount':'249','currencyCode':'AUD'}},
            'lineItems':page([{'id':'line1','title':'Collectors sports art','quantity':1,'variant':{'id':q.gid(1,'ProductVariant'),'product':{'id':q.gid(1,'Product')}},'image':None,
            'originalUnitPriceSet':{'shopMoney':{'amount':'249','currencyCode':'AUD'}}}])}]
    def __call__(self,doc,v):
        self.calls.append((doc,v.copy()))
        if self.fail:raise self.fail
        if doc==q.CUSTOMERS:
            rows=self.customers;query=v.get('query') or ''
            if 'id:' in query:rows=[c for c in rows if c['id'].rsplit('/',1)[-1]==query.split('id:')[1].split()[0]]
            elif query.startswith('"'):rows=[c for c in rows if query.strip('"').lower() in (c['firstName']+' '+c['lastName']+' '+c['email']).lower()]
            return {'customers':page(rows,v.get('after'))}
        if doc==q.CUSTOMER:return {'customer':deepcopy(next((c for c in self.customers if c['id']==v['id']),None))}
        if doc==q.CUSTOMER_BATCH:return {'nodes':deepcopy([c for c in self.customers if c['id'] in v['ids']])}
        if doc==q.TOTAL:return {'customersCount':{'count':len(self.customers),'precision':'EXACT'}}
        if doc==q.COUNT:
            query=v.get('query','')
            rows=[c for c in self.customers if c['emailMarketingConsent']['marketingState']=='SUBSCRIBED']
            if 'number_of_orders' in query:rows=[c for c in self.customers if int(c['numberOfOrders'])>=2]
            if 'customer_added_date' in query:rows=[c for c in self.customers if c['createdAt'][:10]>=query.rsplit(' ',1)[-1]]
            return {'customerSegmentMembers':{'totalCount':len(rows)}}
        if doc==q.ORDERS:return {'customer':{'orders':page(self.orders[v['id']],v.get('after'),20)}}
        if doc==q.FIRST_ORDER:return {'customer':{'orders':page(list(reversed(self.orders[v['id']])),size=1)}}
        if doc==q.ORDER:return {'order':deepcopy(next((o for rows in self.orders.values() for o in rows if o['id']==v['id']),None))}
        if doc==q.PRODUCTS:return {'nodes':deepcopy([p for p in self.products if p['id'] in v['ids']])}
        if doc==q.SEGMENTS:return {'segments':page(self.segments,v.get('after'))}
        if doc==q.SEGMENT:return {'segment':deepcopy(next((s for s in self.segments if s['id']==v['id']),None))}
        if doc==q.MEMBERS:
            rows=[c for c in self.customers if c['emailMarketingConsent']['marketingState']=='SUBSCRIBED'];p=page(rows,v.get('after'))
            return {'customerSegmentMembers':{'edges':[{'node':{'id':c['id'].replace('/Customer/','/CustomerSegmentMember/')}} for c in p['nodes']],'pageInfo':p['pageInfo'],'totalCount':len(rows)}}
        if doc==q.MEMBERSHIPS:return {'customerSegmentMembership':{'memberships':[{'segmentId':s,'isMember':True} for s in v['segments']]}}
        if doc==q.CHECKOUTS:return {'abandonedCheckouts':page(self.checkouts,v.get('after'),25)}
        if doc==q.CHECKOUT:return {'node':deepcopy(next((c for c in self.checkouts if c['id']==v['id']),None))}
        raise AssertionError('Unexpected fixture query')

class ResendFixture:
    def __init__(self):self.sent=[];self.blocked=False;self.error=None;self.checks=[]
    def suppressed(self,address):self.checks.append(address);return self.blocked
    def suppress(self,address):self.blocked=True
    def recipient_for(self,provider_id,hashed):
        from crm_logic import recipient_hash
        return next((r[0] for r in self.sent if recipient_hash(r[0])==hashed),None)
    def send(self,address,message,key,test=False):
        self.sent.append((address,message,key,test))
        if self.error:raise self.error
        return 'fixture-'+str(len(self.sent))
