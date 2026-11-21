"""Fictional recipients and mocked HTTP only; never send or unsubscribe anyone."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_http import router
from crm_unsubscribe_headers import configured,headers
from crm_resend import Resend
from crm_campaign_dispatch import payload
from tests.test_crm import config


class OneClickTests(TestCase):
    def test_signed_header_is_recipient_specific_and_body_link_is_not_rewritten(self):
        cfg=config();identities=[str(uuid4()),str(uuid4())];native='https://shop.example.test/unsubscribe?token=native'
        values=[headers(cfg,i,native) for i in identities]
        self.assertNotEqual(values[0],values[1])
        for identity,value in zip(identities,values):
            self.assertEqual(value['List-Unsubscribe-Post'],'List-Unsubscribe=One-Click')
            token=value['List-Unsubscribe'][1:-1].split('token=')[1]
            self.assertEqual(cfg.verify_token(token),identity)
        message={'subject':'Fixture','html':'<a href="'+native+'">Unsubscribe</a>','text':native,'unsubscribe_url':native,'unsubscribe_headers':values[0]}
        session=Mock();session.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid4())})
        with patch('crm_resend.pace'):Resend(cfg,session).send('collector@example.test',message,'fixture-key')
        mail=session.post.call_args.kwargs['json']
        self.assertEqual(mail['headers'],values[0]);self.assertEqual(mail['html'],message['html'])

    def test_native_only_fallback_and_test_link_never_advertise_unsupported_post(self):
        cfg=config();native='https://shop.example.test/unsubscribe?token=native';identity=str(uuid4())
        self.assertNotIn('List-Unsubscribe-Post',headers(cfg,identity,native,test=True))
        cfg.secret='';self.assertFalse(configured(cfg))
        self.assertEqual(headers(cfg,identity,native),{'List-Unsubscribe':'<'+native+'>'})
        cfg.secret='fixture-only-secret'*3;cfg.public_base='https://hooks.example.test?query=not-a-route'
        self.assertFalse(configured(cfg));self.assertNotIn('List-Unsubscribe-Post',headers(cfg,identity,native))
        for bad in ('https://good.example/\r\nBcc:bad','http://unsafe.example/u','https://good.example/u>'):
            with self.assertRaises(ValueError):headers(cfg,identity,bad)

    def test_get_is_scanner_safe_and_rfc8058_post_uses_existing_suppression_handler(self):
        cfg=config();token=cfg.unsubscribe_url(str(uuid4())).split('token=')[1]
        app=FastAPI();app.include_router(router);client=TestClient(app)
        with patch('crm_resend.Config',return_value=cfg),patch('crm_store.Store') as store,patch('crm_webhooks.unsubscribe',return_value=True) as optout:
            self.assertEqual(client.get('/crm/unsubscribe',params={'token':token}).status_code,200)
            store.assert_not_called();optout.assert_not_called()
            result=client.post('/crm/unsubscribe',params={'token':token},data={'List-Unsubscribe':'One-Click'})
            self.assertEqual(result.status_code,200);optout.assert_called_once()
            self.assertEqual(optout.call_args.args[2],token)
            self.assertEqual(result.headers['cache-control'],'no-store')

    def test_new_batch_headers_are_frozen_and_old_batch_payload_stays_identical(self):
        cfg=config();native='https://shop.example.test/unsubscribe?token=native'
        common={'subject':'Fixture','html':'<p>Fixture</p>','text':'Fixture'}
        old={'address':'collector@example.test','unsubscribe_url':native}
        before=payload(common,old,cfg)
        self.assertEqual(before['headers'],{'List-Unsubscribe':'<'+native+'>'})
        new={**old,'unsubscribe_headers':headers(cfg,str(uuid4()),native)}
        frozen=deepcopy(new);first=payload(common,new,cfg)
        cfg.secret='rotated-fixture-only'*3
        self.assertEqual(payload(common,frozen,cfg),first)
        self.assertEqual(payload(common,old,cfg),before)
        self.assertEqual(new['unsubscribe_url'],native)

    def test_engine_advertises_signed_post_while_keeping_shopify_body_unsubscribe(self):
        from tests.test_crm_native_unsubscribe import NativeUnsubscribeTests,ENV
        from crm_native_unsubscribe import native_unsubscribe_url
        case=NativeUnsubscribeTests()
        try:
            with patch.dict(ENV,{'CRM_UNSUBSCRIBE_SECRET':'fixture-only-secret'*3}):
                customer=case.customer();store,shop,delivery,row=case.worker(customer)
            message=delivery.send.call_args.args[1]
            self.assertTrue(message['unsubscribe_one_click'])
            self.assertEqual(message['unsubscribe_url'],native_unsubscribe_url(customer))
            self.assertIn('/crm/unsubscribe?token=',message['unsubscribe_headers']['List-Unsubscribe'])
        finally:case.doCleanups()
