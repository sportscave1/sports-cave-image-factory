import inspect
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import ads_posting_page
import meta_ads_client
from meta_collection_template_copy import (
    COLLECTION_TEMPLATE_AD_ENV_KEY,
    INITIAL_COLLECTION_TEMPLATE_AD_ID,
    RENAME_READBACK_DELAYS_SECONDS,
    REQUIRED_COLLECTION_FEATURES,
    MetaCollectionTemplateCopySafetyError,
    MetaCollectionTemplateCopyService,
    MetaCollectionTemplateCopyVerificationError,
    build_paused_template_copy_request,
    collection_features_match,
    configured_collection_template_ad_id,
    sanitized_template_copy_error,
)
from meta_posting_service import build_collection_creative_payload


ROOT = Path(__file__).resolve().parents[1]
SOURCE_AD_ID = "120249557468150554"
TARGET_ADSET_ID = "120249720389890554"
TARGET_IA_ID = "1390026833255926"


def target_creative():
    return build_collection_creative_payload(
        name="Six Laps Ahead Peter Brock IA 1 | Collection",
        page_id="page-1",
        instagram_user_id="ig-1",
        image_hash="peter-route-1-image-hash",
        canvas_id=TARGET_IA_ID,
        product_set_id="peter-brock-product-set",
        destination_url="https://sportscaveshop.com/products/peter-brock",
        primary_text="Peter Brock primary text",
        headline="Peter Brock headline",
    )


def source_creative():
    creative = target_creative()
    creative["id"] = "source-creative"
    creative["name"] = "LEGENDS IA 2 | Collection"
    creative["image_hash"] = "aaron-judge-image-hash"
    creative["product_set_id"] = "aaron-judge-product-set"
    link = creative["object_story_spec"]["link_data"]
    link["link"] = "https://fb.com/canvas_doc/aaron-judge-ia"
    link["message"] = "Aaron Judge primary text"
    link["name"] = "Aaron Judge headline"
    link["image_hash"] = "aaron-judge-image-hash"
    return creative


class FakeTemplateCopyClient:
    def __init__(self, *, invalid_target=False, rename_readback_names=()):
        self.invalid_target = invalid_target
        self.copy_calls = []
        self.rename_calls = []
        self.ad_reads = []
        self.creative_reads = []
        self.copy_exists = False
        self.rename_readback_names = list(rename_readback_names)
        self.rename_requested = False
        self.source_ad = {
            "id": SOURCE_AD_ID,
            "name": "LEGENDS IA 2",
            "status": "ACTIVE",
            "configured_status": "ACTIVE",
            "effective_status": "ACTIVE",
            "adset_id": "source-adset",
            "creative": {"id": "source-creative"},
        }
        self.copied_ad = {
            "id": "copied-ad-1",
            "name": "Six Laps Ahead Peter Brock IA 1",
            "status": "ACTIVE" if invalid_target else "PAUSED",
            "configured_status": "ACTIVE" if invalid_target else "PAUSED",
            "effective_status": "CAMPAIGN_PAUSED",
            "adset_id": TARGET_ADSET_ID,
            "creative": {"id": "copied-creative-1"},
        }

    def ad(self, ad_id):
        self.ad_reads.append(str(ad_id))
        if str(ad_id) == SOURCE_AD_ID:
            return dict(self.source_ad)
        if str(ad_id) == "copied-ad-1":
            copied_ad = dict(self.copied_ad)
            if self.rename_requested and self.rename_readback_names:
                copied_ad["name"] = self.rename_readback_names.pop(0)
                self.copied_ad["name"] = copied_ad["name"]
            return copied_ad
        raise AssertionError(f"Unexpected ad read: {ad_id}")

    def creative(self, creative_id):
        self.creative_reads.append(str(creative_id))
        if str(creative_id) == "source-creative":
            return source_creative()
        if str(creative_id) == "copied-creative-1":
            return {"id": "copied-creative-1", **target_creative()}
        raise AssertionError(f"Unexpected creative read: {creative_id}")

    def ad_copies(self, source_ad_id):
        if str(source_ad_id) != SOURCE_AD_ID:
            raise AssertionError("Wrong source ad")
        return (dict(self.copied_ad),) if self.copy_exists else ()

    def copy_paused_ad_from_template(
        self, *, source_ad_id, target_adset_id, creative_parameters
    ):
        self.copy_calls.append(
            {
                "source_ad_id": source_ad_id,
                "target_adset_id": target_adset_id,
                "creative_parameters": dict(creative_parameters),
            }
        )
        self.copy_exists = True
        return "copied-ad-1"

    def rename_paused_ad(self, ad_id, *, name, protected_source_ad_id=""):
        self.rename_calls.append((ad_id, name, protected_source_ad_id))
        if str(ad_id) == str(protected_source_ad_id):
            raise AssertionError("source ad must never be renamed")
        self.rename_requested = True
        if not self.rename_readback_names:
            self.copied_ad["name"] = str(name)


