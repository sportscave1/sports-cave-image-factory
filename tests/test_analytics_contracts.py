from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import analytics_contracts
import analytics_reporting


class AnalyticsDateContractTests(unittest.TestCase):
    def test_exact_inclusive_presets_and_previous_period(self):
        today = date(2026, 8, 17)
        expected = {
            "Today": (today, today, 1),
            "Yesterday": (date(2026, 8, 16), date(2026, 8, 16), 1),
            "Last 7 days": (date(2026, 8, 11), today, 7),
            "Last 28 days": (date(2026, 7, 21), today, 28),
            "Last 30 days": (date(2026, 7, 19), today, 30),
            "Last 90 days": (date(2026, 5, 20), today, 90),
        }
        for preset, (start, end, days) in expected.items():
            period = analytics_contracts.resolve_date_range(
                preset, timezone_name="Australia/Sydney", comparison="Previous period", today=today,
            )
            self.assertEqual((period["start_date"], period["end_date"], period["inclusive_days"]), (start, end, days))
            self.assertEqual(period["previous_end_date"], start - timedelta(days=1))
            self.assertEqual((period["previous_end_date"] - period["previous_start_date"]).days + 1, days)

    def test_property_timezone_dst_and_leap_day_previous_year(self):
        now = datetime(2026, 10, 4, 0, 30, tzinfo=ZoneInfo("Australia/Sydney"))
        self.assertEqual(analytics_contracts.property_today("Australia/Sydney", now=now), date(2026, 10, 4))
        period = analytics_contracts.resolve_date_range(
            "Custom",
            timezone_name="Australia/Sydney",
            comparison="Previous year",
            custom_start=date(2024, 2, 29),
            custom_end=date(2024, 2, 29),
            today=date(2024, 3, 10),
        )
        self.assertEqual(period["previous_start_date"], date(2023, 2, 28))
        self.assertEqual(period["previous_end_date"], date(2023, 2, 28))

    def test_rate_zero_denominator(self):
        self.assertIsNone(analytics_contracts.safe_rate(4, 0))
        self.assertEqual(analytics_contracts.safe_rate(1, 4), 0.25)

    def test_overview_total_contract_never_sums_daily_users(self):
        contract = analytics_contracts.report_contract("overview_totals")
        self.assertEqual(contract.dimensions, ())
        self.assertIn("activeUsers", contract.metrics)
        self.assertNotIn("date", contract.dimensions)

    def test_each_selectable_trend_contract_has_one_exact_metric(self):
        expected = {
            "trend": "sessions",
            "trend_active_users": "activeUsers",
            "trend_views": "screenPageViews",
            "trend_key_events": "keyEvents",
        }
        for key, metric in expected.items():
            contract = analytics_contracts.report_contract(key)
            self.assertEqual(contract.dimensions, ("date",))
            self.assertEqual(contract.metrics, (metric,))


class FakeReportingClient:
    def __init__(self):
        self.calls = []

    def _post(self, endpoint, payload, stage=""):
        self.calls.append((endpoint, payload, stage))
        if endpoint.endswith(":checkCompatibility"):
            return {
                "dimensionCompatibilities": [
                    {"dimensionMetadata": {"apiName": "sessionDefaultChannelGroup"}, "compatibility": "COMPATIBLE"}
                ],
                "metricCompatibilities": [
                    {"metricMetadata": {"apiName": name}, "compatibility": "COMPATIBLE"}
                    for name in analytics_contracts.report_contract("traffic_acquisition").metrics
                ],
            }
        offset = int(payload["offset"])
        rows = [
            {
                "dimensionValues": [{"value": f"Channel {index}"}],
                "metricValues": [{"value": str(index + 1)} for _ in payload["metrics"]],
            }
            for index in range(offset, min(offset + 2, 3))
        ]
        return {
            "rowCount": 3,
            "dimensionHeaders": [{"name": "sessionDefaultChannelGroup"}],
            "metricHeaders": payload["metrics"],
            "rows": rows,
            "metadata": {"timeZone": "Australia/Sydney", "currencyCode": "AUD", "subjectToThresholding": True},
            "dataLossFromOtherRow": True,
        }


class AnalyticsClientTests(unittest.TestCase):
    def test_paginates_and_caches_compatibility(self):
        fake = FakeReportingClient()
        client = analytics_reporting.CanonicalGA4Client("token", reporting_client=fake)
        with patch.object(analytics_reporting, "PAGE_SIZE", 2):
            first = client.fetch_report("355333982", "traffic_acquisition", date(2026, 8, 1), date(2026, 8, 7))
            second = client.fetch_report("355333982", "traffic_acquisition", date(2026, 8, 8), date(2026, 8, 14))
        compatibility_calls = [call for call in fake.calls if call[0].endswith(":checkCompatibility")]
        offsets = [int(call[1]["offset"]) for call in fake.calls if call[0].endswith(":runReport")]
        self.assertEqual(len(compatibility_calls), 1)
        self.assertEqual(offsets, [0, 2, 0, 2])
        self.assertTrue(first["complete"])
        self.assertEqual(first["row_count"], 3)
        self.assertEqual(first["property_timezone"], "Australia/Sydney")
        self.assertEqual(first["currency"], "AUD")
        self.assertEqual(first["quality"]["status"], "Qualified")
        self.assertTrue(first["quality"]["thresholded"])
        self.assertTrue(first["quality"]["data_loss_from_other"])
        self.assertIn("property_quota", first["quality"])
        self.assertNotEqual(first["request_hash"], second["request_hash"])

    def test_reconciliation_tolerates_one_minor_currency_unit_only(self):
        direct = {"request_hash": "same", "rows": [{"metrics": {"purchaseRevenue": "100.00", "sessions": "5"}}]}
        stored = {"request_hash": "same", "response_rows": direct["rows"]}
        self.assertEqual(
            analytics_reporting.reconcile_layers(direct, stored, {"purchaseRevenue": "100.01", "sessions": 5})["divergence"],
            "none",
        )
        self.assertEqual(
            analytics_reporting.reconcile_layers(direct, stored, {"purchaseRevenue": "100.02", "sessions": 5})["divergence"],
            "application_reader_or_renderer",
        )

    def test_custom_queue_saves_complete_reports_and_marks_failures(self):
        class Store:
            def __init__(self):
                self.saved = []
                self.completed = []

            def claim_report_queue(self, limit=20):
                return [{
                    "id": "queue-1", "property_id": "properties/1",
                    "contract_key": "overview_totals",
                    "start_date": date(2026, 6, 1), "end_date": date(2026, 6, 30),
                    "property_currency": "AUD",
                }]

            def save_report(self, report):
                self.saved.append(report)

            def complete_report_request(self, request_id, error=""):
                self.completed.append((request_id, error))

        client = unittest.mock.Mock()
        client.fetch_report.return_value = {"complete": True}
        store = Store()
        result = analytics_reporting.process_custom_report_queue(client, store)
        self.assertEqual(result, {"written": 1, "failures": []})
        self.assertEqual(store.saved, [{"complete": True}])
        self.assertEqual(store.completed, [("queue-1", "")])


if __name__ == "__main__":
    unittest.main()
