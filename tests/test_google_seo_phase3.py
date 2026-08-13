from datetime import date
import inspect
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import google_seo
import google_seo_import as importer
import os_accounts
import run_migrations
import seo_page


ROOT = Path(__file__).resolve().parents[1]


def admin_user():
    return {
        "id": "admin-1",
        "display_name": "Nathan",
        "role": os_accounts.ROLE_ADMIN,
        "is_active": True,
    }


def worker_user():
    return {
        "id": "worker-1",
        "display_name": "Worker",
        "role": os_accounts.ROLE_WORKER,
        "is_active": True,
        "page_permissions": ["seo"],
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class ConnectionStore:
    def __init__(self):
        self.connection = {
            "encrypted_refresh_token": "encrypted-only",
            "has_refresh_token": True,
            "gsc_site_url": "https://example.test/",
            "gsc_property_name": "Example GSC",
            "ga4_property_id": "properties/123",
            "ga4_property_name": "Example GA4",
            "connection_status": "Connected",
            "reconnect_required": False,
        }

    def get_connection_secret(self):
        return dict(self.connection)

    def get_connection(self):
        return dict(self.connection)


class MemoryImportStore:
    def __init__(self, run=None):
        self.run = dict(run or {})
        self.claimed = False
        self.gsc = {}
        self.ga4 = {}
        self.latest = {"GSC": None, "GA4": None}
        self.checkpoints = []
        self.failed = None
        self.completed = None
        self.queued = []

    def queue_run(self, source, mode, **values):
        active = next((row for row in self.queued if row["source"] == source and row["status"] in {"queued", "running"}), None)
        if active:
            return dict(active)
        row = {
            "id": f"run-{source}-{len(self.queued)}",
            "source": source,
            "mode": mode,
            "status": "queued",
            **values,
        }
        self.queued.append(row)
        return dict(row)

    def claim_next_run(self, worker_id, *, source=""):
        if self.claimed or not self.run or (source and self.run.get("source") != source):
            return None
        self.claimed = True
        self.run["status"] = "running"
        return dict(self.run)

    def latest_stored_date(self, source, _property_identifier):
        return self.latest[source]

    def prepare_run_range(self, run_id, lease_owner, start_date, end_date):
        del run_id, lease_owner
        self.run["requested_start_date"] = start_date
        self.run["requested_end_date"] = end_date
        return dict(self.run)

    def renew_lease(self, *_args, **_kwargs):
        return True

    def replace_gsc_date(self, _site, slice_data):
        day = slice_data["date"]
        previous = len(self.gsc.get(day, []))
        self.gsc[day] = list(slice_data["details"])
        self.latest["GSC"] = max(day, self.latest["GSC"] or day)
        return {"inserted": len(slice_data["details"]) + 1, "replaced": previous + 1}

    def replace_ga4_date(self, _property, slice_data, **_metadata):
        day = slice_data["date"]
        previous = len(self.ga4.get(day, []))
        self.ga4[day] = list(slice_data["rows"])
        self.latest["GA4"] = max(day, self.latest["GA4"] or day)
        return {"inserted": len(slice_data["rows"]), "replaced": previous}

    def checkpoint_date(self, _run_id, _lease_owner, slice_date, **counts):
        self.run["checkpoint_date"] = slice_date
        self.checkpoints.append((slice_date, counts))

    def complete_run(self, run_id, lease_owner, source, *, status="completed"):
        del lease_owner
        self.completed = {"id": run_id, "source": source, "status": status}
        return dict(self.completed)

    def fail_run(self, run_id, lease_owner, source, **values):
        del lease_owner
        self.failed = {"id": run_id, "source": source, "status": "partial" if values.get("partial") else "failed", **values}
        return dict(self.failed)

    def recent_status(self):
        return {"GSC": {"rows_stored": 0}, "GA4": {"rows_stored": 0}}


def gsc_row(query):
    return {
        "keys": [query, "https://example.test/page", "aus", "DESKTOP"],
        "clicks": 1,
        "impressions": 10,
        "ctr": 0.1,
        "position": 2.5,
    }


class GoogleAPIContractTests(unittest.TestCase):
    def test_gsc_daily_detail_paginates_and_uses_separate_totals(self):
        calls = []

        def request_post(_url, **kwargs):
            body = kwargs["json"]
            calls.append(body)
            if "dimensions" not in body:
                return FakeResponse({"rows": [{"clicks": 8, "impressions": 80, "ctr": 0.1, "position": 4}]})
            if body["startRow"] == 0:
                return FakeResponse({"rows": [gsc_row("one"), gsc_row("two")]})
            if body["startRow"] == 2:
                return FakeResponse({"rows": [gsc_row("three")]})
            return FakeResponse({"rows": []})

        client = importer.GoogleSEOReportingClient("temporary", request_post=request_post)
        with patch.object(importer, "GSC_PAGE_SIZE", 2), patch.object(importer, "GSC_DAILY_ROW_LIMIT", 10):
            result = client.fetch_gsc_date("https://example.test/", date(2026, 8, 10))
        self.assertEqual([row["query"] for row in result["details"]], ["one", "two", "three"])
        self.assertEqual(result["total"]["clicks"], 8)
        self.assertEqual([body["startRow"] for body in calls if "dimensions" in body], [0, 2])
        self.assertTrue(all(body.get("dataState") == "final" for body in calls))
        self.assertTrue(all(body.get("type") == "web" for body in calls))

    def test_ga4_paginates_to_row_count_and_keeps_organic_filter(self):
        offsets = []

        def request_post(_url, **kwargs):
            body = kwargs["json"]
            offsets.append(body["offset"])
            start = int(body["offset"])
            names = [row["name"] for row in body["dimensions"]]
            metric_names = [row["name"] for row in body["metrics"]]

            def row(path):
                dims = {
                    "date": "20260810",
                    "landingPagePlusQueryString": path,
                    "countryId": "AU",
                    "deviceCategory": "desktop",
                    "sessionDefaultChannelGroup": "Organic Search",
                    "hostname": "example.test",
                }
                metrics = {name: "1" for name in metric_names}
                return {
                    "dimensionValues": [{"value": dims[name]} for name in names],
                    "metricValues": [{"value": metrics[name]} for name in metric_names],
                }

            rows = [row("/a"), row("/b")] if start == 0 else [row("/c")]
            return FakeResponse(
                {
                    "dimensionHeaders": [{"name": name} for name in names],
                    "metricHeaders": [{"name": name} for name in metric_names],
                    "rows": rows,
                    "rowCount": 3,
                    "metadata": {"currencyCode": "AUD", "timeZone": "Australia/Sydney"},
                }
            )

        client = importer.GoogleSEOReportingClient("temporary", request_post=request_post)
        with patch.object(importer, "GA4_PAGE_SIZE", 2):
            result = client.fetch_ga4_date(
                "properties/123",
                date(2026, 8, 10),
                dimensions=(*importer.GA4_REQUIRED_DIMENSIONS, "hostname"),
            )
        self.assertEqual(offsets, ["0", "2"])
        self.assertEqual([row["landing_page_path_query"] for row in result["rows"]], ["/a", "/b", "/c"])
        self.assertEqual(result["currency"], "AUD")
        self.assertTrue(all(row["session_channel_group"] == "Organic Search" for row in result["rows"]))

    def test_compatibility_allows_hostname_fallback_but_requires_core_fields(self):
        def request_post(_url, **_kwargs):
            dimensions = [
                {"dimensionMetadata": {"apiName": name}, "compatibility": "COMPATIBLE"}
                for name in importer.GA4_REQUIRED_DIMENSIONS
            ]
            metrics = [
                {"metricMetadata": {"apiName": name}, "compatibility": "COMPATIBLE"}
                for name in importer.GA4_METRICS
            ]
            return FakeResponse({"dimensionCompatibilities": dimensions, "metricCompatibilities": metrics})

        dimensions = importer.GoogleSEOReportingClient(
            "temporary", request_post=request_post
        ).compatible_ga4_dimensions("properties/123")
        self.assertEqual(dimensions, importer.GA4_REQUIRED_DIMENSIONS)


class DurableImportTests(unittest.TestCase):
    def _worker(self, store, client):
        return importer.SEOImportWorker(
            import_store=store,
            connection_store=ConnectionStore(),
            config_loader=lambda: {},
            access_token_loader=lambda _store, _config: ("temporary", ConnectionStore().connection),
            client_factory=lambda _token: client,
            worker_id="worker-test",
            sleep=lambda _seconds: None,
        )

    def test_historical_import_resumes_after_interruption(self):
        class Client:
            def __init__(self, fail_day=None):
                self.fail_day = fail_day

            def discover_gsc_range(self, _site):
                return date(2026, 8, 1), date(2026, 8, 3)

            def fetch_gsc_date(self, _site, day):
                if day == self.fail_day:
                    raise importer.SEOImportError("Temporary import failure.", code="temporary")
                return {"date": day, "details": [{"query": day.isoformat()}], "total": {}, "rows_received": 2}

        first_run = {
            "id": "run-1", "source": "GSC", "mode": "historical", "status": "running",
            "property_identifier": "https://example.test/",
        }
        store = MemoryImportStore(first_run)
        result = self._worker(store, Client(date(2026, 8, 2)))._process(first_run)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(store.run["checkpoint_date"], date(2026, 8, 1))
        self.assertIn(date(2026, 8, 1), store.gsc)

        resume_run = {
            **first_run,
            "id": "run-2",
            "requested_start_date": date(2026, 8, 2),
            "requested_end_date": date(2026, 8, 3),
            "checkpoint_date": None,
        }
        store.run = resume_run
        result = self._worker(store, Client())._process(resume_run)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(set(store.gsc), {date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)})

    def test_reimport_replaces_slice_and_removes_stale_rows_without_duplicates(self):
        store = MemoryImportStore()
        day = date(2026, 8, 10)
        base = {"date": day, "total": {}}
        store.replace_gsc_date("site", {**base, "details": [{"query": "kept"}, {"query": "stale"}]})
        store.replace_gsc_date("site", {**base, "details": [{"query": "kept"}]})
        self.assertEqual(store.gsc[day], [{"query": "kept"}])

    def test_failed_fetch_never_replaces_previous_valid_slice(self):
        day = date(2026, 8, 10)
        run = {
            "id": "run-1", "source": "GSC", "mode": "manual", "status": "running",
            "property_identifier": "https://example.test/",
            "requested_start_date": day, "requested_end_date": day,
        }
        store = MemoryImportStore(run)
        store.gsc[day] = [{"query": "previous-valid"}]
        store.latest["GSC"] = day

        class Client:
            def discover_gsc_range(self, _site):
                return day, day

            def fetch_gsc_date(self, _site, _day):
                raise importer.SEOImportError("Fetch failed.", code="fetch_failed")

        self._worker(store, Client())._process(run)
        self.assertEqual(store.gsc[day], [{"query": "previous-valid"}])
        self.assertEqual(store.failed["error_code"], "fetch_failed")

    def test_failed_atomic_replacement_retains_previous_valid_slice(self):
        day = date(2026, 8, 10)
        run = {
            "id": "run-1", "source": "GSC", "mode": "manual", "status": "running",
            "property_identifier": "https://example.test/",
            "requested_start_date": day, "requested_end_date": day,
        }

        class Store(MemoryImportStore):
            def replace_gsc_date(self, _site, _slice_data):
                raise importer.SEOImportError("Database write failed.", code="date_replace_failed")

        store = Store(run)
        store.gsc[day] = [{"query": "previous-valid"}]
        store.latest["GSC"] = day

        class Client:
            def discover_gsc_range(self, _site):
                return day, day

            def fetch_gsc_date(self, _site, _day):
                return {"date": day, "details": [{"query": "new"}], "total": {}, "rows_received": 2}

        self._worker(store, Client())._process(run)
        self.assertEqual(store.gsc[day], [{"query": "previous-valid"}])
        self.assertEqual(store.failed["error_code"], "date_replace_failed")

    def test_daily_range_rechecks_seven_completed_days_and_catches_new_dates(self):
        start, end = importer.daily_refresh_range(
            date(2026, 1, 1),
            date(2026, 8, 12),
            date(2026, 8, 10),
        )
        self.assertEqual(start, date(2026, 8, 6))
        self.assertEqual(end, date(2026, 8, 12))
        missed_start, _ = importer.daily_refresh_range(
            date(2026, 1, 1), date(2026, 8, 12), date(2026, 7, 31)
        )
        self.assertEqual(missed_start, date(2026, 8, 1))

    def test_queue_is_idempotent_per_source_and_non_admin_is_rejected(self):
        store = MemoryImportStore()
        connection = ConnectionStore()
        with patch.object(importer, "record_activity_log"):
            first = importer.queue_imports(
                admin_user(), "historical", import_store=store, connection_store=connection
            )
            second = importer.queue_imports(
                admin_user(), "historical", import_store=store, connection_store=connection
            )
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(len(store.queued), 2)
        with self.assertRaises(PermissionError):
            importer.queue_imports(
                worker_user(), "historical", import_store=store, connection_store=connection
            )

    def test_unexpected_errors_are_sanitized_and_never_store_secret_text(self):
        secret = "refresh-token-private-value"
        code, message = importer.sanitize_import_error(RuntimeError(secret))
        self.assertEqual(code, "seo_import_failed")
        self.assertNotIn(secret, message)


