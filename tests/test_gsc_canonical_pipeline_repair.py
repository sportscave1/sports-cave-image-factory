from datetime import date
from decimal import Decimal
import inspect
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import google_seo
import google_seo_import
import seo_growth_intelligence
import seo_live_analytics
import seo_page
import sports_cave_server
from scripts import audit_gsc_connection_and_data


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self.payload


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self.many_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(str(sql).split()), tuple(params or ())))

    def executemany(self, sql, rows):
        self.many_calls.append((" ".join(str(sql).split()), list(rows)))

    def fetchone(self):
        return {}

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class RecordingBackend:
    def __init__(self):
        self.cursor = RecordingCursor()
        self.connection = RecordingConnection(self.cursor)

    def connect(self):
        return self.connection


def canonical_slice():
    return {
        "date": date(2026, 8, 14),
        "data_state": "final",
        "search_type": "web",
        "total": {
            "clicks": Decimal("12"),
            "impressions": Decimal("300"),
            "ctr": Decimal("0.04"),
            "average_position": Decimal("8.5"),
            "aggregation_type": "byProperty",
            "is_complete": True,
            "is_truncated": False,
        },
        "details": [],
        "query_rows": [{
            "raw_query": "sports cave",
            "normalized_query": "sports cave",
            "country_code": "aus",
            "device": "MOBILE",
            "clicks": Decimal("12"),
            "impressions": Decimal("300"),
            "position_weight": Decimal("2550"),
        }],
        "page_rows": [{
            "page_url": "https://www.sportscaveshop.com/",
            "country_code": "aus",
            "device": "MOBILE",
            "clicks": Decimal("12"),
            "impressions": Decimal("300"),
            "position_weight": Decimal("2550"),
        }],
        "query_page_rows": [{
            "raw_query": "sports cave",
            "page_url": "https://www.sportscaveshop.com/",
            "clicks": Decimal("12"),
            "impressions": Decimal("300"),
            "position_weight": Decimal("2550"),
        }],
        "appearance_rows": [],
        "grain_truncation": {},
    }


class GSCPropertyIdentityTests(unittest.TestCase):
    def test_url_prefix_trailing_slash_uses_same_internal_key(self):
        self.assertTrue(google_seo.gsc_properties_match(
            "https://www.sportscaveshop.com/",
            "https://www.sportscaveshop.com",
        ))
        self.assertEqual(
            google_seo.canonical_gsc_property_key("https://www.sportscaveshop.com/"),
            "url:https://www.sportscaveshop.com",
        )

    def test_property_key_does_not_conflate_protocol_www_or_domain_properties(self):
        keys = {
            google_seo.canonical_gsc_property_key(value)
            for value in (
                "https://www.sportscaveshop.com/",
                "https://sportscaveshop.com/",
                "http://www.sportscaveshop.com/",
                "sc-domain:sportscaveshop.com",
            )
        }
        self.assertEqual(len(keys), 4)


class GSCConnectionStateTests(unittest.TestCase):
    def connection(self, **overrides):
        value = {
            "has_refresh_token": True,
            "gsc_site_url": "https://www.sportscaveshop.com/",
            "gsc_connection_test_status": "passed",
            "gsc_canonical_sync_status": "pending",
        }
        value.update(overrides)
        return value

    def test_valid_token_without_property_permission_is_not_ready(self):
        status = google_seo.gsc_connection_status_label(
            {"ready": True},
            self.connection(
                gsc_connection_test_status="failed",
                gsc_connection_test_error_code="gsc_property_permission_denied",
            ),
            {},
        )
        self.assertEqual(status, "Permission/property error")

    def test_connection_probe_rejects_selected_property_without_permission(self):
        connection = self.connection()
        with patch.object(
            google_seo,
            "_access_token_for_connection",
            return_value=("access-token", connection),
        ), patch.object(
            google_seo,
            "list_gsc_properties",
            return_value=[{
                "id": "https://example.com/",
                "permission_level": "siteOwner",
            }],
        ):
            with self.assertRaises(google_seo.GoogleSEOError) as raised:
                google_seo.probe_gsc_connection(Mock(), {})
        self.assertEqual(raised.exception.code, "gsc_property_permission_denied")
        self.assertFalse(raised.exception.reconnect_required)

    def test_permission_error_does_not_force_oauth_reconnection(self):
        response = FakeResponse({
            "error": {"status": "PERMISSION_DENIED", "message": "No access"}
        }, status_code=403)
        with self.assertRaises(google_seo.GoogleSEOError) as raised:
            google_seo._response_json(response, stage="gsc_connection_test")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertFalse(raised.exception.reconnect_required)

    def test_connected_empty_canonical_tables_require_initial_sync(self):
        status = google_seo.gsc_connection_status_label(
            {"ready": True}, self.connection(),
            {"available": False, "canonical_rows": 0, "legacy_rows": 0},
        )
        self.assertEqual(status, "Connected - initial data sync required")

    def test_legacy_rows_require_canonical_backfill(self):
        status = google_seo.gsc_connection_status_label(
            {"ready": True}, self.connection(),
            {"available": False, "canonical_rows": 0, "legacy_rows": 146453},
        )
        self.assertEqual(status, "Connected - canonical backfill required")

    def test_green_ready_requires_passed_test_and_canonical_rows(self):
        status = google_seo.gsc_connection_status_label(
            {"ready": True}, self.connection(gsc_canonical_sync_status="completed"),
            {"available": True, "canonical_rows": 1511},
        )
        self.assertEqual(status, "Connected and data ready")

    def test_canonical_detail_rows_without_property_totals_are_not_ready(self):
        status = google_seo.gsc_connection_status_label(
            {"ready": True}, self.connection(gsc_canonical_sync_status="completed"),
            {"available": False, "canonical_rows": 1511, "legacy_rows": 0},
        )
        self.assertEqual(status, "Connected - initial data sync required")