class MetaCollectionTemplateCopyTransportTests(unittest.TestCase):
    @staticmethod
    def config():
        return {
            "configured": True,
            "ad_account_id": "act_123",
            "access_token": "EAA-ad-token-never-render",
            "page_access_token": "EAA-page-token-never-render",
            "api_version": "v26.0",
            "page_id": "page-1",
            "instagram_user_id": "ig-1",
        }

    def test_configuration_prefers_env_and_allows_initial_known_good_fallback(self):
        self.assertEqual(configured_collection_template_ad_id({}), INITIAL_COLLECTION_TEMPLATE_AD_ID)
        self.assertEqual(
            configured_collection_template_ad_id(
                {COLLECTION_TEMPLATE_AD_ENV_KEY: "dedicated-template-ad"}
            ),
            "dedicated-template-ad",
        )

    def test_request_builder_forces_paused_and_preserves_full_peter_overrides(self):
        request = build_paused_template_copy_request(
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
        )
        self.assertEqual(request["adset_id"], TARGET_ADSET_ID)
        self.assertEqual(request["status_option"], "PAUSED")
        self.assertEqual(request["creative_parameters"], target_creative())

    @mock.patch("meta_ads_client._post", return_value={"id": "copied-ad-1"})
    def test_client_posts_only_to_source_copies_with_paused_status(self, post):
        client = meta_ads_client.MetaPostingClient(self.config())
        copied_id = client.copy_paused_ad_from_template(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
        )

        self.assertEqual(copied_id, "copied-ad-1")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], f"{SOURCE_AD_ID}/copies")
        data = post.call_args.kwargs["data"]
        self.assertEqual(set(data), {"adset_id", "status_option", "creative_parameters"})
        self.assertEqual(data["adset_id"], TARGET_ADSET_ID)
        self.assertEqual(data["status_option"], "PAUSED")
        self.assertEqual(json.loads(data["creative_parameters"]), target_creative())
        self.assertNotIn("access_token", data)

    @mock.patch("meta_ads_client._request")
    def test_readback_methods_fetch_copies_ad_and_full_creative_without_writes(self, request):
        request.return_value = {"id": "copied-creative-1"}
        client = meta_ads_client.MetaPostingClient(self.config())
        client.ad("copied-ad-1")
        client.creative("copied-creative-1")
        self.assertEqual([call.args[0] for call in request.call_args_list], ["copied-ad-1", "copied-creative-1"])
        self.assertIn("product_set_id", request.call_args_list[1].kwargs["params"]["fields"])
        self.assertIn("degrees_of_freedom_spec", request.call_args_list[1].kwargs["params"]["fields"])

    @mock.patch("meta_ads_client._paged_get", return_value={"rows": ({"id": "copy-1"},)})
    def test_copy_reconciliation_is_read_only(self, paged_get):
        client = meta_ads_client.MetaPostingClient(self.config())
        self.assertEqual(client.ad_copies(SOURCE_AD_ID), ({"id": "copy-1"},))
        self.assertEqual(paged_get.call_args.args[0], f"{SOURCE_AD_ID}/copies")

    def test_meta_errors_are_sanitized_before_ui_storage(self):
        config = self.config()
        with mock.patch.dict(os.environ, {
            "META_ACCESS_TOKEN": config["access_token"],
            "META_PAGE_ACCESS_TOKEN": config["page_access_token"],
        }):
            result = sanitized_template_copy_error(
                meta_ads_client.MetaAdsApiError(
                    f"Rejected {config['access_token']} and {config['page_access_token']}",
                    status_code=400,
                    error_code=100,
                    error_subcode=1990065,
                    error_user_msg=f"Bad token {config['access_token']}",
                    fbtrace_id="safe-trace",
                )
            )
        rendered = json.dumps(result)
        self.assertNotIn(config["access_token"], rendered)
        self.assertNotIn(config["page_access_token"], rendered)
        self.assertIn("[redacted]", rendered)
        self.assertEqual(result["error_subcode"], 1990065)