class StorageAndOverviewTests(unittest.TestCase):
    def test_atomic_replace_sql_parameter_contracts_are_consistent(self):
        class Cursor:
            def __init__(self):
                self.row = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                params = tuple(params or ())
                self.assert_placeholders(sql, params)
                if "AS detail_count" in sql:
                    self.row = {"detail_count": 0, "has_total": False}
                elif "FROM seo_ga4_daily_landing_pages" in sql and "AS count" in sql:
                    self.row = {"count": 0}
                else:
                    self.row = {}

            def executemany(self, sql, rows):
                for row in rows:
                    self.assert_placeholders(sql, tuple(row))

            @staticmethod
            def assert_placeholders(sql, params):
                if sql.count("%s") != len(params):
                    raise AssertionError(f"Placeholder mismatch: {sql.count('%s')} != {len(params)}")

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.cursor_value = Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return self.cursor_value

            def commit(self):
                return None

        class Backend:
            def connect(self):
                return Connection()

        store = importer.PostgresSEOImportStore(Backend())
        store._schema_ready = True
        day = date(2026, 8, 10)
        store.replace_gsc_date(
            "https://example.test/",
            {
                "date": day,
                "total": {},
                "details": [
                    {
                        "query": "query", "page_url": "https://example.test/page",
                        "country_code": "aus", "device": "DESKTOP",
                    }
                ],
            },
        )
        store.replace_ga4_date(
            "properties/123",
            {
                "date": day,
                "rows": [{"landing_page_path_query": "/page"}],
            },
            property_timezone="Australia/Sydney",
            property_currency="AUD",
        )

    def test_phase3_migration_is_safe_and_preserves_phase1_encrypted_connection(self):
        sql = (ROOT / "migrations" / importer.SEO_IMPORT_MIGRATION).read_text(encoding="utf-8")
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertNotIn("encrypted_refresh_token", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_sync_runs_one_active_source", sql)
        for table in (
            "seo_sync_runs", "seo_sync_errors", "seo_data_inventories", "seo_gsc_daily_totals",
            "seo_gsc_daily_details", "seo_ga4_daily_landing_pages",
            "seo_shopify_url_mappings", "seo_opportunities", "seo_ai_plans",
            "seo_va_tasks", "seo_measurement_snapshots",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        self.assertIn("PRIMARY KEY (workspace_key, gsc_site_url, date, search_type)", sql)
        self.assertIn("PRIMARY KEY (workspace_key, gsc_site_url, date, dimension_key_hash)", sql)
        self.assertEqual(
            importer.dimension_key_hash("query", "page", "AU", "DESKTOP", "web"),
            importer.dimension_key_hash("query", "page", "AU", "DESKTOP", "web"),
        )
        self.assertIn("GA4 attributed/unconfirmed", sql)
        self.assertIn("WHERE status IN ('queued', 'running')", sql)

    def test_worker_uses_database_checkpoint_and_expiring_skip_locked_lease(self):
        source = inspect.getsource(importer.PostgresSEOImportStore.claim_next_run)
        migration = (ROOT / "migrations" / importer.SEO_IMPORT_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("lease_expires_at", source)
        self.assertIn("WHERE status IN ('queued', 'running')", migration)

    def test_overview_render_is_database_only_even_when_google_clients_raise(self):
        class UI:
            class Node:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def markdown(self, *_args, **_kwargs):
                    return None

                def metric(self, *_args, **_kwargs):
                    return None

                def button(self, *_args, **_kwargs):
                    return False

            def __init__(self):
                self.query_params = {}
                self.session_state = {}

            def columns(self, spec):
                return [self.Node() for _ in range(spec if isinstance(spec, int) else len(spec))]

            def expander(self, *_args, **_kwargs):
                return self.Node()

            def markdown(self, *_args, **_kwargs):
                return None

            def subheader(self, *_args, **_kwargs):
                return None

            def caption(self, *_args, **_kwargs):
                return None

            def info(self, *_args, **_kwargs):
                return None

            def warning(self, *_args, **_kwargs):
                return None

            def divider(self):
                return None

            def checkbox(self, *_args, **_kwargs):
                return False

            def button(self, *_args, **_kwargs):
                return False

            def multiselect(self, *_args, **_kwargs):
                return []

            def progress(self, *_args, **_kwargs):
                return None

        forbidden = Mock(side_effect=AssertionError("Google client called during render"))
        with patch.object(seo_page, "st", UI()), patch.object(
            seo_page, "_shopify_health", return_value={"status": "Connected", "last_sync": "Saved"}
        ), patch.multiple(
            google_seo,
            list_gsc_properties=forbidden,
            list_ga4_properties=forbidden,
            latest_gsc_data_date=forbidden,
            latest_ga4_data_date=forbidden,
            refresh_access_token=forbidden,
        ):
            seo_page._render_overview({}, admin_user(), None, ConnectionStore(), MemoryImportStore())
        forbidden.assert_not_called()

    def test_phase1_connection_and_sync_functions_remain_present(self):
        self.assertTrue(callable(google_seo.complete_authorization))
        self.assertTrue(callable(google_seo.refresh_properties))
        self.assertTrue(callable(google_seo.save_property_selection))
        self.assertTrue(callable(google_seo.sync_now))
        self.assertTrue(callable(google_seo.disconnect_google))
        self.assertEqual(importer.GA4_REVENUE_BASIS, "GA4 attributed/unconfirmed")


if __name__ == "__main__":
    unittest.main()
