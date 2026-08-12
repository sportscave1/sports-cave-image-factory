from pathlib import Path
from unittest import mock
import unittest

import navigation_runtime
import seo_navigation


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
                seo_navigation.SEO_CITATIONS_ROUTE,
                stored=None,
                social_routes=SOCIAL_ROUTES,
                seo_routes=seo_navigation.SEO_ROUTES,
            ),
            "seo",
        )
        self.assertEqual(
            navigation_runtime.initial_disclosure_group(
                seo_navigation.SEO_CITATIONS_ROUTE,
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

    def test_only_selected_renderer_executes(self):
        selected = mock.Mock(return_value="selected")
        inactive = mock.Mock()
        result = navigation_runtime.dispatch_selected(
            seo_navigation.SEO_CITATIONS_ROUTE,
            {
                seo_navigation.SEO_CITATIONS_ROUTE: selected,
                seo_navigation.SEO_BLOG_ROUTE: inactive,
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
        source = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        self.assertNotIn("st.tabs(", source)
        self.assertIn("st.segmented_control(", source)
        self.assertIn("navigation_runtime.dispatch_selected(", source)

    def test_sidebar_imports_only_lightweight_seo_navigation_metadata(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("import seo_navigation as seo_nav", source)
        self.assertNotIn("import seo_workspace", source)


if __name__ == "__main__":
    unittest.main()
