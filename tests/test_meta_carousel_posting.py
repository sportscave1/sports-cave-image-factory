import json
import unittest
from unittest import mock

import ads_posting_page
import meta_ads_client
from meta_carousel_diagnostics import (
    MANUAL_CAROUSEL_AD_ID,
    MANUAL_CAROUSEL_ADSET_ID,
    MANUAL_CAROUSEL_CAMPAIGN_ID,
    MANUAL_CAROUSEL_CREATIVE_ID,
    MetaCarouselDiagnosticSafetyError,
    MetaCarouselValidateOnlyProbe,
    assert_validate_only_transport,
    build_inline_ad_validate_only_payload,
    build_standalone_validate_only_payload,
    validate_manual_carousel_reference_contract,
)
from meta_posting_service import (
    AD_TYPE,
    CAROUSEL_AD_TYPE,
    CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
    META_OBJECT_CREATED_BY_RUN,
    META_OBJECT_EXISTING_TARGET,
    POSTING_MODE_EXISTING,
    POSTING_MODE_NEW,
    CarouselCard,
    MetaPostingService,
    PostingError,
    PostingRequest,
    PostingValidationError,
    _request_fingerprint,
    build_carousel_adset_payload,
    build_carousel_campaign_payload,
    build_carousel_creative_payload,
    carousel_ad_result,
    validate_carousel_posting_request,
    validate_existing_carousel_target,
    verify_carousel_creative_readback,
    verify_new_carousel_adset_readback,
)
from posting_import_csv import (
    build_carousel_posting_import_rows,
    parse_posting_import_csv,
    serialize_carousel_posting_import_csv,
)
from tests.test_meta_posting import FakePostingClient, FakePostingStore, image_bytes


def manual_reference_contract():
    cards = [
        {
            "link": "https://www.sportscaveshop.com/products/lap-of-gods",
            "name": f"Reference Card {index}",
            "description": f"Reference Description {index}",
            "image_hash": f"reference-hash-{index}",
            "call_to_action": {"type": "SHOP_NOW"},
        }
        for index in range(1, 6)
    ]
    return {
        "ad": {
            "id": MANUAL_CAROUSEL_AD_ID,
            "campaign_id": MANUAL_CAROUSEL_CAMPAIGN_ID,
            "adset_id": MANUAL_CAROUSEL_ADSET_ID,
            "creative": {"id": MANUAL_CAROUSEL_CREATIVE_ID},
        },
        "campaign": {
            "id": MANUAL_CAROUSEL_CAMPAIGN_ID,
            "objective": "OUTCOME_SALES",
            "buying_type": "AUCTION",
            "daily_budget": "2500",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "special_ad_categories": [],
        },
        "adset": {
            "id": MANUAL_CAROUSEL_ADSET_ID,
            "campaign_id": MANUAL_CAROUSEL_CAMPAIGN_ID,
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "billing_event": "IMPRESSIONS",
            "promoted_object": {
                "pixel_id": "pixel-1",
                "custom_event_type": "PURCHASE",
                "smart_pse_enabled": False,
            },
            "is_dynamic_creative": False,
        },
        "creative": {
            "id": MANUAL_CAROUSEL_CREATIVE_ID,
            "object_story_spec": {
                "page_id": "page-1",
                "instagram_user_id": "ig-1",
                "link_data": {
                    "link": "https://www.sportscaveshop.com/products/lap-of-gods",
                    "call_to_action": {"type": "SHOP_NOW"},
                    "child_attachments": cards,
                    "multi_share_end_card": True,
                    "multi_share_optimized": True,
                },
            },
            "asset_feed_spec": {
                "bodies": [{"text": f"Reference Primary {index}"} for index in range(1, 11)],
                "optimization_type": "DEGREES_OF_FREEDOM",
            },
            "contextual_multi_ads": {"enroll_status": "OPT_IN"},
            "degrees_of_freedom_spec": {
                "creative_features_spec": {
                    "carousel_to_video": {"enroll_status": "OPT_IN"},
                    "media_order": {"enroll_status": "OPT_IN"},
                }
            },
            # These are captured as Graph read-back evidence, not replayed by
            # the outbound builder unless creation acceptance is proven.
            "format_transformation_spec": [{"format": "manual_uploads"}],
            "portrait_customizations": {"carousel_delivery_mode": "optimal_num_cards"},
        },
    }


