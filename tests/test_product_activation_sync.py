"""DRAFT -> ACTIVE registration and initial storefront mirror, with no live I/O."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import io
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import shopify_sync
import supabase_backend as backend
import webhook_server
from scripts import reconcile_missing_edition_products as reconciliation
from tests.test_product_webhook_restoration import MemoryDatabase


def collector(**changes):
    return {
        "shopify_product_id": "gid://shopify/Product/987", "legacy_resource_id": "987",
        "handle": "new-art", "title": "New Art", "status": "ACTIVE",
        "vendor": "Sports Cave", "product_type": "Framed Art", "tags": ["Collector Series"],
        "online_store_url": "https://example.com/products/new-art", "metafields": [],
        "_edition_registration_canonical": True, **changes,
    }


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(backend, "connect", self.db.connect))
        self.log = self.stack.enter_context(patch.object(backend, "_webhook_log"))
        self.status = self.stack.enter_context(patch.object(backend, "_update_webhook_event_status"))
        self.stack.enter_context(patch.object(backend, "_set_webhook_app_setting"))
        self.fetch = self.stack.enter_context(patch.object(shopify_sync, "fetch_product_by_shopify_id", return_value=collector()))
        self.mirror = self.stack.enter_context(patch.object(shopify_sync, "sync_complete_product_edition_metafields"))
        self.stack.enter_context(patch.object(backend, "_ensure_active_edition_runs_for_products", side_effect=AssertionError("No global run rewrite")))

    def webhook(self, payload=None, topic="products/update"):
        return backend.process_product_create_webhook(payload or {"id": 987}, "event-987", topic, claim_event=False)

    def test_draft_update_then_active_uses_current_state(self):
        self.fetch.return_value = collector(status="DRAFT", online_store_url="", tags=[])
        self.webhook({"id": 987, "status": "active"})
        self.assertEqual(self.db.rows, [])
        self.mirror.assert_not_called()
        self.fetch.return_value = collector(tags=[])
        self.webhook({"id": 987, "status": "draft"})
        self.assertEqual(self.db.rows[0]["next_edition_number"], 1)
        self.mirror.assert_called_once()

    def test_sparse_payload_refetches_canonical_info_before_registration(self):
        self.webhook()
        self.fetch.assert_called_once_with("gid://shopify/Product/987", config=None)
        self.assertEqual(len(self.db.rows), 1)

    def test_duplicate_and_rapid_webhooks_mirror_once_without_reset(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.webhook(), range(8)))
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(len(self.db.runs), 1)
        self.assertEqual(self.db.rows[0]["next_edition_number"], 1)
        self.mirror.assert_called_once()

    def test_existing_counts_override_enabled_and_history_preserved(self):
        self.webhook()
        self.db.rows[0].update(next_edition_number=53, sold_count=19, remaining_count=72,
                               edition_total=125, active=False, is_active=False,
                               allow_counter_history_override=True, edition_status="Archived")
        self.db.history = [{"edition_number": 52, "certificate_id": "cert-52"}]
        before = deepcopy((self.db.rows, self.db.runs, self.db.history))
        self.webhook()
        self.assertEqual((self.db.rows, self.db.runs, self.db.history), before)
        self.mirror.assert_called_once()  # Only the first, genuinely new registration.

    def test_active_non_wall_art_apparel_internal_and_private_are_ignored(self):
        for changes in ({"product_type": "Mug"}, {"product_type": "Apparel"},
                        {"tags": ["Collector Series", "internal"]}, {"tags": ["Collector Series", "private"]},
                        {"handle": "framed-collector-certificate"}, {"vendor": "Other"}):
            with self.subTest(changes=changes):
                self.fetch.return_value = collector(**changes)
                self.webhook()
                self.assertEqual(self.db.rows, [])
        self.mirror.assert_not_called()

    def test_collection_order_is_irrelevant_and_publication_retries(self):
        self.fetch.return_value = collector(collections=[], online_store_url="")
        with self.assertRaisesRegex(RuntimeError, "publication_pending"):
            self.webhook()
        self.assertEqual(self.db.rows, [])
        self.fetch.return_value = collector(collections=[])
        self.webhook()
        self.assertEqual(len(self.db.rows), 1)

    def test_missing_collector_tags_registers_after_active_refetch(self):
        self.fetch.return_value = collector(tags=[])
        self.webhook()
        self.assertEqual(len(self.db.rows), 1)

    def test_new_mirror_satisfies_live_variant_picker_missing_metadata_guard(self):
        self.webhook()
        payload = self.mirror.call_args.args[0]
        fields = {m["key"]: m["value"] for m in shopify_sync.complete_product_edition_metafield_inputs(payload)}
        # Live variant-picker.liquid marks a run archived if enabled/total are
        # missing, or both remaining/next are missing, or next exceeds total.
        self.assertEqual(fields["edition_enabled"], "true")
        self.assertEqual(fields["edition_total"], "100")
        self.assertEqual(fields["edition_next_number"], "1")
        self.assertEqual(fields["edition_remaining"], "100")
        self.assertEqual(fields["edition_sold_count"], "0")
        self.assertEqual(self.db.rows[0]["metafields_sync_status"], "Synced")

    def test_historical_mirror_without_ledger_refuses_new_initialization(self):
        for key, value in (("edition_archived", "true"), ("edition_enabled", "false"),
                           ("edition_status", "Sold Out Archive"), ("edition_next_number", "53"),
                           ("edition_sold", "2"), ("edition_remaining", "0"),
                           ("edition_remaining", "47"), ("edition_total", "125")):
            with self.subTest(key=key):
                self.fetch.return_value = collector(metafields=[{"namespace": "sports_cave", "key": key, "value": value}])
                with self.assertRaises(RuntimeError):
                    self.webhook()
                self.assertEqual(self.db.rows, [])
        self.mirror.assert_not_called()

    def test_mirror_failure_resumes_using_current_ledger_without_reset(self):
        self.mirror.side_effect = RuntimeError("simulated Shopify outage")
        with self.assertRaisesRegex(RuntimeError, "retryable"):
            self.webhook()
        self.assertEqual(self.db.rows[0]["metafields_sync_status"], "Pending automatic mirror")
        self.db.rows[0].update(next_edition_number=53, sold_count=17, remaining_count=63,
                               edition_total=125)
        self.mirror.side_effect = None
        self.webhook()
        payload = self.mirror.call_args.args[0]
        self.assertEqual((payload["edition_next_number"], payload["edition_sold_count"], payload["edition_remaining"]), (53, 17, 63))
        self.assertTrue(payload["edition_enabled"])
        self.assertEqual(self.db.rows[0]["next_edition_number"], 53)

    def test_product_closed_while_initial_mirror_pending_is_never_reopened(self):
        self.mirror.side_effect = RuntimeError("simulated outage")
        with self.assertRaises(RuntimeError):
            self.webhook()
        self.db.rows[0].update(active=False, is_active=False, edition_status="Archived")
        before = deepcopy(self.db.rows)
        self.mirror.reset_mock(side_effect=True)
        self.webhook()
        self.assertEqual(self.db.rows, before)
        self.mirror.assert_not_called()

    def test_manual_after_webhook_uses_shared_service_and_no_mirror_repeat(self):
        with patch.object(backend, "register_shopify_products_for_edition_ops", wraps=backend.register_shopify_products_for_edition_ops) as shared:
            self.webhook()
            self.db.rows[0]["next_edition_number"] = 53
            with patch.object(backend, "_start_new_product_discovery", return_value=(deepcopy(self.db.rows), {})), patch.object(
                shopify_sync, "fetch_newest_products_for_edition_ops", return_value={"products": [collector()], "has_next_page": False}
            ), patch.object(backend, "_finish_new_product_discovery_state"):
                backend.sync_new_shopify_products_to_edition_ops(config={"configured": True})
            self.assertEqual(shared.call_count, 2)
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(self.db.rows[0]["next_edition_number"], 53)
        self.mirror.assert_called_once()

    def test_missing_only_reconciliation_leaves_existing_metadata_untouched(self):
        self.webhook()
        before = deepcopy(self.db.rows)
        backend.register_shopify_products_for_edition_ops([collector(title="New title")], missing_only=True)
        self.assertEqual(self.db.rows, before)

    def test_database_failure_still_logs_when_diagnostics_database_is_down(self):
        self.status.side_effect = RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.webhook()
        events = [call.args[0] for call in self.log.call_args_list]
        self.assertIn("webhook_product_processing_failed", events)
        self.assertEqual(self.db.rows, [])
        self.mirror.assert_not_called()

    def test_http_sparse_payload_and_failed_database_returns_retryable_500(self):
        with patch.object(webhook_server, "verify_shopify_webhook_hmac", return_value={"ok": True}), patch.object(
            backend, "is_configured", return_value=True
        ), patch.object(backend, "claim_product_create_webhook_receipt", return_value={"webhook_id": "test"}):
            client = TestClient(webhook_server.app)
            self.assertEqual(client.post("/webhooks/shopify/products-update", json={"id": 987}).status_code, 200)
            self.status.side_effect = RuntimeError("database unavailable")
            self.assertEqual(client.post("/webhooks/shopify/products-update", json={"id": 987}).status_code, 500)


class RecoveryPreviewTests(unittest.TestCase):
    def test_cli_default_does_not_apply(self):
        with patch.object(shopify_sync, "get_config", return_value={}), patch.object(shopify_sync, "validate_config"), patch.object(
            reconciliation, "preview", return_value=([{"action": "would_create"}], [collector()])
        ), patch.object(backend, "register_shopify_products_for_edition_ops") as register, patch("sys.stdout", new=io.StringIO()):
            reconciliation.main([])
            register.assert_not_called()
            reconciliation.main(["--apply"])
            register.assert_called_once()
            self.assertTrue(register.call_args.kwargs["missing_only"])
            self.assertEqual(register.call_args.args[0], [{"shopify_product_id": collector()["shopify_product_id"]}])

    def test_preview_is_read_only_and_finds_old_activated_product(self):
        cur = Mock()
        cur.__enter__ = Mock(return_value=cur)
        cur.__exit__ = Mock(return_value=False)
        cur.fetchall.return_value = []
        cur.fetchone.return_value = {"has_history": False}
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        conn.cursor.return_value = cur
        with patch.object(backend, "connect", return_value=conn), patch.object(
            shopify_sync, "fetch_edition_ops_active_products", return_value={"complete": True, "products": [collector(created_at="2020-01-01")]}
        ) as fetch, patch.object(shopify_sync, "fetch_product_by_shopify_id", return_value=collector()), patch.object(
            backend, "register_shopify_products_for_edition_ops", side_effect=AssertionError("preview cannot write")
        ):
            report, candidates = reconciliation.preview({})
        self.assertEqual(report[0]["action"], "would_create")
        self.assertEqual(len(candidates), 1)
        self.assertIsNone(fetch.call_args.kwargs["max_products"])
        self.assertEqual(cur.execute.call_args_list[0].args[0], "SET TRANSACTION READ ONLY")
        for call in cur.execute.call_args_list[1:]:
            self.assertTrue(call.args[0].strip().startswith("SELECT"))
        conn.commit.assert_not_called()


class CanonicalFetchTests(unittest.TestCase):
    def test_dedicated_namespace_history_survives_general_metafield_page(self):
        node = {"id": "gid://shopify/Product/987", "status": "ACTIVE", "handle": "new-art",
                "metafields": {"nodes": [{"namespace": "other", "key": "k", "value": "v"}]},
                "editionRegistrationMetafields": {"nodes": [{"namespace": "sports_cave", "key": "edition_archived", "value": "true"}], "pageInfo": {"hasNextPage": False}}}
        with patch.object(shopify_sync, "graphql_request", return_value=({"product": node}, "2026-07")) as request:
            product = shopify_sync.fetch_product_by_shopify_id(987, config={"store_domain": "test.myshopify.com"})
        self.assertIn('namespace: "sports_cave"', request.call_args.args[0])
        self.assertEqual(shopify_sync.edition_registration_history_warning(product), "historical_closed_mirror_requires_review")

    def test_incomplete_history_metadata_fails_closed(self):
        node = {"id": "gid://shopify/Product/987", "editionRegistrationMetafields": {"pageInfo": {"hasNextPage": True}}}
        with patch.object(shopify_sync, "graphql_request", return_value=({"product": node}, "2026-07")):
            with self.assertRaisesRegex(shopify_sync.ShopifyAPIError, "incomplete"):
                shopify_sync.fetch_product_by_shopify_id(987, config={"store_domain": "test.myshopify.com"})


if __name__ == "__main__":
    unittest.main()
