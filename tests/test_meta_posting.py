import io
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import ads_meta_review_page
import ads_navigation
import ads_page
import ads_posting_page
import meta_ads_client
from meta_posting_service import (
    SUCCESS_MESSAGE,
    MetaPostingService,
    PostingError,
    PostingRequest,
    PostingValidationError,
    build_adset_payload,
    build_campaign_payload,
    build_collection_creative_payload,
    build_storefront_element_specs,
    build_targeting,
    adset_name,
    campaign_name,
    COUNTRY_META_CODES,
    next_instant_experience_ad_name,
    product_short_name,
)


ROOT = Path(__file__).resolve().parents[1]


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 30, 40)).save(output, format="JPEG")
    return output.getvalue()


def request_for(**overrides):
    values = {
        "submission_id": "11111111-1111-4111-8111-111111111111",
        "product_id": "shopify-1",
        "product_title": "Max Verstappen Victory Sports Wall Art",
        "product_handle": "max-verstappen-victory",
        "destination_url": "https://sportscaveshop.com/products/max-verstappen-victory",
        "image_bytes": image_bytes(),
        "image_name": "artwork.jpg",
        "country": "AUS",
        "sport": "Motorsport",
        "catalog_id": "catalog-1",
        "product_set_id": "set-1",
        "audience_type": "broad",
        "audience_id": "",
        "primary_text": "Own the moment.",
        "headline": "Claim the limited edition",
        "description": "Limited Edition",
    }
    values.update(overrides)
    return PostingRequest(**values)


class FakePostingStore:
    def __init__(self, existing=None):
        self.record = dict(existing or {})
        self.claims = 0
        self.stages = []

    def claim(self, request_data, *, lease_token):
        self.claims += 1
        if self.record:
            if self.record.get("status") == "FAILED":
                return {"claimed": True, "record": dict(self.record)}
            return {"claimed": False, "record": dict(self.record)}
        self.record = dict(request_data)
        self.record["status"] = "VALIDATING"
        return {"claimed": True, "record": dict(self.record)}

    def update_stage(self, submission_id, status, **fields):
        self.record.update(fields)
        self.record["submission_id"] = submission_id
        self.record["status"] = status
        self.stages.append((status, dict(fields)))
        return dict(self.record)

    def recent(self, limit=20):
        return [dict(self.record)] if self.record else []


class FakePostingClient:
    ad_account_id = "act_123"
    page_id = "page-1"
    instagram_actor_id = "ig-1"
    instagram_user_id = "ig-1"

    def __init__(self, *, fail_at=""):
        self.fail_at = fail_at
        self.calls = []
        self.campaign_payload = None
        self.adset_payload = None
        self.creative_payload = None
        self.last_ad_name = ""

    def permissions(self):
        return ("ads_management",)

    def reference_data(self):
        return {
            "account": {"id": "act_123", "currency": "AUD"},
            "page": {"id": self.page_id, "name": "Sports Cave"},
            "instagram": {"id": self.instagram_user_id, "username": "sportscave"},
            "catalogs": ({"id": "catalog-1", "name": "Shopify Product Catalog"},),
            "pixels": ({"id": "pixel-1", "name": "Sports Cave Pixel 2025"},),
            "saved_audiences": (
                {"id": "saved-1", "name": "Collectors", "targeting": {"age_min": 30}},
            ),
            "custom_audiences": ({"id": "custom-1", "name": "Customers"},),
        }

    def product_sets(self, catalog_id):
        self.calls.append("read_product_sets")
        return ({"id": "set-1", "name": "Motorsport", "product_catalog": {"id": catalog_id}},)

    def existing_ad_names(self):
        return ("Max Verstappen Victory IA 1", "Other IA 4")

    def create_campaign(self, payload):
        self.calls.append("campaign")
        self.campaign_payload = payload
        return "campaign-1"

    def find_campaigns_by_name(self, name):
        return ()

    def create_adset(self, payload):
        self.calls.append("adset")
        self.adset_payload = payload
        return "adset-1"

    def find_adsets_by_name(self, campaign_id, name):
        return ()

    def upload_image(self, data, *, filename, content_type):
        self.calls.append("ad_image")
        return "image-hash-1"

    def upload_page_photo(self, data, *, filename, content_type):
        self.calls.append("page_photo")
        return "photo-1"

    def create_canvas_element(self, element_type, specification):
        self.calls.append(element_type)
        if self.fail_at == element_type:
            raise meta_ads_client.MetaAdsApiError("element failed")
        return {
            "canvas_photo": "photo-element-1",
            "canvas_product_set": "product-element-1",
            "canvas_button": "button-element-1",
            "canvas_footer": "footer-element-1",
        }[element_type]

    def create_canvas(self, *, name, body_element_ids):
        self.calls.append("canvas")
        return "canvas-1"

    def find_canvases_by_name(self, name):
        return ()

    def create_collection_creative(self, payload):
        self.calls.append("creative")
        self.creative_payload = payload
        return "creative-1"

    def find_creative_by_name(self, name):
        return None

    def create_paused_ad(self, *, ad_name, adset_id, creative_id):
        self.calls.append("ad")
        self.last_ad_name = ad_name
        return "ad-1"

    def find_ad_by_creative(self, adset_id, creative_id):
        return None

    def configured_campaign(self, campaign_id):
        return {"id": campaign_id, "configured_status": "PAUSED"}

    def configured_adset(self, adset_id):
        return {"id": adset_id, "configured_status": "PAUSED"}

    def ad(self, ad_id):
        return {"id": ad_id, "configured_status": "PAUSED"}