class GSCAPIContractTests(unittest.TestCase):
    def test_property_total_request_is_final_web_by_property(self):
        post = Mock(return_value=FakeResponse({
            "responseAggregationType": "byProperty",
            "rows": [{"clicks": 12, "impressions": 300, "ctr": .04, "position": 8.5}],
        }))
        result = google_seo_import.GoogleSEOReportingClient(
            "access-token", request_post=post
        ).fetch_gsc_property_totals(
            "https://www.sportscaveshop.com/", date(2026, 8, 8), date(2026, 8, 14)
        )
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("dimensions", payload)
        self.assertEqual(payload["aggregationType"], "byProperty")
        self.assertEqual(payload["dataState"], "final")
        self.assertEqual(payload["type"], "web")
        self.assertEqual(result["clicks"], Decimal("12"))

    def test_query_request_paginates_without_guessing(self):
        post = Mock(side_effect=[
            FakeResponse({"rows": [{"keys": ["a", "aus", "MOBILE"]}] * 2}),
            FakeResponse({"rows": [{"keys": ["b", "usa", "DESKTOP"]}]}),
        ])
        client = google_seo_import.GoogleSEOReportingClient("token", request_post=post)
        with patch.object(google_seo_import, "GSC_PAGE_SIZE", 2), patch.object(
            google_seo_import, "GSC_DAILY_ROW_LIMIT", 10
        ):
            result = client.fetch_gsc_query_range(
                "https://www.sportscaveshop.com/", date(2026, 8, 8), date(2026, 8, 14)
            )
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["startRow"], 0)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["startRow"], 2)


class GSCCanonicalWriterTests(unittest.TestCase):
    def test_successful_slice_writes_all_canonical_grains_and_manifest(self):
        backend = RecordingBackend()
        store = google_seo_import.PostgresSEOImportStore(backend)
        store._schema_ready = True
        result = store.replace_gsc_date(
            "https://www.sportscaveshop.com/", canonical_slice()
        )
        sql = "\n".join(call[0] for call in backend.cursor.calls)
        many_sql = "\n".join(call[0] for call in backend.cursor.many_calls)
        self.assertIn("INSERT INTO seo_gsc_property_totals_v2", sql)
        self.assertIn("INSERT INTO seo_gsc_query_daily_v2", many_sql)
        self.assertIn("INSERT INTO seo_gsc_page_daily_v2", many_sql)
        self.assertIn("INSERT INTO seo_gsc_query_page_daily_v2", many_sql)
        self.assertIn("INSERT INTO seo_gsc_canonical_date_status", sql)
        self.assertTrue(result["canonical_complete"])

    def test_repeated_slice_replaces_same_date_before_insert(self):
        backend = RecordingBackend()
        store = google_seo_import.PostgresSEOImportStore(backend)
        store._schema_ready = True
        store.replace_gsc_date("https://www.sportscaveshop.com/", canonical_slice())
        store.replace_gsc_date("https://www.sportscaveshop.com", canonical_slice())
        canonical_deletes = [
            sql for sql, _params in backend.cursor.calls
            if sql.startswith("DELETE FROM seo_gsc_property_totals_v2")
        ]
        self.assertEqual(len(canonical_deletes), 2)
        self.assertTrue(all("property_key=%s" in sql for sql in canonical_deletes))

    def test_failure_path_does_not_delete_last_good_canonical_rows(self):
        source = inspect.getsource(google_seo_import.PostgresSEOImportStore.fail_run)
        self.assertNotIn("DELETE FROM seo_gsc_", source)
        self.assertIn("gsc_canonical_sync_status", source)

    def test_legacy_backfill_uses_authoritative_totals_not_visible_query_sum(self):
        source = inspect.getsource(
            google_seo_import.PostgresSEOImportStore.backfill_gsc_canonical_from_legacy
        )
        self.assertIn("FROM seo_gsc_daily_totals", source)
        self.assertNotIn("SUM(clicks) AS property", source)
        self.assertIn("position_weight", source)
        self.assertIn('"write_legacy": False', source)

    def test_completion_requires_canonical_date_manifest(self):
        source = inspect.getsource(google_seo_import.PostgresSEOImportStore.complete_run)
        self.assertIn("canonical_gsc_range_status", source)
        self.assertIn("gsc_canonical_incomplete", source)


