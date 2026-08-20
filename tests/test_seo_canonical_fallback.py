from decimal import Decimal
import inspect
import unittest

from pglast import parse_sql

import seo_reporting_runtime


PROPERTY = "https://www.sportscaveshop.com/"


class _ScriptedCursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []
        self.current = None

    def execute(self, sql, params=()):
        self.statements.append((" ".join(str(sql).split()), tuple(params)))
        if not self.responses:
            raise AssertionError("Unexpected database query")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        self.current = response
        return self

    def fetchone(self):
        if isinstance(self.current, list):
            return dict(self.current[0]) if self.current else None
        return dict(self.current or {})

    def fetchall(self):
        if isinstance(self.current, list):
            return [dict(row) for row in self.current]
        return [dict(self.current)] if self.current else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Backend:
    def __init__(self, responses):
        self.cursor = _ScriptedCursor(responses)

    def connect(self):
        return _Connection(self.cursor)


def _filters(**overrides):
    result = {
        "preset": "Last 28 days",
        "market": "All markets",
        "device": "All devices",
        "search_type": "web",
        "query_class": "All known queries",
        "compare": True,
        "comparison": "Previous period",
    }
    result.update(overrides)
    return result


def _canonical_context(**overrides):
    result = {
        "available": True,
        "status": "canonical_fallback",
        "reader_path": "canonical",
        "snapshot_available": False,
        "snapshot_current": False,
        "canonical_available": True,
        "canonical_through_dates": {"web": "2026-08-16"},
        "through_date": "2026-08-16",
        "watermark": "canonical|none|2026-08-16|44|2026-08-16",
        "source_revision": 44,
        "snapshot_revision": 0,
        "gsc_site_url": PROPERTY,
        "brand_terms": ["sports cave"],
    }
    result.update(overrides)
    return result


class SEOCanonicalContextTests(unittest.TestCase):
    def test_current_snapshot_remains_preferred(self):
        backend = _Backend(
            [
                {
                    "latest_status": "completed",
                    "snapshot_id": "snapshot-44",
                    "gsc_reporting_through_date": "2026-08-16",
                    "snapshot_revision": 44,
                    "source_revision": 44,
                    "gsc_site_url": PROPERTY,
                    "canonical_through_dates": {"web": "2026-08-16"},
                    "brand_terms": ["sports cave"],
                }
            ]
        )
        context = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).reporting_context()

        self.assertEqual(context["reader_path"], "snapshot")
        self.assertEqual(context["status"], "ready")
        self.assertTrue(context["snapshot_current"])

    def test_snapshot_absent_with_canonical_rows_selects_fallback(self):
        backend = _Backend(
            [
                {
                    "latest_status": "failed",
                    "source_revision": 44,
                    "gsc_site_url": PROPERTY,
                    "canonical_through_dates": {"web": "2026-08-16"},
                }
            ]
        )
        context = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).reporting_context()

        self.assertTrue(context["available"])
        self.assertEqual(context["reader_path"], "canonical")
        self.assertEqual(context["status"], "canonical_fallback")
        self.assertEqual(context["through_date"], "2026-08-16")

    def test_stale_snapshot_uses_newer_canonical_revision(self):
        backend = _Backend(
            [
                {
                    "latest_status": "completed",
                    "snapshot_id": "snapshot-43",
                    "gsc_reporting_through_date": "2026-08-15",
                    "snapshot_revision": 43,
                    "source_revision": 44,
                    "gsc_site_url": PROPERTY,
                    "canonical_through_dates": {"web": "2026-08-16"},
                }
            ]
        )
        context = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).reporting_context()

        self.assertEqual(context["reader_path"], "canonical")
        self.assertEqual(context["through_date"], "2026-08-16")
        self.assertFalse(context["snapshot_current"])

    def test_no_snapshot_and_no_canonical_rows_is_genuine_unavailable(self):
        backend = _Backend(
            [{"source_revision": 0, "gsc_site_url": PROPERTY, "canonical_through_dates": {}}]
        )
        context = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).reporting_context()

        self.assertFalse(context["available"])
        self.assertEqual(context["reader_path"], "unavailable")

    def test_transient_database_error_is_not_converted_to_cached_empty_data(self):
        backend = _Backend([RuntimeError("temporary database failure")])
        with self.assertRaises(RuntimeError):
            seo_reporting_runtime.PostgresSEOInteractiveReader(backend).reporting_context()


