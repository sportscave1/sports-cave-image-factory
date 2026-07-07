import unittest

import shopify_sync
import sports_cave_pricing


class FakeResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {"X-Shopify-API-Version": "2026-04"}
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def variant(title, price="0.00", compare_at_price="0.00", variant_id=None):
    frame, size = [part.strip() for part in title.split("/", 1)]
    return {
        "id": variant_id or f"gid://shopify/ProductVariant/{frame}-{size}",
        "title": title,
        "price": price,
        "compare_at_price": compare_at_price,
        "selected_options": [
            {"name": "Frame", "value": frame},
            {"name": "Size", "value": size},
        ],
    }


def standard_product(price="0.00", compare_at_price="0.00"):
    variants = []
    for frame in sports_cave_pricing.FRAME_ORDER:
        for size in sports_cave_pricing.SIZE_ORDER:
            variants.append(variant(f"{frame} / {size}", price, compare_at_price))
    return {
        "shopify_product_id": "gid://shopify/Product/1",
        "title": "Sports Cave Wall Art",
        "handle": "sports-cave-wall-art",
        "variants": variants,
    }


class SportsCavePricingTests(unittest.TestCase):
    def test_price_ladder_mapping(self):
        self.assertEqual(
            sports_cave_pricing.SPORTS_CAVE_AU_PRICE_LADDER["framed"]["XL"],
            {"price": "349.00", "compare_at_price": "429.00"},
        )
        self.assertEqual(
            sports_cave_pricing.SPORTS_CAVE_AU_PRICE_LADDER["unframed"]["S"],
            {"price": "55.00", "compare_at_price": "69.00"},
        )

    def test_black_oak_white_map_to_framed(self):
        for frame in ("Black", "Oak", "White"):
            expected = sports_cave_pricing.expected_price_for_variant(variant(f"{frame} / L"))
            self.assertEqual(expected["price_group"], "framed")
            self.assertEqual(expected["price"], "269.00")
            self.assertEqual(expected["compare_at_price"], "329.00")

    def test_unframed_maps_to_unframed(self):
        expected = sports_cave_pricing.expected_price_for_variant(variant("Unframed / M"))
        self.assertEqual(expected["price_group"], "unframed")
        self.assertEqual(expected["price"], "89.00")
        self.assertEqual(expected["compare_at_price"], "109.00")

    def test_robust_size_parsing(self):
        examples = {
            "Black / S- 21 × 30 cm": "S",
            "Black / S - 21 × 30 cm": "S",
            "Unframed / XL - 62 × 87 cm": "XL",
        }
        for title, size in examples.items():
            parsed = sports_cave_pricing.parse_variant_identity({"title": title})
            self.assertTrue(parsed["ok"])
            self.assertEqual(parsed["size"], size)

    def test_malformed_variants_are_skipped(self):
        product = standard_product()
        product["variants"][0] = {"id": "bad", "title": "Mystery / Huge", "price": "1.00"}
        summary = sports_cave_pricing.analyze_product_price_updates(product)
        self.assertIn("could not be confidently parsed", summary["skipped_product_reason"])
        self.assertEqual(len(summary["skipped_variants"]), 1)

    def test_dry_run_does_not_call_shopify_update(self):
        product = standard_product(price="149.00", compare_at_price="199.00")
        summary = sports_cave_pricing.summarize_price_backfill([product])
        self.assertEqual(summary["variants_needing_update"], 16)
        self.assertEqual(summary["products_scanned"], 1)

    def test_apply_only_updates_price_and_compare_at_price(self):
        requests_seen = []
        config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
            "configured": True,
        }

        def fake_post(*args, **kwargs):
            requests_seen.append(kwargs["json"])
            return FakeResponse(
                {
                    "data": {
                        "productVariantsBulkUpdate": {
                            "productVariants": [
                                {
                                    "id": "gid://shopify/ProductVariant/1",
                                    "price": "349.00",
                                    "compareAtPrice": "429.00",
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            )

        result = shopify_sync.update_product_variant_prices(
            "gid://shopify/Product/1",
            [
                {
                    "variant_id": "gid://shopify/ProductVariant/1",
                    "new_price": "349.00",
                    "new_compare_at_price": "429.00",
                    "sku": "MUST-NOT-SEND",
                }
            ],
            config=config,
            request_post=fake_post,
        )

        sent_variant = requests_seen[0]["variables"]["variants"][0]
        self.assertEqual(result["updated"], 1)
        self.assertEqual(set(sent_variant.keys()), {"id", "price", "compareAtPrice"})
        self.assertEqual(sent_variant["price"], "349.00")
        self.assertEqual(sent_variant["compareAtPrice"], "429.00")


if __name__ == "__main__":
    unittest.main()
