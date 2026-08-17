from datetime import date
from decimal import Decimal
import inspect
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import google_seo_import
import run_migrations
import seo_growth_intelligence
import seo_live_analytics
import seo_navigation
import seo_page


ROOT = Path(__file__).resolve().parents[1]


def source_health(*available, ga4_status="ready", refresh_status="completed", snapshot=False):
    dates = {
        "gsc": "2026-08-12",
        "ga4": "2026-08-10",
        "shopify": "2026-08-13",
        "reconciliation": "2026-08-09",
    }
    result = {}
    for source in ("gsc", "ga4", "shopify", "reconciliation"):
        is_available = source in available
        result[source] = {
            "available": is_available,
            "status": ga4_status if source == "ga4" and is_available else ("ready" if is_available else "no_saved_rows"),
            "identifier": f"{source}-id",
            "earliest_date": "2026-01-01" if is_available else "",
            "through_date": dates[source] if is_available else "",
            "rows": 20 if is_available else 0,
            "source_label": source,
        }
    result["snapshot"] = {
        "available": snapshot,
        "status": "completed" if snapshot else "not_refreshed",
        "through_date": "2026-08-09" if snapshot else "",
    }
    result["refresh"] = {"status": refresh_status}
    return result


class FakeLiveReader(seo_live_analytics.PostgresSEOLiveAnalyticsReader):
    def __init__(self, health):
        self.health = health
        self.read_errors = {}

    def source_health(self):
        return self.health

    def _canonical_metadata(self, _paths):
        return {}

    def _gsc_bundle(self, _health, _period, _market, _device, _compare):
        return {
            "current": {
                "organic_clicks": Decimal("12"),
                "organic_impressions": Decimal("300"),
                "ctr": Decimal("0.04"),
                "average_position": Decimal("8.5"),
            },
            "previous": {
                "organic_clicks": Decimal("10"),
                "organic_impressions": Decimal("250"),
                "ctr": Decimal("0.04"),
                "average_position": Decimal("9.5"),
            },
            "daily": [{"date": "2026-08-12", "organic_clicks": Decimal("12")}],
            "previous_daily": [{"date": "2026-07-15", "organic_clicks": Decimal("10")}],
            "top_queries": [{"query": "sports wall art", "clicks": 12}],
            "top_pages": [],
            "breakdowns": [{"country_code": "AU", "device": "MOBILE", "clicks": 12, "impressions": 300}],
        }

    def _ga4_bundle(self, _health, _period, _market, _device, _compare):
        return {
            "current": {
                "organic_sessions": Decimal("40"),
                "engaged_sessions": Decimal("24"),
                "engagement_rate": Decimal("0.6"),
                "ga4_attributed_purchases": Decimal("2"),
                "ga4_attributed_revenue": Decimal("180"),
                "ga4_currency": "AUD",
                "conversion_rate": Decimal("0.05"),
            },
            "previous": {"organic_sessions": Decimal("32")},
            "daily": [{"date": "2026-08-10", "organic_sessions": Decimal("40")}],
            "previous_daily": [{"date": "2026-07-13", "organic_sessions": Decimal("32")}],
            "top_pages": [],
            "breakdowns": [{"country_code": "AU", "device": "MOBILE", "sessions": 40}],
        }

    def _shopify_bundle(self, _period, _market, _device, _compare):
        return {
            "current": {
                "store_orders": 3,
                "store_revenue": Decimal("420"),
                "store_currency": "AUD",
                "store_by_currency": [{"currency": "AUD", "orders": 3, "revenue": Decimal("420")}],
            },
            "previous": {"store_orders": 2, "store_revenue": Decimal("250"), "store_currency": "AUD"},
            "daily": [{"date": "2026-08-13", "store_orders": 3, "store_revenue": Decimal("420")}],
            "previous_daily": [{"date": "2026-07-16", "store_orders": 2, "store_revenue": Decimal("250")}],
        }

    def _reconciliation_bundle(self, _period, _market, _device, _compare):
        return {
            "current": {
                "organic_orders": Decimal("1"),
                "confirmed_organic_revenue": Decimal("120"),
                "confirmed_organic_currency": "AUD",
            },
            "previous": {"organic_orders": Decimal("1"), "confirmed_organic_revenue": Decimal("100")},
        }


