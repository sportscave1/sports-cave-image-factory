import io
import json
import unittest
from unittest import mock

from PIL import Image

import meta_ads_client
from ads_image_workflow import prepare_meta_posting_image
from meta_collection_crop_diagnostics import (
    DEFAULT_PREVIEW_FORMATS,
    MetaCollectionCropAuditError,
    audit_meta_collection_crop_routes,
    audit_meta_collection_crop_state,
    classify_collection_crop_state,
)
from meta_collection_template_copy import REQUIRED_COLLECTION_FEATURES


ROUTE_AD_ID = "route-ad-1"
SOURCE_AD_ID = "120249557468150554"


def creative_payload(
    *,
    creative_id,
    image_hash,
    image_crops=None,
    link_image_crops=None,
    format_transformation_spec=None,
    asset_feed_spec=None,
    platform_customizations=None,
    portrait_customizations=None,
    image_layer_specs=None,
):
    return {
        "id": creative_id,
        "name": f"{creative_id} name",
        "image_hash": image_hash,
        "image_crops": image_crops or {},
        "object_story_spec": {
            "link_data": {
                "image_hash": image_hash,
                "image_crops": link_image_crops or {},
                "image_layer_specs": image_layer_specs or [],
            }
        },
        "format_transformation_spec": format_transformation_spec or [],
        "asset_feed_spec": asset_feed_spec or {},
        "platform_customizations": platform_customizations or {},
        "portrait_customizations": portrait_customizations or {},
        "degrees_of_freedom_spec": {
            "creative_features_spec": {
                "media_type_automation": {"enroll_status": "OPT_IN"},
            }
        },
    }


class FakeReadOnlyCropClient:
    def __init__(self, *, route_creative, source_creative):
        self.route_creative = route_creative
        self.source_creative = source_creative
        self.calls = []

    def ad(self, ad_id):
        self.calls.append(("GET ad", ad_id))
        creative_id = (
            self.route_creative["id"]
            if ad_id == ROUTE_AD_ID
            else self.source_creative["id"]
        )
        return {
            "id": ad_id,
            "name": "Route" if ad_id == ROUTE_AD_ID else "Template",
            "status": "PAUSED" if ad_id == ROUTE_AD_ID else "ACTIVE",
            "configured_status": "PAUSED" if ad_id == ROUTE_AD_ID else "ACTIVE",
            "effective_status": "CAMPAIGN_PAUSED",
            "creative": {"id": creative_id},
        }

    def creative_crop_details(self, creative_id):
        self.calls.append(("GET creative", creative_id))
        if creative_id == self.route_creative["id"]:
            return self.route_creative
        return self.source_creative

    def ad_image_details(self, image_hash):
        self.calls.append(("GET adimages", image_hash))
        return {
            "hash": image_hash,
            "width": 1024,
            "height": 1024,
            "original_width": 1024,
            "original_height": 1024,
        }


class MultiRouteReadOnlyCropClient:
    def __init__(self, creatives):
        self.creatives = creatives
        self.calls = []

    def ad_crop_details(self, ad_id):
        self.calls.append(("GET ad", ad_id))
        return {
            "id": ad_id,
            "name": f"Name {ad_id}",
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "CAMPAIGN_PAUSED",
            "creative": {"id": f"creative-{ad_id}"},
            "created_time": "2026-09-03T05:00:00+0000",
            "updated_time": "2026-09-03T05:01:00+0000",
        }

    def creative_crop_details(self, creative_id):
        self.calls.append(("GET creative", creative_id))
        return self.creatives[creative_id]

    def ad_image_details(self, image_hash):
        self.calls.append(("GET adimages", image_hash))
        return {
            "hash": image_hash,
            "width": 1080,
            "height": 1080,
            "original_width": 1080,
            "original_height": 1080,
            "url": "https://scontent.example.test/image.jpg?sig=private",
            "created_time": "2026-09-03T04:59:00+0000",
        }

    def ad_preview(self, ad_id, *, ad_format):
        self.calls.append(("GET preview", f"{ad_id}:{ad_format}"))
        return {
            "ad_format": ad_format,
            "rows": (
                {
                    "body": (
                        '<iframe src="https://www.facebook.com/ads/preview/'
                        f'{ad_id}/{ad_format}?access_token=never-report"></iframe>'
                    ),
                    "transformation_spec": {"ad_format": ad_format},
                },
            ),
            "unavailable": {},
        }


