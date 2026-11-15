"""Production lifecycle/analytics fixtures: loopback SQL and mocked I/O only."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from crm_logic import now,date,recipient_hash
from crm_campaign_attribution import choose,products,record,mirror,reconcile
from crm_campaign_analytics import sent_page,details,rate,money
from crm_tracking import campaign_link,event_link
from crm_campaign_send import review,queue_campaign
from crm_campaign_store import CampaignStore
from crm_webhooks import receive_resend
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_campaign_v2 import authority,profile

def bag(value,currency='AUD'):return {'shopMoney':{'amount':str(value),'currencyCode':currency}}
def visit(key,at,test=False):
    return {'occurredAt':at.isoformat(),'landingPage':campaign_link('https://www.sportscaveshop.com/products/art',key,'product',test=test),
            'utmParameters':{'source':'sports_cave_os','medium':'email','campaign':key}}
def order_fixture(key,customer,at=None):
    at=at or now()+timedelta(hours=2)
    return {'id':'gid://shopify/Order/'+str(uuid.uuid4().int)[:14],'name':'#Fixture','createdAt':at.isoformat(),
      'customer':{'id':customer},'fullyPaid':True,'test':False,'cancelledAt':None,'netPaymentSet':bag(180),
      'customerJourneySummary':{'ready':True,'lastVisit':visit(key,at-timedelta(hours=1)),'moments':{'nodes':[]}},
      'lineItems':{'nodes':[{'id':'line1','title':'Collector piece','product':{'id':'product1'},'quantity':2,'currentQuantity':2,
                           'originalTotalSet':bag(200),'discountAllocations':[{'allocatedAmountSet':bag(20)}]}]},'refunds':[]}

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.at=now();self.campaigns=[{'id':'a','name':'A','campaign_key':'sc_a','status':'SENT','sending_started_at':self.at-timedelta(days=2)},
                                   {'id':'b','name':'B','campaign_key':'sc_b','status':'SENT','sending_started_at':self.at-timedelta(days=2)}]
        self.order=order_fixture('sc_a','customer',self.at)
    def click(self,key,minutes):
        return {'campaign_key':key,'shopify_customer_id':'customer','occurred_at':self.at-timedelta(minutes=minutes),
                'clicked_url':campaign_link('https://www.sportscaveshop.com/products/art',key,'product',test=False)}
    def test_exact_utm_beats_more_recent_other_campaign_click(self):
        result=choose(self.order,self.campaigns,[self.click('sc_b',10),self.click('sc_a',30)])
        self.assertEqual((result['campaign']['id'],result['method']),('a','SHOPIFY_UTM_EXACT'))
        self.assertEqual(result['click_at'],self.at-timedelta(minutes=30))
    def test_latest_matching_click_needs_supporting_utm(self):
        v=self.order['customerJourneySummary']['lastVisit'];v.update(utmParameters={'source':'sports_cave_os','medium':'email'},landingPage='https://www.sportscaveshop.com/?utm_source=sports_cave_os&utm_medium=email',occurredAt=(self.at-timedelta(minutes=1)).isoformat())
        result=choose(self.order,self.campaigns,[self.click('sc_a',30),self.click('sc_b',10)])
        self.assertEqual((result['campaign']['id'],result['method']),('b','RESEND_CLICK_MATCH'))
        v['landingPage']='https://www.sportscaveshop.com/';v['utmParameters']={}
        self.assertEqual(choose(self.order,self.campaigns,[self.click('sc_a',30)])['method'],'RESEND_CLICK_MATCH')
    def test_unrelated_test_unready_pre_send_and_outside_window_not_attributed(self):
        for change in ('test','unready','old','unknown','before_send'):
            value=deepcopy(self.order);campaigns=deepcopy(self.campaigns)
            if change=='test':value['customerJourneySummary']['lastVisit']=visit('sc_a',self.at-timedelta(hours=1),True)
            if change=='unready':value['customerJourneySummary']['ready']=False
            if change=='old':value['customerJourneySummary']['lastVisit']=visit('sc_a',self.at-timedelta(days=8))
            if change=='unknown':value['customerJourneySummary']['lastVisit']=visit('sc_unknown',self.at-timedelta(hours=1))
            if change=='before_send':campaigns[0]['sending_started_at']=self.at
            with self.subTest(change=change):self.assertIsNone(choose(value,campaigns,[]))
    def test_other_customer_click_is_not_evidence(self):
        self.order['customer']['id']='another';self.order['customerJourneySummary']['lastVisit']['utmParameters']['campaign']=''
        self.order['customerJourneySummary']['lastVisit']['landingPage']='https://www.sportscaveshop.com/?utm_source=sports_cave_os&utm_medium=email'
        self.assertIsNone(choose(self.order,self.campaigns,[self.click('sc_a',90)]))
    def test_all_journey_visits_and_configurable_window(self):
        self.order['customerJourneySummary']['moments']['nodes']=[visit('sc_b',self.at-timedelta(hours=3))]
        self.order['customerJourneySummary']['lastVisit']={}
        self.assertEqual(choose(self.order,self.campaigns,[])['campaign']['id'],'b')
        self.assertIsNone(choose(self.order,self.campaigns,[],days=.01))
    def test_products_use_discounts_and_refunded_amounts_not_order_gross(self):
        self.order['lineItems']['nodes'][0]['currentQuantity']=1
        self.order['refunds']=[{'refundLineItems':{'nodes':[{'lineItem':{'id':'line1'},'quantity':1,'subtotalSet':bag(90)}]}}]
        row=products(self.order,'AUD')[0];self.assertEqual((row['quantity'],row['revenue']),(1,'90'))
        self.order['lineItems']['nodes'][0]['currentQuantity']=0
        self.assertIsNone(products(self.order,'AUD')[0]['revenue'])
    def test_safe_tracking_merge_and_system_external_links(self):
        original='https://www.sportscaveshop.com/products/art?variant=42&UTM_SOURCE=old&utm_campaign=old#details'
        tracked=campaign_link(original,'sc_one','product_1',test=False)
        self.assertIn('utm_source=sports_cave_os',tracked);self.assertIn('utm_campaign=sc_one',tracked)
        self.assertEqual(tracked.count('utm_source='),1);self.assertIn('variant=42',tracked);self.assertTrue(tracked.endswith('#details'))
        self.assertEqual(campaign_link(tracked,'sc_one','product_1',test=False),tracked)
        for url in ('mailto:a@b.com','tel:123','#details','https://external.test/path','https://www.sportscaveshop.com/account/unsubscribe?token=x','https://www.sportscaveshop.com/policies/privacy-policy'):
            self.assertEqual(campaign_link(url,'sc_one','x',test=False),url)
        self.assertNotIn('email=',event_link(tracked+'&email=secret'))
        self.assertIsNone(event_link('https://www.sportscaveshop.com/account/unsubscribe?token=secret'))
    def test_zero_denominators_and_currency_separation(self):
        self.assertIsNone(rate(0,0));self.assertEqual(rate(1,2),50)
        self.assertEqual(money({'AUD':'2840','GBP':'99'}),'A$2,840.00 · £99.00')
    def test_reviewed_schedule_survives_count_ttl_and_healthy_queue_delay(self):
        from crm_campaign_send import production_checks
        from crm_campaign_schedule import overdue_reason
        doc=document();doc['counts']={'members':3,'eligible':3,'excluded':{},'complete':True,'checked_at':(now()-timedelta(days=2)).isoformat()}
        self.assertFalse(production_checks(doc,CFG,LIVE)['Fresh complete eligible audience'])
        self.assertTrue(production_checks(doc,CFG,LIVE,reviewed_audience=True)['Fresh complete eligible audience'])
        snapshot={'audience_snapshot_id':'reviewed','schedule':{'hash':{'due_at':(now()-timedelta(hours=1)).isoformat()}}}
        self.assertEqual(overdue_reason(snapshot,{'recipient_hash':'hash'},now()),'')

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class ProductionSqlTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect);start=int(str(uuid.uuid4().int)[:10])
        self.shop=authority([profile(start+i) for i in range(3)])
        self.rows=self.shop.campaign_subscribers.return_value['nodes']
        for guard in (patch.object(self.store,'render_settings',return_value=deepcopy(CFG)),
                      patch.object(self.store,'active_suppression_hashes',return_value=(set(),set())),
                      patch.object(self.store,'recent_marketing_hashes',return_value=set()),
                      patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O'))):
            guard.start();self.addCleanup(guard.stop)
        doc=document();doc.update(market_audience=True)
        self.editor=self.store.save(ADMIN,'V2 fixture '+uuid.uuid4().hex,doc)
    def reviewed(self):
        result=review(self.shop,self.store,self.editor,LIVE)
        self.assertFalse(result['blockers']);self.assertIsNotNone(result['snapshot_id']);return result
    def queue(self,reviewed=None):
        reviewed=reviewed or self.reviewed()
        return queue_campaign(self.shop,self.store,ADMIN,self.editor,str(uuid.uuid4()),env=LIVE,snapshot_id=reviewed['snapshot_id'])
    def campaign(self):return self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(self.editor['id'],),True)
    def sends(self):return self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY shopify_customer_id',(self.editor['id'],))
    def accepted(self):
        self.queue()
        for row in self.sends():
            self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',provider_email_id=%s,first_submitted_at=now() WHERE id=%s",(str(uuid.uuid4()),row['id']))
        self.store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now() WHERE id=%s",(self.editor['id'],))
        return self.sends()
    def event(self,row,kind,stamp=None,event_id=None,link=None):
        return receive_resend(self.store,event_id or 'evt_'+uuid.uuid4().hex,{'type':kind,'created_at':(stamp or now()).isoformat(),
          'data':{'email_id':row['provider_email_id'],'click':{'link':link},'bounce':{'type':'Permanent'}}})
    def test_snapshot_is_durable_no_new_recipients_only_newly_ineligible_removed(self):
        reviewed=self.reviewed();snapshot=self.store.q('SELECT * FROM crm_campaign_snapshots WHERE id=%s',(reviewed['snapshot_id'],),True)
        self.assertEqual(snapshot['counts']['eligible'],3)
        self.rows[0]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED';self.rows[0]['defaultEmailAddress']['marketingState']='UNSUBSCRIBED'
        self.store.suppress(recipient_hash(self.rows[1]['email']),self.rows[1]['id'],'manual_unsubscribe','fixture')
        self.shop.campaign_subscribers.return_value['nodes'].append(profile(999999999))
        with patch('crm_campaign_send.final_audience',side_effect=AssertionError('No second audience')):
            result=self.queue(reviewed)
        self.assertEqual((result['recipients'],result['skipped_after_review']),(1,2))
        self.assertEqual(len(self.sends()),3);self.assertEqual(sum(r['status']=='PENDING' for r in self.sends()),1)
        self.assertEqual(self.store.q('SELECT counts FROM crm_campaign_snapshots WHERE id=%s',(reviewed['snapshot_id'],),True)['counts']['eligible'],3)
    def test_double_confirm_restart_is_unique_and_snapshot_content_locked(self):
        r=self.reviewed();self.queue(r);again=self.queue(r);self.assertTrue(again['already_started']);self.assertEqual(len(self.sends()),3)
        for sql,args in (
          ('UPDATE crm_campaign_snapshots SET recipients=\'[]\' WHERE id=%s',(r['snapshot_id'],)),
          ("UPDATE crm_campaigns SET campaign_key='changed' WHERE id=%s",(self.editor['id'],)),
          ("UPDATE crm_campaign_drafts SET name='changed' WHERE id=%s",(self.editor['id'],)),
          ("UPDATE crm_template_versions SET content='{}' WHERE template_id=%s",(self.campaign()['template_id'],))):
            with self.subTest(sql=sql),self.assertRaises(Exception):self.store.q(sql,args)
        with self.assertRaises(ValueError):self.store.save(ADMIN,'Edit',self.editor['document'],self.editor['id'],self.editor['version'])
        with self.assertRaises(ValueError):self.store.archive(ADMIN,self.editor['id'],self.editor['version'])
        copy=self.store.duplicate(ADMIN,self.editor['id']);self.assertNotEqual(copy['document']['campaign_key'],self.editor['document']['campaign_key'])
        self.assertNotEqual(copy['id'],self.editor['id'])
    def test_no_snapshot_or_settings_drift_cannot_queue(self):
        with self.assertRaisesRegex(ValueError,'Review the final audience'):
            queue_campaign(self.shop,self.store,ADMIN,self.editor,str(uuid.uuid4()),env=LIVE)
        r=self.reviewed()
        with patch.object(self.store,'render_settings',return_value={**CFG,'reply_to':'changed@example.test'}),self.assertRaisesRegex(ValueError,'settings changed'):self.queue(r)
        self.assertIsNone(self.campaign())
    def test_unique_recipient_metrics_duplicate_and_out_of_order_callbacks(self):
        rows=self.accepted();event_id='evt_'+uuid.uuid4().hex
        self.assertTrue(self.event(rows[0],'email.opened',event_id=event_id))
        self.assertFalse(self.event(rows[0],'email.opened',event_id=event_id))
        self.event(rows[0],'email.opened');self.event(rows[0],'email.clicked');self.event(rows[0],'email.clicked')
        self.event(rows[1],'email.opened')  # Open without delivery is not yet counted.
        self.event(rows[0],'email.delivered');self.event(rows[2],'email.delivered')
        self.event(rows[1],'email.bounced');self.event(rows[1],'email.complained');self.event(rows[1],'email.suppressed')
        self.event(rows[1],'email.delivery_delayed');self.event(rows[1],'email.scheduled');self.event(rows[1],'email.failed')
        result=next(r for r in sent_page(self.store,limit=200) if r['id']==self.editor['id'])
        self.assertEqual([result[k] for k in ('recipients','delivered','opens','clicks','bounces','complaints','suppressed')],[3,2,1,1,1,1,1])
        self.assertEqual((result['open_rate'],result['click_rate']),(50,50))
        self.assertTrue(self.store.suppressed(rows[1]['shopify_customer_id'],rows[1]['recipient_hash']))
    def test_early_event_before_provider_receipt_reconciles(self):
        self.queue();row=self.sends()[0];provider=str(uuid.uuid4());row['provider_email_id']=provider
        self.event(row,'email.delivered')
        self.assertIsNone(self.store.q('SELECT send_id FROM crm_delivery_events WHERE provider_id=%s',(provider,),True)['send_id'])
        self.store.q("UPDATE crm_marketing_sends SET status='CLAIMED',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes' WHERE id=%s",(row['id'],))
        row=self.store.receipt(row['id']);self.store.finish_send(row,'ACCEPTED',provider_id=provider)
        self.assertEqual(self.store.q('SELECT send_id FROM crm_delivery_events WHERE provider_id=%s',(provider,),True)['send_id'],row['id'])
    def test_attributed_order_rollups_refunds_and_one_order_one_campaign(self):
        rows=self.accepted();campaign=self.campaign();key=str(campaign['campaign_send_id']);created=now()+timedelta(hours=2)
        link=campaign_link('https://www.sportscaveshop.com/products/art',key,'product',test=False,campaign_id=campaign['id'],send_id=key)
        self.event(rows[0],'email.delivered');self.event(rows[0],'email.clicked',created-timedelta(hours=1),link=link)
        order=order_fixture(key,rows[0]['shopify_customer_id'],created)
        match=record(self.store,order);self.assertEqual(match['method'],'SHOPIFY_UTM_EXACT');record(self.store,order)
        result=next(r for r in sent_page(self.store,limit=200) if r['id']==campaign['id'])
        self.assertEqual(result['orders'],1);self.assertEqual(Decimal(result['revenue_per_recipient']['AUD']),60)
        self.assertEqual(Decimal(result['revenue_per_click']['AUD']),180)
        detail=details(self.store,campaign['id']);self.assertEqual(detail['products'][0]['units'],2)
        self.assertAlmostEqual(float(detail['timing']['seconds']),3600,places=2)
        order['netPaymentSet']=bag(90);order['lineItems']['nodes'][0]['currentQuantity']=1
        order['refunds']=[{'refundLineItems':{'nodes':[{'quantity':1,'lineItem':{'id':'line1'},'subtotalSet':bag(90)}]}}]
        record(self.store,order);self.assertEqual(float(details(self.store,campaign['id'])['products'][0]['revenue']),90)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)['n'],1)
        order['cancelledAt']=created.isoformat();record(self.store,order)
        self.assertFalse(self.store.q('SELECT eligible FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)['eligible'])
    def test_mirror_scoped_optional_idempotent_and_failure_does_not_erase_attribution(self):
        rows=self.accepted();order=order_fixture(str(self.campaign()['campaign_send_id']),rows[0]['shopify_customer_id']);match=record(self.store,order)
        with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'}),patch('shopify_sync.fetch_metafields',return_value={'metafields':[]}),patch('shopify_sync.metafields_set',side_effect=RuntimeError('missing scope')) as write:
            mirror(self.store,order,match);self.assertEqual(write.call_args.args[0][0]['namespace'],'sports_cave_os')
            self.assertEqual(write.call_args.args[0][0]['key'],'email_attribution')
        saved=self.store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
        self.assertTrue(saved['eligible']);self.assertEqual(saved['mirror_status'],'FAILED')
        with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'false'}),patch('shopify_sync.metafields_set') as write:
            mirror(self.store,order,match);write.assert_not_called()
    def test_background_scan_is_bounded_and_cached_between_cycles(self):
        rows=self.accepted();order=order_fixture(str(self.campaign()['campaign_send_id']),rows[0]['shopify_customer_id'])
        self.store.set_state('email_attribution_scan',{})
        page={'nodes':[{'id':order['id']}],'pageInfo':{'hasNextPage':False}}
        with patch('crm_attribution_shopify.updated',return_value=page) as listing,patch('crm_attribution_shopify.order',return_value=order) as full:
            reconcile(self.store,self.shop);reconcile(self.store,self.shop)
            listing.assert_called_once();full.assert_called_once()
        state=self.store.state('email_attribution_scan');self.assertIn('watermark',state);self.assertIn('next_at',state)
    def test_sent_lock_ui_and_working_list(self):
        self.accepted();self.assertNotIn(self.editor['id'],[r['id'] for r in self.store.list_drafts(working=True)])
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.session_state['campaign_editor']=deepcopy(self.editor)
        at.run(timeout=20);self.assertFalse(at.exception)
        self.assertFalse(any(b.label in ('Send now','Save draft') for b in at.button))
        self.assertFalse(any(t.label=='Subject' for t in at.text_input))
        self.assertTrue(any(b.label=='← Campaigns' for b in at.button))
        fresh=AppTest.from_string(SCRIPT);fresh.session_state['route']='CRM Campaigns'
        fresh.query_params['campaign']=str(self.editor['id']);fresh.run(timeout=20)
        self.assertFalse(fresh.exception);self.assertTrue(any('**Sent**'==m.value for m in fresh.markdown))
        self.assertFalse(any(t.label=='Subject' for t in fresh.text_input))
    def test_scheduled_worker_lifecycle_without_page_and_no_replay(self):
        from crm_engine import Engine
        from crm_resend import Config
        self.editor['document']['send_timing']={'mode':'schedule','date':'2099-10-01','time':'07:00'}
        self.editor=self.store.save(ADMIN,self.editor['name'],self.editor['document'],self.editor['id'],self.editor['version'])
        past=now()-timedelta(minutes=1)
        scheduled={recipient_hash(c['email']):{'timezone':'UTC','reason':'fixture','due_at':(now()+timedelta(minutes=5)).isoformat()} for c in self.rows}
        with patch('crm_campaign_schedule.plan',return_value=scheduled),patch('crm_logic.now',return_value=past),patch('crm_campaign_markets.now',return_value=past):
            self.queue()
        self.assertEqual(self.campaign()['status'],'SCHEDULED')
        # Admission now checks PostgreSQL's clock too. Advance only this
        # synthetic queue after admission to exercise the due worker lifecycle.
        self.store.q('UPDATE crm_marketing_sends SET due_at=%s WHERE campaign_id=%s',(past,self.editor['id']))
        key='campaign-timing:'+str(self.editor['id'])
        self.store.set_state(key,{**self.store.state(key),'due_at':past.isoformat()})
        self.assertFalse(self.store.q("SELECT 1 FROM crm_marketing_sends s JOIN crm_campaigns c ON c.id=s.campaign_id WHERE c.id=%s AND c.status='SENDING'",(self.editor['id'],)))
        self.store.set_state('campaign_schedule_health',{'enabled':True,'checked_at':now().isoformat()})
        provider=Mock();provider.suppressed.return_value=False;provider.send.side_effect=lambda *args:str(uuid.uuid4())
        from tests.test_crm_batch_dispatch import Transport
        provider.batch_transport=Transport()
        engine=Engine(self.store,self.shop,provider,Config(LIVE))
        # This shared disposable database contains queues from other tests;
        # isolate the worker lifecycle being asserted here.
        self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id<>%s AND status='SENDING'",(self.editor['id'],))
        target=self.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id LIMIT 1',(self.editor['id'],),True)['id']
        original_claim=self.store.claim_send
        def claim(**kwargs):
            # Exercise the production claim predicate, including exclusion of
            # frozen batch recipients from the individual-message transport.
            return original_claim(**kwargs,send_id=target)
        with patch.dict(os.environ,LIVE),patch.object(self.store,'claim_send',side_effect=claim),patch.object(self.store,'list',return_value=[]),patch.object(engine,'campaign_page'),patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            engine.tick('fixture-'+uuid.uuid4().hex);engine.tick('fixture-'+uuid.uuid4().hex)
        provider.send.assert_not_called()
        self.assertEqual(len(provider.batch_transport.calls),1)
        self.assertEqual(len(provider.batch_transport.calls[0][1]),3)
        self.assertEqual(self.campaign()['status'],'SENT');self.assertEqual(self.campaign()['final_recipient_count'],3)
        self.assertIsNotNone(self.campaign()['sent_at'])
    def test_concurrent_confirmations_share_one_queue(self):
        from concurrent.futures import ThreadPoolExecutor
        reviewed=self.reviewed()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.queue(reviewed),range(2)))
        self.assertEqual(sum(not r['already_started'] for r in results),1);self.assertEqual(len(self.sends()),3)
    def test_sent_screen_uses_only_local_metrics(self):
        self.accepted()
        from streamlit.testing.v1 import AppTest
        script='''
from unittest.mock import patch
from crm_campaign_analytics_ui import sent_table
from crm_campaign_store import CampaignStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
with patch('requests.sessions.Session.request',side_effect=AssertionError('No provider calls')):
 sent_table(CampaignStore(connect),ADMIN)
'''
        at=AppTest.from_string(script).run(timeout=20);self.assertFalse(at.exception)
        self.assertFalse(at.dataframe);self.assertFalse(at.metric)
        self.assertTrue(any(b.label=='View analytics' for b in at.button))
        self.assertTrue(any('Recipients' in e.proto.body for e in at.get('html')))
    def test_open_analytics_pauses_table_timer_and_preview_is_lazy(self):
        from streamlit.testing.v1 import AppTest
        self.accepted()
        script='''
from unittest.mock import patch
from crm_campaign_analytics_ui import sent_table
from crm_campaign_store import CampaignStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
with patch('crm_campaign_analytics_ui._live_sent_table',side_effect=AssertionError('No timer while dialog is open')):
 sent_table(CampaignStore(connect),ADMIN)
'''
        at=AppTest.from_string(script)
        at.session_state['sent_analytics_id']=self.editor['id'];at.run(timeout=20)
        self.assertFalse(at.exception);self.assertFalse(at.get('iframe'))
        next(b for b in at.button if b.label=='Email preview').click().run(timeout=20)
        self.assertFalse(at.exception);self.assertTrue(at.get('iframe'))
    def test_home_filter_switch_preserves_saved_editor_state(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns'
        at.session_state['campaign_editor']=deepcopy(self.editor);at.run(timeout=20)
        next(t for t in at.text_input if t.label=='Subject').set_value('Keep my unsent subject').run(timeout=20)
        before=deepcopy(at.session_state['campaign_editor']['document'])
        next(b for b in at.button if b.label=='← Campaigns').click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['campaign_view'],'CAMPAIGNS_HOME')
        self.assertFalse(any(b.label=='Save draft' for b in at.button))
        for tab in ('Sent','Drafts'):
            at.button_group(key='campaign_home_tab').set_value(tab).run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['campaign_editor']['document'],before)
        at.session_state['campaign_pending_open']=str(self.editor['id']);at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(next(t for t in at.text_input if t.label=='Subject').value,'Keep my unsent subject')

    def test_history_counts_move_between_drafts_sent_and_archive(self):
        before=self.store.history_counts()
        self.accepted()
        self.assertEqual({k:v for k,v in self.store.history_counts().items() if k!='polling_active'},{'active':before['active']-1,'sent':before['sent']+1})
        row=self.store.draft(self.editor['id']);self.store.archive(ADMIN,row['id'],row['version'])
        self.assertEqual({k:v for k,v in self.store.history_counts().items() if k!='polling_active'},{'active':before['active']-1,'sent':before['sent']})
    def test_older_order_response_cannot_restore_refunded_revenue(self):
        sends=self.accepted();order=order_fixture(str(self.campaign()['campaign_send_id']),sends[0]['shopify_customer_id'])
        order['updatedAt']=order['createdAt'];old=deepcopy(order)
        record(self.store,order)
        order['netPaymentSet']=bag(0);order['updatedAt']=(date(order['createdAt'])+timedelta(hours=1)).isoformat()
        record(self.store,order);self.assertIsNone(record(self.store,old))
        row=self.store.q('SELECT amount FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)
        self.assertEqual(Decimal(row['amount']),0)

class PaginationTests(unittest.TestCase):
    def test_order_lines_visits_and_refunds_follow_all_pages(self):
        from crm_attribution_shopify import order
        value=order_fixture('sc_a','customer');page={'hasNextPage':True,'endCursor':'next'}
        value['lineItems']['pageInfo']=page.copy();value['customerJourneySummary']['moments']['pageInfo']=page.copy()
        value['refunds']=[{'id':'refund','refundLineItems':{'nodes':[],'pageInfo':page.copy()}}]
        done={'nodes':[],'pageInfo':{'hasNextPage':False}}
        shop=Mock();shop.query.side_effect=[{'order':value},{'order':{'lineItems':done}},
            {'order':{'customerJourneySummary':{'moments':done}}},{'node':{'refundLineItems':done}}]
        self.assertEqual(order(shop,value['id'])['id'],value['id']);self.assertEqual(shop.query.call_count,4)
    def test_nonadvancing_cursor_fails_safely(self):
        from crm_attribution_shopify import complete
        page={'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'same'}}
        with self.assertRaisesRegex(ValueError,'did not advance'):complete(page,lambda _:page)
