import json
import inspect
from pathlib import Path
import unittest
from unittest import mock

import ads_posting_page
import meta_ads_client
from meta_collection_diagnostics import (
    MetaCollectionDiagnosticSafetyError,
    MetaCollectionValidateOnlyProbe,
    assert_validate_only_transport,
    build_inline_ad_validate_only_payload,
    build_standalone_validate_only_payload,
    sanitized_collection_request_shape,
)
from meta_posting_service import (
    PostingValidationError,
    SupabasePostingStore,
    build_collection_creative_payload,
)


ROOT = Path(__file__).resolve().parents[1]


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


class PostingCollectionDiagnosticIntegrationTests(unittest.TestCase):
    @staticmethod
    def failed_job():
        return {
            "submission_id": "11111111-1111-4111-8111-111111111111",
            "status": "FAILED",
            "product_title": "Six Laps Ahead Peter Brock Wall Art",
            "product_set_id": "peter-brock-set",
            "campaign_id": "120249720387120554",
            "adset_id": "120249720389890554",
            "ad_results": [
                {
                    "index": 1,
                    "ad_name": "Six Laps Ahead Peter Brock IA 1",
                    "meta_image_hash": "route-1-image-hash",
                    "meta_instant_experience_id": "1390026833255926",
                    "status": "FAILED",
                }
            ],
        }

    class FakeService:
        def __init__(self, record):
            self.record = record
            self.read_calls = []
            self.create_paused_campaign = mock.Mock(
                side_effect=AssertionError("persistent creation must not run")
            )

        def failed_collection_diagnostic_job(self, **kwargs):
            self.read_calls.append(dict(kwargs))
            return dict(self.record)

    class FakeClient:
        page_id = "page-1"
        instagram_user_id = "ig-1"
        config = {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "EAA-ad-token-never-render",
            "page_access_token": "EAA-page-token-never-render",
        }

    class FakeProbe:
        def __init__(self, test_a, test_b):
            self.test_a = test_a
            self.test_b = test_b
            self.calls = []

        def run_ab(self, **kwargs):
            self.calls.append(dict(kwargs))
            return self.test_a, self.test_b

    def test_ui_control_is_posting_only_and_normal_create_control_is_unchanged(self):
        posting_source = (ROOT / "ads_posting_page.py").read_text(encoding="utf-8")
        self.assertEqual(
            posting_source.count('"Run Collection Validation — No Ads Created"'),
            1,
        )
        self.assertIn(
            '"Uses Meta validate_only. Creates no campaign, ad set, creative or ad."',
            posting_source,
        )
        self.assertIn(
            '"Create 3 Paused Meta Ads", type="primary", use_container_width=True,',
            posting_source,
        )
        for path in (ROOT / "ads_page.py", ROOT / "ads_creative_refresh.py"):
            self.assertNotIn(
                "Run Collection Validation — No Ads Created",
                path.read_text(encoding="utf-8"),
            )

    def test_ui_runner_consumes_current_state_and_persisted_route_metadata(self):
        service = self.FakeService(self.failed_job())
        probe = self.FakeProbe(
            {
                "validated": False,
                "http_status": 400,
                "error_code": 100,
                "error_subcode": 1990065,
                "safe_error": "Invalid Collection contract",
            },
            {"validated": True, "http_status": 200, "response": {"success": True}},
        )
        result = ads_posting_page.run_collection_validation_from_posting_state(
            submission_id="11111111-1111-4111-8111-111111111111",
            product_title="Six Laps Ahead Peter Brock Wall Art",
            product_set_id="peter-brock-set",
            product_url="https://sportscaveshop.com/products/peter-brock",
            primary_text="Current visible Ad 1 primary text",
            headline="Current visible Ad 1 headline",
            service=service,
            client=self.FakeClient(),
            probe=probe,
        )

        self.assertEqual(
            service.read_calls,
            [
                {
                    "submission_id": "11111111-1111-4111-8111-111111111111",
                    "product_title": "Six Laps Ahead Peter Brock Wall Art",
                    "product_set_id": "peter-brock-set",
                }
            ],
        )
        call = probe.calls[0]
        self.assertEqual(call["adset_id"], "120249720389890554")
        creative = call["creative_payload"]
        self.assertEqual(creative["product_set_id"], "peter-brock-set")
        self.assertEqual(creative["image_hash"], "route-1-image-hash")
        link_data = creative["object_story_spec"]["link_data"]
        self.assertEqual(link_data["message"], "Current visible Ad 1 primary text")
        self.assertEqual(link_data["name"], "Current visible Ad 1 headline")
        self.assertEqual(
            link_data["link"], "https://fb.com/canvas_doc/1390026833255926"
        )
        self.assertEqual(result["persistent_meta_writes"], "NONE")
        self.assertIn("Inline Collection creation validated", result["decision"])
        rendered = json.dumps(result)
        self.assertNotIn(self.FakeClient.config["access_token"], rendered)
        self.assertNotIn(self.FakeClient.config["page_access_token"], rendered)
        service.create_paused_campaign.assert_not_called()

    def test_runner_requires_no_manual_hash_product_set_or_meta_ids(self):
        parameters = inspect.signature(
            ads_posting_page.run_collection_validation_from_posting_state
        ).parameters
        for forbidden in (
            "image_hash",
            "campaign_id",
            "adset_id",
            "instant_experience_id",
            "page_id",
            "instagram_user_id",
        ):
            self.assertNotIn(forbidden, parameters)
        self.assertIn("product_set_id", parameters)

    def test_failed_probe_results_do_not_call_persistent_posting_methods(self):
        service = self.FakeService(self.failed_job())
        probe = self.FakeProbe(
            {"validated": False, "error_code": 100, "safe_error": "A failed"},
            {"validated": False, "error_code": 100, "safe_error": "B failed"},
        )
        result = ads_posting_page.run_collection_validation_from_posting_state(
            submission_id="new-current-submission",
            product_title="Six Laps Ahead Peter Brock Wall Art",
            product_set_id="peter-brock-set",
            product_url="https://sportscaveshop.com/products/peter-brock",
            primary_text="Current primary text",
            headline="Current headline",
            service=service,
            client=self.FakeClient(),
            probe=probe,
        )
        self.assertIn("Neither direct path validates", result["decision"])
        service.create_paused_campaign.assert_not_called()

    def test_failed_job_lookup_is_select_only_and_never_commits_or_migrates(self):
        record = self.failed_job()
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [record]
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        backend = mock.Mock()
        backend.is_configured.return_value = True
        backend.connect.return_value = connection
        store = SupabasePostingStore()

        with mock.patch.object(store, "_backend", return_value=backend):
            resolved = store.failed_collection_diagnostic_job(
                submission_id=record["submission_id"],
                product_title=record["product_title"],
                product_set_id=record["product_set_id"],
            )

        self.assertEqual(resolved["adset_id"], "120249720389890554")
        backend.ensure_ads_schema.assert_not_called()
        connection.commit.assert_not_called()
        statements = [str(call.args[0]).strip().upper() for call in cursor.execute.call_args_list]
        self.assertTrue(statements)
        self.assertTrue(all(statement.startswith("SELECT") for statement in statements))

    def test_context_rejects_incomplete_partial_job_before_probe(self):
        record = self.failed_job()
        record["ad_results"][0].pop("meta_image_hash")
        probe = self.FakeProbe({"validated": True}, {"validated": True})
        with self.assertRaisesRegex(PostingValidationError, "route 1 Meta image hash"):
            ads_posting_page.run_collection_validation_from_posting_state(
                submission_id=record["submission_id"],
                product_title=record["product_title"],
                product_set_id=record["product_set_id"],
                product_url="https://sportscaveshop.com/products/peter-brock",
                primary_text="Current primary text",
                headline="Current headline",
                service=self.FakeService(record),
                client=self.FakeClient(),
                probe=probe,
            )
        self.assertEqual(probe.calls, [])


if __name__ == "__main__":
    unittest.main()