class MetaCollectionTemplateCopyVerificationTests(unittest.TestCase):
    def test_collection_features_are_semantic_subset_not_exact_object(self):
        actual = {
            name: {"enroll_status": enrollment}
            for name, enrollment in REQUIRED_COLLECTION_FEATURES.items()
        }
        actual.update({
            "meta_generated_feature": {"enroll_status": "OPT_OUT"},
        })
        self.assertTrue(collection_features_match(actual))
        actual["product_browsing"]["enroll_status"] = "OPT_IN"
        self.assertFalse(collection_features_match(actual))

    def test_one_copy_is_created_paused_and_all_peter_values_read_back(self):
        client = FakeTemplateCopyClient()
        result = MetaCollectionTemplateCopyService(client).create_one_paused_copy(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
        )

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["created_now"])
        self.assertEqual(result["persistent_meta_writes"], "ONE PAUSED AD")
        self.assertEqual(result["copied_status"], "PAUSED")
        self.assertEqual(result["copied_configured_status"], "PAUSED")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(len(client.copy_calls), 1)
        copy_call = client.copy_calls[0]
        self.assertEqual(copy_call["source_ad_id"], SOURCE_AD_ID)
        self.assertEqual(copy_call["target_adset_id"], TARGET_ADSET_ID)
        target = copy_call["creative_parameters"]
        link = target["object_story_spec"]["link_data"]
        self.assertEqual(link["link"], f"https://fb.com/canvas_doc/{TARGET_IA_ID}")
        self.assertEqual(link["message"], "Peter Brock primary text")
        self.assertEqual(link["name"], "Peter Brock headline")
        self.assertEqual(link["image_hash"], "peter-route-1-image-hash")
        self.assertEqual(link["retailer_item_ids"], ["0", "0", "0", "0"])
        self.assertEqual(target["product_set_id"], "peter-brock-product-set")
        self.assertNotIn("Aaron Judge", json.dumps(target))
        self.assertEqual(client.source_ad["status"], "ACTIVE")
        self.assertEqual(client.source_ad["creative"]["id"], "source-creative")
        self.assertEqual(client.ad_reads.count(SOURCE_AD_ID), 2)

    def test_existing_single_copy_is_reconciled_without_a_second_post(self):
        client = FakeTemplateCopyClient()
        client.copy_exists = True
        result = MetaCollectionTemplateCopyService(client).create_one_paused_copy(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["reconciled_existing_copy"])
        self.assertEqual(client.copy_calls, [])

    def test_rename_stale_once_then_expected_name_passes_without_real_sleep(self):
        expected_name = "Six Laps Ahead Peter Brock IA 1"
        client = FakeTemplateCopyClient(
            rename_readback_names=("LEGENDS IA 2 – Copy", expected_name)
        )
        client.copied_ad["name"] = "LEGENDS IA 2 – Copy"
        sleeper = mock.Mock()
        result = MetaCollectionTemplateCopyService(
            client,
            sleeper=sleeper,
            rename_readback_delays=(0.0, 0.4, 0.8),
        ).create_one_paused_copy(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
            expected_ad_name=expected_name,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["rename_readback_attempts"], 2)
        sleeper.assert_called_once_with(0.4)

    def test_rename_stale_three_times_then_expected_name_passes(self):
        expected_name = "Six Laps Ahead Peter Brock IA 2"
        client = FakeTemplateCopyClient(
            rename_readback_names=(
                "LEGENDS IA 2 – Copy",
                "LEGENDS IA 2 – Copy",
                "LEGENDS IA 2 – Copy",
                expected_name,
            )
        )
        sleeps = []
        result = MetaCollectionTemplateCopyService(
            client,
            sleeper=sleeps.append,
            rename_readback_delays=(0.0, 0.4, 0.8, 1.2, 2.0),
        ).create_one_paused_copy(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
            expected_ad_name=expected_name,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["rename_readback_attempts"], 4)
        self.assertEqual(sleeps, [0.4, 0.8, 1.2])

    def test_rename_never_propagates_and_wrong_name_remains_fail_closed(self):
        expected_name = "Six Laps Ahead Peter Brock IA 2"
        client = FakeTemplateCopyClient(
            rename_readback_names=("Old name", "Still old", "Wrong final name")
        )
        sleeps = []
        with self.assertRaises(MetaCollectionTemplateCopyVerificationError) as caught:
            MetaCollectionTemplateCopyService(
                client,
                sleeper=sleeps.append,
                rename_readback_delays=(0.0, 0.4, 0.8),
            ).create_one_paused_copy(
                source_ad_id=SOURCE_AD_ID,
                target_adset_id=TARGET_ADSET_ID,
                creative_parameters=target_creative(),
                expected_ad_name=expected_name,
            )

        self.assertEqual(caught.exception.result["failed_checks"], ["route_ad_name"])
        self.assertEqual(caught.exception.result["rename_readback_attempts"], 3)
        self.assertEqual(sleeps, [0.4, 0.8])
        self.assertFalse(caught.exception.result["checks"]["route_ad_name"])

    def test_existing_correct_route_name_does_not_rename_or_sleep(self):
        client = FakeTemplateCopyClient()
        client.copy_exists = True
        sleeper = mock.Mock()
        result = MetaCollectionTemplateCopyService(
            client,
            sleeper=sleeper,
        ).create_one_paused_copy(
            source_ad_id=SOURCE_AD_ID,
            target_adset_id=TARGET_ADSET_ID,
            creative_parameters=target_creative(),
            expected_ad_name="Six Laps Ahead Peter Brock IA 1",
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["rename_readback_attempts"], 0)
        self.assertEqual(client.rename_calls, [])
        sleeper.assert_not_called()

    def test_default_rename_readback_window_is_bounded_to_eight_point_four_seconds(self):
        self.assertEqual(RENAME_READBACK_DELAYS_SECONDS[0], 0.0)
        self.assertEqual(sum(RENAME_READBACK_DELAYS_SECONDS), 8.4)

    def test_failed_readback_blocks_any_second_copy(self):
        client = FakeTemplateCopyClient(invalid_target=True)
        service = MetaCollectionTemplateCopyService(client)
        with self.assertRaises(MetaCollectionTemplateCopyVerificationError) as first:
            service.create_one_paused_copy(
                source_ad_id=SOURCE_AD_ID,
                target_adset_id=TARGET_ADSET_ID,
                creative_parameters=target_creative(),
            )
        self.assertIn("Further copies are blocked", str(first.exception))
        self.assertEqual(len(client.copy_calls), 1)

        with self.assertRaises(MetaCollectionTemplateCopyVerificationError):
            service.create_one_paused_copy(
                source_ad_id=SOURCE_AD_ID,
                target_adset_id=TARGET_ADSET_ID,
                creative_parameters=target_creative(),
            )
        self.assertEqual(len(client.copy_calls), 1)

    def test_multiple_existing_target_copies_fail_closed(self):
        client = FakeTemplateCopyClient()
        client.ad_copies = mock.Mock(return_value=(dict(client.copied_ad), dict(client.copied_ad)))
        with self.assertRaises(MetaCollectionTemplateCopySafetyError):
            MetaCollectionTemplateCopyService(client).create_one_paused_copy(
                source_ad_id=SOURCE_AD_ID,
                target_adset_id=TARGET_ADSET_ID,
                creative_parameters=target_creative(),
            )
        self.assertEqual(client.copy_calls, [])


