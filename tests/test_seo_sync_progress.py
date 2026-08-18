from datetime import date, datetime, timedelta, timezone
import inspect
import unittest
from unittest.mock import Mock, patch

import google_seo_import
import google_seo_phase4
import seo_page
import seo_sync_progress


NOW = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)


def run_record(**overrides):
    record = {
        "status": "running",
        "requested_start_date": "2026-01-01",
        "requested_end_date": "2026-01-10",
        "completed_start_date": "2026-01-01",
        "completed_end_date": "2026-01-04",
        "checkpoint_date": "2026-01-04",
        "active_slice_date": "2026-01-05",
        "rows_received": 120,
        "rows_stored": 100,
        "started_at": (NOW - timedelta(minutes=2)).isoformat(),
        "updated_at": (NOW - timedelta(seconds=5)).isoformat(),
    }
    record.update(overrides)
    return record


class SyncProgressCalculationTests(unittest.TestCase):
    def test_queued_job_starts_at_zero(self):
        result = seo_sync_progress.calculate_sync_progress(
            run_record(status="queued", completed_start_date=None, completed_end_date=None),
            now=NOW,
        )
        self.assertEqual(result["percentage"], 0)
        self.assertEqual(result["completed_dates"], 0)

    def test_running_job_uses_inclusive_requested_range(self):
        result = seo_sync_progress.calculate_sync_progress(run_record(), now=NOW)
        self.assertEqual(result["total_dates"], 10)
        self.assertEqual(result["completed_dates"], 4)
        self.assertEqual(result["percentage"], 40)
        self.assertEqual(result["current_checkpoint_date"], date(2026, 1, 5))

    def test_partial_and_failed_jobs_retain_last_valid_progress(self):
        for status in ("partial", "failed"):
            with self.subTest(status=status):
                result = seo_sync_progress.calculate_sync_progress(
                    run_record(status=status, completed_at=NOW.isoformat()),
                    now=NOW,
                )
                self.assertEqual(result["completed_dates"], 4)
                self.assertEqual(result["percentage"], 40)

    def test_resumed_job_uses_durable_checkpoint(self):
        result = seo_sync_progress.calculate_sync_progress(
            run_record(completed_end_date=None, checkpoint_date="2026-01-06"),
            now=NOW,
        )
        self.assertEqual(result["completed_dates"], 6)
        self.assertEqual(result["percentage"], 60)

    def test_completed_job_is_one_hundred_percent(self):
        result = seo_sync_progress.calculate_sync_progress(
            run_record(status="completed", completed_end_date="2026-01-10", completed_at=NOW.isoformat()),
            now=NOW,
        )
        self.assertEqual(result["percentage"], 100)
        self.assertEqual(result["completed_dates"], 10)

    def test_single_date_range_is_safe(self):
        result = seo_sync_progress.calculate_sync_progress(
            run_record(
                requested_start_date="2026-01-01",
                requested_end_date="2026-01-01",
                completed_end_date="2026-01-01",
                checkpoint_date="2026-01-01",
            ),
            now=NOW,
        )
        self.assertEqual(result["total_dates"], 1)
        self.assertEqual(result["percentage"], 100)

    def test_invalid_and_missing_ranges_remain_unknown(self):
        for start, end in ((None, None), ("2026-02-01", "2026-01-01"), ("bad", "date")):
            with self.subTest(start=start, end=end):
                result = seo_sync_progress.calculate_sync_progress(
                    run_record(requested_start_date=start, requested_end_date=end),
                    now=NOW,
                )
                self.assertFalse(result["range_valid"])
                self.assertEqual(result["percentage"], 0)
                self.assertIsNone(result["eta_seconds"])

    def test_eta_waits_for_a_reasonable_sample(self):
        too_early = seo_sync_progress.calculate_sync_progress(
            run_record(
                completed_end_date="2026-01-01",
                checkpoint_date="2026-01-01",
                started_at=(NOW - timedelta(minutes=2)).isoformat(),
            ),
            now=NOW,
        )
        ready = seo_sync_progress.calculate_sync_progress(run_record(), now=NOW)
        self.assertIsNone(too_early["rate_per_minute"])
        self.assertIsNone(too_early["eta_seconds"])
        self.assertGreater(ready["rate_per_minute"], 0)
        self.assertGreater(ready["eta_seconds"], 0)

    def test_persisted_record_recreates_same_progress_after_restart(self):
        persisted = run_record()
        first = seo_sync_progress.calculate_sync_progress(persisted, now=NOW)
        after_restart = seo_sync_progress.calculate_sync_progress(dict(persisted), now=NOW)
        self.assertEqual(first, after_restart)

    def test_progress_never_moves_backwards_across_later_checkpoints(self):
        earlier = seo_sync_progress.calculate_sync_progress(
            run_record(completed_end_date="2026-01-04", checkpoint_date="2026-01-04"),
            now=NOW,
        )
        later = seo_sync_progress.calculate_sync_progress(
            run_record(completed_end_date="2026-01-06", checkpoint_date="2026-01-06"),
            now=NOW,
        )
        self.assertGreaterEqual(later["completed_dates"], earlier["completed_dates"])
        self.assertGreaterEqual(later["percentage"], earlier["percentage"])

    def test_card_labels_approximate_eta_and_calculating_state_honestly(self):
        card_now = datetime.now(timezone.utc)
        calculating = seo_page._import_status_card(
            "GA4",
            run_record(
                completed_end_date="2026-01-01",
                checkpoint_date="2026-01-01",
                started_at=(card_now - timedelta(minutes=2)).isoformat(),
            ),
        )
        ready = seo_page._import_status_card(
            "GA4",
            run_record(started_at=(card_now - timedelta(minutes=2)).isoformat()),
        )
        self.assertIn("Calculating…", calculating)
        self.assertIn("Approximately", ready)
        self.assertIn("aria-valuenow", ready)


