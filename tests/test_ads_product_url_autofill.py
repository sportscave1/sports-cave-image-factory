"""Exact-row URL resolution and the real Streamlit selection callback."""
import unittest
from unittest.mock import patch

import ads_page as ads
from tests.test_ads_page import run_ads_page_with_product_rows


class ProductURLAutofillTests(unittest.TestCase):
    def test_stored_url_precedes_handle_and_handle_aliases_fall_back(self):
        stored = "https://www.sportscaveshop.com/products/example-product"
        row = {"product_title": "Example Product", "product_handle": "example-product", "online_store_url": stored}
        self.assertEqual(ads._edition_ops_product_page_url_from_row(row), stored)
        for field in ("product_handle", "shopify_handle"):
            with self.subTest(field=field):
                self.assertEqual(ads._edition_ops_product_page_url_from_row({"product_title": "A completely different title", field: "example-product", "online_store_url": ""}), stored)

    def test_invalid_or_foreign_url_uses_handle_not_title(self):
        for url in ("not-a-url", "https://other-shop.example/products/wrong", "https://www.sportscaveshop.com.evil.example/products/wrong"):
            with self.subTest(url=url):
                self.assertEqual(ads._edition_ops_product_page_url_from_row({"online_store_url": url, "product_handle": "exact-handle"}), "https://www.sportscaveshop.com/products/exact-handle")
        for handle in ("", "bad handle", "../wrong", "https://example.com/product"):
            self.assertEqual(ads._edition_ops_product_page_url_from_row({"product_title": "Never Slug This Title", "product_handle": handle}), "")

    def test_callback_uses_supplied_rows_without_catalogue_or_network_lookup(self):
        rows = [{"shopify_product_id": "42", "product_title": "Example", "product_handle": "exact-row", "online_store_url": ""}]
        record = ads.build_ads_product_selector_records(rows)[0]
        state = {ads.ADS_PRODUCT_SELECTOR_KEY: record["identity"]}
        with patch.object(ads.st, "session_state", state), patch("ads_page.load_edition_ops_product_rows", side_effect=AssertionError("No catalogue reload")), patch("requests.sessions.Session.request", side_effect=AssertionError("No HTTP request")):
            ads._on_ads_product_selector_changed(rows)
        expected = "https://www.sportscaveshop.com/products/exact-row"
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY], expected)
        self.assertEqual(state[ads.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY], expected)
        self.assertFalse(state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY])

    def test_rendered_switches_duplicates_manual_edit_and_unresolved_warning(self):
        rows = [
            {"shopify_product_id": "a", "product_title": "Same Name", "product_handle": "product-a", "online_store_url": "https://www.sportscaveshop.com/products/product-a"},
            {"shopify_product_id": "b", "product_title": "Same Name", "product_handle": "product-b", "online_store_url": ""},
            {"shopify_product_id": "c", "product_title": "Similar Name", "shopify_handle": "product-c", "online_store_url": ""},
            {"shopify_product_id": "d", "product_title": "Unresolved Product", "product_handle": "invalid handle", "online_store_url": ""},
        ]
        app = run_ads_page_with_product_rows(rows)

        def field():
            return next(x for x in app.text_input if x.label == "Product page URL *")

        for label, handle in (("Same Name (product-a)", "product-a"), ("Same Name (product-b)", "product-b"), ("Similar Name", "product-c"), ("Same Name (product-a)", "product-a")):
            next(x for x in app.selectbox if x.label == "Product name").select(label)
            app.run(timeout=20)
            expected = "https://www.sportscaveshop.com/products/" + handle
            self.assertEqual(field().value, expected)
            self.assertEqual(app.session_state[ads.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY], expected)
            self.assertFalse(app.session_state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY])
        field().set_value("https://www.sportscaveshop.com/products/manual-a")
        app.run(timeout=20)
        app.run(timeout=20)
        self.assertEqual(field().value, "https://www.sportscaveshop.com/products/manual-a")
        next(x for x in app.selectbox if x.label == "Product name").select("Same Name (product-b)")
        app.run(timeout=20)
        self.assertEqual(field().value, "https://www.sportscaveshop.com/products/product-b")
        self.assertFalse(app.session_state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY])
        next(x for x in app.selectbox if x.label == "Product name").select("Unresolved Product")
        app.run(timeout=20)
        self.assertEqual(field().value, "")
        self.assertTrue(any(ads.NO_EDITION_OPS_PRODUCT_URL_MESSAGE in x.value for x in list(app.warning) + list(app.caption)))
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
