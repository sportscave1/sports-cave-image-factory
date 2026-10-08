"""Shopify transport boundary tests: mocks only, never live products."""
import unittest
from contextlib import nullcontext
from unittest.mock import patch
import edition_versions
import shopify_sync


class EditionVersionMirrorTests(unittest.TestCase):
    def test_sync_recovery_failure_does_not_stop_order_reconciliation(self):
        import supabase_backend
        import shopify_order_reconciliation_worker as worker
        with patch.object(supabase_backend,'is_configured',return_value=True), \
             patch.object(edition_versions,'resume_pending',side_effect=RuntimeError('Database unavailable')), \
             patch.object(supabase_backend,'shopify_order_reconciliation_lease',return_value=nullcontext(True)), \
             patch.object(supabase_backend,'sync_latest_paid_orders_to_supabase',return_value={'orders_synced':0}) as orders, \
             patch.object(worker,'_log'):
            self.assertEqual(worker.run_once(),{'orders_synced':0})
        orders.assert_called_once()

    def test_disclosure_preserves_html_and_only_updates_description(self):
        version = {'id':'release-id','edition_name':'Updated & revised','edition_total':100}
        original = '<p>Original product description</p>'
        requests = []
        def graphql(query, variables, **kwargs):
            requests.append(variables)
            if 'query Edition' in query:
                return {'product':{'id':'gid://shopify/Product/1','descriptionHtml':original}}, {}
            return {'productUpdate':{'product':variables['product'],'userErrors':[]}}, {}
        with patch.object(shopify_sync,'graphql_request',side_effect=graphql):
            edition_versions.ensure_disclosure('gid://shopify/Product/1',version)
        update=requests[1]['product']
        self.assertEqual(set(update),{'id','descriptionHtml'})
        self.assertTrue(update['descriptionHtml'].startswith(original))
        self.assertIn('Updated &amp; revised',update['descriptionHtml'])
        self.assertIn('separate artwork release release-id',update['descriptionHtml'])

    def test_retry_does_not_append_another_disclosure(self):
        version={'id':'release-id','edition_name':'Revised','edition_total':100}
        with patch.object(shopify_sync,'graphql_request',return_value=(
            {'product':{'descriptionHtml':'<p data-sports-cave-release="release-id">Release</p>'}},{}
        )) as request:
            edition_versions.ensure_disclosure('gid://shopify/Product/1',version)
        self.assertEqual(request.call_count,1)

    def test_compare_digest_sent_and_readback_required(self):
        inputs=[{'ownerId':'gid://shopify/Product/1','namespace':'sports_cave','key':'edition_label','type':'single_line_text_field','value':'release-id'}]
        fields=[{'namespace':'sports_cave','key':'edition_label','value':'old','compareDigest':'old-digest'}]
        with patch.object(shopify_sync,'complete_product_edition_metafield_inputs',return_value=inputs), \
             patch.object(shopify_sync,'graphql_request',return_value=({'product':{'metafields':{'nodes':fields}}},{})), \
             patch.object(shopify_sync,'metafields_set',return_value={'metafields':inputs}) as write, \
             patch.object(shopify_sync,'fetch_metafields',return_value={'metafields':inputs}):
            shopify_sync.sync_complete_product_edition_metafields({},verify=True,compare=True)
        self.assertEqual(write.call_args.args[0][0]['compareDigest'],'old-digest')

    def test_missing_digest_fails_before_writing(self):
        inputs=[{'ownerId':'gid://shopify/Product/1','namespace':'sports_cave','key':'edition_label'}]
        with patch.object(shopify_sync,'complete_product_edition_metafield_inputs',return_value=inputs), \
             patch.object(shopify_sync,'graphql_request',return_value=({'product':{'metafields':{'nodes':inputs}}},{})), \
             patch.object(shopify_sync,'metafields_set') as write:
            with self.assertRaisesRegex(shopify_sync.ShopifyAPIError,'digest'):
                shopify_sync.sync_complete_product_edition_metafields({},compare=True)
        write.assert_not_called()
