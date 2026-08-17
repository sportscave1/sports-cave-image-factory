import json
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

import app_branding
import daily_planner
import top_bar
import top_bar_security


ROOT = Path(__file__).resolve().parents[1]
TOP_BAR_CLIENT = ROOT / "components" / "sports_cave_top_bar" / "index.html"
PLANNER_CLIENT = ROOT / "components" / "daily_planner" / "index.html"
HOME_PLANNER_CLIENT = ROOT / "components" / "home_daily_planner" / "index.html"


class MobileShellTests(unittest.TestCase):
    def test_shared_mobile_layer_contains_layout_touch_and_safe_area_contracts(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 820px)", source)
        self.assertIn("(max-width: 940px) and (max-height: 520px)", source)
        self.assertIn("body.sc-mobile-nav-open", source)
        self.assertIn("transform: translateX(-102%)", source)
        self.assertIn("min-height: 44px !important", source)
        self.assertIn("font-size: 16px !important", source)
        self.assertIn("env(safe-area-inset-bottom)", source)
        self.assertIn('[data-testid="stDataFrame"]', source)
        self.assertIn("width: 100% !important", source)
        self.assertNotIn("contain: inline-size", source)
        self.assertIn('[data-testid="stDialog"] [role="dialog"]', source)
        self.assertIn("overflow-x: hidden !important", source)

    def test_top_bar_uses_existing_permission_scoped_sidebar_as_mobile_drawer(self):
        source = TOP_BAR_CLIENT.read_text(encoding="utf-8")

        self.assertEqual(1, source.count('id="sc-os-mobile-menu"'))
        self.assertIn('aria-controls="sports-cave-mobile-sidebar"', source)
        self.assertIn('sidebar.id = "sports-cave-mobile-sidebar"', source)
        self.assertIn("sc-mobile-nav-open", source)
        self.assertIn("closeMobileNavigation", source)
        self.assertIn("mobileViewport()", source)
        self.assertIn("(max-width: 940px) and (max-height: 520px)", source)
        self.assertNotIn("allowed_routes.forEach", source)

    def test_mobile_search_and_timer_are_kept_inside_the_compact_toolbar(self):
        source = TOP_BAR_CLIENT.read_text(encoding="utf-8")

        self.assertEqual(1, source.count('id="sc-os-mobile-search"'))
        self.assertIn("sc-mobile-search-open", source)
        self.assertIn(".sc-os-planner-timer-pill:not([hidden]) + #sc-os-daily-planner", source)
        self.assertIn(".sc-os-planner-pill-time", source)
        self.assertIn("font-variant-numeric: tabular-nums", source)

    def test_top_bar_controller_rebinds_from_the_live_iframe_without_duplicates(self):
        source = TOP_BAR_CLIENT.read_text(encoding="utf-8")

        self.assertIn('CONTROLLER_VERSION = "navigation-reliability-v7"', source)
        self.assertIn("root.dataset.controllerVersion !== CONTROLLER_VERSION", source)
        self.assertIn("SportsCaveTopBar?.destroy?.({preserveDom: true})", source)
        self.assertIn("parentWindow.SportsCaveTopBar = createController()", source)
        self.assertEqual(1, source.count("setInterval(() =>"))
        self.assertIn("reconcileDocumentRoute();", source)
        self.assertIn("if (!state.orderStatusStarted)", source)
        self.assertIn("if (!state.plannerStatusStarted)", source)
        self.assertIn("listenerController.abort()", source)

    def test_top_bar_greeting_cannot_overlap_mobile_toolbar_controls(self):
        source = TOP_BAR_CLIENT.read_text(encoding="utf-8")

        self.assertIn(
            "grid-template-columns: var(--sc-sidebar-width) minmax(0, auto) minmax(260px, 1fr) auto",
            source,
        )
        self.assertIn(".sc-os-topbar-greeting", source)
        self.assertIn("max-width: min(22vw, 220px)", source)
        self.assertIn("text-overflow: ellipsis", source)
        self.assertIn(".sc-os-topbar-greeting { display: none; }", source)

    def test_top_bar_revision_is_stable_until_identity_or_permissions_change(self):
        admin = {
            "id": "admin-mobile",
            "role": "admin",
            "session_version": 3,
            "is_active": True,
            "page_permissions": [],
        }
        with mock.patch.object(
            top_bar_security,
            "create_top_bar_token",
            side_effect=("token-one", "token-two"),
        ):
            first = top_bar.top_bar_config(admin, logo_src="logo", current_route="Dashboard")
            second = top_bar.top_bar_config(admin, logo_src="logo", current_route="Orders")

        self.assertNotEqual(first["authToken"], second["authToken"])
        self.assertEqual(first["revision"], second["revision"])


