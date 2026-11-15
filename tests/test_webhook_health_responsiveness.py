import threading
import time
import unittest
from contextlib import ExitStack, nullcontext
from unittest.mock import patch

from fastapi.testclient import TestClient

import shopify_order_reconciliation_worker
import supabase_backend
import webhook_server


class WebhookHealthResponsivenessTests(unittest.TestCase):
    RAW_BODY = b'{"id":9001,"name":"#TEST9001","financial_status":"paid","line_items":[{"id":7001}]}'

    @staticmethod
    def _headers(webhook_id="health-test-webhook"):
        return {
            "X-Shopify-Hmac-Sha256": "verified-by-test",
            "X-Shopify-Topic": "orders/paid",
            "X-Shopify-Webhook-Id": webhook_id,
        }

    def _patched_paid_order_pipeline(self, *, claim, process, collector=None):
        stack = ExitStack()
        stack.enter_context(
            patch.dict(
                "os.environ",
                {"SHOPIFY_ORDER_RECONCILIATION_ENABLED": "false"},
            )
        )
        stack.enter_context(
            patch.object(
                webhook_server,
                "verify_shopify_webhook_hmac",
                return_value={"ok": True, "secret_env_used": "SHOPIFY_WEBHOOK_SECRET"},
            )
        )
        stack.enter_context(patch.object(supabase_backend, "is_configured", return_value=True))
        stack.enter_context(patch.object(supabase_backend, "claim_order_paid_webhook_receipt", side_effect=claim))
        stack.enter_context(patch.object(supabase_backend, "process_order_paid_webhook", side_effect=process))
        collector_mock = stack.enter_context(
            patch.object(
                webhook_server,
                "_process_collector_vault_background",
                side_effect=collector or (lambda *_args, **_kwargs: None),
            )
        )
        return stack, collector_mock

    def _start_webhook(self, client, responses, *, webhook_id="health-test-webhook"):
        def send():
            responses.append(
                client.post(
                    "/webhooks/shopify/orders-paid",
                    content=self.RAW_BODY,
                    headers=self._headers(webhook_id),
                )
            )

        thread = threading.Thread(target=send, name=f"test-{webhook_id}")
        thread.start()
        return thread

    def _assert_health_is_responsive(self, client, *, requests=5):
        latencies_ms = []
        for _ in range(requests):
            started = time.perf_counter()
            response = client.get("/healthz")
            latencies_ms.append((time.perf_counter() - started) * 1000)
            self.assertEqual(response.status_code, 200)
        self.assertLess(max(latencies_ms), 1000, latencies_ms)
        return latencies_ms

    def test_healthz_responds_while_slow_shopify_mirror_and_order_persistence_run(self):
        processing_started = threading.Event()
        release_processing = threading.Event()

        def claim(*_args, **_kwargs):
            return {"webhook_id": "health-test-webhook", "duplicate": False}

        def slow_process(*_args, **_kwargs):
            processing_started.set()
            self.assertTrue(release_processing.wait(5), "test did not release simulated persistence")
            return {"processed": True, "errors": [], "editions_assigned": 1, "metafields_updated": 1}

        stack, _collector = self._patched_paid_order_pipeline(claim=claim, process=slow_process)
        with stack, TestClient(webhook_server.app) as client:
            responses = []
            webhook_thread = self._start_webhook(client, responses)
            self.assertTrue(processing_started.wait(2))
            try:
                self._assert_health_is_responsive(client)
            finally:
                release_processing.set()
                webhook_thread.join(5)

        self.assertFalse(webhook_thread.is_alive())
        self.assertEqual([response.status_code for response in responses], [200])

    def test_healthz_responds_while_slow_receipt_write_runs(self):
        claim_started = threading.Event()
        release_claim = threading.Event()

        def slow_claim(*_args, **_kwargs):
            claim_started.set()
            self.assertTrue(release_claim.wait(5), "test did not release simulated receipt write")
            return {"webhook_id": "slow-receipt", "duplicate": False}

        def process(*_args, **_kwargs):
            return {"processed": True, "errors": []}

        stack, _collector = self._patched_paid_order_pipeline(claim=slow_claim, process=process)
        with stack, TestClient(webhook_server.app) as client:
            responses = []
            webhook_thread = self._start_webhook(client, responses, webhook_id="slow-receipt")
            self.assertTrue(claim_started.wait(2))
            try:
                self._assert_health_is_responsive(client)
            finally:
                release_claim.set()
                webhook_thread.join(5)

        self.assertFalse(webhook_thread.is_alive())
        self.assertEqual([response.status_code for response in responses], [200])

    def test_healthz_responds_while_reconciliation_worker_runs(self):
        reconciliation_started = threading.Event()
        release_reconciliation = threading.Event()

        def slow_reconciliation(**_kwargs):
            reconciliation_started.set()
            self.assertTrue(release_reconciliation.wait(5), "test did not release reconciliation")
            return {
                "shopify_orders_fetched": 49,
                "new_orders_inserted": 0,
                "orders_updated": 0,
                "orders_requiring_mapping": 0,
                "orders_rejected": 0,
                "orders_retryable_errors": 0,
            }

        with patch.dict("os.environ", {"SHOPIFY_ORDER_RECONCILIATION_ENABLED": "false"}), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "sync_latest_paid_orders_to_supabase",
            side_effect=slow_reconciliation,
        ), patch.object(
            supabase_backend,
            "shopify_order_reconciliation_lease",
            return_value=nullcontext(True),
        ), TestClient(webhook_server.app) as client:
            worker = threading.Thread(target=shopify_order_reconciliation_worker.run_once, name="test-reconciliation")
            worker.start()
            self.assertTrue(reconciliation_started.wait(2))
            try:
                self._assert_health_is_responsive(client)
            finally:
                release_reconciliation.set()
                worker.join(5)

        self.assertFalse(worker.is_alive())

    def test_duplicate_delivery_remains_serial_and_exactly_once(self):
        first_processing_started = threading.Event()
        release_first = threading.Event()
        durable_complete = threading.Event()
        counts = {"claims": 0, "process": 0, "editions": 0, "metafields": 0, "lines": 0}

        def claim(*_args, **_kwargs):
            counts["claims"] += 1
            return {
                "webhook_id": "duplicate-id",
                "duplicate": durable_complete.is_set(),
            }

        def process(*_args, **kwargs):
            counts["process"] += 1
            self.assertFalse(kwargs.get("claim_event", True))
            first_processing_started.set()
            self.assertTrue(release_first.wait(5), "test did not release first delivery")
            counts["editions"] += 1
            counts["metafields"] += 1
            counts["lines"] += 1
            durable_complete.set()
            return {"processed": True, "errors": [], "editions_assigned": 1, "metafields_updated": 1}

        stack, collector = self._patched_paid_order_pipeline(claim=claim, process=process)
        with stack, TestClient(webhook_server.app) as client:
            responses = []
            first = self._start_webhook(client, responses, webhook_id="duplicate-id")
            self.assertTrue(first_processing_started.wait(2))
            second = self._start_webhook(client, responses, webhook_id="duplicate-id")
            time.sleep(0.05)
            release_first.set()
            first.join(5)
            second.join(5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(sorted(response.json()["status"] for response in responses), ["processed", "skipped_duplicate"])
        self.assertEqual(counts, {"claims": 2, "process": 1, "editions": 1, "metafields": 1, "lines": 1})
        self.assertEqual(collector.call_count, 1)

    def test_success_is_not_acknowledged_before_durable_processing_finishes(self):
        def claim(*_args, **_kwargs):
            return {"webhook_id": "durability-test", "duplicate": False}

        def process(*_args, **_kwargs):
            time.sleep(0.15)
            return {"processed": True, "errors": []}

        stack, _collector = self._patched_paid_order_pipeline(claim=claim, process=process)
        with stack, TestClient(webhook_server.app) as client:
            started = time.perf_counter()
            response = client.post(
                "/webhooks/shopify/orders-paid",
                content=self.RAW_BODY,
                headers=self._headers("durability-test"),
            )
            elapsed = time.perf_counter() - started

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(elapsed, 0.12)

    def test_processing_failure_is_logged_and_remains_retryable(self):
        def claim(*_args, **_kwargs):
            return {"webhook_id": "failure-test", "duplicate": False}

        def process(*_args, **_kwargs):
            raise RuntimeError("simulated persistence failure")

        stack, collector = self._patched_paid_order_pipeline(claim=claim, process=process)
        with stack, patch.object(webhook_server, "_webhook_log") as webhook_log, TestClient(
            webhook_server.app
        ) as client:
            response = client.post(
                "/webhooks/shopify/orders-paid",
                content=self.RAW_BODY,
                headers=self._headers("failure-test"),
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("retry", response.text.casefold())
        self.assertTrue(
            any(
                call.args == ("webhook_order_processing_failed",)
                and call.kwargs.get("error") == "RuntimeError"
                for call in webhook_log.call_args_list
            )
        )
        collector.assert_not_called()


if __name__ == "__main__":
    unittest.main()
