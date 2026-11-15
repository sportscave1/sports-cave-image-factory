import inspect
from contextlib import nullcontext
from datetime import date
import threading
import unittest
from unittest.mock import Mock, patch

import google_seo_import
import run_migrations
import seo_growth_intelligence
import seo_page
import seo_technical_audit as technical
import shopify_sync


class FakeResponse:
    def __init__(self, status_code=200, *, url="", text="", headers=None, payload=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.headers = dict(headers or {})
        self._payload = payload if payload is not None else {}
        self.closed = False

    def close(self):
        self.closed = True

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class RecordingSession:
    def __init__(self, responder=None):
        self.headers = {}
        self.calls = []
        self.closed = False
        self.responder = responder

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, dict(kwargs)))
        if self.responder:
            return self.responder(method, url, kwargs)
        return FakeResponse(200, url=url, text="<title>Page</title><h1>Page</h1>")

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        self.closed = True


class FakeAuditStore:
    def __init__(self, urls, *, block_first_request=False):
        self.urls = list(urls)
        self.active = False
        self.guard = threading.Lock()
        self.runs = []
        self.finished = []
        self.page_states = []
        self.saved = []
        self.block_first_request = block_first_request

    def start_audit_run(self, run_id, **values):
        self.runs.append({"id": run_id, **values})

    def acquire_audit_lease(self, _run_id, _owner, **_kwargs):
        with self.guard:
            if self.active:
                return False
            self.active = True
            return True

    def renew_audit_lease(self, *_args, **_kwargs):
        return True

    def release_audit_lease(self, *_args, **_kwargs):
        with self.guard:
            self.active = False

    def finish_audit_run(self, run_id, **values):
        self.finished.append({"id": run_id, **values})

    def claim_rechecks(self, limit=20):
        return []

    def priority_urls(self, limit=20, full=False):
        return self.urls

    def save_url_findings(self, url, findings):
        self.saved.append((url, list(findings)))
        return len(findings)

    def save_page_state(self, **values):
        self.page_states.append(values)


class StorefrontCrawlerUnitTests(unittest.TestCase):
    def test_normalization_removes_equivalent_url_variants(self):
        self.assertEqual(
            technical.normalize_url(
                "HTTP://WWW.Example.COM:80/products//one/?utm_source=email&b=2&a=1#details"
            ),
            "https://example.com/products/one?a=1&b=2",
        )

    def test_page_fetches_are_cached_and_use_explicit_user_agent(self):
        session = RecordingSession()
        crawler = technical.StorefrontCrawler(
            session,
            request_interval_seconds=0,
            request_limit=10,
        )
        first = crawler.fetch_page("https://www.example.test/products/a?utm_source=x")
        second = crawler.fetch_page("http://example.test/products/a/#fragment")
        self.assertIs(first, second)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.headers["User-Agent"], technical.CRAWLER_USER_AGENT)
        self.assertEqual(crawler.stats["duplicate_urls_skipped"], 1)

    def test_link_status_uses_head_then_streaming_get_fallback(self):
        responses = [
            FakeResponse(405, url="https://example.test/missing"),
            FakeResponse(404, url="https://example.test/missing", text="large body should not be read"),
        ]
        session = RecordingSession(lambda *_args: responses.pop(0))
        crawler = technical.StorefrontCrawler(
            session,
            request_interval_seconds=0,
            request_limit=10,
        )
        self.assertEqual(crawler.check_status("https://example.test/missing"), 404)
        self.assertEqual([row[0] for row in session.calls], ["HEAD", "GET"])
        self.assertTrue(all(row[2]["stream"] for row in session.calls))
        self.assertEqual(crawler.stats["head_requests"], 1)
        self.assertEqual(crawler.stats["get_requests"], 1)

    def test_deterministic_rate_limit_spaces_requests(self):
        class Clock:
            value = 0.0

            def now(self):
                return self.value

            def sleep(self, seconds):
                self.value += seconds

        clock = Clock()
        request_times = []
        session = RecordingSession(
            lambda _method, url, _kwargs: (
                request_times.append(clock.value)
                or FakeResponse(200, url=url, text="<title>x</title><h1>x</h1>")
            )
        )
        crawler = technical.StorefrontCrawler(
            session,
            request_interval_seconds=1.25,
            request_limit=10,
            clock=clock.now,
            sleeper=clock.sleep,
        )
        crawler.fetch_page("https://example.test/a")
        crawler.fetch_page("https://example.test/b")
        self.assertEqual(request_times, [0.0, 1.25])

    def test_request_budget_is_a_hard_ceiling(self):
        crawler = technical.StorefrontCrawler(
            RecordingSession(),
            request_interval_seconds=0,
            request_limit=2,
        )
        crawler.fetch_page("https://example.test/a")
        crawler.fetch_page("https://example.test/b")
        with self.assertRaises(technical.RequestBudgetExceeded):
            crawler.fetch_page("https://example.test/c")
        self.assertEqual(crawler.stats["total_storefront_requests"], 2)


