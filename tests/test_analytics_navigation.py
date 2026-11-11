from pathlib import Path
import unittest
from unittest.mock import patch

import analytics_navigation
import navigation_runtime
import os_accounts
import seo_navigation
import social_media


ROOT = Path(__file__).resolve().parents[1]


class AnalyticsNavigationTests(unittest.TestCase):
    def test_analytics_and_seo_are_distinct_top_level_parents(self):
        analytics_parent = os_accounts.PAGE_BY_KEY[analytics_navigation.ANALYTICS_PAGE_KEY]
        seo_parent = os_accounts.PAGE_BY_KEY[seo_navigation.SEO_PAGE_KEY]
        self.assertEqual(analytics_parent["route"], analytics_navigation.ANALYTICS_OVERVIEW_ROUTE)
        self.assertEqual(seo_parent["route"], seo_navigation.SEO_OVERVIEW_ROUTE)
        self.assertNotEqual(analytics_parent["key"], seo_parent["key"])
        for route in analytics_navigation.ANALYTICS_ROUTES[1:]:
            self.assertEqual(os_accounts.PAGE_BY_ROUTE[route]["parent_key"], analytics_navigation.ANALYTICS_PAGE_KEY)
        for route in seo_navigation.SEO_ROUTES[1:]:
            if route != analytics_navigation.WEBSITE_OVERVIEW_ROUTE:
                self.assertEqual(os_accounts.PAGE_BY_ROUTE[route]["parent_key"], seo_navigation.SEO_PAGE_KEY)
        website = os_accounts.PAGE_BY_ROUTE[analytics_navigation.WEBSITE_OVERVIEW_ROUTE]
        self.assertEqual(website["label"], "Website")
        for route in analytics_navigation.WEBSITE_ROUTES[1:]:
            self.assertEqual(os_accounts.PAGE_BY_ROUTE[route]["parent_key"], website["key"])

    def test_active_children_force_their_own_disclosure_open(self):
        for route in analytics_navigation.ANALYTICS_ROUTES:
            self.assertEqual(
                navigation_runtime.active_disclosure_group(route, analytics_routes=analytics_navigation.ANALYTICS_ROUTES),
                "analytics",
            )
        for route in seo_navigation.SEO_ROUTES:
            self.assertEqual(
                navigation_runtime.active_disclosure_group(route, seo_routes=seo_navigation.SEO_ROUTES),
                "seo",
            )

    def test_overview_is_visible_in_analytics_and_seo_submenus(self):
        self.assertEqual(
            navigation_runtime.disclosure_child_routes(
                analytics_navigation.ANALYTICS_ROUTES,
                analytics_navigation.ANALYTICS_OVERVIEW_ROUTE,
                include_overview=True,
            )[0],
            analytics_navigation.ANALYTICS_OVERVIEW_ROUTE,
        )
        self.assertEqual(
            navigation_runtime.disclosure_child_routes(
                seo_navigation.SEO_ROUTES,
                seo_navigation.SEO_OVERVIEW_ROUTE,
                include_overview=True,
            )[0],
            seo_navigation.SEO_OVERVIEW_ROUTE,
        )

    def test_website_opens_the_moved_report_and_owns_the_tool_routes(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / "tests/sidebar_preview_app.py")).run()
        app.sidebar.button(key="sidebar-disclosure::website").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["route"], analytics_navigation.WEBSITE_OVERVIEW_ROUTE)
        for route in analytics_navigation.WEBSITE_ROUTES:
            self.assertIsNotNone(app.sidebar.button(key=f"sidebar-child::{route}"))
        self.assertNotIn(analytics_navigation.WEBSITE_OVERVIEW_ROUTE, seo_navigation.SEO_MENU_ROUTES)

    def test_moving_tools_preserves_their_access(self):
        worker = {"role": "worker", "is_active": True, "page_permissions": ["analytics"]}
        self.assertTrue(os_accounts.can_access_page(worker, analytics_navigation.WEBSITE_OVERVIEW_ROUTE))
        self.assertFalse(os_accounts.can_access_page(worker, analytics_navigation.PRODUCT_QUIZ_ROUTE))
        self.assertFalse(os_accounts.can_access_page(worker, social_media.WALL_PREVIEW_ROUTE))
        worker["page_permissions"] = ["social_media"]
        self.assertFalse(os_accounts.can_access_page(worker, analytics_navigation.WEBSITE_OVERVIEW_ROUTE))
        self.assertTrue(os_accounts.can_access_page(worker, social_media.WALL_PREVIEW_ROUTE))

    def test_website_overview_keeps_google_reporting_and_shows_tool_summaries(self):
        from streamlit.testing.v1 import AppTest
        import tempfile

        fixture = ROOT / "tests/fixtures/seo_phase1_preview.py"
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"SEO_PHASE1_FIXTURE_DIR": tmp}), \
             patch("seo_phase1.local_mode", return_value=False), \
             patch("product_quiz_page.quiz_report", return_value=[{"event": "started", "count": 9}]), \
             patch("wall_preview_analytics_ui.snapshot", return_value={"engagement": {"opens": 5, "confirmed": 3, "atc": 2}}):
            app = AppTest.from_file(fixture)
            app.session_state["fixture-route"] = analytics_navigation.WEBSITE_OVERVIEW_ROUTE
            app.run()
        self.assertFalse(app.exception)
        self.assertIn("Google organic clicks", [metric.label for metric in app.metric])
        summary = next(node.value for node in app.markdown if 'sc-website-tools' in node.value)
        self.assertIn("Wall Preview", summary)
        self.assertIn("Preview opens <strong>5</strong>", summary)
        self.assertIn("Product Quiz", summary)
        self.assertIn("Starts <strong>9</strong>", summary)

    def test_legacy_combined_analytics_keys_redirect_to_analytics(self):
        for key in analytics_navigation.LEGACY_ANALYTICS_PAGE_KEYS:
            self.assertEqual(os_accounts.normalise_page_key(key), analytics_navigation.ANALYTICS_PAGE_KEY)


if __name__ == "__main__":
    unittest.main()