def carousel_request(**overrides):
    values = {
        "submission_id": "22222222-2222-4222-8222-222222222222",
        "product_id": "shopify-carousel",
        "product_title": "Lap of Gods Sports Wall Art",
        "product_handle": "lap-of-gods",
        "destination_url": "https://www.sportscaveshop.com/products/lap-of-gods",
        "country": "AUS",
        "sport": "Motorsport",
        "catalog_id": "",
        "product_set_id": "",
        "creatives": (),
        "audience_type": "broad",
        "audience_id": "",
        "customer_lifecycle_strategy": CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        "posting_mode": POSTING_MODE_NEW,
        "target_campaign_id": "",
        "target_adset_id": "",
        "ad_type": CAROUSEL_AD_TYPE,
        "carousel_cards": tuple(
            CarouselCard(
                image_bytes=image_bytes((20 * index, 30, 40)),
                image_name=f"mockup-{index}.jpg",
                headline=f"CARD HEADLINE {index}",
                description=f"CARD DESCRIPTION {index}",
            )
            for index in range(1, 6)
        ),
        "carousel_primary_texts": tuple(
            f"PRIMARY VARIATION {label}"
            for label in ("ONE", "TWO", "THREE", "FOUR", "FIVE")
        ),
    }
    values.update(overrides)
    return PostingRequest(**values)


class AcceptingCarouselValidator:
    def __init__(self, *, accepted=True, code=None, subcode=None):
        self.accepted = accepted
        self.code = code
        self.subcode = subcode
        self.calls = []

    def run(self, *, ad_name, adset_id, creative_payload):
        self.calls.append(
            {
                "ad_name": ad_name,
                "adset_id": adset_id,
                "creative_payload": creative_payload,
            }
        )
        result = {
            "validated": self.accepted,
            "persistent_meta_writes": "NONE",
            "standalone_creative": {"validated": self.accepted},
            "inline_ad": {"validated": self.accepted},
        }
        if not self.accepted:
            result["inline_ad"].update(
                {"error_code": self.code, "error_subcode": self.subcode}
            )
        return result


class FakeCarouselClient(FakePostingClient):
    def __init__(self, *, existing=False, fail_first_ad=False, product_set_target=False):
        super().__init__()
        self.config = {
            "configured": True,
            "ad_account_id": self.ad_account_id,
            "page_id": self.page_id,
            "instagram_user_id": self.instagram_user_id,
            "access_token": "test-token",
        }
        self.carousel_creatives = {}
        self.carousel_ads = {}
        self.fail_first_ad = fail_first_ad
        self.failed_ad_once = False
        self.forbidden_calls = []
        self.product_set_target = product_set_target
        self.existing = existing

    def carousel_reference_data(self):
        return {
            "account": {"id": self.ad_account_id, "currency": "AUD"},
            "page": {"id": self.page_id, "name": "Sports Cave"},
            "instagram": {"id": self.instagram_user_id, "username": "sportscave"},
            "pixels": ({"id": "pixel-1", "name": "Shprts Cave Pixel 2025"},),
            "saved_audiences": (),
            "custom_audiences": (),
        }

    def carousel_reference_contract(self):
        return manual_reference_contract()

    def configured_campaign(self, campaign_id):
        self.calls.append("read_configured_campaign")
        status = "ACTIVE" if str(campaign_id) == "existing-campaign" else "PAUSED"
        return {
            "id": str(campaign_id),
            "name": "Existing Campaign" if status == "ACTIVE" else "New Campaign",
            "account_id": "123",
            "objective": "OUTCOME_SALES",
            "status": status,
            "configured_status": status,
            "effective_status": status,
        }

    def configured_adset(self, adset_id):
        self.calls.append("read_configured_adset")
        existing = str(adset_id) == "existing-adset"
        promoted = {
            "pixel_id": "pixel-1",
            "custom_event_type": "PURCHASE",
            "smart_pse_enabled": False,
        }
        if existing and self.product_set_target:
            promoted["product_set_id"] = "existing-product-set"
        return {
            "id": str(adset_id),
            "name": "Existing Ad Set" if existing else "New Ad Set",
            "campaign_id": (
                "existing-campaign"
                if existing
                else str((self.adset_payload or {}).get("campaign_id") or "campaign-1")
            ),
            "account_id": "123",
            "status": "ACTIVE" if existing else "PAUSED",
            "configured_status": "ACTIVE" if existing else "PAUSED",
            "effective_status": "ACTIVE" if existing else "PAUSED",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "billing_event": "IMPRESSIONS",
            "destination_type": "WEBSITE",
            "promoted_object": promoted,
            "targeting": {"geo_locations": {"countries": ["AU"]}},
            "ad_set_goal": None,
            "existing_customer_budget_percentage": None,
            "is_dynamic_creative": False,
        }

    def create_carousel_creative(self, payload):
        self.calls.append("carousel_creative")
        creative_id = f"carousel-creative-{len(self.carousel_creatives) + 1}"
        self.carousel_creatives[creative_id] = {"id": creative_id, **dict(payload)}
        return creative_id

    def carousel_creative(self, creative_id):
        self.calls.append("read_carousel_creative")
        return dict(self.carousel_creatives[str(creative_id)])

    def find_creative_by_name(self, name):
        for creative in self.carousel_creatives.values():
            if creative.get("name") == name:
                return dict(creative)
        return None

    def create_paused_ad(self, *, ad_name, adset_id, creative_id):
        self.calls.append("carousel_ad")
        if self.fail_first_ad and not self.failed_ad_once:
            self.failed_ad_once = True
            raise meta_ads_client.MetaAdsApiError("temporary ad failure")
        ad_id = f"carousel-ad-{len(self.carousel_ads) + 1}"
        self.carousel_ads[ad_id] = {
            "id": ad_id,
            "name": ad_name,
            "adset_id": str(adset_id),
            "creative": {"id": str(creative_id)},
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "IN_PROCESS",
        }
        return ad_id

    def find_ad_by_creative(self, adset_id, creative_id):
        for ad in self.carousel_ads.values():
            if (
                str(ad.get("adset_id")) == str(adset_id)
                and str((ad.get("creative") or {}).get("id")) == str(creative_id)
            ):
                return dict(ad)
        return None

    def ad(self, ad_id):
        self.calls.append("read_ad")
        return dict(self.carousel_ads.get(str(ad_id)) or {})

    def product_sets(self, catalog_id):
        self.forbidden_calls.append("product_sets")
        raise AssertionError("Carousel must not read Product Sets")

    def upload_page_photo(self, *args, **kwargs):
        self.forbidden_calls.append("page_photo")
        raise AssertionError("Carousel must not upload a Page photo")

    def create_canvas_element(self, *args, **kwargs):
        self.forbidden_calls.append("canvas_element")
        raise AssertionError("Carousel must not create Canvas elements")

    def create_canvas(self, *args, **kwargs):
        self.forbidden_calls.append("canvas")
        raise AssertionError("Carousel must not create a Canvas")

    def copy_paused_ad_from_template(self, *args, **kwargs):
        self.forbidden_calls.append("template_copy")
        raise AssertionError("Carousel must not copy the Collection template")


