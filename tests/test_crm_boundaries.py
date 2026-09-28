"""Offline HTTP, provider and audience boundaries; no production credentials."""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_http import router
from crm_resend import Resend,ProviderUnavailable
from crm_shopify import Shopify,gid
from crm_audience import count_page
from crm_logic import rule,recipient_hash
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm import config


class HttpTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(router);self.client=TestClient(app)
        self.env=patch.dict(os.environ,{'SHOPIFY_WEBHOOK_SECRET':'synthetic-secret','SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'},clear=True);self.env.start()
        self.addCleanup(self.env.stop)
        self.store=Mock();self.patch=patch('crm_store.Store',return_value=self.store);self.patch.start();self.addCleanup(self.patch.stop)
    def headers(self,raw):
        return {'x-shopify-hmac-sha256':base64.b64encode(hmac.new(b'synthetic-secret',raw,hashlib.sha256).digest()).decode(),
            'x-shopify-topic':'customers/update','x-shopify-webhook-id':'fixture-event','x-shopify-shop-domain':'fixture.myshopify.com'}
    def test_hmac_raw_bytes_no_profile_persistence(self):
        raw=b'{"id":1,"email":"private@example.test","note":"private content"}'
        self.assertEqual(self.client.post('/webhooks/shopify/crm',content=raw,headers=self.headers(raw)).status_code,200)
        self.assertNotIn('private',str(self.store.method_calls))
        self.assertEqual(self.client.post('/webhooks/shopify/crm',content=raw+b' ',headers=self.headers(raw)).status_code,401)
    def test_wrong_shop_and_large_body(self):
        raw=b'{"id":1}';headers=self.headers(raw);headers['x-shopify-shop-domain']='other.myshopify.com'
        self.assertEqual(self.client.post('/webhooks/shopify/crm',content=raw,headers=headers).status_code,403)
        self.assertEqual(self.client.post('/webhooks/shopify/crm',content=b'x'*(2*1024*1024+1)).status_code,400)
        self.store.webhook.assert_not_called()
    def test_database_failure_generic_retryable(self):
        self.store.webhook.side_effect=RuntimeError('private-secret');raw=b'{"id":1}'
        response=self.client.post('/webhooks/shopify/crm',content=raw,headers=self.headers(raw))
        self.assertEqual(response.status_code,503);self.assertNotIn('private',response.text)
    def test_resend_svix_endpoint(self):
        raw=b'{"type":"email.delivered","created_at":"2026-09-28T01:00:00Z","data":{"email_id":"f63b27ee-bf05-465c-9b8d-20cd9fbe3574"}}';timestamp=str(int(time.time()));secret=b'k'*32
        signature=base64.b64encode(hmac.new(secret,b'event.'+timestamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
        with patch.dict(os.environ,{'CRM_RESEND_WEBHOOK_SECRET':'whsec_'+base64.b64encode(secret).decode()}),patch('crm_workspace_store.WorkspaceRecords',return_value=self.store):
            headers={'svix-id':'event','svix-timestamp':timestamp,'svix-signature':'v1,'+signature}
            self.store.q.return_value=None
            self.assertEqual(self.client.post('/webhooks/resend/crm',content=raw,headers=headers).status_code,200)
            self.assertEqual(self.client.post('/webhooks/resend/crm',content=raw+b' ',headers=headers).status_code,401)
    def test_unsubscribe_get_does_not_mutate_post_suppresses_without_shopify(self):
        import uuid
        cfg=config();identity=str(uuid.uuid4());token=cfg.unsubscribe_url(identity).split('token=')[1]
        self.store.receipt.return_value={'recipient_hash':recipient_hash('old@example.test'),'shopify_customer_id':gid(1),'test_recipient':None}
        with patch('crm_resend.Config',return_value=cfg),patch('crm_shopify.Shopify') as shop:
            self.assertEqual(self.client.get('/crm/unsubscribe',params={'token':token}).status_code,200)
            self.store.suppress.assert_not_called()
            self.assertEqual(self.client.post('/crm/unsubscribe',params={'token':token}).status_code,200)
            self.store.suppress.assert_called_once();shop.return_value.customer.assert_not_called()


class DeliveryTests(unittest.TestCase):
    def test_provider_headers_and_single_submission(self):
        session=Mock();session.post.return_value=Mock(status_code=200,json=lambda:{'id':'receipt'})
        provider=Resend(config(),session)
        result=provider.send('recipient@example.test',{'subject':'Subject','html':'<p>Preview</p>','text':'Preview','unsubscribe_url':'https://example.test/u'},'stable-operation')
        self.assertEqual(result,'receipt');session.post.assert_called_once()
        kwargs=session.post.call_args.kwargs
        self.assertEqual(kwargs['headers']['Idempotency-Key'],'stable-operation')
        self.assertIn('List-Unsubscribe-Post',kwargs['json']['headers'])
        self.assertEqual(kwargs['json']['text'],'Preview')
    def test_suppression_failure_closed(self):
        session=Mock();session.request.return_value=Mock(status_code=403,json=lambda:{'message':'private'})
        with self.assertRaises(ProviderUnavailable) as result:Resend(config(),session).suppressed('a@example.test')
        self.assertNotIn('private',str(result.exception))
    def test_old_unsubscribe_recipient_matches_hash(self):
        session=Mock();session.request.return_value=Mock(status_code=200,json=lambda:{'to':['old@example.test'],'html':'private-body'})
        self.assertEqual(Resend(config(),session).recipient_for('receipt',recipient_hash('old@example.test')),'old@example.test')
        self.assertIsNone(Resend(config(),session).recipient_for('receipt',recipient_hash('different@example.test')))


class AudienceTests(unittest.TestCase):
    def test_paginated_count_no_membership_write(self):
        wire=ShopifyFixture();shop=Shopify(wire);store=Mock();store.suppressed.return_value=False
        source=('Sports Cave',{'rules':rule('consent','SUBSCRIBED')})
        state=count_page(shop,store,source);self.assertFalse(state['complete']);self.assertEqual(state['scanned'],50)
        state=count_page(shop,store,source,state);self.assertTrue(state['complete']);self.assertEqual(state['eligible'],37)
        self.assertNotIn('@',str(state));self.assertTrue(all(c[0]=='suppressed' for c in store.method_calls))
    def test_duplicate_addresses_and_suppression_excluded(self):
        wire=ShopifyFixture(5);wire.customers[3]['email']=wire.customers[0]['email'];store=Mock();store.suppressed.return_value=False
        state=count_page(Shopify(wire),store,('Shopify',{'id':gid(1,'Segment')}));self.assertEqual(state['eligible'],2)


if __name__=='__main__':unittest.main()
