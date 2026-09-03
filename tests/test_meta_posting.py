import io
import json
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import ads_meta_review_page
import ads_navigation
import ads_page
import ads_posting_page
import meta_ads_client
from meta_collection_template_copy import (
    REQUIRED_COLLECTION_FEATURES,
    MetaCollectionTemplateCopyVerificationError,
)
from meta_posting_service import (
    _request_fingerprint,
    EXTERNALLY_ABANDONED_MESSAGE,
    EXISTING_TARGET_MISSING_MESSAGE,
    EXPECTED_PIXEL_NAME,
    CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS,
    CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
    CUSTOMER_LIFECYCLE_UNKNOWN,
    META_OBJECT_CREATED_BY_RUN,
    META_OBJECT_EXISTING_TARGET,
    POSTING_MODE_EXISTING,
    POSTING_MODE_NEW,
    adset_uses_all_audiences,
    SUCCESS_MESSAGE,
    MetaPostingService,
    SupabasePostingStore,
    PostingAmbiguousError,
    PostingAbandonedError,
    PostingError,
    PostingCreative,
    PostingRequest,
    PostingValidationError,
    build_adset_payload,
    build_campaign_payload,
    build_collection_creative_payload,
    build_instant_experience_creation_provenance,
    build_storefront_element_specs,
    build_targeting,
    assess_product_set_health,
    adset_name,
    campaign_name,
    COUNTRY_META_CODES,
    catalog_ids_from_sales_campaigns,
    classify_adset_customer_lifecycle,
    customer_lifecycle_verification,
    dataset_ids_from_purchase_adsets,
    load_posting_reference_snapshot,
    load_existing_posting_targets,
    is_meta_object_missing_or_inaccessible,
    next_instant_experience_ad_name,
    next_instant_experience_ad_names,
    posting_ad_results,
    product_short_name,
    resolve_catalog_reference,
    resolve_dataset_reference,
    verify_instant_experience_destination,
    validate_posting_request,
    validate_existing_posting_target,
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


def existing_target_rows(*, campaign_status="ACTIVE", adset_status="ACTIVE"):
    return (
        {
            "id": "existing-campaign",
            "name": "Existing Sales Campaign",
            "status": campaign_status,
            "configured_status": campaign_status,
            "effective_status": campaign_status,
            "account_id": "123",
            "objective": "OUTCOME_SALES",
            "promoted_object": {"product_catalog_id": "catalog-1"},
            "daily_budget": "5000",
        },
        {
            "id": "existing-adset",
            "name": "Existing Motorsport AU",
            "status": adset_status,
            "configured_status": adset_status,
            "effective_status": adset_status,
            "campaign_id": "existing-campaign",
            "account_id": "123",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "billing_event": "IMPRESSIONS",
            "destination_type": "WEBSITE",
            "promoted_object": {
                "pixel_id": "pixel-1",
                "custom_event_type": "PURCHASE",
                "product_set_id": "set-1",
            },
            "targeting": {"geo_locations": {"countries": ["AU"]}},
            "daily_budget": "2500",
            "ad_set_goal": None,
            "existing_customer_budget_percentage": None,
        },
    )


def existing_request(**overrides):
    return request_for(
        posting_mode=POSTING_MODE_EXISTING,
        target_campaign_id="existing-campaign",
        target_adset_id="existing-adset",
        **overrides,
    )


def configure_existing_target(client, *, campaign_status="ACTIVE", adset_status="ACTIVE"):
    campaign, adset = existing_target_rows(
        campaign_status=campaign_status,
        adset_status=adset_status,
    )
    client.configured_campaign = mock.Mock(return_value=dict(campaign))
    client.configured_adset = mock.Mock(return_value=dict(adset))
    return campaign, adset


class FakePostingStore:
    def __init__(self, existing=None):
        self.record = dict(existing or {})
        self.claims = 0
        self.stages = []

    def claim(self, request_data, *, lease_token):
        self.claims += 1
        existing_run_id = str(self.record.get("submission_id") or "")
        requested_run_id = str(request_data.get("submission_id") or "")
        if existing_run_id and existing_run_id != requested_run_id:
            self.record = {}
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
        self.canvas_readbacks = {}
        self.optional_canvas_readbacks = {}
        self.canvas_element_specs = {}
        self.instant_experience_error = None
        self.optional_canvas_details_error = None
        self.instant_experience_elements_error = None
        self.uploaded_images = []
        self.copy_ads = {}
        self.copy_creatives = {}
        self.rename_calls = []
        self.template_source_ad = {
            "id": "120249557468150554",
            "name": "LEGENDS IA 2",
            "status": "ACTIVE",
            "configured_status": "ACTIVE",
            "effective_status": "ACTIVE",
            "adset_id": "source-adset",
            "creative": {"id": "source-creative"},
        }
        self.template_source_creative = build_collection_creative_payload(
            name="LEGENDS IA 2 | Collection",
            page_id=self.page_id,
            instagram_user_id=self.instagram_user_id,
            image_hash="aaron-image-hash",
            canvas_id="aaron-ia",
            product_set_id="aaron-set",
            destination_url="https://sportscaveshop.com/products/aaron-judge",
            primary_text="Aaron Judge primary",
            headline="Aaron Judge headline",
        )

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
        return f"campaign-{self.calls.count('campaign')}"

    def find_campaigns_by_name(self, name):
        return ()

    def create_adset(self, payload):
        self.calls.append("adset")
        self.adset_payload = payload
        return f"adset-{self.calls.count('adset')}"

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
        element_id = f"{element_type}-element-{self.calls.count(element_type)}"
        self.canvas_element_specs[element_id] = dict(specification)
        return element_id

    def create_canvas(self, *, name, body_element_ids):
        self.calls.append("canvas")
        self.canvas_names.append(name)
        canvas_id = f"canvas-{len(self.canvas_names)}"
        elements = [
            {"element": dict(self.canvas_element_specs.get(element_id) or {})}
            for element_id in body_element_ids
        ]
        for element_id in body_element_ids:
            for child_id in (
                self.canvas_element_specs.get(element_id, {}).get("child_elements") or ()
            ):
                elements.append(
                    {"element": dict(self.canvas_element_specs.get(child_id) or {})}
                )
        self.canvas_readbacks[canvas_id] = {
            "id": canvas_id,
            "name": name,
            "is_published": True,
            "body_elements": elements,
        }
        return canvas_id

    def find_canvases_by_name(self, name):
        return ()

    def instant_experience(self, canvas_id):
        self.calls.append("read_instant_experience")
        if self.instant_experience_error:
            raise self.instant_experience_error
        return dict(self.canvas_readbacks.get(str(canvas_id)) or {})

    def instant_experience_optional_details(self, canvas_id):
        self.calls.append("read_instant_experience_optional_details")
        if self.optional_canvas_details_error:
            raise self.optional_canvas_details_error
        return dict(self.optional_canvas_readbacks.get(str(canvas_id)) or {})

    def instant_experience_elements(self, element_ids):
        self.calls.append("read_instant_experience_elements")
        if self.instant_experience_elements_error:
            raise self.instant_experience_elements_error
        return tuple(
            {
                "id": str(element_id),
                "element": dict(self.canvas_element_specs[str(element_id)]),
            }
            for element_id in element_ids or ()
            if str(element_id) in self.canvas_element_specs
        )

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

    def ad_copies(self, source_ad_id):
        self.calls.append("read_template_copies")
        return tuple(dict(row) for row in self.copy_ads.values())

    def copy_paused_ad_from_template(
        self, *, source_ad_id, target_adset_id, creative_parameters
    ):
        copy_number = len(self.copy_ads) + 1
        self.calls.append("template_copy")
        if self.fail_at == f"ad_{copy_number}":
            raise meta_ads_client.MetaAdsApiError("ad failed")
        ad_id = f"ad-{copy_number}"
        creative_id = f"copied-creative-{copy_number}"
        self.creative_payload = dict(creative_parameters)
        self.creative_payloads.append(dict(creative_parameters))
        self.copy_creatives[creative_id] = {
            "id": creative_id,
            **dict(creative_parameters),
        }
        self.copy_ads[ad_id] = {
            "id": ad_id,
            "name": "LEGENDS IA 2 – Copy",
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "IN_PROCESS",
            "adset_id": str(target_adset_id),
            "source_ad_id": str(source_ad_id),
            "creative": {"id": creative_id},
        }
        return ad_id

    def rename_paused_ad(self, ad_id, *, name, protected_source_ad_id=""):
        self.calls.append("rename_ad")
        if str(ad_id) == str(protected_source_ad_id):
            raise AssertionError("source template must not be renamed")
        self.rename_calls.append((str(ad_id), str(name)))
        self.copy_ads[str(ad_id)]["name"] = str(name)

    def creative(self, creative_id):
        self.calls.append("read_creative")
        if str(creative_id) == "source-creative":
            return {"id": "source-creative", **dict(self.template_source_creative)}
        return dict(self.copy_creatives.get(str(creative_id)) or {})

    def product_set_health(self, product_set_id):
        self.calls.append("read_product_set_health")
        return {
            "product_set": {
                "id": str(product_set_id),
                "name": "Motorsport",
                "product_count": 1,
            },
            "products": (
                {
                    "id": "product-1",
                    "availability": "in stock",
                    "status": "PUBLISHED",
                    "visibility": "published",
                    "review_status": "approved",
                    "errors": [],
                    "url": "https://sportscaveshop.com/products/example",
                },
            ),
        }

    def configured_campaign(self, campaign_id):
        self.calls.append("read_configured_campaign")
        return {"id": campaign_id, "configured_status": "PAUSED"}

    def configured_adset(self, adset_id):
        self.calls.append("read_configured_adset")
        return {"id": adset_id, "configured_status": "PAUSED"}

    def ad(self, ad_id):
        self.calls.append("read_ad")
        if str(ad_id) == str(self.template_source_ad["id"]):
            return dict(self.template_source_ad)
        if str(ad_id) in self.copy_ads:
            return dict(self.copy_ads[str(ad_id)])
        return {"id": ad_id, "status": "PAUSED", "configured_status": "PAUSED"}


class ExistingTargetClientTests(unittest.TestCase):
    def config(self):
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "secret",
            "api_version": "v26.0",
            "page_id": "page-1",
            "page_access_token": "page-secret",
            "instagram_user_id": "ig-1",
        }

    @mock.patch("meta_ads_client._paged_get")
    def test_existing_target_discovery_uses_two_read_only_account_edges(self, get):
        get.side_effect = (
            {"rows": [existing_target_rows()[0]]},
            {"rows": [existing_target_rows()[1]]},
        )
        client = meta_ads_client.MetaPostingClient(self.config())

        result = load_existing_posting_targets(client)

        self.assertEqual(result["campaigns"][0]["id"], "existing-campaign")
        self.assertEqual(result["adsets"][0]["id"], "existing-adset")
        self.assertEqual(get.call_count, 2)
        paths = [call.args[0] for call in get.call_args_list]
        self.assertEqual(paths, ["act_123/campaigns", "act_123/adsets"])
        campaign_fields = get.call_args_list[0].kwargs["params"]["fields"]
        adset_fields = get.call_args_list[1].kwargs["params"]["fields"]
        self.assertIn("objective", campaign_fields)
        self.assertIn("account_id", campaign_fields)
        for field in (
            "campaign_id", "optimization_goal", "billing_event", "promoted_object",
            "targeting", "daily_budget", "lifetime_budget", "ad_set_goal",
            "existing_customer_budget_percentage",
        ):
            self.assertIn(field, adset_fields)

    @mock.patch("meta_ads_client._request")
    def test_configured_target_reads_include_compatibility_fields(self, request):
        request.return_value = {}
        client = meta_ads_client.MetaPostingClient(self.config())
        client.configured_campaign("campaign-1")
        campaign_fields = request.call_args.kwargs["params"]["fields"]
        client.configured_adset("adset-1")
        adset_fields = request.call_args.kwargs["params"]["fields"]
        self.assertIn("objective", campaign_fields)
        self.assertIn("promoted_object", campaign_fields)
        self.assertIn("optimization_goal", adset_fields)
        self.assertIn("billing_event", adset_fields)
        self.assertIn("promoted_object", adset_fields)
        self.assertIn("targeting", adset_fields)
        self.assertIn("ad_set_goal", adset_fields)
        self.assertIn("existing_customer_budget_percentage", adset_fields)


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
        self.assertIn('button("New campaign"', source)
        self.assertIn('button("Start fresh campaign"', source)
        self.assertIn("_start_new_posting_run()", source)
        self.assertIn(
            'st.expander("Advanced Meta Diagnostics", expanded=False)', source
        )
        self.assertLess(
            source.index('"Create 3 Paused Meta Ads"'),
            source.index('st.expander("Advanced Meta Diagnostics", expanded=False)'),
        )

    def test_posting_mode_ui_defaults_new_and_keeps_existing_controls_conditional(self):
        source = (ROOT / "ads_posting_page.py").read_text(encoding="utf-8")
        self.assertIn('"New Campaign"', source)
        self.assertIn('"Add to Existing"', source)
        self.assertIn('st.segmented_control(', source)
        self.assertIn('if posting_mode == POSTING_MODE_EXISTING:', source)
        self.assertIn('"Existing Campaign"', source)
        self.assertIn('"Existing Ad Set"', source)
        self.assertIn('"Add 3 Paused Ads to Existing Ad Set"', source)
        self.assertIn('"Audience and targeting will not be changed."', source)
        self.assertIn('"Existing campaign budget will not be changed."', source)

    def test_lifecycle_ui_defaults_all_audiences_and_keeps_acquisition_fail_closed(self):
        source = (ROOT / "ads_posting_page.py").read_text(encoding="utf-8")
        self.assertIn('"Customer Lifecycle Strategy"', source)
        self.assertIn("CUSTOMER_LIFECYCLE_ALL_AUDIENCES", source)
        self.assertIn("CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS", source)
        self.assertIn("Acquire new customers is not available yet", source)
        self.assertIn("Customer lifecycle settings will not be changed.", source)

    def test_existing_adset_options_are_filtered_by_campaign(self):
        targets = {
            "adsets": (
                {"id": "a", "campaign_id": "campaign-1"},
                {"id": "b", "campaign_id": "campaign-2"},
                {"id": "c", "campaign_id": "campaign-1"},
            )
        }
        self.assertEqual(
            [row["id"] for row in ads_posting_page._adsets_for_campaign(targets, "campaign-1")],
            ["a", "c"],
        )

    def test_posting_result_shows_safe_ia_verification_status_and_source(self):
        result = {
            "status": "FAILED",
            "ad_results": (
                {
                    "index": 1,
                    "instant_experience_verification": {
                        "display_status": "VERIFIED VIA CREATION RECORD",
                        "verification_source": "Persisted creation provenance",
                    },
                },
            ),
        }
        with mock.patch.object(ads_posting_page.st, "subheader"), mock.patch.object(
            ads_posting_page.st, "dataframe"
        ), mock.patch.object(ads_posting_page.st, "caption") as caption:
            ads_posting_page._render_object_result(result, title="Partial result")

        rendered = " ".join(
            str(call.args[0]) for call in caption.call_args_list if call.args
        )
        self.assertIn("Instant Experience 1 destination", rendered)
        self.assertIn("VERIFIED VIA CREATION RECORD", rendered)
        self.assertIn("Persisted creation provenance", rendered)

    def test_optional_product_health_capability_is_rendered_neutrally(self):
        result = {
            "status": "COMPLETE",
            "ad_results": (
                {
                    "index": 1,
                    "product_set_health": {
                        "status": "NOT AVAILABLE VIA META API",
                        "message": "Optional read is unavailable.",
                    },
                },
            ),
        }
        with mock.patch.object(ads_posting_page.st, "subheader"), mock.patch.object(
            ads_posting_page.st, "dataframe"
        ), mock.patch.object(ads_posting_page.st, "caption"), mock.patch.object(
            ads_posting_page.st, "success"
        ), mock.patch.object(ads_posting_page.st, "warning") as warning, mock.patch.object(
            ads_posting_page.st, "info"
        ) as info:
            ads_posting_page._render_object_result(result, title="Completed")

        self.assertEqual(info.call_count, 1)
        self.assertIn("NOT AVAILABLE VIA META API", info.call_args.args[0])
        warning.assert_not_called()

    def test_normal_success_ui_is_compact_and_hides_technical_diagnostics(self):
        base_result = {
            "status": "COMPLETE",
            "meta_status": "PAUSED",
            "campaign_id": "campaign-1",
            "campaign_name": "Campaign",
            "adset_id": "adset-1",
            "adset_name": "Ad Set",
            "product_title": "Hidden Product",
            "country": "AUS",
            "product_set_name": "Hidden Product Set",
            "destination_url": "https://sportscaveshop.com/products/hidden",
            "verified_lifecycle_strategy": CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
            "lifecycle_verification_source": "Hidden lifecycle verification",
            "ad_results": tuple(
                {
                    "index": index,
                    "ad_name": f"Route {index}",
                    "instant_experience_name": f"Route {index} | Storefront",
                    "meta_instant_experience_id": f"canvas-{index}",
                    "meta_ad_id": f"ad-{index}",
                    "meta_ad_configured_status": "PAUSED",
                    "instant_experience_verification": {
                        "display_status": "VERIFIED VIA CREATION RECORD",
                        "verification_source": "Persisted creation provenance",
                    },
                    "product_set_health": {
                        "status": "NOT AVAILABLE VIA META API",
                        "message": "Hidden Product Set health message",
                    },
                }
                for index in range(1, 4)
            ),
        }
        for posting_mode, expected_message in (
            (POSTING_MODE_NEW, SUCCESS_MESSAGE),
            (POSTING_MODE_EXISTING, "3 Meta ads added successfully — PAUSED"),
        ):
            with self.subTest(posting_mode=posting_mode):
                result = {**base_result, "posting_mode": posting_mode}
                actions = (mock.Mock(), mock.Mock(), mock.Mock())
                actions[1].button.return_value = False
                with mock.patch.object(
                    ads_posting_page.st, "success"
                ) as success, mock.patch.object(
                    ads_posting_page.st, "subheader"
                ), mock.patch.object(
                    ads_posting_page.st, "dataframe"
                ) as dataframe, mock.patch.object(
                    ads_posting_page.st, "caption"
                ) as caption, mock.patch.object(
                    ads_posting_page.st, "info"
                ) as info, mock.patch.object(
                    ads_posting_page.st, "warning"
                ) as warning, mock.patch.object(
                    ads_posting_page.st, "columns", return_value=actions
                ), mock.patch.object(
                    ads_posting_page, "MetaPostingClient"
                ) as client_type:
                    client_type.return_value.ad_account_id = "act_123"
                    ads_posting_page._render_success(result)

                self.assertEqual(success.call_args.args[0], expected_message)
                rows = dataframe.call_args.args[0]
                self.assertEqual(len(rows), 8)
                self.assertEqual(
                    [row["Object"] for row in rows],
                    [
                        "Campaign",
                        "Ad set",
                        "Instant Experience 1",
                        "Ad 1",
                        "Instant Experience 2",
                        "Ad 2",
                        "Instant Experience 3",
                        "Ad 3",
                    ],
                )
                visible = f"{expected_message} {rows}"
                for hidden_text in (
                    "VERIFIED VIA CREATION RECORD",
                    "Persisted creation provenance",
                    "Product Set health",
                    "Product:",
                    "Campaign budget:",
                    "Customer lifecycle:",
                    "Lifecycle verification:",
                ):
                    self.assertNotIn(hidden_text, visible)
                caption.assert_not_called()
                info.assert_not_called()
                warning.assert_not_called()
                actions[0].link_button.assert_called_once()
                self.assertEqual(
                    actions[0].link_button.call_args.args[0], "Open in Ads Manager"
                )
                self.assertEqual(actions[1].button.call_args.args[0], "New campaign")

    def test_existing_target_result_keeps_active_status_while_new_ads_show_paused(self):
        result = {
            "status": "COMPLETE",
            "meta_status": "PAUSED",
            "posting_mode": POSTING_MODE_EXISTING,
            "campaign_id": "existing-campaign",
            "campaign_name": "Existing Campaign",
            "campaign_ownership": META_OBJECT_EXISTING_TARGET,
            "campaign_configured_status": "ACTIVE",
            "adset_id": "existing-adset",
            "adset_name": "Existing Ad Set",
            "adset_ownership": META_OBJECT_EXISTING_TARGET,
            "adset_configured_status": "ACTIVE",
            "ad_results": tuple(
                {
                    "index": index,
                    "meta_ad_id": f"new-ad-{index}",
                    "meta_ad_configured_status": "PAUSED",
                }
                for index in range(1, 4)
            ),
        }
        with mock.patch.object(ads_posting_page.st, "subheader"), mock.patch.object(
            ads_posting_page.st, "dataframe"
        ) as dataframe, mock.patch.object(ads_posting_page.st, "caption"):
            ads_posting_page._render_object_result(result, title="Completed")
        rows = dataframe.call_args.args[0]
        self.assertEqual(rows[0]["State"], "ACTIVE")
        self.assertEqual(rows[1]["State"], "ACTIVE")
        self.assertEqual(
            [row["State"] for row in rows if row["Object"] in {"Ad 1", "Ad 2", "Ad 3"}],
            ["PAUSED", "PAUSED", "PAUSED"],
        )