class CarouselContractTests(unittest.TestCase):
    def test_default_ad_type_remains_instant_experience(self):
        request = PostingRequest(
            submission_id="11111111-1111-4111-8111-111111111111",
            product_id="",
            product_title="",
            product_handle="",
            destination_url="",
            country="",
            sport="",
            catalog_id="",
            product_set_id="",
            creatives=(),
        )
        self.assertEqual(request.ad_type, AD_TYPE)
        state = {}
        ads_posting_page._ensure_posting_run(state)
        self.assertEqual(state[ads_posting_page.AD_TYPE_KEY], AD_TYPE)

    def test_manual_reference_contract_is_exact_and_product_set_free(self):
        evidence = validate_manual_carousel_reference_contract(
            manual_reference_contract(),
            expected_page_id="page-1",
            expected_instagram_user_id="ig-1",
        )
        self.assertTrue(evidence["validated"])
        self.assertEqual(evidence["card_count"], 5)
        self.assertFalse(evidence["has_product_set"])
        changed = manual_reference_contract()
        changed["adset"]["promoted_object"]["product_set_id"] = "set-1"
        with self.assertRaisesRegex(
            MetaCarouselDiagnosticSafetyError, "adset_product_set_absence"
        ):
            validate_manual_carousel_reference_contract(changed)
        with self.assertRaisesRegex(
            MetaCarouselDiagnosticSafetyError,
            "creative_configured_page_identity",
        ):
            validate_manual_carousel_reference_contract(
                manual_reference_contract(), expected_page_id="other-page"
            )

    def test_new_carousel_adset_readback_requires_paused_non_catalogue_contract(self):
        adset = FakeCarouselClient().configured_adset("adset-1")
        verification = verify_new_carousel_adset_readback(
            adset,
            expected_adset_id="adset-1",
            expected_campaign_id="campaign-1",
            expected_pixel_id="pixel-1",
        )
        self.assertTrue(verification["verified"])
        adset["promoted_object"]["product_set_id"] = "catalogue-set"
        verification = verify_new_carousel_adset_readback(
            adset,
            expected_adset_id="adset-1",
            expected_campaign_id="campaign-1",
            expected_pixel_id="pixel-1",
        )
        self.assertFalse(verification["verified"])
        self.assertIn("no_product_set", verification["failed_checks"])

    def test_validate_only_payloads_and_transport_are_fail_closed(self):
        creative = {"name": "Carousel", "object_story_spec": {}}
        standalone = build_standalone_validate_only_payload(creative)
        inline = build_inline_ad_validate_only_payload(
            ad_name="Carousel", adset_id="adset-1", creative_payload=creative
        )
        self.assertEqual(standalone["execution_options"], ["validate_only"])
        self.assertEqual(inline["execution_options"], ["validate_only"])
        self.assertEqual(inline["status"], "PAUSED")
        self.assertNotIn("name", inline["creative"])
        assert_validate_only_transport("act_123/adcreatives", standalone)
        assert_validate_only_transport("act_123/ads", inline)
        with self.assertRaises(MetaCarouselDiagnosticSafetyError):
            assert_validate_only_transport("act_123/ads", {"status": "PAUSED"})
        with self.assertRaises(MetaCarouselDiagnosticSafetyError):
            assert_validate_only_transport(
                "act_123/ads",
                {"status": "ACTIVE", "execution_options": '["validate_only"]'},
            )

    @mock.patch("meta_carousel_diagnostics._post")
    def test_validate_only_probe_posts_only_two_nonpersistent_requests(self, post):
        post.side_effect = ({"success": True}, {"success": True})
        probe = MetaCarouselValidateOnlyProbe(
            {
                "configured": True,
                "ad_account_id": "act_123",
                "access_token": "secret",
            }
        )
        result = probe.run(
            ad_name="Carousel",
            adset_id="adset-1",
            creative_payload={"name": "Creative", "object_story_spec": {}},
        )
        self.assertTrue(result["validated"])
        self.assertEqual(result["persistent_meta_writes"], "NONE")
        self.assertEqual([call.args[0] for call in post.call_args_list], [
            "act_123/adcreatives",
            "act_123/ads",
        ])
        for call in post.call_args_list:
            self.assertEqual(
                json.loads(call.kwargs["data"]["execution_options"]),
                ["validate_only"],
            )

    def test_carousel_request_and_fingerprint_keep_all_five_variations(self):
        clean = validate_carousel_posting_request(carousel_request())
        self.assertEqual(clean["ad_type"], CAROUSEL_AD_TYPE)
        self.assertEqual(len(clean["carousel_cards"]), 5)
        self.assertEqual(
            clean["carousel_primary_texts"],
            (
                "PRIMARY VARIATION ONE",
                "PRIMARY VARIATION TWO",
                "PRIMARY VARIATION THREE",
                "PRIMARY VARIATION FOUR",
                "PRIMARY VARIATION FIVE",
            ),
        )
        original = _request_fingerprint(clean)
        request = carousel_request(
            carousel_primary_texts=(
                "PRIMARY VARIATION ONE",
                "PRIMARY VARIATION TWO CHANGED",
                "PRIMARY VARIATION THREE",
                "PRIMARY VARIATION FOUR",
                "PRIMARY VARIATION FIVE",
            )
        )
        self.assertNotEqual(original, _request_fingerprint(validate_carousel_posting_request(request)))

    def test_creative_payload_has_ordered_cards_and_independent_bodies(self):
        destination = "https://www.sportscaveshop.com/products/lap-of-gods"
        cards = tuple(
            {
                "image_hash": f"hash-{index}",
                "headline": f"Headline {index}",
                "description": f"Description {index}",
            }
            for index in range(1, 6)
        )
        texts = tuple(f"Primary {index}" for index in range(1, 6))
        payload = build_carousel_creative_payload(
            name="Lap of Gods Carousel 1",
            page_id="page-1",
            instagram_user_id="ig-1",
            cards=cards,
            primary_texts=texts,
            destination_url=destination,
        )
        children = payload["object_story_spec"]["link_data"]["child_attachments"]
        self.assertEqual([row["image_hash"] for row in children], [f"hash-{i}" for i in range(1, 6)])
        self.assertEqual([row["name"] for row in children], [f"Headline {i}" for i in range(1, 6)])
        self.assertEqual([row["description"] for row in children], [f"Description {i}" for i in range(1, 6)])
        self.assertEqual({row["link"] for row in children}, {destination})
        self.assertEqual({row["call_to_action"]["type"] for row in children}, {"SHOP_NOW"})
        self.assertTrue(payload["object_story_spec"]["link_data"]["multi_share_end_card"])
        self.assertTrue(payload["object_story_spec"]["link_data"]["multi_share_optimized"])
        self.assertEqual(payload["asset_feed_spec"]["bodies"], [{"text": value} for value in texts])
        self.assertEqual(payload["asset_feed_spec"]["optimization_type"], "DEGREES_OF_FREEDOM")
        self.assertNotIn("product_set_id", payload)
        self.assertNotIn("format_transformation_spec", payload)
        self.assertNotIn("portrait_customizations", payload)
        verification = verify_carousel_creative_readback(
            payload,
            page_id="page-1",
            instagram_user_id="ig-1",
            cards=cards,
            primary_texts=texts,
            destination_url=destination,
        )
        self.assertTrue(verification["verified"])

    def test_new_campaign_and_adset_payload_match_reference_without_catalogue(self):
        campaign = build_carousel_campaign_payload(name="Campaign")
        adset = build_carousel_adset_payload(
            name="Ad Set",
            campaign_id="campaign-1",
            pixel_id="pixel-1",
            targeting={"geo_locations": {"countries": ["AU"]}},
        )
        self.assertEqual(campaign["objective"], "OUTCOME_SALES")
        self.assertEqual(campaign["daily_budget"], "2500")
        self.assertEqual(campaign["status"], "PAUSED")
        self.assertNotIn("promoted_object", campaign)
        self.assertEqual(adset["optimization_goal"], "OFFSITE_CONVERSIONS")
        self.assertEqual(adset["billing_event"], "IMPRESSIONS")
        self.assertEqual(adset["promoted_object"], {
            "pixel_id": "pixel-1",
            "custom_event_type": "PURCHASE",
            "smart_pse_enabled": False,
        })
        self.assertFalse(adset["is_dynamic_creative"])
        self.assertNotIn("product_set_id", adset["promoted_object"])
        self.assertEqual(adset["status"], "PAUSED")


