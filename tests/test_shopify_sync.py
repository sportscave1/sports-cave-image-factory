import os
import inspect
import json
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import db
import order_allocator
import shopify_sync
import supabase_backend


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"X-Shopify-API-Version": "2026-04"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise shopify_sync.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class ShopifySyncClientTests(unittest.TestCase):
    def setUp(self):
        shopify_sync.clear_access_token_cache()
        self.config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Admin access token mode",
            "configured": True,
        }

    def tearDown(self):
        shopify_sync.clear_access_token_cache()

    def test_normalize_store_domain(self):
        self.assertEqual(
            shopify_sync.normalize_store_domain("https://SPORTS-CAVE.myshopify.com/admin"),
            "sports-cave.myshopify.com",
        )

    def test_shopify_webhook_hmac_verifies_valid_signature(self):
        raw_body = b'{"id":123,"name":"#SC2879"}'
        secret = "app-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")

        self.assertTrue(shopify_sync.verify_shopify_webhook_hmac(raw_body, signature, secret))

    def test_shopify_webhook_hmac_rejects_invalid_or_missing_signature(self):
        raw_body = b'{"id":123}'

        self.assertFalse(shopify_sync.verify_shopify_webhook_hmac(raw_body, "bad", "app-secret"))
        self.assertFalse(shopify_sync.verify_shopify_webhook_hmac(raw_body, "", "app-secret"))
        self.assertFalse(shopify_sync.verify_shopify_webhook_hmac(raw_body, "bad", ""))

    def test_shopify_webhook_secret_prefers_dedicated_webhook_secret(self):
        with patch.dict(
            os.environ,
            {
                "SHOPIFY_WEBHOOK_SECRET": "webhook-secret ",
                "SHOPIFY_CLIENT_SECRET": "client-secret",
            },
        ):
            self.assertEqual(shopify_sync.get_shopify_webhook_secret(config={"client_secret": "config-secret"}), "webhook-secret")

    def test_orders_paid_webhook_topic_accepts_rest_and_graphql_names(self):
        self.assertTrue(shopify_sync.is_orders_paid_webhook_topic("orders/paid"))
        self.assertTrue(shopify_sync.is_orders_paid_webhook_topic("ORDERS_PAID"))
        self.assertFalse(shopify_sync.is_orders_paid_webhook_topic("orders/create"))

    def test_products_create_webhook_topic_accepts_rest_and_graphql_names(self):
        self.assertTrue(shopify_sync.is_products_create_webhook_topic("products/create"))
        self.assertTrue(shopify_sync.is_products_create_webhook_topic("PRODUCTS_CREATE"))
        self.assertFalse(shopify_sync.is_products_create_webhook_topic("products/update"))

    def test_orders_paid_webhook_callback_accepts_base_or_full_url(self):
        self.assertEqual(
            shopify_sync.orders_paid_webhook_callback_url("https://sports-cave-image-factory.onrender.com"),
            "https://sports-cave-image-factory.onrender.com/webhooks/shopify/orders-paid",
        )
        self.assertEqual(
            shopify_sync.orders_paid_webhook_callback_url(
                "https://sports-cave-image-factory.onrender.com/webhooks/shopify/orders-paid"
            ),
            "https://sports-cave-image-factory.onrender.com/webhooks/shopify/orders-paid",
        )

    def test_orders_paid_webhook_callback_prefers_webhook_base_url(self):
        with patch.dict(
            os.environ,
            {
                "SPORTS_CAVE_WEBHOOK_BASE_URL": "https://sports-cave-os-webhooks.onrender.com",
                "SPORTS_CAVE_OS_BASE_URL": "https://sports-cave-image-factory.onrender.com",
            },
        ):
            self.assertEqual(
                shopify_sync.orders_paid_webhook_callback_url(),
                "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/orders-paid",
            )

    def test_products_create_webhook_callback_accepts_base_or_full_url(self):
        self.assertEqual(
            shopify_sync.products_create_webhook_callback_url("https://sports-cave-os-webhooks.onrender.com"),
            "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/products-create",
        )
        self.assertEqual(
            shopify_sync.products_create_webhook_callback_url(
                "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/products-create"
            ),
            "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/products-create",
        )

    def test_products_create_subscription_uses_graphql_registration_helper(self):
        requests = []

        def fake_post(url, headers=None, json=None, timeout=None):
            requests.append(json)
            query = json.get("query") or ""
            if "webhookSubscriptions" in query:
                return FakeResponse({"data": {"webhookSubscriptions": {"nodes": []}}})
            return FakeResponse(
                {
                    "data": {
                        "webhookSubscriptionCreate": {
                            "webhookSubscription": {
                                "id": "gid://shopify/WebhookSubscription/200",
                                "topic": "PRODUCTS_CREATE",
                                "endpoint": {
                                    "__typename": "WebhookHttpEndpoint",
                                    "callbackUrl": "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/products-create",
                                },
                            },
                            "userErrors": [],
                        }
                    }
                }
            )

        result = shopify_sync.ensure_products_create_webhook_subscription(
            callback_url="https://sports-cave-os-webhooks.onrender.com",
            config=self.config,
            request_post=fake_post,
        )

        self.assertTrue(result["created"])
        self.assertEqual(requests[0]["variables"]["topics"], ["PRODUCTS_CREATE"])
        self.assertEqual(requests[1]["variables"]["topic"], "PRODUCTS_CREATE")
        self.assertEqual(
            requests[1]["variables"]["webhookSubscription"]["callbackUrl"],
            "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/products-create",
        )

    def test_orders_paid_fastapi_route_accepts_valid_hmac(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_order_paid_webhook_receipt",
            return_value={
                "webhook_id": "webhook-2879",
                "duplicate": False,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
            },
        ), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
            return_value={
                "source": "webhook",
                "processed": True,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
                "imported_lines": 1,
                "skipped_existing_lines": 0,
                "editions_assigned": 1,
                "affected_handles": ["joel-embiid-76ers-art"],
                "metafields_updated": 1,
                "errors": [],
            },
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                    "X-Shopify-Webhook-Id": "webhook-2879",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")
        process_webhook.assert_called_once()
        self.assertFalse(process_webhook.call_args.kwargs["claim_event"])

    def test_orders_paid_fastapi_route_accepts_valid_webhook_secret(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "webhook-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(
            os.environ,
            {"SHOPIFY_WEBHOOK_SECRET": f" {secret} ", "SHOPIFY_CLIENT_SECRET": "wrong-client-secret"},
        ), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_order_paid_webhook_receipt",
            return_value={
                "webhook_id": "missing-id-test",
                "duplicate": False,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
            },
        ), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
            return_value={
                "source": "webhook",
                "processed": True,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
                "imported_lines": 1,
                "skipped_existing_lines": 0,
                "editions_assigned": 1,
                "affected_handles": [],
                "metafields_updated": 0,
                "errors": [],
            },
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                },
            )

        self.assertEqual(response.status_code, 200)
        process_webhook.assert_called_once()

    def test_orders_paid_fastapi_route_falls_back_to_client_secret(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(
            os.environ,
            {"SHOPIFY_WEBHOOK_SECRET": "wrong-webhook-secret", "SHOPIFY_CLIENT_SECRET": secret},
        ), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_order_paid_webhook_receipt",
            return_value={
                "webhook_id": "missing-id-test",
                "duplicate": False,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
            },
        ), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
            return_value={
                "source": "webhook",
                "processed": True,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
                "imported_lines": 1,
                "skipped_existing_lines": 0,
                "editions_assigned": 1,
                "affected_handles": [],
                "metafields_updated": 0,
                "errors": [],
            },
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                },
            )

        self.assertEqual(response.status_code, 200)
        process_webhook.assert_called_once()

    def test_orders_paid_fastapi_route_duplicate_receipt_skips_background_processing(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_order_paid_webhook_receipt",
            return_value={
                "webhook_id": "webhook-2879",
                "duplicate": True,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
            },
        ), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                    "X-Shopify-Webhook-Id": "webhook-2879",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "skipped_duplicate")
        process_webhook.assert_not_called()

    def test_products_create_fastapi_route_uses_same_hmac_helper(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":100,"admin_graphql_api_id":"gid://shopify/Product/100","handle":"new-wall-art","title":"New Wall Art","status":"active"}'
        with patch.object(
            webhook_server,
            "verify_shopify_webhook_hmac",
            return_value={"ok": True, "secret_env_used": "SHOPIFY_CLIENT_SECRET"},
        ) as verify_hmac, patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_product_create_webhook_receipt",
            return_value={
                "webhook_id": "product-webhook-100",
                "duplicate": False,
                "shopify_product_id": "gid://shopify/Product/100",
                "shopify_handle": "new-wall-art",
            },
        ), patch.object(
            supabase_backend,
            "process_product_create_webhook",
            return_value={"source": "webhook", "processed": True, "errors": []},
        ) as process_product, patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_order:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/products-create",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": "patched-hmac",
                    "X-Shopify-Topic": "products/create",
                    "X-Shopify-Webhook-Id": "product-webhook-100",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")
        verify_hmac.assert_called_once()
        self.assertEqual(verify_hmac.call_args.args[0], raw_body)
        process_product.assert_called_once()
        self.assertFalse(process_product.call_args.kwargs["claim_event"])
        process_order.assert_not_called()

    def test_products_create_fastapi_route_duplicate_receipt_skips_processing(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":100,"admin_graphql_api_id":"gid://shopify/Product/100","handle":"new-wall-art","title":"New Wall Art","status":"active"}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_product_create_webhook_receipt",
            return_value={
                "webhook_id": "product-webhook-100",
                "duplicate": True,
                "shopify_product_id": "gid://shopify/Product/100",
                "shopify_handle": "new-wall-art",
            },
        ), patch.object(
            supabase_backend,
            "process_product_create_webhook",
        ) as process_product:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/products-create",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "products/create",
                    "X-Shopify-Webhook-Id": "product-webhook-100",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "skipped_duplicate")
        process_product.assert_not_called()

    def test_orders_paid_fastapi_logs_do_not_expose_hmac_or_secret_lengths(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(
            os.environ,
            {
                "SHOPIFY_CLIENT_SECRET": secret,
                "SHOPIFY_WEBHOOK_SECRET": "",
                "DEBUG_WEBHOOK_SECURITY": "",
                "RENDER": "true",
            },
        ), patch.object(
            supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            supabase_backend,
            "claim_order_paid_webhook_receipt",
            return_value={
                "webhook_id": "webhook-2879",
                "duplicate": False,
                "order_name": "#SC2879",
                "shopify_order_id": "gid://shopify/Order/2879",
            },
        ), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
            return_value={"source": "webhook", "processed": True, "errors": []},
        ), patch.object(webhook_server, "_webhook_log") as webhook_log:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                    "X-Shopify-Webhook-Id": "webhook-2879",
                },
            )

        self.assertEqual(response.status_code, 200)
        logged_text = " ".join(str(call) for call in webhook_log.call_args_list)
        self.assertNotIn("received_hmac_prefix", logged_text)
        self.assertNotIn("received_hmac_suffix", logged_text)
        self.assertNotIn("calculated_hmac_prefix", logged_text)
        self.assertNotIn("calculated_hmac_suffix", logged_text)
        self.assertNotIn("secret_length", logged_text)
        self.assertNotIn("raw_body", logged_text)

    def test_orders_paid_fastapi_healthz(self):
        from fastapi.testclient import TestClient
        import webhook_server

        response = TestClient(webhook_server.app).get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "sports-cave-os-webhooks")

    def test_orders_paid_fastapi_route_rejects_invalid_hmac(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879}'
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": "client-secret", "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": "bad",
                    "X-Shopify-Topic": "orders/paid",
                },
            )

        self.assertEqual(response.status_code, 401)
        process_webhook.assert_not_called()

    def test_orders_paid_fastapi_route_rejects_wrong_topic_after_hmac(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/create",
                },
            )

        self.assertEqual(response.status_code, 400)
        process_webhook.assert_not_called()

    def test_orders_paid_fastapi_route_rejects_reencoded_json_signature(self):
        from fastapi.testclient import TestClient
        import webhook_server

        sent_body = b'{ "id" : 2879, "name" : "#SC2879", "financial_status" : "paid" }'
        differently_encoded_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid"}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), differently_encoded_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=sent_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                },
            )

        self.assertEqual(response.status_code, 401)
        process_webhook.assert_not_called()

    def test_orders_paid_fastapi_route_rejects_wrong_secret(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"financial_status":"paid"}'
        signature = base64.b64encode(
            hmac.new(b"wrong-secret", raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": "client-secret", "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                },
            )

        self.assertEqual(response.status_code, 401)
        process_webhook.assert_not_called()

    def test_orders_paid_fastapi_route_rejects_missing_hmac_header(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"financial_status":"paid"}'
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": "client-secret", "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={"X-Shopify-Topic": "orders/paid"},
            )

        self.assertEqual(response.status_code, 401)
        process_webhook.assert_not_called()

    def test_orders_paid_fastapi_route_shopify_test_skips_order_processing(self):
        from fastapi.testclient import TestClient
        import webhook_server

        raw_body = b'{"id":2879,"name":"#SC2879","financial_status":"paid","line_items":[]}'
        secret = "client-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret, "SHOPIFY_WEBHOOK_SECRET": ""}), patch.object(
            supabase_backend,
            "is_configured",
        ) as is_configured, patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as process_webhook:
            response = TestClient(webhook_server.app).post(
                "/webhooks/shopify/orders-paid",
                content=raw_body,
                headers={
                    "X-Shopify-Hmac-Sha256": signature,
                    "X-Shopify-Topic": "orders/paid",
                    "X-Shopify-Test": "true",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "shopify_test_verified")
        is_configured.assert_not_called()
        process_webhook.assert_not_called()

    def test_order_certificate_metafields_include_vault_ready_json(self):
        inputs = shopify_sync.order_certificate_metafield_inputs(
            "gid://shopify/Order/1234",
            [
                {
                    "shopify_customer_id": "gid://shopify/Customer/9",
                    "customer_email": "greg@example.com",
                    "customer_name": "Greg Collector",
                    "order_gid": "gid://shopify/Order/1234",
                    "order_name": "#SC1234",
                    "line_item_id": "gid://shopify/LineItem/555",
                    "product_gid": "gid://shopify/Product/777",
                    "variant_gid": "gid://shopify/ProductVariant/888",
                    "product_title": "Greg Murphy Lap of the Gods Wall Art",
                    "handle": "greg-murphy-lap-of-the-gods-wall-art",
                    "variant_title": "Black / XL",
                    "edition_number": 12,
                    "edition_total": 100,
                    "certificate_id": "SC-SC1234-012",
                    "pdf_shopify_file_id": "gid://shopify/GenericFile/1",
                    "pdf_url": "https://cdn.example/cert.pdf",
                    "shopify_print_jpg_file_id": "gid://shopify/MediaImage/2",
                    "shopify_preview_file_id": "gid://shopify/MediaImage/3",
                    "certificate_print_jpg_url": "https://cdn.example/cert-print.jpg",
                    "certificate_preview_image_url": "https://cdn.example/cert-preview.webp",
                    "status": "Ready",
                    "shopify_file_status": "READY",
                    "purchase_date": "2026-06-22T10:00:00Z",
                    "generated_at": "2026-06-22T10:05:00Z",
                },
                {
                    "order_gid": "gid://shopify/Order/1234",
                    "line_item_id": "gid://shopify/LineItem/556",
                    "edition_number": 13,
                    "edition_total": 100,
                    "certificate_id": "SC-SC1234-013",
                    "status": "Generated",
                },
            ],
        )

        self.assertEqual(
            [item["key"] for item in inputs],
            ["certificates", "certificates_json", "certificate_status", "certificate_count"],
        )
        payload = json.loads(inputs[1]["value"])
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["source"], "sports_cave_os")
        ready, processing = payload["certificates"]
        self.assertEqual(ready["edition_display"], "#012/100")
        self.assertEqual(ready["display_edition"], "Edition #012 of 100")
        self.assertEqual(ready["certificate_pdf_url"], "https://cdn.example/cert.pdf")
        self.assertEqual(ready["certificate_print_jpg_url"], "https://cdn.example/cert-print.jpg")
        self.assertEqual(ready["certificate_preview_image_url"], "https://cdn.example/cert-preview.webp")
        self.assertEqual(ready["shopify_pdf_file_id"], "gid://shopify/GenericFile/1")
        self.assertEqual(ready["shopify_print_jpg_file_id"], "gid://shopify/MediaImage/2")
        self.assertEqual(ready["shopify_preview_file_id"], "gid://shopify/MediaImage/3")
        self.assertEqual(ready["certificate_status"], "Ready")
        self.assertEqual(ready["certificate_file_url"], "https://cdn.example/cert.pdf")
        self.assertEqual(processing["certificate_status"], "Processing")
        self.assertEqual(processing["certificate_file_url"], "")
        self.assertEqual(processing["certificate_print_jpg_url"], "")
        self.assertEqual(processing["certificate_preview_image_url"], "")
        self.assertEqual(inputs[2]["value"], "processing")
        self.assertEqual(inputs[3]["value"], "2")

    def test_order_certificate_sync_retries_missing_vault_json_metafield(self):
        requests_seen = []

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            request_index = len(requests_seen)
            if request_index == 1:
                return FakeResponse(
                    {
                        "data": {
                            "metafieldsSet": {
                                "metafields": [
                                    {
                                        "namespace": "sports_cave",
                                        "key": "certificates",
                                        "type": "json",
                                        "value": "[]",
                                        "compareDigest": "legacy-digest",
                                    }
                                ],
                                "userErrors": [],
                            }
                        }
                    }
                )
            requested = kwargs["json"]["variables"]["metafields"][0]
            return FakeResponse(
                {
                    "data": {
                        "metafieldsSet": {
                            "metafields": [
                                {
                                    "namespace": "sports_cave",
                                    "key": requested["key"],
                                    "type": "json",
                                    "value": requested["value"],
                                    "compareDigest": "json-digest",
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            )

        result = shopify_sync.sync_order_certificate_metafields(
            "gid://shopify/Order/1234",
            [
                {
                    "order_gid": "gid://shopify/Order/1234",
                    "line_item_id": "gid://shopify/LineItem/555",
                    "edition_number": 12,
                    "edition_total": 100,
                    "certificate_id": "SC-SC1234-012",
                    "pdf_url": "https://cdn.example/cert.pdf",
                    "status": "Ready",
                }
            ],
            config=self.config,
            request_post=fake_post,
        )

        self.assertEqual(len(requests_seen), 4)
        self.assertEqual(
            [item["key"] for item in requests_seen[0]["variables"]["metafields"]],
            ["certificates", "certificates_json", "certificate_status", "certificate_count"],
        )
        self.assertEqual([item["key"] for item in requests_seen[1]["variables"]["metafields"]], ["certificates_json"])
        self.assertEqual([item["key"] for item in requests_seen[2]["variables"]["metafields"]], ["certificate_status"])
        self.assertEqual([item["key"] for item in requests_seen[3]["variables"]["metafields"]], ["certificate_count"])
        self.assertEqual(
            {item["key"] for item in result["metafields"]},
            {"certificates", "certificates_json", "certificate_status", "certificate_count"},
        )

    def test_environment_config_prefers_client_credentials_over_legacy_admin_token(self):
        environment = {
            "SHOPIFY_STORE_DOMAIN": "sports-cave.myshopify.com",
            "SHOPIFY_API_VERSION": "2026-04",
            "SHOPIFY_ADMIN_ACCESS_TOKEN": "legacy-token",
            "SHOPIFY_CLIENT_ID": "client-id",
            "SHOPIFY_CLIENT_SECRET": "client-secret",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = shopify_sync.get_config()

        self.assertTrue(config["configured"])
        self.assertEqual(config["auth_mode"], "Client credentials mode")
        self.assertEqual(config["edition_ops_max_products"], 500)
        self.assertTrue(config["has_legacy_admin_token"])

    def test_environment_config_accepts_client_credentials(self):
        environment = {
            "SHOPIFY_STORE_DOMAIN": "sports-cave.myshopify.com",
            "SHOPIFY_API_VERSION": "2026-04",
            "SHOPIFY_CLIENT_ID": "client-id",
            "SHOPIFY_CLIENT_SECRET": "client-secret",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = shopify_sync.get_config()

        self.assertTrue(config["configured"])
        self.assertEqual(config["auth_mode"], "Client credentials mode")

    def test_client_credentials_token_is_cached_for_graphql_calls(self):
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Client credentials mode",
            "configured": True,
        }
        token_requests = []
        graphql_requests = []

        def fake_post(url, **kwargs):
            if url.endswith("/admin/oauth/access_token"):
                token_requests.append(kwargs)
                return FakeResponse(
                    {
                        "access_token": "temporary-token",
                        "scope": "read_products read_orders read_customers write_files",
                        "expires_in": 3600,
                    }
                )
            graphql_requests.append(kwargs)
            return FakeResponse(
                {
                    "data": {
                        "shop": {
                            "id": "gid://shopify/Shop/1",
                            "name": "Sports Cave",
                            "myshopifyDomain": "sports-cave.myshopify.com",
                            "primaryDomain": {
                                "host": "sportscaveshop.com",
                                "url": "https://sportscaveshop.com",
                            },
                        }
                    }
                }
            )

        shopify_sync.test_connection(config=config, request_post=fake_post)
        shopify_sync.test_connection(config=config, request_post=fake_post)

        self.assertEqual(len(token_requests), 1)
        self.assertEqual(len(graphql_requests), 2)
        self.assertEqual(
            token_requests[0]["data"],
            {
                "grant_type": "client_credentials",
                "client_id": "client-id",
                "client_secret": "client-secret",
            },
        )
        self.assertEqual(
            graphql_requests[0]["headers"]["X-Shopify-Access-Token"],
            "temporary-token",
        )
        status = shopify_sync.get_token_status(config)
        self.assertIsNotNone(status["last_refresh"])
        self.assertIn("read_orders", status["scopes"])

    def test_connection_returns_scope_diagnostics(self):
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Client credentials mode",
            "configured": True,
        }

        def fake_post(url, **kwargs):
            if url.endswith("/admin/oauth/access_token"):
                return FakeResponse(
                    {
                        "access_token": "temporary-token",
                        "scope": "read_products read_orders",
                        "expires_in": 3600,
                    }
                )
            return FakeResponse(
                {
                    "data": {
                        "shop": {
                            "id": "gid://shopify/Shop/1",
                            "name": "Sports Cave",
                            "myshopifyDomain": "sports-cave.myshopify.com",
                            "primaryDomain": {
                                "host": "sportscaveshop.com",
                                "url": "https://sportscaveshop.com",
                            },
                        }
                    }
                }
            )

        result = shopify_sync.test_connection(config=config, request_post=fake_post)

        self.assertTrue(result["ok"])
        self.assertTrue(result["scope_status"]["read_orders"])
        self.assertTrue(result["scope_status"]["read_products"])
        self.assertFalse(result["scope_status"]["read_customers"])

    def test_client_token_refreshes_when_close_to_expiry(self):
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Client credentials mode",
            "configured": True,
        }
        tokens_issued = []

        def fake_post(*args, **kwargs):
            token = f"temporary-token-{len(tokens_issued) + 1}"
            tokens_issued.append(token)
            return FakeResponse({"access_token": token, "expires_in": 300})

        first_token = shopify_sync.get_access_token(config=config, request_post=fake_post)
        second_token = shopify_sync.get_access_token(config=config, request_post=fake_post)

        self.assertEqual(first_token, "temporary-token-1")
        self.assertEqual(second_token, "temporary-token-2")

    def test_client_credentials_failure_does_not_expose_secret(self):
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "",
            "client_id": "client-id",
            "client_secret": "do-not-expose-this-secret",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Client credentials mode",
            "configured": True,
        }

        with self.assertRaises(shopify_sync.ShopifyAuthenticationError) as context:
            shopify_sync.get_access_token(
                config=config,
                request_post=lambda *args, **kwargs: FakeResponse({}, status_code=401),
            )

        self.assertNotIn(config["client_secret"], str(context.exception))
        self.assertIn("authentication failed", str(context.exception))

    def test_missing_auth_configuration_has_safe_message(self):
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
        }
        with self.assertRaises(shopify_sync.ShopifyConfigurationError) as context:
            shopify_sync.validate_config(config)
        self.assertIn("Missing Shopify authentication", str(context.exception))

    def test_pdf_upload_uses_staged_upload_file_create_and_poll(self):
        requests_seen = []
        upload_calls = []
        responses = [
            FakeResponse(
                {
                    "data": {
                        "stagedUploadsCreate": {
                            "stagedTargets": [
                                {
                                    "url": "https://upload.example",
                                    "resourceUrl": "https://resource.example/certificate.pdf",
                                    "parameters": [{"name": "key", "value": "certificate-key"}],
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "fileCreate": {
                            "files": [
                                {
                                    "id": "gid://shopify/GenericFile/1",
                                    "fileStatus": "PROCESSING",
                                    "url": "",
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "node": {
                            "id": "gid://shopify/GenericFile/1",
                            "fileStatus": "READY",
                            "url": "https://cdn.example/certificate.pdf",
                        }
                    }
                }
            ),
        ]

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return responses.pop(0)

        class UploadResponse:
            status_code = 201

            def raise_for_status(self):
                return None

        def fake_upload_post(url, **kwargs):
            upload_calls.append({"url": url, **kwargs})
            return UploadResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "certificate.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            result = shopify_sync.upload_pdf_to_shopify_files(
                pdf_path,
                config=self.config,
                request_post=fake_post,
                upload_post=fake_upload_post,
                poll_sleep_seconds=0,
            )

        self.assertEqual(result["file_id"], "gid://shopify/GenericFile/1")
        self.assertEqual(result["url"], "https://cdn.example/certificate.pdf")
        self.assertEqual(upload_calls[0]["url"], "https://upload.example")
        self.assertEqual(upload_calls[0]["data"]["key"], "certificate-key")
        self.assertEqual(requests_seen[0]["variables"]["input"][0]["resource"], "FILE")
        self.assertEqual(requests_seen[1]["variables"]["files"][0]["contentType"], "FILE")

    def test_pdf_upload_times_out_when_file_never_becomes_ready(self):
        responses = [
            FakeResponse(
                {
                    "data": {
                        "stagedUploadsCreate": {
                            "stagedTargets": [
                                {
                                    "url": "https://upload.example",
                                    "resourceUrl": "https://resource.example/certificate.pdf",
                                    "parameters": [{"name": "key", "value": "certificate-key"}],
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "fileCreate": {
                            "files": [
                                {
                                    "id": "gid://shopify/GenericFile/1",
                                    "fileStatus": "PROCESSING",
                                    "url": "",
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "node": {
                            "id": "gid://shopify/GenericFile/1",
                            "fileStatus": "PROCESSING",
                            "url": "",
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "node": {
                            "id": "gid://shopify/GenericFile/1",
                            "fileStatus": "PROCESSING",
                            "url": "",
                        }
                    }
                }
            ),
        ]

        def fake_post(*args, **kwargs):
            return responses.pop(0)

        class UploadResponse:
            status_code = 201

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "certificate.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            with self.assertRaises(shopify_sync.ShopifyAPIError) as context:
                shopify_sync.upload_pdf_to_shopify_files(
                    pdf_path,
                    config=self.config,
                    request_post=fake_post,
                    upload_post=lambda *args, **kwargs: UploadResponse(),
                    poll_attempts=2,
                    poll_sleep_seconds=0,
                )

        self.assertIn("timed out waiting for a ready file URL", str(context.exception))

    def test_paid_order_allocator_assigns_current_next_number_and_advances_product(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [
                {
                    "id": 555,
                    "product_id": 777,
                    "title": "Shane Warne Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 1,
                }
            ],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            self.assertEqual(owner_id, "gid://shopify/Product/777")
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "91"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        order_writes = []
        product_writes = []
        events = []

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: (
                events.append("order"),
                order_writes.append(allocations),
            ),
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: (
                events.append("product"),
                product_writes.extend(products),
            ),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertTrue(result["processed"])
        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(events, ["order", "product"])
        allocation = order_writes[0]["line_items"]["gid://shopify/LineItem/555"]
        self.assertEqual(allocation["edition_numbers"], [91])
        self.assertEqual(allocation["edition_display"], "#091/100")
        self.assertEqual(product_writes[0]["edition_next_number"], 92)
        self.assertEqual(product_writes[0]["edition_sold_count"], 91)
        self.assertEqual(product_writes[0]["edition_remaining"], 9)
        unit = allocation["unit_allocations"][0]
        self.assertEqual(unit["order_gid"], "gid://shopify/Order/1234")
        self.assertEqual(unit["line_item_gid"], "gid://shopify/LineItem/555")
        self.assertEqual(unit["line_item_unit_index"], 1)
        self.assertEqual(unit["product_gid"], "gid://shopify/Product/777")
        self.assertEqual(unit["edition_number"], 91)

    def test_paid_order_allocator_falls_back_to_handle_when_product_id_lookup_fails(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [
                {
                    "id": 555,
                    "product_id": 999,
                    "product_handle": "goat-debate-wall-art",
                    "title": "GOAT Debate Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 1,
                }
            ],
        }
        product_fetches = []

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            product_fetches.append(owner_id)
            raise shopify_sync.ShopifyAPIError("Product ID lookup failed")

        def fake_fetch_products_by_handle(after=None, search="", page_size=25, config=None, request_post=None):
            self.assertEqual(search, "handle:goat-debate-wall-art")
            return {
                "products": [
                    {
                        "shopify_product_id": "gid://shopify/Product/777",
                        "handle": "goat-debate-wall-art",
                        "title": "GOAT Debate Wall Art",
                        "status": "ACTIVE",
                        "metafields": [
                            {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                            {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                            {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "35"},
                            {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "34"},
                            {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "66"},
                        ],
                    }
                ],
                "has_next_page": False,
            }

        order_writes = []
        product_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "fetch_limited_edition_products_page",
            side_effect=fake_fetch_products_by_handle,
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: product_writes.extend(products),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(product_fetches, ["gid://shopify/Product/999"])
        self.assertEqual(result["assignments_created"], 1)
        allocation = order_writes[0]["line_items"]["gid://shopify/LineItem/555"]
        self.assertEqual(allocation["edition_numbers"], [35])
        self.assertEqual(allocation["product_id"], "gid://shopify/Product/777")
        self.assertEqual(product_writes[0]["shopify_product_id"], "gid://shopify/Product/777")
        self.assertEqual(product_writes[0]["edition_next_number"], 36)

    def test_paid_order_allocator_splits_quantity_and_updates_product_totals(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [
                {
                    "id": 555,
                    "product_id": 777,
                    "title": "Justin Gaethje Undisputed Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 2,
                }
            ],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true", "compareDigest": "enabled"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100", "compareDigest": "total"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "13", "compareDigest": "next"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "12", "compareDigest": "sold"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "88", "compareDigest": "remaining"},
                    {"namespace": "sports_cave", "key": "edition_status", "type": "single_line_text_field", "value": "Limited Edition", "compareDigest": "status"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition", "compareDigest": "label"},
                ],
                "api_version": "2026-04",
            }

        order_writes = []
        product_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: product_writes.extend(products),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 2)
        allocation = order_writes[0]["line_items"]["gid://shopify/LineItem/555"]
        self.assertEqual(allocation["edition_numbers"], [13, 14])
        self.assertEqual(product_writes[0]["edition_next_number"], 15)
        self.assertEqual(product_writes[0]["edition_sold_count"], 14)
        self.assertEqual(product_writes[0]["edition_remaining"], 86)

    def test_paid_order_allocator_processes_batch_oldest_to_newest(self):
        product_state = {"next": 13, "sold": 12, "remaining": 88}
        order_payloads = [
            {
                "id": 2000,
                "name": "#SC2000",
                "financial_status": "paid",
                "processed_at": "2026-06-22T10:00:00Z",
                "created_at": "2026-06-22T09:55:00Z",
                "line_items": [{"id": 20, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
            },
            {
                "id": 1000,
                "name": "#SC1000",
                "financial_status": "paid",
                "processed_at": "2026-06-21T10:00:00Z",
                "created_at": "2026-06-21T09:55:00Z",
                "line_items": [{"id": 10, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
            },
        ]
        order_writes = {}

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id.startswith("gid://shopify/Order/"):
                payload = order_writes.get(owner_id)
                metafields = []
                if payload:
                    metafields.append(
                        {
                            "namespace": "sports_cave",
                            "key": "edition_allocations",
                            "type": "json",
                            "value": json.dumps(payload),
                            "compareDigest": f"digest-{owner_id}",
                        }
                    )
                return {"metafields": metafields, "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": str(product_state["next"])},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": str(product_state["sold"])},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": str(product_state["remaining"])},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        def fake_product_sync(products, config=None, request_post=None):
            row = products[0]
            product_state["next"] = row["edition_next_number"]
            product_state["sold"] = row["edition_sold_count"]
            product_state["remaining"] = row["edition_remaining"]

        def fake_order_sync(order_gid, allocations, compare_digest=None, config=None, request_post=None):
            order_writes[order_gid] = allocations

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=fake_product_sync,
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=fake_order_sync,
        ):
            result = order_allocator.process_shopify_orders_for_editions(order_payloads, config=self.config)

        self.assertEqual(result["assignments_created"], 2)
        self.assertEqual(
            order_writes["gid://shopify/Order/1000"]["line_items"]["gid://shopify/LineItem/10"]["edition_numbers"],
            [13],
        )
        self.assertEqual(
            order_writes["gid://shopify/Order/2000"]["line_items"]["gid://shopify/LineItem/20"]["edition_numbers"],
            [14],
        )
        self.assertEqual(product_state["next"], 15)

    def test_paid_order_allocator_retry_skips_existing_order_allocation(self):
        existing_payload = {
            "line_items": {
                "gid://shopify/LineItem/555": {
                    "line_item_id": "gid://shopify/LineItem/555",
                    "product_id": "gid://shopify/Product/777",
                    "quantity": 1,
                    "edition_numbers": [13],
                    "edition_total": 100,
                }
            }
        }
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {
                    "metafields": [
                        {
                            "namespace": "sports_cave",
                            "key": "edition_allocations",
                            "type": "json",
                            "value": json.dumps(existing_payload),
                            "compareDigest": "order-digest",
                        }
                    ],
                    "api_version": "2026-04",
                }
            self.fail("Product metafields should not be read when the exact unit is already allocated.")

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as product_sync, patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
        ) as order_sync:
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 0)
        self.assertEqual(result["skipped_existing"], 1)
        product_sync.assert_not_called()
        order_sync.assert_not_called()

    def test_paid_order_allocator_retries_product_compare_digest_failures(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true", "compareDigest": "enabled"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100", "compareDigest": "total"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "13", "compareDigest": "next"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "12", "compareDigest": "sold"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "88", "compareDigest": "remaining"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition", "compareDigest": "label"},
                ],
                "api_version": "2026-04",
            }

        product_attempts = []
        order_writes = []

        def fake_product_sync(products, config=None, request_post=None):
            product_attempts.append(products[0])
            if len(product_attempts) == 1:
                raise shopify_sync.ShopifyAPIError("compareDigest mismatch")

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=fake_product_sync,
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(len(product_attempts), 2)
        self.assertEqual(len(order_writes), 1)
        self.assertEqual(order_writes[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [13])

    def test_paid_order_allocator_never_overwrites_existing_unit_allocation(self):
        existing_payload = {
            "line_items": {
                "gid://shopify/LineItem/555": {
                    "line_item_id": "gid://shopify/LineItem/555",
                    "product_id": "gid://shopify/Product/777",
                    "quantity": 2,
                    "edition_numbers": [50, None],
                    "edition_total": 100,
                }
            }
        }
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 2}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {
                    "metafields": [
                        {
                            "namespace": "sports_cave",
                            "key": "edition_allocations",
                            "type": "json",
                            "value": json.dumps(existing_payload),
                            "compareDigest": "order-digest",
                        }
                    ],
                    "api_version": "2026-04",
                }
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "51"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "50"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "50"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        order_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 1)
        allocation = order_writes[0]["line_items"]["gid://shopify/LineItem/555"]
        self.assertEqual(allocation["edition_numbers"], [50, 51])

    def test_paid_order_allocator_final_edition_does_not_advance_to_101(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "99"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "1"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        product_writes = []
        order_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: product_writes.extend(products),
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(order_writes[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [100])
        self.assertEqual(product_writes[0]["edition_next_number"], 100)
        self.assertEqual(product_writes[0]["edition_sold_count"], 100)
        self.assertEqual(product_writes[0]["edition_remaining"], 0)
        self.assertEqual(product_writes[0]["edition_status"], "Sold Out Archive")

    def test_paid_order_allocator_sold_out_marks_review_without_duplicate_final_number(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "0"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        order_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as product_sync, patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ):
            result = order_allocator.process_shopify_order_for_editions(order_payload, config=self.config)

        self.assertEqual(result["assignments_created"], 0)
        product_sync.assert_not_called()
        allocation = order_writes[0]["line_items"]["gid://shopify/LineItem/555"]
        self.assertEqual(allocation["edition_numbers"], [None])
        self.assertEqual(allocation["edition_number"], None)
        self.assertEqual(allocation["status"], "Needs Review - Sold Out")

    def test_paid_order_allocator_auto_creates_settings_and_lazily_captures_product_baseline(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "processed_at": "2026-06-23T10:00:00Z",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "13"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "12"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "88"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        saved_states = []
        order_writes = []
        product_writes = []

        def fake_save_cutover_state(state):
            saved = dict(state)
            saved_states.append(saved)
            return saved

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            order_allocator,
            "save_cutover_state",
            side_effect=fake_save_cutover_state,
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: product_writes.extend(products),
        ):
            result = order_allocator.process_shopify_order_for_editions(
                order_payload,
                config=self.config,
                require_cutover=True,
                cutover_state={"automation_started_at": "", "baselines": {}},
            )

        self.assertTrue(result["processed"])
        self.assertEqual(result["assignments_created"], 1)
        self.assertTrue(saved_states[0]["active"])
        self.assertTrue(saved_states[0]["allocation_enabled"])
        self.assertTrue(saved_states[0]["automation_started_at"])
        lazy_baseline = saved_states[1]["baselines"]["gid://shopify/Product/777"]
        self.assertEqual(lazy_baseline["baseline_next_number"], 13)
        self.assertEqual(lazy_baseline["baseline_sold_count"], 12)
        self.assertEqual(lazy_baseline["baseline_remaining"], 88)
        self.assertEqual(order_writes[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [13])
        self.assertEqual(product_writes[0]["edition_next_number"], 14)

    def test_activate_live_allocation_saves_cutover_and_product_baselines(self):
        saved_states = []

        def fake_save_cutover_state(state):
            saved_states.append(state)
            return dict(state)

        with patch.object(
            order_allocator,
            "load_cutover_state",
            return_value={"active": False, "automation_started_at": "", "baselines": {}},
        ), patch.object(
            order_allocator,
            "save_cutover_state",
            side_effect=fake_save_cutover_state,
        ):
            result = order_allocator.activate_live_allocation(
                [
                    {
                        "shopify_product_id": "gid://shopify/Product/777",
                        "handle": "justin-gaethje-undisputed-wall-art",
                        "product_title": "Justin Gaethje Undisputed Wall Art",
                        "edition_total": 100,
                        "edition_next_number": 14,
                        "edition_sold_count": 13,
                        "edition_remaining": 87,
                    }
                ],
                started_at="2026-06-23T10:00:00Z",
            )

        self.assertTrue(result["active"])
        self.assertEqual(result["automation_started_at"], "2026-06-23T10:00:00Z")
        self.assertEqual(result["captured_count"], 1)
        self.assertEqual(saved_states[0]["automation_started_at"], "2026-06-23T10:00:00Z")
        self.assertTrue(saved_states[0]["active"])
        baseline = saved_states[0]["baselines"]["gid://shopify/Product/777"]
        self.assertEqual(baseline["baseline_next_number"], 14)
        self.assertEqual(baseline["baseline_sold_count"], 13)
        self.assertEqual(baseline["baseline_remaining"], 87)

    def test_paid_order_allocator_skips_pre_cutover_orders_for_historical_backfill(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            self.fail("Pre-cutover orders must not read product metafields or allocate forward.")

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
        ) as order_sync, patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as product_sync:
            result = order_allocator.process_shopify_order_for_editions(
                order_payload,
                config=self.config,
                require_cutover=True,
                cutover_state={
                    "automation_started_at": "2026-06-23T00:00:00Z",
                    "baselines": {
                        "gid://shopify/Product/777": {
                            "product_gid": "gid://shopify/Product/777",
                            "baseline_next_number": 13,
                        }
                    },
                },
            )

        self.assertTrue(result["processed"])
        self.assertEqual(result["assignments_created"], 0)
        self.assertEqual(result["issues"][0]["status"], "Historical - Backfill required")
        self.assertIn("before the live allocation cutover", result["reason"])
        order_sync.assert_not_called()
        product_sync.assert_not_called()

    def test_paid_order_allocator_allocates_after_cutover_when_requested(self):
        order_payload = {
            "id": 1234,
            "name": "#SC9999",
            "financial_status": "paid",
            "processed_at": "2026-06-23T10:00:00Z",
            "created_at": "2026-06-23T09:55:00Z",
            "line_items": [{"id": 555, "product_id": 777, "title": "Justin Gaethje", "quantity": 1}],
        }

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id == "gid://shopify/Order/1234":
                return {"metafields": [], "api_version": "2026-04"}
            return {
                "metafields": [
                    {"namespace": "sports_cave", "key": "edition_enabled", "type": "boolean", "value": "true"},
                    {"namespace": "sports_cave", "key": "edition_total", "type": "number_integer", "value": "100"},
                    {"namespace": "sports_cave", "key": "edition_next_number", "type": "number_integer", "value": "13"},
                    {"namespace": "sports_cave", "key": "edition_sold_count", "type": "number_integer", "value": "12"},
                    {"namespace": "sports_cave", "key": "edition_remaining", "type": "number_integer", "value": "88"},
                    {"namespace": "sports_cave", "key": "edition_label", "type": "single_line_text_field", "value": "Numbered Edition"},
                ],
                "api_version": "2026-04",
            }

        order_writes = []
        product_writes = []
        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_gid, allocations, compare_digest=None, config=None, request_post=None: order_writes.append(allocations),
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
            side_effect=lambda products, config=None, request_post=None: product_writes.extend(products),
        ):
            result = order_allocator.process_shopify_order_for_editions(
                order_payload,
                config=self.config,
                require_cutover=True,
                cutover_state={
                    "automation_started_at": "2026-06-23T00:00:00Z",
                    "baselines": {
                        "gid://shopify/Product/777": {
                            "product_gid": "gid://shopify/Product/777",
                            "baseline_next_number": 13,
                        }
                    },
                },
            )

        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(order_writes[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [13])
        self.assertEqual(product_writes[0]["edition_next_number"], 14)

    def test_historical_backfill_assigns_backwards_without_product_counter_updates(self):
        rows = [
            {
                "order": "#SC2832",
                "processed_at": "2026-06-20T10:00:00Z",
                "created_at": "2026-06-20T09:55:00Z",
                "shopify_order_id": "gid://shopify/Order/2832",
                "shopify_line_item_id": "gid://shopify/LineItem/832",
                "shopify_product_id": "gid://shopify/Product/777",
                "product": "Justin Gaethje Undisputed Wall Art",
                "variant": "Black / XL",
                "line_quantity": 1,
                "edition_offset": 0,
                "edition": "Needs allocation",
            },
            {
                "order": "#SC2834",
                "processed_at": "2026-06-20T12:00:00Z",
                "created_at": "2026-06-20T11:55:00Z",
                "shopify_order_id": "gid://shopify/Order/2834",
                "shopify_line_item_id": "gid://shopify/LineItem/834",
                "shopify_product_id": "gid://shopify/Product/777",
                "product": "Justin Gaethje Undisputed Wall Art",
                "variant": "Black / XL",
                "line_quantity": 1,
                "edition_offset": 0,
                "edition": "Needs allocation",
            },
            {
                "order": "#SC2837",
                "processed_at": "2026-06-21T10:00:00Z",
                "created_at": "2026-06-21T09:55:00Z",
                "shopify_order_id": "gid://shopify/Order/2837",
                "shopify_line_item_id": "gid://shopify/LineItem/837",
                "shopify_product_id": "gid://shopify/Product/777",
                "product": "Justin Gaethje Undisputed Wall Art",
                "variant": "Black / XL",
                "line_quantity": 1,
                "edition_offset": 0,
                "edition": "Needs allocation",
            },
        ]
        order_writes = {}

        def fake_fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
            if owner_id.startswith("gid://shopify/Order/"):
                return {"metafields": [], "api_version": "2026-04"}
            self.fail("Historical backfill must not fetch product metafields.")

        def fake_order_sync(order_gid, allocations, compare_digest=None, config=None, request_post=None):
            order_writes[order_gid] = allocations

        with patch.object(shopify_sync, "fetch_metafields", side_effect=fake_fetch_metafields), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=fake_order_sync,
        ), patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as product_sync:
            result = order_allocator.historical_backfill_order_rows(
                rows,
                config=self.config,
                cutover_state={
                    "automation_started_at": "2026-06-23T00:00:00Z",
                    "baselines": {
                        "gid://shopify/Product/777": {
                            "product_gid": "gid://shopify/Product/777",
                            "baseline_next_number": 14,
                            "baseline_sold_count": 13,
                            "baseline_remaining": 87,
                        }
                    },
                },
            )

        self.assertEqual(result["assignments_created"], 3)
        self.assertEqual([row["edition_number"] for row in result["assigned_rows"]], [11, 12, 13])
        self.assertEqual(
            order_writes["gid://shopify/Order/2832"]["line_items"]["gid://shopify/LineItem/832"]["edition_numbers"],
            [11],
        )
        self.assertEqual(
            order_writes["gid://shopify/Order/2834"]["line_items"]["gid://shopify/LineItem/834"]["edition_numbers"],
            [12],
        )
        self.assertEqual(
            order_writes["gid://shopify/Order/2837"]["line_items"]["gid://shopify/LineItem/837"]["edition_numbers"],
            [13],
        )
        product_sync.assert_not_called()

    def test_historical_backfill_skips_post_cutover_rows(self):
        rows = [
            {
                "order": "#SC2999",
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
                "shopify_order_id": "gid://shopify/Order/2999",
                "shopify_line_item_id": "gid://shopify/LineItem/999",
                "shopify_product_id": "gid://shopify/Product/777",
                "product": "Justin Gaethje Undisputed Wall Art",
                "variant": "Black / XL",
                "line_quantity": 1,
                "edition_offset": 0,
                "edition": "Needs allocation",
            }
        ]

        with patch.object(
            shopify_sync,
            "fetch_metafields",
            return_value={"metafields": [], "api_version": "2026-04"},
        ), patch.object(
            shopify_sync,
            "sync_order_allocation_metafield",
        ) as order_sync, patch.object(
            shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as product_sync:
            result = order_allocator.historical_backfill_order_rows(
                rows,
                config=self.config,
                cutover_state={
                    "automation_started_at": "2026-06-23T00:00:00Z",
                    "baselines": {
                        "gid://shopify/Product/777": {
                            "product_gid": "gid://shopify/Product/777",
                            "baseline_next_number": 14,
                        }
                    },
                },
            )

        self.assertEqual(result["assignments_created"], 0)
        self.assertEqual(result["skipped_not_historical"], 1)
        self.assertEqual(result["assigned_rows"], [])
        order_sync.assert_not_called()
        product_sync.assert_not_called()

    def test_connection_and_product_page_parsing(self):
        responses = [
            FakeResponse(
                {
                    "data": {
                        "shop": {
                            "id": "gid://shopify/Shop/1",
                            "name": "Sports Cave",
                            "myshopifyDomain": "sports-cave.myshopify.com",
                            "primaryDomain": {"host": "sportscaveshop.com", "url": "https://sportscaveshop.com"},
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "products": {
                            "pageInfo": {"hasNextPage": False, "endCursor": "cursor-1"},
                            "nodes": [
                                {
                                    "id": "gid://shopify/Product/123",
                                    "legacyResourceId": "123",
                                    "title": "All Rise Wall Art",
                                    "handle": "all-rise-wall-art",
                                    "status": "ACTIVE",
                                    "vendor": "Sports Cave",
                                    "productType": "Wall Art",
                                    "tags": ["Baseball"],
                                    "updatedAt": "2026-06-13T00:00:00Z",
                                    "onlineStoreUrl": "https://sportscaveshop.com/products/all-rise-wall-art",
                                    "media": {"nodes": []},
                                    "variants": {
                                        "nodes": [
                                            {
                                                "id": "gid://shopify/ProductVariant/456",
                                                "legacyResourceId": "456",
                                                "title": "Black / XL",
                                                "sku": "ALL-RISE-BLACK-XL",
                                                "price": "149.00",
                                                "inventoryQuantity": 10,
                                                "selectedOptions": [
                                                    {"name": "Frame", "value": "Black"},
                                                    {"name": "Size", "value": "XL"},
                                                ],
                                            }
                                        ]
                                    },
                                    "collections": {"nodes": []},
                                    "metafields": {"nodes": []},
                                }
                            ],
                        }
                    }
                }
            ),
        ]

        def fake_post(*args, **kwargs):
            return responses.pop(0)

        shop = shopify_sync.test_connection(config=self.config, request_post=fake_post)
        page = shopify_sync.fetch_catalog_page(config=self.config, request_post=fake_post)

        self.assertEqual(shop["name"], "Sports Cave")
        self.assertEqual(page["products"][0]["variants"][0]["title"], "Black / XL")
        self.assertEqual(
            page["products"][0]["admin_url"],
            "https://admin.shopify.com/store/sports-cave/products/123",
        )

    def test_limited_edition_product_search_is_small_and_metafield_only(self):
        requests_seen = []

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return FakeResponse(
                {
                    "data": {
                        "products": {
                            "pageInfo": {"hasNextPage": False, "endCursor": "cursor-1"},
                            "nodes": [
                                {
                                    "id": "gid://shopify/Product/123",
                                    "legacyResourceId": "123",
                                    "title": "All Rise Wall Art",
                                    "handle": "all-rise-wall-art",
                                    "status": "ACTIVE",
                                    "media": {
                                        "nodes": [
                                            {
                                                "id": "gid://shopify/MediaImage/1",
                                                "alt": "All Rise",
                                                "image": {
                                                    "url": "https://cdn.shopify.com/product.webp",
                                                    "width": 800,
                                                    "height": 800,
                                                },
                                            }
                                        ]
                                    },
                                    "metafields": {
                                        "nodes": [
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_enabled",
                                                "type": "boolean",
                                                "value": "true",
                                            },
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_total",
                                                "type": "number_integer",
                                                "value": "100",
                                            },
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_next_number",
                                                "type": "number_integer",
                                                "value": "96",
                                            },
                                        ]
                                    },
                                }
                            ],
                        }
                    }
                }
            )

        page = shopify_sync.fetch_limited_edition_products_page(
            search="all rise",
            page_size=50,
            config=self.config,
            request_post=fake_post,
        )

        query = requests_seen[0]["query"]
        self.assertNotIn("variants(", query)
        self.assertNotIn("collections(", query)
        self.assertIn('metafields(first: 10, namespace: "sports_cave")', query)
        self.assertEqual(requests_seen[0]["variables"]["first"], 50)
        product = page["products"][0]
        self.assertEqual(product["title"], "All Rise Wall Art")
        self.assertEqual(product["thumbnail_url"], "https://cdn.shopify.com/product.webp")
        self.assertTrue(product["edition"]["edition_enabled"])
        self.assertEqual(product["edition"]["remaining"], 5)

    def test_edition_ops_active_products_are_active_only_and_lightweight(self):
        requests_seen = []

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return FakeResponse(
                {
                    "data": {
                        "products": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "gid://shopify/Product/123",
                                    "legacyResourceId": "123",
                                    "title": "All Rise Wall Art",
                                    "handle": "all-rise-wall-art",
                                    "status": "ACTIVE",
                                    "onlineStoreUrl": "https://sportscaveshop.com/products/all-rise-wall-art",
                                    "media": {
                                        "nodes": [
                                            {
                                                "image": {
                                                    "url": "https://cdn.shopify.com/product.webp",
                                                }
                                            }
                                        ]
                                    },
                                    "metafields": {
                                        "nodes": [
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_enabled",
                                                "type": "boolean",
                                                "value": "true",
                                            },
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_total",
                                                "type": "number_integer",
                                                "value": "100",
                                            },
                                            {
                                                "namespace": "sports_cave",
                                                "key": "edition_next_number",
                                                "type": "number_integer",
                                                "value": "53",
                                            },
                                        ]
                                    },
                                }
                            ],
                        }
                    }
                }
            )

        result = shopify_sync.fetch_edition_ops_active_products(
            max_products=500,
            page_size=50,
            config=self.config,
            request_post=fake_post,
        )

        request = requests_seen[0]
        self.assertEqual(request["variables"]["query"], "status:active")
        self.assertEqual(request["variables"]["first"], 50)
        self.assertIn("sortKey: TITLE", request["query"])
        self.assertIn("onlineStoreUrl", request["query"])
        self.assertIn('metafields(first: 20, namespace: "sports_cave")', request["query"])
        self.assertNotIn("variants(", request["query"])
        self.assertNotIn("collections(", request["query"])
        product = result["products"][0]
        self.assertEqual(product["online_store_url"], "https://sportscaveshop.com/products/all-rise-wall-art")
        self.assertEqual(product["edition"]["remaining"], 48)

    def test_edition_ops_sync_batches_three_products_per_metafields_set(self):
        requests_seen = []

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return FakeResponse(
                {
                    "data": {
                        "metafieldsSet": {
                            "metafields": [],
                            "userErrors": [],
                        }
                    }
                }
            )

        rows = [
            {
                "shopify_product_id": f"gid://shopify/Product/{index}",
                "title": f"Product {index}",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": index,
                "edition_label": "Numbered Edition",
            }
            for index in range(1, 8)
        ]

        result = shopify_sync.sync_limited_edition_metafields_for_products(
            rows,
            config=self.config,
            request_post=fake_post,
        )

        self.assertEqual(result["synced"], 7)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(requests_seen), 3)
        self.assertEqual(len(requests_seen[0]["variables"]["metafields"]), 21)
        self.assertEqual(len(requests_seen[1]["variables"]["metafields"]), 21)
        self.assertEqual(len(requests_seen[2]["variables"]["metafields"]), 7)

    def test_edition_ops_metafield_definition_check_and_create_missing(self):
        requests_seen = []
        responses = [
            FakeResponse(
                {
                    "data": {
                        "metafieldDefinitions": {
                            "nodes": [
                                {
                                    "id": "gid://shopify/MetafieldDefinition/1",
                                    "name": "Sports Cave Edition Enabled",
                                    "namespace": "sports_cave",
                                    "key": "edition_enabled",
                                    "ownerType": "PRODUCT",
                                    "type": {"name": "boolean"},
                                }
                            ]
                        }
                    }
                }
            ),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "2"}, "userErrors": []}}}),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "3"}, "userErrors": []}}}),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "4"}, "userErrors": []}}}),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "5"}, "userErrors": []}}}),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "6"}, "userErrors": []}}}),
            FakeResponse({"data": {"metafieldDefinitionCreate": {"createdDefinition": {"id": "7"}, "userErrors": []}}}),
            FakeResponse(
                {
                    "data": {
                        "metafieldDefinitions": {
                            "nodes": [
                                {
                                    "id": "gid://shopify/MetafieldDefinition/1",
                                    "name": definition["name"],
                                    "namespace": definition["namespace"],
                                    "key": definition["key"],
                                    "ownerType": definition["ownerType"],
                                    "type": {"name": definition["type"]},
                                }
                                for definition in shopify_sync.EDITION_OPS_METAFIELD_DEFINITIONS
                            ]
                        }
                    }
                }
            ),
        ]

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return responses.pop(0)

        result = shopify_sync.create_missing_edition_ops_metafield_definitions(
            config=self.config,
            request_post=fake_post,
        )

        self.assertEqual(len(result["created"]), 6)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["definitions"][0]["status"], "Ready")
        create_requests = [request for request in requests_seen if "metafieldDefinitionCreate" in request["query"]]
        self.assertEqual(len(create_requests), 6)
        created_keys = {request["variables"]["definition"]["key"] for request in create_requests}
        self.assertNotIn("edition_enabled", created_keys)
        self.assertIn("edition_next_number", created_keys)
        self.assertIn("edition_sold_count", created_keys)
        self.assertIn("edition_remaining", created_keys)
        self.assertIn("edition_status", created_keys)

    def test_limited_edition_metafields_save_exact_keys_and_readback(self):
        requests_seen = []
        responses = [
            FakeResponse(
                {
                    "data": {
                        "metafieldsSet": {
                            "metafields": [],
                            "userErrors": [],
                        }
                    }
                }
            ),
            FakeResponse(
                {
                    "data": {
                        "node": {
                            "id": "gid://shopify/Product/123",
                            "metafields": {
                                "nodes": [
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_enabled",
                                        "type": "boolean",
                                        "value": "true",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_total",
                                        "type": "number_integer",
                                        "value": "100",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_next_number",
                                        "type": "number_integer",
                                        "value": "98",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_sold_count",
                                        "type": "number_integer",
                                        "value": "97",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_remaining",
                                        "type": "number_integer",
                                        "value": "3",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_status",
                                        "type": "single_line_text_field",
                                        "value": "Final Editions",
                                    },
                                    {
                                        "namespace": "sports_cave",
                                        "key": "edition_label",
                                        "type": "single_line_text_field",
                                        "value": "Numbered Edition",
                                    },
                                ]
                            },
                        }
                    }
                }
            ),
        ]

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return responses.pop(0)

        result = shopify_sync.save_limited_edition_metafields(
            "gid://shopify/Product/123",
            {
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 98,
                "edition_label": "Numbered Edition",
            },
            config=self.config,
            request_post=fake_post,
        )

        inputs = requests_seen[0]["variables"]["metafields"]
        keys = {item["key"]: item for item in inputs}
        self.assertEqual(
            set(keys),
            {
                "edition_enabled",
                "edition_total",
                "edition_next_number",
                "edition_sold_count",
                "edition_remaining",
                "edition_status",
                "edition_label",
            },
        )
        self.assertEqual(keys["edition_enabled"]["type"], "boolean")
        self.assertEqual(keys["edition_enabled"]["value"], "true")
        self.assertEqual(keys["edition_sold_count"]["value"], "97")
        self.assertEqual(keys["edition_remaining"]["value"], "3")
        self.assertEqual(keys["edition_status"]["value"], "Final Editions")
        self.assertNotIn("remaining_count", keys)
        self.assertNotIn("sold_count", keys)
        self.assertEqual(result["edition"]["remaining"], 3)
        self.assertEqual(result["edition"]["edition_sold_count"], 97)
        self.assertEqual(result["edition"]["edition_status"], "Final Editions")

    def test_normalize_order_uses_customer_fallbacks(self):
        order = shopify_sync.normalize_order(
            {
                "id": "gid://shopify/Order/1",
                "legacyResourceId": "1",
                "name": "#1001",
                "createdAt": "2026-06-13T00:00:00Z",
                "processedAt": "2026-06-13T00:01:00Z",
                "displayFinancialStatus": "PAID",
                "displayFulfillmentStatus": "UNFULFILLED",
                "email": "fallback@example.com",
                "customer": {"displayName": "", "firstName": "", "lastName": "", "email": ""},
                "shippingAddress": {"name": "Shipping Collector", "firstName": "", "lastName": ""},
                "billingAddress": {"name": "Billing Collector", "firstName": "", "lastName": ""},
                "lineItems": {"nodes": []},
            },
            "sports-cave.myshopify.com",
        )

        self.assertEqual(order["customer_name"], "Shipping Collector")
        self.assertEqual(order["customer_email"], "fallback@example.com")
        self.assertEqual(order["customer_id"], "fallback@example.com")

    def test_build_orders_admin_url_targets_shopify_orders_index(self):
        self.assertEqual(
            shopify_sync.build_orders_admin_url("sports-cave.myshopify.com"),
            "https://admin.shopify.com/store/sports-cave/orders",
        )

    def test_normalize_order_prefers_shopify_customer_identity(self):
        order = shopify_sync.normalize_order(
            {
                "id": "gid://shopify/Order/2",
                "legacyResourceId": "2",
                "name": "#1002",
                "createdAt": "2026-06-13T00:00:00Z",
                "updatedAt": "2026-06-13T00:05:00Z",
                "processedAt": "2026-06-13T00:01:00Z",
                "displayFinancialStatus": "PAID",
                "displayFulfillmentStatus": "UNFULFILLED",
                "email": "order@example.com",
                "totalPriceSet": {"shopMoney": {"amount": "249.00", "currencyCode": "AUD"}},
                "shippingLine": {"title": "Express Shipping", "code": "EXPRESS"},
                "customer": {
                    "id": "gid://shopify/Customer/55",
                    "displayName": "Ada Collector",
                    "firstName": "Ada",
                    "lastName": "Collector",
                    "email": "ada@example.com",
                },
                "shippingAddress": {"name": "Shipping Name", "firstName": "", "lastName": ""},
                "billingAddress": {"name": "Billing Name", "firstName": "", "lastName": ""},
                "lineItems": {"nodes": []},
            },
            "sports-cave.myshopify.com",
        )

        self.assertEqual(order["customer_name"], "Ada Collector")
        self.assertEqual(order["customer_email"], "ada@example.com")
        self.assertEqual(order["customer_id"], "gid://shopify/Customer/55")
        self.assertEqual(order["remote_updated_at"], "2026-06-13T00:05:00Z")
        self.assertEqual(order["total_price"], "249.00")
        self.assertEqual(order["currency"], "AUD")
        self.assertEqual(order["customer_raw"]["displayName"], "Ada Collector")
        self.assertEqual(order["shipping_title"], "Express Shipping")
        self.assertEqual(order["shipping_method"], "Express Shipping")

    def test_orders_safe_query_still_requests_customer_fields(self):
        self.assertIn("customer {", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("shippingLine", shopify_sync.ORDERS_QUERY)
        self.assertIn("shippingLine", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("shippingLines(first: 1)", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("shippingAddress", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("billingAddress", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("email", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("updatedAt", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("totalPriceSet", shopify_sync.ORDERS_SAFE_QUERY)

    def test_latest_paid_sync_light_query_avoids_heavy_fields(self):
        self.assertIn("customer {", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertIn("shippingLine", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertIn("shippingAddress", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertIn("lineItems(first: 100)", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertNotIn("metafields(first: 20", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertNotIn("billingAddress", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertNotIn("totalPriceSet", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertNotIn("cancelledAt", shopify_sync.ORDERS_LIGHT_QUERY)
        self.assertNotIn("note", shopify_sync.ORDERS_LIGHT_QUERY)

    @patch.object(shopify_sync, "iter_order_pages")
    def test_fetch_latest_paid_orders_uses_paid_query_and_not_unfulfilled_filter(self, iter_order_pages):
        iter_order_pages.return_value = [{"orders": [{"order_name": "#SC3000"}]}]

        result = shopify_sync.fetch_latest_paid_orders(limit=50, lookback_days=14, config=self.config)

        self.assertEqual(result["orders"][0]["order_name"], "#SC3000")
        self.assertEqual(result["pages_fetched"], 1)
        self.assertEqual(result["line_items_fetched"], 0)
        self.assertEqual(result["metafields_fetched"], 0)
        self.assertEqual(iter_order_pages.call_args.kwargs["query"], "financial_status:paid")
        self.assertNotIn("created_at", iter_order_pages.call_args.kwargs["query"])
        self.assertNotIn("fulfillment_status:unfulfilled", iter_order_pages.call_args.kwargs["query"])
        self.assertEqual(iter_order_pages.call_args.kwargs["sort_key"], "CREATED_AT")
        self.assertTrue(iter_order_pages.call_args.kwargs["reverse"])
        self.assertFalse(iter_order_pages.call_args.kwargs["lightweight"])
        self.assertFalse(iter_order_pages.call_args.kwargs["default_paid_unfulfilled_filter"])

    @patch.object(shopify_sync, "iter_order_pages")
    def test_fetch_latest_paid_orders_uses_one_broad_paid_query(self, iter_order_pages):
        iter_order_pages.return_value = [{"orders": [{"order_name": "#SC3001"}]}]

        result = shopify_sync.fetch_latest_paid_orders(limit=50, lookback_days=14, config=self.config)

        self.assertEqual(result["orders"][0]["order_name"], "#SC3001")
        self.assertEqual(result["query"], "financial_status:paid")
        self.assertEqual(result["pages_fetched"], 1)
        self.assertEqual(iter_order_pages.call_count, 1)

    def test_snapshot_override_search_returns_recent_allocated_order_lines(self):
        rows = [
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 94,
                "edition": "#094",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
            },
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / M",
                "edition_number": 95,
                "edition": "#095",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8432",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
            },
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Black / L",
                "edition_number": 36,
                "edition": "#036",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8433",
                "shopify_product_id": "gid://shopify/Product/9002",
                "product_handle": "legends-never-die-messi-vs-ronaldo-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
            },
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Black / M",
                "edition_number": 37,
                "edition": "#037",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8434",
                "shopify_product_id": "gid://shopify/Product/9002",
                "product_handle": "legends-never-die-messi-vs-ronaldo-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            order_allocator,
            "SNAPSHOT_PATH",
            Path(tmpdir) / "orders_allocation_snapshot.json",
        ):
            order_allocator.save_orders_snapshot(rows, meta={"last_refreshed": "2026-06-23T10:01:00Z"})

            found = order_allocator.snapshot_allocated_order_rows("#SC2843", limit=50)

        self.assertEqual(len(found), 4)
        self.assertEqual([row["edition_number"] for row in found], [94, 95, 36, 37])
        self.assertTrue(all(row["certificate_status"] == "Certificate Generate" for row in found))
        self.assertTrue(all(str(row["id"]).startswith("snapshot|") for row in found))

    def test_datetime_normalizer_returns_timezone_aware_utc(self):
        naive = order_allocator.normalize_datetime_utc(datetime(2026, 6, 23, 10, 0))
        aware = order_allocator.normalize_datetime_utc("2026-06-23T20:00:00+10:00")
        bad = order_allocator.normalize_datetime_utc("not-a-date")

        self.assertEqual(naive.tzinfo, timezone.utc)
        self.assertEqual(naive.isoformat(), "2026-06-23T10:00:00+00:00")
        self.assertEqual(aware.isoformat(), "2026-06-23T10:00:00+00:00")
        self.assertEqual(bad, order_allocator.DATETIME_MIN_UTC)

    def test_snapshot_override_search_sorts_mixed_dates_without_crashing(self):
        rows = [
            {
                "order": "#SC3001",
                "customer": "Date Test",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 41,
                "edition": "#041",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/3001",
                "shopify_line_item_id": "gid://shopify/LineItem/3001",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "processed_at": "2026-06-23T20:00:00+10:00",
                "created_at": "2026-06-23T09:55:00",
            },
            {
                "order": "#SC3002",
                "customer": "Date Test",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / M",
                "edition_number": 42,
                "edition": "#042",
                "certificate": "Uploaded",
                "shopify_order_id": "gid://shopify/Order/3002",
                "shopify_line_item_id": "gid://shopify/LineItem/3002",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "processed_at": "2026-06-23T11:00:00",
                "created_at": "bad-date",
            },
            {
                "order": "#SC3000",
                "customer": "Date Test",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / S",
                "edition_number": 40,
                "edition": "#040",
                "certificate": "Certificate Ready",
                "shopify_order_id": "gid://shopify/Order/3000",
                "shopify_line_item_id": "gid://shopify/LineItem/3000",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "processed_at": "not-a-date",
                "created_at": "",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            order_allocator,
            "SNAPSHOT_PATH",
            Path(tmpdir) / "orders_allocation_snapshot.json",
        ):
            order_allocator.save_orders_snapshot(rows, meta={"last_refreshed": "2026-06-23T10:01:00Z"})

            found = order_allocator.snapshot_allocated_order_rows("GOAT", limit=50)

        self.assertEqual([row["shopify_order_name"] for row in found], ["#SC3002", "#SC3001", "#SC3000"])
        self.assertEqual([row["certificate_status"] for row in found], ["Uploaded", "Certificate Generate", "Certificate Ready"])

    def test_snapshot_manual_override_updates_only_selected_row_and_recalculates_product(self):
        rows = [
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 94,
                "edition": "#094",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
            },
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / M",
                "edition_number": 95,
                "edition": "#095",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8432",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_handle": "goat-debate-wall-art",
                "edition_offset": 0,
                "line_quantity": 1,
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            order_allocator,
            "SNAPSHOT_PATH",
            Path(tmpdir) / "orders_allocation_snapshot.json",
        ):
            order_allocator.save_orders_snapshot(rows, meta={"last_refreshed": "2026-06-23T10:01:00Z"})
            first, second = order_allocator.snapshot_allocated_order_rows("GOAT debate", limit=50)

            first_result = order_allocator.override_snapshot_allocation_row(first, 50, sync_shopify=False)
            second_result = order_allocator.override_snapshot_allocation_row(second, 51, sync_shopify=False)
            saved = order_allocator.load_orders_snapshot()["rows"]

        self.assertEqual(first_result["old_edition_number"], 94)
        self.assertEqual(second_result["old_edition_number"], 95)
        self.assertEqual([row["edition_number"] for row in saved], [50, 51])
        self.assertEqual([row["edition"] for row in saved], ["#050", "#051"])
        self.assertEqual(second_result["product"]["next_edition_number"], 52)
        self.assertEqual(second_result["product"]["remaining_count"], 49)
        self.assertTrue(all(row["certificate"] == "Generate" for row in saved))


class SupabaseProductSyncLogicTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Admin access token mode",
            "configured": True,
        }

    @patch.object(supabase_backend, "finish_sync_run")
    @patch.object(supabase_backend, "start_sync_run", return_value="run-1")
    @patch.object(supabase_backend, "_set_sync_success")
    @patch.object(supabase_backend, "_set_sync_attempt")
    @patch.object(supabase_backend, "count_shopify_products", return_value=0)
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={
            "last_successful_product_sync_at": "",
            "sync_lookback_buffer_minutes": 10,
        },
    )
    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(supabase_backend.shopify_sync, "iter_catalog_pages")
    @patch.object(supabase_backend, "upsert_products", return_value=1)
    @patch.object(
        supabase_backend,
        "sync_product_edition_metafields_for_handles",
        return_value={"attempted": 1, "synced": 1, "skipped": 0, "errors": []},
    )
    def test_incremental_product_sync_bootstraps_full_catalog_when_empty(
        self,
        metafield_sync,
        upsert_products,
        iter_catalog_pages,
        _ensure_schema,
        _sync_state,
        _count_products,
        _set_attempt,
        _set_success,
        start_sync_run,
        _finish_run,
    ):
        iter_catalog_pages.return_value = [
            {
                "products": [
                    {
                        "handle": "messi-the-final-crown-wall-art",
                        "title": "Messi The Final Crown Wall Art",
                    }
                ]
            }
        ]

        result = supabase_backend.sync_shopify_products_to_supabase(config=self.config, mode="incremental")

        self.assertEqual(result["mode"], "full")
        self.assertTrue(result["bootstrap_full_sync"])
        start_sync_run.assert_called_once_with("shopify_products_full")
        self.assertEqual(iter_catalog_pages.call_args.kwargs["search"], "status:active")
        upsert_products.assert_called_once()
        metafield_sync.assert_called_once()

    def test_new_shopify_product_plans_insert_with_default_edition_values(self):
        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "legacy_resource_id": "100",
            "handle": "new-wall-art",
            "title": "New Wall Art",
            "status": "ACTIVE",
            "images": [{"url": "https://cdn.example/new.jpg"}],
        }

        actions = supabase_backend._plan_edition_product_incremental_sync([product], [])

        self.assertEqual(actions[0]["action"], "insert")
        self.assertEqual(actions[0]["fields"]["shopify_handle"], "new-wall-art")

        class CaptureCursor:
            def execute(self, sql, params=None):
                self.sql = sql
                self.params = params

            def fetchone(self):
                return {"shopify_handle": "new-wall-art"}

        cursor = CaptureCursor()
        supabase_backend._insert_edition_product_from_shopify(cursor, actions[0]["fields"])
        self.assertIn("100, 1, 0, 0, 100", cursor.sql)

    def test_existing_product_is_not_duplicated_when_unchanged(self):
        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "handle": "existing-wall-art",
            "title": "Existing Wall Art",
            "status": "ACTIVE",
            "images": [{"url": "https://cdn.example/existing.jpg"}],
        }
        existing = {
            "id": "1",
            "shopify_product_id": "gid://shopify/Product/100",
            "shopify_product_gid": "gid://shopify/Product/100",
            "shopify_handle": "existing-wall-art",
            "product_title": "Existing Wall Art",
            "active": True,
            "is_active": True,
            "featured_image_url": "https://cdn.example/existing.jpg",
            "next_edition_number": 43,
        }

        actions = supabase_backend._plan_edition_product_incremental_sync([product], [existing])

        self.assertEqual(actions[0]["action"], "skip")

    def test_existing_next_edition_number_is_never_reset_by_product_sync(self):
        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "handle": "existing-wall-art",
            "title": "Existing Wall Art Updated",
            "status": "ACTIVE",
        }
        existing = {
            "id": "1",
            "shopify_product_id": "gid://shopify/Product/100",
            "shopify_product_gid": "gid://shopify/Product/100",
            "shopify_handle": "existing-wall-art",
            "product_title": "Existing Wall Art",
            "active": True,
            "is_active": True,
            "featured_image_url": "",
            "next_edition_number": 43,
            "edition_total": 100,
            "sold_count": 42,
            "remaining_count": 58,
        }

        actions = supabase_backend._plan_edition_product_incremental_sync([product], [existing])

        self.assertEqual(actions[0]["action"], "update")
        self.assertEqual(actions[0]["fields"]["product_title"], "Existing Wall Art Updated")
        self.assertNotIn("next_edition_number", actions[0]["fields"])
        self.assertNotIn("edition_total", actions[0]["fields"])
        self.assertNotIn("sold_count", actions[0]["fields"])
        self.assertNotIn("remaining_count", actions[0]["fields"])

    def test_handle_change_updates_existing_row_by_shopify_product_id(self):
        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "handle": "new-handle",
            "title": "Existing Wall Art",
            "status": "ACTIVE",
        }
        existing = {
            "id": "1",
            "shopify_product_id": "gid://shopify/Product/100",
            "shopify_product_gid": "gid://shopify/Product/100",
            "shopify_handle": "old-handle",
            "product_title": "Existing Wall Art",
            "active": True,
            "is_active": True,
            "featured_image_url": "",
        }

        actions = supabase_backend._plan_edition_product_incremental_sync([product], [existing])

        self.assertEqual(actions[0]["action"], "update")
        self.assertEqual(actions[0]["match_type"], "shopify_product_id")
        self.assertEqual(actions[0]["fields"]["shopify_handle"], "new-handle")

    def test_product_create_webhook_inserts_new_product_with_next_number_one(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        class CaptureCursor:
            def execute(self, sql, params=None):
                self.sql = sql
                self.params = params

            def fetchone(self):
                return {"shopify_handle": "new-wall-art"}

        payload = {
            "id": 100,
            "admin_graphql_api_id": "gid://shopify/Product/100",
            "handle": "new-wall-art",
            "title": "New Wall Art",
            "status": "active",
            "created_at": "2026-07-02T00:00:00Z",
            "updated_at": "2026-07-02T00:00:00Z",
            "image": {"src": "https://cdn.example/new.jpg"},
            "variants": [{"id": 200, "title": "Default", "sku": "NEW-ART", "price": "100.00"}],
        }

        def apply_plan(_cur, actions):
            self.assertEqual(actions[0]["action"], "insert")
            self.assertEqual(actions[0]["fields"]["shopify_handle"], "new-wall-art")
            self.assertEqual(actions[0]["fields"]["featured_image_url"], "https://cdn.example/new.jpg")
            capture = CaptureCursor()
            supabase_backend._insert_edition_product_from_shopify(capture, actions[0]["fields"])
            self.assertIn("100, 1, 0, 0, 100, 'limited_release'", capture.sql)
            return {
                "new_products_inserted": 1,
                "existing_products_updated": 0,
                "existing_products_skipped": 0,
                "variant_sync_errors": [],
                "errors": [],
                "inserted_handles": ["new-wall-art"],
                "updated_handles": [],
            }

        with patch.object(supabase_backend, "_update_webhook_event_status"), patch.object(
            supabase_backend,
            "connect",
            return_value=FakeConnection(),
        ), patch.object(
            supabase_backend,
            "_candidate_edition_products_for_shopify_products",
            return_value=[],
        ), patch.object(
            supabase_backend,
            "_apply_edition_product_incremental_plan",
            side_effect=apply_plan,
        ), patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            return_value={"attempted": 1, "synced": 1, "skipped": 0, "errors": [], "results": []},
        ) as mirror:
            result = supabase_backend.process_product_create_webhook(
                payload,
                "product-webhook-100",
                "products/create",
                claim_event=False,
                config=self.config,
            )

        self.assertEqual(result["new_products_inserted"], 1)
        self.assertEqual(result["shopify_metafields_pushed"], 1)
        mirror.assert_called_once_with(["new-wall-art"], config=self.config, ensure_schema_first=False)

    def test_product_create_webhook_existing_product_is_not_duplicated(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        payload = {
            "id": 100,
            "admin_graphql_api_id": "gid://shopify/Product/100",
            "handle": "existing-wall-art",
            "title": "Existing Wall Art",
            "status": "active",
        }
        existing = {
            "id": "1",
            "shopify_product_id": "gid://shopify/Product/100",
            "shopify_product_gid": "gid://shopify/Product/100",
            "shopify_handle": "existing-wall-art",
            "product_title": "Existing Wall Art",
            "active": True,
            "is_active": True,
            "featured_image_url": "",
            "next_edition_number": 43,
            "edition_total": 100,
            "sold_count": 42,
            "remaining_count": 58,
        }

        def apply_plan(_cur, actions):
            self.assertEqual(actions[0]["action"], "skip")
            return {
                "new_products_inserted": 0,
                "existing_products_updated": 0,
                "existing_products_skipped": 1,
                "variant_sync_errors": [],
                "errors": [],
                "inserted_handles": [],
                "updated_handles": [],
            }

        with patch.object(supabase_backend, "_update_webhook_event_status"), patch.object(
            supabase_backend,
            "connect",
            return_value=FakeConnection(),
        ), patch.object(
            supabase_backend,
            "_candidate_edition_products_for_shopify_products",
            return_value=[existing],
        ), patch.object(
            supabase_backend,
            "_apply_edition_product_incremental_plan",
            side_effect=apply_plan,
        ), patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
        ) as mirror:
            result = supabase_backend.process_product_create_webhook(
                payload,
                "product-webhook-100",
                "products/create",
                claim_event=False,
                config=self.config,
            )

        self.assertEqual(result["new_products_inserted"], 0)
        self.assertEqual(result["existing_products_skipped"], 1)
        mirror.assert_not_called()

    def test_product_create_webhook_handle_change_matches_by_product_id_without_resetting_counters(self):
        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "handle": "new-handle",
            "title": "Existing Wall Art",
            "status": "ACTIVE",
        }
        existing = {
            "id": "1",
            "shopify_product_id": "gid://shopify/Product/100",
            "shopify_product_gid": "gid://shopify/Product/100",
            "shopify_handle": "old-handle",
            "product_title": "Existing Wall Art",
            "active": True,
            "is_active": True,
            "featured_image_url": "",
            "next_edition_number": 43,
            "edition_total": 100,
            "sold_count": 42,
            "remaining_count": 58,
        }

        actions = supabase_backend._plan_edition_product_incremental_sync([product], [existing])

        self.assertEqual(actions[0]["action"], "update")
        self.assertEqual(actions[0]["match_type"], "shopify_product_id")
        self.assertEqual(actions[0]["fields"]["shopify_handle"], "new-handle")
        self.assertNotIn("next_edition_number", actions[0]["fields"])
        self.assertNotIn("edition_total", actions[0]["fields"])
        self.assertNotIn("sold_count", actions[0]["fields"])
        self.assertNotIn("remaining_count", actions[0]["fields"])

    def test_product_create_webhook_metafield_failure_keeps_supabase_row_and_marks_failed(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        payload = {
            "id": 100,
            "admin_graphql_api_id": "gid://shopify/Product/100",
            "handle": "new-wall-art",
            "title": "New Wall Art",
            "status": "active",
        }
        apply_summary = {
            "new_products_inserted": 1,
            "existing_products_updated": 0,
            "existing_products_skipped": 0,
            "variant_sync_errors": [],
            "errors": [],
            "inserted_handles": ["new-wall-art"],
            "updated_handles": [],
        }

        with patch.object(supabase_backend, "_update_webhook_event_status"), patch.object(
            supabase_backend,
            "connect",
            return_value=FakeConnection(),
        ), patch.object(
            supabase_backend,
            "_candidate_edition_products_for_shopify_products",
            return_value=[],
        ), patch.object(
            supabase_backend,
            "_apply_edition_product_incremental_plan",
            return_value=apply_summary,
        ), patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            side_effect=RuntimeError("Shopify unavailable"),
        ), patch.object(
            supabase_backend,
            "_mark_product_metafields_sync",
        ) as mark_failed:
            result = supabase_backend.process_product_create_webhook(
                payload,
                "product-webhook-100",
                "products/create",
                claim_event=False,
                config=self.config,
            )

        self.assertEqual(result["new_products_inserted"], 1)
        self.assertEqual(result["shopify_metafields_pushed"], 0)
        self.assertEqual(result["shopify_metafields_failed_pending"], 1)
        self.assertIn("Shopify unavailable", "\n".join(result["errors"]))
        mark_failed.assert_called_once()
        failed_payload = mark_failed.call_args.args[1]
        self.assertEqual(failed_payload["next_edition_number"], 1)
        self.assertEqual(failed_payload["edition_total"], 100)
        self.assertEqual(failed_payload["sold_count"], 0)
        self.assertEqual(failed_payload["remaining_count"], 100)
        self.assertEqual(failed_payload["edition_status"], "limited_release")

    def test_product_create_webhook_does_not_call_order_allocation_or_certificate_helpers(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        payload = {
            "id": 100,
            "admin_graphql_api_id": "gid://shopify/Product/100",
            "handle": "new-wall-art",
            "title": "New Wall Art",
            "status": "active",
        }
        with patch.object(supabase_backend, "_update_webhook_event_status"), patch.object(
            supabase_backend,
            "connect",
            return_value=FakeConnection(),
        ), patch.object(
            supabase_backend,
            "_candidate_edition_products_for_shopify_products",
            return_value=[],
        ), patch.object(
            supabase_backend,
            "_apply_edition_product_incremental_plan",
            return_value={
                "new_products_inserted": 0,
                "existing_products_updated": 0,
                "existing_products_skipped": 1,
                "variant_sync_errors": [],
                "errors": [],
                "inserted_handles": [],
                "updated_handles": [],
            },
        ), patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
        ) as mirror, patch.object(
            supabase_backend,
            "process_order_paid_webhook",
        ) as order_webhook, patch.object(
            supabase_backend,
            "process_shopify_order_for_editions",
        ) as allocation, patch.object(
            supabase_backend,
            "generate_certificate_pdf",
        ) as certificate:
            result = supabase_backend.process_product_create_webhook(
                payload,
                "product-webhook-100",
                "products/create",
                claim_event=False,
                config=self.config,
            )

        self.assertEqual(result["new_products_inserted"], 0)
        mirror.assert_not_called()
        order_webhook.assert_not_called()
        allocation.assert_not_called()
        certificate.assert_not_called()

    @patch.object(supabase_backend, "set_app_setting")
    @patch.object(supabase_backend, "sync_product_edition_metafields_for_handles")
    @patch.object(supabase_backend, "_apply_edition_product_incremental_plan")
    @patch.object(supabase_backend, "_candidate_edition_products_for_shopify_products", return_value=[])
    @patch.object(supabase_backend.shopify_sync, "iter_catalog_pages")
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={"last_successful_product_sync_at": "2026-07-01T00:00:00Z"},
    )
    @patch.object(supabase_backend, "finish_sync_run")
    @patch.object(supabase_backend, "start_sync_run", return_value="run-1")
    @patch.object(supabase_backend, "ensure_schema")
    def test_metafield_failure_does_not_rollback_supabase_product_insert(
        self,
        _ensure_schema,
        _start_sync_run,
        _finish_sync_run,
        _get_sync_state,
        iter_catalog_pages,
        _candidate_rows,
        apply_plan,
        metafield_sync,
        _set_app_setting,
    ):
        class FakeCursor:
            rowcount = 1

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, *args, **kwargs):
                return None

            def fetchone(self):
                return {}

            def fetchall(self):
                return []

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        product = {
            "shopify_product_id": "gid://shopify/Product/100",
            "handle": "new-wall-art",
            "title": "New Wall Art",
            "status": "ACTIVE",
        }
        iter_catalog_pages.return_value = [{"products": [product]}]
        apply_plan.return_value = {
            "new_products_inserted": 1,
            "existing_products_updated": 0,
            "existing_products_skipped": 0,
            "variant_sync_errors": [],
            "errors": [],
            "inserted_handles": ["new-wall-art"],
        }
        metafield_sync.return_value = {
            "attempted": 1,
            "synced": 0,
            "skipped": 1,
            "errors": ["new-wall-art: Shopify unavailable"],
        }

        with patch.object(supabase_backend, "connect", return_value=FakeConnection()):
            result = supabase_backend.sync_new_shopify_products_to_edition_ops(config=self.config)

        self.assertEqual(result["new_products_inserted"], 1)
        self.assertEqual(result["shopify_metafields_pushed"], 0)
        self.assertEqual(result["shopify_metafields_failed_pending"], 1)
        expected_config = dict(self.config)
        expected_config["max_products"] = 1000
        metafield_sync.assert_called_once_with(["new-wall-art"], config=expected_config)

    def test_shopify_metafield_mirror_preview_reads_without_writing(self):
        payload = {
            "id": "101",
            "shopify_handle": "legends-never-die",
            "shopify_product_gid": "gid://shopify/Product/777",
            "product_title": "Legends Never Die",
            "edition_total": 100,
            "next_edition_number": 43,
            "sold_count": 42,
            "remaining_count": 58,
            "edition_status": "limited_release",
            "edition_name": "Numbered Edition",
            "metafields_synced_at": "2026-06-30T00:00:00Z",
        }

        with patch.object(supabase_backend, "ensure_schema") as ensure_schema, patch.object(
            supabase_backend,
            "get_product_edition_metafield_payload",
            return_value=payload,
        ) as get_payload, patch.object(
            supabase_backend,
            "_fetch_public_edition_metafields",
            return_value={
                "metafields": [
                    {
                        "namespace": "sports_cave",
                        "key": "edition_next_number",
                        "type": "number_integer",
                        "value": "42",
                    }
                ],
                "error": "",
            },
        ), patch.object(
            supabase_backend.shopify_sync,
            "sync_limited_edition_metafields_for_products",
        ) as sync_limited:
            result = supabase_backend.preview_shopify_edition_metafield_mirror_for_handles(
                ["legends-never-die"],
                config=self.config,
            )

        ensure_schema.assert_called_once()
        get_payload.assert_called_once_with("legends-never-die", ensure_schema_first=False)
        sync_limited.assert_not_called()
        self.assertEqual(result["attempted"], 1)
        preview = result["previews"][0]
        self.assertEqual(preview["source_values"]["edition_next_number"], "43")
        next_change = [row for row in preview["changes"] if row["key"] == "edition_next_number"][0]
        self.assertEqual(next_change["shopify_before"], "42")
        self.assertEqual(next_change["supabase_after"], "43")
        self.assertTrue(next_change["will_update"])

    def test_shopify_metafield_mirror_attempt_records_audit(self):
        payload = {
            "id": "101",
            "shopify_handle": "legends-never-die",
            "shopify_product_id": "gid://shopify/Product/777",
            "shopify_product_gid": "gid://shopify/Product/777",
            "product_title": "Legends Never Die",
            "edition_total": 100,
            "next_edition_number": 43,
            "sold_count": 42,
            "remaining_count": 58,
            "edition_status": "limited_release",
            "edition_name": "Numbered Edition",
        }

        snapshots = [
            {
                "metafields": [
                    {
                        "namespace": "sports_cave",
                        "key": "edition_next_number",
                        "type": "number_integer",
                        "value": "42",
                    }
                ],
                "error": "",
            },
            {
                "metafields": [
                    {
                        "namespace": "sports_cave",
                        "key": "edition_next_number",
                        "type": "number_integer",
                        "value": "43",
                    }
                ],
                "error": "",
            },
        ]

        with patch.object(
            supabase_backend,
            "get_product_edition_metafield_payload",
            return_value=payload,
        ), patch.object(
            supabase_backend,
            "_fetch_public_edition_metafields",
            side_effect=snapshots,
        ), patch.object(
            supabase_backend.shopify_sync,
            "sync_limited_edition_metafields_for_products",
            return_value={"synced": 1, "failed": 0, "results": []},
        ) as sync_limited, patch.object(
            supabase_backend.shopify_sync,
            "sync_product_edition_metafields",
            return_value={"count": 8},
        ), patch.object(
            supabase_backend,
            "_mark_product_metafields_sync",
        ), patch.object(
            supabase_backend,
            "_record_product_metafield_mirror_audit",
        ) as audit_log:
            result = supabase_backend.sync_product_edition_metafields(
                "legends-never-die",
                config=self.config,
                ensure_schema_first=False,
            )

        sync_limited.assert_called_once()
        audit_log.assert_called_once()
        self.assertEqual(audit_log.call_args.args[0], "legends-never-die")
        self.assertEqual(audit_log.call_args.kwargs["status"], "updated")
        self.assertEqual(result["source_values"]["edition_next_number"], "43")


class SupabaseOrderSyncLogicTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
            "max_orders": 25,
            "auth_mode": "Admin access token mode",
            "configured": True,
        }

    def paid_order(
        self,
        *,
        processed_at,
        remote_updated_at,
        created_at="2026-06-01T00:00:00Z",
        order_id="gid://shopify/Order/1000",
        order_name="#1000",
        line_item_id="gid://shopify/LineItem/1",
        line_position=1,
    ):
        return {
            "shopify_order_id": order_id,
            "legacy_resource_id": order_id.rsplit("/", 1)[-1],
            "order_name": order_name,
            "order_number": order_name.lstrip("#"),
            "admin_url": f"https://admin.shopify.com/store/sports-cave/orders/{order_id.rsplit('/', 1)[-1]}",
            "created_at": created_at,
            "processed_at": processed_at,
            "remote_updated_at": remote_updated_at,
            "paid_at": processed_at,
            "financial_status": "PAID",
            "fulfillment_status": "UNFULFILLED",
            "customer_name": "Collector",
            "customer_email": "collector@example.com",
            "line_items": [
                {
                    "shopify_line_item_id": line_item_id,
                    "shopify_product_id": "gid://shopify/Product/999",
                    "product_title": "Messi The Final Crown Wall Art",
                    "product_handle": "messi-the-final-crown-wall-art",
                    "variant_title": "Black / XL",
                    "position": line_position,
                    "quantity": 1,
                }
            ],
        }

    class EditionProductCursor:
        def __init__(self, products, variants=None):
            self.products = products
            self.variants = variants or {}
            self.rows = []

        def execute(self, sql, params=()):
            if "ep.shopify_product_id = ANY" in sql:
                ids = set(params[0])
                self.rows = [
                    product
                    for product in self.products
                    if product.get("shopify_product_id") in ids or product.get("shopify_product_gid") in ids
                ]
            elif "FROM shopify_variants sv" in sql:
                variant_ids = set(params[0])
                product_ids = {
                    self.variants[variant_id]
                    for variant_id in variant_ids
                    if variant_id in self.variants
                }
                self.rows = [
                    product
                    for product in self.products
                    if product.get("shopify_product_id") in product_ids or product.get("shopify_product_gid") in product_ids
                ]
            elif "WHERE ep.shopify_handle=%s" in sql:
                handle = params[0]
                self.rows = [product for product in self.products if product.get("shopify_handle") == handle]
            elif "COALESCE(ep.product_title" in sql:
                self.rows = list(self.products)
            else:
                self.rows = []

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    def edition_product(self, **overrides):
        row = {
            "id": 1,
            "shopify_product_id": "gid://shopify/Product/999",
            "shopify_product_gid": "gid://shopify/Product/999",
            "shopify_handle": "cristiano-ronaldo-football-framed-wall-art",
            "product_title": "Cristiano Ronaldo The Captain's Last Dance Wall Art",
            "edition_total": 100,
            "next_edition_number": 75,
            "active": True,
            "is_active": True,
        }
        row.update(overrides)
        return row

    def test_edition_product_resolver_matches_by_product_id(self):
        cursor = self.EditionProductCursor([self.edition_product()])

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(
            cursor,
            {
                "shopify_product_id": "999",
                "product_title": "Different title",
            },
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["handle"], "cristiano-ronaldo-football-framed-wall-art")
        self.assertEqual(result["product"]["match_method"], "shopify_product_id")

    def test_edition_product_resolver_matches_by_handle(self):
        cursor = self.EditionProductCursor([self.edition_product(shopify_product_id="", shopify_product_gid="")])

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(
            cursor,
            {
                "product_handle": "cristiano-ronaldo-football-framed-wall-art",
                "product_title": "Different title",
            },
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["match_method"], "shopify_handle")

    def test_edition_product_resolver_matches_cristiano_by_normalized_title(self):
        cursor = self.EditionProductCursor(
            [
                self.edition_product(
                    shopify_product_id="",
                    shopify_product_gid="",
                    shopify_handle="cristiano-ronaldo-football-framed-wall-art",
                )
            ]
        )

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(
            cursor,
            {
                "shopify_product_id": "",
                "product_handle": "",
                "product_title": "Cristiano Ronaldo The Captain\u2019s Last Dance Wall Art",
            },
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["handle"], "cristiano-ronaldo-football-framed-wall-art")
        self.assertEqual(result["product"]["next_edition_number"], 75)
        self.assertEqual(result["product"]["match_method"], "normalized_product_title")

    def test_edition_product_resolver_blocks_ambiguous_normalized_title(self):
        cursor = self.EditionProductCursor(
            [
                self.edition_product(id=1, shopify_handle="cristiano-one"),
                self.edition_product(id=2, shopify_handle="cristiano-two"),
            ]
        )

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(
            cursor,
            {
                "shopify_product_id": "",
                "product_handle": "",
                "product_title": "Cristiano Ronaldo The Captain's Last Dance Wall Art",
            },
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertFalse(result["product"])

    def test_live_order_allocation_uses_edition_ops_resolver(self):
        process_source = inspect.getsource(supabase_backend.process_paid_order)
        repair_source = inspect.getsource(supabase_backend._known_missing_edition_repair_plan)
        preview_source = inspect.getsource(supabase_backend.preview_missing_edition_repairs)

        self.assertIn("resolve_edition_product_for_order_line", process_source)
        self.assertNotIn("resolve_product_for_line(\n                line_item", process_source)
        self.assertIn("_resolve_edition_product_for_order_line_with_cursor", repair_source)
        self.assertIn("_resolve_edition_product_for_order_line_with_cursor", preview_source)

    @patch.object(supabase_backend, "finish_sync_run")
    @patch.object(supabase_backend, "start_sync_run", return_value="run-1")
    @patch.object(supabase_backend, "_set_sync_success")
    @patch.object(supabase_backend, "_set_sync_attempt")
    @patch.object(supabase_backend, "set_app_setting")
    @patch.object(supabase_backend, "utc_now_datetime", return_value=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc))
    @patch.object(supabase_backend, "count_shopify_orders", return_value=0)
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={
            "last_successful_order_sync_at": "",
            "edition_tracking_start_at": "",
            "sync_lookback_buffer_minutes": 10,
        },
    )
    @patch.object(
        supabase_backend,
        "ensure_edition_tracking_start",
        return_value=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
    )
    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(supabase_backend.shopify_sync, "iter_order_pages")
    @patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set())
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(supabase_backend, "_record_order_fetch_metrics")
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    def test_initial_order_sync_bootstraps_recent_orders_window(
        self,
        process_shopify_order_for_editions,
        _record_order_fetch_metrics,
        _existing_line_ids,
        _existing_order_ids,
        iter_order_pages,
        _ensure_schema,
        _tracking_start,
        _sync_state,
        _count_orders,
        _utc_now,
        set_app_setting,
        _set_attempt,
        _set_success,
        start_run,
        _finish_run,
    ):
        recent_order = self.paid_order(
            processed_at="2026-06-19T00:05:00Z",
            remote_updated_at="2026-06-19T02:05:00Z",
        )
        iter_order_pages.return_value = [{"orders": [recent_order]}]
        process_shopify_order_for_editions.return_value = {
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 0,
            "changed_handles": [],
            "errors": [],
        }

        result = supabase_backend.sync_shopify_orders_to_supabase(config=self.config, max_orders=25)

        self.assertTrue(result["bootstrap_recent_orders"])
        self.assertEqual(result["orders_seen"], 1)
        self.assertEqual(result["orders_processed"], 1)
        self.assertEqual(result["historical_orders_synced"], 0)
        self.assertEqual(start_run.call_args.args[0], "shopify_orders_incremental")
        expected_sync_from = supabase_backend._datetime_to_shopify_query(
            datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
        )
        self.assertIn(expected_sync_from, iter_order_pages.call_args.kwargs["query"])
        self.assertIn("fulfillment_status:unfulfilled", iter_order_pages.call_args.kwargs["query"])
        _, kwargs = process_shopify_order_for_editions.call_args
        self.assertTrue(kwargs["assign_editions"])
        self.assertFalse(kwargs["generate_certificates"])
        self.assertEqual(kwargs["allocation_skip_reason"], "")
        set_app_setting.assert_any_call(
            supabase_backend.EDITION_TRACKING_START_KEY,
            supabase_backend._datetime_to_setting(datetime(2026, 6, 13, 0, 0, tzinfo=timezone.utc)),
        )

    @patch.object(supabase_backend, "finish_sync_run")
    @patch.object(supabase_backend, "start_sync_run", return_value="run-1")
    @patch.object(supabase_backend, "_set_sync_success")
    @patch.object(supabase_backend, "_set_sync_attempt")
    @patch.object(supabase_backend, "set_app_setting")
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={
            "last_successful_order_sync_at": "2026-06-16T02:00:00Z",
            "edition_tracking_start_at": "2026-06-16T01:00:00Z",
            "sync_lookback_buffer_minutes": 10,
        },
    )
    @patch.object(
        supabase_backend,
        "ensure_edition_tracking_start",
        return_value=datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc),
    )
    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(supabase_backend.shopify_sync, "iter_order_pages")
    @patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set())
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(supabase_backend, "_record_order_fetch_metrics")
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    def test_incremental_sync_keeps_historical_updates_but_skips_auto_assignment(
        self,
        process_shopify_order_for_editions,
        _record_order_fetch_metrics,
        _existing_line_ids,
        _existing_order_ids,
        iter_order_pages,
        _ensure_schema,
        _tracking_start,
        _sync_state,
        _set_app_setting,
        _set_attempt,
        _set_success,
        _start_run,
        _finish_run,
    ):
        historical_order = self.paid_order(
            processed_at="2026-06-01T00:05:00Z",
            remote_updated_at="2026-06-16T02:05:00Z",
        )
        iter_order_pages.return_value = [{"orders": [historical_order]}]
        process_shopify_order_for_editions.return_value = {
            "assignments_created": 0,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 1,
            "changed_handles": [],
            "errors": [],
        }

        result = supabase_backend.sync_shopify_orders_to_supabase(config=self.config, max_orders=25)

        self.assertEqual(result["orders_seen"], 1)
        self.assertEqual(result["orders_processed"], 1)
        self.assertEqual(result["historical_orders_synced"], 1)
        self.assertIn("fulfillment_status:unfulfilled", iter_order_pages.call_args.kwargs["query"])
        _, kwargs = process_shopify_order_for_editions.call_args
        self.assertFalse(kwargs["assign_editions"])
        self.assertFalse(kwargs["generate_certificates"])
        self.assertEqual(kwargs["allocation_skip_reason"], supabase_backend.HISTORICAL_ORDER_NOTE)

    @patch.object(supabase_backend, "finish_sync_run")
    @patch.object(supabase_backend, "start_sync_run", return_value="run-1")
    @patch.object(supabase_backend, "_set_sync_success")
    @patch.object(supabase_backend, "_set_sync_attempt")
    @patch.object(supabase_backend, "set_app_setting")
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={
            "last_successful_order_sync_at": "2026-06-16T02:00:00Z",
            "edition_tracking_start_at": "2026-06-01T00:00:00Z",
            "sync_lookback_buffer_minutes": 10,
        },
    )
    @patch.object(
        supabase_backend,
        "ensure_edition_tracking_start",
        return_value=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(supabase_backend.shopify_sync, "iter_order_pages")
    @patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set())
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(supabase_backend, "_record_order_fetch_metrics")
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    def test_supabase_order_sync_allocates_newest_first_response_oldest_first(
        self,
        process_shopify_order_for_editions,
        _record_order_fetch_metrics,
        _existing_line_ids,
        _existing_order_ids,
        iter_order_pages,
        _ensure_schema,
        _tracking_start,
        _sync_state,
        _set_app_setting,
        _set_attempt,
        _set_success,
        _start_run,
        _finish_run,
    ):
        newer_order = self.paid_order(
            order_id="gid://shopify/Order/1002",
            order_name="#1002",
            line_item_id="gid://shopify/LineItem/2002",
            created_at="2026-06-18T00:00:00Z",
            processed_at="2026-06-18T00:05:00Z",
            remote_updated_at="2026-06-19T02:00:00Z",
        )
        older_order = self.paid_order(
            order_id="gid://shopify/Order/1001",
            order_name="#1001",
            line_item_id="gid://shopify/LineItem/2001",
            created_at="2026-06-17T00:00:00Z",
            processed_at="2026-06-17T00:05:00Z",
            remote_updated_at="2026-06-19T03:00:00Z",
        )
        iter_order_pages.return_value = [{"orders": [newer_order, older_order]}]
        process_shopify_order_for_editions.return_value = {
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 0,
            "changed_handles": [],
            "errors": [],
        }

        result = supabase_backend.sync_shopify_orders_to_supabase(config=self.config, max_orders=25)

        self.assertEqual(result["orders_seen"], 2)
        self.assertEqual(result["orders_processed"], 2)
        processed_order_names = [
            call.args[0]["order_name"]
            for call in process_shopify_order_for_editions.call_args_list
        ]
        self.assertEqual(processed_order_names, ["#1001", "#1002"])

    def test_supabase_order_sync_does_not_use_local_snapshot_or_display_order(self):
        source = inspect.getsource(supabase_backend.sync_shopify_orders_to_supabase)

        self.assertIn("sorted(fetched_orders, key=order_allocation_sort_key)", source)
        self.assertNotIn("load_orders_snapshot", source)
        self.assertNotIn("orders_allocation_snapshot", source)
        self.assertIn("new_lines_inserted", source)

    def test_missing_database_url_reports_fallback_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            diagnostic = supabase_backend.database_mode_diagnostic()
            status = supabase_backend.database_status(run_schema_check=False)

        self.assertFalse(diagnostic["configured"])
        self.assertEqual(diagnostic["mode"], "Local/fallback only")
        self.assertIn("DATABASE_URL", diagnostic["warning"])
        self.assertFalse(status["connected"])
        self.assertEqual(status["mode"], "Local/fallback only")

    def test_stage1_migration_contains_required_tables_and_safe_guards(self):
        sql = Path("migrations/20260625_stage1_supabase_operational_ledger.sql").read_text(encoding="utf-8")

        for table_name in (
            "edition_products",
            "edition_orders",
            "shopify_orders",
            "shopify_order_lines",
            "certificates",
            "app_sync_state",
            "audit_logs",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", sql)
        for unsafe in ("DROP ", "DELETE ", "TRUNCATE "):
            self.assertNotIn(unsafe, sql.upper())
        self.assertIn("SET allocation_key =", sql)
        self.assertIn("idx_edition_orders_line_allocation_unique", sql)
        self.assertIn("idx_edition_orders_run_number_active_unique", sql)
        self.assertIn("idx_edition_orders_handle_number_unrun_unique", sql)

    def test_duplicate_and_existing_assignment_guards_are_present(self):
        migration_sql = Path("migrations/20260625_stage1_supabase_operational_ledger.sql").read_text(encoding="utf-8")
        allocation_source = inspect.getsource(supabase_backend.allocate_edition_for_order_line)

        self.assertIn("UNIQUE (shopify_line_item_id, allocation_index)", migration_sql)
        self.assertIn("idx_edition_orders_line_allocation_unique", migration_sql)
        self.assertIn("allocation_key", migration_sql)
        self.assertIn("idx_edition_orders_allocation_key_unique", migration_sql)
        self.assertIn("eo.shopify_order_id = ANY(%s)", allocation_source)
        self.assertIn("eo.shopify_line_item_id = ANY(%s)", allocation_source)
        self.assertIn("COALESCE(eo.allocation_index, 1)=%s", allocation_source)
        self.assertIn("allocation_identity_key", allocation_source)
        self.assertIn("return {\"created\": False", allocation_source)
        self.assertIn("ON CONFLICT DO NOTHING", allocation_source)
        self.assertIn("edition_order_auto_allocation", allocation_source)

    def test_canonical_shopify_id_normalizes_numeric_and_gid(self):
        self.assertEqual(supabase_backend.canonical_shopify_id("123"), "123")
        self.assertEqual(supabase_backend.canonical_shopify_id("gid://shopify/Order/123"), "123")
        self.assertEqual(supabase_backend.canonical_shopify_id("gid://shopify/LineItem/456"), "456")
        self.assertEqual(
            supabase_backend.allocation_identity_key("gid://shopify/Order/123", "456", 2),
            "123:456:2",
        )

    def test_existing_numeric_line_lookup_matches_gid_candidate(self):
        class FakeCursor:
            def execute(self, sql, params=()):
                self.params = params
                self.next_rows = [{"shopify_line_item_id": "3001"}]

            def fetchall(self):
                return self.next_rows

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch.object(supabase_backend, "connect", return_value=FakeConnection()):
            result = supabase_backend.list_existing_shopify_line_item_ids(
                ["gid://shopify/LineItem/3001"],
                ensure_schema_first=False,
            )

        self.assertIn("3001", result)
        self.assertIn("gid://shopify/LineItem/3001", result)

    def test_latest_paid_filter_treats_numeric_and_gid_ids_as_existing(self):
        order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "financial_status": "PAID",
            "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/4001"}],
        }
        existing_orders = set(supabase_backend._shopify_id_candidates("Order", "3001"))
        existing_lines = set(supabase_backend._shopify_id_candidates("LineItem", "4001"))

        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                order,
                existing_orders,
                existing_lines,
                {},
            )
        )

    def test_existing_allocation_key_skip_does_not_increment_counter(self):
        statements = []

        class FakeCursor:
            def execute(self, sql, params=()):
                statements.append(str(sql))
                if "information_schema.columns" in str(sql):
                    self.next_row = {"exists": True}
                elif "SELECT eo.*, o.order_name" in str(sql):
                    self.next_row = {
                        "id": "existing-1",
                        "allocation_key": "3001:4001:1",
                        "shopify_order_id": "3001",
                        "shopify_line_item_id": "4001",
                        "allocation_index": 1,
                        "edition_number": 12,
                    }
                else:
                    self.next_row = None

            def fetchone(self):
                return self.next_row

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

            def rollback(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch.object(supabase_backend, "connect", return_value=FakeConnection()):
            result = supabase_backend.allocate_edition_for_order_line(
                shopify_order_id="gid://shopify/Order/3001",
                shopify_order_name="#SC3001",
                shopify_line_item_id="gid://shopify/LineItem/4001",
                allocation_index=1,
                shopify_handle="legends-never-die",
                product_title="Legends Never Die",
                ensure_schema_first=False,
            )

        self.assertFalse(result["created"])
        self.assertEqual(result["assignment"]["edition_number"], 12)
        self.assertFalse(any("UPDATE edition_runs" in statement for statement in statements))
        self.assertFalse(any("INSERT INTO edition_orders" in statement for statement in statements))

    def test_one_item_order_allocates_one_unit_and_marks_processed_lock(self):
        order = self.paid_order(
            processed_at="2026-06-19T00:05:00Z",
            remote_updated_at="2026-06-19T02:05:00Z",
        )
        allocations = []

        def fake_allocate(**kwargs):
            allocations.append(kwargs)
            return {
                "created": True,
                "assignment": {
                    "id": "eo-1",
                    "shopify_handle": kwargs["shopify_handle"],
                    "edition_number": 25,
                    "edition_total": 100,
                    "allocation_index": kwargs["allocation_index"],
                },
                "sold_out": False,
                "error": "",
            }

        with patch.object(supabase_backend, "_persist_order_snapshot"), patch.object(
            supabase_backend, "list_existing_edition_order_identities", return_value={"order_ids": set(), "order_names": set()}
        ), patch.object(
            supabase_backend, "list_existing_order_sync_locks", return_value=set()
        ), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={
                "product": {
                    "handle": "messi-the-final-crown-wall-art",
                    "title": "Messi The Final Crown Wall Art",
                    "shopify_product_id": "gid://shopify/Product/999",
                    "active": True,
                }
            },
        ), patch.object(
            supabase_backend, "allocate_edition_for_order_line", side_effect=fake_allocate
        ), patch.object(supabase_backend, "connect") as connect, patch.object(
            supabase_backend, "_set_order_line_status"
        ):
            result = supabase_backend.process_paid_order(
                order,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
            )

        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(result["existing_assignments_skipped"], 0)
        self.assertEqual([call["allocation_index"] for call in allocations], [1])
        self.assertTrue(connect.called)

    def test_quantity_two_order_allocates_two_units_and_marks_processed_lock(self):
        order = self.paid_order(
            processed_at="2026-06-19T00:05:00Z",
            remote_updated_at="2026-06-19T02:05:00Z",
        )
        order["line_items"][0]["quantity"] = 2
        allocations = []

        def fake_allocate(**kwargs):
            allocations.append(kwargs)
            return {
                "created": True,
                "assignment": {
                    "id": f"eo-{kwargs['allocation_index']}",
                    "shopify_handle": kwargs["shopify_handle"],
                    "edition_number": 24 + kwargs["allocation_index"],
                    "edition_total": 100,
                    "allocation_index": kwargs["allocation_index"],
                },
                "sold_out": False,
                "error": "",
            }

        with patch.object(supabase_backend, "_persist_order_snapshot"), patch.object(
            supabase_backend, "list_existing_edition_order_identities", return_value={"order_ids": set(), "order_names": set()}
        ), patch.object(
            supabase_backend, "list_existing_order_sync_locks", return_value=set()
        ), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={
                "product": {
                    "handle": "messi-the-final-crown-wall-art",
                    "title": "Messi The Final Crown Wall Art",
                    "shopify_product_id": "gid://shopify/Product/999",
                    "active": True,
                }
            },
        ), patch.object(
            supabase_backend, "allocate_edition_for_order_line", side_effect=fake_allocate
        ), patch.object(supabase_backend, "connect") as connect, patch.object(
            supabase_backend, "_set_order_line_status"
        ) as set_status:
            result = supabase_backend.process_paid_order(
                order,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
            )

        self.assertEqual(result["assignments_created"], 2)
        self.assertEqual(result["existing_assignments_skipped"], 0)
        self.assertEqual(result["missing_mapping_skipped"], 0)
        self.assertEqual([call["allocation_index"] for call in allocations], [1, 2])
        self.assertEqual(set_status.call_args.args[2], "Assigned")
        self.assertTrue(connect.called)

    def test_two_eligible_products_same_order_allocate_two_rows(self):
        order = self.paid_order(
            processed_at="2026-06-19T00:05:00Z",
            remote_updated_at="2026-06-19T02:05:00Z",
        )
        order["line_items"].append(
            {
                "shopify_line_item_id": "gid://shopify/LineItem/2",
                "shopify_product_id": "gid://shopify/Product/1000",
                "product_title": "Second Limited Wall Art",
                "product_handle": "second-limited-wall-art",
                "variant_title": "Oak / L",
                "position": 2,
                "quantity": 1,
            }
        )
        allocations = []

        def fake_resolve(line_item, **_kwargs):
            return {
                "product": {
                    "handle": line_item["product_handle"],
                    "title": line_item["product_title"],
                    "shopify_product_id": line_item["shopify_product_id"],
                    "active": True,
                }
            }

        def fake_allocate(**kwargs):
            allocations.append(kwargs)
            return {
                "created": True,
                "assignment": {
                    "id": kwargs["shopify_line_item_id"],
                    "shopify_handle": kwargs["shopify_handle"],
                    "edition_number": len(allocations),
                    "edition_total": 100,
                    "allocation_index": kwargs["allocation_index"],
                },
                "sold_out": False,
                "error": "",
            }

        with patch.object(supabase_backend, "_persist_order_snapshot"), patch.object(
            supabase_backend, "list_existing_edition_order_identities", return_value={"order_ids": set(), "order_names": set()}
        ), patch.object(
            supabase_backend, "list_existing_order_sync_locks", return_value=set()
        ), patch.object(
            supabase_backend, "resolve_edition_product_for_order_line", side_effect=fake_resolve
        ), patch.object(
            supabase_backend, "allocate_edition_for_order_line", side_effect=fake_allocate
        ), patch.object(supabase_backend, "connect"), patch.object(
            supabase_backend, "_set_order_line_status"
        ):
            result = supabase_backend.process_paid_order(
                order,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
            )

        self.assertEqual(result["assignments_created"], 2)
        self.assertEqual(
            [call["shopify_line_item_id"] for call in allocations],
            ["gid://shopify/LineItem/1", "gid://shopify/LineItem/2"],
        )
        self.assertEqual([call["allocation_index"] for call in allocations], [1, 1])

    def test_duplicate_diagnostic_blocks_latest_paid_sync_before_shopify_fetch(self):
        with patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("No schema check in no-schema mode."),
        ), patch.object(
            supabase_backend,
            "start_sync_run",
            return_value="run-duplicate-block",
        ) as start_run, patch.object(
            supabase_backend,
            "finish_sync_run",
        ) as finish_run, patch.object(
            supabase_backend,
            "edition_allocation_duplicate_diagnostics",
            return_value={
                "edition_orders_total": 173,
                "duplicate_group_count": 4,
                "duplicate_row_count": 16,
                "groups": [{"shopify_order_name": "#SC2883"}],
            },
        ), patch.object(
            supabase_backend,
            "_latest_paid_orders_payload",
            side_effect=AssertionError("Duplicate block must happen before Shopify fetch."),
        ):
            result = supabase_backend.sync_latest_paid_orders_to_supabase(
                config=self.config,
                limit=50,
                lookback_days=14,
                ensure_schema_first=False,
                backfill_latest_paid=True,
            )

        start_run.assert_called_once_with("shopify_orders_latest_paid", ensure_schema_first=False)
        finish_run.assert_called_once()
        self.assertTrue(result["sync_blocked"])
        self.assertIn("Duplicate edition allocations detected", result["block_reason"])
        self.assertEqual(result["shopify_orders_fetched"], 0)
        self.assertEqual(result["edition_counters_incremented"], 0)

    def test_orders_top_actions_accepts_duplicate_diagnostics_argument(self):
        import orders_page

        signature = inspect.signature(orders_page._render_top_actions)
        actions_source = inspect.getsource(orders_page._render_top_actions)

        self.assertIn("duplicate_diagnostics", signature.parameters)
        self.assertEqual(signature.parameters["duplicate_diagnostics"].default, None)
        self.assertIn("Orders sync automatically after payment.", actions_source)
        self.assertNotIn("Check New Paid Orders", actions_source)

    def test_orders_duplicate_warning_disappears_when_raw_diagnostics_are_clean(self):
        import orders_page

        class FakeStreamlit:
            def __init__(self):
                self.errors = []

            def error(self, message):
                self.errors.append(message)

        fake_st = FakeStreamlit()
        with patch.object(orders_page, "st", fake_st):
            orders_page._render_duplicate_warning_panel({"duplicate_group_count": 0, "sync_allowed": True})
            self.assertEqual(fake_st.errors, [])

            orders_page._render_duplicate_warning_panel({"duplicate_group_count": 1, "sync_allowed": False})
            self.assertEqual(fake_st.errors, ["Orders need repair before new sync. Please contact Nathan/admin."])

    def test_existing_order_name_in_edition_orders_skips_entire_sync_candidate(self):
        order = {
            "shopify_order_id": "gid://shopify/Order/2883",
            "order_name": "#SC2883",
            "financial_status": "PAID",
            "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/9001"}],
        }

        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                order,
                set(),
                set(),
                {},
                {"order_ids": set(), "order_names": {"#SC2883"}},
            )
        )

    def test_existing_numeric_order_identity_matches_gid_candidate(self):
        order = {
            "shopify_order_id": "gid://shopify/Order/2883",
            "order_name": "#SC2883",
            "financial_status": "PAID",
            "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/9001"}],
        }

        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                order,
                set(),
                set(),
                {},
                {"order_ids": {"2883"}, "order_names": set()},
            )
        )

    def test_existing_order_lock_skips_entire_sync_candidate(self):
        order = {
            "shopify_order_id": "gid://shopify/Order/2883",
            "order_name": "#SC2883",
            "financial_status": "PAID",
            "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/9001"}],
        }

        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                order,
                set(),
                set(),
                {},
                {"order_ids": set(), "order_names": set()},
                {"id:2883"},
            )
        )

    def test_sc2880_sc2883_repair_plan_keeps_one_expected_row_per_order(self):
        from scripts import repair_sc2880_sc2883_single_order_duplicates as repair

        rows = [
            {
                "id": "1",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "gid://shopify/Order/2883",
                "shopify_line_item_id": "gid://shopify/LineItem/9001",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 63,
                "edition_total": 100,
                "created_at": "2026-06-29T01:00:00Z",
            },
            {
                "id": "2",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "2883",
                "shopify_line_item_id": "9001",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 64,
                "edition_total": 100,
                "created_at": "2026-06-29T01:01:00Z",
            },
            {
                "id": "3",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "gid://shopify/Order/2883",
                "shopify_line_item_id": "gid://shopify/LineItem/9001",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 63,
                "edition_total": 100,
                "created_at": "2026-06-29T02:00:00Z",
            },
            {
                "id": "4",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "2883",
                "shopify_line_item_id": "9001",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 64,
                "edition_total": 100,
                "created_at": "2026-06-29T02:01:00Z",
            },
            {
                "id": "5",
                "shopify_order_name": "#SC2880",
                "shopify_order_id": "gid://shopify/Order/2880",
                "shopify_line_item_id": "gid://shopify/LineItem/8001",
                "shopify_handle": "seventh-nolan-ryan",
                "product_title": "The Seventh Nolan Ryan Wall Art",
                "variant_title": "Black / S",
                "customer_name": "Nathan Baker",
                "edition_number": 28,
                "edition_total": 100,
                "created_at": "2026-06-29T01:00:00Z",
            },
            {
                "id": "6",
                "shopify_order_name": "#SC2880",
                "shopify_order_id": "2880",
                "shopify_line_item_id": "8001",
                "shopify_handle": "seventh-nolan-ryan",
                "product_title": "The Seventh Nolan Ryan Wall Art",
                "variant_title": "Black / S",
                "customer_name": "Nathan Baker",
                "edition_number": 25,
                "edition_total": 100,
                "created_at": "2026-06-29T01:01:00Z",
            },
            {
                "id": "7",
                "shopify_order_name": "#SC2880",
                "shopify_order_id": "2880",
                "shopify_line_item_id": "8001",
                "shopify_handle": "seventh-nolan-ryan",
                "product_title": "The Seventh Nolan Ryan Wall Art",
                "variant_title": "Black / S",
                "customer_name": "Nathan Baker",
                "edition_number": 25,
                "edition_total": 100,
                "created_at": "2026-06-29T02:01:00Z",
            },
        ]

        plan = repair.build_repair_plan(rows)

        kept = {row["shopify_order_name"]: row["edition_number"] for row in plan["rows_to_keep"]}
        self.assertEqual(kept, {"#SC2883": 63, "#SC2880": 25})
        self.assertEqual(sorted(plan["delete_ids"]), ["2", "3", "4", "5", "7"])
        self.assertEqual(len(plan["rows_to_delete"]), 5)

    def test_shopify_truth_repair_plan_keeps_sc2880_sc2883_and_deletes_12_extras(self):
        from scripts import repair_duplicate_order_allocations_from_shopify_truth as repair

        keep_map = {"#SC2880": 25, "#SC2881": 26, "#SC2882": 27, "#SC2883": 63}
        edition_sequences = {
            "#SC2880": [28, 25, 28, 25],
            "#SC2881": [29, 26, 29, 26],
            "#SC2882": [30, 27, 30, 27],
            "#SC2883": [63, 64, 63, 64],
        }
        rows = []
        shopify_lines = []
        next_id = 1
        for offset, (order_name, editions) in enumerate(edition_sequences.items(), start=2880):
            line_id = f"gid://shopify/LineItem/{offset}001"
            order_id = f"gid://shopify/Order/{offset}"
            handle = "legends-never-die" if order_name == "#SC2883" else "seventh-nolan-ryan"
            shopify_lines.append(
                {
                    "shopify_order_id": order_id,
                    "order_name": order_name,
                    "shopify_line_item_id": line_id,
                    "quantity": 1,
                    "shopify_handle": handle,
                    "product_title": "Legends Never Die Messi vs Ronaldo Wall Art"
                    if order_name == "#SC2883"
                    else "The Seventh Nolan Ryan Wall Art",
                    "variant_title": "Black / L" if order_name == "#SC2883" else "Black / S",
                    "eligible": True,
                }
            )
            for index, edition_number in enumerate(editions, start=1):
                rows.append(
                    {
                        "id": str(next_id),
                        "shopify_order_name": order_name,
                        "shopify_order_id": order_id if index % 2 else str(offset),
                        "shopify_line_item_id": line_id if index % 2 else str(offset) + "001",
                        "allocation_index": 1,
                        "allocation_key": f"{offset}:{offset}001:1" if index in (1, 3) else "",
                        "shopify_handle": handle,
                        "product_title": shopify_lines[-1]["product_title"],
                        "variant_title": shopify_lines[-1]["variant_title"],
                        "customer_name": "ANDREW KEELING" if order_name == "#SC2883" else "Nathan Baker",
                        "edition_number": edition_number,
                        "edition_total": 100,
                        "created_at": f"2026-06-29T0{index}:00:00Z",
                    }
                )
                next_id += 1

        plan = repair.build_repair_plan(rows, shopify_lines)

        self.assertEqual(len(plan["delete_ids"]), 12)
        self.assertEqual(plan["expected_before_after"], {
            "#SC2880": {"before": 4, "after": 1},
            "#SC2881": {"before": 4, "after": 1},
            "#SC2882": {"before": 4, "after": 1},
            "#SC2883": {"before": 4, "after": 1},
        })
        for order_name, keep_edition in keep_map.items():
            kept = plan["known_repairs"][order_name]["keep"]
            deleted_editions = [row["edition_number"] for row in plan["known_repairs"][order_name]["delete"]]
            self.assertEqual(kept["edition_number"], keep_edition)
            self.assertEqual(len(deleted_editions), 3)
            self.assertNotIn(kept["id"], plan["delete_ids"])
        self.assertEqual(len(plan["matching_rows_before"]), 16)

    def test_shopify_truth_repair_plan_preserves_valid_quantity_two_units(self):
        from scripts import repair_duplicate_order_allocations_from_shopify_truth as repair

        rows = [
            {
                "id": "1",
                "shopify_order_name": "#SC3000",
                "shopify_order_id": "gid://shopify/Order/3000",
                "shopify_line_item_id": "gid://shopify/LineItem/7000",
                "allocation_index": 1,
                "allocation_key": "3000:7000:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "Collector",
                "edition_number": 10,
                "edition_total": 100,
                "created_at": "2026-06-29T01:00:00Z",
            },
            {
                "id": "2",
                "shopify_order_name": "#SC3000",
                "shopify_order_id": "gid://shopify/Order/3000",
                "shopify_line_item_id": "gid://shopify/LineItem/7000",
                "allocation_index": 2,
                "allocation_key": "3000:7000:2",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "Collector",
                "edition_number": 11,
                "edition_total": 100,
                "created_at": "2026-06-29T01:01:00Z",
            },
        ]
        shopify_lines = [
            {
                "shopify_order_id": "gid://shopify/Order/3000",
                "order_name": "#SC3000",
                "shopify_line_item_id": "gid://shopify/LineItem/7000",
                "quantity": 2,
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "eligible": True,
            }
        ]

        plan = repair.build_repair_plan(rows, shopify_lines)

        self.assertEqual(plan["delete_ids"], [])
        self.assertEqual(plan["rows_to_delete"], [])

    def test_shopify_truth_repair_plan_removes_duplicate_allocation_key_unit(self):
        from scripts import repair_duplicate_order_allocations_from_shopify_truth as repair

        rows = [
            {
                "id": "1",
                "shopify_order_name": "#SC3000",
                "shopify_order_id": "gid://shopify/Order/3000",
                "shopify_line_item_id": "gid://shopify/LineItem/7000",
                "allocation_index": 1,
                "allocation_key": "3000:7000:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "Collector",
                "edition_number": 10,
                "edition_total": 100,
                "created_at": "2026-06-29T01:00:00Z",
            },
            {
                "id": "2",
                "shopify_order_name": "#SC3000",
                "shopify_order_id": "3000",
                "shopify_line_item_id": "7000",
                "allocation_index": 1,
                "allocation_key": "3000:7000:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "Collector",
                "edition_number": 10,
                "edition_total": 100,
                "created_at": "2026-06-29T01:01:00Z",
            },
        ]

        plan = repair.build_repair_plan(rows, [])

        self.assertEqual(plan["delete_ids"], ["2"])
        self.assertEqual(plan["rows_to_delete"][0]["duplicate_type"], "allocation_key")

    def test_shopify_truth_repair_plan_renumbers_sc2884_65_to_64_when_safe(self):
        from scripts import repair_duplicate_order_allocations_from_shopify_truth as repair

        rows = [
            {
                "id": "1",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "gid://shopify/Order/2883",
                "shopify_line_item_id": "gid://shopify/LineItem/9001",
                "allocation_index": 1,
                "allocation_key": "2883:9001:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 63,
                "edition_total": 100,
                "certificate_status": "Needs certificate",
                "created_at": "2026-06-29T01:00:00Z",
            },
            {
                "id": "2",
                "shopify_order_name": "#SC2883",
                "shopify_order_id": "gid://shopify/Order/2883",
                "shopify_line_item_id": "gid://shopify/LineItem/9001",
                "allocation_index": 1,
                "allocation_key": "2883:9001:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Black / L",
                "customer_name": "ANDREW KEELING",
                "edition_number": 64,
                "edition_total": 100,
                "certificate_status": "Needs certificate",
                "created_at": "2026-06-29T01:01:00Z",
            },
            {
                "id": "3",
                "shopify_order_name": "#SC2884",
                "shopify_order_id": "gid://shopify/Order/2884",
                "shopify_line_item_id": "gid://shopify/LineItem/9002",
                "allocation_index": 1,
                "allocation_key": "2884:9002:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Oak / M",
                "customer_name": "Michael Winn",
                "edition_number": 65,
                "edition_total": 100,
                "certificate_status": "Needs certificate",
                "created_at": "2026-06-30T01:00:00Z",
            },
        ]

        plan = repair.build_repair_plan(rows, [])

        self.assertEqual(plan["delete_ids"], ["2"])
        self.assertEqual(len(plan["renumber_rows"]), 1)
        self.assertEqual(plan["renumber_rows"][0]["id"], "3")
        self.assertEqual(plan["renumber_rows"][0]["old_edition_number"], 65)
        self.assertEqual(plan["renumber_rows"][0]["new_edition_number"], 64)
        self.assertEqual(plan["manual_review"], [])

    def test_shopify_truth_repair_plan_blocks_sc2884_renumber_when_certificate_ready(self):
        from scripts import repair_duplicate_order_allocations_from_shopify_truth as repair

        rows = [
            {
                "id": "1",
                "shopify_order_name": "#SC2884",
                "shopify_order_id": "gid://shopify/Order/2884",
                "shopify_line_item_id": "gid://shopify/LineItem/9002",
                "allocation_index": 1,
                "allocation_key": "2884:9002:1",
                "shopify_handle": "legends-never-die",
                "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant_title": "Oak / M",
                "customer_name": "Michael Winn",
                "edition_number": 65,
                "edition_total": 100,
                "certificate_status": "Ready",
                "created_at": "2026-06-30T01:00:00Z",
            },
        ]

        plan = repair.build_repair_plan(rows, [])

        self.assertEqual(plan["renumber_rows"], [])
        self.assertEqual(plan["manual_review"][0]["order_name"], "#SC2884")
        self.assertIn("certificate", plan["manual_review"][0]["reason"])

    def test_orders_page_keeps_one_visible_row_per_allocation_unit(self):
        import orders_page

        rows = [
            {
                "order": "#SC2880",
                "edition_order_id": "eo-25",
                "shopify_line_item_id": "gid://shopify/LineItem/8001",
                "allocation_index": 1,
                "edition_number": 25,
                "edition_total": 100,
                "customer": "Nathan Baker",
                "product": "The Seventh Nolan Ryan Wall Art",
                "variant": "Black / S",
            },
            {
                "order": "#SC2880",
                "edition_order_id": "eo-26",
                "shopify_line_item_id": "gid://shopify/LineItem/8002",
                "allocation_index": 1,
                "edition_number": 26,
                "edition_total": 100,
                "customer": "Nathan Baker",
                "product": "Second Limited Wall Art",
                "variant": "Oak / L",
            },
            {"order": "#SC2881", "edition_order_id": "eo-26", "edition_number": 26, "edition_total": 100},
        ]

        filtered = orders_page._filter_rows(rows, "")
        render_source = inspect.getsource(orders_page.render_page)

        self.assertEqual(len(filtered), 3)
        self.assertEqual([row["edition_order_id"] for row in filtered if row["order"] == "#SC2880"], ["eo-25", "eo-26"])
        self.assertNotIn("_one_row_per_order(_filter_rows", render_source)

    def test_allocation_unit_display_preserves_selected_sc2883_row_for_certificate_actions(self):
        import orders_page

        rows = [
            {
                "order": "#SC2883",
                "edition_order_id": "eo-63",
                "shopify_line_item_id": "gid://shopify/LineItem/9001",
                "allocation_index": 1,
                "edition_number": 63,
                "edition_total": 100,
                "customer": "ANDREW KEELING",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Black / L",
                "certificate_status": "Needs certificate",
            },
            {
                "order": "#SC2884",
                "edition_order_id": "eo-64",
                "shopify_line_item_id": "gid://shopify/LineItem/9002",
                "allocation_index": 1,
                "edition_number": 64,
                "edition_total": 100,
                "customer": "ANDREW KEELING",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Black / L",
            },
        ]

        filtered = orders_page._filter_rows(rows, "#SC2883")

        self.assertEqual(len(filtered), 1)
        selected = filtered[0]
        self.assertEqual(selected["order"], "#SC2883")
        self.assertEqual(selected["edition_order_id"], "eo-63")
        self.assertEqual(selected["edition_number"], 63)
        self.assertEqual(selected["edition_total"], 100)
        self.assertEqual(selected["customer"], "ANDREW KEELING")
        self.assertEqual(selected["product"], "Legends Never Die Messi vs Ronaldo Wall Art")
        self.assertEqual(selected["variant"], "Black / L")

    def test_orders_backend_uses_shopify_mirror_first_with_supabase_edition_overlay(self):
        list_orders_source = inspect.getsource(supabase_backend.list_orders)
        hybrid_source = inspect.getsource(supabase_backend.list_hybrid_order_rows)

        self.assertIn("FROM shopify_orders o", list_orders_source)
        self.assertIn("LEFT JOIN LATERAL", list_orders_source)
        self.assertIn("FROM shopify_orders o", hybrid_source)
        self.assertIn("assignments_by_order", hybrid_source)
        self.assertIn("assignments_by_order_name", hybrid_source)

    def test_va_orders_page_hides_developer_duplicate_diagnostics_and_backfill(self):
        import orders_page

        warning_source = inspect.getsource(orders_page._render_duplicate_warning_panel)
        actions_source = inspect.getsource(orders_page._render_top_actions)

        self.assertIn("Orders need repair before new sync. Please contact Nathan/admin.", warning_source)
        self.assertNotIn("allocation_key", warning_source)
        self.assertNotIn("Backfill latest paid orders", actions_source)
        self.assertNotIn("Check New Paid Orders", actions_source)
        self.assertIn("Orders sync automatically after payment.", actions_source)

    def test_developer_page_has_orders_cache_recheck_diagnostics_only(self):
        import app

        developer_source = inspect.getsource(app._render_developer_allocation_tools)

        self.assertIn("Clear Orders Cache / Recheck Diagnostics", developer_source)
        self.assertIn("edition_allocation_duplicate_diagnostics", developer_source)
        self.assertIn("check_new_paid_orders_allowed", developer_source)
        self.assertIn("Shopify truth duplicate repair", developer_source)
        self.assertIn("repair_duplicate_order_allocations_from_shopify_truth", developer_source)
        self.assertIn("RUN MANUAL ORDER SYNC", developer_source)
        self.assertIn("sync_latest_paid_orders_to_supabase", developer_source)

    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(
        supabase_backend,
        "get_sync_state",
        return_value={
            "last_successful_order_fetch_at": "2026-06-16T02:00:00Z",
            "edition_tracking_start_at": "2026-06-01T00:00:00Z",
            "sync_lookback_buffer_minutes": 10,
        },
    )
    @patch.object(
        supabase_backend,
        "ensure_edition_tracking_start",
        return_value=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    @patch.object(supabase_backend.shopify_sync, "iter_order_pages")
    @patch.object(supabase_backend, "count_shopify_orders", return_value=95)
    @patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set())
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(supabase_backend, "get_order_line_assignment_snapshot", return_value={})
    @patch.object(supabase_backend, "_preview_product_counter_state")
    def test_preview_shopify_order_sync_is_read_only_and_oldest_first(
        self,
        preview_product_state,
        _assignment_snapshot,
        _existing_line_ids,
        _existing_order_ids,
        _count_orders,
        iter_order_pages,
        _tracking_start,
        _sync_state,
        _ensure_schema,
    ):
        newer_order = self.paid_order(
            order_id="gid://shopify/Order/1002",
            order_name="#1002",
            line_item_id="gid://shopify/LineItem/2002",
            created_at="2026-06-18T00:00:00Z",
            processed_at="2026-06-18T00:05:00Z",
            remote_updated_at="2026-06-19T02:00:00Z",
        )
        older_order = self.paid_order(
            order_id="gid://shopify/Order/1001",
            order_name="#1001",
            line_item_id="gid://shopify/LineItem/2001",
            created_at="2026-06-17T00:00:00Z",
            processed_at="2026-06-17T00:05:00Z",
            remote_updated_at="2026-06-19T03:00:00Z",
        )
        iter_order_pages.return_value = [{"orders": [newer_order, older_order]}]
        seen_line_ids = []

        def fake_preview_state(_cur, line_item, cache):
            seen_line_ids.append(line_item["shopify_line_item_id"])
            return cache.setdefault(
                "messi-the-final-crown-wall-art",
                {
                    "handle": "messi-the-final-crown-wall-art",
                    "next_edition_number": 12,
                    "edition_total": 100,
                    "sold_out": False,
                    "run_status": supabase_backend.ACTIVE_RUN_STATUS,
                },
            )

        preview_product_state.side_effect = fake_preview_state

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch.object(supabase_backend, "connect", return_value=FakeConnection()):
            result = supabase_backend.preview_shopify_orders_to_supabase(config=self.config, max_orders=25)

        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["shopify_orders_fetched"], 2)
        self.assertEqual(result["new_orders_inserted"], 2)
        self.assertEqual(result["new_lines_inserted"], 2)
        self.assertEqual(result["edition_allocations_created"], 2)
        self.assertEqual(seen_line_ids, ["gid://shopify/LineItem/2001", "gid://shopify/LineItem/2002"])

    def test_sync_latest_paid_orders_to_supabase_mirrors_then_repairs_then_allocates(self):
        events = []
        payload = {
            "orders": [
                {
                    "shopify_order_id": "gid://shopify/Order/3001",
                    "order_name": "#SC2848",
                    "financial_status": "PAID",
                    "line_items": [
                        {
                            "shopify_line_item_id": "gid://shopify/LineItem/3001",
                            "quantity": 1,
                            "shopify_product_id": "gid://shopify/Product/1",
                            "product_handle": "legends-never-die",
                            "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                        }
                    ],
                }
            ],
            "query": "financial_status:paid",
            "limit": 50,
            "lookback_days": 14,
        }
        with patch.object(supabase_backend, "ensure_schema"), patch.object(
            supabase_backend, "start_sync_run", return_value="run-1"
        ), patch.object(supabase_backend, "_set_sync_attempt"), patch.object(
            supabase_backend, "set_app_setting"
        ), patch.object(
            supabase_backend, "_latest_paid_orders_payload", return_value=payload
        ), patch.object(
            supabase_backend, "list_existing_shopify_order_ids", return_value=set()
        ), patch.object(
            supabase_backend, "list_existing_shopify_line_item_ids", return_value=set()
        ), patch.object(
            supabase_backend, "list_existing_shopify_order_states", return_value={}
        ), patch.object(
            supabase_backend,
            "list_existing_edition_order_identities",
            return_value={"order_ids": set(), "order_names": set()},
        ), patch.object(
            supabase_backend,
            "list_existing_order_sync_locks",
            return_value=set(),
        ), patch.object(
            supabase_backend,
            "apply_known_missing_edition_repair",
            side_effect=lambda **_kwargs: events.append("known_repair")
            or {"applied_rows": 1, "already_exists_consistent": 0, "errors": []},
        ), patch.object(
            supabase_backend,
            "process_shopify_order_for_editions",
            side_effect=lambda *args, **kwargs: events.append("allocate")
            or {
                "assignments_created": 1,
                "existing_assignments_skipped": 0,
                "missing_mapping_skipped": 0,
                "changed_handles": ["legends-never-die"],
                "errors": [],
            },
        ) as process_order, patch.object(
            supabase_backend, "_set_sync_success", return_value="2026-06-25T00:00:00Z"
        ), patch.object(
            supabase_backend, "_record_order_fetch_metrics"
        ), patch.object(
            supabase_backend, "finish_sync_run"
        ), patch.object(
            supabase_backend, "_log_order_fetch_timing"
        ):
            result = supabase_backend.sync_latest_paid_orders_to_supabase(config=self.config, limit=50, lookback_days=14)

        self.assertEqual(events, ["known_repair", "allocate"])
        _, process_kwargs = process_order.call_args
        self.assertFalse(process_kwargs["fetch_missing_products"])
        self.assertTrue(process_kwargs["assign_editions"])
        self.assertFalse(process_kwargs["generate_certificates"])
        self.assertFalse(process_kwargs["sync_product_metafields"])
        self.assertEqual(result["query"], "financial_status:paid")
        self.assertEqual(result["shopify_orders_fetched"], 1)
        self.assertEqual(result["new_orders_inserted"], 1)
        self.assertEqual(result["new_lines_inserted"], 1)
        self.assertEqual(result["edition_allocations_created"], 2)
        self.assertEqual(result["known_missing_repairs_applied"], 1)

    def test_sync_latest_paid_orders_to_supabase_skips_unchanged_existing_orders(self):
        payload = {
            "orders": [
                {
                    "shopify_order_id": "gid://shopify/Order/3001",
                    "order_name": "#SC3001",
                    "financial_status": "PAID",
                    "remote_updated_at": "2026-06-25T10:00:00Z",
                    "line_items": [
                        {
                            "shopify_line_item_id": "gid://shopify/LineItem/3001",
                            "quantity": 1,
                            "shopify_product_id": "gid://shopify/Product/1",
                            "product_handle": "legends-never-die",
                            "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                        }
                    ],
                }
            ],
            "query": "financial_status:paid updated_at:>='2026-06-25T09:50:00Z'",
            "limit": 50,
            "lookback_days": 14,
            "sync_from": "2026-06-25T09:50:00Z",
        }
        with patch.object(supabase_backend, "ensure_schema"), patch.object(
            supabase_backend, "start_sync_run", return_value="run-1"
        ), patch.object(supabase_backend, "_set_sync_attempt"), patch.object(
            supabase_backend, "set_app_setting"
        ), patch.object(
            supabase_backend, "_latest_paid_orders_payload", return_value=payload
        ), patch.object(
            supabase_backend, "list_existing_shopify_order_ids", return_value={"gid://shopify/Order/3001"}
        ), patch.object(
            supabase_backend, "list_existing_shopify_line_item_ids", return_value={"gid://shopify/LineItem/3001"}
        ), patch.object(
            supabase_backend,
            "list_existing_shopify_order_states",
            return_value={
                "gid://shopify/Order/3001": {
                    "remote_updated_at": "2026-06-25T10:00:00Z",
                    "created_at": "2026-06-25T10:00:00Z",
                    "synced_at": "2026-06-25T10:00:00Z",
                }
            },
        ), patch.object(
            supabase_backend,
            "list_existing_edition_order_identities",
            return_value={"order_ids": {"gid://shopify/Order/3001", "3001"}, "order_names": {"#SC3001"}},
        ), patch.object(
            supabase_backend,
            "list_existing_order_sync_locks",
            return_value={"id:3001", "name:#SC3001"},
        ), patch.object(
            supabase_backend, "apply_known_missing_edition_repair"
        ) as known_repair, patch.object(
            supabase_backend, "process_shopify_order_for_editions"
        ) as process_order, patch.object(
            supabase_backend, "_edition_product_handles_for_orders"
        ) as handles_lookup, patch.object(
            supabase_backend, "sync_product_edition_metafields_for_handles"
        ) as mirror_handles, patch.object(
            supabase_backend, "_set_sync_success", return_value="2026-06-25T10:01:00Z"
        ), patch.object(
            supabase_backend, "_record_order_fetch_metrics"
        ), patch.object(
            supabase_backend, "finish_sync_run"
        ), patch.object(
            supabase_backend, "_log_order_fetch_timing"
        ):
            result = supabase_backend.sync_latest_paid_orders_to_supabase(config=self.config, limit=50, lookback_days=14)

        process_order.assert_not_called()
        known_repair.assert_not_called()
        handles_lookup.assert_not_called()
        mirror_handles.assert_not_called()
        self.assertEqual(result["orders_processed"], 0)
        self.assertEqual(result["existing_orders_skipped"], 1)
        self.assertEqual(result["new_orders_inserted"], 0)
        self.assertEqual(result["sync_from"], "2026-06-25T09:50:00Z")

    def test_sync_latest_paid_orders_no_schema_mode_skips_ensure_and_mirrors_affected_handles(self):
        payload = {
            "orders": [
                {
                    "shopify_order_id": "gid://shopify/Order/3001",
                    "order_name": "#SC3001",
                    "financial_status": "PAID",
                    "remote_updated_at": "2026-06-25T10:00:00Z",
                    "line_items": [
                        {
                            "shopify_line_item_id": "gid://shopify/LineItem/3001",
                            "quantity": 1,
                            "shopify_product_id": "gid://shopify/Product/1",
                            "product_handle": "legends-never-die",
                            "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                        }
                    ],
                }
            ],
            "query": "financial_status:paid updated_at:>='2026-06-25T09:50:00Z'",
            "limit": 50,
            "lookback_days": 14,
            "sync_from": "2026-06-25T09:50:00Z",
        }
        with patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Orders sync should not run schema migrations."),
        ) as ensure_schema, patch.object(
            supabase_backend, "start_sync_run", return_value="run-1"
        ) as start_sync_run, patch.object(
            supabase_backend, "_set_sync_attempt"
        ), patch.object(
            supabase_backend, "set_app_setting"
        ), patch.object(
            supabase_backend, "_latest_paid_orders_payload", return_value=payload
        ), patch.object(
            supabase_backend, "list_existing_shopify_order_ids", return_value=set()
        ), patch.object(
            supabase_backend, "list_existing_shopify_line_item_ids", return_value=set()
        ), patch.object(
            supabase_backend, "list_existing_shopify_order_states", return_value={}
        ), patch.object(
            supabase_backend,
            "list_existing_edition_order_identities",
            return_value={"order_ids": set(), "order_names": set()},
        ), patch.object(
            supabase_backend,
            "list_existing_order_sync_locks",
            return_value=set(),
        ), patch.object(
            supabase_backend, "apply_known_missing_edition_repair"
        ) as known_repair, patch.object(
            supabase_backend,
            "process_shopify_order_for_editions",
            return_value={
                "assignments_created": 1,
                "existing_assignments_skipped": 0,
                "missing_mapping_skipped": 0,
                "changed_handles": ["legends-never-die"],
                "errors": [],
            },
        ) as process_order, patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            return_value={"attempted": 1, "synced": 1, "skipped": 0, "errors": [], "results": []},
        ) as mirror_handles, patch.object(
            supabase_backend, "_set_sync_success_at", return_value="2026-06-25T10:00:00Z"
        ), patch.object(
            supabase_backend, "_record_order_fetch_metrics"
        ), patch.object(
            supabase_backend, "finish_sync_run"
        ), patch.object(
            supabase_backend, "_log_order_fetch_timing"
        ):
            result = supabase_backend.sync_latest_paid_orders_to_supabase(
                config=self.config,
                limit=50,
                lookback_days=14,
                ensure_schema_first=False,
            )

        ensure_schema.assert_not_called()
        start_sync_run.assert_called_once_with("shopify_orders_latest_paid", ensure_schema_first=False)
        known_repair.assert_not_called()
        self.assertFalse(process_order.call_args.kwargs["ensure_schema_first"])
        mirror_handles.assert_called_once_with(
            ["legends-never-die"],
            config=self.config,
            ensure_schema_first=False,
        )
        self.assertEqual(result["edition_allocations_created"], 1)
        self.assertEqual(result["product_metafields_synced"], 1)

    def test_sync_latest_paid_orders_no_schema_mode_reports_missing_schema_cleanly(self):
        class MissingSchemaError(Exception):
            sqlstate = "42P01"

        with patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Orders sync should not run schema migrations."),
        ) as ensure_schema, patch.object(
            supabase_backend,
            "start_sync_run",
            side_effect=MissingSchemaError("relation sync_runs does not exist"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Orders sync failed: missing required database schema"):
                supabase_backend.sync_latest_paid_orders_to_supabase(
                    config=self.config,
                    limit=50,
                    lookback_days=14,
                    ensure_schema_first=False,
                )

        ensure_schema.assert_not_called()

    @patch.object(supabase_backend, "get_sync_state")
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders")
    def test_sync_latest_paid_orders_skips_existing_cursor_orders_without_latest_created_catchup(
        self,
        fetch_latest_paid_orders,
        get_sync_state,
    ):
        get_sync_state.return_value = {
            "last_successful_order_fetch_at": "2026-06-29T06:22:12Z",
            "sync_lookback_buffer_minutes": 10,
        }
        existing_order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "order_name": "#SC3001",
            "financial_status": "PAID",
            "remote_updated_at": "2026-06-29T06:25:00Z",
            "line_items": [
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/3001",
                    "quantity": 1,
                    "shopify_product_id": "gid://shopify/Product/1",
                    "product_handle": "legends-never-die",
                    "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                }
            ],
        }
        new_order = {
            "shopify_order_id": "gid://shopify/Order/3002",
            "order_name": "#SC3002",
            "financial_status": "PAID",
            "remote_updated_at": "2026-06-29T06:20:00Z",
            "created_at": "2026-06-29T06:18:00Z",
            "line_items": [
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/3002",
                    "quantity": 1,
                    "shopify_product_id": "gid://shopify/Product/1",
                    "product_handle": "legends-never-die",
                    "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
                }
            ],
        }
        fetch_latest_paid_orders.return_value = {
            "orders": [existing_order],
            "query": "financial_status:paid updated_at:>='2026-06-29T06:12:12Z'",
            "limit": 50,
            "lookback_days": 14,
            "pages_fetched": 1,
        }

        with patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Orders sync should not run schema migrations."),
        ) as ensure_schema, patch.object(
            supabase_backend, "start_sync_run", return_value="run-1"
        ), patch.object(
            supabase_backend, "_set_sync_attempt"
        ), patch.object(
            supabase_backend, "set_app_setting"
        ), patch.object(
            supabase_backend,
            "list_existing_shopify_order_ids",
            return_value={"gid://shopify/Order/3001"},
        ), patch.object(
            supabase_backend,
            "list_existing_shopify_line_item_ids",
            return_value={"gid://shopify/LineItem/3001"},
        ), patch.object(
            supabase_backend,
            "list_existing_shopify_order_states",
            return_value={
                "gid://shopify/Order/3001": {
                    "remote_updated_at": "2026-06-29T06:25:00Z",
                    "created_at": "2026-06-29T06:00:00Z",
                    "synced_at": "2026-06-29T06:25:00Z",
                }
            },
        ), patch.object(
            supabase_backend,
            "list_existing_edition_order_identities",
            return_value={"order_ids": {"gid://shopify/Order/3001", "3001"}, "order_names": {"#SC3001"}},
        ), patch.object(
            supabase_backend,
            "list_existing_order_sync_locks",
            return_value={"id:3001", "name:#SC3001"},
        ), patch.object(
            supabase_backend, "_edition_product_handles_for_orders", return_value=[]
        ) as handles_lookup, patch.object(
            supabase_backend, "apply_known_missing_edition_repair"
        ) as known_repair, patch.object(
            supabase_backend,
            "process_shopify_order_for_editions",
            return_value={
                "assignments_created": 1,
                "existing_assignments_skipped": 0,
                "missing_mapping_skipped": 0,
                "changed_handles": ["legends-never-die"],
                "errors": [],
            },
        ) as process_order, patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            return_value={"attempted": 1, "synced": 1, "skipped": 0, "errors": [], "results": []},
        ) as mirror_handles, patch.object(
            supabase_backend, "_set_sync_success_at", return_value="2026-06-29T06:25:00Z"
        ), patch.object(
            supabase_backend, "_record_order_fetch_metrics"
        ), patch.object(
            supabase_backend, "finish_sync_run"
        ), patch.object(
            supabase_backend, "_log_order_fetch_timing"
        ):
            result = supabase_backend.sync_latest_paid_orders_to_supabase(
                config=self.config,
                limit=50,
                lookback_days=14,
                ensure_schema_first=False,
            )

        ensure_schema.assert_not_called()
        known_repair.assert_not_called()
        handles_lookup.assert_not_called()
        process_order.assert_not_called()
        mirror_handles.assert_not_called()
        self.assertEqual(fetch_latest_paid_orders.call_count, 1)
        self.assertEqual(result["fetch_strategy"], "cursor_only")
        self.assertEqual(result["cursor_orders_fetched"], 1)
        self.assertEqual(result["latest_created_orders_fetched"], 0)
        self.assertEqual(result["duplicate_orders_removed"], 0)
        self.assertEqual(result["shopify_orders_fetched"], 1)
        self.assertEqual(result["existing_orders_skipped"], 1)
        self.assertEqual(result["new_orders_inserted"], 0)
        self.assertEqual(result["new_lines_inserted"], 0)
        self.assertEqual(result["edition_allocations_created"], 0)
        self.assertEqual(result["fetched_order_names"], ["#SC3001"])
        self.assertEqual(result["imported_order_names"], [])
        self.assertEqual(result["preserved_order_names"], ["#SC3001"])
        self.assertEqual(result["assigned_order_names"], [])
        self.assertEqual(result["affected_order_names"], [])
        self.assertEqual(result["affected_shopify_order_ids"], [])
        self.assertTrue(result["cursor_updated"])

    @patch.object(supabase_backend, "ensure_schema", side_effect=AssertionError("webhook must not run schema DDL"))
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders", side_effect=AssertionError("webhook must not fetch latest paid orders"))
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    @patch.object(supabase_backend, "sync_product_edition_metafields_for_handles")
    def test_webhook_single_order_processes_one_order_without_latest_fetch_or_schema(
        self,
        sync_product_edition_metafields_for_handles,
        process_shopify_order_for_editions,
        list_existing_shopify_line_item_ids,
        _fetch_latest_paid_orders,
        _ensure_schema,
    ):
        order = self.paid_order(
            order_id="gid://shopify/Order/2879",
            order_name="#SC2879",
            line_item_id="gid://shopify/LineItem/28791",
            processed_at="2026-06-29T06:30:00Z",
            remote_updated_at="2026-06-29T06:30:10Z",
        )
        process_shopify_order_for_editions.return_value = {
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "missing_mapping_skipped": 0,
            "changed_handles": ["messi-the-final-crown-wall-art"],
            "new_assignment_ids": ["edition-2879"],
            "errors": [],
        }
        sync_product_edition_metafields_for_handles.return_value = {
            "attempted": 1,
            "synced": 1,
            "errors": [],
            "results": [],
        }

        result = supabase_backend.process_single_paid_shopify_order_for_editions(
            order,
            source="webhook",
            config=self.config,
            ensure_schema_first=False,
        )

        self.assertEqual(result["source"], "webhook")
        self.assertEqual(result["order_name"], "#SC2879")
        self.assertEqual(result["imported_lines"], 1)
        self.assertEqual(result["skipped_existing_lines"], 0)
        self.assertEqual(result["editions_assigned"], 1)
        self.assertEqual(result["assigned_editions"], ["edition-2879"])
        self.assertEqual(result["affected_handles"], ["messi-the-final-crown-wall-art"])
        self.assertEqual(result["metafields_updated"], 1)
        list_existing_shopify_line_item_ids.assert_called_once_with(
            ["gid://shopify/LineItem/28791"],
            ensure_schema_first=False,
        )
        process_shopify_order_for_editions.assert_called_once()
        _, process_kwargs = process_shopify_order_for_editions.call_args
        self.assertFalse(process_kwargs["generate_certificates"])
        self.assertFalse(process_kwargs["sync_product_metafields"])
        self.assertFalse(process_kwargs["ensure_schema_first"])
        sync_product_edition_metafields_for_handles.assert_called_once_with(
            ["messi-the-final-crown-wall-art"],
            config=self.config,
            ensure_schema_first=False,
        )

    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders", side_effect=AssertionError("webhook must not fetch latest paid orders"))
    @patch.object(supabase_backend.shopify_sync, "fetch_orders_by_ids")
    @patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @patch.object(
        supabase_backend,
        "process_shopify_order_for_editions",
        return_value={
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "missing_mapping_skipped": 0,
            "changed_handles": [],
            "new_assignment_ids": ["edition-2879"],
            "errors": [],
        },
    )
    def test_webhook_thin_payload_fetches_single_order_by_id(
        self,
        process_shopify_order_for_editions,
        _existing_line_ids,
        fetch_orders_by_ids,
        _fetch_latest_paid_orders,
    ):
        fetched_order = self.paid_order(
            order_id="gid://shopify/Order/2879",
            order_name="#SC2879",
            line_item_id="gid://shopify/LineItem/28791",
            processed_at="2026-06-29T06:30:00Z",
            remote_updated_at="2026-06-29T06:30:10Z",
        )
        fetch_orders_by_ids.return_value = [fetched_order]

        result = supabase_backend.process_single_paid_shopify_order_for_editions(
            {"id": 2879, "admin_graphql_api_id": "gid://shopify/Order/2879", "financial_status": "paid"},
            source="webhook",
            config=self.config,
            ensure_schema_first=False,
        )

        fetch_orders_by_ids.assert_called_once_with(["gid://shopify/Order/2879"], config=self.config)
        self.assertEqual(result["order_name"], "#SC2879")
        self.assertEqual(result["editions_assigned"], 1)
        process_shopify_order_for_editions.assert_called_once()

    @patch.object(supabase_backend, "ensure_schema", side_effect=AssertionError("webhook must not run schema DDL"))
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders", side_effect=AssertionError("webhook must not fetch latest paid orders"))
    @patch.object(
        supabase_backend,
        "list_existing_shopify_line_item_ids",
        return_value={"gid://shopify/LineItem/28791"},
    )
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    @patch.object(supabase_backend, "sync_product_edition_metafields_for_handles")
    def test_webhook_existing_line_skips_allocation_and_mirror(
        self,
        sync_product_edition_metafields_for_handles,
        process_shopify_order_for_editions,
        _existing_line_ids,
        _fetch_latest_paid_orders,
        _ensure_schema,
    ):
        order = self.paid_order(
            order_id="gid://shopify/Order/2879",
            order_name="#SC2879",
            line_item_id="gid://shopify/LineItem/28791",
            processed_at="2026-06-29T06:30:00Z",
            remote_updated_at="2026-06-29T06:30:10Z",
        )

        result = supabase_backend.process_single_paid_shopify_order_for_editions(
            order,
            source="webhook",
            config=self.config,
            ensure_schema_first=False,
        )

        self.assertEqual(result["imported_lines"], 0)
        self.assertEqual(result["skipped_existing_lines"], 1)
        self.assertEqual(result["editions_assigned"], 0)
        process_shopify_order_for_editions.assert_not_called()
        sync_product_edition_metafields_for_handles.assert_not_called()

    @patch.object(supabase_backend, "process_single_paid_shopify_order_for_editions")
    @patch.object(supabase_backend, "_claim_webhook_event", return_value=False)
    def test_duplicate_webhook_id_skips_processing(self, _claim_webhook_event, process_single_paid_shopify_order_for_editions):
        result = supabase_backend.process_order_paid_webhook({"id": 2879, "line_items": []}, "webhook-1", "orders/paid")

        self.assertTrue(result["duplicate"])
        self.assertEqual(result["editions_assigned"], 0)
        process_single_paid_shopify_order_for_editions.assert_not_called()

    def test_webhook_backend_path_does_not_call_ensure_schema(self):
        process_source = inspect.getsource(supabase_backend.process_order_paid_webhook)
        single_order_source = inspect.getsource(supabase_backend.process_single_paid_shopify_order_for_editions)

        self.assertNotIn("ensure_schema()", process_source)
        self.assertNotIn("ensure_schema()", single_order_source)

    def test_latest_paid_order_needs_sync_rejects_unpaid_and_cancelled_orders(self):
        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                {
                    "shopify_order_id": "gid://shopify/Order/4001",
                    "financial_status": "REFUNDED",
                    "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/4001"}],
                },
                set(),
                set(),
                {},
            )
        )
        self.assertFalse(
            supabase_backend._latest_paid_order_needs_sync(
                {
                    "shopify_order_id": "gid://shopify/Order/4002",
                    "financial_status": "PAID",
                    "cancelled_at": "2026-06-29T07:00:00Z",
                    "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/4002"}],
                },
                set(),
                set(),
                {},
            )
        )

    @patch.object(supabase_backend, "get_sync_state")
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders")
    def test_latest_paid_orders_payload_uses_last_sync_timestamp(self, fetch_latest_paid_orders, get_sync_state):
        get_sync_state.return_value = {
            "last_successful_order_fetch_at": "2026-06-25T10:00:00Z",
            "sync_lookback_buffer_minutes": 10,
        }
        fetch_latest_paid_orders.return_value = {
            "orders": [],
            "query": "financial_status:paid updated_at:>='2026-06-25T09:50:00Z'",
            "limit": 50,
            "lookback_days": 14,
        }

        payload = supabase_backend._latest_paid_orders_payload(config=self.config, limit=50, lookback_days=14)

        self.assertEqual(
            fetch_latest_paid_orders.call_args_list[0].kwargs["query"],
            "financial_status:paid updated_at:>='2026-06-25T09:50:00Z'",
        )
        self.assertEqual(fetch_latest_paid_orders.call_args_list[0].kwargs["sort_key"], "UPDATED_AT")
        self.assertTrue(fetch_latest_paid_orders.call_args_list[0].kwargs["lightweight"])
        self.assertEqual(fetch_latest_paid_orders.call_count, 1)
        self.assertEqual(payload["sync_from"], "2026-06-25T09:50:00Z")
        self.assertEqual(payload["query_mode"], "cursor")
        self.assertEqual(payload["fetch_strategy"], "cursor_only")
        self.assertFalse(payload["backfill_latest_paid"])
        self.assertEqual(payload["pages_fetched"], 0)
        self.assertEqual(payload["line_items_fetched"], 0)
        self.assertEqual(payload["metafields_fetched"], 0)

    @patch.object(supabase_backend, "utc_now_datetime", return_value=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc))
    @patch.object(supabase_backend, "get_sync_state")
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders")
    def test_latest_paid_orders_payload_without_cursor_uses_small_safe_window(
        self,
        fetch_latest_paid_orders,
        get_sync_state,
        _utc_now,
    ):
        get_sync_state.return_value = {"sync_lookback_buffer_minutes": 10}
        fetch_latest_paid_orders.return_value = {
            "orders": [],
            "query": "financial_status:paid updated_at:>='2026-06-24T12:00:00Z'",
            "limit": 50,
            "lookback_days": 14,
        }

        payload = supabase_backend._latest_paid_orders_payload(config=self.config, limit=50, lookback_days=14)

        self.assertEqual(
            fetch_latest_paid_orders.call_args_list[0].kwargs["query"],
            "financial_status:paid updated_at:>='2026-06-24T12:00:00Z'",
        )
        self.assertEqual(fetch_latest_paid_orders.call_args_list[0].kwargs["sort_key"], "UPDATED_AT")
        self.assertTrue(fetch_latest_paid_orders.call_args_list[0].kwargs["lightweight"])
        self.assertEqual(fetch_latest_paid_orders.call_count, 1)
        self.assertEqual(payload["sync_from"], "2026-06-24T12:00:00Z")
        self.assertEqual(payload["query_mode"], "safe_window")
        self.assertEqual(payload["fetch_strategy"], "cursor_only")
        self.assertFalse(payload["backfill_latest_paid"])

    @patch.object(supabase_backend, "get_sync_state")
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders")
    def test_latest_paid_orders_payload_is_cursor_only_without_backfill(
        self,
        fetch_latest_paid_orders,
        get_sync_state,
    ):
        get_sync_state.return_value = {
            "last_successful_order_fetch_at": "2026-06-29T06:22:12Z",
            "sync_lookback_buffer_minutes": 10,
        }
        cursor_order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "order_name": "#SC3001",
            "remote_updated_at": "2026-06-29T06:25:00Z",
            "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/3001"}],
        }
        fetch_latest_paid_orders.return_value = {
            "orders": [dict(cursor_order)],
            "query": "financial_status:paid updated_at:>='2026-06-29T06:12:12Z'",
            "limit": 50,
            "lookback_days": 14,
            "pages_fetched": 1,
        }

        payload = supabase_backend._latest_paid_orders_payload(config=self.config, limit=50, lookback_days=14)

        self.assertEqual(fetch_latest_paid_orders.call_count, 1)
        self.assertEqual(payload["fetch_strategy"], "cursor_only")
        self.assertEqual(payload["cursor_orders_fetched"], 1)
        self.assertEqual(payload["latest_created_orders_fetched"], 0)
        self.assertEqual(payload["duplicate_orders_removed"], 0)
        self.assertEqual([order["order_name"] for order in payload["orders"]], ["#SC3001"])
        self.assertEqual(payload["line_items_fetched"], 1)

    @patch.object(supabase_backend, "get_sync_state")
    @patch.object(supabase_backend.shopify_sync, "fetch_latest_paid_orders")
    def test_latest_paid_orders_payload_backfill_is_explicit_broad_query(self, fetch_latest_paid_orders, get_sync_state):
        get_sync_state.return_value = {
            "last_successful_order_fetch_at": "2026-06-25T10:00:00Z",
            "sync_lookback_buffer_minutes": 10,
        }
        fetch_latest_paid_orders.return_value = {
            "orders": [],
            "query": "financial_status:paid",
            "limit": 50,
            "lookback_days": 14,
        }

        payload = supabase_backend._latest_paid_orders_payload(
            config=self.config,
            limit=50,
            lookback_days=14,
            backfill_latest_paid=True,
        )

        self.assertEqual(fetch_latest_paid_orders.call_args.kwargs["query"], "financial_status:paid")
        self.assertEqual(fetch_latest_paid_orders.call_args.kwargs["sort_key"], "CREATED_AT")
        self.assertEqual(fetch_latest_paid_orders.call_args.kwargs["limit"], 50)
        self.assertTrue(fetch_latest_paid_orders.call_args.kwargs["lightweight"])
        self.assertEqual(payload["sync_from"], "")
        self.assertEqual(payload["query_mode"], "latest_paid_backfill")
        self.assertTrue(payload["backfill_latest_paid"])

    @patch.object(supabase_backend, "ensure_schema")
    @patch.object(supabase_backend, "ensure_edition_tracking_start", return_value=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc))
    @patch.object(supabase_backend, "get_sync_state", return_value={"edition_tracking_start_at": "2026-06-01T00:00:00Z"})
    @patch.object(supabase_backend, "_latest_paid_orders_payload")
    @patch.object(supabase_backend, "_analyze_fetched_orders_for_preview")
    def test_preview_latest_paid_orders_sync_uses_latest_paid_payload(
        self,
        analyze_preview,
        latest_paid_orders_payload,
        _sync_state,
        _tracking_start,
        _ensure_schema,
    ):
        latest_paid_orders_payload.return_value = {
            "orders": [{"order_name": "#SC3002"}],
            "query": "financial_status:paid created_at:>=2026-06-11",
            "limit": 50,
            "lookback_days": 14,
        }
        analyze_preview.return_value = {"mode": "latest_paid_dry_run", "shopify_orders_fetched": 1}

        result = supabase_backend.preview_latest_paid_orders_sync(config=self.config, limit=50, lookback_days=14)

        self.assertEqual(result["query"], "financial_status:paid created_at:>=2026-06-11")
        self.assertEqual(result["mode"], "latest_paid_dry_run")
        self.assertEqual(result["pages_fetched"], 0)
        self.assertEqual(analyze_preview.call_args.kwargs["mode_label"], "latest_paid_dry_run")

    @patch.object(supabase_backend, "ensure_schema")
    def test_backfill_missing_shopify_order_details_dry_run_does_not_write(self, _ensure_schema):
        class FakeCursor:
            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return [
                    {
                        "shopify_order_id": "gid://shopify/Order/2843",
                        "order_name": "#SC2843",
                        "customer_email": "",
                        "shipping_address_summary": "",
                        "missing_variant_rows": 1,
                        "missing_product_rows": 0,
                    }
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fetched_order = {
            "shopify_order_id": "gid://shopify/Order/2843",
            "order_name": "#SC2843",
            "customer_email": "ashkan@example.com",
            "shipping_address_summary": "Austin, TX, US",
            "line_items": [
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/1",
                    "variant_title": "Black / L",
                }
            ],
        }

        with patch.object(supabase_backend, "connect", return_value=FakeConnection()), patch.object(
            supabase_backend.shopify_sync,
            "fetch_orders_by_ids",
            return_value=[fetched_order],
        ), patch.object(
            supabase_backend,
            "_persist_order_snapshot",
            side_effect=AssertionError("Dry-run backfill must not write order snapshots."),
        ):
            result = supabase_backend.backfill_missing_shopify_order_details(
                config=self.config,
                limit=10,
                dry_run=True,
            )

        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["candidate_orders"], 1)
        self.assertEqual(result["orders_updated"], 1)
        self.assertEqual(result["variant_rows_filled"], 1)
        self.assertEqual(result["shipping_rows_filled"], 1)
        self.assertEqual(result["email_rows_filled"], 1)

    def test_manual_edition_counter_ahead_of_history_is_respected(self):
        result = supabase_backend._resolve_next_edition_number_state(75, 12, False)

        self.assertEqual(result["next_number"], 75)
        self.assertEqual(result["mode"], "respect_manual_counter")

    def test_manual_override_recalculate_sets_next_after_max_assigned(self):
        class FakeCursor:
            def __init__(self, max_assigned):
                self.max_assigned = max_assigned
                self.product_update_params = None
                self.run_update_params = None

            def execute(self, sql, params=()):
                self.sql = sql
                self.params = params
                if "SELECT COALESCE(MAX(edition_number)" in sql:
                    self.next_row = {"max_assigned": self.max_assigned}
                elif "UPDATE edition_products" in sql:
                    self.product_update_params = params
                    self.next_row = {
                        "shopify_handle": "goat-debate-wall-art",
                        "shopify_product_id": "gid://shopify/Product/777",
                        "edition_total": 100,
                        "next_edition_number": params[0],
                    }
                else:
                    if "UPDATE edition_runs" in sql:
                        self.run_update_params = params
                    self.next_row = None

            def fetchone(self):
                return self.next_row

        cursor = FakeCursor(max_assigned=51)
        result = supabase_backend._recalculate_next_edition_number_with_cursor(
            cursor,
            {
                "id": 1,
                "shopify_handle": "goat-debate-wall-art",
                "shopify_product_id": "gid://shopify/Product/777",
                "edition_total": 100,
                "next_edition_number": 96,
            },
            {"id": "run-1", "edition_total": 100, "next_edition_number": 96},
            reason="Manual correction",
        )

        self.assertEqual(result["next_edition_number"], 52)
        self.assertEqual(result["max_assigned"], 51)
        self.assertEqual(result["remaining_count"], 49)
        self.assertFalse(result["sold_out"])
        self.assertEqual(cursor.run_update_params[0], 52)
        self.assertEqual(cursor.product_update_params[0], 52)

    def test_manual_override_recalculate_never_exceeds_edition_total(self):
        class FakeCursor:
            def execute(self, sql, params=()):
                if "SELECT COALESCE(MAX(edition_number)" in sql:
                    self.next_row = {"max_assigned": 100}
                elif "UPDATE edition_products" in sql:
                    self.product_update_params = params
                    self.next_row = {
                        "shopify_handle": "goat-debate-wall-art",
                        "shopify_product_id": "gid://shopify/Product/777",
                        "edition_total": 100,
                        "next_edition_number": params[0],
                    }
                else:
                    self.next_row = None

            def fetchone(self):
                return self.next_row

        cursor = FakeCursor()
        result = supabase_backend._recalculate_next_edition_number_with_cursor(
            cursor,
            {
                "id": 1,
                "shopify_handle": "goat-debate-wall-art",
                "shopify_product_id": "gid://shopify/Product/777",
                "edition_total": 100,
                "next_edition_number": 100,
            },
            {"id": "run-1", "edition_total": 100, "next_edition_number": 100},
            reason="Manual correction",
        )

        self.assertEqual(result["next_edition_number"], 100)
        self.assertEqual(result["max_assigned"], 100)
        self.assertEqual(result["remaining_count"], 0)
        self.assertTrue(result["sold_out"])
        self.assertEqual(cursor.product_update_params[0], 100)

    def test_update_edition_products_batch_does_not_run_schema_check_on_save(self):
        class FakeCursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append(str(sql).strip())

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.committed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.committed = True

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_connection = FakeConnection()
        with patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Normal Edition Ops saves must not run schema checks."),
        ), patch.object(
            supabase_backend,
            "connect",
            return_value=fake_connection,
        ), patch.object(
            supabase_backend,
            "_update_edition_product_with_cursor",
            return_value={"handle": "legends-never-die", "next_edition_number": 43, "edition_total": 100},
        ) as update_row:
            results = supabase_backend.update_edition_products_batch(
                [
                    {
                        "row_key": "edition_product:101",
                        "edition_product_id": "101",
                        "handle": "legends-never-die",
                        "edition_total": 100,
                        "next_edition_number": 43,
                        "active": True,
                    }
                ],
                reason="Edition Ops save",
            )

        self.assertEqual(results, [{"ok": True, "handle": "legends-never-die", "key": "edition_product:101"}])
        self.assertTrue(fake_connection.committed)
        update_row.assert_called_once()

    @patch.object(supabase_backend, "process_paid_order")
    @patch.object(
        supabase_backend,
        "ensure_edition_tracking_start",
        return_value=datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc),
    )
    @patch.object(supabase_backend, "ensure_schema")
    def test_reprocess_cached_problem_orders_uses_saved_order_snapshot(
        self,
        _ensure_schema,
        _tracking_start,
        process_paid_order,
    ):
        class FakeCursor:
            def __init__(self, rows):
                self.rows = rows

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return self.rows

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConnection:
            def __init__(self, rows):
                self.rows = rows

            def cursor(self):
                return FakeCursor(self.rows)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        snapshot = self.paid_order(
            processed_at="2026-06-16T03:00:00Z",
            remote_updated_at="2026-06-16T03:05:00Z",
        )
        process_paid_order.return_value = {
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "generated_certificates": 0,
            "historical_lines_marked": 0,
            "changed_handles": [],
            "errors": [],
        }

        with patch.object(
            supabase_backend,
            "connect",
            return_value=FakeConnection(
                [{"shopify_order_id": snapshot["shopify_order_id"], "raw_json": snapshot}]
            ),
        ):
            result = supabase_backend.reprocess_cached_problem_orders(limit=10)

        self.assertEqual(result["orders_reprocessed"], 1)
        self.assertEqual(result["assignments_created"], 1)
        process_paid_order.assert_called_once()
        args, kwargs = process_paid_order.call_args
        self.assertEqual(args[0]["shopify_order_id"], snapshot["shopify_order_id"])
        self.assertTrue(kwargs["assign_editions"])
        self.assertEqual(kwargs["allocation_skip_reason"], "")

    def test_edition_order_search_by_order_name_does_not_regex_uuid_columns(self):
        where_sql, params = supabase_backend._edition_order_search_filter("#SC2843")

        self.assertIn("eo.shopify_order_name", where_sql)
        self.assertIn("o.order_name", where_sql)
        self.assertIn("eo.shopify_order_id", where_sql)
        self.assertIn("%#SC2843%", params)
        self.assertIn("%SC2843%", params)
        self.assertNotIn("~*", where_sql)
        self.assertNotIn("edition_order_id::text = %s", where_sql)

    def test_edition_order_search_only_checks_uuid_ids_for_valid_uuid_input(self):
        search = "123e4567-e89b-12d3-a456-426614174000"
        where_sql, params = supabase_backend._edition_order_search_filter(search)

        self.assertIn("eo.id::text = %s", where_sql)
        self.assertIn("c.edition_order_id::text = %s", where_sql)
        self.assertIn("c.related_edition_order_id::text = %s", where_sql)
        self.assertGreaterEqual(params.count(search), 3)
        self.assertNotIn("~*", where_sql)

    def test_edition_order_search_matches_manual_edition_number_input(self):
        where_sql, params = supabase_backend._edition_order_search_filter("#094")

        self.assertIn("eo.edition_number = %s", where_sql)
        self.assertIn(94, params)

    def test_certificate_uuid_repair_casts_before_regex(self):
        source = (Path(__file__).resolve().parents[1] / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertNotIn("edition_order_id ~*", source)
        self.assertIn("edition_order_id::text ~*", source)


class ShopifyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "sports-cave-test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def remote_product(self):
        return {
            "shopify_product_id": "gid://shopify/Product/123",
            "legacy_resource_id": "123",
            "title": "All Rise Wall Art",
            "handle": "all-rise-wall-art",
            "status": "ACTIVE",
            "vendor": "Sports Cave",
            "product_type": "Wall Art",
            "tags": ["Baseball"],
            "collections": [],
            "variants": [],
            "images": [],
            "metafields": [],
            "online_store_url": "https://sportscaveshop.com/products/all-rise-wall-art",
            "admin_url": "https://admin.shopify.com/store/sports-cave/products/123",
            "remote_updated_at": "2026-06-13T00:00:00Z",
        }

    def test_exact_handle_auto_match_and_unmatch(self):
        product_id = db.create_product(
            {
                "product_name": "All Rise Wall Art",
                "handle": "all-rise-wall-art",
                "sport_category": "Baseball",
                "country_focus": "USA",
                "status": "Live",
            }
        )
        db.upsert_shopify_products([self.remote_product()])

        matched = db.auto_match_shopify_products()
        product = db.get_product(product_id)

        self.assertEqual(matched, 1)
        self.assertEqual(product["shopify_sync_status"], "Shopify Active")
        self.assertEqual(product["shopify_variant_count"], 0)
        self.assertTrue(product["shopify_admin_url"].endswith("/products/123"))

        db.unmatch_shopify_product("gid://shopify/Product/123")
        product = db.get_product(product_id)
        self.assertEqual(product["shopify_product_id"], "")
        self.assertTrue(product["shopify_admin_url"].endswith("/products/123"))
        self.assertEqual(product["shopify_sync_status"], "Not Matched")

    def test_create_internal_product_from_shopify(self):
        db.upsert_shopify_products([self.remote_product()])
        product_id = db.create_product_from_shopify("gid://shopify/Product/123")
        product = db.get_product(product_id)

        self.assertEqual(product["product_name"], "All Rise Wall Art")
        self.assertEqual(product["status"], "Live")
        self.assertEqual(product["shopify_sync_status"], "Shopify Active")


class LimitedEditionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "sports-cave-editions-test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def remote_product(self):
        return {
            "shopify_product_id": "gid://shopify/Product/999",
            "legacy_resource_id": "999",
            "title": "Messi The Final Crown Wall Art",
            "handle": "messi-the-final-crown-wall-art",
            "status": "ACTIVE",
            "vendor": "Sports Cave",
            "product_type": "Wall Art",
            "tags": ["Soccer"],
            "collections": [],
            "variants": [],
            "images": [],
            "metafields": [],
            "online_store_url": "https://sportscaveshop.com/products/messi-the-final-crown-wall-art",
            "admin_url": "https://admin.shopify.com/store/sports-cave/products/999",
            "remote_updated_at": "2026-06-13T00:00:00Z",
        }

    def paid_order(self, line_id="gid://shopify/LineItem/1", quantity=1):
        return {
            "shopify_order_id": "gid://shopify/Order/1000",
            "legacy_resource_id": "1000",
            "order_name": "#1000",
            "order_number": "1000",
            "admin_url": "https://admin.shopify.com/store/sports-cave/orders/1000",
            "created_at": "2026-06-13T00:00:00Z",
            "paid_at": "2026-06-13T00:01:00Z",
            "financial_status": "PAID",
            "fulfillment_status": "UNFULFILLED",
            "customer_name": "Collector",
            "customer_email": "collector@example.com",
            "line_items": [
                {
                    "shopify_line_item_id": line_id,
                    "shopify_product_id": "gid://shopify/Product/999",
                    "product_title": "Messi The Final Crown Wall Art",
                    "product_handle": "messi-the-final-crown-wall-art",
                    "variant_title": "Black / XL",
                    "quantity": quantity,
                }
            ],
        }

    def seed_edition_product(self, *, limit=100, next_number=37, sold=36):
        db.upsert_shopify_products([self.remote_product()])
        return db.update_shopify_edition_product(
            "gid://shopify/Product/999",
            edition_limit=limit,
            next_available_edition=next_number,
            editions_sold=sold,
            psd_file_url="https://drive.google.com/psd",
            prodigi_url="https://dashboard.prodigi.com/product/999",
            prodigi_product_id="GLOBAL-CFP-A1",
        )

    def test_paid_quantity_assigns_sequential_numbers_and_is_idempotent(self):
        self.seed_edition_product()
        order = self.paid_order(quantity=2)

        result = db.process_shopify_order_for_editions(order)
        product = db.get_shopify_edition_product("gid://shopify/Product/999")

        self.assertEqual(result["assignments_created"], 2)
        self.assertEqual(product["next_available_edition"], 39)
        self.assertEqual(product["editions_sold"], 38)
        self.assertEqual(product["editions_remaining"], 62)
        assignments = db.list_shopify_orders()[0]["line_items"][0]["assignments"]
        self.assertEqual([item["edition_number"] for item in assignments], [37, 38])

        second_result = db.process_shopify_order_for_editions(order)
        product_after_resync = db.get_shopify_edition_product("gid://shopify/Product/999")
        self.assertEqual(second_result["assignments_created"], 0)
        self.assertEqual(product_after_resync["next_available_edition"], 39)

    def test_paid_order_matches_cached_product_by_handle(self):
        self.seed_edition_product()
        order = self.paid_order()
        order["line_items"][0]["shopify_product_id"] = "gid://shopify/Product/missing-from-order"

        result = db.process_shopify_order_for_editions(order)
        line = db.list_shopify_orders()[0]["line_items"][0]

        self.assertEqual(result["assignments_created"], 1)
        self.assertEqual(line["shopify_product_id"], "gid://shopify/Product/999")
        self.assertEqual(line["assignments"][0]["edition_number"], 37)

    def test_sold_out_line_does_not_assign_duplicate_or_over_limit(self):
        self.seed_edition_product(limit=1, next_number=2, sold=1)
        result = db.process_shopify_order_for_editions(self.paid_order(quantity=1))

        line = db.list_shopify_orders()[0]["line_items"][0]
        self.assertEqual(result["assignments_created"], 0)
        self.assertEqual(line["assignment_status"], "Sold Out")
        self.assertEqual(line["assignments"], [])

    def test_manual_override_blocks_duplicate_edition_numbers(self):
        self.seed_edition_product(limit=100, next_number=1, sold=0)
        db.process_shopify_order_for_editions(self.paid_order(line_id="gid://shopify/LineItem/1"))
        second_order = self.paid_order(line_id="gid://shopify/LineItem/2")
        second_order["shopify_order_id"] = "gid://shopify/Order/1001"
        second_order["order_name"] = "#1001"
        db.process_shopify_order_for_editions(second_order)
        second_line_id = db.list_shopify_orders()[0]["line_items"][0]["id"]

        with self.assertRaises(ValueError):
            db.manual_override_edition_assignment(second_line_id, 1, notes="Duplicate check")

    def test_metafield_inputs_use_exact_display_text_and_no_inventory(self):
        product = self.seed_edition_product(limit=100, next_number=98, sold=97)
        metafields = shopify_sync.edition_metafield_inputs(product)
        keys = {item["key"]: item for item in metafields}

        self.assertEqual(keys["edition_display_text"]["value"], "FINAL EDITION #98 OF 100 AVAILABLE")
        self.assertNotIn("inventory", " ".join(item["key"] for item in metafields).lower())


if __name__ == "__main__":
    unittest.main()
