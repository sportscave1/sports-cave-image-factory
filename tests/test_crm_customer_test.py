"""Recipient-specific manual tests: synthetic Shopify, mocked Resend, disposable SQL."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from tests.test_crm_abandoned_checkout import checkout,native_document
from tests.crm_fixtures import TestRecipientShop
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE,CFG
from crm_test_checkout import owned_checkout,contact_record,document
from crm_test_recipient import authorize_internal

ADDRESS='internal@example.test'
USER={**ADMIN,'email':ADDRESS}

def fixture(shop=None,cart=None):
    shop=shop or Mock();cart=deepcopy(cart or checkout(83))
    customer=TestRecipientShop().customers(query='email:"'+ADDRESS+'"',fresh=True)['nodes'][0]
    cart['customer']=customer
    cart['abandonedCheckoutUrl']='https://www.sportscaveshop.com/checkouts/83/recover?key=opaque%2Bvalue&locale=en#details'
    for i,line in enumerate(cart['lineItems']['nodes']):
        line['variant']={'id':'gid://shopify/ProductVariant/'+str(100+i),'availableForSale':True,
                         'product':{'id':'gid://shopify/Product/10','status':'ACTIVE','onlineStoreUrl':'https://www.sportscaveshop.com/products/fixture'}}
    evidence={'id':83,'email':ADDRESS,'customer':{'id':customer['id'].rsplit('/',1)[-1]},
              'abandoned_checkout_url':cart['abandonedCheckoutUrl'],'completed_at':None,'closed_at':None,
              'line_items':[{'variant_id':100+i,'quantity':x['quantity']} for i,x in enumerate(cart['lineItems']['nodes'])]}
    # Match arbitrary fixture checkout IDs without putting real data in tests.
    evidence['id']=int(cart['id'].rsplit('/',1)[-1])
    shop.customers.return_value={'nodes':[customer],'pageInfo':{'hasNextPage':False}}
    shop.recent_test_checkouts.return_value={'nodes':[cart],'pageInfo':{'hasNextPage':False}}
    shop.checkout.return_value=cart
    return shop,cart,customer,evidence

class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.shop,self.cart,self.customer,self.evidence=fixture()
        editions=patch('supabase_backend.list_edition_products_read_only',return_value=[])
        editions.start();self.addCleanup(editions.stop)
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('No network'))
        self.guard.start();self.addCleanup(self.guard.stop)
    def owned(self):return owned_checkout(self.shop,ADDRESS,self.customer,contact_reader=lambda c:self.evidence)
    def test_newest_matching_checkout_skips_other_customers_and_completed(self):
        other=deepcopy(self.cart);other['customer']['email']='other@example.test'
        completed=deepcopy(self.cart);completed['completedAt']='2026-10-09'
        self.shop.recent_test_checkouts.return_value['nodes']=[other,completed,self.cart]
        self.assertEqual(self.owned(),self.cart);self.shop.checkout.assert_called_once_with(self.cart['id'],fresh=True)
    def test_no_match_never_fetches_private_checkout(self):
        self.shop.recent_test_checkouts.return_value['nodes'][0]['customer']['email']='other@example.test'
        with self.assertRaises(ValueError):self.owned()
        self.shop.checkout.assert_not_called()
    def test_contact_email_must_match_separately_from_customer(self):
        self.evidence['email']='other@example.test'
        with self.assertRaisesRegex(ValueError,'No matching'):self.owned()
    def test_identity_variants_quantity_price_url_and_complete_state_fail_closed(self):
        mutations=[lambda c,e:e.update(id=99),lambda c,e:e['customer'].update(id='99'),
                   lambda c,e:e.update(abandoned_checkout_url='https://www.sportscaveshop.com/checkouts/other'),
                   lambda c,e:e['line_items'][0].update(quantity=1),lambda c,e:c['lineItems']['pageInfo'].update(hasNextPage=True),
                   lambda c,e:c['lineItems']['nodes'][0]['variant'].update(availableForSale=False),
                   lambda c,e:c.update(completedAt='2026-10-09'),lambda c,e:e.update(completed_at='2026-10-09'),
                   lambda c,e:c['lineItems']['nodes'][0]['discountedTotalPriceWithCodeDiscount']['presentmentMoney'].update(amount='NaN')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.shop,self.cart,self.customer,self.evidence=fixture();mutation(self.cart,self.evidence)
                with self.assertRaises(ValueError):self.owned()
    def test_pagination_bounded_and_reverse_query_is_separate_from_production(self):
        from crm_shopify import TEST_CHECKOUTS,CHECKOUTS
        self.assertIn('reverse:true',TEST_CHECKOUTS);self.assertNotIn('reverse:true',CHECKOUTS)
        self.shop.recent_test_checkouts.side_effect=[{'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'next'}},
                                                   {'nodes':[self.cart],'pageInfo':{'hasNextPage':False}}]
        self.assertEqual(self.owned(),self.cart);self.assertEqual(self.shop.recent_test_checkouts.call_args.kwargs,{'after':'next'})
    def test_authorization_has_no_ui_owned_allowlist(self):
        authorize_internal(USER,ADDRESS,{})
        authorize_internal(ADMIN,ADDRESS,{'CRM_INTERNAL_TEST_RECIPIENTS':ADDRESS})
        for user,recipient in ((ADMIN,ADDRESS),({**USER,'role':'worker'},ADDRESS),(USER,'other@example.test')):
            with self.assertRaises(PermissionError):authorize_internal(user,recipient,{})
    def test_rest_read_is_bounded_authenticated_and_errors_do_not_leak(self):
        cfg={'store_domain':'fixture.myshopify.com','api_version':'2026-04'}
        with patch('shopify_sync.get_config',return_value=cfg),patch('shopify_sync.get_shopify_access_token',return_value='fixture-secret'),patch('requests.get') as get:
            get.return_value=Mock(status_code=200,json=lambda:{'checkouts':[self.evidence]})
            self.assertEqual(contact_record(self.cart),self.evidence)
            self.assertFalse(get.call_args.kwargs['allow_redirects']);self.assertEqual(get.call_args.kwargs['timeout'],10)
            get.side_effect=RuntimeError('private-token')
            with self.assertRaises(ValueError) as error:contact_record(self.cart)
            self.assertNotIn('private-token',str(error.exception))
    def test_production_hydration_preserves_original_url_and_draft(self):
        from crm_campaign_content import render_campaign
        from crm_recovery_links import inspect,checkout_url
        doc=native_document();doc['content'].update(subject='{{first_name}}, your artwork',preheader='Your {{product_name}} awaits')
        before=deepcopy(doc)
        with patch('crm_test_checkout.contact_record',return_value=self.evidence):result=document(self.shop,doc,ADDRESS,self.customer)
        message=render_campaign(result,CFG,production=True,test_tracking=True,unsubscribe_url='https://www.sportscaveshop.com/account/unsubscribe?token=fixture')
        urls=[u for u in inspect(message['html']).urls if checkout_url(u)]
        self.assertTrue(urls);self.assertEqual(set(urls),{self.cart['abandonedCheckoutUrl']})
        self.assertNotIn('Recovery action disabled',message['html']);self.assertNotIn('{{',message['html'])
        self.assertIn('A$199.50',message['html']);self.assertIn('Black frame / Large',message['html'])
        self.assertEqual(doc,before)

    def test_every_configured_recovery_action_and_wall_preview(self):
        from tests.test_crm_recovery_elements import design,html_section
        from crm_checkout_elements import element
        from crm_campaign_content import render_campaign
        from crm_recovery_links import inspect,checkout_url
        html=''.join('<a href="SC_CHECKOUT_RECOVERY_URL">'+name+'</a>' for name in ('Black','Oak','White','Complete Your Order','Claim Your Edition','Secure My Edition'))
        doc=design(element('product_image'),element('lifestyle',position=2),element(action='wall'),html_section(html))
        self.shop.campaign_images.return_value={'nodes':[{'url':'https://cdn.shopify.com/product.png'},{'url':'https://cdn.shopify.com/lifestyle.png'}]}
        with patch('crm_test_checkout.contact_record',return_value=self.evidence):result=document(self.shop,doc,ADDRESS,self.customer)
        msg=render_campaign(result,CFG,production=True,test_tracking=True,unsubscribe_url='https://www.sportscaveshop.com/account/unsubscribe?token=fixture')
        urls=inspect(msg['html']).urls;recovery=[u for u in urls if checkout_url(u)]
        self.assertEqual(recovery,[self.cart['abandonedCheckoutUrl']]*8)
        wall=[u for u in urls if 'sc_wall_preview=1' in u]
        self.assertEqual(len(wall),1);self.assertIn('/products/fixture',wall[0]);self.assertNotIn('/checkouts/',wall[0])
        self.assertIn('lifestyle.png',msg['html']);self.shop.campaign_images.assert_called_once()

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CustomerSendTests(unittest.TestCase):
    def setUp(self):
        from tests.test_crm_native_automations import NativeAutomationTests
        from crm_automation_definition import email_step
        f=NativeAutomationTests();f.setUp();self.addCleanup(f.doCleanups);self.f=f
        editions=patch('supabase_backend.list_edition_products_read_only',return_value=[])
        editions.start();self.addCleanup(editions.stop)
        self.shop,self.cart,self.customer,self.evidence=fixture();f.store.preview_shop=self.shop
        a=f.store.create(ADMIN,'abandoned','Recipient test fixture');f.created.append(str(a['id']))
        flow=deepcopy(a['config']['draft']);flow['emails']=[email_step(native_document(),0)]
        a=f.store.save_flow(ADMIN,a['id'],a['name'],flow,1);f.store.step_id=flow['emails'][0]['step_id']
        self.editor=f.store.draft(a['id']);self.operation=str(uuid.uuid4());self.wire=Mock()
        self.wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        for p in (patch('crm_test_checkout.contact_record',return_value=self.evidence),patch('crm_resend_marketing._audit',return_value=True)):
            p.start();self.addCleanup(p.stop)
    def send(self):
        from crm_campaign_send import send_test
        return send_test(self.f.store,USER,self.editor,ADDRESS,self.operation,env=LIVE,session=self.wire)
    def test_actual_transport_retry_does_not_revalidate_or_send_twice_and_no_journey(self):
        tables=['crm_automation_enrollments','crm_marketing_sends','edition_orders']
        before={t:self.f.store.q('SELECT count(*) n FROM '+t,one=True)['n'] for t in tables}
        first=self.send();self.shop.recent_test_checkouts.side_effect=RuntimeError('offline')
        second=self.send();self.assertEqual(first['message_id'],second['message_id']);self.wire.post.assert_called_once()
        message=self.wire.post.call_args.kwargs['json'];self.assertFalse(message['subject'].startswith('[CAMPAIGN TEST]'))
        self.assertIn('opaque%2Bvalue',message['html']);self.assertNotIn('Recovery action disabled',message['html'])
        for t in tables:self.assertEqual(self.f.store.q('SELECT count(*) n FROM '+t,one=True)['n'],before[t])
        receipt=self.f.store.q('SELECT * FROM crm_internal_tests WHERE id=%s',(self.operation,),True)
        self.assertEqual(receipt['status'],'ACCEPTED');self.assertNotIn('opaque',str(receipt))
    def test_unknown_provider_outcome_never_replays(self):
        import requests
        from crm_resend_marketing import DeliveryError
        self.wire.post.side_effect=requests.Timeout('synthetic')
        with self.assertRaises(DeliveryError):self.send()
        with self.assertRaises(ValueError):self.send()
        self.wire.post.assert_called_once()
    def test_missing_owned_checkout_has_no_provider_call(self):
        self.shop.recent_test_checkouts.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
        with self.assertRaisesRegex(ValueError,'No matching'):self.send()
        self.wire.post.assert_not_called()
