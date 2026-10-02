"""Loopback SQL and mocked Resend only; no live sending or Shopify dispatch."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
import os
import time
import unittest
import uuid
from crm_campaign_dispatch import dispatch,payload
from crm_campaign_send import review,queue_campaign
from crm_campaign_store import CampaignStore
from crm_engine import Engine
from crm_logic import now,recipient_hash
from crm_resend import Config
from crm_resend_batch import BatchError,BatchTransport,Gate
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_campaign_v2 import authority,profile
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_simple_editor import document


class Transport:
    concurrency=2
    def __init__(self):self.calls=[];self.receipts={};self.errors={};self.blocked=set()
    def suppressed_hashes(self):return self.blocked
    def send(self,messages,key):
        self.calls.append((key,deepcopy(messages)))
        if self.errors.get(key):raise self.errors.pop(key)
        if key not in self.receipts:self.receipts[key]=[str(uuid.uuid4()) for _ in messages]
        return {'ids':self.receipts[key],'status':200,'remaining':'8','retry_after':0}


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect);self.ids=[];self.transport=Transport()
        self.provider=SimpleNamespace(batch_transport=self.transport)
        self.shop=Mock();self.shop.customer.side_effect=AssertionError('No Shopify dispatch')
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden'))
        self.guard.start();self.addCleanup(self.guard.stop)
        self.config=Config(LIVE);self.engine=Engine(self.store,self.shop,self.provider,self.config)
    def tearDown(self):
        for identity in self.ids:self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id=%s AND status='SENDING'",(identity,))
    def queue(self,count):
        seed=uuid.uuid4().int%100000000000
        rows=[profile(seed+i,'NZ') for i in range(count)]
        shop=authority(rows);doc=document();doc.update(market='NZ',market_audience=True)
        from crm_campaign_markets import audience
        doc['audience']=audience('NZ')
        with patch.object(self.store,'render_settings',return_value=deepcopy(CFG)),patch.dict(os.environ,LIVE):
            editor=self.store.save(ADMIN,'Batch '+uuid.uuid4().hex,doc,env=LIVE)
            reviewed=review(shop,self.store,editor,LIVE)
            result=queue_campaign(shop,self.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=reviewed['snapshot_id'])
        self.ids.append(editor['id']);self.assertEqual(result['recipients'],count)
        # PGlite's clock can trail Python by a few milliseconds. These immediate
        # send fixtures are due already; do not let clock skew select an older job.
        self.store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 second' WHERE campaign_id=%s",(editor['id'],))
        return editor['id']
    def states(self,identity):
        return self.store.q("SELECT value FROM crm_runtime_state WHERE value->>'campaign_id'=%s AND key LIKE 'campaign-batch:%%' ORDER BY (value->>'batch_index')::integer",(str(identity),))
    def sends(self,identity):return self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY recipient_hash',(identity,))
    def test_counts_one_99_100_101_1095_and_deterministic_order(self):
        for count,expected in ((1,1),(99,1),(100,1),(101,2),(1095,11)):
            with self.subTest(count=count):
                identity=self.queue(count);self.transport.calls.clear()
                with patch('crm_campaign_content.render_campaign',side_effect=AssertionError('No dispatch rerender')):
                    self.assertTrue(dispatch(self.engine))
                self.assertEqual(len(self.transport.calls),expected)
                messages=[m for _,group in self.transport.calls for m in group]
                self.assertEqual(len(messages),count);self.assertTrue(all(len(g)<=100 for _,g in self.transport.calls))
                self.assertEqual([recipient_hash(m['to'][0]) for m in messages],sorted(recipient_hash(m['to'][0]) for m in messages))
                self.assertEqual(len({m['headers']['List-Unsubscribe'] for m in messages}),count)
                for m in messages:
                    self.assertIn(m['headers']['List-Unsubscribe'][1:-1].replace('&','&amp;'),m['html'])
                    self.assertIn('sc_campaign_id=',m['html']);self.assertNotIn('sc_test=1',m['html'])
                self.assertTrue(all(r['status']=='ACCEPTED' for r in self.sends(identity)))
                self.assertTrue(all('payloads' not in s['value'] and '_payloads' not in s['value'] for s in self.states(identity)))
                self.assertFalse(dispatch(self.engine))
                self.assertEqual(len(self.transport.calls),expected)
        self.shop.customer.assert_not_called()
    def test_429_retry_same_payload_key_and_successful_batch_never_replayed(self):
        identity=self.queue(101)
        send_id=self.store.q('SELECT campaign_send_id FROM crm_campaigns WHERE id=%s',(identity,),True)['campaign_send_id']
        key=f'sports-cave/{send_id}/batch/1';self.transport.errors[key]=BatchError(429,120)
        dispatch(self.engine)
        self.assertEqual(sum(s['status']=='ACCEPTED' for s in self.sends(identity)),100)
        state=self.states(identity)[1]['value'];self.assertGreaterEqual((__import__('crm_logic').date(state['retry_at'])-now()).total_seconds(),118)
        self.assertFalse(dispatch(self.engine))
        state['retry_at']=(now()-timedelta(seconds=1)).isoformat()
        self.store.set_state('campaign-batch:'+str(send_id)+':1',state)
        dispatch(Engine(self.store,self.shop,self.provider,self.config))
        self.assertEqual([k for k,_ in self.transport.calls].count(key),2)
        self.assertEqual(self.transport.calls[1],self.transport.calls[2])
        self.assertEqual(len(self.transport.calls),3)
        self.assertTrue(all(s['status']=='ACCEPTED' for s in self.sends(identity)))
    def test_provider_success_then_db_failure_retries_identically(self):
        identity=self.queue(1)
        import crm_campaign_dispatch as module
        original=module.finish
        with patch.object(module,'finish',side_effect=RuntimeError('simulated receipt outage')):
            with self.assertRaises(RuntimeError):dispatch(self.engine)
        state=self.states(identity)[0]['value'];self.assertEqual(state['attempt_count'],1)
        self.assertEqual(self.sends(identity)[0]['status'],'SUBMITTING')
        dispatch(Engine(self.store,self.shop,self.provider,self.config))
        self.assertEqual(self.transport.calls[0],self.transport.calls[1]);self.assertEqual(len(self.transport.receipts),1)
        self.assertEqual(self.sends(identity)[0]['status'],'ACCEPTED')
        dispatch(self.engine);self.assertEqual(len(self.transport.calls),2)
    def test_expired_uncertain_batch_held_without_transport(self):
        identity=self.queue(1)
        with patch('crm_campaign_dispatch.finish',side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):dispatch(self.engine)
        entry=self.states(identity)[0]['value'];entry['request_started_at']=(now()-timedelta(hours=24)).isoformat()
        key='campaign-batch:'+entry['campaign_send_id']+':0';self.store.set_state(key,entry)
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),1);self.assertEqual(self.sends(identity)[0]['status'],'UNCERTAIN')
    def test_local_and_provider_suppression_remove_only_blocked_recipients(self):
        identity=self.queue(3);rows=self.sends(identity)
        self.store.suppress(rows[0]['recipient_hash'],rows[0]['shopify_customer_id'],'unsubscribe','fixture')
        self.transport.blocked={rows[1]['recipient_hash']}
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls[0][1]),1)
        self.assertEqual(sorted(s['status'] for s in self.sends(identity)),['ACCEPTED','BLOCKED','BLOCKED'])
    def test_consent_change_after_queue_blocks_without_shopify(self):
        identity=self.queue(2);row=self.sends(identity)[0]
        self.store.webhook('shopify',uuid.uuid4().hex,'customers_email_marketing_consent/update',row['shopify_customer_id'],row['shopify_customer_id'],now())
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls[0][1]),1);self.shop.customer.assert_not_called()
    def test_rejection_failed_and_no_repeat(self):
        identity=self.queue(1);cid=self.store.q('SELECT campaign_send_id FROM crm_campaigns WHERE id=%s',(identity,),True)['campaign_send_id']
        self.transport.errors[f'sports-cave/{cid}/batch/0']=BatchError(422,category='provider_rejected')
        dispatch(self.engine);dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),1);self.assertEqual(self.sends(identity)[0]['status'],'FAILED')
    def test_worker_complete_on_acceptance_then_webhook_delivery(self):
        identity=self.queue(2)
        with patch.object(self.store,'list',return_value=[]),patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            self.engine.tick(uuid.uuid4().hex)
        row=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        self.assertEqual(row['status'],'SENT');self.assertEqual(row['final_recipient_count'],2)
        from crm_webhooks import receive_resend
        receipt=self.sends(identity)[0]
        receive_resend(self.store,uuid.uuid4().hex,{'type':'email.delivered','created_at':now().isoformat(),'data':{'email_id':receipt['provider_email_id']}})
        self.assertTrue(self.store.q("SELECT 1 FROM crm_delivery_events WHERE send_id=%s AND event_type='email.delivered'",(receipt['id'],)))
        dispatch(self.engine);self.assertEqual(len(self.transport.calls),1)
    def test_home_row_shows_batch_truth_without_delivery_guessing(self):
        identity=self.queue(2);dispatch(self.engine)
        from crm_campaign_home_data import rows
        from crm_campaign_home import row_html
        row=next(r for r in rows(self.store,detail=identity) if str(r['id'])==str(identity))
        self.assertEqual(row['submitted'],2);self.assertEqual(row['planned'],2)
        self.assertEqual(row['delivered'],0)
        self.assertIn('2 / 2 submitted',row_html(row));self.assertIn('Sending',row_html(row))
    def test_durable_1095_progress_survives_client_loss_and_reopen(self):
        identity=self.queue(1095)
        from crm_campaign_progress import read_progress
        import crm_campaign_dispatch as module
        initial=read_progress(self.store,[identity])[str(identity)]
        self.assertEqual((initial['total'],initial['processed']),(1095,0))
        values=[];original=module.finish
        def finish(*args):
            original(*args)
            # New connection/session: no browser state is needed to read truth.
            progress=read_progress(CampaignStore(connect),[identity])[str(identity)]
            values.append(progress['processed'])
            self.assertIsNotNone(progress['worker_started_at'])
            self.assertIsNotNone(progress['last_progress_at'])
            self.assertLessEqual(progress['processed'],progress['total'])
        with patch.object(module,'finish',side_effect=finish):dispatch(self.engine)
        self.assertEqual(values,[100,200,300,400,500,600,700,800,900,1000,1095])
        with patch.object(self.store,'list',return_value=[]),patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            self.engine.tick(uuid.uuid4().hex)
        reopened=read_progress(CampaignStore(connect),[identity])[str(identity)]
        self.assertEqual((reopened['status'],reopened['processed']),('SENT',1095))
        self.assertEqual(len(self.transport.calls),11)
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),11)
    def test_marketing_off_no_dispatch(self):
        self.queue(1);self.engine.config.enabled=False
        self.assertFalse(dispatch(self.engine));self.assertFalse(self.transport.calls)
    def test_one_invalid_frozen_address_does_not_poison_valid_members(self):
        identity=self.queue(3)
        campaign=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        content=self.store.template(campaign['template_id'],campaign['template_version'])
        first=next(iter(content['dispatch']['recipients'].values()));first['address']='invalid'
        with patch.object(self.store,'template',return_value=content):dispatch(self.engine)
        self.assertEqual(len(self.transport.calls[0][1]),2)
        self.assertEqual(sorted(s['status'] for s in self.sends(identity)),['ACCEPTED','ACCEPTED','BLOCKED'])
    def test_pretransport_persistence_failure_rolls_back_and_can_retry(self):
        identity=self.queue(2)
        with patch('crm_campaign_dispatch.persist',side_effect=ValueError('fixture failure')):
            with self.assertRaises(ValueError):dispatch(self.engine)
        self.assertFalse(self.transport.calls)
        self.assertTrue(all(s['status']=='PENDING' for s in self.sends(identity)))
        dispatch(self.engine);self.assertEqual(len(self.transport.calls),1)
    def test_logs_only_safe_ids_counts_and_timings(self):
        identity=self.queue(2)
        with self.assertLogs('crm_campaign_dispatch',level='INFO') as capture:dispatch(self.engine)
        logs='\n'.join(capture.output)
        self.assertIn('batch_size=2',logs);self.assertIn('shopify_calls_during_dispatch=0',logs)
        self.assertNotIn('@example.test',logs);self.assertNotIn('token=',logs)
        self.assertNotIn('<html',logs);self.assertNotIn('unsubscribe',logs)
        self.assertNotIn(self.config.api_key,logs)
    def test_future_recipient_is_not_submitted_early(self):
        identity=self.queue(2);row=self.sends(identity)[0]
        self.store.q("UPDATE crm_marketing_sends SET due_at=now()+interval '1 day' WHERE id=%s",(row['id'],))
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls[0][1]),1)
        self.assertEqual(sum(s['status']=='PENDING' for s in self.sends(identity)),1)
    def test_early_delivery_event_reconciles_after_bulk_receipts(self):
        identity=self.queue(1);original=self.transport.send
        from crm_webhooks import receive_resend
        def early(messages,key):
            result=original(messages,key)
            receive_resend(self.store,uuid.uuid4().hex,{'type':'email.delivered','created_at':now().isoformat(),'data':{'email_id':result['ids'][0]}})
            return result
        self.transport.send=early;dispatch(self.engine)
        row=self.sends(identity)[0]
        self.assertTrue(self.store.q('SELECT 1 FROM crm_delivery_events WHERE send_id=%s',(row['id'],)))
    def test_stop_state_changes_before_later_batch_submit(self):
        identity=self.queue(101);original=self.transport.send
        # First wave only: inject a local opt-out while the first batch is sent.
        self.transport.concurrency=1
        def stop(messages,key):
            if key.endswith('/0'):
                row=self.sends(identity)[-1]
                self.store.suppress(row['recipient_hash'],row['shopify_customer_id'],'unsubscribe','fixture')
            return original(messages,key)
        self.transport.send=stop;dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),1)
        self.assertEqual(sum(s['status']=='BLOCKED' for s in self.sends(identity)),1)
    def test_substitution_matches_actual_production_renderer(self):
        identity=self.queue(1)
        c=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        content=self.store.template(c['template_id'],c['template_version'])
        recipient=next(iter(content['dispatch']['recipients'].values()))
        from crm_campaign_content import render_campaign
        expected=render_campaign(content['document'],content['render_settings'],production=True,
            unsubscribe_url=recipient['unsubscribe_url'],campaign_id=str(identity),send_id=str(c['campaign_send_id']))
        actual=payload(content['dispatch']['message'],recipient,self.config)
        self.assertEqual({k:actual[k] for k in ('subject','html','text')},expected)
    def test_uncertain_retry_is_held_when_stop_state_changes(self):
        identity=self.queue(2)
        with patch('crm_campaign_dispatch.finish',side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):dispatch(self.engine)
        row=self.sends(identity)[0]
        self.store.suppress(row['recipient_hash'],row['shopify_customer_id'],'unsubscribe','fixture')
        dispatch(self.engine)
        self.assertEqual(len(self.transport.calls),1)
        self.assertTrue(all(r['status']=='UNCERTAIN' for r in self.sends(identity)))


class ApiTests(unittest.TestCase):
    def provider(self,responses):
        session=Mock();session.request.side_effect=responses
        transport=BatchTransport(SimpleNamespace(session=session,config=Config(LIVE)))
        transport.gate.wait=Mock();return session,transport
    def response(self,status=200,data=None,headers=None):
        return SimpleNamespace(status_code=status,json=lambda:data,headers=headers or {})
    def test_documented_endpoint_idempotency_and_ordered_uuids(self):
        ids=[str(uuid.uuid4()),str(uuid.uuid4())]
        session,transport=self.provider([self.response(data={'data':[{'id':i} for i in ids]})])
        result=transport.send([{'to':['a@example.test']},{'to':['b@example.test']}],'stable-key')
        self.assertEqual(result['ids'],ids)
        args,kwargs=session.request.call_args
        self.assertEqual(args,('POST','https://api.resend.com/emails/batch'))
        self.assertEqual(kwargs['headers']['Idempotency-Key'],'stable-key');self.assertEqual(kwargs['headers']['x-batch-validation'],'strict')
        self.assertFalse(kwargs['allow_redirects'])
    def test_429_honors_retry_after_and_gate(self):
        session,transport=self.provider([self.response(429,headers={'retry-after':'42','ratelimit-limit':'2','ratelimit-remaining':'0','ratelimit-reset':'1'})])
        with self.assertRaises(BatchError) as caught:transport.send([{}],'same')
        self.assertEqual(caught.exception.retry_after,42);self.assertGreater(transport.gate.next,time.monotonic()+40)
        self.assertEqual(transport.concurrency,1)
    def test_unknown_malformed_response_never_guesses_mapping(self):
        for data in ({'data':[]},{'data':[{'id':'bad'}]},{'data':[{'id':str(uuid.uuid4())}],'errors':[{'index':0,'message':'PII secret'}]}):
            _,transport=self.provider([self.response(data=data)])
            with self.assertRaises(BatchError) as error:transport.send([{}],'stable')
            self.assertEqual(str(error.exception),'submission_uncertain')
    def test_suppression_and_contacts_paginate_once_not_per_recipient(self):
        first={'data':[{'id':'one','email':'a@example.test'}],'has_more':True}
        last={'data':[{'id':'two','email':'b@example.test'}],'has_more':False}
        contacts={'data':[{'id':'three','email':'c@example.test','unsubscribed':True}],'has_more':False}
        session,transport=self.provider([self.response(data=d) for d in (first,last,contacts)])
        self.assertEqual(transport.suppressed_hashes(),{recipient_hash(v+'@example.test') for v in 'abc'})
        self.assertEqual(session.request.call_count,3)
        self.assertEqual(session.request.call_args_list[1].kwargs['params']['after'],'one')
    def test_incomplete_stop_state_fails_closed(self):
        _,transport=self.provider([self.response(data={'data':[],'has_more':True})])
        with self.assertRaises(BatchError):transport.suppressed_hashes()
    def test_rate_limit_headers_establish_bounded_two_concurrency(self):
        gate=Gate();self.assertEqual(gate.concurrency,1)
        gate.observe({'ratelimit-limit':'10','ratelimit-remaining':'9','ratelimit-reset':'1'},200)
        self.assertEqual(gate.concurrency,2)
        gate.observe({'ratelimit-limit':'99999','ratelimit-remaining':'99999','ratelimit-reset':'1'},200)
        self.assertEqual(gate.concurrency,2)
