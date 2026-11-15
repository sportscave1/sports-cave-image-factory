from pathlib import Path
import unittest

import navigation_runtime
import seo_navigation
import social_media


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class SidebarNavigationCleanupTests(unittest.TestCase):
    def test_unused_training_page_is_not_registered_or_discoverable(self):
        import os_accounts
        import app_search
        self.assertNotIn('va_training', os_accounts.PAGE_BY_KEY)
        self.assertNotIn('VA Training', os_accounts.PAGE_BY_ROUTE)
        self.assertNotIn('VA Training', APP_SOURCE)
        self.assertNotIn('va_training', app_search.ALIASES)
        routes = [page['route'] for page in os_accounts.PAGE_REGISTRY]
        self.assertFalse(any(row['route_key']=='va_training' for row in app_search.build_app_index(routes)))
        self.assertNotIn('VA Training', [page['route'] for page in os_accounts.navigation_pages()])

    def test_only_overview_routes_activate_disclosure_parents(self):
        self.assertTrue(
            navigation_runtime.disclosure_parent_is_active(
                social_media.SOCIAL_MEDIA_ROUTE,
                social_media.SOCIAL_MEDIA_ROUTE,
            )
        )
        self.assertFalse(
            navigation_runtime.disclosure_parent_is_active(
                social_media.AI_REELS_ROUTE,
                social_media.SOCIAL_MEDIA_ROUTE,
            )
        )
        self.assertTrue(
            navigation_runtime.disclosure_parent_is_active(
                seo_navigation.SEO_OVERVIEW_ROUTE,
                seo_navigation.SEO_OVERVIEW_ROUTE,
            )
        )
        self.assertFalse(
            navigation_runtime.disclosure_parent_is_active(
                seo_navigation.SEO_CITATIONS_ROUTE,
                seo_navigation.SEO_OVERVIEW_ROUTE,
            )
        )

    def test_overview_routes_are_not_rendered_as_children(self):
        self.assertEqual(
            navigation_runtime.disclosure_child_routes(
                (
                    social_media.SOCIAL_MEDIA_ROUTE,
                    social_media.AI_REELS_ROUTE,
                ),
                social_media.SOCIAL_MEDIA_ROUTE,
            ),
            (social_media.AI_REELS_ROUTE,),
        )
        self.assertEqual(
            navigation_runtime.disclosure_child_routes(
                seo_navigation.SEO_ROUTES,
                seo_navigation.SEO_OVERVIEW_ROUTE,
            ),
            seo_navigation.SEO_ROUTES[1:],
        )

    def test_parent_click_opens_group_and_navigates_to_existing_overview(self):
        disclosure_start = APP_SOURCE.index("    def disclosure(")
        disclosure_end = APP_SOURCE.index("    def child_button(", disclosure_start)
        disclosure_source = APP_SOURCE[disclosure_start:disclosure_end]

        self.assertIn("st.session_state[SIDEBAR_OPEN_GROUP_KEY] = group", disclosure_source)
        self.assertIn("set_current_page(overview_route, source=\"sidebar\")", disclosure_source)
        self.assertIn('st.rerun(scope="app")', disclosure_source)

    def test_disclosure_parent_style_uses_normal_sidebar_button_colours(self):
        from sidebar_theme import SIDEBAR_CSS
        self.assertIn('--sidebar-panel:#272826', SIDEBAR_CSS)
        self.assertIn('[class*="st-key-sidebar-disclosure-"]', SIDEBAR_CSS)
        self.assertIn('[class*="-children"]', SIDEBAR_CSS)
        self.assertNotIn('st-key-sidebar-disclosure-crm', SIDEBAR_CSS)

    def test_remaining_child_routes_and_deep_route_metadata_are_unchanged(self):
        self.assertIn(
            "elif current_page == social_media.AI_REELS_ROUTE:",
            APP_SOURCE,
        )
        for route in seo_navigation.SEO_ROUTES:
            self.assertIn(route, seo_navigation.SEO_NAV_LABELS)
        self.assertIn("elif current_page in seo_nav.SEO_ROUTES:", APP_SOURCE)
        self.assertIn("elif current_page == social_media.SOCIAL_MEDIA_ROUTE:", APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
