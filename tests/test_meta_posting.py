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
    EXPECTED_PIXEL_NAME,
    SUCCESS_MESSAGE,
    MetaPostingService,
    SupabasePostingStore,
    PostingError,
    PostingCreative,
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
    catalog_ids_from_sales_campaigns,
    dataset_ids_from_purchase_adsets,
    load_posting_reference_snapshot,
    next_instant_experience_ad_name,
    next_instant_experience_ad_names,
    posting_ad_results,
    product_short_name,
    resolve_catalog_reference,
    resolve_dataset_reference,
)


ROOT = Path(__file__).resolve().parents[1]


def image_bytes(colour=(20, 30, 40)):
    output = io.BytesIO()
    Image.new("RGB", (1080, 1350), colour).save(output, format="JPEG")
    return output.getvalue()


def formatted_image_bytes(image_format, colour):
    output = io.BytesIO()
    Image.new("RGB", (720, 900), colour).save(output, format=image_format)
    return output.getvalue()


def request_for(**overrides):
    values = {
        "submission_id": "11111111-1111-4111-8111-111111111111",
        "product_id": "shopify-1",
        "product_title": "Max Verstappen Victory Sports Wall Art",
        "product_handle": "max-verstappen-victory",
        "destination_url": "https://sportscaveshop.com/products/max-verstappen-victory",
        "country": "AUS",
        "sport": "Motorsport",
        "catalog_id": "catalog-1",
        "product_set_id": "set-1",
        "audience_type": "broad",
        "audience_id": "",
        "creatives": tuple(
            PostingCreative(
                image_bytes=image_bytes((20 * index, 30, 40)),
                image_name=f"artwork-{index}.jpg",
                primary_text=f"Primary {index}",
                headline=f"Headline {index}",
                description=f"Description {index}",
            )
            for index in range(1, 4)
        ),
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
    page_access_token = "page-token"
    instagram_actor_id = "ig-1"
    instagram_user_id = "ig-1"

    def __init__(self, *, fail_at=""):
        self.fail_at = fail_at
        self.calls = []
        self.campaign_payload = None
        self.adset_payload = None
        self.creative_payload = None
        self.creative_payloads = []
        self.last_ad_name = ""
        self.ad_creations = []
        self.canvas_names = []
        self.canvas_element_payloads = []
        self.uploaded_images = []

    def permissions(self):
        return ("ads_management",)

    def validate_page_auth(self):
        return {
            "ready": True,
            "page_id": self.page_id,
            "permission": "pages_manage_posts",
        }

    def reference_data(self):
        return {
            "account": {"id": "act_123", "currency": "AUD"},
            "page": {"id": self.page_id, "name": "Sports Cave"},
            "instagram": {"id": self.instagram_user_id, "username": "sportscave"},
            "catalogs": ({"id": "catalog-1", "name": "Shopify Product Catalog"},),
            "pixels": ({"id": "pixel-1", "name": "Shprts Cave Pixel 2025"},),
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
        self.uploaded_images.append((data, filename, content_type))
        return f"image-hash-{len(self.uploaded_images)}"

    def upload_page_photo(self, data, *, filename, content_type):
        self.calls.append("page_photo")
        return f"photo-{self.calls.count('page_photo')}"

    def create_canvas_element(self, element_type, specification):
        self.calls.append(element_type)
        if self.fail_at == element_type:
            raise meta_ads_client.MetaAdsApiError("element failed")
        self.canvas_element_payloads.append((element_type, dict(specification)))
        return f"{element_type}-element-{self.calls.count(element_type)}"

    def create_canvas(self, *, name, body_element_ids):
        self.calls.append("canvas")
        self.canvas_names.append(name)
        return f"canvas-{len(self.canvas_names)}"

    def find_canvases_by_name(self, name):
        return ()

    def create_collection_creative(self, payload):
        self.calls.append("creative")
        self.creative_payload = payload
        self.creative_payloads.append(payload)
        return f"creative-{len(self.creative_payloads)}"

    def find_creative_by_name(self, name):
        return None

    def create_paused_ad(self, *, ad_name, adset_id, creative_id):
        self.calls.append("ad")
        if self.fail_at == f"ad_{len(self.ad_creations) + 1}":
            raise meta_ads_client.MetaAdsApiError("ad failed")
        self.last_ad_name = ad_name
        self.ad_creations.append((ad_name, adset_id, creative_id))
        return f"ad-{len(self.ad_creations)}"

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

    def test_posting_v3_ui_keeps_shared_setup_and_three_compact_creatives(self):
        source = (ROOT / "ads_posting_page.py").read_text(encoding="utf-8")
        self.assertIn('"Meta connected · ready"', source)
        self.assertIn('"Create 3 Paused Meta Ads"', source)
        self.assertIn('st.subheader("Creatives")', source)
        self.assertIn("for index in range(1, 4)", source)
        self.assertIn("one paused campaign, one paused ad set and three paused", source)


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

    def test_valid_handle_supplies_current_canonical_url_without_live_shopify(self):
        row = {
            "shopify_product_id": "1",
            "product_title": "Mean Joe Greene & Jack Lambert NFL Wall Art",
            "product_handle": "mean-joe-greene-jack-lambert-wall-art",
            "online_store_url": "https://sportscave.com.au/products/obsolete",
        }
        self.assertEqual(
            ads_page.canonical_shopify_product_url_from_row(row),
            "https://www.sportscaveshop.com/products/mean-joe-greene-jack-lambert-wall-art",
        )
        self.assertIn(
            "canonical_shopify_product_url_from_row",
            (ROOT / "ads_page.py").read_text(encoding="utf-8").split(
                "def _edition_ops_product_page_url_from_row", 1
            )[1].split("def _positive_int_or_none", 1)[0],
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
        story = payload["object_story_spec"]
        self.assertNotIn("link_data", story)
        template = story["template_data"]
        self.assertNotIn("canvas_id", template)
        self.assertEqual(template["format_option"], "collection_video")
        self.assertEqual(template["link"], "https://fb.com/canvas_doc/canvas-1")
        self.assertEqual(template["image_hash"], "hash")
        self.assertNotIn("video_id", template)
        self.assertEqual(template["message"], "Text")
        self.assertEqual(template["name"], "Headline")
        self.assertEqual(template["call_to_action"], {"type": "SHOP_NOW"})
        self.assertNotIn("retailer_item_ids", template)
        self.assertEqual(payload["product_set_id"], "set-1")
        self.assertEqual(payload["object_story_spec"]["page_id"], "page-1")
        self.assertEqual(payload["object_story_spec"]["instagram_user_id"], "ig-1")
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
            "page_access_token": "page-secret", "api_version": "v26.0",
            "page_id": "page-1", "instagram_user_id": "ig-1",
        }

    @mock.patch("meta_ads_client.requests.post")
    def test_common_post_defaults_to_ad_token_and_accepts_explicit_page_override(self, post):
        response = mock.Mock(ok=True, status_code=200)
        response.json.return_value = {"id": "created"}
        post.return_value = response
        config = self.config()

        meta_ads_client._post("act_123/campaigns", data={"name": "Campaign"}, config=config)
        self.assertEqual(post.call_args.kwargs["data"]["access_token"], "secret")

        meta_ads_client._post(
            "page-1/photos",
            data={"published": "false"},
            config=config,
            access_token="page-secret",
        )
        self.assertEqual(post.call_args.kwargs["data"]["access_token"], "page-secret")

    @mock.patch("meta_ads_client.requests.post")
    def test_page_token_is_redacted_from_meta_errors(self, post):
        page_token = "EAA-page-secret-that-must-never-leak"
        response = mock.Mock(ok=False, status_code=403)
        response.json.return_value = {
            "error": {
                "message": f"Rejected access_token={page_token}",
                "code": 100,
                "error_subcode": 1443050,
                "error_user_title": "Using unsupported field in object_story_spec",
                "error_user_msg": f"canvas_id is invalid; access_token={page_token}",
                "fbtrace_id": "safe-trace-id",
            }
        }
        post.return_value = response
        with self.assertRaises(meta_ads_client.MetaAdsApiError) as caught:
            meta_ads_client._post(
                "page-1/photos",
                config=self.config(),
                access_token=page_token,
            )
        self.assertNotIn(page_token, str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))
        self.assertEqual(caught.exception.error_code, 100)
        self.assertEqual(caught.exception.error_subcode, 1443050)
        self.assertEqual(
            caught.exception.error_user_title,
            "Using unsupported field in object_story_spec",
        )
        self.assertNotIn(page_token, caught.exception.error_user_msg)
        self.assertIn("[redacted]", caught.exception.error_user_msg)
        self.assertEqual(caught.exception.fbtrace_id, "safe-trace-id")

    @mock.patch("meta_ads_client.requests.post")
    def test_product_set_without_collection_template_has_safe_actionable_guidance(self, post):
        response = mock.Mock(ok=False, status_code=400)
        response.json.return_value = {
            "error": {
                "message": "Invalid parameter",
                "code": 100,
                "error_subcode": 1990065,
                "error_user_title": "Cannot use product set ID without template spec",
                "error_user_msg": "Use a carousel or collection ad.",
                "fbtrace_id": "safe-product-set-trace",
            }
        }
        post.return_value = response

        with self.assertRaises(meta_ads_client.MetaAdsApiError) as caught:
            meta_ads_client._post(
                "act_123/adcreatives",
                data={"name": "Collection creative"},
                config=self.config(),
            )

        message = str(caught.exception)
        self.assertIn("code 100", message)
        self.assertIn("subcode 1990065", message)
        self.assertIn("object_story_spec.template_data", message)
        self.assertIn("catalogue Collection creative", message)
        self.assertEqual(caught.exception.fbtrace_id, "safe-product-set-trace")

    @mock.patch("meta_ads_client.fetch_meta_permissions", return_value=("ads_management",))
    @mock.patch("meta_ads_client.fetch_meta_campaigns", return_value={"rows": ()})
    @mock.patch("meta_ads_client.fetch_meta_account", return_value={"id": "act_123"})
    @mock.patch("meta_ads_client.fetch_meta_token_identity", return_value={"id": "system-user"})
    def test_missing_page_token_is_a_distinct_non_destructive_readiness_failure(
        self, _identity, _account, _campaigns, _permissions
    ):
        overview = meta_ads_client.diagnose_meta_posting_connection(
            {
                "configured": True,
                "ad_account_id": "act_123",
                "access_token": "ad-secret",
                "api_version": "v26.0",
                "api_version_source": "provided config",
                "page_id": "page-1",
                "page_access_token": "",
                "instagram_user_id": "ig-1",
            }
        )
        self.assertTrue(overview["connected"])
        self.assertFalse(overview["posting_ready"])
        self.assertEqual(overview["diagnosis_category"], "missing_page_token")
        self.assertEqual(overview["checks"]["page_auth"]["status"], "failed")

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
        self.assertNotIn("access_token", post.call_args_list[0].kwargs)
        self.assertNotIn("access_token", post.call_args_list[1].kwargs)
        for call in post.call_args_list[2:5]:
            self.assertEqual(call.kwargs["access_token"], "page-secret")
        self.assertNotIn("access_token", post.call_args_list[5].kwargs)

    @mock.patch("meta_ads_client.fetch_meta_page_token_debug")
    @mock.patch("meta_ads_client.fetch_meta_page_token_identity")
    def test_page_auth_rejects_wrong_page_and_missing_publishing_task(self, identity, debug):
        config = {
            **self.config(),
            "app_id": "app-1",
            "app_secret": "app-secret",
        }
        identity.return_value = {"id": "other-page", "name": "Other"}
        with self.assertRaisesRegex(meta_ads_client.MetaPageAuthError, "different Facebook Page"):
            meta_ads_client.MetaPostingClient(config).validate_page_auth()
        debug.assert_not_called()

        identity.return_value = {"id": "page-1", "name": "Sports Cave"}
        debug.return_value = {
            "is_valid": True,
            "app_id": "app-1",
            "type": "PAGE",
            "scopes": ("pages_read_engagement",),
        }
        with self.assertRaisesRegex(meta_ads_client.MetaPageAuthError, "pages_manage_posts"):
            meta_ads_client.MetaPostingClient(config).validate_page_auth()

    @mock.patch("meta_ads_client.fetch_meta_page_token_debug")
    @mock.patch("meta_ads_client.fetch_meta_page_token_identity")
    def test_page_auth_rejects_page_without_expected_task_assignment(self, identity, debug):
        config = {
            **self.config(),
            "app_id": "app-1",
            "app_secret": "app-secret",
        }
        identity.return_value = {"id": "page-1", "name": "Sports Cave"}
        debug.return_value = {
            "is_valid": True,
            "app_id": "app-1",
            "type": "PAGE",
            "scopes": ("pages_manage_posts",),
            "granular_scopes": (
                {"scope": "pages_manage_posts", "target_ids": ("other-page",)},
            ),
        }
        with self.assertRaisesRegex(meta_ads_client.MetaPageAuthError, "required content task"):
            meta_ads_client.MetaPostingClient(config).validate_page_auth()

    @mock.patch("meta_ads_client.fetch_meta_page_token_identity")
    def test_page_auth_classifies_invalid_token_without_leaking_it(self, identity):
        page_token = "EAA-invalid-page-token-never-display"
        identity.side_effect = meta_ads_client.MetaAdsApiError(
            f"Invalid OAuth access token {page_token}",
            error_code=190,
        )
        with self.assertRaises(meta_ads_client.MetaPageAuthError) as caught:
            meta_ads_client.MetaPostingClient(
                {**self.config(), "page_access_token": page_token}
            ).validate_page_auth()
        self.assertEqual(caught.exception.category, "invalid_page_token")
        self.assertNotIn(page_token, str(caught.exception))

    @mock.patch("meta_ads_client.fetch_meta_page_token_debug")
    @mock.patch("meta_ads_client.fetch_meta_page_token_identity")
    def test_page_auth_confirms_expected_page_permission_and_assignment(self, identity, debug):
        config = {
            **self.config(),
            "app_id": "app-1",
            "app_secret": "app-secret",
        }
        identity.return_value = {"id": "page-1", "name": "Sports Cave"}
        debug.return_value = {
            "is_valid": True,
            "app_id": "app-1",
            "type": "PAGE",
            "scopes": ("pages_manage_posts",),
            "granular_scopes": (
                {"scope": "pages_manage_posts", "target_ids": ("page-1",)},
            ),
        }
        readiness = meta_ads_client.MetaPostingClient(config).validate_page_auth()
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["page_id"], "page-1")
        self.assertNotIn("page-secret", str(readiness))

    @mock.patch("meta_ads_client._post", return_value={"id": "ad-1"})
    def test_ad_is_created_paused(self, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(
            client.create_paused_ad(ad_name="Ad", adset_id="adset-1", creative_id="creative-1"),
            "ad-1",
        )
        self.assertEqual(post.call_args.kwargs["data"]["status"], "PAUSED")

    @mock.patch("meta_ads_client._paged_get")
    def test_dataset_and_reference_fallbacks_use_current_read_edges(self, paged_get):
        paged_get.return_value = {"rows": ()}
        client = meta_ads_client.MetaPostingClient(self.config())
        client.pixels()
        client.reference_campaigns()
        client.reference_adsets()
        self.assertEqual(
            [call.args[0] for call in paged_get.call_args_list],
            ["act_123/adspixels", "act_123/campaigns", "act_123/adsets"],
        )
        self.assertIn("campaign{objective}", paged_get.call_args_list[2].kwargs["params"]["fields"])


class PostingReferenceRepairTests(unittest.TestCase):
    @staticmethod
    def references(**overrides):
        payload = {
            "account": {"id": "act_123", "currency": "AUD"},
            "page": {"id": "page-1", "name": "Sports Cave"},
            "instagram": {"id": "ig-1", "username": "sportscave"},
            "catalogs": ({"id": "catalog-1", "name": "Shopify Product Catalog"},),
            "pixels": ({"id": "dataset-1", "name": EXPECTED_PIXEL_NAME},),
            "saved_audiences": (),
            "custom_audiences": (),
        }
        payload.update(overrides)
        return payload

    def test_ordinary_form_reruns_reuse_reference_snapshot(self):
        state = {}
        calls = []

        def loader():
            calls.append("discover")
            return {"catalog_resolution": {"resolved": True, "id": "catalog-1"}}

        ads_posting_page._session_cached_load(state, "references", "error", loader)
        for key, value in (
            (ads_posting_page.PRODUCT_KEY, "product-2"),
            (ads_posting_page.COUNTRY_KEY, "USA"),
            (ads_posting_page.SPORT_KEY, "NFL"),
            (ads_posting_page.IMAGE_KEYS[0], "image-1"),
            (ads_posting_page.IMAGE_KEYS[1], "image-2"),
            (ads_posting_page.IMAGE_KEYS[2], "image-3"),
            (ads_posting_page.PRIMARY_TEXT_KEYS[0], "Updated copy 1"),
            (ads_posting_page.PRIMARY_TEXT_KEYS[1], "Updated copy 2"),
            (ads_posting_page.PRIMARY_TEXT_KEYS[2], "Updated copy 3"),
            (ads_posting_page.HEADLINE_KEYS[0], "Headline 1"),
            (ads_posting_page.DESCRIPTION_KEYS[2], "Description 3"),
        ):
            state[key] = value
            ads_posting_page._session_cached_load(state, "references", "error", loader)
        self.assertEqual(calls, ["discover"])

    def test_explicit_refresh_forces_reference_refetch(self):
        state = {}
        calls = []

        def loader():
            calls.append("discover")
            return {"sequence": len(calls)}

        first, _ = ads_posting_page._session_cached_load(state, "references", "error", loader)
        cached, _ = ads_posting_page._session_cached_load(state, "references", "error", loader)
        refreshed, _ = ads_posting_page._session_cached_load(
            state, "references", "error", loader, force=True
        )
        self.assertEqual((first["sequence"], cached["sequence"], refreshed["sequence"]), (1, 1, 2))
        self.assertEqual(calls, ["discover", "discover"])

    def test_catalog_resolution_is_deterministic_and_not_name_only(self):
        configured = resolve_catalog_reference(
            self.references(catalogs=()), environ={"META_CATALOG_ID": "catalog-configured"}
        )
        self.assertEqual((configured["id"], configured["source"]), ("catalog-configured", "configured_id"))
        configured_over_selected = resolve_catalog_reference(
            self.references(
                catalogs=(
                    {"id": "catalog-configured", "name": "Shopify Product Catalog"},
                    {"id": "catalog-selected", "name": "Shopify Product Catalog"},
                )
            ),
            expected_id="catalog-selected",
            environ={"META_CATALOG_ID": "catalog-configured"},
        )
        self.assertEqual(configured_over_selected["id"], "catalog-configured")
        sole = resolve_catalog_reference(
            self.references(catalogs=({"id": "catalog-sole", "name": "Sports Cave Store"},)),
            environ={},
        )
        self.assertEqual((sole["id"], sole["source"]), ("catalog-sole", "only_accessible_catalog"))

    def test_catalog_fallback_uses_only_consistent_sales_campaign_evidence(self):
        ids = catalog_ids_from_sales_campaigns(
            (
                {"objective": "OUTCOME_SALES", "promoted_object": {"product_catalog_id": "catalog-1"}},
                {"objective": "AWARENESS", "promoted_object": {"product_catalog_id": "ignore"}},
            )
        )
        resolved = resolve_catalog_reference(
            self.references(catalogs=(), catalog_fallback_ids=ids), environ={}
        )
        self.assertEqual((resolved["id"], resolved["source"]), ("catalog-1", "existing_sales_campaign"))
        conflict = resolve_catalog_reference(
            self.references(catalogs=(), catalog_fallback_ids=("catalog-1", "catalog-2")),
            environ={},
        )
        self.assertFalse(conflict["resolved"])

    def test_direct_unique_catalog_wins_over_historical_campaign_ids(self):
        resolved = resolve_catalog_reference(
            self.references(
                catalogs=({"id": "catalog-current", "name": "Shopify Product Catalog"},),
                catalog_fallback_ids=("catalog-old-1", "catalog-old-2"),
                catalog_campaign_evidence=(
                    {
                        "objective": "OUTCOME_SALES",
                        "promoted_object": {"product_catalog_id": "catalog-old-1"},
                    },
                ),
            ),
            environ={},
        )
        self.assertEqual((resolved["id"], resolved["source"]), ("catalog-current", "exact_name"))

    def test_duplicate_named_catalogs_use_unique_current_campaign_evidence(self):
        references = self.references(
            catalogs=(
                {"id": "catalog-old", "name": "Shopify Product Catalog"},
                {"id": "catalog-current", "name": "Shopify Product Catalog"},
            ),
            catalog_campaign_evidence=(
                {
                    "objective": "OUTCOME_SALES", "status": "PAUSED",
                    "created_time": "2025-02-07T00:00:00+0000",
                    "promoted_object": {"product_catalog_id": "catalog-old"},
                },
                {
                    "objective": "OUTCOME_SALES", "status": "ACTIVE",
                    "created_time": "2026-09-01T00:00:00+0000",
                    "promoted_object": {"product_catalog_id": "catalog-current"},
                },
            ),
        )
        resolved = resolve_catalog_reference(references, environ={})
        self.assertEqual(resolved["id"], "catalog-current")
        self.assertEqual(resolved["source"], "exact_name_current_sales_campaign")

    def test_multiple_genuinely_current_catalogs_block_instead_of_guessing(self):
        references = self.references(
            catalogs=(
                {"id": "catalog-a", "name": "Shopify Product Catalog"},
                {"id": "catalog-b", "name": "Shopify Product Catalog"},
            ),
            catalog_campaign_evidence=tuple(
                {
                    "objective": "OUTCOME_SALES", "status": "ACTIVE",
                    "promoted_object": {"product_catalog_id": catalog_id},
                }
                for catalog_id in ("catalog-a", "catalog-b")
            ),
        )
        resolved = resolve_catalog_reference(references, environ={})
        self.assertFalse(resolved["resolved"])
        self.assertIn("currently used", resolved["error"])

    def test_catalog_permission_error_is_reported_separately_from_ambiguity(self):
        client = meta_ads_client.MetaPostingClient(
            {
                "configured": True, "ad_account_id": "act_123", "access_token": "secret",
                "api_version": "v26.0", "page_id": "page-1", "instagram_user_id": "ig-1",
            }
        )
        client.account = mock.Mock(return_value={"business": {"id": "business-1"}})
        client.pixels = mock.Mock(return_value=())
        client.saved_audiences = mock.Mock(return_value=())
        client.custom_audiences = mock.Mock(return_value=())
        client.page = mock.Mock(return_value={"id": "page-1"})
        client.instagram_account = mock.Mock(return_value={"id": "ig-1"})
        error = meta_ads_client.MetaAdsApiError(
            "Permission denied", error_code=200, error_type="OAuthException",
            request_path="business-1/owned_product_catalogs",
        )
        with mock.patch("meta_ads_client._paged_get", side_effect=error):
            references = client.reference_data()
        self.assertEqual(references["catalog_error"]["error_code"], 200)
        self.assertEqual(
            references["catalog_error"]["endpoint"],
            "business-1/owned_product_catalogs",
        )
        self.assertNotIn("multiple", references["catalog_error"]["message"].casefold())

    def test_dataset_resolution_uses_exact_intentional_name_or_configured_id(self):
        self.assertEqual(EXPECTED_PIXEL_NAME, "Shprts Cave Pixel 2025")
        configured = resolve_dataset_reference(
            self.references(pixels=()), environ={"META_DATASET_ID": "dataset-configured"}
        )
        self.assertEqual((configured["id"], configured["name"]), ("dataset-configured", EXPECTED_PIXEL_NAME))
        exact = resolve_dataset_reference(self.references(), environ={})
        self.assertEqual((exact["id"], exact["source"]), ("dataset-1", "exact_name"))
        wrong_name = resolve_dataset_reference(
            self.references(pixels=({"id": "wrong", "name": "Sports Cave Pixel 2025"},)),
            environ={},
        )
        self.assertFalse(wrong_name["resolved"])

    def test_dataset_fallback_requires_one_sales_purchase_dataset(self):
        base = {
            "campaign": {"objective": "OUTCOME_SALES"},
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "promoted_object": {"custom_event_type": "PURCHASE", "pixel_id": "dataset-1"},
        }
        self.assertEqual(dataset_ids_from_purchase_adsets((base,)), ("dataset-1",))
        resolved = resolve_dataset_reference(
            self.references(pixels=(), dataset_fallback_ids=("dataset-1",)), environ={}
        )
        self.assertEqual((resolved["id"], resolved["source"]), ("dataset-1", "existing_purchase_adsets"))
        conflicting = dict(base)
        conflicting["promoted_object"] = {
            "custom_event_type": "PURCHASE", "dataset_id": "dataset-2"
        }
        conflict_ids = dataset_ids_from_purchase_adsets((base, conflicting))
        conflict = resolve_dataset_reference(
            self.references(pixels=(), dataset_fallback_ids=conflict_ids), environ={}
        )
        self.assertFalse(conflict["resolved"])
        self.assertIn("multiple", conflict["error"].casefold())

    def test_snapshot_loads_product_sets_and_ad_names_once_then_session_reuses_it(self):
        class ReadClient:
            def __init__(self):
                self.calls = []

            def reference_data(inner_self):
                inner_self.calls.append("reference_data")
                return PostingReferenceRepairTests.references()

            def product_sets(inner_self, catalog_id):
                inner_self.calls.append(f"product_sets:{catalog_id}")
                return ({"id": "set-1", "name": "NFL", "product_catalog": {"id": catalog_id}},)

            def existing_ad_names(inner_self):
                inner_self.calls.append("existing_ad_names")
                return ("Product IA 1",)

        client = ReadClient()
        state = {}
        loader = lambda: load_posting_reference_snapshot(client, environ={})
        first, _ = ads_posting_page._session_cached_load(state, "references", "error", loader)
        second, _ = ads_posting_page._session_cached_load(state, "references", "error", loader)
        self.assertEqual(first, second)
        self.assertEqual(
            client.calls,
            ["reference_data", "product_sets:catalog-1", "existing_ad_names"],
        )
        self.assertEqual(first["product_sets"][0]["id"], "set-1")

    def test_snapshot_loads_product_sets_from_current_duplicate_named_catalog(self):
        class DuplicateCatalogClient:
            def __init__(inner_self):
                inner_self.product_set_catalog_ids = []

            def reference_data(inner_self):
                return PostingReferenceRepairTests.references(
                    catalogs=(
                        {"id": "catalog-old", "name": "Shopify Product Catalog"},
                        {"id": "catalog-current", "name": "Shopify Product Catalog"},
                    )
                )

            def reference_campaigns(inner_self):
                return (
                    {
                        "objective": "OUTCOME_SALES", "status": "PAUSED",
                        "created_time": "2025-02-07T00:00:00+0000",
                        "promoted_object": {"product_catalog_id": "catalog-old"},
                    },
                    {
                        "objective": "OUTCOME_SALES", "status": "ACTIVE",
                        "created_time": "2026-09-01T00:00:00+0000",
                        "promoted_object": {"product_catalog_id": "catalog-current"},
                    },
                )

            def product_sets(inner_self, catalog_id):
                inner_self.product_set_catalog_ids.append(catalog_id)
                return ({"id": "set-current", "product_catalog": {"id": catalog_id}},)

            def existing_ad_names(inner_self):
                return ()

        client = DuplicateCatalogClient()
        snapshot = load_posting_reference_snapshot(client, environ={})
        self.assertEqual(snapshot["catalog_resolution"]["id"], "catalog-current")
        self.assertEqual(client.product_set_catalog_ids, ["catalog-current"])
        self.assertEqual(snapshot["product_sets"][0]["id"], "set-current")

    def test_snapshot_uses_mocked_sales_asset_fallbacks_when_direct_lists_are_empty(self):
        class FallbackClient:
            def reference_data(inner_self):
                return PostingReferenceRepairTests.references(catalogs=(), pixels=())

            def reference_campaigns(inner_self):
                return (
                    {
                        "objective": "OUTCOME_SALES",
                        "promoted_object": {"product_catalog_id": "catalog-fallback"},
                    },
                )

            def reference_adsets(inner_self):
                return (
                    {
                        "campaign": {"objective": "OUTCOME_SALES"},
                        "promoted_object": {
                            "custom_event_type": "PURCHASE",
                            "pixel_id": "dataset-fallback",
                        },
                    },
                )

            def product_sets(inner_self, catalog_id):
                return ({"id": "set-1", "product_catalog": {"id": catalog_id}},)

            def existing_ad_names(inner_self):
                return ()

        snapshot = load_posting_reference_snapshot(FallbackClient(), environ={})
        self.assertEqual(snapshot["catalog_resolution"]["id"], "catalog-fallback")
        self.assertEqual(snapshot["dataset_resolution"]["id"], "dataset-fallback")
        self.assertEqual(snapshot["product_sets"][0]["product_catalog"]["id"], "catalog-fallback")

    @mock.patch("meta_ads_client._post")
    def test_reference_refresh_is_read_only_and_never_calls_meta_write_edge(self, post):
        client = meta_ads_client.MetaPostingClient(
            {
                "configured": True,
                "ad_account_id": "act_123",
                "access_token": "secret",
                "api_version": "v26.0",
                "page_id": "page-1",
                "instagram_user_id": "ig-1",
            }
        )
        client.reference_data = mock.Mock(return_value=self.references())
        client.product_sets = mock.Mock(return_value=({"id": "set-1", "name": "NFL"},))
        client.existing_ad_names = mock.Mock(return_value=())
        snapshot = load_posting_reference_snapshot(client, environ={})
        self.assertTrue(snapshot["catalog_resolution"]["resolved"])
        post.assert_not_called()

    def test_audience_failure_keeps_broad_default_available(self):
        self.assertEqual(
            ads_posting_page._audience_options({}),
            ({"key": "broad", "type": "broad", "label_type": "Broad", "id": "", "name": "Broad"},),
        )

    def test_product_switch_updates_nfl_and_url_in_same_resolution(self):
        row = {
            "shopify_product_id": "nfl-1",
            "product_title": "Legends Never Die: Mean Joe Greene & Jack Lambert NFL Wall Art",
            "product_handle": "mean-joe-greene-jack-lambert",
            "collections": ("NFL",),
        }
        selection = {
            "selected_label": row["product_title"],
            "selector_identity": "id::nfl-1",
            "row": row,
        }
        self.assertEqual(ads_posting_page._infer_sport(selection), "NFL")
        self.assertEqual(
            ads_page.canonical_shopify_product_url_from_row(row),
            "https://www.sportscaveshop.com/products/mean-joe-greene-jack-lambert",
        )

    def test_create_readiness_only_blocks_real_required_dependencies(self):
        complete = {
            "product_title": "Product",
            "product_url": "https://www.sportscaveshop.com/products/product",
            "creatives": tuple(
                {
                    "image": {"data": b"image"}, "image_error": "",
                    "primary_text": f"Primary {index}", "headline": f"Headline {index}",
                }
                for index in range(1, 4)
            ),
            "country": "AUS",
            "sport": "NFL",
            "catalog_id": "catalog-1",
            "product_set_id": "set-1",
            "dataset_id": "dataset-1",
            "identities_ready": True,
        }
        self.assertTrue(ads_posting_page._posting_form_ready(**complete))
        for required in ("product_url", "catalog_id", "product_set_id", "dataset_id"):
            missing = dict(complete)
            missing[required] = ""
            self.assertFalse(ads_posting_page._posting_form_ready(**missing), required)


class PostingServiceTests(unittest.TestCase):
    def test_missing_page_token_blocks_before_campaign_creation(self):
        client = FakePostingClient()
        client.page_access_token = ""
        with self.assertRaisesRegex(PostingValidationError, "META_PAGE_ACCESS_TOKEN"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for()
            )
        self.assertNotIn("campaign", client.calls)
        self.assertNotIn("adset", client.calls)

    def test_invalid_page_auth_blocks_before_campaign_creation(self):
        client = FakePostingClient()
        client.validate_page_auth = mock.Mock(
            side_effect=meta_ads_client.MetaPageAuthError(
                "The Facebook Page token lacks pages_manage_posts for Page-owned content.",
                category="page_permission_missing",
            )
        )
        with self.assertRaisesRegex(PostingValidationError, "pages_manage_posts"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for()
            )
        self.assertNotIn("campaign", client.calls)
        self.assertNotIn("adset", client.calls)

    def test_complete_sequence_creates_every_object_paused(self):
        client = FakePostingClient()
        store = FakePostingStore()
        result = MetaPostingService(client=client, store=store).create_paused_campaign(request_for())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["meta_status"], "PAUSED")
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["adset_id"], "adset-1")
        self.assertEqual(
            [row["meta_instant_experience_id"] for row in result["ad_results"]],
            ["canvas-1", "canvas-2", "canvas-3"],
        )
        self.assertEqual(
            [row["meta_ad_id"] for row in result["ad_results"]],
            ["ad-1", "ad-2", "ad-3"],
        )
        self.assertEqual(
            [call for call in client.calls if not call.startswith("read_")],
            ["campaign", "adset"] + [
                "campaign", "adset", "ad_image", "page_photo", "canvas_photo",
                "canvas_product_set", "canvas_button", "canvas_footer", "canvas",
                "creative", "ad",
            ][2:] * 3,
        )
        self.assertEqual(client.campaign_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["promoted_object"]["pixel_id"], "pixel-1")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls.count("ad"), 3)
        self.assertEqual(client.calls.count("canvas"), 3)
        self.assertEqual(len(client.uploaded_images), 3)
        self.assertEqual(
            [data for data, _filename, _content_type in client.uploaded_images],
            [creative.image_bytes for creative in request_for().creatives],
        )
        self.assertEqual(
            [payload["object_story_spec"]["template_data"]["message"] for payload in client.creative_payloads],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [payload["object_story_spec"]["template_data"]["name"] for payload in client.creative_payloads],
            ["Headline 1", "Headline 2", "Headline 3"],
        )
        self.assertEqual(
            [payload["object_story_spec"]["template_data"]["description"] for payload in client.creative_payloads],
            ["Description 1", "Description 2", "Description 3"],
        )
        self.assertEqual(
            [payload["object_story_spec"]["template_data"]["image_hash"] for payload in client.creative_payloads],
            ["image-hash-1", "image-hash-2", "image-hash-3"],
        )
        photo_specs = [
            specification
            for element_type, specification in client.canvas_element_payloads
            if element_type == "canvas_photo"
        ]
        self.assertEqual(
            [specification["photo_id"] for specification in photo_specs],
            ["photo-1", "photo-2", "photo-3"],
        )
        product_specs = [
            specification
            for element_type, specification in client.canvas_element_payloads
            if element_type == "canvas_product_set"
        ]
        self.assertTrue(
            all(specification["item_description"] == "Limited Edition" for specification in product_specs)
        )
        for payload in client.creative_payloads:
            story = payload["object_story_spec"]
            self.assertNotIn("link_data", story)
            template_data = story["template_data"]
            self.assertEqual(template_data["format_option"], "collection_video")
            self.assertEqual(template_data["call_to_action"]["type"], "SHOP_NOW")
            self.assertEqual(
                payload["degrees_of_freedom_spec"]["creative_features_spec"]
                ["image_background_gen"]["enroll_status"],
                "OPT_OUT",
            )
            self.assertIn("utm_source=facebook", payload["url_tags"])
        self.assertTrue(all(adset_id == "adset-1" for _name, adset_id, _creative in client.ad_creations))
        self.assertEqual(
            [row["ad_name"] for row in result["ad_results"]],
            [
                "Max Verstappen Victory IA 2",
                "Max Verstappen Victory IA 3",
                "Max Verstappen Victory IA 4",
            ],
        )

    def test_mixed_source_formats_stay_mapped_to_their_own_meta_upload(self):
        source_rows = (
            (formatted_image_bytes("JPEG", (190, 20, 30)), "ad-1.jpg"),
            (formatted_image_bytes("PNG", (20, 190, 30)), "ad-2.png"),
            (formatted_image_bytes("WEBP", (20, 30, 190)), "ad-3.webp"),
        )
        request = request_for(
            creatives=tuple(
                PostingCreative(
                    image_bytes=data,
                    image_name=name,
                    primary_text=f"Primary {index}",
                    headline=f"Headline {index}",
                    description=f"Description {index}",
                )
                for index, (data, name) in enumerate(source_rows, start=1)
            )
        )
        client = FakePostingClient()
        MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(request)

        self.assertEqual(client.uploaded_images[0][0], source_rows[0][0])
        self.assertEqual(client.uploaded_images[1][0], source_rows[1][0])
        self.assertEqual(
            [(name, content_type) for _data, name, content_type in client.uploaded_images],
            [
                ("ad-1.jpg", "image/jpeg"),
                ("ad-2.png", "image/png"),
                ("ad-3.png", "image/png"),
            ],
        )
        with Image.open(io.BytesIO(client.uploaded_images[2][0])) as converted_webp:
            converted_webp.load()
            self.assertEqual(converted_webp.format, "PNG")
            self.assertEqual(converted_webp.size, (720, 900))
            red, green, blue = converted_webp.getpixel((100, 100))
            self.assertLess(red, 50)
            self.assertLess(green, 60)
            self.assertGreater(blue, 150)

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

    def test_ad_three_failure_retries_without_recreating_ads_one_and_two(self):
        client = FakePostingClient(fail_at="ad_3")
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        with self.assertRaises(PostingError) as caught:
            service.create_paused_campaign(request_for())
        partial = posting_ad_results(caught.exception.result["ad_results"])
        self.assertEqual([row["meta_ad_id"] for row in partial[:2]], ["ad-1", "ad-2"])
        self.assertEqual(partial[2]["status"], "FAILED")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)

        calls_before_retry = list(client.calls)
        client.fail_at = ""
        completed = service.create_paused_campaign(request_for())
        self.assertEqual(completed["status"], "COMPLETE")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls[len(calls_before_retry):].count("ad"), 1)
        self.assertEqual(client.calls[len(calls_before_retry):].count("canvas"), 0)
        self.assertEqual(
            [row["meta_ad_id"] for row in completed["ad_results"]],
            ["ad-1", "ad-2", "ad-3"],
        )

    def test_new_submission_id_resumes_unique_partial_campaign_and_adset(self):
        original_submission_id = "22222222-2222-4222-8222-222222222222"
        existing = {
            "submission_id": original_submission_id,
            "status": "FAILED",
            "campaign_id": "120249720387120554",
            "campaign_name": "Original campaign",
            "adset_id": "120249720389890554",
            "adset_name": "Original ad set",
            "ad_name": "Max Verstappen Victory IA 1",
            "ad_results": posting_ad_results(
                (),
                ad_names=(
                    "Max Verstappen Victory IA 1",
                    "Max Verstappen Victory IA 2",
                    "Max Verstappen Victory IA 3",
                ),
            ),
        }
        client = FakePostingClient()
        store = FakePostingStore(existing=existing)
        result = MetaPostingService(client=client, store=store).create_paused_campaign(
            request_for(submission_id="33333333-3333-4333-8333-333333333333")
        )
        self.assertEqual(result["submission_id"], original_submission_id)
        self.assertEqual(result["campaign_id"], "120249720387120554")
        self.assertEqual(result["adset_id"], "120249720389890554")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("ad"), 3)

    def test_retry_reuses_peter_brock_campaign_adset_and_first_instant_experience(self):
        original_submission_id = "22222222-2222-4222-8222-222222222222"
        ad_results = posting_ad_results(
            (),
            ad_names=(
                "Six Laps Ahead Peter Brock IA 1",
                "Six Laps Ahead Peter Brock IA 2",
                "Six Laps Ahead Peter Brock IA 3",
            ),
        )
        ad_results[0].update(
            {
                "meta_image_hash": "existing-image-hash",
                "meta_page_photo_id": "existing-page-photo",
                "meta_canvas_photo_element_id": "existing-photo-element",
                "meta_canvas_product_element_id": "existing-product-element",
                "meta_canvas_button_element_id": "existing-button-element",
                "meta_canvas_footer_element_id": "existing-footer-element",
                "meta_instant_experience_id": "1390026833255926",
                "status": "FAILED",
            }
        )
        existing = {
            "submission_id": original_submission_id,
            "status": "FAILED",
            "campaign_id": "120249720387120554",
            "campaign_name": "020926 AUS Motorsport Six Laps Ahead Peter Brock",
            "adset_id": "120249720389890554",
            "adset_name": "AUS Motorsport Broad",
            "ad_name": "Six Laps Ahead Peter Brock IA 1",
            "ad_results": ad_results,
        }
        client = FakePostingClient()
        result = MetaPostingService(
            client=client,
            store=FakePostingStore(existing=existing),
        ).create_paused_campaign(
            request_for(
                submission_id="33333333-3333-4333-8333-333333333333",
                product_title="Six Laps Ahead Peter Brock Wall Art",
                product_handle="six-laps-ahead-peter-brock-wall-art",
                destination_url=(
                    "https://sportscaveshop.com/products/"
                    "six-laps-ahead-peter-brock-wall-art"
                ),
            )
        )

        self.assertEqual(result["submission_id"], original_submission_id)
        self.assertEqual(result["campaign_id"], "120249720387120554")
        self.assertEqual(result["adset_id"], "120249720389890554")
        self.assertEqual(
            result["ad_results"][0]["meta_instant_experience_id"],
            "1390026833255926",
        )
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("canvas"), 2)
        self.assertEqual(client.calls.count("ad"), 3)
        self.assertEqual(
            client.creative_payloads[0]["object_story_spec"]["template_data"]["link"],
            "https://fb.com/canvas_doc/1390026833255926",
        )
        self.assertEqual(
            [row["meta_instant_experience_id"] for row in result["ad_results"]],
            ["1390026833255926", "canvas-1", "canvas-2"],
        )

    def test_store_claim_reuses_unique_failed_fingerprint_without_inserting_new_job(self):
        original_submission_id = "22222222-2222-4222-8222-222222222222"
        partial = {
            "submission_id": original_submission_id,
            "request_fingerprint": "same-fingerprint",
            "status": "FAILED",
            "campaign_id": "120249720387120554",
            "adset_id": "120249720389890554",
        }
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [None, partial, partial]
        cursor.fetchall.return_value = [partial]
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        backend = mock.Mock()
        backend.connect.return_value = connection
        store = SupabasePostingStore()

        with mock.patch.object(store, "_backend", return_value=backend):
            claim = store.claim(
                {
                    "submission_id": "33333333-3333-4333-8333-333333333333",
                    "request_fingerprint": "same-fingerprint",
                    "ad_results": (),
                },
                lease_token="44444444-4444-4444-8444-444444444444",
            )

        self.assertTrue(claim["claimed"])
        self.assertEqual(claim["record"]["submission_id"], original_submission_id)
        statements = [str(call.args[0]) for call in cursor.execute.call_args_list]
        self.assertTrue(any("status='FAILED'" in statement for statement in statements))
        self.assertFalse(any("INSERT INTO meta_posting_submissions" in statement for statement in statements))

    def test_three_name_sequence_advances_as_one_batch(self):
        self.assertEqual(
            next_instant_experience_ad_names(
                "Legends Sports Wall Art",
                ("Legends IA 1", "Legends IA 2", "Legends IA 3"),
            ),
            ("Legends IA 4", "Legends IA 5", "Legends IA 6"),
        )

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
            "ad_name": "Max Verstappen Victory IA 1",
            "ad_results": posting_ad_results(
                (),
                ad_names=(
                    "Max Verstappen Victory IA 1",
                    "Max Verstappen Victory IA 2",
                    "Max Verstappen Victory IA 3",
                ),
            ),
        }
        client = FakePostingClient()
        result = MetaPostingService(client=client, store=FakePostingStore(existing=existing)).create_paused_campaign(
            request_for()
        )
        self.assertEqual(
            [row["ad_name"] for row in result["ad_results"]],
            [
                "Max Verstappen Victory IA 1",
                "Max Verstappen Victory IA 2",
                "Max Verstappen Victory IA 3",
            ],
        )

    def test_missing_canonical_url_blocks_before_meta(self):
        client = FakePostingClient()
        with self.assertRaisesRegex(PostingValidationError, "valid https"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for(destination_url="")
            )
        self.assertEqual(client.calls, [])

    def test_success_copy_is_exact(self):
        self.assertEqual(SUCCESS_MESSAGE, "3 Meta ads created successfully — PAUSED")

    def test_duplicate_pixel_name_blocks_before_writes(self):
        client = FakePostingClient()
        original = client.reference_data

        def references():
            payload = original()
            payload["pixels"] = (
                {"id": "pixel-1", "name": "Shprts Cave Pixel 2025"},
                {"id": "pixel-2", "name": "Shprts Cave Pixel 2025"},
            )
            return payload

        client.reference_data = references
        with self.assertRaisesRegex(PostingValidationError, "Multiple Meta datasets"):
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

    def test_v3_migration_adds_only_the_per_ad_json_ledger(self):
        source = (ROOT / "migrations" / "20260901_meta_posting_v3.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("ADD COLUMN IF NOT EXISTS ad_results JSONB", source)
        self.assertNotIn("DROP TABLE", source.upper())
        self.assertIn(
            'BASE_DIR / "migrations" / "20260901_meta_posting_v3.sql"',
            (ROOT / "supabase_backend.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
