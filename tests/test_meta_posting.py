import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import ads_navigation
import ads_posting_page
import meta_ads_client
import supabase_backend
from ads_image_workflow import prepare_meta_posting_image
from ads_meta_contract import META_AD_URL_PARAMETERS, META_DEFAULT_CTA
from meta_posting_service import (
    MetaPostingService,
    PostingRequest,
    PostingValidationError,
    SUCCESS_MESSAGE,
    default_ad_name,
    posting_submission_id,
    validate_posting_request,
)


ROOT = Path(__file__).resolve().parents[1]


def image_bytes(image_format, *, size=(320, 180)):
    output = io.BytesIO()
    image = Image.new("RGB", size, (20, 18, 15))
    image.save(output, format=image_format, quality=95)
    return output.getvalue()


def request_for(**overrides):
    values = {
        "submission_id": posting_submission_id(),
        "campaign_id": "campaign-1",
        "adset_id": "adset-1",
        "destination_url": "  https://www.sportscaveshop.com/products/shane-warne-framed-art?variant=1  ",
        "image_bytes": image_bytes("PNG"),
        "image_name": "finished-ad.png",
        "primary_text": "Greatness doesn't fade.\n\nIt gets framed.",
        "headline": "Only 100 Shane Warne Editions",
        "ad_name": "SC | shane-warne-framed-art | 2026-08-31",
        "description": "Limited Edition",
    }
    values.update(overrides)
    return PostingRequest(**values)


class FakePostingStore:
    def __init__(self):
        self.records = {}
        self.stage_updates = []

    def claim(self, request_data, *, lease_token):
        del lease_token
        submission_id = request_data["submission_id"]
        existing = self.records.get(submission_id)
        if existing and existing.get("status") == "COMPLETE":
            return {"claimed": False, "record": dict(existing)}
        if not existing:
            existing = {**request_data, "status": "VALIDATING"}
            self.records[submission_id] = existing
        return {"claimed": True, "record": dict(existing)}

    def update_stage(self, submission_id, status, **fields):
        record = self.records[submission_id]
        record.update(fields)
        record["status"] = status
        self.stage_updates.append((status, dict(fields)))
        return dict(record)

    def recent(self, limit=20):
        return list(self.records.values())[:limit]


class FakeMetaClient:
    ad_account_id = "act_123"
    page_id = "page-1"
    instagram_actor_id = "instagram-1"

    def __init__(self):
        self.upload_calls = 0
        self.creative_calls = 0
        self.ad_create_calls = 0
        self.created_creative = None
        self.created_ad = None
        self.fail_creative_once = False
        self.fail_ad_once = False

    def permissions(self):
        return ("ads_read", "ads_management")

    def campaign(self, campaign_id):
        return {
            "id": campaign_id,
            "name": "Collectors AU",
            "account_id": "123",
            "status": "PAUSED",
        }

    def adset(self, adset_id):
        return {
            "id": adset_id,
            "name": "Warm Audience",
            "campaign_id": "campaign-1",
            "account_id": "123",
            "status": "PAUSED",
        }

    def upload_image(self, image_data, *, filename, content_type):
        self.upload_calls += 1
        self.upload_payload = (bytes(image_data), filename, content_type)
        return "image-hash-1"

    def find_creative_by_name(self, creative_name):
        if self.created_creative and self.created_creative["name"] == creative_name:
            return self.created_creative
        return None

    def create_creative(self, **payload):
        self.creative_calls += 1
        if self.fail_creative_once:
            self.fail_creative_once = False
            raise meta_ads_client.MetaAdsApiError("creative failed")
        self.creative_payload = dict(payload)
        self.created_creative = {"id": "creative-1", "name": payload["creative_name"]}
        return "creative-1"

    def find_ad_by_creative(self, adset_id, creative_id):
        del adset_id
        if self.created_ad and self.created_ad["creative_id"] == creative_id:
            return self.created_ad
        return None

    def create_paused_ad(self, **payload):
        self.ad_create_calls += 1
        if self.fail_ad_once:
            self.fail_ad_once = False
            raise meta_ads_client.MetaAdsApiError("ad failed")
        self.ad_payload = dict(payload)
        self.created_ad = {"id": "ad-1", "creative_id": payload["creative_id"]}
        return "ad-1"

    def ad(self, ad_id):
        return {
            "id": ad_id,
            "configured_status": "PAUSED",
            "effective_status": "PENDING_REVIEW",
        }


