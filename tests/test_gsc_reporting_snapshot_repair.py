from pathlib import Path
import inspect
import unittest
from unittest.mock import patch

import google_seo
import google_seo_import
import google_seo_phase4
import run_migrations
import seo_page
import seo_reporting_runtime


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self):
        self.statements = []
        self._row = {}

    def execute(self, sql, params=()):
        clean = " ".join(str(sql).split())
        self.statements.append((clean, params))
        if "pg_try_advisory_xact_lock" in clean:
            self._row = {"acquired": True}
        elif "AS daily_metric_rows" in clean:
            self._row = {
                "gsc_rows": 4700,
                "ga4_rows": 0,
                "ga4_transaction_rows": 0,
                "shopify_order_rows": 0,
                "mapped_url_rows": 0,
                "reconciled_transaction_rows": 0,
                "daily_metric_rows": 45,
                "query_metric_rows": 2674,
                "page_metric_rows": 2014,
                "opportunity_rows": 12,
            }
        else:
            self._row = {}
        return self

    def fetchone(self):
        return dict(self._row)

    def fetchall(self):
        return []

    def executemany(self, _sql, _rows):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Backend:
    def __init__(self, cursor=None):
        self.cursor = cursor or _Cursor()
        self.connection = _Connection(self.cursor)

    def connect(self):
        return self.connection


class GSCOnlySnapshotBuilderTests(unittest.TestCase):
    def test_saved_gsc_rows_build_without_ga4_shopify_or_common_date(self):
        backend = _Backend()
        store = google_seo_phase4.PostgresSEOPhase4Store(backend)
        store._schema_ready = True
        with patch.object(store, "get_settings", return_value={"brand_terms": ["sports cave"]}), patch.object(
            store,
            "refresh_health",
            return_value={"common_reporting_date": None, "latest_gsc_date": "2026-08-16"},
        ), patch.object(
            store,
            "connection_record",
            return_value={
                "gsc_site_url": "https://www.sportscaveshop.com/",
                "gsc_final_reporting_through_date": "2026-08-16",
                "gsc_canonical_data_through_date": "2026-08-16",
                "gsc_canonical_revision": 44,
                "ga4_property_id": "",
            },
        ):
            result = store.refresh_reporting_snapshots(trigger_source="test")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["gsc_reporting_through_date"], "2026-08-16")
        self.assertEqual(result["query_metric_rows"], 2674)
        sql = "\n".join(statement for statement, _params in backend.cursor.statements)
        self.assertIn("FROM seo_gsc_property_totals_v2", sql)
        self.assertIn("FROM seo_gsc_query_daily_v2", sql)
        self.assertIn("FROM seo_gsc_page_daily_v2", sql)
        self.assertIn("INSERT INTO seo_reporting_snapshot_runs", sql)
        self.assertIn("gsc_reporting_through_date", sql)

    def test_builder_scopes_to_exact_saved_property_and_final_web_rows(self):
        builder_source = inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store.refresh_reporting_snapshots
        )
        source = builder_source + inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store._refresh_query_snapshots
        ) + inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store._refresh_landing_page_snapshots
        )
        self.assertIn("property_id=%s", source)
        self.assertIn("search_type='web'", source)
        self.assertIn("data_state='final'", source)
        self.assertNotIn("property_id=%s OR property_key=%s", source)
        self.assertNotIn("if not common:", builder_source)

    def test_ctr_and_position_remain_weighted(self):
        source = inspect.getsource(
            seo_reporting_runtime.PostgresSEOInteractiveReader.overview_base
        )
        metrics = inspect.getsource(
            seo_reporting_runtime.PostgresSEOInteractiveReader._metrics
        )
        self.assertIn("SUM(position_weight)", source)
        self.assertIn("clicks / impressions", metrics)
        self.assertIn("weight\")) / impressions", metrics)