class SyncProgressArchitectureTests(unittest.TestCase):
    def test_checkpoint_writes_never_move_backwards(self):
        phase3 = inspect.getsource(google_seo_import.PostgresSEOImportStore.checkpoint_date)
        phase4 = inspect.getsource(google_seo_phase4.PostgresSEOPhase4Store.checkpoint_run)
        self.assertIn("GREATEST(COALESCE(checkpoint_date", phase3)
        self.assertIn("GREATEST(", phase4)
        self.assertIn("COALESCE(checkpoint_date", phase4)

    def test_progress_component_is_isolated_and_restrained(self):
        source = inspect.getsource(seo_page._render_historical_import_controls)
        self.assertIn("st.rerun(scope=\"fragment\")", source)
        self.assertEqual(seo_page.SEO_PROGRESS_POLL_SECONDS, 15)
        self.assertIsNotNone(
            getattr(seo_page._render_historical_import_controls, "_fragment", True)
        )

    def test_combined_status_read_uses_one_database_query(self):
        class Cursor:
            def __init__(self):
                self.execute_count = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _sql, _params=None):
                self.execute_count += 1

            def fetchall(self):
                return []

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        class Backend:
            def connect(self):
                return Connection()

        store = google_seo_phase4.PostgresSEOPhase4Store(Backend())
        store._schema_ready = True
        self.assertEqual(store.progress_status(), {"phase3": {}, "phase4": {}})
        self.assertEqual(cursor.execute_count, 1)

    def test_reporting_and_administration_are_lazy(self):
        source = inspect.getsource(seo_page._render_data_connections_admin)
        guard = source.index("if not is_open:")
        self.assertLess(guard, source.index("google_seo.configuration_status()"))
        self.assertLess(guard, source.index("_cached_default_google_connection()"))
        self.assertLess(guard, source.index("_render_historical_import_controls("))
        self.assertLess(guard, source.index("_render_analytics_refresh_admin("))

    def test_overview_route_skips_full_legacy_workspace_read(self):
        source = inspect.getsource(seo_page._render_active_route)
        self.assertIn("if route in state_routes:", source)
        state_routes = source[
            source.index("state_routes = {") : source.index("if route in state_routes:")
        ]
        self.assertNotIn("SEO_OVERVIEW_ROUTE", state_routes)
        self.assertNotIn("SEO_LANDING_PAGES_ROUTE", state_routes)
        self.assertNotIn("SEO_HEALTH_ROUTE", state_routes)
        self.assertLess(
            source.index("if route in state_routes:"),
            source.index("state = store.load()"),
        )

    def test_summary_cache_has_short_ttl_and_explicit_invalidation(self):
        self.assertEqual(seo_page.SEO_OVERVIEW_CACHE_TTL_SECONDS, 15)
        with patch.object(seo_page._cached_default_shopify_health, "clear") as shopify_clear, patch.object(
            seo_page._cached_default_google_connection, "clear"
        ) as google_clear, patch.object(
            seo_page._cached_default_phase4_health, "clear"
        ) as phase4_clear, patch.object(
            seo_page._cached_default_live_source_health, "clear"
        ) as live_health_clear, patch.object(
            seo_page._cached_default_reporting_snapshot, "clear"
        ) as reporting_clear:
            seo_page.invalidate_seo_overview_summary_cache()
        shopify_clear.assert_called_once_with()
        google_clear.assert_called_once_with()
        phase4_clear.assert_called_once_with()
        live_health_clear.assert_called_once_with()
        reporting_clear.assert_called_once_with()

    def test_import_actions_explicitly_invalidate_summary_cache(self):
        progress_source = inspect.getsource(seo_page._render_historical_import_controls)
        phase4_source = inspect.getsource(seo_page._render_phase4_foundation)
        self.assertGreaterEqual(
            progress_source.count("invalidate_seo_overview_summary_cache()"),
            3,
        )
        self.assertGreaterEqual(
            phase4_source.count("invalidate_seo_overview_summary_cache()"),
            3,
        )

    def test_phase4_ga4_worker_persists_discovered_date_range(self):
        source = inspect.getsource(google_seo_phase4.SEOPhase4Worker._process_ga4_transactions)
        self.assertIn("prepare_run_range", source)
        self.assertIn("run[\"requested_start_date\"]", source)
        self.assertIn("run[\"requested_end_date\"]", source)

    def test_overview_source_contains_no_external_client_calls(self):
        source = inspect.getsource(seo_page._render_overview)
        for forbidden in (
            "GoogleSEOReportingClient",
            "ShopifySEOClient",
            "requests.get",
            "requests.post",
            "list_gsc_properties",
            "list_ga4_properties",
        ):
            self.assertNotIn(forbidden, source)

    def test_existing_queue_guards_remain_in_place(self):
        phase3 = inspect.getsource(google_seo_import.PostgresSEOImportStore.queue_run)
        phase4 = inspect.getsource(google_seo_phase4.PostgresSEOPhase4Store.queue_run)
        self.assertIn("status IN ('queued', 'running')", phase3)
        self.assertIn("status IN ('queued', 'running')", phase4)


if __name__ == "__main__":
    unittest.main()
