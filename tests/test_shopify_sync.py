import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import db
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

    def test_edition_ops_sync_batches_five_products_per_metafields_set(self):
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
                "edition_status_override": "",
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
        self.assertEqual(len(requests_seen), 2)
        self.assertEqual(len(requests_seen[0]["variables"]["metafields"]), 20)
        self.assertEqual(len(requests_seen[1]["variables"]["metafields"]), 8)

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

        self.assertEqual(len(result["created"]), 4)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["definitions"][0]["status"], "Ready")
        create_requests = [request for request in requests_seen if "metafieldDefinitionCreate" in request["query"]]
        self.assertEqual(len(create_requests), 4)
        created_keys = {request["variables"]["definition"]["key"] for request in create_requests}
        self.assertNotIn("edition_enabled", created_keys)
        self.assertIn("edition_next_number", created_keys)

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
                                        "key": "edition_status_override",
                                        "type": "single_line_text_field",
                                        "value": " ",
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
                "edition_status_override": "",
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
                "edition_label",
            },
        )
        self.assertEqual(keys["edition_enabled"]["type"], "boolean")
        self.assertEqual(keys["edition_enabled"]["value"], "true")
        self.assertNotIn("remaining_count", keys)
        self.assertNotIn("sold_count", keys)
        self.assertEqual(result["edition"]["remaining"], 3)
        self.assertEqual(result["edition"]["edition_status_override"], "")

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
        self.assertNotIn("shippingLine", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("shippingAddress", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("billingAddress", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("email", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("updatedAt", shopify_sync.ORDERS_SAFE_QUERY)
        self.assertIn("totalPriceSet", shopify_sync.ORDERS_SAFE_QUERY)


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

    def paid_order(self, *, processed_at, remote_updated_at):
        return {
            "shopify_order_id": "gid://shopify/Order/1000",
            "legacy_resource_id": "1000",
            "order_name": "#1000",
            "order_number": "1000",
            "admin_url": "https://admin.shopify.com/store/sports-cave/orders/1000",
            "created_at": "2026-06-01T00:00:00Z",
            "processed_at": processed_at,
            "remote_updated_at": remote_updated_at,
            "paid_at": processed_at,
            "financial_status": "PAID",
            "fulfillment_status": "UNFULFILLED",
            "customer_name": "Collector",
            "customer_email": "collector@example.com",
            "line_items": [
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/1",
                    "shopify_product_id": "gid://shopify/Product/999",
                    "product_title": "Messi The Final Crown Wall Art",
                    "product_handle": "messi-the-final-crown-wall-art",
                    "variant_title": "Black / XL",
                    "quantity": 1,
                }
            ],
        }

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
    @patch.object(supabase_backend, "_record_order_fetch_metrics")
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    def test_initial_order_sync_bootstraps_recent_orders_window(
        self,
        process_shopify_order_for_editions,
        _record_order_fetch_metrics,
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
    @patch.object(supabase_backend, "_record_order_fetch_metrics")
    @patch.object(supabase_backend, "process_shopify_order_for_editions")
    def test_incremental_sync_keeps_historical_updates_but_skips_auto_assignment(
        self,
        process_shopify_order_for_editions,
        _record_order_fetch_metrics,
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

    def test_manual_edition_counter_ahead_of_history_is_respected(self):
        result = supabase_backend._resolve_next_edition_number_state(75, 12, False)

        self.assertEqual(result["next_number"], 75)
        self.assertEqual(result["mode"], "respect_manual_counter")

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