class MetaCollectionCropClientReadTests(unittest.TestCase):
    @staticmethod
    def config():
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "secret",
            "api_version": "v26.0",
        }

    @mock.patch("meta_ads_client._request", return_value={"id": "creative-1"})
    def test_optional_creative_crop_read_requests_current_sdk_fields(self, request):
        client = meta_ads_client.MetaPostingClient(self.config())
        result = client.creative_crop_details("creative-1")
        requested_fields = [
            call.kwargs["params"]["fields"] for call in request.call_args_list
        ]
        self.assertIn("object_story_spec", requested_fields[0])
        self.assertIn("id,image_crops", requested_fields)
        self.assertIn("id,image_url", requested_fields)
        self.assertIn("id,thumbnail_url", requested_fields)
        self.assertIn("id,effective_object_story_id", requested_fields)
        self.assertIn("id,format_transformation_spec", requested_fields)
        self.assertIn("id,asset_feed_spec", requested_fields)
        self.assertIn("id,platform_customizations", requested_fields)
        self.assertIn("id,portrait_customizations", requested_fields)
        self.assertEqual(
            set(result["_unavailable_crop_fields"]),
            {
                "image_crops",
                "image_url",
                "thumbnail_url",
                "effective_object_story_id",
                "format_transformation_spec",
                "asset_feed_spec",
                "platform_customizations",
                "portrait_customizations",
            },
        )

    @mock.patch("meta_ads_client._request")
    def test_optional_code_three_is_recorded_without_hiding_auth_errors(self, request):
        request.side_effect = [
            {"id": "creative-1", "image_hash": "hash-1"},
            meta_ads_client.MetaAdsApiError("No capability", error_code=3),
            {"id": "creative-1", "image_url": "https://example.test/image.jpg"},
            {"id": "creative-1", "thumbnail_url": "https://example.test/thumb.jpg"},
            {"id": "creative-1", "effective_object_story_id": "story-1"},
            {"id": "creative-1", "format_transformation_spec": []},
            {"id": "creative-1", "asset_feed_spec": {}},
            {"id": "creative-1", "platform_customizations": {}},
            {"id": "creative-1", "portrait_customizations": {}},
        ]
        result = meta_ads_client.MetaPostingClient(self.config()).creative_crop_details(
            "creative-1"
        )
        self.assertEqual(
            result["_unavailable_crop_fields"]["image_crops"]["error_code"], 3
        )

        request.reset_mock(side_effect=True)
        request.side_effect = [
            {"id": "creative-1", "image_hash": "hash-1"},
            meta_ads_client.MetaAdsApiError("Token expired", error_code=190),
        ]
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            meta_ads_client.MetaPostingClient(self.config()).creative_crop_details(
                "creative-1"
            )

    @mock.patch("meta_ads_client._paged_get")
    def test_ad_image_dimension_read_is_get_only_and_hash_scoped(self, paged_get):
        paged_get.return_value = {
            "rows": [
                {
                    "hash": "route-hash",
                    "width": 1024,
                    "height": 1024,
                    "original_width": 1024,
                    "original_height": 1024,
                }
            ]
        }
        client = meta_ads_client.MetaPostingClient(self.config())
        result = client.ad_image_details("route-hash")
        self.assertEqual(result["original_width"], 1024)
        self.assertEqual(paged_get.call_args_list[0].args[0], "act_123/adimages")
        params = paged_get.call_args_list[0].kwargs["params"]
        self.assertEqual(json.loads(params["hashes"]), ["route-hash"])
        self.assertEqual(
            params["fields"],
            "hash,width,height,original_width,original_height",
        )
        self.assertEqual(
            paged_get.call_args_list[1].kwargs["params"]["fields"],
            (
                "hash,url,url_128,permalink_url,created_time,updated_time"
            ),
        )

    @mock.patch("meta_ads_client._paged_get")
    def test_optional_ad_image_metadata_capability_error_does_not_hide_dimensions(
        self, paged_get
    ):
        paged_get.side_effect = [
            {
                "rows": [
                    {
                        "hash": "route-hash",
                        "width": 1080,
                        "height": 1080,
                        "original_width": 1080,
                        "original_height": 1080,
                    }
                ]
            },
            meta_ads_client.MetaAdsApiError("No capability", error_code=3),
        ]
        result = meta_ads_client.MetaPostingClient(self.config()).ad_image_details(
            "route-hash"
        )
        self.assertEqual(result["width"], 1080)
        self.assertEqual(result["_unavailable_image_fields"]["error_code"], 3)

    @mock.patch("meta_ads_client._paged_get")
    def test_official_placement_preview_read_is_get_only(self, paged_get):
        paged_get.return_value = {
            "rows": [
                {
                    "body": '<iframe src="https://www.facebook.com/preview?sig=secret"></iframe>',
                    "transformation_spec": {"placement": "facebook_feed"},
                }
            ]
        }
        client = meta_ads_client.MetaPostingClient(self.config())
        result = client.ad_preview("ad-2", ad_format="MOBILE_FEED_STANDARD")
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(paged_get.call_args.args[0], "ad-2/previews")
        self.assertEqual(
            paged_get.call_args.kwargs["params"]["ad_format"],
            "MOBILE_FEED_STANDARD",
        )
        self.assertEqual(paged_get.call_args.kwargs["max_pages"], 1)

    @mock.patch("meta_ads_client._paged_get")
    def test_optional_preview_capability_error_is_recorded_but_auth_propagates(
        self, paged_get
    ):
        paged_get.side_effect = meta_ads_client.MetaAdsApiError(
            "No capability", error_code=3
        )
        client = meta_ads_client.MetaPostingClient(self.config())
        result = client.ad_preview("ad-2", ad_format="FACEBOOK_STORY_MOBILE")
        self.assertEqual(result["unavailable"]["error_code"], 3)

        paged_get.side_effect = meta_ads_client.MetaAdsApiError(
            "Token expired", error_code=190
        )
        with self.assertRaises(meta_ads_client.MetaAdsApiError):
            client.ad_preview("ad-2", ad_format="INSTAGRAM_STANDARD")


