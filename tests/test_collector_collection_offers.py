import io
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image

import collector_collection_offers as offers
import collector_vault
from tests.test_collector_vault import _frame_product_payload, _frame_environment, _certificate_row, CUSTOMER_A


class CollectionOffersTests(unittest.TestCase):
    def test_account_matching_excludes_all_purchases_and_certificates(self):
        owned = "gid://shopify/Product/55"
        certificate_product = "gid://shopify/Product/56"
        candidate = "gid://shopify/Product/57"
        catalogue = MagicMock()
        catalogue.resolve.return_value = [{"id": candidate, "edition": {"sold": 3}}]
        with patch("crm_smart_catalogue.histories", return_value={CUSTOMER_A: [{"products": [{"product_id": 55}]}]}), \
             patch.object(collector_vault, "list_owned_certificates", return_value=[{"shopify_product_id": certificate_product}]), \
             patch("crm_collector_transport.bounded", return_value=MagicMock()), patch("crm_catalogue.Catalogue", return_value=catalogue), \
             patch("crm_smart_candidates.memberships", return_value=[{"id": "sport"}]), \
             patch("crm_smart_candidates.collection_products", return_value=[owned, certificate_product, candidate]), \
             patch("crm_catalogue.edition_available", return_value=True), patch("crm_catalogue.product_issues", return_value=[]):
            result = offers.recommendations(CUSTOMER_A)
        self.assertEqual([p["id"] for p in result], [candidate])
        self.assertEqual(catalogue.resolve.call_args.args[0], [candidate])

    def test_oak_paid_webhook_matches_request_and_variant_together(self):
        import os
        reference = "12345678-1234-4234-8234-123456789012"
        oak = "gid://shopify/ProductVariant/2"
        payload = {"id": 99, "customer": {"id": 101}, "line_items": [{
            "product_id": _frame_environment()["FRAMED_CERTIFICATE_PRODUCT_ID"],
            "variant_id": oak, "sku": "SC-FCC-A4-OAK",
            "properties": [{"name": "_sports_cave_frame_request", "value": reference}],
        }]}
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        with patch.dict(os.environ, _frame_environment(), clear=True), patch.object(collector_vault.supabase_backend, "connect", return_value=connection):
            collector_vault.process_framed_order_paid(payload)
        sql, params = cursor.execute.call_args.args
        self.assertIn("request_reference::text, frame_variant_id", sql)
        self.assertEqual(params[-2:], ([reference], [oak]))

    def test_only_known_available_certificate_skus_are_offered(self):
        product = _frame_product_payload()["product"]
        base = product["variants"]["nodes"][0]
        product["variants"]["nodes"] += [
            dict(base, id="gid://shopify/ProductVariant/2", sku="SC-FCC-A4-OAK"),
            dict(base, id="gid://shopify/ProductVariant/3", sku="SC-FCC-A4-WHT"),
            dict(base, id="gid://shopify/ProductVariant/4", sku="OTHER"),
            dict(base, id="gid://shopify/ProductVariant/5", sku="SC-FCC-A4-OAK", availableForSale=False),
        ]
        self.assertEqual([v["color"] for v in offers.frame_variants(product)], ["Black", "Oak", "White"])

    def test_owner_preview_preserves_certificate_edges_for_every_frame(self):
        with Image.new("RGB", (700, 500), "red") as image:
            stream = io.BytesIO()
            image.save(stream, "PNG")
        for color in ("black", "oak", "white"):
            with self.subTest(color=color), Image.open(io.BytesIO(offers.render_certificate_frame(stream.getvalue(), color))) as rendered:
                x, y, w, h = offers.FRAME_BOX
                for point in ((x + 10, y + 10), (x + w - 10, y + h - 10)):
                    red, green, blue = rendered.getpixel(point)
                    self.assertGreater(red, 230)
                    self.assertLess(green, 30)
                    self.assertLess(blue, 30)
        with self.assertRaises(ValueError):
            offers.render_certificate_frame(stream.getvalue(), "../../other")

    def test_frame_request_rejects_arbitrary_variant_before_database_access(self):
        with patch.object(collector_vault, "_resolve_certificate_reference", return_value=_certificate_row()), \
             patch.object(collector_vault, "get_frame_product", return_value={"available": True, "variant_id": "gid://shopify/ProductVariant/1", "variants": [{"variant_id": "gid://shopify/ProductVariant/2"}]}), \
             patch.object(collector_vault.supabase_backend, "connect") as connect:
            with self.assertRaises(collector_vault.CollectorVaultUnavailableError):
                collector_vault.create_frame_request(CUSTOMER_A, certificate_reference="owned", frame_variant_id="gid://shopify/ProductVariant/99", idempotency_key="test-key-123")
            connect.assert_not_called()

    def test_personalized_offer_does_not_require_public_product_image(self):
        import os
        payload = _frame_product_payload()
        payload["product"]["featuredImage"] = None
        with patch.dict(os.environ, _frame_environment(), clear=True), patch.object(collector_vault.shopify_sync, "graphql_request", return_value=(payload, "2026-04")):
            result = collector_vault.get_frame_product(force=True)
        self.assertTrue(result["available"])
        self.assertEqual(result["variants"][0]["color"], "Black")
