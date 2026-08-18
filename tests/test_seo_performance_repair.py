from pathlib import Path
import inspect
import unittest

import google_seo
import google_seo_phase4
import navigation_runtime
import seo_page
import seo_pagination
import seo_reporting_runtime


ROOT = Path(__file__).resolve().parents[1]


class SEOLazyExecutionRepairTests(unittest.TestCase):
    def test_only_selected_route_renderer_executes(self):
        calls = []
        result = navigation_runtime.dispatch_selected(
            "Keywords & Rankings",
            {
                "SEO Overview": lambda: calls.append("overview"),
                "Keywords & Rankings": lambda: calls.append("keywords") or "done",
                "SEO Opportunities": lambda: calls.append("opportunities"),
            },
        )
        self.assertEqual(result, "done")
        self.assertEqual(calls, ["keywords"])

    def test_overview_resolves_selected_view_before_page_specific_read(self):
        source = inspect.getsource(seo_page._render_search_overview)
        selected = source.index('view = st.segmented_control(')
        detail_read = source.index("_progressive_query_rows(")
        self.assertLess(selected, detail_read)
        self.assertNotIn("st.tabs(", source)
        self.assertIn('view == "Rank distribution" and reader is not None', source)
        self.assertIn("reader.rank_distribution(filters, context=context)", source)

    def test_collapsed_admin_no_longer_executes_inside_an_expander(self):
        source = inspect.getsource(seo_page._render_search_overview)
        self.assertNotIn('with st.expander("Data Connections & Sync Settings"', source)
        self.assertIn("_render_data_connections_admin(", source)

    def test_routes_without_workspace_state_skip_store_load(self):
        source = inspect.getsource(seo_page._render_active_route)
        state_routes = source[
            source.index("state_routes = {") : source.index("if route in state_routes:")
        ]
        self.assertNotIn("SEO_OVERVIEW_ROUTE", state_routes)
        self.assertNotIn("SEO_LANDING_PAGES_ROUTE", state_routes)
        self.assertNotIn("SEO_HEALTH_ROUTE", state_routes)


class SEOSnapshotReaderRepairTests(unittest.TestCase):
    def test_interactive_reader_never_uses_raw_gsc_history_or_google(self):
        source = inspect.getsource(seo_reporting_runtime.PostgresSEOInteractiveReader)
        self.assertIn("seo_reporting_query_daily", source)
        self.assertIn("seo_reporting_landing_page_daily", source)
        self.assertNotIn("seo_gsc_query_daily_v2", source)
        self.assertNotIn("seo_gsc_daily_details", source)
        self.assertNotIn("googleapis.com", source)
        self.assertNotIn("requests.", source)

    def test_branded_overview_aggregates_detail_rows(self):
        source = inspect.getsource(
            seo_reporting_runtime.PostgresSEOInteractiveReader.overview_base
        )
        self.assertIn('summary=search_class == "all"', source)

    def test_watermark_contains_snapshot_and_source_revision(self):
        class Cursor:
            def execute(self, _sql, _params=()):
                return None

            def fetchone(self):
                return {
                    "latest_status": "completed",
                    "snapshot_id": "snapshot-9",
                    "common_reporting_date": "2026-08-17",
                    "refreshed_at": "2026-08-18T00:00:00Z",
                    "source_revision": 42,
                    "gsc_site_url": "https://example.test/",
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
        self.assertEqual(context["watermark"], "snapshot-9|2026-08-17|42")
        self.assertTrue(context["available"])

    def test_cache_key_contract_accepts_watermark(self):
        parameters = inspect.signature(
            seo_page._cached_interactive_overview.__wrapped__
        ).parameters
        self.assertIn("watermark", parameters)

    def test_performance_migration_is_additive_and_registered(self):
        name = "20260818_seo_interactive_performance.sql"
        sql = (ROOT / "migrations" / name).read_text(encoding="utf-8")
        self.assertIn("CREATE INDEX IF NOT EXISTS", sql)
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())
        self.assertIn(name, google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS)
        self.assertIn(name, google_seo_phase4.PHASE4_MIGRATIONS)