class PostingNavigationTests(unittest.TestCase):
    def test_meta_review_is_last_ads_child(self):
        self.assertEqual(
            ads_navigation.ADS_ROUTES,
            ("Ads", "Creative Refresh", "Posting", "Meta Review"),
        )
        self.assertEqual(ads_navigation.ADS_NAV_LABELS["Ads"], "New Ads")

    def test_pages_are_lazy_loaded_and_routed(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('importlib.import_module("ads_posting_page")', source)
        self.assertIn('importlib.import_module("ads_meta_review_page")', source)
        self.assertIn("get_ads_meta_review_page().render_page()", source)


class PostingPayloadTests(unittest.TestCase):
    def test_names_remove_generic_suffix_and_increment_ia(self):
        self.assertEqual(
            product_short_name("Max Verstappen Victory — Sports Wall Art"),
            "Max Verstappen Victory",
        )
        self.assertEqual(
            next_instant_experience_ad_name(
                "Max Verstappen Victory Sports Wall Art",
                ("Max Verstappen Victory IA 1", "Max Verstappen Victory IA 3"),
            ),
            "Max Verstappen Victory IA 4",
        )
        self.assertEqual(
            campaign_name(
                "Max Verstappen Victory Sports Wall Art", "AUS", "Motorsport",
                now=__import__("datetime").datetime(2026, 9, 1),
            ),
            "010926 AUS Motorsport Max Verstappen Victory",
        )
        boundary = __import__("datetime").datetime(
            2026, 8, 31, 15, 30, tzinfo=__import__("datetime").timezone.utc
        )
        self.assertTrue(campaign_name("Product", "AUS", "Other", now=boundary).startswith("010926"))
        self.assertEqual(adset_name("USA", "NBA", "Collectors"), "USA NBA Collectors")

    def test_country_codes_are_exact(self):
        self.assertEqual(
            COUNTRY_META_CODES,
            {"AUS": "AU", "USA": "US", "UK": "GB", "CAN": "CA", "NZ": "NZ"},
        )

    def test_canonical_product_selection_supplies_url(self):
        rows = [
            {
                "shopify_product_id": "1", "product_title": "Shane Warne Sports Wall Art",
                "product_handle": "shane-warne", "online_store_url": "https://www.sportscaveshop.com/products/shane-warne",
            }
        ]
        records = ads_page.build_ads_product_selector_records(rows)
        selection = ads_page.resolve_ads_product_selector_value(
            records[0]["identity"], rows=rows, records=records
        )
        self.assertEqual(
            selection["product_url"], "https://www.sportscaveshop.com/products/shane-warne"
        )

    def test_campaign_is_paused_sales_cbo(self):
        payload = build_campaign_payload(name="Campaign", catalog_id="catalog-1")
        self.assertEqual(payload["objective"], "OUTCOME_SALES")
        self.assertEqual(payload["daily_budget"], "2500")
        self.assertEqual(payload["status"], "PAUSED")
        self.assertEqual(payload["promoted_object"]["product_catalog_id"], "catalog-1")

    def test_broad_targeting_uses_country_and_advantage_without_placements(self):
        targeting = build_targeting(country="AUS")
        self.assertEqual(targeting["geo_locations"], {"countries": ["AU"]})
        self.assertEqual(targeting["age_min"], 24)
        self.assertEqual(targeting["age_max"], 65)
        self.assertEqual(targeting["targeting_automation"], {"advantage_audience": 1})
        self.assertNotIn("publisher_platforms", targeting)
        self.assertNotIn("facebook_positions", targeting)

    def test_saved_audience_strips_manual_placements_and_forces_country(self):
        targeting = build_targeting(
            country="UK", audience_type="saved",
            audience={
                "id": "saved-1",
                "targeting": {"age_min": 35, "publisher_platforms": ["facebook"], "geo_locations": {"countries": ["US"]}},
            },
        )
        self.assertEqual(targeting["age_min"], 35)
        self.assertEqual(targeting["geo_locations"], {"countries": ["GB"]})
        self.assertNotIn("publisher_platforms", targeting)

    def test_adset_optimizes_purchase_and_remains_paused(self):
        payload = build_adset_payload(
            name="Ad set", campaign_id="campaign-1", product_set_id="set-1",
            pixel_id="pixel-1", targeting=build_targeting(country="AUS"),
        )
        self.assertEqual(payload["status"], "PAUSED")
        self.assertEqual(payload["optimization_goal"], "OFFSITE_CONVERSIONS")
        self.assertEqual(payload["promoted_object"]["custom_event_type"], "PURCHASE")
        self.assertEqual(payload["promoted_object"]["product_set_id"], "set-1")

    def test_collection_creative_contract(self):
        payload = build_collection_creative_payload(
            name="Creative", page_id="page-1", instagram_user_id="ig-1",
            image_hash="hash", canvas_id="canvas-1", product_set_id="set-1",
            destination_url="https://sportscaveshop.com/products/a", primary_text="Text",
            headline="Headline",
        )
        link = payload["object_story_spec"]["link_data"]
        self.assertEqual(link["canvas_id"], "canvas-1")
        self.assertEqual(link["call_to_action"]["type"], "SHOP_NOW")
        self.assertEqual(payload["contextual_multi_ads"], {"enroll_status": "OPT_IN"})
        features = payload["degrees_of_freedom_spec"]["creative_features_spec"]
        self.assertEqual(features["hide_price"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["inline_comment"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["image_background_gen"]["enroll_status"], "OPT_OUT")
        self.assertIn("utm_source=facebook", payload["url_tags"])

    def test_storefront_component_contract(self):
        specs = build_storefront_element_specs(
            page_photo_id="photo-1", product_set_id="set-1",
            destination_url="https://sportscaveshop.com/products/shane-warne",
            button_element_id="button-1",
        )
        self.assertEqual(specs["canvas_photo"]["photo_id"], "photo-1")
        self.assertEqual(specs["canvas_product_set"]["product_set_id"], "set-1")
        self.assertEqual(specs["canvas_product_set"]["item_headline"], "{{product.name}}")
        self.assertEqual(specs["canvas_product_set"]["item_description"], "Limited Edition")
        self.assertEqual(specs["canvas_button"]["rich_text"]["plain_text"], "Claim Your Edition")
        self.assertEqual(
            specs["canvas_button"]["open_url_action"]["url"],
            "https://sportscaveshop.com/products/shane-warne",
        )
        self.assertEqual(specs["canvas_footer"]["child_elements"], ["button-1"])


class MetaPostingClientTests(unittest.TestCase):
    def config(self):
        return {
            "configured": True, "ad_account_id": "act_123", "access_token": "secret",
            "api_version": "v26.0", "page_id": "page-1", "instagram_user_id": "ig-1",
        }

    @mock.patch("meta_ads_client._post")
    def test_new_object_writes_use_expected_edges_and_json(self, post):
        post.side_effect = [
            {"id": "campaign-1"}, {"id": "adset-1"}, {"id": "photo-1"},
            {"id": "element-1"}, {"id": "canvas-1"}, {"id": "creative-1"},
        ]
        client = meta_ads_client.MetaPostingClient(self.config())
        client.create_campaign(build_campaign_payload(name="C", catalog_id="catalog-1"))
        client.create_adset(
            build_adset_payload(
                name="A", campaign_id="campaign-1", product_set_id="set-1",
                pixel_id="pixel-1", targeting=build_targeting(country="AUS"),
            )
        )
        client.upload_page_photo(b"image", filename="image.jpg", content_type="image/jpeg")
        client.create_canvas_element("canvas_photo", {"photo_id": "photo-1"})
        client.create_canvas(name="IA", body_element_ids=("element-1",))
        client.create_collection_creative(
            build_collection_creative_payload(
                name="Creative", page_id="page-1", instagram_user_id="ig-1",
                image_hash="hash", canvas_id="canvas-1", product_set_id="set-1",
                destination_url="https://example.com/product", primary_text="Text", headline="H",
            )
        )
        paths = [call.args[0] for call in post.call_args_list]
        self.assertEqual(
            paths,
            ["act_123/campaigns", "act_123/adsets", "page-1/photos", "page-1/canvas_elements", "page-1/canvases", "act_123/adcreatives"],
        )
        self.assertEqual(post.call_args_list[0].kwargs["data"]["status"], "PAUSED")
        self.assertIn('"advantage_audience": 1', post.call_args_list[1].kwargs["data"]["targeting"])
        self.assertEqual(post.call_args_list[2].kwargs["data"]["published"], "false")

    @mock.patch("meta_ads_client._post", return_value={"id": "ad-1"})
    def test_ad_is_created_paused(self, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(
            client.create_paused_ad(ad_name="Ad", adset_id="adset-1", creative_id="creative-1"),
            "ad-1",
        )
        self.assertEqual(post.call_args.kwargs["data"]["status"], "PAUSED")


class PostingServiceTests(unittest.TestCase):
    def test_complete_sequence_creates_every_object_paused(self):
        client = FakePostingClient()
        store = FakePostingStore()
        result = MetaPostingService(client=client, store=store).create_paused_campaign(request_for())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["meta_status"], "PAUSED")
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["adset_id"], "adset-1")
        self.assertEqual(result["meta_instant_experience_id"], "canvas-1")
        self.assertEqual(result["meta_ad_id"], "ad-1")
        self.assertEqual(
            [call for call in client.calls if not call.startswith("read_")],
            [
                "campaign", "adset", "ad_image", "page_photo", "canvas_photo",
                "canvas_product_set", "canvas_button", "canvas_footer", "canvas",
                "creative", "ad",
            ],
        )
        self.assertEqual(client.campaign_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["promoted_object"]["pixel_id"], "pixel-1")
        self.assertEqual(result["ad_name"], "Max Verstappen Victory IA 2")

    def test_partial_failure_preserves_created_ids(self):
        client = FakePostingClient(fail_at="canvas_product_set")
        store = FakePostingStore()
        with self.assertRaises(PostingError) as caught:
            MetaPostingService(client=client, store=store).create_paused_campaign(request_for())
        result = caught.exception.result
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["adset_id"], "adset-1")
        self.assertEqual(result["meta_page_photo_id"], "photo-1")
        self.assertNotIn("ad", client.calls)

    def test_complete_fingerprint_result_is_returned_without_writes(self):
        existing = {"status": "COMPLETE", "meta_ad_id": "existing-ad"}
        client = FakePostingClient()
        store = FakePostingStore(existing=existing)
        result = MetaPostingService(client=client, store=store).create_paused_campaign(request_for())
        self.assertEqual(result["meta_ad_id"], "existing-ad")
        self.assertNotIn("campaign", client.calls)

    def test_retry_keeps_original_persisted_ia_name(self):
        existing = {
            "status": "FAILED", "campaign_id": "campaign-1", "campaign_name": "Original campaign",
            "adset_id": "adset-1", "adset_name": "Original ad set",
            "ad_name": "Max Verstappen Victory IA 1", "meta_image_hash": "hash",
            "meta_page_photo_id": "photo-1", "meta_canvas_photo_element_id": "photo-element-1",
            "meta_canvas_product_element_id": "product-element-1",
            "meta_canvas_button_element_id": "button-element-1",
            "meta_canvas_footer_element_id": "footer-element-1",
            "meta_instant_experience_id": "canvas-1", "meta_creative_id": "creative-1",
        }
        client = FakePostingClient()
        result = MetaPostingService(client=client, store=FakePostingStore(existing=existing)).create_paused_campaign(
            request_for()
        )
        self.assertEqual(client.last_ad_name, "Max Verstappen Victory IA 1")
        self.assertEqual(result["ad_name"], "Max Verstappen Victory IA 1")

    def test_missing_canonical_url_blocks_before_meta(self):
        client = FakePostingClient()
        with self.assertRaisesRegex(PostingValidationError, "valid https"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for(destination_url="")
            )
        self.assertEqual(client.calls, [])

    def test_success_copy_is_exact(self):
        self.assertEqual(SUCCESS_MESSAGE, "Meta ad created successfully — PAUSED")

    def test_duplicate_pixel_name_blocks_before_writes(self):
        client = FakePostingClient()
        original = client.reference_data

        def references():
            payload = original()
            payload["pixels"] = (
                {"id": "pixel-1", "name": "Sports Cave Pixel 2025"},
                {"id": "pixel-2", "name": "Sports Cave Pixel 2025"},
            )
            return payload

        client.reference_data = references
        with self.assertRaisesRegex(PostingValidationError, "found 2"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(request_for())
        self.assertNotIn("campaign", client.calls)

    def test_page_render_does_not_invoke_write_service(self):
        overview = {"connected": False, "summary": "Meta unavailable", "checks": {}}
        with mock.patch.object(ads_posting_page, "_load_meta_overview", return_value=overview), mock.patch.object(
            ads_posting_page.MetaPostingService, "create_paused_campaign"
        ) as create:
            ads_posting_page.render_page()
        create.assert_not_called()


class ReviewAndPersistenceTests(unittest.TestCase):
    def test_review_aggregates_purchase_funnel(self):
        metrics = ads_meta_review_page.aggregate_ad_metrics(
            [
                {
                    "ad_id": "ad-1", "spend": "50", "impressions": "1000", "reach": "800",
                    "inline_link_clicks": "25",
                    "actions": [
                        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},
                        {"action_type": "offsite_conversion.fb_pixel_add_to_cart", "value": "5"},
                        {"action_type": "offsite_conversion.fb_pixel_initiate_checkout", "value": "3"},
                    ],
                    "action_values": [
                        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "200"},
                    ],
                }
            ]
        )["ad-1"]
        self.assertEqual(metrics["purchases"], 2)
        self.assertEqual(metrics["purchase_value"], 200)
        self.assertEqual(metrics["roas"], 4)
        self.assertEqual(metrics["ctr"], 2.5)
        self.assertEqual(metrics["cpa"], 25)
        self.assertEqual(metrics["cpm"], 50)

    def test_review_page_has_no_write_client(self):
        source = (ROOT / "ads_meta_review_page.py").read_text(encoding="utf-8")
        self.assertNotIn("MetaPostingService", source)
        self.assertNotIn("_post(", source)
        self.assertIn("fetch_meta_ad_insights_summary", source)

    def test_v2_migration_tracks_all_object_ids(self):
        source = (ROOT / "migrations" / "20260901_meta_posting_v2.sql").read_text(encoding="utf-8")
        for field in (
            "meta_page_photo_id", "meta_canvas_product_element_id",
            "meta_instant_experience_id", "CAMPAIGN_CREATED", "ADSET_CREATED",
        ):
            self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main()