class PostingNavigationTests(unittest.TestCase):
    def test_ads_navigation_order_is_new_ads_refresh_posting(self):
        self.assertEqual(ads_navigation.ADS_ROUTES, ("Ads", "Creative Refresh", "Posting"))
        self.assertEqual(
            tuple(ads_navigation.ADS_NAV_LABELS[route] for route in ads_navigation.ADS_ROUTES),
            ("New Ads", "Creative Refresh", "Posting"),
        )

    def test_posting_is_lazy_and_does_not_call_meta_at_app_startup(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('importlib.import_module("ads_posting_page")', source)
        self.assertNotIn("import ads_posting_page\n", source)
        with mock.patch.object(meta_ads_client.requests, "get") as get_mock, mock.patch.object(
            meta_ads_client.requests, "post"
        ) as post_mock:
            meta_ads_client.MetaPostingClient()
        get_mock.assert_not_called()
        post_mock.assert_not_called()

    def test_existing_ads_renderers_are_unchanged_and_posting_has_own_route(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = source[source.index("def render_selected_page"):]
        self.assertIn('elif current_page in {"Ads", "Marketing Factory"}:', route_source)
        self.assertIn("get_ads_page().render_page()", route_source)
        self.assertIn("get_ads_creative_refresh_page().render_page()", route_source)
        self.assertIn("get_ads_posting_page().render_page()", route_source)


class PostingValidationTests(unittest.TestCase):
    def test_product_url_must_be_https_and_whitespace_is_trimmed(self):
        with self.assertRaisesRegex(PostingValidationError, "https"):
            validate_posting_request(request_for(destination_url="http://example.com/product"))
        clean = validate_posting_request(request_for())
        self.assertEqual(
            clean["destination_url"],
            "https://www.sportscaveshop.com/products/shane-warne-framed-art?variant=1",
        )

    def test_missing_and_invalid_images_are_blocked(self):
        with self.assertRaisesRegex(PostingValidationError, "Upload"):
            validate_posting_request(request_for(image_bytes=b""))
        with self.assertRaisesRegex(PostingValidationError, "corrupt"):
            validate_posting_request(request_for(image_bytes=b"not-an-image"))

    def test_jpg_png_and_webp_are_valid_and_preserve_aspect_ratio(self):
        for image_format, name in (("JPEG", "ad.jpg"), ("PNG", "ad.png"), ("WEBP", "ad.webp")):
            with self.subTest(image_format=image_format):
                prepared = prepare_meta_posting_image(
                    image_bytes(image_format, size=(400, 240)),
                    original_name=name,
                )
                self.assertEqual((prepared["source_width"], prepared["source_height"]), (400, 240))
                if image_format == "WEBP":
                    self.assertTrue(prepared["converted"])
                    self.assertEqual(prepared["upload_format"], "PNG")
                else:
                    self.assertFalse(prepared["converted"])

    def test_missing_copy_blocks_submission(self):
        with self.assertRaisesRegex(PostingValidationError, "primary text"):
            validate_posting_request(request_for(primary_text="  "))
        with self.assertRaisesRegex(PostingValidationError, "headline"):
            validate_posting_request(request_for(headline=""))

    def test_ad_name_uses_product_handle_and_sydney_date(self):
        class FixedDate:
            def date(self):
                return __import__("datetime").date(2026, 8, 31)

        self.assertEqual(
            default_ad_name(
                "https://www.sportscaveshop.com/products/shane-warne-framed-art?variant=1",
                now=FixedDate(),
            ),
            "SC | shane-warne-framed-art | 2026-08-31",
        )


class MetaPostingClientTests(unittest.TestCase):
    def config(self):
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "secret-token",
            "api_version": "v26.0",
            "api_version_source": "default",
            "page_id": "page-1",
            "instagram_actor_id": "instagram-1",
        }

    def test_campaigns_and_only_selected_campaign_adsets_use_read_endpoints(self):
        calls = []

        def fake_paged_get(path, params=None, config=None, max_pages=25):
            del params, config, max_pages
            calls.append(path)
            if path.endswith("/campaigns"):
                return {"rows": [{"id": "campaign-1"}]}
            return {
                "rows": [
                    {"id": "adset-1", "campaign_id": "campaign-1"},
                    {"id": "adset-2", "campaign_id": "campaign-1"},
                ]
            }

        client = meta_ads_client.MetaPostingClient(self.config())
        with mock.patch.object(meta_ads_client, "_paged_get", side_effect=fake_paged_get):
            self.assertEqual([row["id"] for row in client.campaigns()], ["campaign-1"])
            self.assertEqual(
                [row["id"] for row in client.campaign_adsets("campaign-1")],
                ["adset-1", "adset-2"],
            )
        self.assertEqual(calls, ["act_123/campaigns", "campaign-1/adsets"])

    def test_current_default_api_version_and_render_override_source(self):
        with mock.patch.dict(os.environ, {"META_API_VERSION": ""}, clear=False):
            default_config = meta_ads_client.get_meta_config()
        self.assertEqual(default_config["api_version"], "v26.0")
        self.assertEqual(default_config["api_version_source"], "default")

        with mock.patch.dict(os.environ, {"META_API_VERSION": "v25.0"}, clear=False):
            override_config = meta_ads_client.get_meta_config()
        self.assertEqual(override_config["api_version"], "v25.0")
        self.assertEqual(override_config["api_version_source"], "META_API_VERSION")

    def test_meta_response_error_code_is_preserved_but_secrets_are_sanitized(self):
        response = mock.Mock(ok=False, status_code=400)
        response.json.return_value = {
            "error": {
                "message": "Invalid token access_token=secret-token-value",
                "type": "OAuthException",
                "code": 190,
            }
        }
        with self.assertRaises(meta_ads_client.MetaAdsApiError) as raised:
            meta_ads_client._raise_for_meta_error(response, request_path="me")
        self.assertEqual(raised.exception.error_code, 190)
        self.assertEqual(raised.exception.request_path, "me")
        self.assertNotIn("secret-token-value", str(raised.exception))

    def test_ad_create_payload_is_unconditionally_paused(self):
        client = meta_ads_client.MetaPostingClient(self.config())
        with mock.patch.object(meta_ads_client, "_post", return_value={"id": "ad-1"}) as post_mock:
            self.assertEqual(
                client.create_paused_ad(ad_name="Named ad", adset_id="adset-1", creative_id="creative-1"),
                "ad-1",
            )
        path, call = post_mock.call_args.args[0], post_mock.call_args.kwargs
        self.assertEqual(path, "act_123/ads")
        self.assertEqual(call["data"]["status"], "PAUSED")
        self.assertEqual(call["data"]["adset_id"], "adset-1")

    def test_creative_uses_current_instagram_user_identity_field(self):
        client = meta_ads_client.MetaPostingClient(self.config())
        with mock.patch.object(meta_ads_client, "_post", return_value={"id": "creative-1"}) as post_mock:
            client.create_creative(
                creative_name="SC creative",
                image_hash="hash-1",
                primary_text="Primary text",
                headline="Headline",
                description="",
                destination_url="https://www.sportscaveshop.com/products/example",
                cta_type="SHOP_NOW",
                url_tags="",
            )
        story_spec = json.loads(post_mock.call_args.kwargs["data"]["object_story_spec"])
        self.assertEqual(story_spec["instagram_user_id"], "instagram-1")
        self.assertNotIn("instagram_actor_id", story_spec)

    def test_current_and_legacy_instagram_identity_reads_remain_compatible(self):
        current = supabase_backend._extract_creative_fields(
            {"object_story_spec": {"instagram_user_id": "instagram-current"}}
        )
        legacy = supabase_backend._extract_creative_fields(
            {"object_story_spec": {"instagram_actor_id": "instagram-legacy"}}
        )
        self.assertEqual(current["instagram_actor_id"], "instagram-current")
        self.assertEqual(legacy["instagram_actor_id"], "instagram-legacy")

    def test_posting_has_no_campaign_or_adset_write_method_and_no_live_status_option(self):
        self.assertFalse(hasattr(meta_ads_client.MetaPostingClient, "update_campaign"))
        self.assertFalse(hasattr(meta_ads_client.MetaPostingClient, "update_adset"))
        posting_source = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("ads_posting_page.py", "meta_posting_service.py")
        )
        self.assertNotIn('"ACTIVE"', posting_source)
        self.assertNotIn("'ACTIVE'", posting_source)


