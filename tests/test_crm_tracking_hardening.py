"""Offline attribution acceptance: no live Shopify, Resend or database mutations."""
from copy import deepcopy
from datetime import timedelta
import json
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlsplit
from crm_logic import now
from crm_tracking import campaign_link,send_identity,validate_links,event_link
from crm_campaign_attribution import choose,record,mirror,schedule_order,reconcile,mirror_payload
from crm_tracking_health import verify,webhook_status,observations
from tests.test_crm_production_v2 import order_fixture,visit,bag
from tests import test_crm_production_v2 as fixtures


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.identity=str(uuid.uuid4());self.sid=send_identity(self.identity)
        self.link=campaign_link('https://www.sportscaveshop.com/products/art?variant=123&UTM_CAMPAIGN=old#art',
          'sc_draft','product_1',test=False,campaign_id=self.identity,send_id=self.sid)
        self.at=now();self.campaign={'id':self.identity,'name':'Fixture','campaign_key':'sc_draft',
          'campaign_send_id':self.sid,'status':'SENT','sending_started_at':self.at-timedelta(days=1)}
        self.order=order_fixture(self.sid,'customer',self.at)
        self.click={'campaign_key':'sc_draft','shopify_customer_id':'customer','occurred_at':self.at-timedelta(minutes=10),'clicked_url':self.link}

    def test_send_identity_and_query_fragment(self):
        p=urlsplit(self.link);q=parse_qs(p.query)
        self.assertEqual(q['utm_campaign'],[self.sid]);self.assertEqual(q['sc_campaign_id'],[self.identity])
        self.assertEqual(q['sc_campaign_send_id'],[self.sid]);self.assertEqual(q['variant'],['123']);self.assertEqual(p.fragment,'art')
        self.assertEqual(self.sid,send_identity(self.identity));self.assertNotEqual(self.sid,send_identity(str(uuid.uuid4())))
        self.assertFalse(validate_links('<a href="'+self.link+'">Art</a>',self.identity,self.sid))
        self.assertIn('sc_campaign_send_id',event_link(self.link))

    def test_invalid_decoration_blocks(self):
        for url in ('https://www.sportscaveshop.com/products/art',self.link.replace(self.sid,'wrong'),self.link.replace('#art','&UTM_SOURCE=other#art')):
            with self.subTest(url=url):self.assertTrue(validate_links('<a href="'+url+'">Art</a>',self.identity,self.sid))

    def test_broken_decorator_cannot_bypass_final_validation(self):
        from crm_campaign_content import render_campaign
        from tests.test_crm_simple_editor import document
        from tests.test_crm_send_flow import CFG
        with patch('crm_tracking.campaign_link',side_effect=lambda url,*a,**k:url),self.assertRaisesRegex(ValueError,'Tracking validation failed'):
            render_campaign(document(),CFG,production=True,unsubscribe_url='https://www.sportscaveshop.com/account/unsubscribe',campaign_id=self.identity,send_id=self.sid)

    def test_protected_links_untouched(self):
        for url in ('mailto:hello@example.test','tel:123','#art','https://external.example/art','https://www.sportscaveshop.com/account/unsubscribe?token=x','https://www.sportscaveshop.com/products/art?signature=x'):
            self.assertEqual(campaign_link(url,'draft','x',test=False,campaign_id=self.identity,send_id=self.sid),url)
            self.assertFalse(validate_links('<a href="'+url+'">Link</a>',self.identity,self.sid))

    def test_first_last_intermediate_exact(self):
        for position in ('firstVisit','lastVisit','moments'):
            order=deepcopy(self.order);v=order['customerJourneySummary']['lastVisit'];order['customerJourneySummary']={'ready':True}
            order['customerJourneySummary'][position]={'nodes':[{},v,{}]} if position=='moments' else v
            self.assertEqual(choose(order,[self.campaign],[])['method'],'SHOPIFY_UTM_EXACT')

    def test_pending_does_not_fallback(self):
        self.order['customerJourneySummary']['ready']=False
        self.assertIsNone(choose(self.order,[self.campaign],[self.click]))

    def test_missing_journey_requires_real_exact_click(self):
        self.order['customerJourneySummary']=None
        self.assertIsNone(choose(self.order,[self.campaign],[]))  # delivered/opened are not candidates
        self.assertEqual(choose(self.order,[self.campaign],[self.click])['method'],'RESEND_CLICK_MATCH')
        for change in ({'shopify_customer_id':'other'},{'clicked_url':self.link.replace('sc_campaign_send_id','missing')},
                       {'occurred_at':self.at+timedelta(seconds=1)},{'occurred_at':self.at-timedelta(days=8)}):
            self.assertIsNone(choose(self.order,[self.campaign],[{**self.click,**change}]))

    def test_exact_beats_later_click_otherwise_latest_valid_click(self):
        other={**self.campaign,'id':str(uuid.uuid4()),'campaign_key':'sc_other'};other['campaign_send_id']=send_identity(other['id'])
        click={**self.click,'campaign_key':'sc_other','occurred_at':self.at-timedelta(minutes=1),
          'clicked_url':campaign_link('https://www.sportscaveshop.com/products/other','sc_other','other',test=False,campaign_id=other['id'],send_id=other['campaign_send_id'])}
        self.assertEqual(choose(self.order,[self.campaign,other],[self.click,click])['campaign']['id'],self.identity)
        self.order['customerJourneySummary']=None
        self.assertEqual(choose(self.order,[self.campaign,other],[self.click,click])['campaign']['id'],other['id'])

    def test_complete_conflicting_journey_never_falls_back(self):
        self.order['customerJourneySummary']['lastVisit']['utmParameters']['campaign']='other_marketing_campaign'
        self.assertIsNone(choose(self.order,[self.campaign],[self.click]))

    def test_pagination_preserves_intermediate_visits(self):
        from crm_attribution_shopify import complete
        fetch=Mock(side_effect=[{'nodes':[2],'pageInfo':{'hasNextPage':True,'endCursor':'b'}},{'nodes':[3],'pageInfo':{'hasNextPage':False}}])
        self.assertEqual(complete({'nodes':[1],'pageInfo':{'hasNextPage':True,'endCursor':'a'}},fetch),[1,2,3])
        with self.assertRaises(ValueError):complete({'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'a'}},lambda _: {'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'a'}})

    def test_own_endpoint_only_and_paid_forwarding(self):
        env={'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://os.example'}
        rows=[{'topic':t,'endpoint':{'callbackUrl':'https://os.example/webhooks/shopify/'+('orders-paid' if t=='ORDERS_PAID' else 'crm')}} for t in ('ORDERS_CREATE','ORDERS_UPDATED','ORDERS_PAID')]
        self.assertTrue(all(webhook_status(rows,env).values()))
        rows[0]['endpoint']['callbackUrl']='https://another-app.example/webhook'
        self.assertFalse(webhook_status(rows,env)['ORDERS_CREATE'])

    def test_configuration_alone_is_never_ready(self):
        shop=Mock();shop.query.side_effect=RuntimeError('unavailable')
        result=verify(shop,env={'CRM_RESEND_WEBHOOK_SECRET':'fixture','CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'})
        self.assertEqual(result['status'],'NOT READY');self.assertEqual(result['checks']['Shopify Journey API'],'UNAVAILABLE')
        self.assertNotIn('fixture',json.dumps(result))

    def test_health_requires_actual_events_and_recent_worker(self):
        store=Mock();store.q.return_value={'shopify':None,'resend':None};store.state.return_value={}
        state=observations(store);self.assertEqual(state['Resend webhook'],'NEVER RECEIVED');self.assertEqual(state['Attribution reconcile'],'NEVER RECEIVED')
        store.q.return_value={'shopify':now(),'resend':now()};store.state.side_effect=lambda k:{'last_run':now().isoformat()} if k=='email_reconcile_health' else {}
        self.assertTrue(observations(store)['Attribution reconcile'].startswith('RECENT'))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class LedgerTests(unittest.TestCase):
    setUp=fixtures.ProductionSqlTests.setUp
    reviewed=fixtures.ProductionSqlTests.reviewed
    queue=fixtures.ProductionSqlTests.queue
    campaign=fixtures.ProductionSqlTests.campaign
    sends=fixtures.ProductionSqlTests.sends
    accepted=fixtures.ProductionSqlTests.accepted
    event=fixtures.ProductionSqlTests.event

    def make_order(self):
        recipient=self.accepted()[0];c=self.campaign()
        order=order_fixture(str(c['campaign_send_id']),recipient['shopify_customer_id'])
        self.addCleanup(lambda:self.store.q('DELETE FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],)))
        order.update(totalReceivedSet=bag(180),totalRefundedSet=bag(0))
        return order,recipient

    def saved(self,order):return self.store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)

    def test_delayed_journey_is_durable_then_attributes(self):
        order,_=self.make_order();order['customerJourneySummary']['ready']=False
        self.assertIsNone(record(self.store,order));row=self.saved(order)
        self.assertEqual(row['attribution_status'],'PENDING_JOURNEY');self.assertIsNotNone(row['retry_at']);self.assertFalse(row['eligible'])
        order['customerJourneySummary']['ready']=True
        self.assertEqual(record(self.store,order)['method'],'SHOPIFY_UTM_EXACT')
        self.assertEqual(self.saved(order)['attribution_status'],'ATTRIBUTED')

    def test_event_idempotency_all_order_topics(self):
        from crm_webhooks import receive_shopify
        order,_=self.make_order()
        for topic in ('orders/create','orders/updated','orders/paid'):
            event='fixture-'+uuid.uuid4().hex;payload={'id':order['id'].rsplit('/',1)[-1]}
            self.assertTrue(receive_shopify(self.store,topic,event,payload,now().isoformat()))
            self.assertFalse(receive_shopify(self.store,topic,event,payload,now().isoformat()))
            schedule_order(self.store,order['id'])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_order_attribution WHERE shopify_order_id=%s',(order['id'],),True)['n'],1)

    def test_refund_preserves_attribution_when_journey_disappears(self):
        order,_=self.make_order();record(self.store,order);before=self.saved(order)
        order.update(netPaymentSet=bag(0),totalRefundedSet=bag(180),fullyPaid=False,customerJourneySummary=None)
        record(self.store,order);after=self.saved(order)
        self.assertEqual(after['campaign_id'],before['campaign_id']);self.assertEqual(after['method'],before['method'])
        self.assertEqual(float(after['amount']),0);self.assertEqual(float(after['refund_amount']),180);self.assertTrue(after['eligible'])

    def test_pre_v2_association_is_not_erased(self):
        order,_=self.make_order();record(self.store,order);prior=self.saved(order)
        self.store.q('UPDATE crm_order_attribution SET method=NULL WHERE shopify_order_id=%s',(order['id'],))
        order['customerJourneySummary']=None;record(self.store,order)
        self.assertEqual(self.saved(order)['campaign_id'],prior['campaign_id'])
        self.assertIsNone(self.saved(order)['method'])

    def test_mirror_idempotent_non_pii_conflict_and_retry(self):
        order,_=self.make_order();match=record(self.store,order);payload=mirror_payload(self.saved(order))
        self.assertNotIn('customer',json.dumps(payload));self.assertNotIn('email@',json.dumps(payload))
        with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'}),patch('shopify_sync.fetch_metafields',return_value={'metafields':[]}),patch('shopify_sync.metafields_set',return_value={'count':1}) as write:
            mirror(self.store,order,match);sent=write.call_args.args[0][0]
            self.assertEqual((sent['namespace'],sent['key'],sent['type']),('sports_cave_os','email_attribution','json'))
            self.assertIsNone(sent['compareDigest'])
        self.assertEqual(self.saved(order)['mirror_status'],'UPDATED')
        for value,expected in ((payload,'UPDATED'),({**payload,'campaign_send_id':'conflict'},'FAILED')):
            with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'}),patch('shopify_sync.fetch_metafields',return_value={'metafields':[{'key':'email_attribution','value':json.dumps(value),'compareDigest':'digest'}]}),patch('shopify_sync.metafields_set') as write:
                mirror(self.store,order,match);write.assert_not_called();self.assertEqual(self.saved(order)['mirror_status'],expected)
        self.assertEqual(self.saved(order)['mirror_error'],'attribution_conflict_admin_review')
        with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'}),patch('shopify_sync.fetch_metafields',side_effect=RuntimeError('no credentials')):
            mirror(self.store,order,match)
        self.assertTrue(self.saved(order)['eligible']);self.assertIsNotNone(self.saved(order)['retry_at'])
        schedule_order(self.store,order['id']);self.store.set_state('email_attribution_scan',{'next_at':(now()+timedelta(hours=1)).isoformat()})
        with patch.dict(os.environ,{'CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED':'true'}),patch('crm_attribution_shopify.order',return_value=order),patch('shopify_sync.fetch_metafields',return_value={'metafields':[]}),patch('shopify_sync.metafields_set',return_value={'count':1}):
            reconcile(self.store,self.shop)
        self.assertEqual(self.saved(order)['mirror_status'],'UPDATED')

    def test_real_click_records_recipient_and_timing_but_delivery_alone_does_not(self):
        order,recipient=self.make_order();order['customerJourneySummary']=None
        self.event(recipient,'email.delivered');self.event(recipient,'email.opened')
        self.assertIsNone(record(self.store,order))
        c=self.campaign();link=campaign_link('https://www.sportscaveshop.com/products/art',c['campaign_key'],'art',test=False,campaign_id=c['id'],send_id=c['campaign_send_id'])
        self.event(recipient,'email.clicked',now(),link=link)
        record(self.store,order);saved=self.saved(order)
        self.assertEqual(saved['method'],'RESEND_CLICK_MATCH');self.assertEqual(saved['evidence']['recipient_send_id'],str(recipient['id']))
        self.assertEqual(saved['evidence']['resend_message_id'],recipient['provider_email_id']);self.assertGreater(saved['evidence']['time_to_purchase_seconds'],0)

    def test_audit_columns_rls_and_orders_ui(self):
        order,_=self.make_order();record(self.store,order)
        from crm_campaign_analytics import details
        self.assertEqual(details(self.store,self.campaign()['id'])['orders'][0]['shopify_order_id'],order['id'])
        row=self.store.q("SELECT relrowsecurity FROM pg_class WHERE relname='crm_order_attribution'",one=True)
        self.assertTrue(row['relrowsecurity'])
        for role in ('anon','authenticated'):
            self.assertFalse(self.store.q("SELECT has_table_privilege(%s,'crm_order_attribution','SELECT') allowed",(role,),True)['allowed'])

    def test_evidence_ui_is_lazy_and_uses_local_records(self):
        order,_=self.make_order();record(self.store,order)
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import patch
from crm_campaign_analytics_ui import email_orders
from crm_campaign_store import CampaignStore
from tests.crm_db_fixture import connect
store=CampaignStore(connect)
rows=store.q('SELECT * FROM crm_order_attribution WHERE shopify_order_id=%s',(st.session_state['order_id'],))
with patch('requests.sessions.Session.request',side_effect=AssertionError('No external calls')):
 email_orders(store,rows)
'''
        at=AppTest.from_string(script);at.session_state['order_id']=order['id'];at.run(timeout=20)
        self.assertFalse(at.exception);self.assertFalse(at.tabs)
        at.selectbox[0].set_value(order['id']).run(timeout=20)
        self.assertFalse(at.exception);self.assertEqual([t.label for t in at.tabs],['Resend','Shopify','Attribution','Purchase'])
