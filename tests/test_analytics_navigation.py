from pathlib import Path
import unittest

import analytics_navigation
import navigation_runtime
import os_accounts
import seo_navigation


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
            self.assertEqual(os_accounts.PAGE_BY_ROUTE[route]["parent_key"], seo_navigation.SEO_PAGE_KEY)

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

    def test_sidebar_places_analytics_immediately_above_seo(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertLess(source.index('"sidebar-analytics-children"'), source.index('"sidebar-seo-children"'))
        self.assertIn("force_open_routes=analytics_nav.ANALYTICS_ROUTES", source)
        self.assertIn("force_open_routes=seo_nav.SEO_ROUTES", source)

    def test_legacy_combined_analytics_keys_redirect_to_analytics(self):
        for key in analytics_navigation.LEGACY_ANALYTICS_PAGE_KEYS:
            self.assertEqual(os_accounts.normalise_page_key(key), analytics_navigation.ANALYTICS_PAGE_KEY)


if __name__ == "__main__":
    unittest.main()
