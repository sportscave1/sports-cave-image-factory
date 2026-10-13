"""Publication gates and real-work health; synthetic evidence, no transport."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import Mock,patch
from crm_logic import now
from crm_resend import Config
from crm_automation_readiness import blockers,required_topics,worker_configuration
from tests.crm_publication_fixture import ready
from tests.test_crm_send_flow import LIVE


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.values={};self.store=Mock()
        self.store.set_state.side_effect=lambda key,value:self.values.update({key:value})
        self.store.state.side_effect=lambda key:self.values.get(key,{})
        ready(self.store)
        self.row={'trigger_type':'post_purchase','config':{'draft':{'trigger':'post_purchase','lifecycle_version':1,
            'emails':[{'enabled':True,'anchor':'payment','delay_seconds':10800,'document':{}}]}}}

    def test_topic_matrix_uses_only_enabled_stages(self):
        flow=self.row['config']['draft']
        self.assertEqual(required_topics('post_purchase',flow),('ORDERS_PAID',))
        for dependent in ({'anchor':'delivery'},{'anchor':'payment','requires_fulfilment':True}):
            with self.subTest(dependent=dependent):
                flow['emails'].append({'enabled':False,**dependent})
                self.assertNotIn('ORDERS_FULFILLED',required_topics('post_purchase',flow))
                flow['emails'][-1]['enabled']=True
                self.assertIn('ORDERS_FULFILLED',required_topics('post_purchase',flow))
                flow['emails'].pop()
        self.assertIn('ORDERS_FULFILLED',required_topics('fulfilled',{}))
        self.assertIn('CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE',required_topics('welcome',{}))

    def test_native_publication_needs_no_legacy_secret_or_base(self):
        with patch('crm_lifecycle_products.selected',return_value=False),patch('crm_collector_images.configurations',return_value=[]):
            self.assertEqual(blockers(self.store,self.row,{**LIVE,'CRM_UNSUBSCRIBE_SECRET':'','CRM_PUBLIC_BASE_URL':''}),[])

    def test_recent_delivery_work_can_outlive_full_cycle_but_never_stuck_work(self):
        health=deepcopy(self.values['worker_health']);health['checked_at']=(now()-timedelta(minutes=8)).isoformat()
        self.values['worker_health']=health
        self.values['campaign_schedule_health']={'checked_at':now().isoformat(),'enabled':True}
        with patch('crm_lifecycle_products.selected',return_value=False),patch('crm_collector_images.configurations',return_value=[]):
            self.assertTrue(any('delivery worker' in x for x in blockers(self.store,self.row,LIVE)))
            self.values['automation_delivery_health']={**health,'checked_at':now().isoformat()}
            self.assertEqual(blockers(self.store,self.row,LIVE),[])
            self.values['automation_delivery_health']=health
            self.assertTrue(any('delivery worker' in x for x in blockers(self.store,self.row,LIVE)))
            self.values['automation_delivery_health']={**health,'checked_at':now().isoformat(),'marketing_enabled':False}
            self.assertTrue(any('configuration is incomplete' in x for x in blockers(self.store,self.row,LIVE)))

    def test_provider_and_mailbox_configuration_fails_closed(self):
        for changed in ({'RESEND_REPLY_TO':'a@example.test,b@example.test'},
            {'RESEND_FROM_EMAIL':'bad'}, {'RESEND_FROM_NAME':'Sports\r\nBcc: bad@example.test'},
            {'RESEND_MARKETING_API_KEY':'  '}):
            with self.subTest(changed=changed):
                cfg=worker_configuration(Config({**LIVE,**changed}))
                self.assertFalse(cfg['provider_configured'] and cfg['sender_configured'])

    def test_only_completed_leased_delivery_persists_health(self):
        from crm_engine import Engine
        engine=Engine(self.store,Mock(),config=Config(LIVE));engine.owner='fixture-owner'
        engine.hold_lease=Mock();engine.advance_due=Mock();engine.send_one=Mock(return_value=False)
        with patch('crm_campaign_schedule.activate_due'),patch('crm_campaign_dispatch.dispatch') as dispatch:
            engine.delivery_checkpoint(force=True)
            self.assertEqual(self.values['automation_delivery_health']['status'],'ok')
            self.values.pop('automation_delivery_health');dispatch.side_effect=RuntimeError('blocked')
            with self.assertRaises(RuntimeError):engine.delivery_checkpoint(force=True)
            self.assertNotIn('automation_delivery_health',self.values)
        self.assertGreaterEqual(engine.hold_lease.call_count,3)


if __name__=='__main__':unittest.main()