class MetaCollectionCropAuditTests(unittest.TestCase):
    def test_explicit_template_crop_is_reported_as_case_a_and_inherited_candidate(self):
        crops = {"100x100": [[96, 0], [928, 832]]}
        route = creative_payload(
            creative_id="route-creative", image_hash="route-hash", image_crops=crops
        )
        source = creative_payload(
            creative_id="source-creative", image_hash="source-hash", image_crops=crops
        )
        client = FakeReadOnlyCropClient(
            route_creative=route, source_creative=source
        )
        report = audit_meta_collection_crop_state(
            client=client,
            route_ad_id=ROUTE_AD_ID,
            source_template_ad_id=SOURCE_AD_ID,
        )
        self.assertTrue(report["read_only"])
        self.assertEqual(report["meta_writes"], "NONE")
        self.assertEqual(report["classification"]["case"], "CASE_A")
        self.assertTrue(
            report["classification"]["inherited_from_template_candidate"]
        )
        self.assertTrue(report["route"]["route_hash_consistent"])
        self.assertTrue(client.calls)
        self.assertTrue(all(operation.startswith("GET ") for operation, _ in client.calls))

    def test_format_transformation_without_crop_is_reported_as_case_b(self):
        route = creative_payload(
            creative_id="route-creative",
            image_hash="route-hash",
            format_transformation_spec=[{"format": "vertical"}],
        )
        source = creative_payload(
            creative_id="source-creative", image_hash="source-hash"
        )
        classification = classify_collection_crop_state(
            route={"creative": route, "meta_image": {"width": 1024, "height": 1024}},
            source_template={"creative": source},
        )
        self.assertEqual(classification["case"], "CASE_B")
        self.assertIn("format_transformation_spec", classification["active_transformations"])

    def test_no_serialized_crop_or_transform_remains_case_f_without_preview_proof(self):
        route = creative_payload(
            creative_id="route-creative", image_hash="route-hash"
        )
        route["degrees_of_freedom_spec"]["creative_features_spec"][
            "media_type_automation"
        ]["enroll_status"] = "OPT_OUT"
        source = creative_payload(
            creative_id="source-creative", image_hash="source-hash"
        )
        classification = classify_collection_crop_state(
            route={"creative": route, "meta_image": {"width": 1024, "height": 1024}},
            source_template={"creative": source},
        )
        self.assertEqual(classification["case"], "CASE_F")
        self.assertFalse(classification["media_type_automation_causality_proven"])

    def test_media_type_automation_presence_alone_does_not_claim_case_b(self):
        route = creative_payload(
            creative_id="route-creative", image_hash="route-hash"
        )
        source = creative_payload(
            creative_id="source-creative", image_hash="source-hash"
        )
        classification = classify_collection_crop_state(
            route={"creative": route, "meta_image": {"width": 1024, "height": 1024}},
            source_template={"creative": source},
        )
        self.assertEqual(
            classification["case"], "CASE_F"
        )
        self.assertFalse(classification["media_type_automation_causality_proven"])

    def test_audit_rejects_source_ad_as_route(self):
        with self.assertRaises(MetaCollectionCropAuditError):
            audit_meta_collection_crop_state(
                client=mock.Mock(),
                route_ad_id=SOURCE_AD_ID,
                source_template_ad_id=SOURCE_AD_ID,
            )

    def test_three_route_audit_captures_hashes_crops_transforms_and_safe_previews(self):
        route_ids = ("route-ad-2", "route-ad-1", "route-ad-3")
        shared = {
            "image_crops": {"100x100": [[0, 0], [1080, 1080]]},
            "link_image_crops": {"100x100": [[0, 0], [1080, 1080]]},
            "format_transformation_spec": [{"format": "collection"}],
            "asset_feed_spec": {"images": []},
            "platform_customizations": {"facebook": {"image": "full"}},
            "portrait_customizations": {"image_cropping": "none"},
            "image_layer_specs": [{"type": "IMAGE"}],
        }
        creatives = {
            f"creative-{ad_id}": {
                **creative_payload(
                    creative_id=f"creative-{ad_id}",
                    image_hash=f"hash-{ad_id}",
                    **shared,
                ),
                "image_url": "https://scontent.example.test/creative.jpg?sig=private",
                "thumbnail_url": "https://scontent.example.test/thumb.jpg?sig=private",
                "effective_object_story_id": f"story-{ad_id}",
            }
            for ad_id in route_ids
        }
        creatives["creative-source"] = creative_payload(
            creative_id="creative-source",
            image_hash="hash-source",
            **shared,
        )
        client = MultiRouteReadOnlyCropClient(creatives)

        report = audit_meta_collection_crop_routes(
            client=client,
            route_ad_ids=route_ids,
            source_template_ad_id="source",
            preview_formats=DEFAULT_PREVIEW_FORMATS,
        )

        route = report["routes"]["route-ad-2"]
        self.assertEqual(route["creative"]["image_hash"], "hash-route-ad-2")
        self.assertEqual(
            route["creative"]["link_data_image_hash"], "hash-route-ad-2"
        )
        self.assertTrue(route["creative"]["image_crops"])
        self.assertTrue(route["creative"]["link_data_image_crops"])
        self.assertTrue(route["creative"]["link_data_image_layer_specs"])
        self.assertTrue(route["creative"]["format_transformation_spec"])
        self.assertTrue(route["creative"]["asset_feed_spec"])
        self.assertTrue(route["creative"]["platform_customizations"])
        self.assertTrue(route["creative"]["portrait_customizations"])
        self.assertEqual(route["meta_image"]["width"], 1080)
        self.assertNotIn("?", route["meta_image"]["url"])
        facebook_feed = route["previews"]["MOBILE_FEED_STANDARD"]
        self.assertTrue(facebook_feed["available"])
        self.assertFalse(facebook_feed["raw_preview_html_included"])
        self.assertTrue(facebook_feed["body_sha256"])
        self.assertTrue(
            all("?" not in value for value in facebook_feed["render_references"])
        )
        comparison = report["cross_route_comparison"]
        self.assertEqual(comparison["route_order"], list(route_ids))
        self.assertTrue(comparison["all_route_hashes_consistent"])
        self.assertTrue(
            comparison["all_routes_have_identical_crop_transformation_structure"]
        )
        self.assertTrue(
            comparison["facebook_vs_instagram_preview_responses"]["route-ad-2"][
                "FACEBOOK_FEED"
            ]["both_available"]
        )
        self.assertEqual(
            sum(1 for operation, value in client.calls if operation == "GET ad" and value == "source"),
            1,
        )
        self.assertTrue(all(operation.startswith("GET ") for operation, _ in client.calls))

    def test_three_route_comparison_is_deterministic_and_detects_one_route_difference(self):
        creatives = {
            "creative-route-a": creative_payload(
                creative_id="creative-route-a", image_hash="hash-a"
            ),
            "creative-route-b": creative_payload(
                creative_id="creative-route-b",
                image_hash="hash-b",
                platform_customizations={"facebook": {"crop": "different"}},
            ),
            "creative-source": creative_payload(
                creative_id="creative-source", image_hash="hash-source"
            ),
        }
        client = MultiRouteReadOnlyCropClient(creatives)
        first = audit_meta_collection_crop_routes(
            client=client,
            route_ad_ids=("route-a", "route-b"),
            source_template_ad_id="source",
            preview_formats=(),
        )
        second = audit_meta_collection_crop_routes(
            client=client,
            route_ad_ids=("route-a", "route-b"),
            source_template_ad_id="source",
            preview_formats=(),
        )
        self.assertFalse(
            first["cross_route_comparison"][
                "all_routes_have_identical_crop_transformation_structure"
            ]
        )
        self.assertEqual(
            first["cross_route_comparison"], second["cross_route_comparison"]
        )

    def test_meta_image_preparation_preserves_square_source_bytes_and_dimensions(self):
        output = io.BytesIO()
        Image.new("RGB", (1024, 1024), (32, 24, 18)).save(output, format="JPEG")
        source = output.getvalue()
        prepared = prepare_meta_posting_image(source, original_name="route-1.jpg")
        self.assertEqual(prepared["data"], source)
        self.assertEqual(prepared["source_width"], 1024)
        self.assertEqual(prepared["source_height"], 1024)
        self.assertFalse(prepared["converted"])

    def test_existing_artwork_and_collection_feature_policy_is_unchanged(self):
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["image_background_gen"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["image_auto_crop"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["adapt_to_placement"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["image_touchups"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["image_uncrop"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["pac_genai_recomposition"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["pac_recomposition"], "OPT_OUT")
        self.assertEqual(REQUIRED_COLLECTION_FEATURES["media_type_automation"], "OPT_IN")


if __name__ == "__main__":
    unittest.main()