class MobilePlannerTests(unittest.TestCase):
    def test_mobile_uses_same_planner_route_and_desktop_keeps_named_popup(self):
        source = TOP_BAR_CLIENT.read_text(encoding="utf-8")

        self.assertIn('state.config.dailyPlannerWindowUrl || "/daily-planner"', source)
        self.assertIn('sessionStorage.setItem("scSportsCavePlannerLaunchAuth"', source)
        self.assertIn('navigateDocument(url.toString())', source)
        self.assertIn('"sports_cave_daily_planner"', source)
        self.assertIn('"popup=yes,width=950,height=760,resizable=yes,scrollbars=yes"', source)

    def test_planner_consumes_mobile_auth_once_and_keeps_existing_api_contracts(self):
        source = PLANNER_CLIENT.read_text(encoding="utf-8")

        self.assertIn('sessionStorage.getItem("scSportsCavePlannerLaunchAuth")', source)
        self.assertIn('sessionStorage.removeItem("scSportsCavePlannerLaunchAuth")', source)
        self.assertIn("acceptPlannerAuth", source)
        for path in (
            "/api/os/daily-planner/bootstrap",
            "/api/os/daily-planner/mutate",
            "/api/os/daily-planner/history",
            "/api/os/daily-planner/weekly-review",
        ):
            self.assertIn(path, source)

    def test_planner_mobile_layout_preserves_actions_and_internal_modal_scrolling(self):
        source = PLANNER_CLIENT.read_text(encoding="utf-8")

        self.assertIn("viewport-fit=cover", source)
        self.assertIn("@media (max-width: 820px)", source)
        self.assertIn(".planner-modal-layer { align-items: flex-end; padding: 0; }", source)
        self.assertIn("overscroll-behavior: contain", source)
        self.assertIn("body.planner-modal-open .main", source)
        self.assertIn("font-size: 16px", source)
        self.assertIn('class="save-row mobile-sticky-actions"', source)
        self.assertEqual(1, source.count('class="save-row mobile-sticky-actions"'))
        for action in (
            "start-timer",
            "pause-timer",
            "resume-timer",
            "finish-task",
            "skip-task",
            "reopen-task",
        ):
            self.assertIn(action, source)
        self.assertIn("new Date(timer.deadline_at).valueOf() - Date.now()", source)

    def test_home_planner_panel_is_compact_and_mobile_safe(self):
        source = HOME_PLANNER_CLIENT.read_text(encoding="utf-8")

        self.assertIn("max-height: 280px", source)
        self.assertIn("max-height: 146px", source)
        self.assertIn("overflow-y: auto", source)
        self.assertIn("@media (max-width: 820px)", source)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", source)
        self.assertIn("min-height: 40px", source)
        self.assertNotIn("overflow-x: auto", source)
        self.assertNotIn("<input", source)

    def test_authenticated_planner_json_is_never_cacheable(self):
        response = daily_planner._json({"ok": True})

        self.assertEqual("no-store", response.headers["cache-control"])


class PwaInstallabilityTests(unittest.TestCase):
    def test_manifest_and_icons_are_install_ready(self):
        manifest = json.loads(
            (ROOT / "static" / "sports-cave-os-v1.webmanifest").read_text(encoding="utf-8")
        )
        self.assertEqual("Sports Cave OS", manifest["name"])
        self.assertEqual("Sports Cave OS", manifest["short_name"])
        self.assertEqual("/?page=dashboard", manifest["start_url"])
        self.assertEqual("/", manifest["scope"])
        self.assertEqual("standalone", manifest["display"])
        purposes = {icon.get("purpose") for icon in manifest["icons"]}
        sizes = {icon.get("sizes") for icon in manifest["icons"]}
        self.assertIn("maskable", purposes)
        self.assertTrue({"192x192", "512x512"}.issubset(sizes))
        for icon in manifest["icons"]:
            path = ROOT / icon["src"].removeprefix("/app/")
            expected = tuple(int(value) for value in icon["sizes"].split("x"))
            with Image.open(path) as image:
                self.assertEqual(expected, image.size)

    def test_install_metadata_has_one_safe_area_viewport_and_no_service_worker_cache(self):
        html = app_branding.initial_document_metadata_html()
        client = app_branding.install_metadata_html()
        combined_source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (ROOT / "components").rglob("*.html")
        )

        self.assertEqual(1, html.count('name="viewport"'))
        self.assertIn("viewport-fit=cover", html)
        self.assertIn('name="apple-mobile-web-app-status-bar-style"', html)
        self.assertIn('selector: \'meta[name="viewport"]\'', client)
        self.assertNotIn("serviceWorker.register", combined_source)
        self.assertFalse(any(ROOT.glob("static/*service*worker*")))
        self.assertFalse(any(ROOT.glob("static/sw.js")))


if __name__ == "__main__":
    unittest.main()
