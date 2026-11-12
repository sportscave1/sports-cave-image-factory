from datetime import datetime,timezone
import json
import unittest
from unittest.mock import Mock,patch
import requests
from scripts import render_source_preflight as probe

class ReadOnlyPreflightTests(unittest.TestCase):
    def session(self,*payloads):
        session=Mock()
        session.request.side_effect=[Mock(status_code=200,headers={},json=Mock(return_value=p)) for p in payloads]
        return session

    def test_client_credentials_precedence_and_no_mutation(self):
        s=self.session({'access_token':'secret-new'}, {'data':{'currentAppInstallation':{'accessScopes':[{'handle':'read_orders'},{'handle':'read_all_orders'}]}}})
        env={'SHOPIFY_STORE_DOMAIN':'synthetic.myshopify.com','SHOPIFY_API_VERSION':'2026-04',
             'SHOPIFY_CLIENT_ID':'secret-id','SHOPIFY_CLIENT_SECRET':'secret-value','SHOPIFY_ADMIN_ACCESS_TOKEN':'secret-old'}
        result=probe.shopify(s,env)
        self.assertTrue(result['historical_order_scope_present'])
        self.assertEqual(s.request.call_count,2)
        self.assertEqual(s.request.call_args_list[1].kwargs['headers']['X-Shopify-Access-Token'],'secret-new')
        self.assertNotIn('mutation',s.request.call_args_list[1].kwargs['json']['query'])
        for call in s.request.call_args_list:
            self.assertFalse(call.kwargs['allow_redirects'])
        self.assertNotIn('secret',json.dumps(result))

    def test_existing_admin_token_and_missing_historical_scope(self):
        s=self.session({'data':{'currentAppInstallation':{'accessScopes':[{'handle':'read_orders'}]}}})
        result=probe.shopify(s,{'SHOPIFY_STORE_DOMAIN':'synthetic.myshopify.com','SHOPIFY_API_VERSION':'2026-04','SHOPIFY_ADMIN_ACCESS_TOKEN':'secret'})
        self.assertFalse(result['historical_order_scope_present']);self.assertEqual(s.request.call_count,1)

    def test_meta_account_and_single_day_sample_are_get_only(self):
        s=self.session({'account_id':'123','currency':'AUD','timezone_name':'Australia/Sydney'},
                       {'data':[{'account_id':'123','date_start':'2026-11-05','date_stop':'2026-11-05'}],'paging':{'next':'never-follow'}})
        result=probe.meta(s,{'META_AD_ACCOUNT_ID':'act_123','META_ACCESS_TOKEN':'secret','META_API_VERSION':'v26.0'},datetime(2026,11,6,tzinfo=timezone.utc))
        self.assertEqual(result['status'],'read_succeeded');self.assertFalse(result['complete_report'])
        self.assertTrue(result['has_more']);self.assertEqual(s.request.call_count,2)
        self.assertTrue(all(c.args[0]=='GET' for c in s.request.call_args_list))

    def test_errors_and_transports_do_not_leak_or_retry(self):
        s=self.session({'error':{'message':'Bearer secret-value', 'code':190,'error_subcode':463,'fbtrace_id':'trace123'}})
        data,result=probe.call(s,'GET','https://graph.facebook.com/v26.0/act_123',params={'access_token':'secret-value'})
        self.assertIsNone(data);self.assertEqual(result['error_code'],190)
        self.assertNotIn('secret',json.dumps(result));self.assertEqual(s.request.call_count,1)
        s.request.side_effect=requests.ConnectionError('access_token=secret-value')
        self.assertEqual(probe.call(s,'GET','https://graph.facebook.com/')[1],{'status':'transport_failed'})

    def test_invalid_hosts_and_versions_stop_before_network(self):
        s=Mock()
        self.assertIn('configuration',probe.shopify(s,{'SHOPIFY_STORE_DOMAIN':'evil.test','SHOPIFY_API_VERSION':'secret'})['status'])
        self.assertIsNone(probe.shopify(s,{'SHOPIFY_API_VERSION':'secret'})['requested_api_version'])
        s.request.assert_not_called()

    def test_default_meta_version_read_without_import(self):
        with patch.object(probe.Path,'read_text',return_value="DEFAULT_META_API_VERSION = 'v26.0'\nraise Exception('must not execute')"):
            self.assertEqual(probe.deployed_meta_version(),'v26.0')
