from copy import deepcopy
import unittest
import os
import uuid
from unittest.mock import Mock,patch
from crm_personalisation import render,resolve,validate,short_name,values_from_preview


def document(subject='{{first_name}}, see your {{short_product_name}}',preview='{{sport_category}} · {{product_name}}'):
    return {'content':{'subject':subject,'preheader':preview}}


class PersonalisationTests(unittest.TestCase):
    def setUp(self):
        self.customer={'id':'gid://shopify/Customer/1','firstName':"Anne-Marie O’Neil"}
        self.source={'id':'gid://shopify/AbandonedCheckout/1','customer':self.customer,'lineItems':{'nodes':[
            {'id':'gid://shopify/LineItem/1','title':"Dick Johnson Crash – Bathurst 1980 Collector's Wall Art",'product':{'id':'gid://shopify/Product/8'}},
            {'title':'Unrelated NBA artwork','product':{'id':'gid://shopify/Product/9'}}]}}
        self.edition={'shopify_product_id':'8','edition_total':150,'next_edition_number':78,'sold_count':77,'remaining_count':73,'active':True}
        self.reader=Mock(return_value=[self.edition]);self.metadata=Mock(return_value={'classifications':['Best Sellers','Motorsport']})
    def facts(self,**kw):return resolve(self.source,self.customer,edition_reader=self.reader,metadata_reader=self.metadata,**kw)
    def test_all_five_exact_primary_identity_and_no_mutation(self):
        facts=self.facts();doc=document();before=deepcopy(doc)
        result=render(doc,facts)
        self.assertEqual(result['content']['subject'],"Anne-Marie O’Neil, see your Dick Johnson Crash – Bathurst 1980")
        self.assertNotIn('NBA',str(result));self.assertEqual(doc,before)
        self.assertEqual(render(document('Next available edition: {{edition_number}}',''),facts)['content']['subject'],'Next available edition: #078/150')
        self.reader.assert_called_once_with(product_ids=['gid://shopify/Product/8'],handles=[],limit=2)
    def test_missing_names_and_field_fallbacks(self):
        for name in ('',None,'null','undefined','123','\r\nBcc: secret','{{product_name}}'):
            with self.subTest(name=name):
                self.assertEqual(render(document('{{first_name}}, see your edition',''),{'first_name':name})['content']['subject'],'See your edition')
        for facts in ({},{'product_name':'x'*300}):
            result=render(document('Your {{product_name}} awaits','{{first_name}} {{sport_category}}'),facts)
            self.assertEqual(result['content']['subject'],'See your selected artwork')
            self.assertNotIn('{{',str(result))
        self.assertEqual(render(document('{{first_name}},',''),{})['content']['subject'],'See your selected artwork')
    def test_injection_unsupported_malformed_and_length_rejected(self):
        for text in ('{{email}}','{{first_name | upper}}','{% if x %}','{{first_name','x}}','hi\r\nBcc: a','x\x00', 'x'*251+'{{first_name}}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):validate(document(text,''))
        self.assertEqual(render(document('{{product_name}}',''),{'product_name':'{{first_name}}'})['content']['subject'],'See your selected artwork')
    def test_categories_ambiguous_and_marketing_fallback(self):
        for categories in (['NBA','Formula One'],['Best Sellers'],[]):
            self.metadata.return_value={'classifications':categories}
            self.assertNotIn('sport_category',self.facts())
        self.metadata.return_value={'classifications':['Motorsport','Formula One']}
        self.assertEqual(self.facts()['sport_category'],'Formula One')
    def test_edition_fresh_sold_out_missing_ambiguous_and_blocked(self):
        self.assertEqual(self.facts()['edition_number'],'#078/150')
        self.edition['next_edition_number']=79
        self.assertEqual(self.facts()['edition_number'],'#079/150')
        for rows in ([],[self.edition,self.edition],[dict(self.edition,remaining_count=0)],[dict(self.edition,allocation_blocked=True)], [dict(self.edition,next_edition_number=151)]):
            self.reader.return_value=rows;self.assertNotIn('edition_number',self.facts())
        self.assertEqual(render(document('Next available edition: {{edition_number}}',''),{})['content']['subject'],'Check current edition availability')
    def test_reservation_claims_blocked_and_paid_uses_allocation_only(self):
        for text in ('Your reserved edition is {{edition_number}}','Your edition {{edition_number}}','Guaranteed next available edition: {{edition_number}}'):
            with self.assertRaises(ValueError):validate(document(text,''))
        allocated=Mock(return_value='#004/50')
        self.assertEqual(self.facts(trigger='post_purchase',allocation_reader=allocated)['edition_number'],'#004/50')
        self.reader.assert_not_called()
        allocated.return_value=None
        self.assertNotIn('edition_number',self.facts(trigger='post_purchase',allocation_reader=allocated))
    def test_conservative_shortening_preserves_identities(self):
        for value in ('Warne 1999 Rivalry','Crash – Bathurst 1980','Shane Warne Nostalgic Tribute'):
            self.assertEqual(short_name(value+' Limited Edition Wall Art'),value)
    def test_plain_published_documents_unchanged_and_preview_same_rules(self):
        plain=document('Original subject','Original preview');self.assertEqual(render(plain,{}),plain)
        facts=self.facts();data={'personalisation':facts}
        self.assertEqual(render(document(),values_from_preview(data)),render(document(),facts))
    def test_name_only_never_reads_product_or_edition(self):
        self.assertEqual(resolve(self.source,self.customer,wanted={'first_name'},metadata_reader=self.metadata,edition_reader=self.reader),{'first_name':self.customer['firstName']})
        self.metadata.assert_not_called();self.reader.assert_not_called()
    def test_runtime_identity_gate_and_exact_render(self):
        from crm_automation_runtime import render as live_render
        from tests.test_crm_simple_editor import document as full_document
        from tests.test_crm_send_flow import CFG
        doc=full_document();doc['content'].update(subject='{{first_name}}, your {{product_name}}',preheader='Next available edition: {{edition_number}}')
        frozen={'document':doc,'render_settings':CFG,'trigger':'abandoned'}
        row={'id':'11111111-1111-1111-1111-111111111111','shopify_customer_id':self.customer['id']}
        ctx={'_customer':self.customer,'_checkout':self.source,'_checkout_id':self.source['id']}
        with patch('crm_personalisation.resolve',return_value=self.facts()),patch('crm_campaign_send.production_checks',return_value={'ready':True}):
            message=live_render(frozen,row,'https://example.test/unsubscribe',ctx)
            self.assertIn("Anne-Marie O’Neil, your Dick Johnson",message['subject'])
            self.assertNotIn('{{',message['html']);self.assertIn('#078/150',message['html'])
            self.assertIn('{{first_name}}',frozen['document']['content']['subject'])
            with self.assertRaisesRegex(ValueError,'recipient context'):
                live_render(frozen,{**row,'shopify_customer_id':'other'},'https://example.test/unsubscribe',ctx)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable CRM PostgreSQL required')
class PersonalisationSQLTests(unittest.TestCase):
    def test_exact_mapping_read_only_queries_and_allocation_isolation(self):
        from tests.crm_db_fixture import connect
        from tests.test_meta_posting_jobs_sql import SQLConnection
        from crm_personalisation_data import metadata,allocation
        with connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS shopify_products(shopify_product_id text,product_type text,raw_json jsonb)')
            conn.execute("ALTER TABLE edition_orders ADD COLUMN IF NOT EXISTS shopify_order_id text, ADD COLUMN IF NOT EXISTS shopify_line_item_id text, ADD COLUMN IF NOT EXISTS shopify_product_gid text, ADD COLUMN IF NOT EXISTS shopify_product_id text, ADD COLUMN IF NOT EXISTS allocation_valid boolean, ADD COLUMN IF NOT EXISTS identity_enforced boolean, ADD COLUMN IF NOT EXISTS status text")
            conn.execute("INSERT INTO shopify_products VALUES('987654321','Formula One','{\"tags\":[\"Best Sellers\"]}')")
            conn.execute("INSERT INTO edition_orders(shopify_customer_id,shopify_order_id,shopify_line_item_id,shopify_product_id,edition_number,edition_total,allocation_valid,identity_enforced,status) VALUES('123','456','789','987654321',17,50,true,true,'allocated')")
        with patch('supabase_backend.connect',SQLConnection):
            self.assertEqual(metadata('gid://shopify/Product/987654321')['classifications'],['Formula One','Best Sellers'])
            self.assertEqual(allocation('gid://shopify/Order/456','gid://shopify/Customer/123','gid://shopify/Product/987654321','gid://shopify/LineItem/789'),'#017/50')
            self.assertIsNone(allocation('456','999','987654321','789'))
            self.assertIsNone(allocation('456','123','987654322','789'))
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT edition_number FROM edition_orders WHERE shopify_order_id='456'").fetchone()['edition_number'],17)

    def test_published_checkout_delivery_and_test_send_use_same_substitution(self):
        from tests.test_crm_native_automations import NativeAutomationTests
        fixture=NativeAutomationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        from tests.test_crm_abandoned_checkout import checkout,native_document
        from crm_automation_definition import email_step
        from crm_automation_runtime import enter,advance
        from crm_logic import now
        from datetime import timedelta
        doc=native_document();doc['content'].update(subject='{{first_name}}, see {{product_name}}',preheader='See {{short_product_name}}')
        a=fixture.store.create(ADMIN,'abandoned','Personalisation fixture');fixture.created.append(str(a['id']))
        flow=deepcopy(a['config']['draft']);flow['emails']=[email_step(doc,0),email_step(doc,43200)]
        a=fixture.store.save_flow(ADMIN,a['id'],a['name'],flow,1)
        a=fixture.store.publish(ADMIN,a['id'],a['config']['revision'],env=LIVE)
        cart=checkout(751);cart['customer']=deepcopy(fixture.customer);cart['createdAt']=(now()+timedelta(seconds=1)).isoformat()
        cart['lineItems']['nodes'][0]['title']='Bathurst 1980 Wall Art';fixture.shop.checkout.return_value=cart
        journey=enter(fixture.engine,a,fixture.customer['id'],cart['id'],str(uuid.uuid4()),now()+timedelta(seconds=2))
        advance(fixture.engine,fixture.due(journey));fixture.engine.send_one()
        fixture.provider.send.assert_called_once();message=fixture.provider.send.call_args.args[1]
        self.assertEqual(message['subject'],'Fixture, see Bathurst 1980 Wall Art')
        self.assertNotIn('{{',message['html']);self.assertIn('See Bathurst 1980',message['html'])
        frozen=fixture.store.template(journey['steps'][0]['template_id'],journey['steps'][0]['template_version'])
        self.assertIn('{{first_name}}',frozen['document']['content']['subject'])
        fixture.store.step_id=flow['emails'][0]['step_id'];fixture.store.draft_identity=a['id']
        fixture.store.preview_shop=Mock();fixture.store.preview_shop.abandoned_preview.return_value={'nodes':[cart],'pageInfo':{'hasNextPage':False}}
        test_doc=fixture.store.test_document(doc,str(uuid.uuid4()))
        self.assertEqual(test_doc['content']['subject'],message['subject'])
        from crm_campaign_send import send_test
        from tests.crm_fixtures import TestRecipientShop
        editor=fixture.store.draft(a['id']);wire=Mock()
        wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        with patch('crm_resend_marketing._audit',return_value=True),patch('crm_test_recipient.Shopify',return_value=TestRecipientShop()):
            send_test(fixture.store,ADMIN,editor,'internal@example.test',str(uuid.uuid4()),env=LIVE,session=wire)
        wire.post.assert_called_once()
        self.assertEqual(wire.post.call_args.kwargs['json']['subject'],'[CAMPAIGN TEST] '+message['subject'])
        fixture.shop.abandoned_preview.assert_not_called()


if __name__=='__main__':unittest.main()
