"""All discount/API/provider operations are local fixtures."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock,patch
import os
import unittest
import uuid
from crm_logic import now
from crm_discount_api import metadata,search,fresh,CACHE,SCOPES,LOOKUP,SEARCH,CHECKOUT,AUTOMATIC,CODES
from crm_recovery_discount import prepare,substitute,recovery_url,apply_links,DiscountHold,validate


def node(kind='DiscountCodeBasic'):
    return {'id':'gid://shopify/DiscountCodeNode/11','codeDiscount':{
        '__typename':kind,'title':'Fixture discount','status':'ACTIVE','startsAt':'2025-01-01T00:00:00Z','endsAt':None,
        'usageLimit':None,'asyncUsageCount':0,'appliesOncePerCustomer':False,
        'combinesWith':{'productDiscounts':False,'orderDiscounts':False,'shippingDiscounts':True},
        'discountClasses':['PRODUCT'],'context':{'__typename':'DiscountBuyerSelectionAll'},
        'summary':'Buy 2 get 1 free' if kind=='DiscountCodeBxgy' else 'A$5 off eligible products',
        'customerGets':{'value':{'__typename':'DiscountAmount','amount':{'amount':'5.0','currencyCode':'AUD'},'appliesOnEachItem':False},'items':{'__typename':'AllDiscountItems'}},
        'minimumRequirement':None,'codes':{'nodes':[{'code':'FIXTURE5'}],'pageInfo':{'hasNextPage':False,'endCursor':None}}}}


class DiscountShop:
    def __init__(self):
        self.namespace='discount-fixture-'+str(uuid.uuid4());self.node=node();self.calls=[];self.automatic=[]
        self.checkout={'id':'gid://shopify/AbandonedCheckout/1','customer':{'id':'gid://shopify/Customer/1'},
            'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/cn/abc/recover?key=a%2Bb&locale=en#payment',
            'completedAt':None,'discountCodes':[],'subtotalPriceSet':{'shopMoney':{'amount':'100','currencyCode':'AUD'}}}
    def query(self,query,variables,*args,**kwargs):
        self.calls.append((query,variables,kwargs))
        if query==SCOPES:return {'currentAppInstallation':{'accessScopes':[{'handle':'read_discounts'}]}}
        if query==LOOKUP:return {'codeDiscountNodeByCode':deepcopy(self.node)}
        if query==CHECKOUT:return {'node':deepcopy(self.checkout)}
        if query==AUTOMATIC:return {'discountNodes':{'nodes':deepcopy(self.automatic),'pageInfo':{'hasNextPage':False}}}
        if query==SEARCH:return {'discountNodes':{'nodes':[deepcopy(self.node)],'pageInfo':{'hasNextPage':False}}}
        if query==CODES:return {'node':deepcopy(self.node)}
        raise AssertionError('Unexpected API operation')


def doc(shop):
    row=metadata(shop.node,'FIXTURE5')
    return {'recovery_discount':{k:row[k] for k in ('id','code','type','value')},
            'content':{'subject':'Your offer: {{discount_code}}','preheader':'{{discount_value}}','body':'Use {{discount_code}}'},
            'custom_html':'<p>{{discount_value}}</p>'}


class DiscountTests(unittest.TestCase):
    def setUp(self):self.shop=DiscountShop();self.doc=doc(self.shop);self.cart=deepcopy(self.shop.checkout);self.cart['lineItems']={'nodes':[{'quantity':2,'variant':{'id':'v1'}}]}
    def ready(self):return prepare(self.shop,self.doc,self.cart,self.cart['customer']['id'])
    def test_types_values_are_from_shopify_never_code_name(self):
        self.assertEqual(self.doc['recovery_discount']['value'],'A$5 off')
        for kind in ('DiscountCodeBasic','DiscountCodeFreeShipping','DiscountCodeBxgy','DiscountCodeApp'):
            self.shop.node=node(kind);self.doc=doc(self.shop);result=self.ready()
            self.assertTrue(result['supported']);self.assertIn('discount=FIXTURE5',result['url'])
        self.shop.node=node();self.shop.node['codeDiscount']['customerGets']['value']={'__typename':'DiscountPercentage','percentage':.15}
        self.assertEqual(metadata(self.shop.node,'FIXTURE5')['value'],'15% off')
    def test_inactive_scheduled_expired_removed_and_changed_offer_hold(self):
        for field,value in [('status','EXPIRED'),('status','SCHEDULED'),('status','INACTIVE'),('startsAt',(now()+timedelta(days=1)).isoformat()),('endsAt',(now()-timedelta(days=1)).isoformat()),('usageLimit',0)]:
            with self.subTest(field=field,value=value):
                self.shop.node=node();self.shop.node['codeDiscount'][field]=value
                with self.assertRaises(DiscountHold):self.ready()
        self.shop.node=node();self.shop.node['codeDiscount']['customerGets']['value']['amount']['amount']='10'
        with self.assertRaisesRegex(DiscountHold,'offer_changed'):self.ready()
        self.shop.node=None
        with self.assertRaises(DiscountHold):self.ready()
    def test_original_url_query_bytes_fragment_and_variants_preserved(self):
        original=deepcopy(self.cart);result=self.ready()
        self.assertEqual(result['url'],self.cart['abandonedCheckoutUrl'].replace('#payment','&discount=FIXTURE5#payment'))
        self.assertEqual(self.cart,original)
        self.assertEqual(recovery_url(result['url'],'FIXTURE5'),result['url'])
        self.assertIn('discount=A%26B',recovery_url(self.cart['abandonedCheckoutUrl'],'A&B'))
    def test_existing_code_never_replaced_or_duplicated(self):
        for codes in (['BETTER15'],['FIXTURE5','BETTER15']):
            self.shop.checkout['discountCodes']=codes
            with self.assertRaisesRegex(DiscountHold,'existing_code_conflict'):self.ready()
        self.shop.checkout['discountCodes']=['FIXTURE5'];self.ready()
        for url in ('https://shop.test/checkouts/x?discount=BETTER','https://shop.test/checkouts/x?discount=FIXTURE5&discount=FIXTURE5'):
            with self.assertRaises(DiscountHold):recovery_url(url,'FIXTURE5')
    def test_multibuy_standard_best_offer_and_bxgy_app_conflicts(self):
        self.shop.automatic=[{'discount':{'__typename':'DiscountAutomaticBasic','discountClasses':['PRODUCT']}}]
        self.ready() # Shopify's documented best-discount choice, no code deletion.
        for kind in ('DiscountAutomaticBxgy','DiscountAutomaticApp','UnknownAutomatic'):
            self.shop.automatic=[{'discount':{'__typename':kind,'discountClasses':['PRODUCT'],'combinesWith':{}}}]
            with self.assertRaises(DiscountHold):self.ready()
    def test_minimum_quantity_spend_and_currency_guards(self):
        d=self.shop.node['codeDiscount'];d['minimumRequirement']={'__typename':'DiscountMinimumQuantity','greaterThanOrEqualToQuantity':'3'}
        with self.assertRaisesRegex(DiscountHold,'minimum_quantity'):self.ready()
        d['minimumRequirement']={'__typename':'DiscountMinimumSubtotal','greaterThanOrEqualToSubtotal':{'amount':'150','currencyCode':'AUD'}}
        with self.assertRaisesRegex(DiscountHold,'minimum_spend'):self.ready()
        d['minimumRequirement']['greaterThanOrEqualToSubtotal']={'amount':'10','currencyCode':'USD'}
        with self.assertRaisesRegex(DiscountHold,'minimum_spend'):self.ready()
    def test_customer_restrictions_remain_shopify_authority_identity_is_enforced(self):
        self.shop.node['codeDiscount']['context']={'__typename':'DiscountCustomers'}
        self.shop.node['codeDiscount']['appliesOncePerCustomer']=True;self.ready()
        self.shop.checkout['customer']['id']='different'
        with self.assertRaisesRegex(DiscountHold,'checkout_changed'):self.ready()
    def test_rendered_links_tracking_and_wall_preview_preserved(self):
        from html import escape
        url=self.cart['abandonedCheckoutUrl'];tracked=url.replace('#payment','&utm_campaign=fixture#payment')
        message={'subject':'Offer','html':'<a href="'+escape(tracked,quote=True)+'">Complete Your Order</a><a href="https://shop.test/wall-preview?product=8">Wall</a>', 'text':tracked}
        result=apply_links(message,self.ready());self.assertIn('utm_campaign=fixture',result['html']);self.assertIn('&amp;discount=FIXTURE5',result['html'])
        self.assertIn('https://shop.test/wall-preview?product=8',result['html']);self.assertNotIn('discount=',message['html'])
    def test_substitution_frozen_content_and_safe_unselected_validation(self):
        before=deepcopy(self.doc);result=substitute(self.doc)
        self.assertEqual(result['content']['subject'],'Your offer: FIXTURE5');self.assertIn('A$5 off',result['custom_html']);self.assertEqual(self.doc,before)
        self.doc.pop('recovery_discount')
        with self.assertRaises(DiscountHold):substitute(self.doc)
    def test_search_cache_refresh_and_exact_code_are_bounded(self):
        first=search(self.shop,'FIXTURE5');count=len(self.shop.calls);self.assertEqual(search(self.shop,'FIXTURE5'),first);self.assertEqual(len(self.shop.calls),count)
        search(self.shop,'FIXTURE5',refresh=True);self.assertGreater(len(self.shop.calls),count)
        self.assertIn('first:15',SEARCH);self.assertIn('first:20',SEARCH)
        fresh(self.shop,self.doc['recovery_discount']);self.assertTrue(self.shop.calls[-1][2]['fresh'])
    def test_bulk_code_pages_and_permission_failure(self):
        from crm_discount_api import code_page,require_scope
        codes=self.shop.node['codeDiscount']['codes'];codes['pageInfo']={'hasNextPage':True,'endCursor':'page2'}
        result=search(self.shop);self.assertEqual(len(result['more_codes']),1)
        result=code_page(self.shop,self.shop.node['id'],'page2');self.assertEqual(result['more_codes'][0]['after'],'page2')
        self.assertEqual(self.shop.calls[-1][1]['codesAfter'],'page2')
        self.shop.query=Mock(return_value={'currentAppInstallation':{'accessScopes':[]}})
        with self.assertRaisesRegex(ValueError,'read_discounts'):require_scope(self.shop)
    def test_rate_limit_network_and_unknown_checkout_hold(self):
        for error in (TimeoutError('private connection data'),RuntimeError('429 private payload')):
            self.shop.query=Mock(side_effect=error)
            with self.assertRaisesRegex(DiscountHold,'verification_unavailable') as raised:self.ready()
            self.assertNotIn('private',str(raised.exception))
    def test_unavailable_products_and_header_or_url_injection(self):
        self.cart['lineItems']['nodes'][0]['variant']['availableForSale']=False
        with self.assertRaisesRegex(DiscountHold,'product_unavailable'):self.ready()
        self.doc['content']['subject']='bad\r\nheader'
        with self.assertRaisesRegex(DiscountHold,'invalid_header'):substitute(self.doc)
        self.doc=doc(self.shop);self.doc['content']['cta_url']='https://example.test/{{discount_code}}'
        with self.assertRaisesRegex(DiscountHold,'variable_in_url'):substitute(self.doc)
    def test_reciprocal_app_combinations_and_currency_labels(self):
        self.shop.node['codeDiscount']['combinesWith']['productDiscounts']=True
        self.shop.automatic=[{'discount':{'__typename':'DiscountAutomaticApp','discountClasses':['PRODUCT'],'combinesWith':{'productDiscounts':True}}}]
        self.ready()
        for code,label in [('USD','US$5 off'),('NZD','NZ$5 off'),('JPY','JPY 5 off')]:
            self.shop.node['codeDiscount']['customerGets']['value']['amount']['currencyCode']=code
            self.assertEqual(metadata(self.shop.node,'FIXTURE5')['value'],label)


if __name__=='__main__':unittest.main()