class LiveAnalyticsAvailabilityTests(unittest.TestCase):
    def test_gsc_only_dashboard_is_ready_without_common_date(self):
        snapshot = FakeLiveReader(source_health("gsc")).snapshot()
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["current"]["organic_clicks"], Decimal("12"))
        self.assertIsNone(snapshot["current"]["organic_sessions"])
        self.assertIsNone(snapshot["current"]["store_revenue"])
        self.assertEqual(snapshot["top_queries"][0]["query"], "sports wall art")

    def test_ga4_only_and_partial_history_remain_visible(self):
        snapshot = FakeLiveReader(source_health("ga4", ga4_status="partial_failure")).snapshot()
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["current"]["organic_sessions"], Decimal("40"))
        self.assertIsNone(snapshot["current"]["organic_clicks"])
        self.assertEqual(snapshot["health"]["ga4"]["status"], "partial_failure")

    def test_shopify_only_uses_operational_data_without_seo_identifier(self):
        health = source_health("shopify")
        health["shopify"]["identifier"] = "operational-ledger"
        snapshot = FakeLiveReader(health).snapshot()
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["current"]["store_orders"], 3)
        self.assertEqual(snapshot["current"]["store_revenue"], Decimal("420"))
        self.assertIsNone(snapshot["current"]["confirmed_organic_revenue"])

    def test_gsc_and_ga4_do_not_require_shopify(self):
        snapshot = FakeLiveReader(source_health("gsc", "ga4")).snapshot()
        self.assertEqual(snapshot["current"]["organic_clicks"], Decimal("12"))
        self.assertEqual(snapshot["current"]["organic_sessions"], Decimal("40"))
        self.assertIsNone(snapshot["current"]["store_orders"])

    def test_raw_saved_fallback_and_source_specific_dates(self):
        snapshot = FakeLiveReader(source_health("gsc", "ga4", "shopify")).snapshot()
        self.assertTrue(snapshot["fallback_mode"])
        self.assertEqual(snapshot["source_periods"]["gsc"]["end_date"], "2026-08-12")
        self.assertEqual(snapshot["source_periods"]["ga4"]["end_date"], "2026-08-10")
        self.assertEqual(snapshot["source_periods"]["shopify"]["end_date"], "2026-08-13")

    def test_failed_refresh_keeps_saved_analytics_visible(self):
        snapshot = FakeLiveReader(
            source_health("gsc", snapshot=True, refresh_status="partial")
        ).snapshot()
        self.assertTrue(snapshot["ready"])
        self.assertTrue(snapshot["stale"])
        self.assertEqual(snapshot["current"]["organic_clicks"], Decimal("12"))

    def test_device_filter_does_not_turn_store_unavailable_into_zero(self):
        snapshot = FakeLiveReader(source_health("gsc", "shopify")).snapshot(device="Mobile")
        self.assertEqual(snapshot["current"]["organic_clicks"], Decimal("12"))
        self.assertIsNone(snapshot["current"]["store_orders"])
        self.assertIsNone(snapshot["current"]["store_revenue"])


class LiveAnalyticsMathTests(unittest.TestCase):
    def test_weighted_ctr_and_impression_weighted_position(self):
        self.assertEqual(seo_live_analytics.weighted_ctr(30, 600), Decimal("0.05"))
        self.assertEqual(
            seo_live_analytics.impression_weighted_position(Decimal("5100"), 600),
            Decimal("8.5"),
        )

    def test_previous_matching_period_is_exact(self):
        period = seo_live_analytics.matching_period(
            preset="Last 28 days", through_date=date(2026, 8, 12)
        )
        self.assertEqual(period["start_date"], date(2026, 7, 16))
        self.assertEqual(period["previous_start_date"], date(2026, 6, 18))
        self.assertEqual(period["previous_end_date"], date(2026, 7, 15))

    def test_currency_safety_never_sums_unlike_currencies(self):
        result = seo_live_analytics.PostgresSEOLiveAnalyticsReader._aggregate_shopify(
            [
                {"currency": "AUD", "orders": 1, "revenue": "100"},
                {"currency": "USD", "orders": 1, "revenue": "80"},
            ]
        )
        self.assertEqual(result["store_orders"], 2)
        self.assertIsNone(result["store_revenue"])
        self.assertEqual(len(result["store_by_currency"]), 2)


