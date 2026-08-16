import json
from pathlib import Path
import unittest
from unittest import mock

import os_accounts
import top_bar
import top_bar_api
import top_bar_security


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "components" / "sports_cave_top_bar" / "index.html"


def admin_claims():
    return {
        "sub": "admin-1",
        "display_name": "Sports Cave Admin",
        "username": "admin",
        "role": "admin",
        "allowed_routes": [page["route"] for page in os_accounts.PAGE_REGISTRY],
        "can_view_activity": True,
        "can_view_all_activity": True,
    }


class _ComponentsRecorder:
    def __init__(self):
        self.calls = []

    def html(self, body, **kwargs):
        self.calls.append((body, kwargs))


class TopBarSecurityTests(unittest.TestCase):
    def test_signed_snapshot_contains_permissions_but_no_email_or_secrets(self):
        token = top_bar_security.create_top_bar_token(
            {
                "id": "user-1",
                "display_name": "Worker",
                "username": "worker",
                "email": "private@example.test",
                "password_hash": "secret-hash",
                "role": "worker",
            },
            allowed_routes=("Dashboard", "Orders"),
            now=100,
        )

        valid, reason, claims = top_bar_security.validate_top_bar_token(
            token,
            now=101,
        )

        self.assertTrue(valid)
        self.assertEqual("ok", reason)
        self.assertEqual(["Dashboard", "Orders"], claims["allowed_routes"])
        serialised = json.dumps(claims).casefold()
        self.assertNotIn("private@example.test", serialised)
        self.assertNotIn("secret-hash", serialised)
        self.assertNotIn("password", serialised)

    def test_expired_or_modified_snapshot_is_rejected(self):
        token = top_bar_security.create_top_bar_token(
            {"id": "user-1", "role": "worker"},
            now=100,
            seconds=60,
        )
        self.assertFalse(
            top_bar_security.validate_top_bar_token(token, now=161)[0]
        )
        self.assertFalse(
            top_bar_security.validate_top_bar_token(f"{token}x", now=101)[0]
        )