class MetaConnectionDiagnosticTests(unittest.TestCase):
    def config(self):
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "secret-token-value",
            "api_version": "v26.0",
            "api_version_source": "META_API_VERSION",
            "page_id": "page-1",
            "instagram_user_id": "instagram-1",
        }

    def successful_reads(self):
        return (
            mock.patch.object(meta_ads_client, "fetch_meta_token_identity", return_value={"id": "system-1"}),
            mock.patch.object(meta_ads_client, "fetch_meta_account", return_value={"id": "act_123"}),
            mock.patch.object(
                meta_ads_client,
                "fetch_meta_campaigns",
                return_value={"rows": [{"id": "campaign-1", "name": "Collectors"}]},
            ),
        )

    def test_permission_endpoint_failure_is_non_fatal_and_sanitized(self):
        identity_patch, account_patch, campaign_patch = self.successful_reads()
        permission_error = meta_ads_client.MetaAdsApiError(
            "Meta API error HTTP 400: permission introspection unavailable (code 100)",
            error_code=100,
        )
        with identity_patch, account_patch, campaign_patch, mock.patch.object(
            meta_ads_client,
            "fetch_meta_permissions",
            side_effect=permission_error,
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        self.assertTrue(result["connected"])
        self.assertTrue(result["posting_ready"])
        self.assertEqual(result["permission_state"], "unverified")
        self.assertEqual(
            result["checks"]["permissions"]["message"],
            "permission introspection unavailable",
        )

    def test_campaign_failure_is_identified_even_when_permission_check_succeeds(self):
        campaign_error = meta_ads_client.MetaAdsApiError(
            "Meta API error HTTP 403: access denied (code 200)",
            error_code=200,
            request_path="act_123/campaigns",
        )
        with mock.patch.object(
            meta_ads_client, "fetch_meta_token_identity", return_value={"id": "system-1"}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_account", return_value={"id": "act_123"}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_campaigns", side_effect=campaign_error
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_permissions", return_value=("ads_management",)
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        self.assertFalse(result["connected"])
        self.assertEqual(result["summary"], "Meta unavailable — campaign read failed.")
        self.assertEqual(result["checks"]["campaigns"]["error_code"], 200)

    def test_successful_account_and_campaign_reads_are_connected(self):
        identity_patch, account_patch, campaign_patch = self.successful_reads()
        with identity_patch, account_patch, campaign_patch, mock.patch.object(
            meta_ads_client,
            "fetch_meta_permissions",
            return_value=("ads_read", "ads_management"),
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        self.assertTrue(result["connected"])
        self.assertTrue(result["posting_ready"])
        self.assertEqual(result["summary"], "Meta connected")
        self.assertEqual(result["campaigns"][0]["id"], "campaign-1")

    def test_secrets_are_never_returned_in_diagnostics(self):
        token = "secret-token-value"
        app_secret = "secret-app-value"
        identity_error = meta_ads_client.MetaAdsApiError(
            f"access_token={token} app_secret={app_secret} (code 190)",
            error_code=190,
        )
        with mock.patch.object(
            meta_ads_client, "fetch_meta_token_identity", side_effect=identity_error
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_account", return_value={"id": "act_123"}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_campaigns", return_value={"rows": []}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_permissions", return_value=("ads_management",)
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        serialized = json.dumps(result)
        self.assertNotIn(token, serialized)
        self.assertNotIn(app_secret, serialized)
        self.assertIn("[redacted]", serialized)
        self.assertEqual(result["summary"], "Meta unavailable — Meta returned error code 190.")

    def test_effective_api_version_and_source_are_reported_safely(self):
        identity_patch, account_patch, campaign_patch = self.successful_reads()
        with identity_patch, account_patch, campaign_patch, mock.patch.object(
            meta_ads_client, "fetch_meta_permissions", return_value=("ads_management",)
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        self.assertEqual(result["api_version"], "v26.0")
        self.assertEqual(result["api_version_source"], "META_API_VERSION")
        self.assertNotIn(self.config()["access_token"], json.dumps(result))

    def test_unsupported_version_error_is_understandable(self):
        version_error = meta_ads_client.MetaAdsApiError(
            "This API version is no longer supported.",
            error_code=12,
        )
        with mock.patch.object(
            meta_ads_client, "fetch_meta_token_identity", side_effect=version_error
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_account", return_value={"id": "act_123"}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_campaigns", return_value={"rows": []}
        ), mock.patch.object(
            meta_ads_client, "fetch_meta_permissions", return_value=("ads_management",)
        ):
            result = meta_ads_client.diagnose_meta_posting_connection(self.config())

        self.assertEqual(result["summary"], "Meta unavailable — API version unsupported.")

    def test_connection_diagnostic_never_posts(self):
        identity_patch, account_patch, campaign_patch = self.successful_reads()
        with identity_patch, account_patch, campaign_patch, mock.patch.object(
            meta_ads_client, "fetch_meta_permissions", return_value=("ads_management",)
        ), mock.patch.object(meta_ads_client.requests, "post") as post_mock:
            meta_ads_client.diagnose_meta_posting_connection(self.config())
        post_mock.assert_not_called()


class PostingServiceTests(unittest.TestCase):
    def test_one_submission_creates_one_paused_ad_and_stores_safe_ids(self):
        client = FakeMetaClient()
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)

        result = service.create_paused_ad(request_for())

        self.assertEqual(client.upload_calls, 1)
        self.assertEqual(client.creative_calls, 1)
        self.assertEqual(client.ad_create_calls, 1)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["meta_ad_id"], "ad-1")
        self.assertEqual(result["meta_creative_id"], "creative-1")
        self.assertEqual(result["meta_status"], "PAUSED")
        self.assertEqual(client.creative_payload["cta_type"], META_DEFAULT_CTA)
        self.assertEqual(client.creative_payload["url_tags"], META_AD_URL_PARAMETERS)

    def test_unavailable_permission_introspection_does_not_override_real_api_checks(self):
        client = FakeMetaClient()
        client.permissions = lambda: (_ for _ in ()).throw(
            meta_ads_client.MetaAdsApiError("Permission introspection unavailable")
        )
        result = MetaPostingService(client=client, store=FakePostingStore()).create_paused_ad(
            request_for()
        )

        self.assertEqual(result["meta_status"], "PAUSED")
        self.assertEqual(client.ad_create_calls, 1)

    def test_double_click_or_rerun_cannot_create_a_second_ad(self):
        client = FakeMetaClient()
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        request = request_for()

        first = service.create_paused_ad(request)
        second = service.create_paused_ad(request)

        self.assertEqual(first["meta_ad_id"], second["meta_ad_id"])
        self.assertEqual(client.ad_create_calls, 1)
        self.assertEqual(client.creative_calls, 1)
        self.assertEqual(client.upload_calls, 1)

    def test_partial_creative_failure_resumes_from_saved_image(self):
        client = FakeMetaClient()
        client.fail_creative_once = True
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        request = request_for()

        with self.assertRaisesRegex(Exception, "creative failed"):
            service.create_paused_ad(request)
        result = service.create_paused_ad(request)

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(client.upload_calls, 1)
        self.assertEqual(client.creative_calls, 2)
        self.assertEqual(client.ad_create_calls, 1)

    def test_partial_ad_failure_resumes_from_saved_creative(self):
        client = FakeMetaClient()
        client.fail_ad_once = True
        store = FakePostingStore()
        service = MetaPostingService(client=client, store=store)
        request = request_for()

        with self.assertRaisesRegex(Exception, "ad failed"):
            service.create_paused_ad(request)
        result = service.create_paused_ad(request)

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(client.upload_calls, 1)
        self.assertEqual(client.creative_calls, 1)
        self.assertEqual(client.ad_create_calls, 2)

    def test_campaign_and_adset_ownership_are_revalidated(self):
        client = FakeMetaClient()
        client.adset = lambda _adset_id: {
            "id": "adset-1",
            "campaign_id": "different-campaign",
            "account_id": "123",
        }
        with self.assertRaisesRegex(PostingValidationError, "ad set"):
            MetaPostingService(client=client, store=FakePostingStore()).create_paused_ad(request_for())
        self.assertEqual(client.upload_calls, 0)
        self.assertEqual(client.ad_create_calls, 0)

    def test_secrets_and_raw_image_bytes_are_not_in_persistent_schema(self):
        migration = (ROOT / "migrations" / "20260831_meta_posting_v1.sql").read_text(encoding="utf-8")
        for prohibited in ("access_token", "app_secret", "authorization", "raw_image", "image_bytes"):
            self.assertNotIn(prohibited, migration.casefold())
        self.assertIn("image_checksum", migration)

    def test_success_wording_is_exact_and_page_uses_it(self):
        self.assertEqual(SUCCESS_MESSAGE, "Paused in Meta — ready for review")
        self.assertIs(ads_posting_page.SUCCESS_MESSAGE, SUCCESS_MESSAGE)


if __name__ == "__main__":
    unittest.main()
