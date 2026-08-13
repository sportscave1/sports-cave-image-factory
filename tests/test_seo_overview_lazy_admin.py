import inspect
import unittest
from unittest.mock import Mock, patch

import google_seo
import google_seo_import
import google_seo_phase4
import os_accounts
import seo_page


def admin_user():
    return {
        "id": "admin-1",
        "display_name": "Nathan",
        "role": os_accounts.ROLE_ADMIN,
        "is_active": True,
    }


class FakeUI:
    class Node:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def button(self, label, *_args, **_kwargs):
            self.owner.events.append(("button", label))
            return False

        def markdown(self, value, *_args, **_kwargs):
            self.owner.events.append(("markdown", str(value)))

        def metric(self, label, value, *_args, **_kwargs):
            self.owner.events.append(("metric", f"{label}:{value}"))

        def caption(self, value, *_args, **_kwargs):
            self.owner.events.append(("caption", str(value)))

        def selectbox(self, _label, options, *_args, **_kwargs):
            return tuple(options)[0]

        def date_input(self, *_args, **_kwargs):
            return None

    def __init__(self, *, admin_open=False, click_toggle=False):
        self.events = []
        self.query_params = {}
        self.session_state = {seo_page.SEO_ADMIN_OPEN_STATE_KEY: admin_open}
        self.click_toggle = click_toggle
        self.rerun_count = 0

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [self.Node(self) for _ in range(count)]

    def expander(self, label, *_args, **_kwargs):
        self.events.append(("expander", label))
        return self.Node(self)

    def markdown(self, value, *_args, **_kwargs):
        self.events.append(("markdown", str(value)))

    def subheader(self, value, *_args, **_kwargs):
        self.events.append(("subheader", str(value)))

    def caption(self, value, *_args, **_kwargs):
        self.events.append(("caption", str(value)))

    def info(self, value, *_args, **_kwargs):
        self.events.append(("info", str(value)))

    def divider(self):
        self.events.append(("divider", ""))

    def button(self, label, *_args, **_kwargs):
        self.events.append(("button", label))
        clicked = self.click_toggle
        self.click_toggle = False
        return clicked

    def multiselect(self, *_args, **_kwargs):
        return []

    def progress(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def rerun(self, *_args, **_kwargs):
        self.rerun_count += 1


class SEOOverviewLazyAdminTests(unittest.TestCase):
    def test_default_page_orders_reporting_before_current_work_and_admin(self):
        source = inspect.getsource(seo_page._render_overview)
        reporting = source.index("_render_reporting_dashboard(")
        current_work = source.index("_render_current_work(")
        administration = source.index("_render_data_connections_admin(")

        self.assertLess(reporting, current_work)
        self.assertLess(current_work, administration)

        reporting_source = inspect.getsource(seo_page._render_reporting_dashboard)
        expected = (
            '"Main SEO metrics"',
            '"Organic Performance"',
            '"SEO opportunities"',
            "_render_reporting_tables(snapshot)",
        )
        positions = [reporting_source.index(value) for value in expected]
        self.assertEqual(positions, sorted(positions))

    def test_closed_admin_performs_no_connection_progress_or_phase4_admin_reads(self):
        ui = FakeUI(admin_open=False)
        connection_store = Mock()
        import_store = Mock()
        phase4_store = Mock()

        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_render_historical_import_controls"
        ) as progress, patch.object(
            seo_page, "_render_phase4_foundation"
        ) as phase4_admin, patch.object(
            seo_page, "_shopify_health"
        ) as shopify_health, patch.object(
            google_seo, "configuration_status"
        ) as configuration_status:
            seo_page._render_data_connections_admin(
                admin_user(),
                google_store=connection_store,
                import_store=import_store,
                phase4_store=phase4_store,
            )

        connection_store.get_connection.assert_not_called()
        import_store.recent_status.assert_not_called()
        phase4_store.saved_health.assert_not_called()
        phase4_store.get_settings.assert_not_called()
        progress.assert_not_called()
        phase4_admin.assert_not_called()
        shopify_health.assert_not_called()
        configuration_status.assert_not_called()

    def test_progress_fragment_and_admin_content_only_activate_while_open(self):
        ui = FakeUI(admin_open=True)
        connection_store = Mock()
        connection_store.get_connection.return_value = {
            "has_refresh_token": True,
            "gsc_property_name": "Sports Cave",
            "gsc_site_url": "https://example.test/",
            "ga4_property_name": "Sports Cave GA4",
            "ga4_property_id": "properties/1",
        }
        import_store = Mock()
        phase4_store = Mock()
        config_status = {"ready": True}

        with patch.object(seo_page, "st", ui), patch.object(
            google_seo, "configuration_status", return_value=config_status
        ), patch.object(
            google_seo, "connection_status_label", return_value="Connected"
        ), patch.object(
            seo_page, "_shopify_health", return_value={"status": "Connected", "last_sync": "Saved"}
        ), patch.object(
            seo_page, "_render_google_controls"
        ) as google_controls, patch.object(
            seo_page, "_render_historical_import_controls"
        ) as progress, patch.object(
            seo_page, "_render_phase4_foundation"
        ) as phase4_admin:
            seo_page._render_data_connections_admin(
                admin_user(),
                google_store=connection_store,
                import_store=import_store,
                phase4_store=phase4_store,
            )

            ui.session_state[seo_page.SEO_ADMIN_OPEN_STATE_KEY] = False
            seo_page._render_data_connections_admin(
                admin_user(),
                google_store=connection_store,
                import_store=import_store,
                phase4_store=phase4_store,
            )

        google_controls.assert_called_once()
        progress.assert_called_once()
        phase4_admin.assert_called_once()
        self.assertEqual(connection_store.get_connection.call_count, 1)
        rendered = " ".join(value for _kind, value in ui.events)
        self.assertIn("Google Search Console", rendered)
        self.assertIn("Google Analytics 4", rendered)
        self.assertIn("Shopify", rendered)

    def test_disclosure_toggle_changes_only_session_state(self):
        ui = FakeUI(admin_open=False, click_toggle=True)
        with patch.object(seo_page, "st", ui):
            seo_page._render_data_connections_admin(admin_user())

        self.assertTrue(ui.session_state[seo_page.SEO_ADMIN_OPEN_STATE_KEY])
        self.assertEqual(ui.rerun_count, 1)

    def test_default_overview_does_not_construct_admin_or_call_external_clients(self):
        ui = FakeUI(admin_open=False)
        forbidden = Mock(side_effect=AssertionError("external client called"))
        health_reads = Mock(return_value={})

        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_load_reporting_health", health_reads
        ), patch.object(
            seo_page, "_render_current_work"
        ), patch.object(
            google_seo, "list_gsc_properties", forbidden
        ), patch.object(
            google_seo, "list_ga4_properties", forbidden
        ), patch.object(
            google_seo, "refresh_access_token", forbidden
        ), patch.object(
            google_seo_import, "queue_imports", forbidden
        ), patch.object(
            google_seo_phase4, "queue_phase4_pipeline", forbidden
        ):
            seo_page._render_overview({}, admin_user(), None)

        health_reads.assert_called_once_with(None)
        forbidden.assert_not_called()
        rendered = " ".join(value for _kind, value in ui.events)
        self.assertIn("Main SEO metrics", rendered)
        self.assertIn("Organic Performance", rendered)
        self.assertNotIn("Google Search Console", rendered)
        self.assertNotIn("Google data import", rendered)

    def test_all_existing_admin_actions_remain_available_and_admin_guarded(self):
        sources = "\n".join(
            (
                inspect.getsource(seo_page._render_google_controls),
                inspect.getsource(seo_page._render_historical_import_controls),
                inspect.getsource(seo_page._render_phase4_foundation),
            )
        )
        for label in (
            "Connect Google",
            "Refresh properties",
            "Manage connection",
            "Disconnect Google",
            "Import historical data",
            "Sync now",
            "Retry failed import",
            "Save reporting settings",
            "Build joined reporting data",
            "Refresh joined data",
        ):
            self.assertIn(label, sources)
        self.assertGreaterEqual(sources.count("os_accounts.is_admin(user)"), 3)


if __name__ == "__main__":
    unittest.main()