class TopBarSearchTests(unittest.TestCase):
    def test_search_finds_every_permission_registered_page(self):
        claims = admin_claims()
        results = top_bar_api.build_search_index(claims, {})
        page_titles = {
            result["title"]
            for result in results
            if result["group"] == "Pages"
        }

        expected = {page["label"] for page in os_accounts.PAGE_REGISTRY}
        self.assertTrue(expected.issubset(page_titles))
        self.assertIn("Activity Log", page_titles)

    def test_search_projects_safe_metadata_and_never_exposes_secrets(self):
        claims = admin_claims()
        sources = {
            "tasks": [
                {
                    "title": "Create Ayrton Senna design",
                    "section": "New designs to complete",
                    "status": "open",
                    "metadata": {
                        "sport": "Motorsport",
                        "team_or_athlete": "Ayrton Senna",
                        "notes": "private task body",
                        "access_token": "task-token-value",
                    },
                }
            ],
            "products": [
                {
                    "product_name": "Senna Monaco Collector Print",
                    "handle": "senna-monaco",
                    "sport_category": "Motorsport",
                    "status": "Live",
                    "notes": "private product notes",
                    "api_key": "product-secret",
                }
            ],
            "seo": {
                "citations": [
                    {
                        "platform": "Example Directory",
                        "profile_url": "https://example.test/sportscave",
                        "status": "Live",
                        "email_used": "private@example.test",
                        "login_reference": "credential-1",
                    }
                ],
                "blog_records": [
                    {
                        "article_title": "Great motorsport rivalries",
                        "primary_keyword": "motorsport wall art",
                        "body": "full private article body",
                        "oauth_token": "blog-token-value",
                    }
                ],
                "outreach_records": [
                    {
                        "site_creator": "Racing Archive",
                        "website": "https://racing.example.test",
                        "contact_email": "contact@example.test",
                    }
                ],
            },
            "accounts": [
                {
                    "display_name": "Operations Worker",
                    "username": "ops-worker",
                    "role": "worker",
                    "password_hash": "password-hash-value",
                    "email": "worker@example.test",
                }
            ],
        }

        results = top_bar_api.build_search_index(claims, sources)
        serialised = json.dumps(results, ensure_ascii=False).casefold()

        self.assertIn("ayrton senna", serialised)
        self.assertIn("senna monaco collector print", serialised)
        self.assertIn("example directory", serialised)
        self.assertIn("great motorsport rivalries", serialised)
        self.assertIn("operations worker", serialised)
        for forbidden in (
            "private@example.test",
            "contact@example.test",
            "task-token-value",
            "product-secret",
            "full private article body",
            "password-hash-value",
            "credential-1",
        ):
            self.assertNotIn(forbidden, serialised)

    def test_worker_index_is_permission_scoped(self):
        claims = {
            **admin_claims(),
            "role": "worker",
            "allowed_routes": ["Dashboard", "Orders", "Accounts & Access"],
            "can_view_all_activity": False,
        }
        results = top_bar_api.build_search_index(
            claims,
            {"products": [{"product_name": "Hidden product"}]},
        )
        serialised = json.dumps(results)

        self.assertIn("Home", serialised)
        self.assertIn("Orders", serialised)
        self.assertNotIn("Hidden product", serialised)
        self.assertNotIn("Design Studio", serialised)

    def test_top_bar_data_loading_has_no_connector_or_migration_calls(self):
        source = (ROOT / "top_bar_api.py").read_text(encoding="utf-8")

        for forbidden in (
            "dropbox_integration",
            "shopify_sync",
            "google_search_console",
            "google_analytics",
            "ensure_schema()",
            "init_db()",
            "CREATE TABLE",
            "ALTER TABLE",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("SELECT to_jsonb(row_data) AS payload", source)
        self.assertNotIn("SELECT * FROM products", source)
        self.assertNotIn("SELECT * FROM shopify_orders", source)


class TopBarNotificationTests(unittest.TestCase):
    def test_notifications_use_real_rows_put_warnings_first_and_show_no_badge(self):
        claims = admin_claims()
        activity = [
            {
                "event_type": "task_completed",
                "created_at": "2026-08-12T10:00:00Z",
                "source": "Dashboard",
                "new_value": {
                    "message": "Task completed: Upload print",
                    "page": "Dashboard",
                    "metadata": {"actor_id": "admin-1"},
                },
            },
            {
                "event_type": "citation_import_failed",
                "created_at": "2026-08-12T09:00:00Z",
                "source": "Citations",
                "new_value": {
                    "message": "Citation import failed",
                    "page": "Citations",
                    "metadata": {"actor_id": "admin-1"},
                },
            },
        ]

        notifications = top_bar_api.build_notifications(
            claims,
            activity_rows=activity,
            alerts=[{"label": "US Open tennis soon"}],
        )

        self.assertEqual("Citation import failed", notifications[0]["title"])
        self.assertNotIn("US Open tennis soon", json.dumps(notifications))
        component = COMPONENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("unread-badge", component)
        self.assertIn("No new notifications", component)

    def test_worker_does_not_receive_another_users_activity(self):
        claims = {
            **admin_claims(),
            "can_view_all_activity": False,
        }
        rows = [
            {
                "event_type": "warning",
                "new_value": {
                    "message": "Another user warning",
                    "metadata": {"actor_id": "someone-else"},
                },
            }
        ]
        self.assertEqual(
            [],
            top_bar_api.build_notifications(claims, activity_rows=rows),
        )


class TopBarComponentTests(unittest.TestCase):
    def test_component_renders_branding_search_and_icons_in_order(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertIn("Search Sports Cave OS", source)
        self.assertIn("Sports Cave OS monogram", source)
        markup_start = source.index("const markup = `")
        markup = source[markup_start : source.index("`;", markup_start)]
        refresh = markup.index('id="sc-os-refresh"')
        search = markup.index('id="sc-os-global-search"')
        planner = markup.index('id="sc-os-daily-planner"')
        notifications = markup.index('id="sc-os-notifications"')
        profile = markup.index('id="sc-os-profile"')
        settings = markup.index('id="sc-os-settings"')
        self.assertLess(refresh, search)
        self.assertLess(planner, notifications)
        self.assertLess(notifications, profile)
        self.assertLess(profile, settings)
        self.assertIn('aria-label="Open Daily Planner"', markup)
        self.assertIn('title="Open Daily Planner"', markup)
        self.assertNotIn("Shopify", source)

    def test_refresh_button_performs_a_full_page_reload(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertEqual(1, source.count('id="sc-os-refresh"'))
        self.assertIn('aria-label="Refresh Sports Cave OS"', source)
        self.assertIn('refreshButton.addEventListener("click"', source)
        self.assertIn("parentWindow.location.reload();", source)

    def test_profile_settings_and_keyboard_contracts_are_functional(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertIn("accountsRouteKey", source)
        self.assertIn("navigateDocument", source)
        self.assertIn('link.target = "_self"', source)
        self.assertIn('event.key.toLocaleLowerCase() === "k"', source)
        self.assertIn("event.ctrlKey || event.metaKey", source)
        self.assertIn('event.key === "Escape"', source)
        self.assertIn('event.key === "ArrowDown"', source)
        self.assertIn('event.key === "ArrowUp"', source)
        self.assertIn("parentWindow.print()", source)
        self.assertIn("getDisplayMedia", source)
        self.assertIn("MediaRecorder", source)
        for theme in ("System", "Light", "Dark"):
            self.assertIn(f'"{theme}"', source)

    def test_notifications_and_search_load_lazily_once_in_browser(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        focus_index = source.index('searchInput.addEventListener("focus"')
        search_load_index = source.index("const loadSearchIndex")
        notification_click_index = source.index(
            'notificationsButton.addEventListener("click"'
        )
        notification_load_index = source.index(
            "const loadNotifications",
        )
        self.assertLess(search_load_index, focus_index)
        self.assertLess(notification_load_index, notification_click_index)
        self.assertIn("if (state.searchIndex)", source)
        self.assertIn("if (!state.notifications)", source)
        self.assertNotIn("st.rerun", source)

    def test_component_rebinds_cleanly_after_streamlit_reruns(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertIn("new parentWindow.AbortController()", source)
        self.assertIn("SportsCaveTopBar?.destroy?.({preserveDom: true})", source)
        self.assertIn("listenerController.abort()", source)
        self.assertNotIn("parentWindow.location.assign", source)

    def test_native_header_is_hidden_only_by_installed_component(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertIn('header[data-testid="stHeader"]', source)
        self.assertIn('[data-testid="stToolbar"]', source)
        self.assertIn("display: none !important", source)

    def test_sidebar_is_compact_and_has_no_brand_or_section_headings(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("def _sidebar_section_label", app_source)
        self.assertNotIn("sc-sidebar-brand", app_source)
        self.assertNotIn("sc-sidebar-section-label", app_source)
        self.assertIn("min-height: 2.25rem", app_source)
        self.assertIn("min-height: 2rem", app_source)
        self.assertIn("--sc-topbar-height: 64px", app_source)
        self.assertIn("height: calc(100dvh - var(--sc-topbar-height))", app_source)
        self.assertIn('[data-testid="stSidebarHeader"]', app_source)
        self.assertIn("resetInitialSidebarScroll", COMPONENT_PATH.read_text(encoding="utf-8"))

    def test_component_bridge_has_zero_layout_height(self):
        user = {
            "id": "admin-1",
            "display_name": "Admin",
            "username": "admin",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }
        components = _ComponentsRecorder()

        with mock.patch.object(
            top_bar_security,
            "create_top_bar_token",
            return_value="signed-token",
        ):
            top_bar.render_top_bar(
                components,
                user,
                logo_src="data:image/webp;base64,AAAA",
                current_route="Dashboard",
            )

        self.assertEqual(1, len(components.calls))
        body, kwargs = components.calls[0]
        self.assertEqual({"height": 0, "width": 0}, kwargs)
        self.assertIn('"authToken": "signed-token"', body)
        self.assertEqual(1, body.count('id="sc-os-refresh"'))
        self.assertEqual(1, body.count('id="sc-os-daily-planner"'))
        self.assertEqual(1, body.count('id="sc-os-notifications"'))
        self.assertEqual(1, body.count('id="sc-os-profile"'))
        self.assertEqual(1, body.count('id="sc-os-settings"'))


if __name__ == "__main__":
    unittest.main()