class LastGoodReaderTests(unittest.TestCase):
    def test_failed_newest_uses_older_gsc_snapshot_and_marks_stale(self):
        class Cursor:
            def execute(self, _sql, _params=()):
                return None

            def fetchone(self):
                return {
                    "latest_status": "failed",
                    "latest_error_code": "reporting_snapshot_failed",
                    "latest_error_summary": "safe failure",
                    "snapshot_id": "last-good",
                    "gsc_reporting_through_date": "2026-08-16",
                    "common_reporting_date": None,
                    "snapshot_revision": 40,
                    "source_revision": 41,
                    "refreshed_at": "2026-08-18T18:47:00Z",
                    "gsc_site_url": "https://www.sportscaveshop.com/",
                }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Connection:
            def cursor(self):
                return Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Backend:
            def connect(self):
                return Connection()

        context = seo_reporting_runtime.PostgresSEOInteractiveReader(Backend()).reporting_context()
        self.assertTrue(context["available"])
        self.assertEqual(context["status"], "stale_last_good")
        self.assertEqual(context["through_date"], "2026-08-16")
        self.assertEqual(context["error_code"], "reporting_snapshot_failed")


class ReportingRepairQueueTests(unittest.TestCase):
    def test_gsc_completion_queues_revision_rebuild(self):
        source = inspect.getsource(google_seo_import.PostgresSEOImportStore.complete_run)
        self.assertIn("queue_reporting_repair", source)
        self.assertIn('trigger_source="gsc_revision"', source)

    def test_worker_processes_import_then_reporting_queue(self):
        source = inspect.getsource(google_seo_import._run_worker_loop) + inspect.getsource(
            google_seo_import._run_worker_cycle
        )
        self.assertIn("process_queued_reporting_repair", source)
        claim = inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store.claim_reporting_repair
        )
        self.assertIn("SKIP LOCKED", claim)
        self.assertIn("expired reporting repair lease", claim)

    def test_manual_repair_is_background_queued(self):
        source = inspect.getsource(google_seo_import.queue_gsc_reporting_repair)
        ui_source = inspect.getsource(seo_page._render_analytics_refresh_admin)
        self.assertIn('"GSC"', source)
        self.assertIn('"manual"', source)
        self.assertIn("gsc_sync_run_id", source)
        self.assertIn("queue_gsc_reporting_repair", ui_source)
        self.assertNotIn("probe_gsc_connection", ui_source)
        self.assertNotIn("refresh_reporting_snapshots", ui_source)

    def test_snapshot_rebuild_has_no_storefront_or_google_requests(self):
        source = inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store.refresh_reporting_snapshots
        )
        for forbidden in (
            "requests.get", "requests.post", "sportscave.com.au/products",
            "sportscaveshop.com/products", "GoogleSEOReportingClient",
        ):
            self.assertNotIn(forbidden, source)