class CarouselMetaClientTests(unittest.TestCase):
    def client(self):
        return meta_ads_client.MetaPostingClient(
            {
                "configured": True,
                "ad_account_id": "act_123",
                "access_token": "secret",
                "api_version": "v26.0",
                "page_id": "page-1",
                "instagram_user_id": "ig-1",
            }
        )

    @mock.patch("meta_ads_client._post")
    def test_creative_write_serializes_only_supported_nested_fields(self, post):
        post.return_value = {"id": "creative-1"}
        payload = build_carousel_creative_payload(
            name="Carousel",
            page_id="page-1",
            instagram_user_id="ig-1",
            cards=tuple(
                {
                    "image_hash": f"hash-{index}",
                    "headline": f"Headline {index}",
                    "description": f"Description {index}",
                }
                for index in range(1, 6)
            ),
            primary_texts=tuple(f"Primary {index}" for index in range(1, 6)),
            destination_url="https://www.sportscaveshop.com/products/lap-of-gods",
        )
        self.assertEqual(self.client().create_carousel_creative(payload), "creative-1")
        self.assertEqual(post.call_args.args[0], "act_123/adcreatives")
        data = post.call_args.kwargs["data"]
        self.assertEqual(
            len(json.loads(data["object_story_spec"])["link_data"]["child_attachments"]),
            5,
        )
        self.assertEqual(len(json.loads(data["asset_feed_spec"])["bodies"]), 5)
        self.assertNotIn("product_set_id", data)

    @mock.patch("meta_ads_client._request")
    def test_carousel_adset_read_requests_dynamic_and_purchase_contract(self, request):
        request.return_value = {"id": "adset-1", "is_dynamic_creative": False}
        result = self.client().configured_carousel_adset("adset-1")
        self.assertFalse(result["is_dynamic_creative"])
        fields = request.call_args.kwargs["params"]["fields"]
        self.assertIn("promoted_object", fields)
        self.assertIn("is_dynamic_creative", fields)
        self.assertIn("configured_status", fields)

    @mock.patch("meta_ads_client._request")
    def test_manual_reference_read_is_get_only_and_optional_fields_are_isolated(self, request):
        contract = manual_reference_contract()

        def read(path, *, params, config):
            fields = params["fields"]
            if path == MANUAL_CAROUSEL_CREATIVE_ID:
                if fields == "id,format_transformation_spec":
                    return {
                        "id": path,
                        "format_transformation_spec": contract["creative"][
                            "format_transformation_spec"
                        ],
                    }
                if fields == "id,portrait_customizations":
                    return {
                        "id": path,
                        "portrait_customizations": contract["creative"][
                            "portrait_customizations"
                        ],
                    }
                return contract["creative"]
            if path == MANUAL_CAROUSEL_AD_ID:
                return contract["ad"]
            if path == MANUAL_CAROUSEL_CAMPAIGN_ID:
                return contract["campaign"]
            if path == MANUAL_CAROUSEL_ADSET_ID:
                return contract["adset"]
            raise AssertionError(path)

        request.side_effect = read
        result = self.client().carousel_reference_contract()
        self.assertTrue(validate_manual_carousel_reference_contract(result)["validated"])
        self.assertEqual(request.call_count, 6)
        self.assertTrue(all(call.args[0] in {
            MANUAL_CAROUSEL_AD_ID,
            MANUAL_CAROUSEL_CAMPAIGN_ID,
            MANUAL_CAROUSEL_ADSET_ID,
            MANUAL_CAROUSEL_CREATIVE_ID,
        } for call in request.call_args_list))

    @mock.patch("meta_ads_client._request")
    def test_unsupported_optional_reference_fields_do_not_hide_core_contract(self, request):
        contract = manual_reference_contract()

        def read(path, *, params, config):
            fields = params["fields"]
            if path == MANUAL_CAROUSEL_CREATIVE_ID:
                if fields in {
                    "id,format_transformation_spec",
                    "id,portrait_customizations",
                }:
                    raise meta_ads_client.MetaAdsApiError(
                        "Tried accessing nonexisting field",
                        error_code=100,
                    )
                return contract["creative"]
            return {
                MANUAL_CAROUSEL_AD_ID: contract["ad"],
                MANUAL_CAROUSEL_CAMPAIGN_ID: contract["campaign"],
                MANUAL_CAROUSEL_ADSET_ID: contract["adset"],
            }[path]

        request.side_effect = read
        result = self.client().carousel_reference_contract()
        evidence = validate_manual_carousel_reference_contract(result)
        self.assertTrue(evidence["validated"])
        self.assertEqual(
            set(evidence["normalized_readback"]["unavailable_fields"]),
            {"format_transformation_spec", "portrait_customizations"},
        )

    @mock.patch("meta_ads_client._request")
    def test_core_reference_auth_error_propagates(self, request):
        request.side_effect = meta_ads_client.MetaAdsApiError(
            "Invalid OAuth access token", error_code=190
        )
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            self.client().carousel_reference_contract()


