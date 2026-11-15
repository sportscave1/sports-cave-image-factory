"""Local SQL and fake Shopify only: creative freedom must not mutate LIVE."""
from copy import deepcopy
import os
import unittest
import uuid
from crm_middle_sections import apply_event,middle_sections
from tests.test_crm_discount_editor_v2 import event
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class V6PublicationTests(unittest.TestCase):
    def test_reusable_template_retains_hidden_html_and_independent_copies(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from crm_campaign_library import insert_saved_template,template_sections
        from crm_campaign_content import new_document
        from crm_middle_sections import commit_middle
        from crm_discount_section import section
        from crm_template_cache import invalidate
        store=CampaignStore(connect);doc=new_document();doc.update(content_mode='HTML',custom_html='')
        source='<style>.title{color:#123456}</style><!-- keep exactly --><h2 class="title">Custom</h2>'
        creative=section();creative['html']='<p>Unfinished creative'
        commit_middle(doc,[dict(id='hidden-source',type='html',html_number=1,visible=False,html=source),creative])
        row=store.save_design(ADMIN,'V6 source '+uuid.uuid4().hex,doc)
        self.addCleanup(lambda:store.archive_design(ADMIN,row['id'],row['version']))
        self.addCleanup(invalidate)
        self.assertEqual(template_sections(store,row),doc['middle_sections'])
        target=new_document();target.update(content_mode='HTML',custom_html='')
        insert_saved_template(store,target,row['id'],row['version'])
        self.assertFalse(target['middle_sections'][0]['visible'])
        self.assertEqual(target['middle_sections'][0]['html'],source)
        self.assertEqual(target['middle_sections'][1]['html'],creative['html'])
        self.assertEqual(target['middle_sections'][1]['type'],'discount')
        self.assertNotIn('recovery_discount',target)
        self.assertNotEqual(target['middle_sections'][0]['id'],'hidden-source')
        target['middle_sections'][0]['html']='changed locally'
        self.assertEqual(template_sections(store,row)[0]['html'],source)

    def test_code_free_creative_saved_published_and_rendered_with_verified_offer(self):
        from tests.test_crm_discount_delivery import DiscountDeliveryTests
        from crm_recovery_discount import prepare
        from crm_recovery_links import inspect,verify
        from crm_automation_runtime import render
        fixture=DiscountDeliveryTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        store=fixture.f.store;old=deepcopy(fixture.a['config']['published_flow'])
        for source in ('<p>Personal invitation</p>','<p>{{discount_value}}</p>'):
            row=store.flow(fixture.a['id']);flow=deepcopy(row['config']['draft']);doc=flow['emails'][2]['document']
            section=next(s for s in middle_sections(doc) if s['type']=='discount')
            apply_event(doc,event(doc,'html',id=section['id'],html=source))
            saved=store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
            self.assertEqual(store.flow(row['id'])['config']['published_flow'],old)
            self.assertEqual(saved['config']['draft']['emails'][2]['document']['middle_sections'][-1]['html'],source)
            published=store.publish(ADMIN,row['id'],saved['config']['revision'],env=LIVE)
            frozen=published['config']['published_flow']['emails'][2]['document']
            verified=prepare(fixture.discounts,frozen,fixture.cart,fixture.cart['customer']['id'])
            content=store.template(published['steps'][2]['template_id'],published['steps'][2]['template_version'])
            message=render(content,{'id':str(uuid.uuid4()),'shopify_customer_id':fixture.cart['customer']['id']},
                'https://example.test/unsubscribe',{'_checkout':fixture.cart,'_checkout_id':fixture.cart['id'],
                '_customer':fixture.cart['customer'],'_recovery_discount':verified})
            urls=[u for u in inspect(message['html']).urls if '/checkouts/' in u]
            self.assertTrue(urls);verify(message,verified['url'],len(urls))
            self.assertIn('https://example.test/unsubscribe',message['html'])
            self.assertEqual(verified['original_url'],fixture.cart['abandonedCheckoutUrl'])
            self.assertEqual(frozen['recovery_discount'],doc['recovery_discount'])
            self.assertNotIn('{{discount_',message['html'])
            fixture.f.provider.send.assert_not_called()
            old=deepcopy(published['config']['published_flow'])
