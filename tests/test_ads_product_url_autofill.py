"""Exact-row URL resolution and the real Streamlit selection callback."""
import unittest
from unittest.mock import patch

import ads_page as ads
from ads_product_catalog import recommend_new_ads_category
from tests.test_ads_page import run_ads_page_with_product_rows, select_option


class NewAdsDefaultsTests(unittest.TestCase):
    def test_collection_and_specific_motorsport_evidence(self):
        cases = (
            ({"collections": ["NBA Wall Art"]}, "A Cricket Title", "NBA"),
            ({"collections": ["Motor Racing Wall Art", "V8 Supercars Wall Art"]}, "Tribute", "V8 Supercars"),
            ({"collections": [{"handle": "nascar-wall-art", "title": "Stock Cars"}]}, "Tribute", "NASCAR"),
            ({"collections": ["Motor Racing Wall Art"], "tags": ["SC_SPORT_FORMULA_ONE"]}, "Tribute", "Formula One"),
            ({"collections": ["Motor Racing Wall Art"]}, "Jett Lawrence Tribute", "Motocross"),
            ({"collections": ["Motor Racing Wall Art"]}, "VW Golf", ""),
            ({"collections": ["Motor Racing Wall Art"]}, "Unknown Racing Tribute", ""),
            ({"collections": ["NASCAR Wall Art", "Formula One Wall Art"]}, "Tribute", ""),
        )
        for row, title, expected in cases:
            with self.subTest(row=row, title=title):
                self.assertEqual(recommend_new_ads_category(row, title), expected)

    def test_new_meta_product_selection_sets_defaults_and_allows_override(self):
        rows = [
            {"shopify_product_id": "a", "product_title": "Race Tribute", "collections": ["NASCAR Wall Art"]},
            {"shopify_product_id": "b", "product_title": "Unknown Tribute", "collections": ["Motor Racing Wall Art"]},
        ]
        app = run_ads_page_with_product_rows(rows)
        self.assertEqual(app.selectbox(key="ads_campaign_type").value, "Instant Experience")
        select_option(app, "Product name", "Race Tribute")
        self.assertEqual(app.selectbox(key="ads_category").value, "NASCAR")
        select_option(app, "Category", "V8 Supercars")
        select_option(app, "Campaign type", "Carousel")
        self.assertEqual(app.selectbox(key="ads_category").value, "V8 Supercars")
        self.assertEqual(app.selectbox(key="ads_campaign_type").value, "Carousel")
        select_option(app, "Product name", "Unknown Tribute")
        self.assertEqual(app.selectbox(key="ads_category").value, "Select category")
        self.assertEqual(app.selectbox(key="ads_campaign_type").value, "Instant Experience")
        self.assertEqual(len(app.exception), 0)

    def test_google_keeps_demand_gen_when_product_is_selected(self):
        rows = [{"product_title": "Race Tribute", "collections": ["NASCAR Wall Art"]}]
        app = run_ads_page_with_product_rows(rows)
        select_option(app, "Platform", "Google")
        select_option(app, "Product name", "Race Tribute")
        self.assertEqual(app.selectbox(key="ads_category").value, "NASCAR")
        self.assertEqual(app.selectbox(key="ads_google_campaign_type").value, "Demand Gen")
        self.assertEqual(len(app.exception), 0)


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
