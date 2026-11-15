import inspect
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import shopify_order_reconciliation_worker
import sports_cave_server
import supabase_backend
import top_bar_api
import webhook_server


class RenderHealthRepairTests(unittest.TestCase):
    def test_main_health_paths_bypass_streamlit_runtime(self):
        self.assertIsInstance(sports_cave_server.app, sports_cave_server.ConstantTimeHealthMiddleware)
        client = TestClient(sports_cave_server.app)
        for path in sorted(sports_cave_server.MAIN_HEALTH_PATHS):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "ok\n")
            self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_main_and_webhook_health_remain_responsive_during_six_second_reconciliation(self):
        reconciliation_started = threading.Event()
        release_reconciliation = threading.Event()

        def slow_reconciliation(**_kwargs):
            reconciliation_started.set()
            self.assertTrue(release_reconciliation.wait(8), "test did not release reconciliation")
            return {
                "shopify_orders_fetched": 50,
                "new_orders_inserted": 0,
                "orders_updated": 20,
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
            "shopify_order_reconciliation_lease",
            return_value=nullcontext(True),
        ), patch.object(
            supabase_backend,
            "sync_latest_paid_orders_to_supabase",
            side_effect=slow_reconciliation,
        ), TestClient(webhook_server.app) as webhook_client:
            main_client = TestClient(sports_cave_server.app)
            worker = threading.Thread(target=shopify_order_reconciliation_worker.run_once, name="six-second-reconciliation")
            worker.start()
            self.assertTrue(reconciliation_started.wait(2))
            latencies_ms = []
            started = time.perf_counter()
            try:
                while time.perf_counter() - started < 6.1:
                    for client, path in (
                        (main_client, "/_stcore/health"),
                        (main_client, "/healthz"),
                        (webhook_client, "/healthz"),
                    ):
                        request_started = time.perf_counter()
                        response = client.get(path)
                        latencies_ms.append((time.perf_counter() - request_started) * 1000)
                        self.assertEqual(response.status_code, 200)
                    time.sleep(0.1)
            finally:
                release_reconciliation.set()
                worker.join(5)

        self.assertFalse(worker.is_alive())
        self.assertGreaterEqual(time.perf_counter() - started, 6.0)
        self.assertLess(max(latencies_ms), 1000, latencies_ms)

    def test_blocking_top_bar_database_read_runs_off_event_loop(self):
        read_started = threading.Event()
        release_read = threading.Event()
        responses = []

        def slow_order_status(_claims):
            read_started.set()
            self.assertTrue(release_read.wait(5), "test did not release top-bar database read")
            return {"action_required_count": 0, "badge_label": "", "notification": {}}

        client = TestClient(sports_cave_server.app)
        with patch.object(top_bar_api, "_claims", return_value={"allowed_routes": ["Orders"]}), patch.object(
            top_bar_api,
            "load_order_status",
            side_effect=slow_order_status,
        ):
            request_thread = threading.Thread(
                target=lambda: responses.append(client.get(top_bar_api.ORDER_STATUS_PATH)),
                name="slow-top-bar-order-status",
            )
            request_thread.start()
            self.assertTrue(read_started.wait(2))
            try:
                started = time.perf_counter()
                health = client.get("/_stcore/health")
                elapsed_ms = (time.perf_counter() - started) * 1000
            finally:
                release_read.set()
                request_thread.join(5)

        self.assertFalse(request_thread.is_alive())
        self.assertEqual(health.status_code, 200)
        self.assertLess(elapsed_ms, 1000)
        self.assertEqual([response.status_code for response in responses], [200])

    def test_service_entry_points_and_health_paths_are_distinct(self):
        server_source = inspect.getsource(sports_cave_server)
        webhook_source = inspect.getsource(webhook_server)
        blueprint = Path("render.yaml").read_text(encoding="utf-8")
        topology = Path("docs/RENDER_SERVICE_TOPOLOGY.md").read_text(encoding="utf-8")

        self.assertIn('host=os.getenv("HOST", "0.0.0.0")', server_source)
        self.assertIn('port=int(os.getenv("PORT", "8501"))', server_source)
        self.assertIn('uvicorn.run(', server_source)
        self.assertIn('log_collector_vault_readiness(check_shopify=False)', server_source)
        self.assertIn('srv-d8kl4on7f7vs73dvavv0', topology)
        self.assertIn('srv-d9146onlk1mc739nrm7g', topology)
        self.assertIn('"/_stcore/health"', server_source)
        self.assertIn('name: sports-cave-os-webhooks', blueprint)
        self.assertIn('startCommand: python webhook_server.py', blueprint)
        self.assertIn('healthCheckPath: /healthz', blueprint)
        self.assertIn('@app.get("/healthz")', webhook_source)
        self.assertNotIn('name: sports-cave-os\n', blueprint)


if __name__ == "__main__":
    unittest.main()