class TechnicalAuditIntegrationTests(unittest.TestCase):
    @staticmethod
    def _google_unavailable(*_args, **_kwargs):
        raise RuntimeError("Google evidence unavailable in this isolated test")

    def test_one_session_deduplicates_and_bounds_many_urls(self):
        urls = []
        for index in range(15):
            urls.extend(
                [
                    {"canonical_url": f"https://www.example.test/products/{index}?utm_source=x#one", "page_type": "product"},
                    {"canonical_url": f"http://example.test/products/{index}/", "page_type": "product"},
                ]
            )
        store = FakeAuditStore(urls)
        sessions = []

        def session_factory():
            session = RecordingSession(
                lambda method, url, _kwargs: FakeResponse(
                    200,
                    url=url,
                    text=(
                        f'<title>Page</title><meta name="description" content="x">'
                        f'<link rel="canonical" href="{url}"><h1>Page</h1>'
                        '<a href="/shared?utm_campaign=test">Shared</a>'
                    ) if method == "GET" else "",
                )
            )
            sessions.append(session)
            return session

        with patch.object(technical.google_seo, "access_token_for_connection", self._google_unavailable):
            result = technical.run_background_audit(
                store=store,
                connection_store=object(),
                session_factory=session_factory,
                page_limit=20,
                inspection_limit=0,
                internal_link_limit=5,
                request_interval_seconds=0,
                request_limit=25,
                trigger_source="regression-test",
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].closed)
        self.assertEqual(result["pages_scheduled"], 15)
        self.assertEqual(result["pages_fetched"], 15)
        self.assertEqual(result["get_requests"], 15)
        self.assertEqual(result["head_requests"], 1)
        self.assertEqual(result["total_storefront_requests"], 16)
        self.assertGreaterEqual(result["duplicate_urls_skipped"], 15)
        self.assertEqual(len({row[0] for row in store.saved}), 15)
        self.assertEqual(len(store.page_states), 15)

    def test_session_start_failure_releases_durable_lease(self):
        store = FakeAuditStore([{"canonical_url": "https://example.test/a"}])
        result = technical.run_background_audit(
            store=store,
            connection_store=object(),
            session_factory=Mock(side_effect=RuntimeError("session failed")),
            request_interval_seconds=0,
        )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(store.active)
        self.assertEqual(store.finished[-1]["status"], "failed")

    def test_concurrent_attempt_returns_already_running_without_second_session(self):
        store = FakeAuditStore([{"canonical_url": "https://example.test/a"}])
        request_started = threading.Event()
        release_request = threading.Event()
        sessions = []

        def session_factory():
            def responder(_method, url, _kwargs):
                request_started.set()
                release_request.wait(timeout=5)
                return FakeResponse(200, url=url, text="<title>A</title><h1>A</h1>")

            session = RecordingSession(responder)
            sessions.append(session)
            return session

        results = []
        with patch.object(technical.google_seo, "access_token_for_connection", self._google_unavailable):
            thread = threading.Thread(
                target=lambda: results.append(
                    technical.run_background_audit(
                        store=store,
                        connection_store=object(),
                        session_factory=session_factory,
                        inspection_limit=0,
                        internal_link_limit=0,
                        request_interval_seconds=0,
                    )
                )
            )
            thread.start()
            self.assertTrue(request_started.wait(timeout=5))
            second = technical.run_background_audit(
                store=store,
                connection_store=object(),
                session_factory=session_factory,
                inspection_limit=0,
                internal_link_limit=0,
                request_interval_seconds=0,
            )
            release_request.set()
            thread.join(timeout=5)
        self.assertEqual(second["status"], "already_running")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(results[0]["status"], "completed")

    def test_safety_migration_is_additive(self):
        migration = technical.BASE_DIR / "migrations" / "20260819_technical_audit_safety.sql"
        self.assertTrue(run_migrations.safe_migration_sql(migration.read_text(encoding="utf-8")))


