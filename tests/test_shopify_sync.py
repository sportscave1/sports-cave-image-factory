from pathlib import Path
import tempfile
import unittest

import db
import shopify_sync


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
        self.config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "api_version": "2026-04",
            "max_products": 25,
            "configured": True,
        }

    def test_normalize_store_domain(self):
        self.assertEqual(
            shopify_sync.normalize_store_domain("https://SPORTS-CAVE.myshopify.com/admin"),
            "sports-cave.myshopify.com",
        )

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


if __name__ == "__main__":
    unittest.main()
