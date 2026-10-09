"""Disposable PostgreSQL, Shopify fixtures and mocked Resend; no live delivery."""
from copy import deepcopy
from datetime import timedelta
import os
import unittest
import uuid
from unittest.mock import patch,Mock
from tests.test_crm_discounts import DiscountShop,doc
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE
from tests.test_crm_abandoned_checkout import checkout,native_document
from crm_automation_definition import email_step
from crm_automation_runtime import enter,advance
from crm_logic import now


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DiscountDeliveryTests(unittest.TestCase):
    def setUp(self):
        from tests.test_crm_native_automations import NativeAutomationTests
        f=NativeAutomationTests();f.setUp();self.addCleanup(f.doCleanups);self.f=f
        self.discounts=DiscountShop();f.shop.query.side_effect=self.discounts.query
        cart=checkout(9751);cart['customer']=deepcopy(f.customer);cart['createdAt']=(now()+timedelta(seconds=1)).isoformat()
        f.shop.checkout.return_value=cart;self.discounts.checkout.update(id=cart['id'],customer=deepcopy(f.customer),abandonedCheckoutUrl=cart['abandonedCheckoutUrl'])
        self.cart=cart
        a=f.store.create(ADMIN,'abandoned','Discount fixture');f.created.append(str(a['id']))
        flow=deepcopy(a['config']['draft']);flow['emails']=[email_step(native_document(),d) for d in (0,43200,86400)]
        third=flow['emails'][2]['document'];offer=doc(self.discounts)
        third['recovery_discount']=offer['recovery_discount'];third['content'].update(subject=offer['content']['subject'],preheader=offer['content']['preheader'])
        self.flow=flow
        a=f.store.save_flow(ADMIN,a['id'],a['name'],flow,1)
        self.a=f.store.publish(ADMIN,a['id'],a['config']['revision'],env=LIVE)
        self.j=enter(f.engine,self.a,f.customer['id'],cart['id'],str(uuid.uuid4()),now()+timedelta(seconds=2))
        frequency=patch('crm_workspace_store.WorkspaceRecords.frequency_blocked',return_value=False);frequency.start();self.addCleanup(frequency.stop)
    def send_step(self):
        advance(self.f.engine,self.f.due(self.j));self.f.engine.send_one();advance(self.f.engine,self.f.due(self.j))
    def test_email_three_only_frozen_versions_tracking_and_no_duplicates(self):
        f=self.f;frozen=deepcopy(self.j['steps'])
        self.send_step();self.send_step();self.assertEqual(self.discounts.calls,[])
        # A newly published selection cannot rewrite this customer's frozen journey.
        flow=deepcopy(self.flow);flow['emails'][2]['document'].pop('recovery_discount')
        flow['emails'][2]['document']['content'].update(subject='New future version',preheader='New future version')
        saved=f.store.save_flow(ADMIN,self.a['id'],self.a['name'],flow,self.a['config']['revision'])
        f.store.publish(ADMIN,saved['id'],saved['config']['revision'],env=LIVE)
        self.send_step();self.assertEqual(f.provider.send.call_count,3)
        messages=[c.args[1] for c in f.provider.send.call_args_list]
        self.assertNotIn('discount=',messages[0]['html']);self.assertNotIn('discount=',messages[1]['html'])
        self.assertEqual(messages[2]['subject'],'Your offer: FIXTURE5');self.assertIn('A$5 off',messages[2]['html'])
        self.assertIn('discount=FIXTURE5',messages[2]['html']);self.assertNotIn('{{',messages[2]['html'])
        self.assertEqual(f.store.q('SELECT steps FROM crm_automation_enrollments WHERE id=%s',(self.j['id'],),True)['steps'],frozen)
        f.engine.send_one();self.assertEqual(f.provider.send.call_count,3)
        self.assertEqual(f.store.template(frozen[2]['template_id'],frozen[2]['template_version'])['document']['recovery_discount'],self.flow['emails'][2]['document']['recovery_discount'])
    def test_expired_third_email_is_held_with_actionable_reason(self):
        self.send_step();self.send_step();self.discounts.node['codeDiscount']['status']='EXPIRED';self.send_step()
        self.assertEqual(self.f.provider.send.call_count,2)
        row=self.f.store.q('SELECT status,error_code FROM crm_marketing_sends WHERE enrollment_id=%s AND step_index=2',(self.j['id'],),True)
        self.assertEqual(row['status'],'BLOCKED');self.assertIn('discount_not_active',row['error_code'])
        self.f.engine.send_one();self.assertEqual(self.f.provider.send.call_count,2)
    def test_purchase_before_third_preserves_cancellation(self):
        self.send_step();self.send_step();self.cart['completedAt']=now().isoformat();self.send_step()
        self.assertEqual(self.f.provider.send.call_count,2);self.assertEqual(self.discounts.calls,[])
    def test_verification_timeout_never_submits_or_retries_provider(self):
        self.send_step();self.send_step();self.f.shop.query.side_effect=TimeoutError('Synthetic timeout')
        self.send_step();self.f.engine.send_one();self.assertEqual(self.f.provider.send.call_count,2)
        row=self.f.store.q('SELECT status,error_code FROM crm_marketing_sends WHERE enrollment_id=%s AND step_index=2',(self.j['id'],),True)
        self.assertEqual(row['status'],'BLOCKED');self.assertIn('discount_verification_unavailable',row['error_code'])
    def test_mocked_internal_provider_has_resolved_offer_and_disabled_recovery(self):
        f=self.f;f.store.step_id=self.flow['emails'][2]['step_id'];f.store.draft_identity=self.a['id']
        f.store.preview_shop=f.shop;f.shop.abandoned_preview.return_value={'nodes':[self.cart],'pageInfo':{'hasNextPage':False}}
        from crm_campaign_send import send_test
        from tests.crm_fixtures import TestRecipientShop
        editor=f.store.draft(self.a['id']);wire=Mock();wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        with patch('crm_resend_marketing._audit',return_value=True),patch('crm_test_recipient.Shopify',return_value=TestRecipientShop()):
            send_test(f.store,ADMIN,editor,'internal@example.test',str(uuid.uuid4()),env=LIVE,session=wire)
        wire.post.assert_called_once();message=wire.post.call_args.kwargs['json']
        self.assertEqual(message['subject'],'[CAMPAIGN TEST] Your offer: FIXTURE5')
        self.assertNotIn('{{',message['html']);self.assertIn('A$5 off',message['html'])


if __name__=='__main__':unittest.main()