class StorefrontIsolationTests(unittest.TestCase):
    def test_analytics_and_growth_reporting_have_no_technical_crawl_stage(self):
        analytics_source = inspect.getsource(seo_growth_intelligence.run_daily_analytics_refresh)
        growth_source = inspect.getsource(seo_growth_intelligence.run_daily_growth_pipeline)
        self.assertNotIn("run_background_audit", analytics_source)
        self.assertNotIn("technical_audit", analytics_source)
        self.assertNotIn("run_background_audit", growth_source)
        self.assertNotIn("technical_audit", dict(seo_growth_intelligence.PIPELINE_STAGES))

    def test_normal_analytics_refresh_makes_zero_storefront_crawler_calls(self):
        class Store:
            def queue_pipeline_run(self, **_kwargs):
                return {"id": "analytics-1", "status": "queued"}

            def claim_pipeline_run(self, _worker_id, **_kwargs):
                return {"id": "analytics-1", "status": "running"}

            def renew_pipeline_lease(self, *_args, **_kwargs):
                return True

            def ensure_schema(self):
                return None

            def start_stage(self, *_args, **_kwargs):
                return None

            def complete_stage(self, *_args, **_kwargs):
                return None

            def fail_stage(self, *_args, **_kwargs):
                raise AssertionError("analytics refresh stage failed")

            def complete_pipeline(self, pipeline_id, **values):
                return {"id": pipeline_id, **values}

        class Phase4:
            def map_saved_urls(self):
                return {"status": "completed", "written": 1}

            def reconcile_revenue(self):
                return {"status": "completed", "written": 1}

            def refresh_reporting_snapshots(self):
                return {"status": "completed", "written": 1}

            def refresh_health(self):
                return {}

        class Worker:
            def __init__(self, **_kwargs):
                pass

            def run_once(self, **_kwargs):
                return {"status": "completed", "written": 1}

        class HealthReader:
            def __init__(self, _store):
                pass

            def source_health(self):
                return {
                    "gsc": {"rows": 1, "through_date": "2026-08-18"},
                    "ga4": {"rows": 1, "through_date": "2026-08-18"},
                    "shopify": {"rows": 1, "through_date": "2026-08-18"},
                }

        with patch.object(google_seo_import, "SEOImportWorker", Worker), patch.object(
            google_seo_import, "queue_daily_source", return_value={"status": "queued"}
        ), patch.object(
            seo_growth_intelligence.analytics_reporting,
            "refresh_saved_report_contracts",
            return_value={"status": "completed", "written": 1},
        ), patch.object(
            seo_growth_intelligence.seo_live_analytics,
            "PostgresSEOLiveAnalyticsReader",
            HealthReader,
        ), patch.object(technical, "run_background_audit") as audit:
            result = seo_growth_intelligence.run_daily_analytics_refresh(
                store=Store(),
                import_store=object(),
                phase4_store=Phase4(),
                connection_store=object(),
                fresh_gsc_refresher=lambda: {"status": "preliminary", "written": 1},
            )
        self.assertEqual(result["status"], "completed")
        audit.assert_not_called()

    def test_gsc_refresh_calls_only_search_console_api(self):
        calls = []

        def post(url, **_kwargs):
            calls.append(url)
            return FakeResponse(200, payload={"rows": []})

        client = google_seo_import.GoogleSEOReportingClient("token", request_post=post)
        client.fetch_gsc_property_totals(
            "sc-domain:sportscave.com.au", date(2026, 8, 18), date(2026, 8, 18)
        )
        self.assertTrue(calls)
        self.assertTrue(all(url.startswith("https://www.googleapis.com/webmasters/") for url in calls))

    def test_ga4_refresh_calls_only_analytics_data_api(self):
        calls = []

        def post(url, **_kwargs):
            calls.append(url)
            return FakeResponse(200, payload={"rowCount": 0, "rows": []})

        client = google_seo_import.GoogleSEOReportingClient("token", request_post=post)
        client.fetch_ga4_date(
            "1234",
            date(2026, 8, 18),
            dimensions=google_seo_import.GA4_REQUIRED_DIMENSIONS,
        )
        self.assertTrue(calls)
        self.assertTrue(all(url.startswith("https://analyticsdata.googleapis.com/") for url in calls))

    def test_shopify_refresh_uses_admin_graphql_not_product_pages(self):
        calls = []

        def post(url, **_kwargs):
            calls.append((url, _kwargs))
            return FakeResponse(
                200,
                headers={"X-Shopify-API-Version": "2026-07"},
                payload={"data": {"shop": {"name": "Sports Cave"}}},
            )

        data, version = shopify_sync.graphql_request(
            "query { shop { name } }",
            config={
                "store_domain": "sports-cave-test.myshopify.com",
                "api_version": "2026-07",
                "access_token": "test-token",
                "client_id": "",
                "client_secret": "",
            },
            request_post=post,
        )
        self.assertEqual(data["shop"]["name"], "Sports Cave")
        self.assertEqual(version, "2026-07")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            "https://sports-cave-test.myshopify.com/admin/api/2026-07/graphql.json",
        )
        self.assertNotIn("/products/", calls[0][0])

    def test_streamlit_analytics_and_health_rerenders_do_not_crawl(self):
        class Reader:
            def _query_all(self, *_args, **_kwargs):
                return []

        class GrowthStore:
            def recent_pipeline_status(self):
                return {}

        fake_st = Mock()
        fake_st.button.return_value = False
        fake_st.expander.side_effect = lambda *_args, **_kwargs: nullcontext()
        with patch.object(seo_page, "st", fake_st), patch.object(
            seo_page, "_header"
        ), patch.object(seo_page, "_table"), patch.object(
            seo_page.os_accounts, "is_admin", side_effect=lambda user: bool(user.get("admin"))
        ), patch.object(
            technical, "run_background_audit"
        ) as audit:
            seo_page._render_seo_health({}, reporting_reader=Reader())
            seo_page._render_seo_health({}, reporting_reader=Reader())
            seo_page._render_analytics_refresh_admin({"admin": True}, growth_store=GrowthStore())
            seo_page._render_analytics_refresh_admin({"admin": True}, growth_store=GrowthStore())
        audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
