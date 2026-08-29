import inspect
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

import files_window_launcher
import orders_page
import ui_feedback
import ui_loading


class TemporaryNotificationLifecycleTests(unittest.TestCase):
    def test_parent_toast_runtime_owns_one_absolute_three_second_deadline(self):
        source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("TEMPORARY_TOAST_MS = 3000", source)
        self.assertIn("parentWindow.SportsCaveTemporaryToastRuntime", source)
        self.assertIn("current.identity === cleanIdentity", source)
        self.assertIn("current.expiresAt > now", source)
        self.assertIn("expiresAt: Date.now() + TEMPORARY_TOAST_MS", source)
        self.assertIn("this.entries.delete(channel)", source)
        self.assertIn("region.replaceChildren()", source)
        self.assertIn("entry.timer = parentWindow.setTimeout(() => this.dismiss(channel), TEMPORARY_TOAST_MS)", source)
        self.assertNotIn("state.orderToastTimer", source)
        self.assertNotIn("state.plannerToastTimer", source)

    def test_parent_toasts_have_accessible_manual_dismiss_controls(self):
        source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('close.className = "sc-os-toast-close"', source)
        self.assertIn('close.textContent = "×"', source)
        self.assertIn('close.setAttribute("aria-label", label)', source)
        self.assertIn('close.title = label', source)
        self.assertIn('event.stopPropagation()', source)
        self.assertIn('appendToastClose(toast, dismissOrderToast)', source)
        self.assertIn('appendToastClose(toast, dismissPlannerToast)', source)

    def test_expired_and_dismissed_parent_toasts_do_not_return_on_rerun(self):
        source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )

        expired_cleanup = source.index("if (current && current.expiresAt <= now)")
        remembered_check = source.index("if (remember && this.seen.has(seenIdentity))")
        self.assertLess(expired_cleanup, remembered_check)
        self.assertIn("this.dismiss(channel);\n          current = null;", source)
        self.assertIn("this.hide(region);\n          return \"seen\";", source)
        self.assertIn("parentWindow.sessionStorage.getItem(TOAST_SEEN_STORAGE_KEY)", source)
        self.assertIn("parentWindow.sessionStorage.setItem(", source)
        self.assertIn("writeSeenToastIdentities(this.seen)", source)
        self.assertIn('return "new";', source)

    def test_streamlit_temporary_toast_is_rerun_safe_and_clears_temporary_state(self):
        source = ui_feedback.temporary_toast_html("Saved", event_key="save:1")

        self.assertEqual(3000, ui_feedback.TEMPORARY_TOAST_MS)
        self.assertIn("SportsCaveTransientToast", source)
        self.assertIn("this.current?.identity === nextIdentity", source)
        self.assertIn("this.current.expiresAt > now", source)
        self.assertIn("this.current = null", source)
        self.assertIn("liveRoot.replaceChildren()", source)
        self.assertIn("setTimeout(() => this.dismiss(), durationMs)", source)

    def test_no_native_streamlit_toast_bypasses_the_three_second_runtime(self):
        for path in ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("st.toast(", source, path.name)

    def test_component_toasts_use_exact_three_second_lifecycle(self):
        planner = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        files = (ROOT / "components" / "files_window" / "index.html").read_text(
            encoding="utf-8"
        )

        for source in (planner, files):
            self.assertIn("TEMPORARY_TOAST_MS = 3000", source)
            self.assertIn("toastIdentity", source)
        self.assertIn('toast.textContent = ""', planner)
        self.assertIn('elements.toastText.textContent = ""', files)


class SpinnerOnlyLoadingTests(unittest.TestCase):
    def test_shared_spinner_has_no_visible_copy_and_respects_reduced_motion(self):
        html = ui_loading.spinner_html()

        self.assertIn('class="sc-loading-spinner"', html)
        self.assertIn('aria-label="Loading"', html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertNotIn(">Loading<", html)

    def test_ordinary_streamlit_reads_use_shared_spinner(self):
        orders = (ROOT / "orders_page.py").read_text(encoding="utf-8")
        pages = (ROOT / "os_pages.py").read_text(encoding="utf-8")
        seo = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("ui_loading.render_spinner()", orders)
        self.assertIn("with ui_loading.spinner_only():", pages)
        self.assertIn("ui_loading.render_spinner(controls[2], compact=True)", seo)
        self.assertIn("ui_loading.spinner_html()", app)
        for visible_copy in (
            "Loading orders...",
            "Loading Fulfilment orders...",
            "Loading edition products...",
            "Loading live Shopify orders...",
            "Loading the next 25 keywords",
            "Opening folder...",
        ):
            self.assertNotIn(visible_copy, "\n".join((orders, pages, seo, app)))

    def test_custom_components_have_one_spinner_without_loading_copy_or_skeletons(self):
        sources = [
            (ROOT / "components" / relative).read_text(encoding="utf-8")
            for relative in (
                "sports_cave_top_bar/index.html",
                "home_daily_planner/index.html",
                "daily_planner/index.html",
                "files_window/index.html",
            )
        ]

        for source in sources:
            self.assertIn("sc-loading-spinner", source)
        combined = "\n".join(sources)
        self.assertNotIn("Loading Sports Cave OS", combined)
        self.assertNotIn("Loading notifications", combined)
        self.assertNotIn("Loading today's plan", combined)
        self.assertNotIn("Searching...", combined)
        self.assertNotIn("Opening folder...", combined)
        self.assertNotIn("sc-navigation-skeleton", combined)
        self.assertNotIn('class="skeleton', combined)

    def test_every_streamlit_cache_disables_automatic_spinner(self):
        for path in ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                if line.lstrip().startswith(("@st.cache_data", "@st.cache_resource")):
                    self.assertIn("show_spinner=False", line, path.name)


class OrdersPsdLabelTests(unittest.TestCase):
    def test_orders_uses_psd_label_but_preserves_internal_field_and_destination(self):
        config = inspect.getsource(orders_page._column_config)
        handler = files_window_launcher.table_click_handler_html(
            relative_path=orders_page.ORDERS_FILES_RELATIVE_FOLDER,
            display_label="PSD",
        )

        self.assertEqual("file", orders_page.VISIBLE_COLUMNS[-1])
        self.assertIn('"PSD"', config)
        self.assertIn('display_text="PSD"', config)
        self.assertIn('const displayLabel = "PSD"', handler)
        self.assertIn("02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED", handler)
        self.assertIn("SportsCaveFilesWindow", handler)


if __name__ == "__main__":
    unittest.main()
