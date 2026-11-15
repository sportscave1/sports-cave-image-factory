from copy import deepcopy
import io
import json
import unittest
from unittest import mock

from meta_ads_client import MetaAdsApiError
from scripts import audit_meta_carousel_settings as audit


class CarouselSettingsAuditTests(unittest.TestCase):
    def setUp(self):
        self.config = {"configured": True, "ad_account_id": "act_10", "access_token": "private-token-value", "app_secret": "private-secret-value", "app_id": "50", "api_version": "v26.0"}
        self.objects = {
            "11": {"id": "11", "account_id": "10", "campaign_id": "20", "adset_id": "30", "creative": {"id": "40"}, "status": "PAUSED", "tracking_specs": [{"action.type": ["offsite_conversion"], "fb_pixel": ["60"]}]},
            "20": {"id": "20", "objective": "OUTCOME_SALES"},
            "30": {"id": "30", "promoted_object": {"pixel_id": "60", "custom_event_type": "PURCHASE"}, "optimization_goal": "OFFSITE_CONVERSIONS"},
            "40": {"id": "40", "object_story_spec": {"link_data": {"multi_share_end_card": True, "multi_share_optimized": True}}, "degrees_of_freedom_spec": {"creative_features_spec": {"profile_card": {"enroll_status": "OPT_IN"}}}, "asset_feed_spec": {"audios": [{"id": "70"}]}},
            "50": {"id": "50", "name": "Sports Cave OS"},
        }
        self.read = mock.Mock(side_effect=lambda path, **kwargs: deepcopy(self.objects[path]))

    def test_reads_existing_linked_objects_and_configured_app_without_writes(self):
        with mock.patch("meta_ads_client._post", side_effect=AssertionError("No writes")):
            result = audit.audit_carousel_settings(self.config, ad_id="11", read=self.read)
        self.assertEqual([call.args[0] for call in self.read.call_args_list], ["11", "20", "30", "40", "50"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["configured_app"]["verified"])
        self.assertEqual(result["configured_app"]["name"], "Sports Cave OS")
        self.assertEqual(result["ad"]["tracking_specs"], self.objects["11"]["tracking_specs"])
        self.assertEqual(result["creative"]["asset_feed_spec"], self.objects["40"]["asset_feed_spec"])
        self.assertFalse(result["all_optimisations_verified"])
        fields = self.read.call_args_list[0].kwargs["params"]["fields"]
        self.assertIn("tracking_and_conversion_with_defaults", fields)
        self.assertIn("conversion_domain", fields)

    def test_missing_fields_are_reported_as_unknown_not_opted_out(self):
        result = audit.audit_carousel_settings(self.config, ad_id="11", read=self.read)
        self.assertEqual(result["ad"]["_unavailable_fields"]["conversion_domain"]["reason"], "omitted_by_meta")
        self.assertNotIn("conversion_domain", result["ad"])
        self.assertNotIn("degrees_of_freedom_spec", result["creative"]["_unavailable_fields"])

    def test_unsupported_optional_field_does_not_hide_other_readback(self):
        def read(path, *, params, config):
            if path == "11" and "creative_automation_spec" in params["fields"]:
                raise MetaAdsApiError("Tried accessing nonexisting field", error_code=100)
            return deepcopy(self.objects[path])
        result = audit.audit_carousel_settings(self.config, ad_id="11", read=read)
        self.assertEqual(result["ad"]["_unavailable_fields"]["creative_automation_spec"]["reason"], "unsupported_or_unavailable")
        self.assertEqual(result["ad"]["tracking_specs"], self.objects["11"]["tracking_specs"])

    def test_auth_failure_is_not_swallowed_as_optional_field_omission(self):
        with self.assertRaises(MetaAdsApiError):
            audit.audit_carousel_settings(self.config, ad_id="11", read=mock.Mock(side_effect=MetaAdsApiError("Invalid token", error_code=190)))

    def test_wrong_account_stops_before_reading_related_objects(self):
        self.objects["11"]["account_id"] = "999"
        with self.assertRaisesRegex(ValueError, "configured ad account"):
            audit.audit_carousel_settings(self.config, ad_id="11", read=self.read)
        self.assertEqual(self.read.call_count, 1)

    def test_unverified_app_is_reported_without_inventing_an_id(self):
        self.objects["50"] = {}
        result = audit.audit_carousel_settings(self.config, ad_id="11", read=self.read)
        self.assertFalse(result["configured_app"]["verified"])
        self.assertIsNone(result["configured_app"]["id"])

    def test_report_redacts_tokens_and_secrets(self):
        self.objects["40"]["object_story_spec"].update(access_token="private-token-value", text="private-secret-value", url="https://example.test/?access_token=private-token-value")
        report = json.dumps(audit.audit_carousel_settings(self.config, ad_id="11", read=self.read))
        self.assertNotIn("private-token-value", report)
        self.assertNotIn("private-secret-value", report)

    def test_dry_run_and_missing_credentials_send_no_requests(self):
        with mock.patch.object(audit, "_request", side_effect=AssertionError("No Graph request")), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(audit.main([]), 0)
            with self.assertRaisesRegex(ValueError, "not configured"):
                audit.audit_carousel_settings({}, ad_id="11")


if __name__ == "__main__":
    unittest.main()