class LiveAnalyticsContractTests(unittest.TestCase):
    def test_source_health_queries_bind_every_placeholder(self):
        class CapturingReader(seo_live_analytics.PostgresSEOLiveAnalyticsReader):
            def __init__(self):
                self.calls = []
                self.read_errors = {}

            def _selected_properties(self):
                return {"gsc": "https://example.test/", "ga4": "properties/1"}

            def _query_one(self, source, sql, params=()):
                self.calls.append((source, sql, tuple(params)))
                return {}

            def _latest_import_status(self, _source, _identifier):
                return {}

        reader = CapturingReader()
        reader.source_health()
        for source, sql, params in reader.calls:
            self.assertEqual(sql.count("%s"), len(params), source)

    def test_reader_is_database_only_and_uses_operational_shopify_tables(self):
        source = inspect.getsource(seo_live_analytics.PostgresSEOLiveAnalyticsReader)
        self.assertIn("FROM seo_gsc_property_totals_v2", source)
        self.assertIn("FROM seo_gsc_query_daily_v2", source)
        self.assertIn("FROM seo_gsc_page_daily_v2", source)
        self.assertIn("FROM seo_ga4_daily_landing_pages", source)
        self.assertIn("FROM shopify_orders", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("GoogleSEOReportingClient", source)
        self.assertNotIn("ShopifySEOClient", source)

    def test_navigation_is_gsc_first_and_legacy_routes_are_reversible(self):
        self.assertEqual(
            seo_navigation.SEO_ROUTES,
            (
                seo_navigation.SEO_OVERVIEW_ROUTE,
                seo_navigation.SEO_KEYWORDS_ROUTE,
                seo_navigation.SEO_OPPORTUNITIES_ROUTE,
                seo_navigation.SEO_LANDING_PAGES_ROUTE,
                seo_navigation.SEO_MAPPING_ROUTE,
                seo_navigation.SEO_BLOG_ROUTE,
                seo_navigation.SEO_HEALTH_ROUTE,
            ),
        )
        self.assertIn(seo_navigation.SEO_REPORTS_ROUTE, seo_navigation.SEO_WORKSPACE_ROUTES)
        self.assertFalse(seo_navigation.SEO_FULL_WORKSPACE_ENABLED)

    def test_overview_has_one_refresh_action_and_no_workflow_sections(self):
        overview = inspect.getsource(seo_page._render_overview)
        admin = inspect.getsource(seo_page._render_data_connections_admin)
        refresh = inspect.getsource(seo_page._render_analytics_refresh_admin)
        self.assertNotIn("_render_current_work", overview)
        self.assertNotIn("_render_phase4_foundation", admin)
        self.assertNotIn("_render_growth_pipeline_admin", admin)
        self.assertEqual(refresh.count('"Refresh analytics"'), 1)

    def test_migrations_and_existing_daily_command_activate_analytics(self):
        self.assertTrue(
            run_migrations.safe_migration_sql(
                (ROOT / "migrations" / seo_growth_intelligence.GROWTH_MIGRATION).read_text(encoding="utf-8")
            )
        )
        command_source = inspect.getsource(google_seo_import.run_complete_daily_pipeline)
        self.assertIn("run_daily_analytics_refresh", command_source)
        self.assertNotIn("run_daily_growth_pipeline", command_source)

    def test_source_specific_queue_does_not_require_other_property(self):
        class ImportStore:
            def queue_run(self, source, mode, **kwargs):
                return {"source": source, "mode": mode, **kwargs}

        class ConnectionStore:
            def get_connection_secret(self):
                return {
                    "encrypted_refresh_token": "saved",
                    "gsc_site_url": "https://example.test/",
                    "ga4_property_id": "",
                }

        run = google_seo_import.queue_daily_source(
            "GSC", import_store=ImportStore(), connection_store=ConnectionStore()
        )
        self.assertEqual(run["source"], "GSC")

    def test_analytics_refresh_runs_only_analytics_stages_under_one_lock(self):
        class Store:
            def __init__(self):
                self.started = []
                self.completed = []

            def queue_pipeline_run(self, **_kwargs):
                return {"id": "refresh-1", "status": "queued"}

            def claim_pipeline_run(self, _worker_id):
                return {"id": "refresh-1", "status": "running"}

            def renew_pipeline_lease(self, *_args, **_kwargs):
                return True

            def ensure_schema(self):
                return None

            def start_stage(self, _run_id, stage_key, _order):
                self.started.append(stage_key)

            def complete_stage(self, _run_id, stage_key, **_kwargs):
                self.completed.append(stage_key)

            def fail_stage(self, *_args, **_kwargs):
                raise AssertionError("analytics stage should not fail")

            def complete_pipeline(self, pipeline_id, **values):
                return {"id": pipeline_id, **values}

        class Phase4:
            def map_saved_urls(self):
                return {"status": "completed", "processed": 2, "written": 2}

            def reconcile_revenue(self):
                return {"status": "completed", "processed": 1, "written": 1}

            def refresh_reporting_snapshots(self):
                return {"status": "completed", "common_reporting_date": "2026-08-10"}

            def refresh_health(self):
                return {}

        class Worker:
            def __init__(self, **_kwargs):
                pass

            def run_once(self, **_kwargs):
                return {"status": "completed", "received": 1, "written": 1}

        class HealthReader:
            def __init__(self, _store):
                pass

            def source_health(self):
                return source_health("gsc", "ga4", "shopify")

        store = Store()
        with patch.object(google_seo_import, "SEOImportWorker", Worker), patch.object(
            google_seo_import, "queue_daily_source", return_value={"status": "queued"}
        ), patch.object(
            seo_growth_intelligence.seo_live_analytics,
            "PostgresSEOLiveAnalyticsReader",
            HealthReader,
        ), patch.object(
            seo_growth_intelligence.analytics_reporting,
            "refresh_saved_report_contracts",
            return_value={"status": "completed", "written": 9},
        ):
            result = seo_growth_intelligence.run_daily_analytics_refresh(
                store=store,
                import_store=object(),
                phase4_store=Phase4(),
                connection_store=Mock(),
                requested_by="test",
                worker_id="worker-1",
                fresh_gsc_refresher=lambda: {"status": "preliminary", "received": 1, "written": 1},
            )
        expected = [stage[0] for stage in seo_growth_intelligence.ANALYTICS_REFRESH_STAGES]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(store.started, expected)
        self.assertEqual(store.completed, expected)
        self.assertNotIn("opportunities", store.started)
        self.assertNotIn("measurements", store.started)


if __name__ == "__main__":
    unittest.main()
