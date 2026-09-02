import json
import unittest
from unittest import mock

import meta_ads_client
from meta_collection_diagnostics import (
    MetaCollectionDiagnosticSafetyError,
    MetaCollectionValidateOnlyProbe,
    assert_validate_only_transport,
    build_inline_ad_validate_only_payload,
    build_standalone_validate_only_payload,
    sanitized_collection_request_shape,
)
from meta_posting_service import build_collection_creative_payload


class MetaCollectionValidateOnlyTests(unittest.TestCase):
    @staticmethod
    def config():
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "EAA-ad-token-never-log",
            "page_access_token": "EAA-page-token-never-log",
            "api_version": "v26.0",
            "page_id": "page-1",
            "instagram_user_id": "ig-1",
        }

    @staticmethod
    def creative():
        return build_collection_creative_payload(
            name="Route 1 | Collection",
            page_id="page-1",
            instagram_user_id="ig-1",
            image_hash="route-1-image-hash",
            canvas_id="1390026833255926",
            product_set_id="peter-brock-set",
            destination_url="https://sportscaveshop.com/products/peter-brock",
            primary_text="Peter Brock primary text",
            headline="Peter Brock headline",
        )

    def test_standalone_builder_adds_exact_validate_only_option(self):
        payload = build_standalone_validate_only_payload(self.creative())
        self.assertEqual(payload["execution_options"], ["validate_only"])
        self.assertEqual(payload["product_set_id"], "peter-brock-set")

    def test_inline_builder_uses_paused_ad_and_full_creative_not_creative_id(self):
        payload = build_inline_ad_validate_only_payload(
            ad_name="Diagnostic",
            adset_id="120249720389890554",
            creative_payload=self.creative(),
        )
        self.assertEqual(payload["status"], "PAUSED")
        self.assertEqual(payload["execution_options"], ["validate_only"])
        self.assertEqual(payload["creative"]["product_set_id"], "peter-brock-set")
        self.assertNotIn("creative_id", payload["creative"])
        self.assertNotIn("name", payload["creative"])

    def test_transport_guard_rejects_missing_option_wrong_edge_and_active_status(self):
        with self.assertRaises(MetaCollectionDiagnosticSafetyError):
            assert_validate_only_transport("act_123/ads", {"status": "PAUSED"})
        with self.assertRaises(MetaCollectionDiagnosticSafetyError):
            assert_validate_only_transport(
                "act_123/campaigns", {"execution_options": '["validate_only"]'}
            )
        with self.assertRaises(MetaCollectionDiagnosticSafetyError):
            assert_validate_only_transport(
                "act_123/ads",
                {"execution_options": '["validate_only"]', "status": "ACTIVE"},
            )

    @mock.patch("meta_collection_diagnostics._post", return_value={"success": True})
    def test_test_a_posts_only_to_standalone_edge_with_json_validate_only(self, post):
        result = MetaCollectionValidateOnlyProbe(
            self.config()
        ).validate_standalone_creative(self.creative())
        self.assertTrue(result["validated"])
        self.assertEqual(post.call_args.args[0], "act_123/adcreatives")
        data = post.call_args.kwargs["data"]
        self.assertEqual(json.loads(data["execution_options"]), ["validate_only"])
        self.assertEqual(json.loads(data["object_story_spec"])["page_id"], "page-1")
        self.assertEqual(data["product_set_id"], "peter-brock-set")
        self.assertEqual(result["response"], {"success": True})

    @mock.patch("meta_collection_diagnostics._post", return_value={"success": True})
    def test_test_b_posts_inline_creative_to_ads_with_validate_only_and_paused(self, post):
        result = MetaCollectionValidateOnlyProbe(self.config()).validate_inline_ad(
            ad_name="Diagnostic",
            adset_id="120249720389890554",
            creative_payload=self.creative(),
        )
        self.assertTrue(result["validated"])
        self.assertEqual(post.call_args.args[0], "act_123/ads")
        data = post.call_args.kwargs["data"]
        self.assertEqual(json.loads(data["execution_options"]), ["validate_only"])
        self.assertEqual(data["status"], "PAUSED")
        inline = json.loads(data["creative"])
        self.assertEqual(inline["product_set_id"], "peter-brock-set")
        self.assertEqual(
            inline["object_story_spec"]["link_data"]["retailer_item_ids"],
            ["0", "0", "0", "0"],
        )

    @mock.patch("meta_collection_diagnostics._post")
    def test_test_b_runs_after_test_a_returns_1990065(self, post):
        post.side_effect = [
            meta_ads_client.MetaAdsApiError(
                "Invalid parameter",
                status_code=400,
                error_code=100,
                error_subcode=1990065,
                fbtrace_id="safe-trace",
            ),
            {"success": True},
        ]
        results = MetaCollectionValidateOnlyProbe(self.config()).run_ab(
            ad_name="Diagnostic",
            adset_id="120249720389890554",
            creative_payload=self.creative(),
        )
        self.assertFalse(results[0]["validated"])
        self.assertEqual(results[0]["error_subcode"], 1990065)
        self.assertTrue(results[1]["validated"])
        self.assertEqual(post.call_count, 2)

    @mock.patch("meta_collection_diagnostics._post")
    def test_diagnostic_error_never_leaks_configured_tokens(self, post):
        config = self.config()
        post.side_effect = meta_ads_client.MetaAdsApiError(
            f"Rejected {config['access_token']} and {config['page_access_token']}",
            error_code=100,
        )
        result = MetaCollectionValidateOnlyProbe(
            config
        ).validate_standalone_creative(self.creative())
        rendered = json.dumps(result)
        self.assertNotIn(config["access_token"], rendered)
        self.assertNotIn(config["page_access_token"], rendered)
        self.assertIn("[redacted]", rendered)

    @mock.patch("meta_collection_diagnostics._post")
    def test_success_response_is_recorded_but_secrets_are_redacted(self, post):
        config = self.config()
        post.return_value = {
            "success": True,
            "access_token": config["access_token"],
            "detail": f"validated with {config['page_access_token']}",
        }
        result = MetaCollectionValidateOnlyProbe(
            config
        ).validate_standalone_creative(self.creative())
        rendered = json.dumps(result)
        self.assertNotIn(config["access_token"], rendered)
        self.assertNotIn(config["page_access_token"], rendered)
        self.assertEqual(result["response"]["access_token"], "[redacted]")
        self.assertIn("[redacted]", result["response"]["detail"])

    def test_sanitized_shapes_contain_no_real_ids_hashes_or_copy(self):
        rendered = json.dumps(
            {
                "a": sanitized_collection_request_shape(mode="standalone"),
                "b": sanitized_collection_request_shape(
                    mode="inline_ad", adset_id="120249720389890554"
                ),
            }
        )
        for value in (
            "120249720389890554",
            "1390026833255926",
            "route-1-image-hash",
            "Peter Brock primary text",
        ):
            self.assertNotIn(value, rendered)
        self.assertIn("validate_only", rendered)


if __name__ == "__main__":
    unittest.main()