class _InitialRepairCursor:
    def __init__(
        self,
        *,
        canonical_ready=True,
        current_snapshot_ready=False,
        source_revision=44,
        active_job=None,
    ):
        self.canonical_ready = canonical_ready
        self.current_snapshot_ready = current_snapshot_ready
        self.source_revision = source_revision
        self.active_job = dict(active_job or {})
        self.jobs = [self.active_job] if self.active_job else []
        self.statements = []
        self._row = None

    def execute(self, sql, params=()):
        clean = " ".join(str(sql).split())
        self.statements.append((clean, params))
        if "AS canonical_ready" in clean:
            self._row = {
                "gsc_site_url": "https://www.sportscaveshop.com/",
                "source_revision": self.source_revision,
                "canonical_ready": self.canonical_ready,
                "current_snapshot_ready": self.current_snapshot_ready,
            }
        elif clean.startswith("SELECT * FROM seo_reporting_repair_jobs"):
            self._row = dict(self.jobs[0]) if self.jobs else None
        elif clean.startswith("INSERT INTO seo_reporting_repair_jobs"):
            if self.jobs:
                self._row = None
            else:
                self._row = {
                    "id": params[0],
                    "workspace_key": params[1],
                    "status": "queued",
                    "trigger_source": "initial_gsc_reporting_backfill",
                    "requested_by": "startup",
                    "attempt_count": 0,
                }
                self.jobs.append(dict(self._row))
        else:
            self._row = None

    def fetchone(self):
        return dict(self._row) if self._row else None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class InitialReportingRepairTests(unittest.TestCase):
    @staticmethod
    def store_for(cursor):
        store = google_seo_phase4.PostgresSEOPhase4Store(_Backend(cursor))
        store._schema_ready = True
        return store

    def test_existing_canonical_data_queues_exactly_one_initial_repair(self):
        cursor = _InitialRepairCursor()
        store = self.store_for(cursor)

        first = store.ensure_initial_gsc_reporting_repair()
        second = store.ensure_initial_gsc_reporting_repair()

        self.assertEqual(first["status"], "queued")
        self.assertEqual(second["status"], "already_active")
        self.assertEqual(len(cursor.jobs), 1)
        sql = "\n".join(statement for statement, _params in cursor.statements)
        self.assertIn("total.property_id=connection.gsc_site_url", sql)
        self.assertIn("total.search_type='web'", sql)
        self.assertIn("total.data_state='final'", sql)
        self.assertIn("total.is_complete=TRUE", sql)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("ON CONFLICT DO NOTHING", sql)

        migration = (
            ROOT / "migrations" / "20260819_gsc_reporting_snapshot_repair.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("idx_seo_reporting_repair_one_active", migration)
        self.assertIn("WHERE status IN ('queued', 'running')", migration)

    def test_current_revision_snapshot_does_not_queue(self):
        cursor = _InitialRepairCursor(current_snapshot_ready=True)
        result = self.store_for(cursor).ensure_initial_gsc_reporting_repair()

        self.assertEqual(result["status"], "not_required")
        self.assertEqual(result["reason"], "current_snapshot_available")
        self.assertEqual(cursor.jobs, [])

    def test_existing_active_repair_is_reused(self):
        active = {
            "id": "existing",
            "workspace_key": google_seo.GOOGLE_SEO_WORKSPACE_KEY,
            "status": "running",
            "attempt_count": 1,
        }
        cursor = _InitialRepairCursor(active_job=active)
        result = self.store_for(cursor).ensure_initial_gsc_reporting_repair()

        self.assertEqual(result["status"], "already_active")
        self.assertEqual(result["job"]["id"], "existing")
        self.assertEqual(len(cursor.jobs), 1)

    def test_missing_complete_canonical_data_does_not_queue(self):
        cursor = _InitialRepairCursor(canonical_ready=False)
        result = self.store_for(cursor).ensure_initial_gsc_reporting_repair()

        self.assertEqual(result["status"], "not_required")
        self.assertEqual(result["reason"], "canonical_gsc_data_unavailable")
        self.assertEqual(cursor.jobs, [])

    def test_startup_enqueue_only_inspects_database_and_queue(self):
        source = inspect.getsource(
            google_seo_phase4.PostgresSEOPhase4Store.ensure_initial_gsc_reporting_repair
        )
        for forbidden in (
            "requests.", "googleapis.com", "refresh_reporting_snapshots",
            "sportscaveshop.com/products", "seo_technical_audit",
        ):
            self.assertNotIn(forbidden, source)


class MigrationTests(unittest.TestCase):
    def test_reporting_repair_migration_is_additive_and_registered(self):
        name = "20260819_gsc_reporting_snapshot_repair.sql"
        sql = (ROOT / "migrations" / name).read_text(encoding="utf-8")
        self.assertIn("gsc_reporting_through_date", sql)
        self.assertIn("seo_reporting_page_daily", sql)
        self.assertIn("seo_reporting_repair_jobs", sql)
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())
        self.assertNotIn("INSERT ", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn(name, google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS)
        self.assertIn(name, google_seo_phase4.PHASE4_MIGRATIONS)


if __name__ == "__main__":
    unittest.main()
