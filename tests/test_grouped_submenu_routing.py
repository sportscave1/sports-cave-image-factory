from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import ads_navigation
import analytics_navigation
import navigation_runtime
import os_accounts
import seo_navigation


ROOT = Path(__file__).resolve().parents[1]


def authenticated_app(page_key="seo"):
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["sports_cave_authenticated"] = True
    app.session_state["startup_shell_loaded"] = True
    app.query_params["page"] = page_key
    return app.run(timeout=30)


def click_route(app, route):
    key = f"sidebar-child::{route}"
    button = next(item for item in app.sidebar.button if item.key == key)
    button.click()
    app.run(timeout=30)
    return app


def query_page(app):
    value = app.query_params["page"]
    return value[0] if isinstance(value, (list, tuple)) else value


class SEOFirstClickRoutingTests(unittest.TestCase):
    def test_every_seo_child_opens_on_first_click_and_survives_extra_rerun(self):
        app = authenticated_app()
        for route in seo_navigation.SEO_ROUTES[1:]:
            click_route(app, route)
            self.assertFalse(app.exception, route)
            self.assertEqual(app.session_state["current_page"], route)
            self.assertEqual(app.session_state["selected_page"], route)
            self.assertEqual(
                query_page(app),
                os_accounts.page_key_for_route(route),
            )
            self.assertEqual(app.session_state["sidebar-open-group"], "seo")
            app.run(timeout=30)
            self.assertEqual(app.session_state["current_page"], route)

        click_route(app, seo_navigation.SEO_OVERVIEW_ROUTE)
        self.assertEqual(app.session_state["current_page"], seo_navigation.SEO_OVERVIEW_ROUTE)
        self.assertEqual(query_page(app), seo_navigation.SEO_PAGE_KEY)
        self.assertEqual(app.session_state["sidebar-open-group"], "seo")

    def test_history_query_change_restores_child_and_expanded_parent(self):
        app = authenticated_app(seo_navigation.SEO_PAGE_KEY)
        click_route(app, seo_navigation.SEO_KEYWORDS_ROUTE)
        click_route(app, seo_navigation.SEO_LANDING_PAGES_ROUTE)

        app.query_params["page"] = seo_navigation.SEO_PAGE_KEYS[
            seo_navigation.SEO_KEYWORDS_ROUTE
        ]
        app.run(timeout=30)
        self.assertEqual(app.session_state["current_page"], seo_navigation.SEO_KEYWORDS_ROUTE)
        self.assertEqual(app.session_state["sidebar-open-group"], "seo")

        app.query_params["page"] = seo_navigation.SEO_PAGE_KEYS[
            seo_navigation.SEO_LANDING_PAGES_ROUTE
        ]
        app.run(timeout=30)
        self.assertEqual(
            app.session_state["current_page"],
            seo_navigation.SEO_LANDING_PAGES_ROUTE,
        )
        self.assertEqual(app.session_state["sidebar-open-group"], "seo")

    def test_empty_legacy_component_payload_cannot_reset_a_valid_child(self):
        app = authenticated_app(seo_navigation.SEO_PAGE_KEYS[seo_navigation.SEO_BLOG_ROUTE])
        app.session_state["navigation_client_route_pending"] = ""
        app.run(timeout=30)
        self.assertEqual(app.session_state["current_page"], seo_navigation.SEO_BLOG_ROUTE)
        self.assertNotIn("navigation_client_route_pending", app.session_state)


class SharedGroupedMenuRegressionTests(unittest.TestCase):
    def test_each_group_route_is_authoritative_over_a_stale_open_parent(self):
        grouped = {
            "seo": seo_navigation.SEO_ROUTES,
            "ads": ads_navigation.ADS_ROUTES,
            "analytics": analytics_navigation.ANALYTICS_ROUTES,
        }
        for group, routes in grouped.items():
            for route in routes:
                self.assertEqual(
                    navigation_runtime.initial_disclosure_group(
                        route,
                        stored="social",
                        seo_routes=seo_navigation.SEO_ROUTES,
                        ads_routes=ads_navigation.ADS_ROUTES,
                        analytics_routes=analytics_navigation.ANALYTICS_ROUTES,
                    ),
                    group,
                )

    def test_grouped_rows_are_full_width_native_keyboard_buttons(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        child_start = source.index("    def child_button(")
        child_end = source.index("    _sidebar_route_button", child_start)
        child_source = source[child_start:child_end]
        self.assertIn("row.button(", child_source)
        self.assertIn("use_container_width=True", child_source)
        self.assertNotIn("st.markdown(\"<a", child_source)


if __name__ == "__main__":
    unittest.main()
