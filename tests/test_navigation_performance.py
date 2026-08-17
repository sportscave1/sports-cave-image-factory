from pathlib import Path
from unittest import mock
import inspect
import unittest

import navigation_runtime
import ads_navigation
import os_accounts
import seo_navigation
import seo_page


ROOT = Path(__file__).resolve().parents[1]
SOCIAL_ROUTES = {"Social Media", "AI Reels"}


class SidebarDisclosureTests(unittest.TestCase):
    def test_each_parent_opens_and_collapses(self):
        self.assertEqual(navigation_runtime.toggle_disclosure_group("", "social"), "social")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("social", "social"), "")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("", "seo"), "seo")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("seo", "seo"), "")

    def test_opening_another_parent_closes_the_previous_one(self):
        self.assertEqual(navigation_runtime.toggle_disclosure_group("social", "seo"), "seo")
        self.assertEqual(navigation_runtime.toggle_disclosure_group("seo", "social"), "social")

    def test_deep_route_opens_once_but_explicit_collapse_survives_rerun(self):
        self.assertEqual(
            navigation_runtime.initial_disclosure_group(
                seo_navigation.SEO_KEYWORDS_ROUTE,
                stored=None,
                social_routes=SOCIAL_ROUTES,
                seo_routes=seo_navigation.SEO_ROUTES,
            ),
            "seo",
        )
        self.assertEqual(
            navigation_runtime.initial_disclosure_group(
                seo_navigation.SEO_KEYWORDS_ROUTE,
                stored="",
                social_routes=SOCIAL_ROUTES,
                seo_routes=seo_navigation.SEO_ROUTES,
            ),
            "",
        )

    def test_toggle_is_navigation_only_and_invokes_no_heavy_loader(self):
        page_renderer = mock.Mock()
        seo_store_loader = mock.Mock()
        dropbox_loader = mock.Mock()
        self.assertEqual(navigation_runtime.toggle_disclosure_group("", "seo"), "seo")
        page_renderer.assert_not_called()
        seo_store_loader.assert_not_called()
        dropbox_loader.assert_not_called()

    def test_active_ads_routes_are_authoritative_over_persisted_disclosure_state(self):
        for route in ads_navigation.ADS_ROUTES:
            for stale_group in ("", "social", "seo", "reporting"):
                self.assertTrue(
                    navigation_runtime.disclosure_group_is_expanded(
                        route,
                        group="ads",
                        stored_group=stale_group,
                        force_open_routes=ads_navigation.ADS_ROUTES,
                    )
                )

        self.assertTrue(
            navigation_runtime.disclosure_group_is_expanded(
                "Dashboard",
                group="ads",
                stored_group="ads",
                force_open_routes=ads_navigation.ADS_ROUTES,
            )
        )
        self.assertFalse(
            navigation_runtime.disclosure_group_is_expanded(
                "Dashboard",
                group="ads",
                stored_group="seo",
                force_open_routes=ads_navigation.ADS_ROUTES,
            )
        )

    def test_only_selected_renderer_executes(self):
        selected = mock.Mock(return_value="selected")
        inactive = mock.Mock()
        result = navigation_runtime.dispatch_selected(
            seo_navigation.SEO_KEYWORDS_ROUTE,
            {
                seo_navigation.SEO_KEYWORDS_ROUTE: selected,
                seo_navigation.SEO_CITATIONS_ROUTE: inactive,
            },
        )
        self.assertEqual(result, "selected")
        selected.assert_called_once_with()
        inactive.assert_not_called()

    def test_sidebar_uses_one_fragment_button_and_integrated_css_chevron(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("@st.fragment\ndef _render_sidebar_create_growth", source)
        self.assertIn("button::after", source)
        self.assertIn("transform: rotate(-45deg)", source)
        self.assertIn("transform: rotate(45deg)", source)
        self.assertIn("transition: transform 140ms ease", source)
        self.assertIn('aria-expanded=', source)
        self.assertIn('aria-controls=', source)
        self.assertNotIn('"v" if expanded else ">"', source)
        self.assertNotIn('st.columns([5, 1]', source)

    def test_parent_toggle_does_not_navigate_and_email_has_no_route(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        toggle_start = source.index("def _toggle_sidebar_group")
        toggle_end = source.index("@st.fragment", toggle_start)
        self.assertNotIn("set_current_page", source[toggle_start:toggle_end])
        self.assertNotIn('"route": "Email"', source)

    def test_inactive_seo_tabs_are_not_constructed(self):
        source = inspect.getsource(seo_page._render_active_route)
        self.assertNotIn("st.tabs(", source)
        self.assertIn("navigation_runtime.dispatch_selected(", source)

    def test_sidebar_imports_only_lightweight_seo_navigation_metadata(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("import seo_navigation as seo_nav", source)
        self.assertNotIn("import seo_workspace", source)


class RouteReliabilityTests(unittest.TestCase):
    def test_browser_history_route_overrides_stale_session_route(self):
        route, source = navigation_runtime.resolve_route(
            session_route="Orders",
            query_route="Dashboard",
            query_value="dashboard",
            last_synced_query="orders",
        )
        self.assertEqual((route, source), ("Dashboard", "history"))

    def test_browser_back_to_root_returns_home(self):
        route, source = navigation_runtime.resolve_route(
            session_route="Orders",
            query_route="",
            query_value="",
            last_synced_query="orders",
        )
        self.assertEqual((route, source), ("Dashboard", "history"))

    def test_normal_rerun_keeps_the_committed_session_route(self):
        route, source = navigation_runtime.resolve_route(
            session_route="Edition Ops",
            query_route="Edition Ops",
            query_value="edition_ops",
            last_synced_query="edition_ops",
        )
        self.assertEqual((route, source), ("Edition Ops", "session"))

    def test_invalid_url_cannot_replace_a_working_route(self):
        route, source = navigation_runtime.resolve_route(
            session_route="Orders",
            query_route="",
            query_value="unknown-page",
            last_synced_query="orders",
        )
        self.assertEqual((route, source), ("Orders", "invalid-url"))

    def test_latest_of_100_mixed_transitions_wins_on_desktop_and_mobile(self):
        routes = tuple(page["route"] for page in os_accounts.PAGE_REGISTRY)
        for surface in ("desktop", "mobile"):
            session_route = "Dashboard"
            last_query = "dashboard"
            expected = session_route
            for index in range(100):
                expected = routes[(index + 1) % len(routes)]
                query_value = os_accounts.page_key_for_route(expected)
                resolved, source = navigation_runtime.resolve_route(
                    session_route=session_route,
                    query_route=expected,
                    query_value=query_value,
                    last_synced_query=last_query,
                )
                self.assertEqual(resolved, expected, f"{surface} transition {index}")
                self.assertEqual(source, "history")
                session_route = resolved
                last_query = query_value
            self.assertEqual(session_route, expected)

    def test_transition_epochs_are_monotonic_and_display_safe(self):
        first = navigation_runtime.route_transition(0, "Dashboard", "Orders", "sidebar")
        second = navigation_runtime.route_transition(
            first["epoch"],
            first["to"],
            "Design Studio",
            "history",
        )
        self.assertEqual(first["epoch"], 1)
        self.assertEqual(second["epoch"], 2)
        self.assertEqual(second["status"], "pending")
        self.assertNotIn("token", second)

    def test_app_uses_history_aware_resolution_and_recoverable_error_actions(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("navigation_runtime.resolve_route(", source)
        self.assertIn("CURRENT_PAGE_QUERY_STATE_KEY", source)
        self.assertIn("query_params.set_with_no_forward_msg", source)
        self.assertIn("NAVIGATION_CLIENT_ROUTE_STATE_KEY", source)
        self.assertIn('source == "sidebar"', source)
        self.assertIn('route, source = client_route, "client-transition"', source)
        self.assertIn("update_browser=not bool(", source)
        self.assertIn('retry_col.button("Retry"', source)
        self.assertIn('back_col.button("Back"', source)
        self.assertIn("_finish_navigation_transition(current_page, status=\"ready\")", source)

    def test_top_bar_navigation_feedback_and_lifecycle_are_idempotent(self):
        source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("const timers = new Set();", source)
        self.assertIn("timers.delete(timer);", source)
        self.assertIn("state.reportingBindTimer", source)
        self.assertIn("beginNavigation(intendedRouteKey);", source)
        self.assertIn('body.sc-navigation-pending #${ROOT_ID}::after', source)
        self.assertIn("listenerController.abort()", source)
        self.assertIn("destroy({preserveDom = false} = {})", source)
        self.assertIn("SportsCaveTopBar?.destroy?.({preserveDom: true})", source)
        self.assertIn("statusCacheKey = (kind)", source)
        self.assertIn("state.config.revision", source)
        self.assertIn('readStatusCache("orders")', source)
        self.assertIn("rememberPendingNavigation(routeKey)", source)
        self.assertIn("reconcilePendingNavigation", source)
        self.assertIn("handleHistoryNavigation", source)
        self.assertIn("historyDuplicateSkips", source)
        self.assertIn("visibleRoute === state.config.currentRouteKey", source)
        self.assertIn("parentWindow.history.pushState(", source)
        self.assertIn("bindPersistentSidebarRoutes", source)
        self.assertIn("button.dataset.scRouteKey", source)
        self.assertIn("h.dataset.configRevision", source)
        self.assertIn("scRecoveryScheduled", source)
        self.assertIn("stStatusWidget", source)
        self.assertIn("liveNavigationEpoch > incomingNavigationEpoch", source)
        self.assertIn("root.dataset.navigationEpoch", source)
        self.assertIn("navigation_epoch=st.session_state.get", (ROOT / "app.py").read_text(encoding="utf-8"))
        self.assertIn("navigationRouteKeys", (ROOT / "top_bar.py").read_text(encoding="utf-8"))
        self.assertEqual(source.count('doc.addEventListener("click"'), 1)
        self.assertEqual(source.count('parentWindow.addEventListener("popstate"'), 1)
        self.assertIn("sidebarRouteButton(routeKey)", source)


if __name__ == "__main__":
    unittest.main()
