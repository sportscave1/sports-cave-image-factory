"""Receiver and OS contract fixtures. No Shopify mutations or email transport."""
import json
import os
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from starlette.routing import NoMatchFound
from crm_shopify_webhook_config import (
    CANONICAL_BASE, callbacks, ReceiverReadinessError, receiver_readiness,
    receiver_callback_status,
)


def report(**changes):
    return dict(service='sports-cave-os-webhooks', receiver_reachable=True,
                base_url=CANONICAL_BASE, callbacks=callbacks({'RENDER':'true'}),
                api_version='2026-04', routes_ready=True, hmac_status='CONFIGURED', **changes)


class ReadinessContractTests(unittest.TestCase):
    def read(self, body):
        wire=Mock(status_code=200, content=b'{}', json=lambda:body)
        with patch('requests.get',return_value=wire):
            return receiver_readiness({'RENDER':'true'})

    def test_lazy_included_router_without_path_is_supported(self):
        import webhook_server as server
        # Reproduce production's route container: no .path, public lookup works.
        class IncludedRouter:
            def __init__(self, routes):self.routes=routes
            def url_path_for(self,name,**params):
                for route in self.routes:
                    try:return route.url_path_for(name,**params)
                    except NoMatchFound:pass
                raise NoMatchFound(name,params)
        routes=server.app.router.routes
        with patch.object(server.app.router,'routes',[IncludedRouter(routes)]),patch.dict(os.environ,{'RENDER':'true'},clear=True):
            self.assertFalse(hasattr(server.app.routes[0],'path'))
            result=json.loads(server.shopify_receiver_readiness().body)
            self.assertTrue(result['routes_ready'])
            self.assertTrue(result['receiver_reachable'])

    def test_real_receiver_contract_and_client_agree(self):
        import webhook_server as server
        with patch.dict(os.environ,{'RENDER':'true','SHOPIFY_WEBHOOK_SECRET':'shpss_fixture'},clear=True):
            response=TestClient(server.app).get('/webhooks/shopify/readiness')
            self.assertEqual(response.status_code,200)
            self.assertEqual(receiver_callback_status(self.read(response.json()),{'RENDER':'true'}),'VERIFIED')

    def test_missing_registered_route_reports_configuration_failure(self):
        import webhook_server as server
        with patch.object(server.app,'url_path_for',side_effect=NoMatchFound('missing',{})),patch.dict(os.environ,{'RENDER':'true'},clear=True):
            result=json.loads(server.shopify_receiver_readiness().body)
            self.assertFalse(result['routes_ready'])
            self.assertIn('routes missing',receiver_callback_status(self.read(result),{'RENDER':'true'}))

    def test_invalid_receiver_base_is_json_not_server_error(self):
        import webhook_server as server
        for base in ('', 'https://[broken', 'http://receiver.example'):
            with patch.dict(os.environ,{'SPORTS_CAVE_WEBHOOK_BASE_URL':base},clear=True):
                result=json.loads(server.shopify_receiver_readiness().body)
                self.assertEqual(result['base_url'],'')
                self.assertIn('INVALID HTTPS',receiver_callback_status(self.read(result),{'RENDER':'true'}))

    def test_transport_failures_have_safe_specific_reasons(self):
        for exception,reason in ((requests.Timeout('private credentials'),'timed out'),
                                 (requests.ConnectionError('private credentials'),'unreachable')):
            with self.subTest(reason=reason),patch('requests.get',side_effect=exception):
                with self.assertRaisesRegex(ReceiverReadinessError,reason) as caught:
                    receiver_readiness({'RENDER':'true'})
                self.assertNotIn('private',str(caught.exception))

    def test_http_error_body_is_never_exposed(self):
        for status in (302,401,404,500,503):
            with patch('requests.get',return_value=Mock(status_code=status,content=b'private body')):
                with self.assertRaisesRegex(ReceiverReadinessError,'HTTP '+str(status)) as caught:
                    receiver_readiness({'RENDER':'true'})
                self.assertNotIn('private',str(caught.exception))

    def test_invalid_json_has_safe_reason(self):
        with patch('requests.get',return_value=Mock(status_code=200,content=b'<html>',json=Mock(side_effect=ValueError('private body')))):
            with self.assertRaisesRegex(ReceiverReadinessError,'invalid JSON'):
                receiver_readiness({'RENDER':'true'})

    def test_malformed_contract_is_rejected(self):
        good=report()
        for change in ({'service':'other'}, {'callbacks':[]}, {'callbacks':{'crm':3,'paid':'ok'}},
                       {'routes_ready':'true'}, {'hmac_status':[]}, {'api_version':None},
                       {'base_url':None}, {'receiver_reachable':False}):
            with self.subTest(change=change),self.assertRaisesRegex(ReceiverReadinessError,'malformed'):
                self.read({**good,**change})
        for body in ([],None,'private body',{}):
            with self.assertRaises(ReceiverReadinessError):self.read(body)

    def test_config_failure_not_misreported_as_network_failure(self):
        for change,reason in (({'base_url':''},'INVALID HTTPS'),
                              ({'base_url':'https://wrong.example'},'base URL mismatch'),
                              ({'callbacks':{'crm':'wrong','paid':'wrong'}},'callback routes mismatch'),
                              ({'api_version':'2025-10'},'API version mismatch'),
                              ({'routes_ready':False},'routes missing')):
            parsed=self.read({**report(),**change})
            self.assertIn(reason,receiver_callback_status(parsed,{'RENDER':'true'}))

    def diagnostic(self,receiver=None,error=None,hooks=None):
        from crm_automation_capabilities import verify
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        if hooks is None:
            hooks=[{'topic':t,'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':CANONICAL_BASE+p}}
                   for t,p in (('ORDERS_CREATE','/webhooks/shopify/crm'),('ORDERS_PAID','/webhooks/shopify/orders-paid'))]
        with patch.dict(os.environ,{'RENDER':'true'},clear=True),patch('crm_tracking_health.subscriptions',return_value=hooks),patch('crm_shopify_webhook_config.receiver_readiness',return_value=receiver or report(),side_effect=error):
            return verify(CapabilitiesTests().shop(),Mock(),persist=False)

    def test_missing_checkout_topics_independent_of_readiness_failure(self):
        for error in (None,ReceiverReadinessError('Receiver HTTP 500')):
            result=self.diagnostic(error=error)
            for topic in ('CHECKOUTS_CREATE','CHECKOUTS_UPDATE'):
                self.assertEqual(result['checks'][topic],'MISSING')
                self.assertEqual(result['webhook_details'][topic]['subscriptions'],[])
            if error:self.assertIn('HTTP 500',result['checks']['Webhook HMAC'])
            else:
                self.assertEqual(result['checks']['ORDERS_CREATE'],'VERIFIED')
                self.assertEqual(result['checks']['ORDERS_PAID'],'VERIFIED')
            self.assertNotEqual(result['triggers']['abandoned'],'AVAILABLE')

    def test_diagnostic_exposes_safe_reason_and_stays_fail_closed(self):
        for message in ('Receiver HTTP 500','Receiver timed out','Receiver unreachable',
                        'Receiver returned invalid JSON','Receiver returned a malformed readiness report'):
            result=self.diagnostic(error=ReceiverReadinessError(message))
            self.assertIn(message,result['checks']['Webhook HMAC'])
            self.assertIn(message,result['checks']['Callback configuration'])
            self.assertFalse(result['webhook_hmac_configured'])

    def test_diagnostic_missing_secret_does_not_hide_valid_callback_configuration(self):
        result=self.diagnostic(receiver={**report(),'hmac_status':'MISSING'})
        self.assertEqual(result['checks']['Webhook HMAC'],'MISSING')
        self.assertEqual(result['checks']['Callback configuration'],'VERIFIED')
        self.assertFalse(result['webhook_hmac_configured'])

    def test_diagnostic_configuration_error_blocks_readiness(self):
        result=self.diagnostic(receiver={**report(),'api_version':'2025-10'})
        self.assertIn('API version mismatch',result['checks']['Callback configuration'])
        self.assertEqual(result['checks']['ORDERS_PAID'],'CALLBACK CONFIGURATION UNVERIFIED')

    def test_legacy_contract_compatible_during_rollout(self):
        legacy=report();legacy.pop('receiver_reachable')
        self.assertEqual(receiver_callback_status(self.read(legacy),{'RENDER':'true'}),'VERIFIED')

    def test_diagnostic_parses_real_client_failure_paths_without_uncaught_valueerror(self):
        from crm_automation_capabilities import verify
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        fixtures=[(Mock(status_code=500,content=b'Internal Server Error'),None,'HTTP 500'),
                  (Mock(status_code=200,content=b'html',json=Mock(side_effect=ValueError('private'))),None,'invalid JSON'),
                  (Mock(status_code=200,content=b'{}',json=lambda:[]),None,'malformed'),
                  (None,requests.Timeout('private'),'timed out'),
                  (None,requests.ConnectionError('private'),'unreachable')]
        for response,error,reason in fixtures:
            with self.subTest(reason=reason),patch.dict(os.environ,{'RENDER':'true'},clear=True),patch('crm_tracking_health.subscriptions',return_value=[]),patch('requests.get',return_value=response,side_effect=error):
                result=verify(CapabilitiesTests().shop(),Mock(),persist=False)
                self.assertIn(reason,result['checks']['Webhook HMAC'])
                self.assertNotIn('private',json.dumps(result))
                self.assertNotEqual(result['triggers']['abandoned'],'AVAILABLE')