class PostingTemplateCopyIntegrationTests(unittest.TestCase):
    @staticmethod
    def failed_job():
        return {
            "submission_id": "11111111-1111-4111-8111-111111111111",
            "status": "FAILED",
            "product_title": "Six Laps Ahead Peter Brock Wall Art",
            "product_set_id": "peter-brock-product-set",
            "campaign_id": "120249720387120554",
            "adset_id": TARGET_ADSET_ID,
            "ad_results": [
                {
                    "index": 1,
                    "ad_name": "Six Laps Ahead Peter Brock IA 1",
                    "meta_image_hash": "peter-route-1-image-hash",
                    "meta_instant_experience_id": TARGET_IA_ID,
                    "status": "FAILED",
                }
            ],
        }

    class FakePostingService:
        def __init__(self):
            self.read_calls = []
            self.update_stage = mock.Mock(side_effect=AssertionError("ledger must not change"))
            self.create_paused_campaign = mock.Mock(
                side_effect=AssertionError("normal production must not run")
            )

        def failed_collection_diagnostic_job(self, **kwargs):
            self.read_calls.append(dict(kwargs))
            return PostingTemplateCopyIntegrationTests.failed_job()

    class FakeClient:
        page_id = "page-1"
        instagram_user_id = "ig-1"

    class FakeCopyService:
        def __init__(self):
            self.calls = []

        def create_one_paused_copy(self, **kwargs):
            self.calls.append(dict(kwargs))
            return {"status": "PASS", "persistent_meta_writes": "ONE PAUSED AD"}

    def test_runner_uses_current_copy_and_failed_route_metadata_without_ledger_write(self):
        posting_service = self.FakePostingService()
        copy_service = self.FakeCopyService()
        with mock.patch.dict(os.environ, {COLLECTION_TEMPLATE_AD_ENV_KEY: SOURCE_AD_ID}):
            result = ads_posting_page.run_collection_template_copy_from_posting_state(
                submission_id="11111111-1111-4111-8111-111111111111",
                product_title="Six Laps Ahead Peter Brock Wall Art",
                product_set_id="peter-brock-product-set",
                product_url="https://sportscaveshop.com/products/peter-brock",
                primary_text="Current visible Peter Brock primary text",
                headline="Current visible Peter Brock headline",
                service=posting_service,
                client=self.FakeClient(),
                template_copy_service=copy_service,
            )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(copy_service.calls), 1)
        call = copy_service.calls[0]
        self.assertEqual(call["source_ad_id"], SOURCE_AD_ID)
        self.assertEqual(call["target_adset_id"], TARGET_ADSET_ID)
        creative = call["creative_parameters"]
        link = creative["object_story_spec"]["link_data"]
        self.assertEqual(link["message"], "Current visible Peter Brock primary text")
        self.assertEqual(link["name"], "Current visible Peter Brock headline")
        self.assertEqual(link["link"], f"https://fb.com/canvas_doc/{TARGET_IA_ID}")
        self.assertEqual(creative["product_set_id"], "peter-brock-product-set")
        posting_service.update_stage.assert_not_called()
        posting_service.create_paused_campaign.assert_not_called()

    def test_runner_requires_no_manual_meta_ids_or_image_hash(self):
        parameters = inspect.signature(
            ads_posting_page.run_collection_template_copy_from_posting_state
        ).parameters
        for forbidden in (
            "source_ad_id",
            "campaign_id",
            "adset_id",
            "instant_experience_id",
            "image_hash",
            "page_id",
            "instagram_user_id",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_ui_is_posting_only_and_normal_three_ad_button_is_unchanged(self):
        posting_source = (ROOT / "ads_posting_page.py").read_text(encoding="utf-8")
        self.assertEqual(posting_source.count('"Create 1 Paused Template Copy"'), 1)
        self.assertIn(
            '"Create 3 Paused Meta Ads", type="primary", use_container_width=True,',
            posting_source,
        )
        self.assertIn("COLLECTION_TEMPLATE_COPY_ATTEMPTED_KEY", posting_source)
        for path in (ROOT / "ads_page.py", ROOT / "ads_creative_refresh.py"):
            self.assertNotIn(
                "Create 1 Paused Template Copy", path.read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
