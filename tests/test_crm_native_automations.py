"""Disposable loopback PostgreSQL and mocked Shopify/Resend only."""
from copy import deepcopy
from datetime import timedelta
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from crm_automation_definition import new_flow,validate,email_step,status
from crm_automation_store import AutomationStore
from crm_automation_runtime import enter,advance,process_event,render
from crm_automation_home_data import counts,rows,delivery_summary,step_metrics
from crm_engine import Engine
from crm_logic import now,recipient_hash,date
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_simple_editor import document


class DefinitionTests(unittest.TestCase):
    def test_no_artificial_email_limit_and_unique_duplicate_ids(self):
        flow=new_flow();flow['emails']=[email_step(document(),i*60) for i in range(60)]
        self.assertEqual(len(validate(flow)['emails']),60)
        flow['emails'][1]['step_id']=flow['emails'][0]['step_id']
        with self.assertRaises(ValueError):validate(flow)
    def test_invalid_rules_delays_trigger_and_reentry_fail_closed(self):
        for field,value in (('trigger','fake'),('reentry_days',1),('rules',[{'field':'email','condition':'is','value':'private'}])):
            f=new_flow();f[field]=value
            with self.assertRaises(ValueError):validate(f)
        for delay in (-1,1.5,True,365*86400+1):
            f=new_flow();f['emails'][0]['delay_seconds']=delay
            with self.assertRaises(ValueError):validate(f)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class NativeAutomationTests(unittest.TestCase):
    def setUp(self):
        self.store=AutomationStore(connect);self.clock=now();self.created=[]
        self.store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','abandoned','fulfilled')}})
        self.addCleanup(lambda:self.store.q("UPDATE crm_automations SET status='PAUSED' WHERE id=ANY(%s::uuid[])",(self.created,)))
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External network forbidden'))
        self.guard.start();self.addCleanup(self.guard.stop)
        self.env=patch.dict(os.environ,LIVE);self.env.start();self.addCleanup(self.env.stop)
        self.settings=patch.object(self.store,'render_settings',return_value=deepcopy(CFG));self.settings.start();self.addCleanup(self.settings.stop)
        self.customer={'id':'gid://shopify/Customer/'+str(uuid.uuid4().int%10**12),'email':uuid.uuid4().hex+'@example.test',
          'firstName':'Fixture','emailMarketingConsent':{'marketingState':'SUBSCRIBED','consentUpdatedAt':self.clock.isoformat()},
          'defaultAddress':{'countryCodeV2':'AU'},'numberOfOrders':0,'lastOrder':None,
          'unsubscribeUrl':'https://example.test/unsubscribe/fixture'}
        self.shop=Mock();self.shop.customer.side_effect=lambda *a,**k:deepcopy(self.customer)
        self.provider=Mock();self.provider.suppressed.return_value=False;self.provider.send.side_effect=lambda *a,**k:str(uuid.uuid4())
        from crm_resend import Config
        self.engine=Engine(self.store,self.shop,self.provider,Config(LIVE),clock=lambda:self.clock)
        self.native_url=patch('crm_native_unsubscribe.native_unsubscribe_url',return_value='https://example.test/unsubscribe/fixture')
        self.native_url.start();self.addCleanup(self.native_url.stop)
    def published(self,kind='welcome',delays=(0,)):
        a=self.store.create(ADMIN,kind,'Automation '+uuid.uuid4().hex)
        self.created.append(str(a['id']))
        flow=deepcopy(a['config']['draft']);flow['emails']=[email_step(document(),d) for d in delays]
        for s in flow['emails']:s['document']['copy_reviewed']=True
        a=self.store.save_flow(ADMIN,a['id'],a['name'],flow,1)
        return self.store.publish(ADMIN,a['id'],a['config']['revision'],env=LIVE)
    def enroll(self,a,key=None):
        self.clock=now()+timedelta(seconds=1)
        return enter(self.engine,a,self.customer['id'],self.customer['id'],key or str(uuid.uuid4()),self.clock)
    def due(self,j):
        self.store.q('UPDATE crm_automation_enrollments SET next_due_at=%s WHERE id=%s',(now()-timedelta(seconds=1),j['id']))
        self.clock=now()+timedelta(seconds=1)
        return self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
    def test_publish_freezes_versions_and_does_not_enqueue_or_enroll(self):
        before=self.store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n']
        a=self.published(delays=(0,86400));self.assertEqual(a['status'],'ACTIVE')
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n'],before)
        j=self.enroll(a);old=deepcopy(j['steps']);flow=deepcopy(a['config']['draft']);flow['emails'][1]['document']['content']['subject']='New version'
        saved=self.store.save_flow(ADMIN,a['id'],a['name'],flow,a['config']['revision'])
        newer=self.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE)
        self.assertEqual(newer['config']['published_version'],2)
        self.assertEqual(self.store.q('SELECT steps FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['steps'],old)
        content=self.store.template(old[1]['template_id'],old[1]['template_version'])
        self.assertNotEqual(content['document']['content']['subject'],'New version')
    def test_future_only_idempotency_once_and_rules(self):
        a=self.published();past=date(a['activated_at'])-timedelta(seconds=1)
        self.assertIsNone(enter(self.engine,a,self.customer['id'],self.customer['id'],'historic',past))
        j=self.enroll(a,'source-event');self.assertIsNotNone(j)
        self.assertIsNone(self.enroll(a,'source-event'));self.assertIsNone(self.enroll(a,'another-event'))
        other=self.published();f=deepcopy(other['config']['draft']);f['rules']=[{'field':'market','condition':'is','value':'NZ'}]
        other=self.store.save_flow(ADMIN,other['id'],other['name'],f,other['config']['revision']);other=self.store.publish(ADMIN,other['id'],other['config']['revision'],env=LIVE)
        self.assertIsNone(self.enroll(other))
    def test_pause_prevents_entry_claim_and_submission_resume_preserves_wait(self):
        a=self.published(delays=(0,86400));j=self.enroll(a);advance(self.engine,self.due(j))
        receipt=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
        self.store.lifecycle(ADMIN,a['id'],'pause')
        self.assertIsNone(self.enroll(a));self.assertIsNone(self.store.claim_send())
        self.store.lifecycle(ADMIN,a['id'],'resume')
        self.assertIsNotNone(self.store.claim_send())
        self.assertEqual(self.store.flow(a['id'])['status'],'ACTIVE')
    def test_step_progression_delay_restart_and_duplicate_execution(self):
        a=self.published(delays=(0,3600));j=self.enroll(a);j=self.due(j)
        advance(self.engine,j);advance(self.engine,j)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['n'],1)
        self.assertTrue(self.engine.send_one());self.provider.send.assert_called_once()
        from crm_resend import Config
        restarted=Engine(AutomationStore(connect),self.shop,self.provider,Config(LIVE),clock=lambda:self.clock)
        advance(restarted,self.due(j));fresh=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertEqual(fresh['current_step'],1);self.assertGreater(date(fresh['next_due_at']),self.clock)
        advance(restarted,fresh)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['n'],1)
        advance(restarted,self.due(j))
        with patch('crm_workspace_store.WorkspaceRecords.frequency_blocked',return_value=False):self.assertTrue(restarted.send_one())
        advance(restarted,self.due(j))
        self.assertEqual(self.provider.send.call_count,2)
        self.assertEqual(self.store.q('SELECT status FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['status'],'COMPLETED')
    def test_unsubscribe_and_suppression_before_due_step_blocks_transport(self):
        for suppress in (False,True):
            a=self.published();j=self.enroll(a);advance(self.engine,self.due(j))
            if suppress:self.store.suppress(recipient_hash(self.customer['email']),self.customer['id'],'manual_unsubscribe','fixture')
            else:self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
            self.engine.send_one();self.provider.send.assert_not_called()
            self.customer['emailMarketingConsent']['marketingState']='SUBSCRIBED'
    def test_abandoned_checkout_completed_stops_remaining_steps(self):
        a=self.published('abandoned');j=self.enroll(a);self.shop.checkout.return_value={'completedAt':now().isoformat()}
        advance(self.engine,self.due(j));self.provider.send.assert_not_called()
        self.assertEqual(self.store.q('SELECT status FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['status'],'RECOVERED')
    def test_archive_delete_tombstone_preserves_receipts(self):
        a=self.published();j=self.enroll(a)
        with self.assertRaises(ValueError):self.store.lifecycle(ADMIN,a['id'],'delete')
        self.store.lifecycle(ADMIN,a['id'],'pause');self.store.lifecycle(ADMIN,a['id'],'archive');self.store.lifecycle(ADMIN,a['id'],'delete')
        self.assertTrue(self.store.q('SELECT 1 FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True))
        self.assertNotIn(str(a['id']),[str(r['id']) for r in rows(self.store)])
    def test_optimistic_save_and_invalid_publication(self):
        a=self.store.create(ADMIN);f=deepcopy(a['config']['draft']);f['emails'][0]['document']=document()
        a=self.store.save_flow(ADMIN,a['id'],a['name'],f,1)
        f['emails'][0]['document']['content']['subject']='Changed'
        with self.assertRaises(ValueError):self.store.save_flow(ADMIN,a['id'],a['name'],f,1)
        with self.assertRaises(ValueError):self.store.publish(ADMIN,a['id'],a['config']['revision'],env={**LIVE,'CRM_MARKETING_ENABLED':'false'})
    def test_shared_templates_have_same_identity_and_native_snapshots_hidden(self):
        from crm_campaign_store import CampaignStore
        campaign=CampaignStore(connect);t=campaign.save_design(ADMIN,'Shared '+uuid.uuid4().hex,document())
        self.assertIn(str(t['id']),[str(r['id']) for r in self.store.html_library()])
        t2=self.store.save_design(ADMIN,'From automation '+uuid.uuid4().hex,document())
        self.assertIn(str(t2['id']),[str(r['id']) for r in campaign.html_library()])
        a=self.published()
        self.assertNotIn(str(a['steps'][0]['template_id']),[str(r['id']) for r in self.store.templates()])
    def test_verified_events_and_30day_denominator(self):
        a=self.published();j=self.enroll(a);advance(self.engine,self.due(j));self.engine.send_one()
        s=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
        for event in ('email.delivered','email.clicked','email.opened','email.bounced'):
            self.store.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,%s,now(),%s)',(str(uuid.uuid4()),s['provider_email_id'],event,s['id']))
        data=step_metrics(self.store,a['id'])[0]
        self.assertEqual([data[k] for k in ('sent','delivered','opened','clicked','bounced')],[1]*5)
        summary=delivery_summary(self.store,(now()-timedelta(seconds=1),now()+timedelta(seconds=1)))
        self.assertGreater(summary['sent_emails'],0);self.assertGreater(float(summary['bounce_rate']),0)

    def test_signed_welcome_event_requires_new_consent_and_is_idempotent(self):
        a=self.published();self.clock=now()+timedelta(seconds=1)
        self.customer['emailMarketingConsent']['consentUpdatedAt']=self.clock.isoformat()
        event={'topic':'customers_email_marketing_consent/update','related_customer_id':self.customer['id'],'occurred_at':self.clock.isoformat(),'normalized':{'consent_state':'SUBSCRIBED','consent_updated_at':self.clock.isoformat()}}
        process_event(self.engine,event,[a]);process_event(self.engine,event,[a])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
        other=self.published();event['occurred_at']=(self.clock+timedelta(minutes=10)).isoformat()
        process_event(self.engine,event,[other])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(other['id'],),True)['n'],0)

    def test_post_purchase_paid_authority_and_unrelated_event(self):
        a=self.published('post_purchase');self.clock=now()+timedelta(seconds=1)
        order={'id':'gid://shopify/Order/1234','createdAt':self.clock.isoformat(),'customer':{'id':self.customer['id']},'fullyPaid':True,'cancelledAt':None}
        self.shop.order.return_value=order
        event={'topic':'orders/paid','object_id':order['id'],'occurred_at':self.clock.isoformat()}
        process_event(self.engine,{**event,'topic':'segments/update'},[a])
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        process_event(self.engine,event,[a]);process_event(self.engine,event,[a])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)

    def test_abandoned_reconciliation_is_future_bounded_and_pagination_closed(self):
        from crm_automation_runtime import reconcile
        a=self.published('abandoned');self.clock=now()+timedelta(hours=2)
        from crm_webhooks import receive_shopify
        with patch.dict(os.environ,{'SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'}):
            receive_shopify(self.store,'checkouts/create',uuid.uuid4().hex,{'token':'native-checkout-token','customer':{'id':self.customer['id']},'created_at':(self.clock-timedelta(hours=1,minutes=1)).isoformat()},self.clock-timedelta(hours=1,minutes=1))
        self.shop.checkouts.return_value={'nodes':[{'id':'gid://shopify/AbandonedCheckout/1','createdAt':(self.clock-timedelta(hours=1,minutes=1)).isoformat(),'customer':{'id':self.customer['id']},'completedAt':None}], 'pageInfo':{'hasNextPage':False,'endCursor':None}}
        self.shop.checkouts.return_value['nodes'][0]['abandonedCheckoutUrl']='https://fixture.myshopify.com/checkouts/native-checkout-token/recover'
        with patch.dict(os.environ,{'SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'}):reconcile(self.engine,a)
        self.assertIn('created_at:>=',self.shop.checkouts.call_args.kwargs['query'])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
        newer=self.published('abandoned');self.shop.checkouts.return_value={'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':None}}
        with self.assertRaises(ValueError):reconcile(self.engine,newer)

    def test_global_email_templates_and_test_transport_have_no_campaign_draft(self):
        from crm_campaign_send import send_test
        from tests.crm_fixtures import TestRecipientShop
        a=self.store.create(ADMIN);f=deepcopy(a['config']['draft']);f['emails'][0]['document']=document()
        a=self.store.save_flow(ADMIN,a['id'],a['name'],f,1);self.store.step_id=f['emails'][0]['step_id']
        editor=self.store.draft(a['id']);operation=str(uuid.uuid4());wire=Mock()
        wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        before=self.store.q('SELECT count(*) n FROM crm_campaign_drafts',one=True)['n']
        user={**ADMIN,'role':'worker','page_permissions':['crm_automations_manage']}
        with patch('crm_resend_marketing._audit',return_value=True),patch('crm_test_recipient.Shopify',return_value=TestRecipientShop()):
            first=send_test(self.store,user,editor,'internal@example.test',operation,env=LIVE,session=wire)
            second=send_test(self.store,user,editor,'internal@example.test',operation,env=LIVE,session=wire)
        self.assertEqual(first['message_id'],second['message_id']);wire.post.assert_called_once()
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_campaign_drafts',one=True)['n'],before)
        receipt=self.store.q('SELECT * FROM crm_internal_tests WHERE id=%s',(operation,),True)
        self.assertIsNone(receipt['campaign_id']);self.assertEqual(str(receipt['automation_id']),str(a['id']))
        self.assertEqual(str(receipt['automation_step_id']),self.store.step_id)

    def test_size_guard_and_tracking_share_production_renderer(self):
        from crm_campaign_content import render_campaign
        from crm_tracking import send_identity
        from crm_automation_definition import production_document
        a=self.published();content=self.store.template(a['steps'][0]['template_id'],1)
        identity=str(uuid.uuid4());s={'id':identity}
        doc=production_document(content['document']);doc['campaign_key']='auto_'+identity.replace('-','')
        actual=render(content,s,'https://example.test/unsubscribe/fixture')
        expected=render_campaign(doc,CFG,unsubscribe_url='https://example.test/unsubscribe/fixture',production=True,campaign_id=identity,send_id=send_identity(identity))
        self.assertEqual(actual['html'],expected['html']);self.assertIn(send_identity(identity),actual['html'])
        oversized=deepcopy(content);oversized['document']['custom_html']='<p>'+'x'*94700+'</p>'
        with self.assertRaises(ValueError):render(oversized,s,'https://example.test/unsubscribe/fixture')

    def test_canonical_order_attribution_preserves_automation_and_step_identity(self):
        from crm_campaign_attribution import record
        from crm_tracking import campaign_link,send_identity
        from tests.test_crm_production_v2 import order_fixture
        from crm_automation_home_data import orders_summary
        a=self.published();j=self.enroll(a);advance(self.engine,self.due(j));self.engine.send_one()
        s=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
        order=order_fixture('unused',self.customer['id'],now()+timedelta(minutes=2))
        url=campaign_link('https://www.sportscaveshop.com/products/fixture','auto_'+str(s['id']).replace('-',''),'product',test=False,campaign_id=str(s['id']),send_id=send_identity(s['id']))
        order['customerJourneySummary']['lastVisit']={'occurredAt':(now()+timedelta(minutes=1)).isoformat(),'landingPage':url}
        match=record(self.store,order);self.assertEqual(match['method'],'SHOPIFY_UTM_EXACT')
        row=self.store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
        self.assertIsNone(row['campaign_id']);self.assertEqual(row['evidence']['automation_id'],str(a['id']))
        self.assertEqual(row['evidence']['journey_id'],str(j['id']));self.assertEqual(row['evidence']['step_id'],a['steps'][0]['step_id'])
        order['customerJourneySummary']={'ready':False};record(self.store,order)
        saved=self.store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
        self.assertEqual(saved['evidence'],row['evidence'])
        self.assertGreater(orders_summary(self.store,(now()-timedelta(days=30),now()+timedelta(hours=1)))['orders'],0)

    def test_selected_step_saves_do_not_overwrite_other_emails_or_campaign_drafts(self):
        a=self.published(delays=(0,86400));flow=a['config']['draft']
        before=self.store.q('SELECT count(*) n FROM crm_campaign_drafts',one=True)['n']
        first=deepcopy(flow['emails'][0]['document'])
        self.store.step_id=flow['emails'][1]['step_id'];editor=self.store.draft(a['id'])
        editor['document']['content']['subject']='Only email two changes'
        self.store.save(ADMIN,a['name'],editor['document'],a['id'],editor['version'])
        current=self.store.flow(a['id'])['config']['draft']['emails']
        self.assertEqual(current[0]['document'],first)
        self.assertEqual(current[1]['document']['content']['subject'],'Only email two changes')
        self.store.step_id=flow['emails'][0]['step_id']
        self.assertEqual(self.store.draft(a['id'])['document'],first)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_campaign_drafts',one=True)['n'],before)

    def test_pause_between_due_query_and_advance_preserves_journey(self):
        a=self.published();j=self.due(self.enroll(a))
        self.store.lifecycle(ADMIN,a['id'],'pause')
        advance(self.engine,j)
        current=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertEqual(current['status'],'ACTIVE')
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True))
        self.provider.send.assert_not_called()

    def test_publish_paused_preserves_remaining_wait_and_frozen_journey(self):
        a=self.published(delays=(86400,));j=self.enroll(a)
        before=date(j['next_due_at']);old=deepcopy(j['steps'])
        self.store.lifecycle(ADMIN,a['id'],'pause')
        row=self.store.flow(a['id']);row['config']['paused_at']=(now()-timedelta(hours=2)).isoformat()
        self.store.q('UPDATE crm_automations SET config=%s::jsonb WHERE id=%s',(__import__('json').dumps(row['config']),a['id']))
        self.store.publish(ADMIN,a['id'],row['config']['revision'],env=LIVE)
        current=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertGreaterEqual(date(current['next_due_at']),before+timedelta(hours=2))
        self.assertEqual(current['steps'],old)

    def test_reentry_cooldown_remains_serialized_after_completion(self):
        a=self.published();flow=deepcopy(a['config']['draft']);flow['reentry_days']=7
        saved=self.store.save_flow(ADMIN,a['id'],a['name'],flow,a['config']['revision'])
        a=self.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE);j=self.enroll(a)
        self.store.q("UPDATE crm_automation_enrollments SET status='COMPLETED' WHERE id=%s",(j['id'],))
        self.assertIsNone(enter(self.engine,a,self.customer['id'],self.customer['id'],'too-early',self.clock+timedelta(days=6)))
        self.assertIsNotNone(enter(self.engine,a,self.customer['id'],self.customer['id'],'new-event',self.clock+timedelta(days=8)))
        self.assertIsNone(enter(self.engine,a,self.customer['id'],self.customer['id'],'duplicate-active',self.clock+timedelta(days=9)))

    def test_safe_entry_submission_logs_exclude_personal_data_and_content(self):
        a=self.published()
        with self.assertLogs('crm_automation_runtime',level='INFO') as captured:
            j=self.enroll(a);advance(self.engine,self.due(j));self.engine.send_one()
            advance(self.engine,self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True))
        logs=' '.join(captured.output)
        for private in (self.customer['email'],self.customer['firstName'],self.customer['unsubscribeUrl']):self.assertNotIn(private,logs)
        for label in ('automation_id=','journey_id=','step_id=','provider_message_id=','sent_at='):self.assertIn(label,logs)

    def test_pause_after_claim_holds_pending_without_transport(self):
        a=self.published();j=self.enroll(a);advance(self.engine,self.due(j))
        original=self.store.claim_send
        def claim(**kwargs):
            row=original(**kwargs);self.store.lifecycle(ADMIN,a['id'],'pause');return row
        with patch.object(self.store,'claim_send',side_effect=claim):self.engine.send_one()
        self.provider.send.assert_not_called()
        self.assertEqual(self.store.q('SELECT status FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['status'],'PENDING')

    def test_empty_submission_cohort_shows_unknown_bounce_rate(self):
        summary=delivery_summary(self.store,(now()-timedelta(days=400),now()-timedelta(days=370)))
        self.assertEqual(summary['sent_emails'],0);self.assertIsNone(summary['bounce_rate'])


if __name__=='__main__':unittest.main()