class SEOCanonicalFallbackReadTests(unittest.TestCase):
    def test_overview_returns_weighted_real_metrics_and_previous_period(self):
        backend = _Backend(
            [
                {
                    "current_clicks": 10,
                    "current_impressions": 100,
                    "current_weight": 250,
                    "current_rows": 28,
                    "previous_clicks": 4,
                    "previous_impressions": 80,
                    "previous_weight": 320,
                    "previous_rows": 28,
                },
                [
                    {
                        "date": "2026-08-16",
                        "organic_clicks": 10,
                        "organic_impressions": 100,
                        "position_weight": 250,
                    }
                ],
                {"known_clicks": 8, "known_impressions": 80, "quality_weight": 60},
            ]
        )
        reader = seo_reporting_runtime.PostgresSEOInteractiveReader(backend)
        result = reader.overview_base(_filters(), context=_canonical_context())

        self.assertTrue(result["ready"])
        self.assertTrue(result["fallback_mode"])
        self.assertEqual(result["current"]["organic_clicks"], Decimal("10"))
        self.assertEqual(result["current"]["ctr"], Decimal("0.1"))
        self.assertEqual(result["current"]["average_position"], Decimal("2.5"))
        self.assertEqual(result["previous"]["ctr"], Decimal("0.05"))
        self.assertEqual(result["previous"]["average_position"], Decimal("4"))
        self.assertEqual(result["rank_quality"]["score"], Decimal("75"))
        sql = "\n".join(statement for statement, _params in backend.cursor.statements)
        self.assertIn("FROM seo_gsc_property_totals_v2", sql)
        self.assertIn("FROM seo_gsc_query_daily_v2", sql)
        self.assertIn("source_date BETWEEN %s AND %s", sql)
        self.assertNotIn("seo_gsc_daily_details", sql)
        self.assertNotIn("property_key", sql)
        self.assertIn(PROPERTY, [value for _sql, params in backend.cursor.statements for value in params])
        for statement, params in backend.cursor.statements:
            self.assertEqual(statement.count("%s"), len(params))
            self.assertTrue(parse_sql(statement.replace("%s", "NULL")))

    def test_empty_selected_range_is_not_confused_with_snapshot_failure(self):
        backend = _Backend(
            [
                {
                    "current_clicks": 0,
                    "current_impressions": 0,
                    "current_weight": 0,
                    "current_rows": 0,
                    "previous_rows": 0,
                },
                [],
                {"known_clicks": 0, "known_impressions": 0, "quality_weight": 0},
            ]
        )
        result = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).overview_base(
            _filters(), context=_canonical_context()
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "no_saved_gsc_data_for_range")

    def test_query_page_reads_canonical_rows_with_filters_and_stable_pagination(self):
        backend = _Backend(
            [
                [
                    {
                        "query": "sports cave art",
                        "query_key": "sports cave art",
                        "query_hash": "abc",
                        "canonical_page_key": "",
                        "clicks": Decimal("7"),
                        "impressions": Decimal("70"),
                        "position_weight": Decimal("350"),
                        "ctr": Decimal("0.1"),
                        "average_position": Decimal("5"),
                        "previous_clicks": Decimal("3"),
                        "previous_impressions": Decimal("60"),
                        "previous_position": Decimal("7"),
                        "ranking_change": Decimal("2"),
                        "click_change": Decimal("4"),
                        "market_mix": ["AU"],
                        "device_mix": ["desktop"],
                        "sort_score": Decimal("7"),
                        "total_count": 1,
                    }
                ]
            ]
        )
        result = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).query_page(
            _filters(market="Australia", device="Desktop"),
            context=_canonical_context(),
            limit=25,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["query"], "sports cave art")
        self.assertEqual(result["rows"][0]["device_mix"], ["Desktop"])
        statement, params = backend.cursor.statements[0]
        self.assertIn("FROM seo_gsc_query_daily_v2", statement)
        self.assertIn("UPPER(country_code)=ANY(%s)", statement)
        self.assertIn("LOWER(device)=%s", statement)
        self.assertEqual(params.count(PROPERTY), 2)
        self.assertEqual(statement.count("%s"), len(params))
        self.assertTrue(parse_sql(statement.replace("%s", "NULL")))

    def test_landing_pages_use_saved_gsc_pages_without_ga4(self):
        backend = _Backend(
            [
                [
                    {
                        "canonical_url": f"{PROPERTY}products/example",
                        "title": "Example",
                        "page_type": "Product",
                        "clicks": 5,
                        "impressions": 50,
                        "position_weight": 200,
                        "sessions": 0,
                        "engaged_sessions": 0,
                        "total_count": 1,
                    }
                ]
            ]
        )
        result = seo_reporting_runtime.PostgresSEOInteractiveReader(backend).landing_pages(
            _filters(), context=_canonical_context()
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["ctr"], Decimal("0.1"))
        self.assertEqual(result["rows"][0]["average_position"], Decimal("4"))
        sql = backend.cursor.statements[0][0]
        self.assertIn("FROM seo_gsc_page_daily_v2", sql)
        self.assertNotIn("seo_ga4", sql)
        self.assertNotIn("seo_reporting_landing_page_daily", sql)
        self.assertEqual(sql.count("%s"), len(backend.cursor.statements[0][1]))
        self.assertTrue(parse_sql(sql.replace("%s", "NULL")))

    def test_reader_never_calls_google_or_requires_analytics(self):
        source = inspect.getsource(seo_reporting_runtime.PostgresSEOInteractiveReader)
        for forbidden in (
            "googleapis.com",
            "requests.get",
            "GoogleSEOReportingClient",
            "seo_ga4_daily_landing_pages",
            "shopify_orders",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
