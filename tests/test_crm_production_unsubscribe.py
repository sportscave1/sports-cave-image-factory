"""Offline opt-out tests. Shopify writes and email delivery are always mocked."""
import os
import uuid
import unittest
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_http import router
from crm_webhooks import unsubscribe
from crm_consent_sync import reconcile_opt_out,reconcile_pending
from crm_shopify import Shopify,UNSUBSCRIBE,CapabilityUnavailable
from crm_campaign_store import CampaignStore
from crm_campaign_markets import calculate
from crm_campaign_content import render_campaign
from crm_logic import recipient_hash
from tests.crm_db_fixture import connect
from tests.test_crm import config
from tests.test_crm_campaign_v2 import profile,authority
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

class TokenAndTransportTests(unittest.TestCase):
    def test_tokens_tamper_and_no_pii(self):
        cfg=config(False);identity=str(uuid.uuid4());url=cfg.unsubscribe_url(identity)
        token=url.split('token=')[1]
        self.assertEqual(cfg.verify_token(token),identity)
        for bad in [token+'x',token[:-1]+'z','ÃƒÆ’Ã‚Â©.'+'z'*64,None,'x'*10000]:
            self.assertIsNone(cfg.verify_token(bad))
        self.assertNotIn('@',url);self.assertNotIn('shopify',url);self.assertFalse(cfg.enabled)

    def test_mutation_exact_and_acknowledged(self):
        cid='gid://shopify/Customer/42'
        wire=Mock(return_value={'customerEmailMarketingConsentUpdate':{'customer':{'id':cid,'emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}},'userErrors':[]}})
        shop=Shopify(wire)
        self.assertTrue(shop.unsubscribe_only(cid))
        wire.assert_called_once_with(UNSUBSCRIBE,{'input':{'customerId':cid,'emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}}})
        wire.return_value={'customerEmailMarketingConsentUpdate':{'userErrors':[{'message':'private'}]}}
        with self.assertRaises(CapabilityUnavailable) as error:shop.unsubscribe_only(cid)
        self.assertNotIn('private',str(error.exception))

    def test_count_cache_refreshes_on_suppression_revision(self):
        from crm_segment_counts import SegmentCounts
        class Queue:
            def submit(self,fn,*args):self.job=lambda:fn(*args)
        queue=Queue();clock=[0];store=Mock();store.state.return_value={'version':'before'}
        counts={m:{'subscribed':1} for m in ['AU','US','UK','Global']};loader=Mock(return_value=counts)
        cache=SegmentCounts(clock=lambda:clock[0],executor=queue,loader=loader);shop=Mock()
        cache.display(shop,store);queue.job()
        cache.display(shop,store);self.assertEqual(loader.call_count,1)
        clock[0]=11;store.state.return_value={'version':'after'};loader.return_value={m:{'subscribed':0} for m in counts}
        cache.display(shop,store);queue.job()
        self.assertEqual(cache.display(shop,store)['counts']['Global'],0)
        self.assertEqual(loader.call_count,2)

    def test_local_storage_failure_never_calls_shopify(self):
        store=Mock();writer=Mock();identity=str(uuid.uuid4());cfg=config(False)
        store.receipt.return_value={'recipient_hash':'hash','shopify_customer_id':'gid://shopify/Customer/1','test_send':False}
        store.record_unsubscribe.side_effect=RuntimeError('storage unavailable')
        with self.assertRaises(RuntimeError):unsubscribe(store,cfg,cfg.unsubscribe_url(identity).split('token=')[1],writer)
        writer.unsubscribe_only.assert_not_called()

    def test_public_test_link_never_touches_store(self):
        app=FastAPI();app.include_router(router)
        with patch('crm_store.Store') as store,patch('crm_shopify.Shopify') as shop:
            for method in ['get','post']:
                result=getattr(TestClient(app),method)('/crm/unsubscribe/test')
                self.assertEqual(result.status_code,200);self.assertIn('No subscription',result.text)
            store.assert_not_called();shop.assert_not_called()

    def test_preview_test_safe_and_production_link_required(self):
        doc=document()
        from crm_campaign_sections import section_defaults
        doc['html_sections']=section_defaults(CFG)
        with patch.dict(os.environ,{'CRM_PUBLIC_BASE_URL':'https://hooks.example.test'},clear=True):
            from crm_campaign_content import settings
            preview=render_campaign(doc,{**CFG,**settings()})
            self.assertIn('/crm/unsubscribe/test',preview['html']);self.assertNotIn('?token=',preview['html'])
            url=config(False).unsubscribe_url(str(uuid.uuid4()))
            live=render_campaign(doc,CFG,unsubscribe_url=url,production=True)
            self.assertIn(url,live['html']);self.assertNotIn('/crm/unsubscribe/test',live['html'])
            doc['html_sections']['footer']='<p>Removed link</p>'
            with self.assertRaises(ValueError):render_campaign(doc,CFG,unsubscribe_url=url,production=True)

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect);self.cfg=config(False)
        self.identity=str(uuid.uuid4());self.cid='gid://shopify/Customer/'+str(uuid.uuid4().int)[:14]
        self.hashed=recipient_hash(self.identity+'@example.test')
        self.row={'id':self.identity,'recipient_hash':self.hashed,'shopify_customer_id':self.cid,'test_send':False}
        self.token=self.cfg.unsubscribe_url(self.identity).split('token=')[1]
        self.receipt=patch.object(self.store,'receipt',return_value=self.row);self.receipt.start();self.addCleanup(self.receipt.stop)
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden'));self.guard.start();self.addCleanup(self.guard.stop)
        self.writer=Mock();self.writer.unsubscribe_only.return_value=True
    def state(self):return self.store.q('SELECT * FROM crm_suppressions WHERE recipient_hash=%s',(self.hashed,),True)
    def expire(self):self.store.q("UPDATE crm_suppressions SET shopify_sync_checked_at=now()-interval '6 minutes' WHERE recipient_hash=%s",(self.hashed,))
    def test_suppression_first_audit_once_and_repeat_safe(self):
        def write(**kwargs):
            self.assertTrue(self.store.suppressed(self.cid,self.hashed))
            self.assertEqual(self.state()['shopify_sync_state'],'PENDING')
            return True
        self.writer.unsubscribe_only.side_effect=write
        unsubscribe(self.store,self.cfg,self.token,self.writer)
        revision=self.store.state('cache_version')
        unsubscribe(self.store,self.cfg,self.token,self.writer)
        self.writer.unsubscribe_only.assert_called_once()
        self.assertEqual(self.state()['shopify_sync_state'],'SYNCED')
        self.assertEqual(self.store.state('cache_version'),revision)
        self.assertEqual(self.store.q("SELECT count(*) n FROM crm_marketing_events WHERE event_id=%s",('unsubscribe:'+self.identity,),True)['n'],1)
    def test_failure_pending_backoff_and_safe_retry(self):
        self.writer.unsubscribe_only.side_effect=RuntimeError('secret')
        unsubscribe(self.store,self.cfg,self.token,self.writer)
        self.assertTrue(self.store.suppressed(self.cid,self.hashed));self.assertEqual(self.state()['shopify_sync_state'],'PENDING')
        unsubscribe(self.store,self.cfg,self.token,self.writer);self.writer.unsubscribe_only.assert_called_once()
        self.expire();self.writer.unsubscribe_only.side_effect=None
        self.assertEqual(reconcile_opt_out(self.store,self.hashed,self.writer,approved=True),'SYNCED')
        self.assertTrue(self.store.suppressed(self.cid,self.hashed));self.assertEqual(self.state()['shopify_sync_attempts'],2)
    def test_worker_retries_pending_while_marketing_off(self):
        self.writer.unsubscribe_only.side_effect=RuntimeError('offline')
        unsubscribe(self.store,self.cfg,self.token,self.writer)
        self.expire();self.writer.unsubscribe_only.side_effect=None
        # Other suites leave synthetic pending opt-outs. Keep their backoff
        # active so the bounded five-row worker selects this test's recipient.
        self.store.q('UPDATE crm_suppressions SET shopify_sync_checked_at=now() WHERE recipient_hash<>%s',(self.hashed,))
        reconcile_pending(self.store,self.writer)
        self.assertFalse(self.cfg.enabled)
        self.assertEqual(self.state()['shopify_sync_state'],'SYNCED')

    def test_claim_prevents_concurrent_replay(self):
        def during_write(**kwargs):
            other=Mock()
            self.assertEqual(reconcile_opt_out(self.store,self.hashed,other,approved=True),'PENDING')
            other.unsubscribe_only.assert_not_called()
            return True
        self.writer.unsubscribe_only.side_effect=during_write
        unsubscribe(self.store,self.cfg,self.token,self.writer)
        self.writer.unsubscribe_only.assert_called_once()

    def test_client_config_failure_cannot_prevent_local_optout(self):
        with patch('crm_shopify.Shopify',side_effect=RuntimeError('credentials')):
            self.assertTrue(unsubscribe(self.store,self.cfg,self.token))
        self.assertTrue(self.store.suppressed(self.cid,self.hashed));self.assertEqual(self.state()['shopify_sync_error'],'writer_unavailable')
    def test_test_receipt_and_tampered_token_cannot_suppress(self):
        self.row['test_send']=True
        for token in [self.token,self.token+'x']:
            with self.assertRaises(ValueError):unsubscribe(self.store,self.cfg,token,self.writer)
        self.assertIsNone(self.state());self.writer.unsubscribe_only.assert_not_called()
    def test_market_and_global_counts_decrease_even_shopify_still_subscribed(self):
        for market,code in [('AU','AU'),('US','US'),('UK','GB')]:
            customer=profile(uuid.uuid4().int,code);self.row['shopify_customer_id']=customer['id'];self.row['recipient_hash']=recipient_hash(customer['email'])
            before=calculate(authority([customer]),self.store)
            self.writer.unsubscribe_only.side_effect=RuntimeError('offline')
            unsubscribe(self.store,self.cfg,self.token,self.writer)
            after=calculate(authority([customer]),self.store)
            self.assertEqual(before[market]['eligible'],1);self.assertEqual(before['Global']['eligible'],1)
            self.assertEqual(after[market]['eligible'],0);self.assertEqual(after['Global']['eligible'],0)
    def test_http_confirmation_and_one_click_off(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        with patch('crm_store.Store',return_value=self.store),patch('crm_resend.Config',return_value=self.cfg),patch('crm_shopify.Shopify',return_value=self.writer):
            self.assertEqual(client.get('/crm/unsubscribe',params={'token':self.token}).status_code,200)
            self.assertIsNone(self.state())
            response=client.post('/crm/unsubscribe',params={'token':self.token},data={'List-Unsubscribe':'One-Click'})
            self.assertEqual(response.status_code,200);self.assertIn("You&#x27;ve been unsubscribed",response.text)
            self.assertEqual(response.headers['referrer-policy'],'no-referrer')
            self.assertEqual(client.post('/crm/unsubscribe',params={'token':'bad'}).status_code,400)
            self.assertTrue(self.store.suppressed(self.cid,self.hashed))