class CarouselCsvAndUiTests(unittest.TestCase):
    def test_dedicated_csv_preserves_five_cards_and_primary_texts(self):
        rows = build_carousel_posting_import_rows(
            product_name="Lap of Gods",
            product_handle="lap-of-gods",
            product_url="https://www.sportscaveshop.com/products/lap-of-gods",
            country="AUS",
            sport_category="Motorsport",
            cards=tuple(
                {
                    "image_filename": f"mockup-{index}.jpg",
                    "headline": f"Headline {index}",
                    "description": f"Description {index}",
                    "primary_text": f"Primary {index}",
                }
                for index in range(1, 6)
            ),
        )
        batch = parse_posting_import_csv(
            serialize_carousel_posting_import_csv(rows),
            allowed_countries=("AUS",),
            allowed_sports=("Motorsport",),
            allowed_campaign_types=("Carousel",),
        )
        self.assertEqual(batch["source_schema_kind"], "carousel")
        self.assertEqual([card["image_filename"] for card in batch["cards"]], [f"mockup-{i}.jpg" for i in range(1, 6)])
        self.assertEqual(batch["primary_texts"], tuple(f"Primary {i}" for i in range(1, 6)))

    def test_ui_hydration_and_request_mapping_keep_five_ordered_slots(self):
        product = {
            "identity": "id::1",
            "label": "Lap of Gods",
            "row": {
                "product_title": "Lap of Gods",
                "product_handle": "lap-of-gods",
            },
        }
        batch = {
            "source_schema_kind": "carousel",
            "product_name": "Lap of Gods",
            "product_handle": "lap-of-gods",
            "product_url": "https://www.sportscaveshop.com/products/lap-of-gods",
            "country": "AUS",
            "sport_category": "Motorsport",
            "cards": tuple(
                {
                    "image_filename": f"mockup-{i}.jpg",
                    "headline": f"Headline {i}",
                    "description": f"Description {i}",
                }
                for i in range(1, 6)
            ),
            "primary_texts": tuple(f"Primary {i}" for i in range(1, 6)),
        }
        state = {}
        summary = ads_posting_page.apply_posting_import_to_state(
            batch, (product,), state=state
        )
        self.assertEqual(summary["cards_loaded"], 5)
        self.assertEqual(
            [state[key] for key in ads_posting_page.CAROUSEL_PRIMARY_TEXT_KEYS],
            [f"Primary {i}" for i in range(1, 6)],
        )
        cards = tuple(
            {
                "image": {"data": image_bytes((i * 20, 30, 40)), "name": f"mockup-{i}.jpg"},
                "headline": state[ads_posting_page.CAROUSEL_HEADLINE_KEYS[i - 1]],
                "description": state[ads_posting_page.CAROUSEL_DESCRIPTION_KEYS[i - 1]],
            }
            for i in range(1, 6)
        )
        request = ads_posting_page._build_posting_request(
            submission_id=state[ads_posting_page.SUBMISSION_ID_KEY],
            product_id="1",
            product_title="Lap of Gods",
            product_handle="lap-of-gods",
            product_url="https://www.sportscaveshop.com/products/lap-of-gods",
            country="AUS",
            sport="Motorsport",
            catalog_id="",
            product_set_id="",
            audience={"type": "broad", "id": ""},
            creatives=(),
            ad_type=CAROUSEL_AD_TYPE,
            carousel_cards=cards,
            carousel_primary_texts=tuple(
                state[key] for key in ads_posting_page.CAROUSEL_PRIMARY_TEXT_KEYS
            ),
        )
        self.assertEqual([card.headline for card in request.carousel_cards], [f"Headline {i}" for i in range(1, 6)])
        self.assertEqual(request.carousel_primary_texts, tuple(f"Primary {i}" for i in range(1, 6)))

    def test_carousel_readiness_requires_five_images_and_distinct_texts(self):
        values = {
            "product_title": "Lap of Gods",
            "product_url": "https://www.sportscaveshop.com/products/lap-of-gods",
            "cards": tuple(
                {
                    "image": {"data": b"image"},
                    "image_error": "",
                    "headline": f"Headline {i}",
                    "description": f"Description {i}",
                }
                for i in range(1, 6)
            ),
            "primary_texts": tuple(f"Primary {i}" for i in range(1, 6)),
            "country": "AUS",
            "sport": "Motorsport",
            "dataset_id": "pixel-1",
            "identities_ready": True,
        }
        self.assertTrue(ads_posting_page._carousel_form_ready(**values))
        values["cards"] = values["cards"][:4]
        self.assertFalse(ads_posting_page._carousel_form_ready(**values))
        values["cards"] = tuple(list(values["cards"]) + [{
            "image": {"data": b"image"}, "image_error": "", "headline": "Headline 5", "description": "Description 5"
        }])
        values["primary_texts"] = ("same",) * 5
        self.assertFalse(ads_posting_page._carousel_form_ready(**values))