class PostingPayloadTests(unittest.TestCase):
    def test_posting_request_defaults_to_new_campaign_without_external_ids(self):
        clean = validate_posting_request(request_for())
        self.assertEqual(clean["posting_mode"], POSTING_MODE_NEW)
        self.assertEqual(clean["target_campaign_id"], "")
        self.assertEqual(clean["target_adset_id"], "")
        self.assertEqual(
            clean["customer_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )

    def test_existing_mode_uses_inherited_audience_and_requires_both_targets(self):
        clean = validate_posting_request(existing_request())
        self.assertEqual(clean["posting_mode"], POSTING_MODE_EXISTING)
        self.assertEqual(clean["audience_type"], "inherited")
        self.assertEqual(clean["audience_id"], "")
        self.assertEqual(clean["customer_lifecycle_strategy"], "")
        with self.assertRaisesRegex(PostingValidationError, "existing Meta Ad Set"):
            validate_posting_request(
                request_for(
                    posting_mode=POSTING_MODE_EXISTING,
                    target_campaign_id="existing-campaign",
                    target_adset_id="",
                )
            )

    def test_new_mode_rejects_external_ids_from_another_run(self):
        with self.assertRaisesRegex(PostingValidationError, "cannot use Campaign"):
            validate_posting_request(
                request_for(
                    posting_mode=POSTING_MODE_NEW,
                    target_campaign_id="historical-campaign",
                )
            )

    def test_existing_target_compatibility_requires_sales_purchase_pixel_and_product_set(self):
        campaign, adset = existing_target_rows()
        validated = validate_existing_posting_target(
            campaign=campaign,
            adset=adset,
            expected_campaign_id="existing-campaign",
            expected_adset_id="existing-adset",
            expected_account_id="act_123",
            expected_catalog_id="catalog-1",
            expected_product_set_id="set-1",
            expected_pixel_id="pixel-1",
        )
        self.assertEqual(validated["campaign_status"], "ACTIVE")
        for field, value, message in (
            ("optimization_goal", "LINK_CLICKS", "website Purchase"),
            ("billing_event", "APP_INSTALLS", "billing"),
        ):
            incompatible = dict(adset)
            incompatible[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                PostingValidationError, message
            ):
                validate_existing_posting_target(
                    campaign=campaign,
                    adset=incompatible,
                    expected_campaign_id="existing-campaign",
                    expected_adset_id="existing-adset",
                    expected_account_id="act_123",
                    expected_catalog_id="catalog-1",
                    expected_product_set_id="set-1",
                    expected_pixel_id="pixel-1",
                )

        compatibility_cases = (
            ("campaign", "objective", "OUTCOME_AWARENESS", "Sales campaign"),
            ("campaign", "account_id", "999", "ad account"),
            ("adset", "account_id", "999", "ad account"),
        )
        for row_name, field, value, message in compatibility_cases:
            changed_campaign = dict(campaign)
            changed_adset = dict(adset)
            (changed_campaign if row_name == "campaign" else changed_adset)[field] = value
            with self.subTest(row=row_name, field=field), self.assertRaisesRegex(
                PostingValidationError, message
            ):
                validate_existing_posting_target(
                    campaign=changed_campaign,
                    adset=changed_adset,
                    expected_campaign_id="existing-campaign",
                    expected_adset_id="existing-adset",
                    expected_account_id="act_123",
                    expected_catalog_id="catalog-1",
                    expected_product_set_id="set-1",
                    expected_pixel_id="pixel-1",
                )
        wrong_pixel = dict(adset)
        wrong_pixel["promoted_object"] = {
            **adset["promoted_object"],
            "pixel_id": "another-pixel",
        }
        with self.assertRaisesRegex(PostingValidationError, "different Pixel"):
            validate_existing_posting_target(
                campaign=campaign,
                adset=wrong_pixel,
                expected_campaign_id="existing-campaign",
                expected_adset_id="existing-adset",
                expected_account_id="act_123",
                expected_catalog_id="catalog-1",
                expected_product_set_id="set-1",
                expected_pixel_id="pixel-1",
            )

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
        self.assertNotIn("ad_set_goal", payload)
        self.assertNotIn("existing_customer_budget_percentage", payload)
        self.assertEqual(
            payload["targeting"], build_targeting(country="AUS")
        )

    def test_customer_lifecycle_readback_requires_no_acquisition_configuration(self):
        self.assertFalse(adset_uses_all_audiences({}))
        self.assertEqual(
            classify_adset_customer_lifecycle({}),
            CUSTOMER_LIFECYCLE_UNKNOWN,
        )
        self.assertFalse(
            adset_uses_all_audiences({}, acquisition_fields_requested=True)
        )
        self.assertTrue(
            adset_uses_all_audiences(
                {"id": "adset-1"}, acquisition_fields_requested=True
            )
        )
        self.assertTrue(
            adset_uses_all_audiences(
                {"ad_set_goal": None, "existing_customer_budget_percentage": None}
            )
        )
        self.assertFalse(adset_uses_all_audiences({"ad_set_goal": {"type": "NEW_CUSTOMER"}}))
        self.assertFalse(adset_uses_all_audiences({"existing_customer_budget_percentage": 0}))

    def test_customer_lifecycle_verification_has_three_evidence_based_states(self):
        unknown = customer_lifecycle_verification({})
        all_audiences = customer_lifecycle_verification(
            {"id": "adset-1"}, acquisition_fields_requested=True
        )
        acquisition = customer_lifecycle_verification(
            {"ad_set_goal": {"type": 1}},
            acquisition_fields_requested=True,
        )
        self.assertEqual(unknown["strategy"], CUSTOMER_LIFECYCLE_UNKNOWN)
        self.assertEqual(
            all_audiences["strategy"], CUSTOMER_LIFECYCLE_ALL_AUDIENCES
        )
        self.assertEqual(
            acquisition["strategy"],
            CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS,
        )
        self.assertNotIn("type", acquisition["verification_source"])

    def test_unverified_acquire_new_customers_never_builds_partial_payload(self):
        with self.assertRaisesRegex(
            PostingValidationError,
            "complete existing-customer audience contract",
        ):
            validate_posting_request(
                request_for(
                    customer_lifecycle_strategy=(
                        CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS
                    )
                )
            )
        with self.assertRaisesRegex(PostingValidationError, "cannot be sent"):
            build_adset_payload(
                name="Ad set",
                campaign_id="campaign-1",
                product_set_id="set-1",
                pixel_id="pixel-1",
                targeting=build_targeting(country="AUS"),
                customer_lifecycle_strategy=(
                    CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS
                ),
            )

    def test_non_default_lifecycle_is_part_of_request_content_not_run_identity(self):
        clean = validate_posting_request(request_for())
        default_fingerprint = _request_fingerprint(clean)
        acquisition_content = dict(clean)
        acquisition_content["customer_lifecycle_strategy"] = (
            CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS
        )
        self.assertNotEqual(
            default_fingerprint,
            _request_fingerprint(acquisition_content),
        )
        another_run = validate_posting_request(
            request_for(
                submission_id="22222222-2222-4222-8222-222222222222"
            )
        )
        self.assertEqual(default_fingerprint, _request_fingerprint(another_run))

    def test_collection_creative_contract(self):
        payload = build_collection_creative_payload(
            name="Creative", page_id="page-1", instagram_user_id="ig-1",
            image_hash="route-image-hash",
            canvas_id="canvas-1", product_set_id="set-1",
            destination_url="https://sportscaveshop.com/products/a", primary_text="Text",
            headline="Headline", description="Description retained in Posting state",
        )
        story = payload["object_story_spec"]
        self.assertNotIn("template_data", story)
        link_data = story["link_data"]
        self.assertNotIn("canvas_id", link_data)
        self.assertNotIn("format_option", link_data)
        self.assertNotIn("picture", link_data)
        self.assertEqual(link_data["image_hash"], "route-image-hash")
        self.assertEqual(link_data["link"], "https://fb.com/canvas_doc/canvas-1")
        self.assertEqual(link_data["message"], "Text")
        self.assertEqual(link_data["name"], "Headline")
        self.assertEqual(link_data["call_to_action"], {"type": "SHOP_NOW"})
        self.assertEqual(link_data["retailer_item_ids"], ["0", "0", "0", "0"])
        self.assertTrue(all(isinstance(value, str) for value in link_data["retailer_item_ids"]))
        self.assertNotIn("customization_rules_spec", link_data)
        self.assertNotIn("description", link_data)
        self.assertEqual(payload["product_set_id"], "set-1")
        self.assertEqual(payload["image_hash"], link_data["image_hash"])
        self.assertEqual(payload["object_story_spec"]["page_id"], "page-1")
        self.assertEqual(payload["object_story_spec"]["instagram_user_id"], "ig-1")
        self.assertEqual(payload["contextual_multi_ads"], {"enroll_status": "OPT_IN"})
        features = payload["degrees_of_freedom_spec"]["creative_features_spec"]
        self.assertEqual(
            features,
            {
                name: {"enroll_status": enrollment}
                for name, enrollment in REQUIRED_COLLECTION_FEATURES.items()
            },
        )
        self.assertEqual(features["description_automation"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["inline_comment"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["hide_price"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["enhance_cta"]["enroll_status"], "OPT_IN")
        self.assertEqual(features["image_background_gen"]["enroll_status"], "OPT_OUT")
        self.assertEqual(features["adapt_to_placement"]["enroll_status"], "OPT_OUT")
        self.assertEqual(features["image_auto_crop"]["enroll_status"], "OPT_OUT")
        self.assertEqual(features["image_touchups"]["enroll_status"], "OPT_OUT")
        self.assertEqual(features["pac_genai_recomposition"]["enroll_status"], "OPT_OUT")
        self.assertEqual(features["pac_recomposition"]["enroll_status"], "OPT_OUT")
        self.assertNotIn("standard_enhancements", features)
        self.assertIn("utm_source=facebook", payload["url_tags"])

    def test_storefront_component_contract(self):
        specs = build_storefront_element_specs(
            page_photo_id="photo-1", product_set_id="set-1",
            destination_url="https://sportscaveshop.com/products/shane-warne",
            button_element_id="button-1",
        )
        self.assertEqual(specs["canvas_photo"]["photo_id"], "photo-1")
        self.assertEqual(
            specs["canvas_photo"],
            {"photo_id": "photo-1", "style": "FIT_TO_WIDTH"},
        )
        self.assertEqual(specs["canvas_product_set"]["product_set_id"], "set-1")
        self.assertEqual(specs["canvas_product_set"]["item_headline"], "{{product.name}}")
        self.assertEqual(specs["canvas_product_set"]["item_description"], "Limited Edition")
        self.assertEqual(specs["canvas_button"]["rich_text"]["plain_text"], "Claim Your Edition")
        self.assertEqual(
            specs["canvas_button"]["open_url_action"]["url"],
            "https://sportscaveshop.com/products/shane-warne",
        )
        self.assertEqual(specs["canvas_footer"]["child_elements"], ["button-1"])

    def test_instant_experience_fixed_button_readback_requires_exact_shopify_url(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        canvas = {
            "body_elements": [
                {
                    "element": {
                        "rich_text": {"plain_text": "Claim Your Edition"},
                        "open_url_action": {"url": url},
                    }
                }
            ]
        }
        self.assertTrue(
            verify_instant_experience_destination(canvas, expected_url=url)["verified"]
        )
        self.assertFalse(
            verify_instant_experience_destination(
                canvas,
                expected_url="https://sportscaveshop.com/products/a-different-product",
            )["verified"]
        )
        with self.assertRaisesRegex(PostingValidationError, "Facebook URL"):
            verify_instant_experience_destination(
                canvas, expected_url="https://facebook.com/products/not-allowed"
            )
        with self.assertRaisesRegex(PostingValidationError, "Facebook URL"):
            verify_instant_experience_destination(
                canvas, expected_url="https://fb.com/canvas_doc/not-a-shopify-url"
            )
        with self.assertRaisesRegex(PostingValidationError, "Sports Cave product URL"):
            verify_instant_experience_destination(
                canvas, expected_url="https://example.com/products/not-sports-cave"
            )

    def test_instant_experience_element_payload_json_verifies(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        result = verify_instant_experience_destination(
            {
                "element_payload": json.dumps(
                    {
                        "canvas_button": {
                            "rich_text": {"plain_text": "Claim Your Edition"},
                            "open_url_action": {"url": url},
                        }
                    }
                )
            },
            expected_url=url,
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["verification_source"], "Meta element payload")

    def test_instant_experience_fb_body_elements_verifies(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        result = verify_instant_experience_destination(
            {
                "fb_body_elements": [
                    {
                        "element": {
                            "rich_text": {"plain_text": "Claim Your Edition"},
                            "open_url_action": {"url": url},
                        }
                    }
                ]
            },
            expected_url=url,
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["verification_source"], "Meta element payload")

    def test_instant_experience_reference_only_body_is_unavailable_not_mismatch(self):
        result = verify_instant_experience_destination(
            {"body_elements": [{"id": "button-1"}, "footer-1"]},
            expected_url="https://sportscaveshop.com/products/shane-warne",
        )
        self.assertFalse(result["verified"])
        self.assertEqual(result["verification_state"], "UNAVAILABLE")

    def test_instant_experience_direct_child_element_verifies(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        result = verify_instant_experience_destination(
            {"body_elements": [{"id": "button-1"}]},
            expected_url=url,
            child_elements=(
                {
                    "id": "button-1",
                    "element": {
                        "rich_text": {"plain_text": "Claim Your Edition"},
                        "open_url_action": {"url": url},
                    },
                },
            ),
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["verification_source"], "Meta child element")

    def test_instant_experience_explicit_wrong_label_or_url_is_mismatch(self):
        expected_url = "https://sportscaveshop.com/products/shane-warne"
        for label, url in (
            ("Wrong label", expected_url),
            (
                "Claim Your Edition",
                "https://sportscaveshop.com/products/wrong-product",
            ),
            ("Claim Your Edition", "https://facebook.com/products/wrong"),
        ):
            with self.subTest(label=label, url=url):
                result = verify_instant_experience_destination(
                    {
                        "body_elements": [
                            {
                                "element": {
                                    "rich_text": {"plain_text": label},
                                    "open_url_action": {"url": url},
                                }
                            }
                        ]
                    },
                    expected_url=expected_url,
                )
                self.assertFalse(result["verified"])
                self.assertEqual(result["verification_state"], "MISMATCH")

    def test_instant_experience_complete_creation_provenance_verifies_omission(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        provenance = build_instant_experience_creation_provenance(
            submission_id="11111111-1111-4111-8111-111111111111",
            request_fingerprint="fingerprint-1",
            canvas_id="canvas-1",
            button_element_id="button-1",
            footer_element_id="footer-1",
            destination_url=url,
        )
        result = verify_instant_experience_destination(
            {"id": "canvas-1", "body_elements": [{"id": "footer-1"}]},
            expected_url=url,
            provenance=provenance,
            expected_canvas_id="canvas-1",
            expected_request_fingerprint="fingerprint-1",
            expected_submission_id="11111111-1111-4111-8111-111111111111",
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["display_status"], "VERIFIED VIA CREATION RECORD")
        self.assertEqual(
            result["verification_source"], "Persisted creation provenance"
        )

    def test_instant_experience_provenance_rejects_changed_request_or_destination(self):
        url = "https://sportscaveshop.com/products/shane-warne"
        provenance = build_instant_experience_creation_provenance(
            submission_id="11111111-1111-4111-8111-111111111111",
            request_fingerprint="fingerprint-1",
            canvas_id="canvas-1",
            button_element_id="button-1",
            footer_element_id="footer-1",
            destination_url=url,
        )
        cases = (
            (url, "different-fingerprint"),
            ("https://sportscaveshop.com/products/different", "fingerprint-1"),
        )
        for expected_url, fingerprint in cases:
            with self.subTest(expected_url=expected_url, fingerprint=fingerprint):
                result = verify_instant_experience_destination(
                    {"id": "canvas-1", "body_elements": [{"id": "footer-1"}]},
                    expected_url=expected_url,
                    provenance=provenance,
                    expected_canvas_id="canvas-1",
                    expected_request_fingerprint=fingerprint,
                    expected_submission_id="11111111-1111-4111-8111-111111111111",
                )
                self.assertFalse(result["verified"])
                self.assertEqual(result["verification_state"], "UNAVAILABLE")

    def test_product_set_health_warns_when_meta_exposes_no_eligible_products(self):
        health = assess_product_set_health(
            {
                "product_set": {
                    "id": "set-1",
                    "name": "Motor Racing Wall Art",
                    "product_count": 2,
                },
                "products": (
                    {
                        "id": "p1",
                        "availability": "out of stock",
                        "status": "PUBLISHED",
                        "visibility": "published",
                        "review_status": "approved",
                    },
                    {
                        "id": "p2",
                        "availability": "in stock",
                        "status": "STAGING",
                        "visibility": "staging",
                        "review_status": "rejected",
                    },
                ),
            }
        )
        self.assertEqual(health["status"], "WARNING")
        self.assertEqual(health["eligible_product_count"], 0)
        self.assertTrue(health["read_only"])
        self.assertIn("no eligible catalogue products", health["message"])
        self.assertTrue(
            any("availability=out of stock" in row for row in health["reason_details"])
        )

    def test_product_set_health_does_not_treat_missing_availability_as_eligible(self):
        health = assess_product_set_health(
            {
                "product_set": {"id": "set-1", "product_count": 1},
                "products": ({"id": "p1", "status": "PUBLISHED"},),
            }
        )
        self.assertEqual(health["status"], "WARNING")
        self.assertEqual(health["eligible_product_count"], 0)
        self.assertEqual(health["reason_counts"], {"availability=unknown": 1})
        self.assertEqual(health["reason_details"], ("p1: availability=unknown",))


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

    @mock.patch("meta_ads_client._request", return_value={"id": "adset-1"})
    def test_configured_adset_readback_requests_customer_lifecycle_fields(self, request):
        meta_ads_client.MetaPostingClient(self.config()).configured_adset("adset-1")
        fields = request.call_args.kwargs["params"]["fields"]
        self.assertIn("ad_set_goal", fields)
        self.assertIn("existing_customer_budget_percentage", fields)

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
        self.assertIn("object_story_spec.link_data", message)
        self.assertIn("image_hash", message)
        self.assertIn("retailer_item_ids", message)
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
                image_hash="hash",
                canvas_id="canvas-1", product_set_id="set-1",
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

    @mock.patch("meta_ads_client._request", return_value={"id": "canvas-1"})
    def test_instant_experience_readback_is_page_scoped_and_read_only(self, request):
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(client.instant_experience("canvas-1"), {"id": "canvas-1"})
        self.assertEqual(request.call_args.args[0], "canvas-1")
        self.assertEqual(request.call_args.kwargs["access_token"], "page-secret")
        self.assertEqual(
            request.call_args.kwargs["params"]["fields"],
            "id,name,is_published,body_elements",
        )

    @mock.patch("meta_ads_client._request")
    def test_instant_experience_base_read_does_not_swallow_code_three(self, request):
        request.side_effect = meta_ads_client.MetaAdsApiError(
            "Application does not have the capability to make this API call.",
            error_code=3,
        )
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            meta_ads_client.MetaPostingClient(self.config()).instant_experience("canvas-1")

    @mock.patch("meta_ads_client._request")
    def test_optional_instant_experience_details_swallow_code_three(self, request):
        request.side_effect = meta_ads_client.MetaAdsApiError(
            "Application does not have the capability to make this API call.",
            error_code=3,
        )
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(client.instant_experience_optional_details("canvas-1"), {})
        self.assertEqual(request.call_args.args[0], "canvas-1")
        self.assertEqual(request.call_args.kwargs["access_token"], "page-secret")
        self.assertEqual(
            request.call_args.kwargs["params"]["fields"],
            "fb_body_elements,element_payload,store_url,use_retailer_item_ids",
        )

    @mock.patch("meta_ads_client._request")
    def test_optional_instant_experience_details_do_not_swallow_auth_error(self, request):
        request.side_effect = meta_ads_client.MetaAdsApiError(
            "Invalid OAuth access token.",
            error_code=190,
        )
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            meta_ads_client.MetaPostingClient(
                self.config()
            ).instant_experience_optional_details("canvas-1")

    @mock.patch("meta_ads_client._paged_get")
    def test_instant_experience_element_read_is_page_scoped_and_read_only(
        self, paged_get
    ):
        paged_get.return_value = {
            "rows": (
                {"id": "button-1", "element": {"canvas_button": {}}},
                {"id": "other", "element": {}},
            )
        }
        client = meta_ads_client.MetaPostingClient(self.config())

        self.assertEqual(
            client.instant_experience_elements(("button-1", "footer-1")),
            ({"id": "button-1", "element": {"canvas_button": {}}},),
        )
        self.assertEqual(paged_get.call_args.args[0], "page-1/canvas_elements")
        self.assertEqual(paged_get.call_args.kwargs["access_token"], "page-secret")
        self.assertEqual(
            paged_get.call_args.kwargs["params"]["fields"], "id,element"
        )

    @mock.patch("meta_ads_client._paged_get")
    def test_optional_instant_experience_element_read_swallows_code_three(
        self, paged_get
    ):
        paged_get.side_effect = meta_ads_client.MetaAdsApiError(
            "Application does not have the capability to make this API call.",
            error_code=3,
        )
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(client.instant_experience_elements(("button-1",)), ())

    @mock.patch("meta_ads_client._paged_get")
    def test_optional_instant_experience_element_read_does_not_swallow_auth_error(
        self, paged_get
    ):
        paged_get.side_effect = meta_ads_client.MetaAdsApiError(
            "Invalid OAuth access token.",
            error_code=190,
        )
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            meta_ads_client.MetaPostingClient(self.config()).instant_experience_elements(
                ("button-1",)
            )

    @mock.patch("meta_ads_client._post")
    @mock.patch("meta_ads_client._paged_get", return_value={"rows": ({"id": "p1"},)})
    @mock.patch("meta_ads_client._request", return_value={"id": "set-1", "product_count": 1})
    def test_product_set_health_check_uses_only_read_edges(self, request, paged_get, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        result = client.product_set_health("set-1")
        self.assertEqual(result["product_set"]["id"], "set-1")
        self.assertEqual(result["products"], ({"id": "p1"},))
        self.assertEqual(request.call_args.args[0], "set-1")
        self.assertEqual(paged_get.call_args.args[0], "set-1/products")
        self.assertIn("availability", paged_get.call_args.kwargs["params"]["fields"])
        post.assert_not_called()

    @mock.patch("meta_ads_client._post")
    @mock.patch(
        "meta_ads_client._request",
        return_value={
            "id": "copied-ad",
            "status": "PAUSED",
            "configured_status": "PAUSED",
        },
    )
    def test_rename_updates_only_new_paused_copy_and_never_source(self, request, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        client.rename_paused_ad(
            "copied-ad",
            name="Six Laps Ahead Peter Brock IA 1",
            protected_source_ad_id="source-ad",
        )
        self.assertEqual(post.call_args.args[0], "copied-ad")
        self.assertEqual(
            post.call_args.kwargs["data"],
            {"name": "Six Laps Ahead Peter Brock IA 1"},
        )
        with self.assertRaisesRegex(meta_ads_client.MetaAdsApiError, "cannot be renamed"):
            client.rename_paused_ad(
                "source-ad", name="Forbidden", protected_source_ad_id="source-ad"
            )
        self.assertEqual(post.call_count, 1)

    @mock.patch("meta_ads_client._post")
    @mock.patch(
        "meta_ads_client._request",
        return_value={
            "id": "copied-ad",
            "status": "PAUSED",
            "configured_status": "ACTIVE",
        },
    )
    def test_rename_requires_both_status_fields_to_be_paused(self, request, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        with self.assertRaisesRegex(meta_ads_client.MetaAdsApiError, "not PAUSED"):
            client.rename_paused_ad(
                "copied-ad",
                name="Six Laps Ahead Peter Brock IA 2",
                protected_source_ad_id="source-ad",
            )
        post.assert_not_called()

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

    def test_existing_target_discovery_is_short_cached_and_refreshable(self):
        targets = {
            "campaigns": (existing_target_rows()[0],),
            "adsets": (existing_target_rows()[1],),
        }
        ads_posting_page._load_existing_meta_targets.clear()
        try:
            with mock.patch.object(
                ads_posting_page,
                "load_existing_posting_targets",
                return_value=targets,
            ) as load:
                first, first_error = ads_posting_page._existing_targets_state()
                cached, cached_error = ads_posting_page._existing_targets_state()
                refreshed, refreshed_error = ads_posting_page._existing_targets_state(
                    force=True
                )
        finally:
            ads_posting_page._load_existing_meta_targets.clear()
        self.assertEqual((first_error, cached_error, refreshed_error), ("", "", ""))
        self.assertEqual(first, cached)
        self.assertEqual(cached, refreshed)
        self.assertEqual(load.call_count, 2)

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
    def test_existing_mode_creates_only_three_new_ias_and_three_paused_ads(self):
        client = FakePostingClient()
        campaign_before, adset_before = configure_existing_target(client)
        store = FakePostingStore()

        result = MetaPostingService(client=client, store=store).create_paused_campaign(
            existing_request()
        )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["posting_mode"], POSTING_MODE_EXISTING)
        self.assertEqual(result["campaign_id"], "existing-campaign")
        self.assertEqual(result["adset_id"], "existing-adset")
        self.assertEqual(result["campaign_ownership"], META_OBJECT_EXISTING_TARGET)
        self.assertEqual(result["adset_ownership"], META_OBJECT_EXISTING_TARGET)
        self.assertEqual(result["campaign_configured_status"], "ACTIVE")
        self.assertEqual(result["adset_configured_status"], "ACTIVE")
        self.assertIsNone(result["requested_lifecycle_strategy"])
        self.assertEqual(
            result["verified_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertTrue(result["lifecycle_verification_source"])
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("canvas"), 3)
        self.assertEqual(client.calls.count("template_copy"), 3)
        self.assertEqual(
            {row["adset_id"] for row in client.copy_ads.values()},
            {"existing-adset"},
        )
        self.assertEqual(
            {row["configured_status"] for row in client.copy_ads.values()},
            {"PAUSED"},
        )
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["message"]
                for payload in client.creative_payloads
            ],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["name"]
                for payload in client.creative_payloads
            ],
            ["Headline 1", "Headline 2", "Headline 3"],
        )
        self.assertTrue(
            all(ad_id in client.copy_ads for ad_id, _name in client.rename_calls)
        )
        self.assertEqual(client.configured_campaign.call_count, 1)
        self.assertEqual(client.configured_adset.call_count, 1)
        self.assertEqual(client.configured_campaign.return_value, campaign_before)
        self.assertEqual(client.configured_adset.return_value, adset_before)
        self.assertEqual(client.template_source_ad["status"], "ACTIVE")

    def test_existing_mode_accepts_paused_target_without_changing_it(self):
        client = FakePostingClient()
        configure_existing_target(
            client, campaign_status="PAUSED", adset_status="PAUSED"
        )
        result = MetaPostingService(
            client=client, store=FakePostingStore()
        ).create_paused_campaign(existing_request())
        self.assertEqual(result["campaign_configured_status"], "PAUSED")
        self.assertEqual(result["adset_configured_status"], "PAUSED")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)

    def test_existing_mode_product_set_mismatch_blocks_before_meta_writes(self):
        client = FakePostingClient()
        campaign, adset = existing_target_rows()
        adset["promoted_object"] = {
            **adset["promoted_object"],
            "product_set_id": "different-set",
        }
        client.configured_campaign = mock.Mock(return_value=campaign)
        client.configured_adset = mock.Mock(return_value=adset)

        with self.assertRaisesRegex(PostingValidationError, "different Product Set"):
            MetaPostingService(
                client=client, store=FakePostingStore()
            ).create_paused_campaign(existing_request())

        self.assertNotIn("campaign", client.calls)
        self.assertNotIn("adset", client.calls)
        self.assertNotIn("ad_image", client.calls)
        self.assertNotIn("page_photo", client.calls)
        self.assertNotIn("template_copy", client.calls)

    def test_existing_mode_wrong_campaign_relationship_blocks_before_writes(self):
        client = FakePostingClient()
        campaign, adset = existing_target_rows()
        adset["campaign_id"] = "another-campaign"
        client.configured_campaign = mock.Mock(return_value=campaign)
        client.configured_adset = mock.Mock(return_value=adset)
        with self.assertRaisesRegex(PostingValidationError, "does not belong"):
            MetaPostingService(
                client=client, store=FakePostingStore()
            ).create_paused_campaign(existing_request())
        self.assertNotIn("ad_image", client.calls)
        self.assertNotIn("template_copy", client.calls)

    def test_existing_mode_deleted_target_is_abandoned_without_replacement(self):
        client = FakePostingClient()
        client.configured_campaign = mock.Mock(
            side_effect=meta_ads_client.MetaAdsApiError(
                "Unsupported get request. Object with ID does not exist.",
                error_code=100,
            )
        )
        store = FakePostingStore()
        with self.assertRaises(PostingAbandonedError) as caught:
            MetaPostingService(client=client, store=store).create_paused_campaign(
                existing_request()
            )
        self.assertEqual(str(caught.exception), EXISTING_TARGET_MISSING_MESSAGE)
        self.assertEqual(store.record["status"], "ABANDONED_EXTERNALLY")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("template_copy"), 0)

        adset_missing_client = FakePostingClient()
        campaign, _adset = existing_target_rows()
        adset_missing_client.configured_campaign = mock.Mock(return_value=campaign)
        adset_missing_client.configured_adset = mock.Mock(
            side_effect=meta_ads_client.MetaAdsApiError(
                "Unsupported get request. Ad Set does not exist.", error_code=100
            )
        )
        missing_store = FakePostingStore()
        with self.assertRaises(PostingAbandonedError):
            MetaPostingService(
                client=adset_missing_client, store=missing_store
            ).create_paused_campaign(existing_request())
        self.assertEqual(missing_store.record["status"], "ABANDONED_EXTERNALLY")
        self.assertNotIn("template_copy", adset_missing_client.calls)

    def test_existing_mode_same_run_retry_reuses_routes_and_never_creates_hierarchy(self):
        client = FakePostingClient(fail_at="ad_2")
        configure_existing_target(client)
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        with self.assertRaises(PostingError):
            service.create_paused_campaign(existing_request())

        client.fail_at = ""
        result = service.create_paused_campaign(existing_request())

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("canvas"), 3)
        self.assertEqual(client.calls.count("template_copy"), 4)
        self.assertEqual(len(client.copy_ads), 3)
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["message"]
                for payload in client.creative_payloads
            ],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [row["meta_ad_id"] for row in result["ad_results"]],
            ["ad-1", "ad-2", "ad-3"],
        )

    def test_two_existing_mode_runs_can_add_distinct_routes_to_same_adset(self):
        client = FakePostingClient()
        configure_existing_target(client)
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        first = service.create_paused_campaign(
            existing_request(
                submission_id="22222222-2222-4222-8222-222222222222"
            )
        )
        second = service.create_paused_campaign(
            existing_request(
                submission_id="33333333-3333-4333-8333-333333333333"
            )
        )
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("canvas"), 6)
        self.assertEqual(client.calls.count("template_copy"), 6)
        self.assertTrue(
            set(row["meta_instant_experience_id"] for row in first["ad_results"])
            .isdisjoint(
                row["meta_instant_experience_id"] for row in second["ad_results"]
            )
        )
        self.assertTrue(
            set(row["meta_ad_id"] for row in first["ad_results"]).isdisjoint(
                row["meta_ad_id"] for row in second["ad_results"]
            )
        )

    def test_new_adset_acquisition_configuration_blocks_before_route_writes(self):
        client = FakePostingClient()
        store = FakePostingStore()
        client.configured_adset = mock.Mock(
            return_value={
                "id": "adset-1",
                "configured_status": "PAUSED",
                "ad_set_goal": {"type": "NEW_CUSTOMER"},
            }
        )
        with self.assertRaises(PostingAmbiguousError) as caught:
            MetaPostingService(
                client=client, store=store
            ).create_paused_campaign(request_for())

        self.assertIn("Get conversions from all audiences", str(caught.exception))
        self.assertEqual(client.campaign_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["status"], "PAUSED")
        self.assertNotIn("ad_image", client.calls)
        self.assertNotIn("page_photo", client.calls)
        self.assertEqual(
            store.record["requested_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertEqual(
            store.record["verified_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS,
        )
        self.assertTrue(store.record["lifecycle_verification_source"])

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
        self.assertEqual(
            result["requested_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertEqual(
            result["verified_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertIn("Meta Graph", result["lifecycle_verification_source"])
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
                "template_copy", "rename_ad",
            ][2:] * 3,
        )
        self.assertEqual(client.campaign_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["status"], "PAUSED")
        self.assertEqual(client.adset_payload["promoted_object"]["pixel_id"], "pixel-1")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls.count("template_copy"), 3)
        self.assertEqual(client.calls.count("creative"), 0)
        self.assertEqual(client.calls.count("ad"), 0)
        self.assertEqual(client.calls.count("canvas"), 3)
        self.assertEqual(len(client.uploaded_images), 3)
        self.assertEqual(
            [data for data, _filename, _content_type in client.uploaded_images],
            [creative.image_bytes for creative in request_for().creatives],
        )
        self.assertEqual(
            [payload["object_story_spec"]["link_data"]["message"] for payload in client.creative_payloads],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [payload["object_story_spec"]["link_data"]["name"] for payload in client.creative_payloads],
            ["Headline 1", "Headline 2", "Headline 3"],
        )
        self.assertTrue(
            all("description" not in payload["object_story_spec"]["link_data"] for payload in client.creative_payloads)
        )
        self.assertEqual(
            [payload["object_story_spec"]["link_data"]["image_hash"] for payload in client.creative_payloads],
            ["image-hash-1", "image-hash-2", "image-hash-3"],
        )
        self.assertEqual(
            [payload["image_hash"] for payload in client.creative_payloads],
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
            self.assertNotIn("template_data", story)
            link_data = story["link_data"]
            self.assertNotIn("picture", link_data)
            self.assertEqual(link_data["retailer_item_ids"], ["0", "0", "0", "0"])
            self.assertEqual(link_data["call_to_action"]["type"], "SHOP_NOW")
            self.assertEqual(
                payload["degrees_of_freedom_spec"]["creative_features_spec"],
                {
                    name: {"enroll_status": enrollment}
                    for name, enrollment in REQUIRED_COLLECTION_FEATURES.items()
                },
            )
            self.assertIn("utm_source=facebook", payload["url_tags"])
        self.assertTrue(
            all(row["adset_id"] == "adset-1" for row in client.copy_ads.values())
        )
        self.assertEqual(
            [name for _ad_id, name in client.rename_calls],
            [
                "Max Verstappen Victory IA 2",
                "Max Verstappen Victory IA 3",
                "Max Verstappen Victory IA 4",
            ],
        )
        self.assertEqual(
            [row["ad_name"] for row in result["ad_results"]],
            [
                "Max Verstappen Victory IA 2",
                "Max Verstappen Victory IA 3",
                "Max Verstappen Victory IA 4",
            ],
        )
        self.assertEqual(
            result["ad_results"][0]["product_set_health"]["status"], "NOT RUN"
        )
        self.assertEqual(client.calls.count("read_product_set_health"), 0)
        for index, row in enumerate(result["ad_results"], start=1):
            provenance = row["instant_experience_creation_provenance"]
            self.assertEqual(
                provenance["button_label"], "Claim Your Edition"
            )
            self.assertEqual(
                provenance["destination_url"],
                "https://sportscaveshop.com/products/max-verstappen-victory",
            )
            self.assertEqual(
                provenance["instant_experience_id"], f"canvas-{index}"
            )
            self.assertTrue(provenance["button_element_id"])
            self.assertTrue(provenance["footer_element_id"])
            self.assertTrue(provenance["request_fingerprint"])

    def test_success_path_removes_only_redundant_reads_and_reports_progress(self):
        client = FakePostingClient()
        store = FakePostingStore()
        progress = []
        ticks = iter(float(value) for value in range(20))

        result = MetaPostingService(
            client=client,
            store=store,
            progress_callback=progress.append,
            clock=lambda: next(ticks),
        ).create_paused_campaign(request_for())

        self.assertEqual(
            progress,
            [
                "Preparing Meta campaign…",
                "Creating campaign…",
                "Creating Ad Set…",
                "Creating Ad 1 of 3…",
                "Creating Ad 2 of 3…",
                "Creating Ad 3 of 3…",
                "Verifying paused Meta ads…",
                "Done — 3 Meta ads are PAUSED",
            ],
        )
        self.assertEqual(
            [row["stage"] for row in result["performance_trace"]],
            [
                "request_validation",
                "meta_reference_validation",
                "ledger_claim",
                "campaign_resolution",
                "adset_resolution",
                "route_1",
                "route_2",
                "route_3",
                "paused_status_verification",
                "final_persistence",
            ],
        )
        self.assertTrue(
            all(row["duration_ms"] == 1000.0 for row in result["performance_trace"])
        )
        self.assertEqual(client.calls.count("read_instant_experience"), 3)
        self.assertEqual(client.calls.count("read_ad"), 13)
        self.assertEqual(client.calls.count("read_creative"), 7)
        self.assertEqual(client.calls.count("read_product_set_health"), 0)
        self.assertEqual(store.claims, 1)
        self.assertEqual(len(store.stages), 28)
        self.assertEqual(store.claims + len(store.stages), 29)
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["message"]
                for payload in client.creative_payloads
            ],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [row["meta_ad_configured_status"] for row in result["ad_results"]],
            ["PAUSED", "PAUSED", "PAUSED"],
        )

    def test_future_new_adset_uses_selected_saved_custom_or_broad_audience(self):
        cases = (
            (
                "saved",
                "saved-1",
                lambda targeting: (
                    targeting.get("age_min") == 30
                    and "custom_audiences" not in targeting
                ),
            ),
            (
                "custom",
                "custom-1",
                lambda targeting: targeting.get("custom_audiences")
                == [{"id": "custom-1"}],
            ),
            (
                "broad",
                "",
                lambda targeting: (
                    targeting.get("age_min") == 24
                    and "custom_audiences" not in targeting
                ),
            ),
        )
        for audience_type, audience_id, assertion in cases:
            with self.subTest(audience_type=audience_type):
                client = FakePostingClient()
                MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                    request_for(
                        submission_id=str(__import__("uuid").uuid4()),
                        audience_type=audience_type,
                        audience_id=audience_id,
                    )
                )
                targeting = client.adset_payload["targeting"]
                self.assertTrue(assertion(targeting))
                self.assertEqual(targeting["geo_locations"], {"countries": ["AU"]})
                self.assertEqual(
                    targeting["targeting_automation"], {"advantage_audience": 1}
                )
                self.assertNotIn("ad_set_goal", client.adset_payload)
                self.assertNotIn(
                    "existing_customer_budget_percentage", client.adset_payload
                )

    def test_wrong_instant_experience_button_url_blocks_before_template_copy(self):
        client = FakePostingClient()
        original_read = client.instant_experience

        def wrong_destination(canvas_id):
            canvas = original_read(canvas_id)
            for row in canvas.get("body_elements") or ():
                element = row.get("element") or {}
                if element.get("open_url_action"):
                    element["open_url_action"]["url"] = (
                        "https://sportscaveshop.com/products/wrong-product"
                    )
            return canvas

        client.instant_experience = wrong_destination
        with self.assertRaisesRegex(PostingError, "fixed button verification mismatch"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for()
            )
        self.assertEqual(client.calls.count("template_copy"), 0)

    def test_optional_canvas_auth_error_still_blocks_posting(self):
        client = FakePostingClient()
        original_read = client.instant_experience

        def reference_only_readback(canvas_id):
            canvas = original_read(canvas_id)
            return {
                "id": canvas.get("id"),
                "name": canvas.get("name"),
                "is_published": canvas.get("is_published"),
                "body_elements": [
                    {"id": f"reference-{index}"} for index in range(1, 4)
                ],
            }

        client.instant_experience = reference_only_readback
        client.optional_canvas_details_error = meta_ads_client.MetaAdsApiError(
            "Invalid OAuth access token.",
            error_code=190,
        )

        with mock.patch(
            "meta_posting_service.build_instant_experience_creation_provenance",
            return_value={},
        ), self.assertRaisesRegex(PostingError, "Invalid OAuth access token"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_campaign(
                request_for()
            )

        self.assertEqual(client.calls.count("template_copy"), 0)

    def test_unknown_reused_instant_experience_without_provenance_blocks(self):
        request = request_for()
        clean = validate_posting_request(request)
        ad_results = posting_ad_results(
            (),
            ad_names=(
                "Max Verstappen Victory IA 1",
                "Max Verstappen Victory IA 2",
                "Max Verstappen Victory IA 3",
            ),
        )
        ad_results[0]["meta_instant_experience_id"] = "external-canvas"
        existing = {
            "submission_id": request.submission_id,
            "request_fingerprint": _request_fingerprint(clean),
            "destination_url": clean["destination_url"],
            "status": "FAILED",
            "campaign_id": "campaign-existing",
            "campaign_name": "Existing campaign",
            "adset_id": "adset-existing",
            "adset_name": "Existing ad set",
            "ad_results": ad_results,
        }
        client = FakePostingClient()
        client.canvas_readbacks["external-canvas"] = {
            "id": "external-canvas",
            "body_elements": [{"id": "external-footer"}],
        }

        with self.assertRaisesRegex(PostingError, "verification unavailable"):
            MetaPostingService(
                client=client, store=FakePostingStore(existing=existing)
            ).create_paused_campaign(request)

        self.assertEqual(client.calls.count("template_copy"), 0)

    def test_optional_product_health_is_not_on_the_creation_critical_path(self):
        client = FakePostingClient()
        client.product_set_health = mock.Mock(
            return_value={
                "product_set": {
                    "id": "set-1",
                    "name": "Motor Racing Wall Art",
                    "product_count": 1,
                },
                "products": (
                    {
                        "id": "product-1",
                        "availability": "out of stock",
                        "status": "PUBLISHED",
                        "visibility": "published",
                        "review_status": "approved",
                    },
                ),
            }
        )
        result = MetaPostingService(
            client=client, store=FakePostingStore()
        ).create_paused_campaign(request_for())
        health = result["ad_results"][0]["product_set_health"]
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(health["status"], "NOT RUN")
        self.assertTrue(health["read_only"])
        client.product_set_health.assert_not_called()

    def test_optional_product_health_code_three_cannot_delay_creation(self):
        client = FakePostingClient()
        client.product_set_health = mock.Mock(
            side_effect=meta_ads_client.MetaAdsApiError(
                "Application does not have the capability to make this API call.",
                status_code=400,
                error_code=3,
            )
        )
        result = MetaPostingService(
            client=client, store=FakePostingStore()
        ).create_paused_campaign(request_for())
        health = result["ad_results"][0]["product_set_health"]
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(health["status"], "NOT RUN")
        self.assertTrue(health["read_only"])
        client.product_set_health.assert_not_called()

    def test_optional_product_health_non_capability_error_is_not_hidden_by_creation(self):
        client = FakePostingClient()
        client.product_set_health = mock.Mock(
            side_effect=meta_ads_client.MetaAdsApiError(
                "Catalogue access was denied.", status_code=403, error_code=200
            )
        )
        result = MetaPostingService(
            client=client, store=FakePostingStore()
        ).create_paused_campaign(request_for())
        health = result["ad_results"][0]["product_set_health"]
        self.assertEqual(health["status"], "NOT RUN")
        client.product_set_health.assert_not_called()

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

    def test_paused_copy_with_pending_name_verification_is_preserved_for_retry(self):
        class PendingNameVerificationService:
            def create_or_reconcile_paused_route_copy(self, **_kwargs):
                raise MetaCollectionTemplateCopyVerificationError(
                    "Meta created or returned a PAUSED template copy, but read-back "
                    "verification failed. Further copies are blocked. Failed checks: "
                    "route_ad_name.",
                    result={
                        "copied_ad_id": "created-but-stale-ad",
                        "copied_creative_id": "created-but-stale-creative",
                        "copied_status": "PAUSED",
                        "copied_configured_status": "PAUSED",
                        "reconciled_existing_copy": False,
                        "failed_checks": ["route_ad_name"],
                    },
                )

        store = FakePostingStore()
        with self.assertRaises(PostingError) as caught:
            MetaPostingService(
                client=FakePostingClient(),
                store=store,
                template_copy_service=PendingNameVerificationService(),
            ).create_paused_campaign(request_for())

        route_one = caught.exception.result["ad_results"][0]
        self.assertEqual(route_one["meta_ad_id"], "created-but-stale-ad")
        self.assertEqual(
            route_one["meta_creative_id"], "created-but-stale-creative"
        )
        self.assertEqual(route_one["meta_ad_configured_status"], "PAUSED")
        self.assertEqual(route_one["status"], "VERIFICATION_PENDING")
        self.assertEqual(store.record["status"], "FAILED")

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
        self.assertEqual(
            completed["requested_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertEqual(
            completed["verified_lifecycle_strategy"],
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls[len(calls_before_retry):].count("template_copy"), 1)
        self.assertEqual(client.calls[len(calls_before_retry):].count("canvas"), 0)
        self.assertEqual(
            [row["meta_ad_id"] for row in completed["ad_results"]],
            ["ad-1", "ad-2", "ad-3"],
        )

    def test_new_submission_id_does_not_resume_partial_campaign_and_adset(self):
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
        self.assertEqual(
            result["submission_id"], "33333333-3333-4333-8333-333333333333"
        )
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["adset_id"], "adset-1")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls.count("template_copy"), 3)

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
        product_url = (
            "https://sportscaveshop.com/products/"
            "six-laps-ahead-peter-brock-wall-art"
        )
        retry_request = request_for(
            submission_id=original_submission_id,
            product_title="Six Laps Ahead Peter Brock Wall Art",
            product_handle="six-laps-ahead-peter-brock-wall-art",
            destination_url=product_url,
        )
        existing["destination_url"] = product_url
        existing["request_fingerprint"] = _request_fingerprint(
            validate_posting_request(retry_request)
        )
        client.canvas_readbacks["1390026833255926"] = {
            "id": "1390026833255926",
            "name": "Six Laps Ahead Peter Brock IA 1 | Storefront",
            "is_published": True,
            "body_elements": [
                {"id": "existing-photo-element"},
                {"id": "existing-product-element"},
                {"id": "existing-footer-element"},
            ],
        }
        client.optional_canvas_details_error = meta_ads_client.MetaAdsApiError(
            "Application does not have the capability to make this API call.",
            error_code=3,
        )
        client.instant_experience_elements_error = meta_ads_client.MetaAdsApiError(
            "Application does not have the capability to make this API call.",
            error_code=3,
        )
        existing_route_one_creative = build_collection_creative_payload(
            name="Six Laps Ahead Peter Brock IA 1 | Collection",
            page_id=client.page_id,
            instagram_user_id=client.instagram_user_id,
            image_hash="existing-image-hash",
            canvas_id="1390026833255926",
            product_set_id="set-1",
            destination_url=product_url,
            primary_text="Primary 1",
            headline="Headline 1",
        )
        existing_route_one_creative["degrees_of_freedom_spec"][
            "creative_features_spec"
        ]["meta_generated_extra"] = {"enroll_status": "OPT_OUT"}
        client.copy_creatives["1092729016821293"] = {
            "id": "1092729016821293",
            **existing_route_one_creative,
        }
        client.copy_ads["120249733966310554"] = {
            "id": "120249733966310554",
            "name": "LEGENDS IA 2 – Copy",
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "IN_PROCESS",
            "adset_id": "120249720389890554",
            "source_ad_id": "120249557468150554",
            "creative": {"id": "1092729016821293"},
        }
        source_before = dict(client.template_source_ad)
        result = MetaPostingService(
            client=client,
            store=FakePostingStore(existing=existing),
        ).create_paused_campaign(retry_request)

        self.assertEqual(result["submission_id"], original_submission_id)
        self.assertEqual(result["campaign_id"], "120249720387120554")
        self.assertEqual(result["adset_id"], "120249720389890554")
        self.assertEqual(
            result["ad_results"][0]["meta_instant_experience_id"],
            "1390026833255926",
        )
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertIsNone(client.adset_payload)
        self.assertEqual(client.calls.count("canvas"), 2)
        self.assertEqual(client.calls.count("template_copy"), 2)
        self.assertEqual(client.calls.count("ad_image"), 2)
        self.assertEqual(client.calls.count("page_photo"), 2)
        first_creative = client.copy_creatives["1092729016821293"]
        self.assertEqual(first_creative["image_hash"], "existing-image-hash")
        self.assertEqual(
            first_creative["object_story_spec"]["link_data"]["image_hash"],
            "existing-image-hash",
        )
        self.assertEqual(
            first_creative["object_story_spec"]["link_data"]["link"],
            "https://fb.com/canvas_doc/1390026833255926",
        )
        self.assertEqual(
            [row["meta_instant_experience_id"] for row in result["ad_results"]],
            ["1390026833255926", "canvas-1", "canvas-2"],
        )
        self.assertEqual(
            [row["meta_ad_id"] for row in result["ad_results"]],
            ["120249733966310554", "ad-2", "ad-3"],
        )
        self.assertEqual(
            result["ad_results"][0]["meta_creative_id"], "1092729016821293"
        )
        self.assertTrue(result["ad_results"][0]["meta_ad_reused"])
        self.assertTrue(result["ad_results"][0]["meta_instant_experience_reused"])
        self.assertNotIn("read_instant_experience_optional_details", client.calls)
        self.assertNotIn("read_instant_experience_elements", client.calls)
        self.assertEqual(
            result["ad_results"][0]["instant_experience_verification"][
                "display_status"
            ],
            "VERIFIED VIA CREATION RECORD",
        )
        self.assertEqual(
            result["ad_results"][0]["instant_experience_verification"][
                "verification_source"
            ],
            "Persisted creation provenance",
        )
        self.assertEqual(
            [row["meta_ad_configured_status"] for row in result["ad_results"]],
            ["PAUSED", "PAUSED", "PAUSED"],
        )
        self.assertEqual(
            [row["ad_name"] for row in result["ad_results"]],
            [
                "Six Laps Ahead Peter Brock IA 1",
                "Six Laps Ahead Peter Brock IA 2",
                "Six Laps Ahead Peter Brock IA 3",
            ],
        )
        self.assertEqual(
            client.copy_ads["120249733966310554"]["name"],
            "Six Laps Ahead Peter Brock IA 1",
        )
        self.assertNotIn("LEGENDS", " ".join(row["ad_name"] for row in result["ad_results"]))
        self.assertNotIn("Copy", " ".join(row["ad_name"] for row in result["ad_results"]))
        self.assertEqual(client.template_source_ad, source_before)
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["link"]
                for payload in client.creative_payloads[-2:]
            ],
            ["https://fb.com/canvas_doc/canvas-1", "https://fb.com/canvas_doc/canvas-2"],
        )
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["message"]
                for payload in client.creative_payloads[-2:]
            ],
            ["Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [
                payload["object_story_spec"]["link_data"]["name"]
                for payload in client.creative_payloads[-2:]
            ],
            ["Headline 2", "Headline 3"],
        )

    def test_retry_reconciles_existing_route_two_after_stale_name_readback(self):
        original_submission_id = "22222222-2222-4222-8222-222222222222"
        campaign_id = "120249745234420554"
        adset_id = "120249745234830554"
        ia_ids = ("4648209915398007", "1023273974081022")
        ad_ids = ("120249745246230554", "120249745250000554")
        image_hashes = ("existing-route-1-hash", "existing-route-2-hash")
        product_url = (
            "https://sportscaveshop.com/products/"
            "six-laps-ahead-peter-brock-wall-art"
        )
        retry_request = request_for(
            submission_id=original_submission_id,
            product_title="Six Laps Ahead Peter Brock Wall Art",
            product_handle="six-laps-ahead-peter-brock-wall-art",
            destination_url=product_url,
        )
        fingerprint = _request_fingerprint(validate_posting_request(retry_request))
        ad_results = posting_ad_results(
            (),
            ad_names=(
                "Six Laps Ahead Peter Brock IA 1",
                "Six Laps Ahead Peter Brock IA 2",
                "Six Laps Ahead Peter Brock IA 3",
            ),
        )
        for index in range(2):
            route = index + 1
            ad_results[index].update(
                {
                    "meta_image_hash": image_hashes[index],
                    "meta_page_photo_id": f"existing-page-photo-{route}",
                    "meta_canvas_photo_element_id": f"existing-photo-element-{route}",
                    "meta_canvas_product_element_id": f"existing-product-element-{route}",
                    "meta_canvas_button_element_id": f"existing-button-element-{route}",
                    "meta_canvas_footer_element_id": f"existing-footer-element-{route}",
                    "meta_instant_experience_id": ia_ids[index],
                    "meta_ad_id": ad_ids[index] if index == 0 else "",
                    "meta_creative_id": f"existing-creative-{route}" if index == 0 else "",
                    "meta_ad_configured_status": "PAUSED" if index == 0 else "",
                    "status": "CREATED" if index == 0 else "VERIFICATION_PENDING",
                }
            )
        existing = {
            "submission_id": original_submission_id,
            "status": "FAILED",
            "campaign_id": campaign_id,
            "campaign_name": "030926 AUS Motorsport Six Laps Ahead Peter Brock",
            "adset_id": adset_id,
            "adset_name": "AUS Motorsport Motor Racing Classic Cars Men 35-65+ 110326",
            "ad_name": "Six Laps Ahead Peter Brock IA 1",
            "destination_url": product_url,
            "request_fingerprint": fingerprint,
            "ad_results": ad_results,
        }
        client = FakePostingClient()
        for index in range(2):
            route = index + 1
            creative_id = f"existing-creative-{route}"
            creative_payload = build_collection_creative_payload(
                name=f"Six Laps Ahead Peter Brock IA {route} | Collection",
                page_id=client.page_id,
                instagram_user_id=client.instagram_user_id,
                image_hash=image_hashes[index],
                canvas_id=ia_ids[index],
                product_set_id="set-1",
                destination_url=product_url,
                primary_text=f"Primary {route}",
                headline=f"Headline {route}",
            )
            client.copy_creatives[creative_id] = {
                "id": creative_id,
                **creative_payload,
            }
            client.copy_ads[ad_ids[index]] = {
                "id": ad_ids[index],
                "name": f"Six Laps Ahead Peter Brock IA {route}",
                "status": "PAUSED",
                "configured_status": "PAUSED",
                "effective_status": "IN_PROCESS",
                "adset_id": adset_id,
                "source_ad_id": "120249557468150554",
                "creative": {"id": creative_id},
            }
            client.canvas_readbacks[ia_ids[index]] = {
                "id": ia_ids[index],
                "name": f"Six Laps Ahead Peter Brock IA {route} | Storefront",
                "is_published": True,
                "body_elements": [
                    {"id": f"existing-photo-element-{route}"},
                    {"id": f"existing-product-element-{route}"},
                    {"id": f"existing-footer-element-{route}"},
                ],
            }

        source_before = dict(client.template_source_ad)
        result = MetaPostingService(
            client=client,
            store=FakePostingStore(existing=existing),
        ).create_paused_campaign(retry_request)

        self.assertEqual(result["submission_id"], original_submission_id)
        self.assertEqual(result["campaign_id"], campaign_id)
        self.assertEqual(result["adset_id"], adset_id)
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("ad_image"), 1)
        self.assertEqual(client.calls.count("page_photo"), 1)
        self.assertEqual(client.calls.count("canvas"), 1)
        self.assertEqual(client.calls.count("template_copy"), 1)
        self.assertEqual(
            [row["meta_instant_experience_id"] for row in result["ad_results"]],
            [ia_ids[0], ia_ids[1], "canvas-1"],
        )
        self.assertEqual(
            [row["meta_ad_id"] for row in result["ad_results"]],
            [ad_ids[0], ad_ids[1], "ad-3"],
        )
        self.assertEqual(len(client.copy_ads), 3)
        self.assertIn(ad_ids[1], client.copy_ads)
        self.assertEqual(
            {row["status"] for row in client.copy_ads.values()}, {"PAUSED"}
        )
        self.assertEqual(
            {row["configured_status"] for row in client.copy_ads.values()},
            {"PAUSED"},
        )
        self.assertEqual(
            [row["meta_ad_configured_status"] for row in result["ad_results"]],
            ["PAUSED", "PAUSED", "PAUSED"],
        )
        self.assertEqual(
            [row["ad_name"] for row in result["ad_results"]],
            [
                "Six Laps Ahead Peter Brock IA 1",
                "Six Laps Ahead Peter Brock IA 2",
                "Six Laps Ahead Peter Brock IA 3",
            ],
        )
        self.assertEqual(client.rename_calls, [("ad-3", "Six Laps Ahead Peter Brock IA 3")])
        self.assertEqual(client.template_source_ad, source_before)

    def test_store_claim_uses_exact_run_id_and_never_queries_fingerprint_history(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        inserted = {
            "submission_id": "33333333-3333-4333-8333-333333333333",
            "request_fingerprint": "same-fingerprint",
            "status": "VALIDATING",
        }
        claimed_row = {**inserted, "status": "VALIDATING"}
        cursor.fetchone.side_effect = [inserted, claimed_row]
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
        self.assertEqual(
            claim["record"]["submission_id"],
            "33333333-3333-4333-8333-333333333333",
        )
        statements = [str(call.args[0]) for call in cursor.execute.call_args_list]
        self.assertTrue(any("INSERT INTO meta_posting_submissions" in statement for statement in statements))
        self.assertFalse(any("WHERE request_fingerprint" in statement for statement in statements))

    def test_identical_request_content_in_two_runs_creates_two_complete_hierarchies(self):
        client = FakePostingClient()
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        source_before = dict(client.template_source_ad)

        first_request = request_for(
            submission_id="22222222-2222-4222-8222-222222222222"
        )
        second_request = request_for(
            submission_id="33333333-3333-4333-8333-333333333333"
        )
        self.assertEqual(
            _request_fingerprint(validate_posting_request(first_request)),
            _request_fingerprint(validate_posting_request(second_request)),
        )

        first = service.create_paused_campaign(first_request)
        second = service.create_paused_campaign(second_request)

        self.assertNotEqual(first["submission_id"], second["submission_id"])
        self.assertNotEqual(first["campaign_id"], second["campaign_id"])
        self.assertNotEqual(first["adset_id"], second["adset_id"])
        self.assertTrue(
            set(row["meta_instant_experience_id"] for row in first["ad_results"])
            .isdisjoint(
                row["meta_instant_experience_id"] for row in second["ad_results"]
            )
        )
        self.assertTrue(
            set(row["meta_ad_id"] for row in first["ad_results"]).isdisjoint(
                row["meta_ad_id"] for row in second["ad_results"]
            )
        )
        self.assertEqual(client.calls.count("campaign"), 2)
        self.assertEqual(client.calls.count("adset"), 2)
        self.assertEqual(client.calls.count("canvas"), 6)
        self.assertEqual(client.calls.count("template_copy"), 6)
        self.assertEqual(
            {row["status"] for row in client.copy_ads.values()}, {"PAUSED"}
        )
        self.assertEqual(client.template_source_ad, source_before)

    def test_missing_campaign_abandons_same_run_without_meta_writes(self):
        request = request_for()
        existing = {
            "submission_id": request.submission_id,
            "request_fingerprint": _request_fingerprint(
                validate_posting_request(request)
            ),
            "status": "FAILED",
            "campaign_id": "deleted-campaign",
            "campaign_name": "Old campaign",
            "adset_id": "old-adset",
            "adset_name": "Old ad set",
            "ad_results": posting_ad_results(()),
        }
        client = FakePostingClient()
        client.configured_campaign = mock.Mock(
            side_effect=meta_ads_client.MetaAdsApiError(
                "Unsupported get request. Object with ID does not exist or is inaccessible.",
                error_code=100,
            )
        )
        store = FakePostingStore(existing=existing)

        with self.assertRaises(PostingAbandonedError) as caught:
            MetaPostingService(client=client, store=store).create_paused_campaign(
                request
            )

        self.assertEqual(str(caught.exception), EXTERNALLY_ABANDONED_MESSAGE)
        self.assertEqual(store.record["status"], "ABANDONED_EXTERNALLY")
        self.assertEqual(store.record["campaign_id"], "deleted-campaign")
        self.assertEqual(store.record["adset_id"], "old-adset")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("template_copy"), 0)

    def test_new_run_after_external_abandonment_creates_fresh_campaign(self):
        abandoned = {
            "submission_id": "22222222-2222-4222-8222-222222222222",
            "request_fingerprint": "same-content",
            "status": "ABANDONED_EXTERNALLY",
            "campaign_id": "deleted-campaign",
            "adset_id": "old-adset",
            "ad_results": posting_ad_results(()),
        }
        client = FakePostingClient()
        result = MetaPostingService(
            client=client,
            store=FakePostingStore(existing=abandoned),
        ).create_paused_campaign(
            request_for(submission_id="33333333-3333-4333-8333-333333333333")
        )
        self.assertEqual(
            result["submission_id"], "33333333-3333-4333-8333-333333333333"
        )
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["adset_id"], "adset-1")
        self.assertNotEqual(result["campaign_id"], abandoned["campaign_id"])
        self.assertNotEqual(result["adset_id"], abandoned["adset_id"])

    def test_auth_error_reading_persisted_campaign_is_not_classified_as_missing(self):
        error = meta_ads_client.MetaAdsApiError(
            "Invalid OAuth access token.", error_code=190
        )
        self.assertFalse(is_meta_object_missing_or_inaccessible(error))

    def test_campaign_ambiguous_response_never_reuses_an_old_same_name_campaign(self):
        client = FakePostingClient()
        client.create_campaign = mock.Mock(
            side_effect=meta_ads_client.MetaAdsAmbiguousResultError(
                "Campaign request timed out after dispatch."
            )
        )
        client.find_campaigns_by_name = mock.Mock(
            side_effect=AssertionError("campaign names are labels, not run identity")
        )
        store = FakePostingStore()
        with self.assertRaises(PostingAmbiguousError):
            MetaPostingService(client=client, store=store).create_paused_campaign(
                request_for()
            )
        client.find_campaigns_by_name.assert_not_called()
        self.assertEqual(store.record["status"], "AMBIGUOUS")

    def test_three_name_sequence_advances_as_one_batch(self):
        self.assertEqual(
            next_instant_experience_ad_names(
                "Legends Sports Wall Art",
                ("Legends IA 1", "Legends IA 2", "Legends IA 3"),
            ),
            ("Legends IA 4", "Legends IA 5", "Legends IA 6"),
        )

    def test_complete_result_for_exact_same_run_is_returned_without_writes(self):
        request = request_for()
        existing = {
            "submission_id": request.submission_id,
            "request_fingerprint": _request_fingerprint(
                validate_posting_request(request)
            ),
            "status": "COMPLETE",
            "meta_ad_id": "existing-ad",
        }
        client = FakePostingClient()
        store = FakePostingStore(existing=existing)
        result = MetaPostingService(client=client, store=store).create_paused_campaign(request)
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

    def test_run_identity_migration_is_additive_and_keeps_history(self):
        migration_name = "20260903_meta_posting_run_identity.sql"
        source = (ROOT / "migrations" / migration_name).read_text(
            encoding="utf-8"
        )
        self.assertIn("ABANDONED_EXTERNALLY", source)
        self.assertIn("submission_id", source)
        self.assertIn("request_fingerprint", source)
        self.assertIn("posting_mode", source)
        self.assertIn("campaign_ownership", source)
        self.assertIn("adset_ownership", source)
        self.assertIn("EXISTING_TARGET", source)
        self.assertIn("CREATED_BY_RUN", source)
        self.assertNotIn("DELETE FROM", source.upper())
        self.assertNotIn("DROP TABLE", source.upper())
        self.assertNotIn("UPDATE META_POSTING_SUBMISSIONS", source.upper())
        self.assertIn(
            f'BASE_DIR / "migrations" / "{migration_name}"',
            (ROOT / "supabase_backend.py").read_text(encoding="utf-8"),
        )

    def test_customer_lifecycle_migration_is_additive_and_sanitized(self):
        migration_name = "20260903_meta_posting_customer_lifecycle.sql"
        source = (ROOT / "migrations" / migration_name).read_text(
            encoding="utf-8"
        )
        for field in (
            "requested_lifecycle_strategy",
            "verified_lifecycle_strategy",
            "lifecycle_verification_source",
            "ALL_AUDIENCES",
            "ACQUIRE_NEW_CUSTOMERS",
            "UNKNOWN",
        ):
            self.assertIn(field, source)
        self.assertNotIn("DELETE FROM", source.upper())
        self.assertNotIn("DROP TABLE", source.upper())
        self.assertNotIn("UPDATE META_POSTING_SUBMISSIONS", source.upper())
        self.assertIn(
            f'BASE_DIR / "migrations" / "{migration_name}"',
            (ROOT / "supabase_backend.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
