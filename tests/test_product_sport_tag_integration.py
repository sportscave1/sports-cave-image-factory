"""Real prompt builders and webhook processor with in-memory Shopify/ledger."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import patch

import app
import shopify_sync
import supabase_backend as backend
from product_sport_tags import START, TAGS, strip_prompt_rules
from tests.test_product_sport_tags import FakeShopify, product
from tests.test_product_webhook_restoration import MemoryDatabase
from tests.test_product_activation_sync import collector


class PromptIntegrationTests(unittest.TestCase):
    def test_all_three_actual_prompts_preserve_existing_content(self):
        for existing, mode in [(False, 'DRAFT'), (False, 'LIVE'), (True, 'DRAFT')]:
            metadata = {'product_name': 'Peter Brock Tribute'}
            with self.subTest(existing=existing, mode=mode):
                with patch('product_sport_tags.apply_prompt_rules', side_effect=lambda text, metadata: text):
                    baseline = app.get_product_upload_prompt(metadata, update_existing=existing, publication_mode=mode)
                result = app.get_product_upload_prompt(metadata, update_existing=existing, publication_mode=mode)
                self.assertEqual(strip_prompt_rules(result), baseline)
                self.assertEqual(result.count(START), 1)
                self.assertIn(TAGS['V8 Supercars'], result)
                self.assertIn('SC_SPORT_MOTORSPORT', result)
                again = app.apply_product_upload_prompt_updates(result, metadata, update_existing=existing, publication_mode=mode)
                self.assertEqual(again, result)


class WebhookIntegrationTests(unittest.TestCase):
    def test_all_nine_disciplines_add_only_and_retry(self):
        from product_sport_tags import MOTOR_CHILDREN
        for discipline in sorted(MOTOR_CHILDREN):
            with self.subTest(discipline=discipline):
                self.api=FakeShopify(product(discipline+' Artwork',tags=['collector']))
                self.assertEqual(self.deliver('products/update')['sport_tagging']['status'],'verified')
                self.assertEqual(self.deliver('products/update')['sport_tagging']['status'],'verified')
                self.assertEqual(self.api.adds,1)
                self.assertIn(TAGS[discipline],self.api.product['tags'])
                self.assertIn('collector',self.api.product['tags'])

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.db = MemoryDatabase()
        self.api = FakeShopify(product('Peter Brock Tribute'))
        self.stack.enter_context(patch.object(backend, 'connect', self.db.connect))
        self.stack.enter_context(patch.object(backend, '_set_webhook_app_setting'))
        self.status = self.stack.enter_context(patch.object(backend, '_update_webhook_event_status'))
        self.stack.enter_context(patch.object(backend, '_webhook_log'))
        self.fetch = self.stack.enter_context(patch.object(shopify_sync, 'fetch_product_by_shopify_id',
            return_value=collector(shopify_product_id='gid://shopify/Product/123', legacy_resource_id='123', title='Peter Brock Tribute')))
        self.stack.enter_context(patch.object(shopify_sync, 'sync_complete_product_edition_metafields'))
        self.stack.enter_context(patch.object(shopify_sync, 'graphql_request',
            side_effect=lambda query, variables, **kw: (self.api(query, variables), '2026-04')))

    def deliver(self, topic='products/create'):
        return backend.process_product_create_webhook({'id': 123, 'title': 'STALE incorrect snapshot'},
                                                     'test-tag-event', topic, claim_event=False)

    def test_draft_create_then_existing_active_update_no_edition_reset(self):
        self.fetch.return_value['status'] = 'DRAFT'
        self.assertEqual(self.deliver()['sport_tagging']['status'], 'verified')
        self.assertEqual(self.db.rows, [])
        self.fetch.return_value['status'] = 'ACTIVE'
        self.assertEqual(self.deliver('products/update')['sport_tagging']['status'], 'verified')
        self.assertEqual(len(self.db.rows), 1)
        self.db.rows[0].update(next_edition_number=42, sold_count=17, remaining_count=58)
        before = deepcopy((self.db.rows, self.db.runs, self.db.history))
        self.deliver('products/update')
        self.assertEqual((self.db.rows, self.db.runs, self.db.history), before)
        self.assertEqual(self.api.adds, 1)

    def test_conflict_persisted_for_review_but_does_not_break_edition_registration(self):
        self.api.product = product('Ayrton Senna', ['NBA Wall Art'])
        result = self.deliver()
        self.assertEqual(result['sport_tagging']['status'], 'review_required')
        self.assertEqual(result['status'], 'processed_with_warnings')
        self.assertEqual(self.api.adds, 0)
        self.assertEqual(len(self.db.rows), 1)
        self.assertIn('Sport classification review required', self.status.call_args.kwargs['error_message'])

    def test_failure_marks_receipt_failed_and_retry_resumes_same_product(self):
        self.api.readback_fail = True
        with self.assertRaisesRegex(RuntimeError, 'SPORT TAGGING UNVERIFIED'): self.deliver()
        self.assertEqual(len(self.db.rows), 1, 'Tagging failure must not prevent Edition Ops registration')
        self.assertEqual(self.status.call_args.args[1], 'failed')
        self.api.readback_fail = False
        self.assertEqual(self.deliver()['sport_tagging']['status'], 'verified')
        self.assertEqual(self.api.adds, 1)

    def test_duplicate_receipt_skips_tag_mutation(self):
        with patch.object(backend, 'claim_product_create_webhook_receipt', return_value={'duplicate': True}):
            result = backend.process_product_create_webhook({'id': 123}, 'same-id', 'products/update')
        self.assertTrue(result['duplicate'])
        self.assertEqual(self.api.calls, [])


if __name__ == '__main__': unittest.main()