class GSCReaderAndOrchestrationTests(unittest.TestCase):
    def test_cached_empty_reader_key_includes_canonical_revision(self):
        filters = {
            "preset": "Last 7 days", "market": "All markets", "device": "All devices",
            "compare": False, "comparison": "Off", "search_type": "web",
            "query_class": "All known queries", "custom_start": None, "custom_end": None,
        }
        cached = Mock(return_value={})
        reader = Mock()
        reader.cache_revision.return_value = 42
        with patch.object(seo_page, "_cached_default_reporting_snapshot", cached), patch.object(
            seo_live_analytics, "default_reader", return_value=reader
        ):
            seo_page._load_reporting_snapshot(filters)
        self.assertEqual(cached.call_args.args[-1], 42)

    def test_source_health_cache_is_also_keyed_by_canonical_revision(self):
        parameters = inspect.signature(
            seo_page._cached_default_live_source_health.__wrapped__
        ).parameters
        self.assertIn("cache_revision", parameters)

    def test_failed_google_worker_result_is_not_a_successful_pipeline_stage(self):
        source = inspect.getsource(seo_growth_intelligence.run_daily_analytics_refresh)
        self.assertIn('source_status not in {"completed", "preliminary"}', source)
        self.assertIn("_analytics_failure_summary", source)

    def test_all_rebuilt_search_pages_use_the_compact_interactive_reader(self):
        for renderer in (
            seo_page._render_search_overview,
            seo_page._render_keywords_rankings,
            seo_page._render_opportunities,
            seo_page._render_search_landing_pages,
        ):
            source = inspect.getsource(renderer)
            self.assertIn("_interactive_reader", source)
            self.assertNotIn("_saved_search_snapshot", source)

    def test_normal_rendering_contains_no_live_google_request(self):
        source = inspect.getsource(seo_live_analytics.PostgresSEOLiveAnalyticsReader)
        self.assertNotIn("requests.", source)
        self.assertNotIn("googleapis.com", source)

    def test_startup_applies_every_gsc_pipeline_migration(self):
        with patch.object(sports_cave_server.run_migrations, "get_database_url", return_value=("db", "test")), patch.object(
            sports_cave_server.run_migrations, "run_migrations"
        ) as migrate, patch(
            "google_seo_phase4.ensure_initial_gsc_reporting_repair",
            return_value={"status": "not_required"},
        ) as initial_repair:
            self.assertTrue(sports_cave_server.prepare_google_seo_storage())
        self.assertEqual(
            [call.kwargs["only"] for call in migrate.call_args_list],
            list(google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS),
        )
        initial_repair.assert_called_once_with(schema_ready=True)

    def test_startup_pipeline_migrations_all_pass_the_real_safety_gate(self):
        real_run_migrations = sports_cave_server.run_migrations.run_migrations

        def safety_only(*, only):
            return real_run_migrations(only=only, check=True)

        with patch.object(
            sports_cave_server.run_migrations,
            "get_database_url",
            return_value=("db", "test"),
        ), patch.object(
            sports_cave_server.run_migrations,
            "run_migrations",
            side_effect=safety_only,
        ), patch(
            "google_seo_phase4.ensure_initial_gsc_reporting_repair",
            return_value={"status": "not_required"},
        ):
            self.assertTrue(sports_cave_server.prepare_google_seo_storage())

    def test_audit_is_ready_for_render_when_local_database_is_absent(self):
        with patch.object(audit_gsc_connection_and_data.run_migrations, "get_database_url", return_value=("", "")):
            result = audit_gsc_connection_and_data.run_audit(date(2026, 8, 14))
        self.assertFalse(result["ok"])
        self.assertIn("Render", result["reason"] + result["render_shell_command"])

    def test_audit_compares_clicks_and_impressions_at_reader_boundary(self):
        source = inspect.getsource(audit_gsc_connection_and_data._first_divergence)
        self.assertIn('reader.get("organic_clicks")', source)
        self.assertIn('reader.get("organic_impressions")', source)


class GSCPipelineMigrationTests(unittest.TestCase):
    def test_repair_migration_is_additive_and_indexed(self):
        sql = (ROOT / "migrations" / "20260817_gsc_canonical_pipeline_repair.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_gsc_canonical_date_status", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS property_key", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_seo_gsc_totals_v2_canonical_range", sql)
        self.assertNotIn("DROP TABLE", sql.upper())
        self.assertNotIn("TRUNCATE", sql.upper())


if __name__ == "__main__":
    unittest.main()