class SEOProgressivePaginationTests(unittest.TestCase):
    def test_append_has_no_duplicates_or_missing_rows(self):
        state = seo_pagination.initial_state("a", 25)
        first = {
            "rows": [{"query": f"q-{index}"} for index in range(25)],
            "total": 50,
            "next_cursor": {"query": "q-24"},
        }
        second = {
            "rows": [{"query": f"q-{index}"} for index in range(24, 50)],
            "total": 50,
            "next_cursor": None,
        }
        state = seo_pagination.append_page(state, first)
        state = seo_pagination.append_page(state, second)
        self.assertEqual(len(state["rows"]), 50)
        self.assertEqual(len({row["query"] for row in state["rows"]}), 50)
        self.assertTrue(state["complete"])

    def test_filters_and_sort_persist_and_changes_reset(self):
        session = {}
        first_signature = seo_pagination.pagination_signature(
            {"market": "AU", "sort": "clicks", "search": "cave"}
        )
        state = seo_pagination.state_for(session, "table", signature=first_signature)
        state = seo_pagination.append_page(
            state,
            {"rows": [{"query": "sports cave"}], "total": 2, "next_cursor": {"query": "sports cave"}},
        )
        session["table"] = state
        self.assertEqual(
            seo_pagination.state_for(session, "table", signature=first_signature)["rows"],
            [{"query": "sports cave"}],
        )
        changed = seo_pagination.pagination_signature(
            {"market": "US", "sort": "clicks", "search": "cave"}
        )
        self.assertEqual(
            seo_pagination.state_for(session, "table", signature=changed)["rows"],
            [],
        )

    def test_server_order_has_stable_query_tie_breaker_and_keyset(self):
        source = inspect.getsource(seo_reporting_runtime.PostgresSEOInteractiveReader.query_page)
        self.assertIn("ORDER BY sort_score DESC, impressions DESC, query ASC", source)
        self.assertIn("query>%s", source)
        self.assertNotIn("OFFSET", source.upper())
        self.assertIn("LIMIT %s", source)

    def test_complete_export_is_explicit_and_never_rendered_as_show_all(self):
        reader_source = inspect.getsource(
            seo_reporting_runtime.PostgresSEOInteractiveReader.query_export
        )
        page_source = inspect.getsource(seo_page._progressive_query_rows)
        self.assertIn("_export_all=True", reader_source)
        self.assertIn("Prepare filtered CSV", page_source)
        self.assertNotIn("Show all", page_source)


class SportsCaveLoaderRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_loader_starts_completes_and_times_out(self):
        self.assertIn("beginNavigation", self.source)
        self.assertIn("completeNavigation", self.source)
        self.assertIn("12000", self.source)
        self.assertIn("clearNavigationPending({clearIntent: true})", self.source)
        self.assertIn("lastNavigationUsableMs", self.source)
        self.assertIn("if (wasPending || !root.dataset.lastNavigationStatus)", self.source)
        self.assertIn("if (wasPending) {", self.source)

    def test_latest_intent_and_history_are_guarded(self):
        self.assertIn("pending.route_key !== routeKey", self.source)
        self.assertIn("liveEpoch > Number(epoch", self.source)
        self.assertIn('parentWindow.addEventListener("popstate"', self.source)
        self.assertIn("visibleRoute === state.config.currentRouteKey", self.source)

    def test_loader_is_branded_mobile_safe_and_reduced_motion_safe(self):
        self.assertIn("sports-cave-navigation-loader", self.source)
        self.assertIn("#b79243", self.source)
        self.assertIn("prefers-reduced-motion", self.source)
        self.assertIn("#${LOADER_ID} { left: 0; }", self.source)
        self.assertIn("sc-navigation-skeleton", self.source)

    def test_errors_are_recoverable_instead_of_blank(self):
        source = inspect.getsource(seo_page._render_active_route)
        self.assertIn('button("Retry"', source)
        self.assertIn('button("Back"', source)
        self.assertIn('render_status = "error"', source)


if __name__ == "__main__":
    unittest.main()