class CarouselServiceTests(unittest.TestCase):
    def test_new_mode_creates_one_paused_carousel_and_no_instant_experience_work(self):
        client = FakeCarouselClient()
        store = FakePostingStore()
        validator = AcceptingCarouselValidator()
        result = MetaPostingService(
            client=client, store=store, carousel_validator=validator
        ).create_paused_campaign(carousel_request())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["ad_type"], CAROUSEL_AD_TYPE)
        self.assertEqual(result["campaign_ownership"], META_OBJECT_CREATED_BY_RUN)
        self.assertEqual(result["adset_ownership"], META_OBJECT_CREATED_BY_RUN)
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls.count("ad_image"), 5)
        self.assertEqual(client.calls.count("carousel_creative"), 1)
        self.assertEqual(client.calls.count("carousel_ad"), 1)
        self.assertEqual(client.forbidden_calls, [])
        self.assertEqual(len(validator.calls), 1)
        self.assertEqual(validator.calls[0]["adset_id"], MANUAL_CAROUSEL_ADSET_ID)
        ad_result = carousel_ad_result(result["ad_results"])
        self.assertEqual(ad_result["meta_ad_configured_status"], "PAUSED")
        self.assertEqual(ad_result["creative_ownership"], META_OBJECT_CREATED_BY_RUN)
        self.assertEqual(ad_result["ad_ownership"], META_OBJECT_CREATED_BY_RUN)
        self.assertTrue(ad_result["carousel_verification"]["verified"])
        self.assertNotIn("product_set_id", client.adset_payload["promoted_object"])

    def test_new_mode_validate_only_rejection_blocks_all_persistent_meta_writes(self):
        client = FakeCarouselClient()
        validator = AcceptingCarouselValidator(
            accepted=False, code=100, subcode=1885316
        )
        with self.assertRaisesRegex(
            PostingValidationError,
            "did not validate.*No persistent Meta objects were created",
        ):
            MetaPostingService(
                client=client,
                store=FakePostingStore(),
                carousel_validator=validator,
            ).create_paused_campaign(carousel_request())
        for write in ("campaign", "adset", "ad_image", "carousel_creative", "carousel_ad"):
            self.assertNotIn(write, client.calls)

    def test_existing_mode_preserves_active_parent_and_creates_only_one_paused_ad(self):
        client = FakeCarouselClient(existing=True)
        store = FakePostingStore()
        validator = AcceptingCarouselValidator()
        request = carousel_request(
            posting_mode=POSTING_MODE_EXISTING,
            target_campaign_id="existing-campaign",
            target_adset_id="existing-adset",
            audience_type="inherited",
            customer_lifecycle_strategy="",
        )
        result = MetaPostingService(
            client=client, store=store, carousel_validator=validator
        ).create_paused_campaign(request)
        self.assertEqual(result["campaign_id"], "existing-campaign")
        self.assertEqual(result["adset_id"], "existing-adset")
        self.assertEqual(result["campaign_ownership"], META_OBJECT_EXISTING_TARGET)
        self.assertEqual(result["adset_ownership"], META_OBJECT_EXISTING_TARGET)
        self.assertEqual(result["campaign_configured_status"], "ACTIVE")
        self.assertEqual(result["adset_configured_status"], "ACTIVE")
        self.assertEqual(client.calls.count("campaign"), 0)
        self.assertEqual(client.calls.count("adset"), 0)
        self.assertEqual(client.calls.count("carousel_ad"), 1)
        self.assertEqual(validator.calls[0]["adset_id"], "existing-adset")
        self.assertEqual(next(iter(client.carousel_ads.values()))["status"], "PAUSED")

    def test_product_set_adset_validate_only_rejection_blocks_before_meta_writes(self):
        client = FakeCarouselClient(existing=True, product_set_target=True)
        store = FakePostingStore()
        validator = AcceptingCarouselValidator(
            accepted=False, code=100, subcode=1885316
        )
        request = carousel_request(
            posting_mode=POSTING_MODE_EXISTING,
            target_campaign_id="existing-campaign",
            target_adset_id="existing-adset",
            audience_type="inherited",
            customer_lifecycle_strategy="",
        )
        with self.assertRaisesRegex(
            PostingValidationError,
            "not compatible with a standard Carousel.*Meta code 100, subcode 1885316",
        ):
            MetaPostingService(
                client=client, store=store, carousel_validator=validator
            ).create_paused_campaign(request)
        for write in ("campaign", "adset", "ad_image", "carousel_creative", "carousel_ad"):
            self.assertNotIn(write, client.calls)

    def test_product_set_adset_is_allowed_only_when_meta_validate_only_accepts(self):
        client = FakeCarouselClient(existing=True, product_set_target=True)
        request = carousel_request(
            posting_mode=POSTING_MODE_EXISTING,
            target_campaign_id="existing-campaign",
            target_adset_id="existing-adset",
            audience_type="inherited",
            customer_lifecycle_strategy="",
        )
        result = MetaPostingService(
            client=client,
            store=FakePostingStore(),
            carousel_validator=AcceptingCarouselValidator(),
        ).create_paused_campaign(request)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(client.calls.count("carousel_ad"), 1)
        self.assertEqual(next(iter(client.carousel_ads.values()))["status"], "PAUSED")

    def test_wrong_card_readback_fails_closed(self):
        client = FakeCarouselClient()
        original_read = client.carousel_creative

        def wrong_readback(creative_id):
            creative = original_read(creative_id)
            creative["object_story_spec"]["link_data"]["child_attachments"][2][
                "name"
            ] = "WRONG CARD"
            return creative

        client.carousel_creative = wrong_readback
        with self.assertRaisesRegex(PostingError, "card_3_headline"):
            MetaPostingService(
                client=client,
                store=FakePostingStore(),
                carousel_validator=AcceptingCarouselValidator(),
            ).create_paused_campaign(carousel_request())
        self.assertEqual(next(iter(client.carousel_ads.values()))["status"], "PAUSED")

    def test_same_run_retry_reuses_five_uploads_and_creative(self):
        client = FakeCarouselClient(fail_first_ad=True)
        store = FakePostingStore()
        service = MetaPostingService(
            client=client, store=store, carousel_validator=AcceptingCarouselValidator()
        )
        request = carousel_request()
        with self.assertRaises(PostingError):
            service.create_paused_campaign(request)
        self.assertEqual(client.calls.count("ad_image"), 5)
        self.assertEqual(client.calls.count("carousel_creative"), 1)
        result = service.create_paused_campaign(request)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(client.calls.count("campaign"), 1)
        self.assertEqual(client.calls.count("adset"), 1)
        self.assertEqual(client.calls.count("ad_image"), 5)
        self.assertEqual(client.calls.count("carousel_creative"), 1)
        self.assertEqual(client.calls.count("carousel_ad"), 2)
        self.assertEqual(len(client.carousel_ads), 1)

    def test_different_run_intentionally_creates_another_carousel(self):
        client = FakeCarouselClient()
        validator = AcceptingCarouselValidator()
        first = MetaPostingService(
            client=client, store=FakePostingStore(), carousel_validator=validator
        ).create_paused_campaign(carousel_request())
        second = MetaPostingService(
            client=client, store=FakePostingStore(), carousel_validator=validator
        ).create_paused_campaign(
            carousel_request(
                submission_id="33333333-3333-4333-8333-333333333333"
            )
        )
        self.assertNotEqual(first["campaign_id"], second["campaign_id"])
        self.assertNotEqual(first["meta_ad_id"], second["meta_ad_id"])
        self.assertEqual(len(client.carousel_ads), 2)

    def test_existing_target_static_relationship_mismatch_blocks(self):
        campaign = FakeCarouselClient().configured_campaign("existing-campaign")
        adset = FakeCarouselClient().configured_adset("existing-adset")
        adset["campaign_id"] = "other-campaign"
        with self.assertRaisesRegex(PostingValidationError, "does not belong"):
            validate_existing_carousel_target(
                campaign=campaign,
                adset=adset,
                expected_campaign_id="existing-campaign",
                expected_adset_id="existing-adset",
                expected_account_id="act_123",
                expected_pixel_id="pixel-1",
            )


if __name__ == "__main__":
    unittest.main()
