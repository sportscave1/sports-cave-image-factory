import inspect
from pathlib import Path
import unittest

import os_accounts
import run_migrations
import social_media
import social_media_creator
import social_media_store


ROOT = Path(__file__).resolve().parents[1]


def worker(*, permissions=(), active=True, user_id="worker-1"):
    return {
        "id": user_id,
        "email": f"{user_id}@example.test",
        "display_name": user_id,
        "role": "worker",
        "is_active": active,
        "page_permissions": list(permissions),
    }


class SocialNavigationTests(unittest.TestCase):
    def test_registry_has_one_parent_and_one_non_top_level_child(self):
        parent = os_accounts.PAGE_BY_KEY[social_media.SOCIAL_MEDIA_PAGE_KEY]
        child = os_accounts.PAGE_BY_KEY[social_media.AI_REELS_PAGE_KEY]

        self.assertEqual(parent["route"], "Social Media")
        self.assertTrue(parent["worker_assignable"])
        self.assertEqual(child["route"], "AI Reels")
        self.assertEqual(child["parent_key"], parent["key"])
        self.assertTrue(child["navigation_child"])
        self.assertFalse(child["worker_assignable"])
        self.assertNotIn("Social Media Reels Studio", os_accounts.allowed_navigation_routes(
            {"id": "admin", "role": "admin", "is_active": True, "page_permissions": []}
        ))

    def test_legacy_reels_permission_grants_parent_and_child_only(self):
        approved = worker(permissions=[social_media.LEGACY_REELS_PAGE_KEY])
        unapproved = worker(permissions=["orders"])

        self.assertTrue(os_accounts.can_access_page(approved, "Social Media"))
        self.assertTrue(os_accounts.can_access_page(approved, "AI Reels"))
        self.assertFalse(os_accounts.can_access_page(unapproved, "Social Media"))
        self.assertFalse(os_accounts.can_access_page(unapproved, "AI Reels"))

    def test_inactive_and_direct_route_access_are_denied(self):
        inactive = worker(
            permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
            active=False,
        )
        self.assertFalse(os_accounts.can_access_page(inactive, "Social Media"))
        self.assertFalse(os_accounts.can_access_page(inactive, "AI Reels"))

    def test_old_route_and_bookmark_have_documented_compatibility(self):
        self.assertEqual(
            os_accounts.normalise_route("Social Media Reels Studio"),
            "AI Reels",
        )
        self.assertEqual(
            os_accounts.normalise_page_key("social_media_reels_studio"),
            "social_media",
        )
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            "if value == social_media.LEGACY_REELS_PAGE_KEY:",
            app_source,
        )
        self.assertIn("return social_media.AI_REELS_ROUTE", app_source)

    def test_sidebar_uses_nested_parent_and_keeps_group_expanded_when_active(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("social_group_active = current_page in", source)
        self.assertIn('st.session_state["social-media-nav-expanded"] = True', source)
        self.assertIn('key="sidebar-nav::Social Media::toggle"', source)
        self.assertIn('key="sidebar-nav::AI Reels"', source)
        self.assertNotIn('sidebar-nav::Social Media Reels Studio', source)

    def test_existing_reels_renderer_and_prompt_path_are_reused(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        reels_source = (ROOT / "social_media_reels_studio_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("get_social_media_reels_studio_page().render_page(", app_source)
        self.assertIn("can_edit_prompts=prompt_editing_allowed()", app_source)
        self.assertIn("<h1>AI Reels</h1>", reels_source)
        self.assertIn("BACKGROUND_FINDER_PROMPT", reels_source)
        self.assertIn("VIDEO_PROMPT_KEYS", reels_source)


class SocialStorageContractTests(unittest.TestCase):
    def test_migration_is_safe_and_has_required_unique_constraints(self):
        sql = (ROOT / "migrations" / social_media_store.SOCIAL_MEDIA_MIGRATION).read_text(
            encoding="utf-8"
        )
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        for table in (
            "social_daily_plans",
            "social_daily_priorities",
            "social_posts",
            "social_post_platforms",
            "social_weekly_reports",
            "social_weekly_platform_metrics",
            "social_action_requests",
            "social_weekly_priorities",
            "social_content_jobs",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
            self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("UNIQUE (user_id, plan_date)", sql)
        self.assertIn("UNIQUE (user_id, week_start)", sql)
        self.assertIn("UNIQUE (post_id, platform)", sql)
        self.assertIn("UNIQUE (report_id, platform)", sql)
        self.assertIn("request_key TEXT NOT NULL UNIQUE", sql)

    def test_history_is_bounded_and_uses_one_connection_path(self):
        history_source = inspect.getsource(social_media_store.list_history)
        self.assertIn("_safe_limit(limit)", history_source)
        self.assertIn("_list_posts_with_cursor(", history_source)
        self.assertNotIn("list_posts(", history_source)
        self.assertEqual(history_source.count("backend.connect()"), 1)

    def test_store_uses_authenticated_target_identity(self):
        viewer = worker(
            permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
            user_id="worker-1",
        )
        self.assertEqual(
            social_media_store.resolve_target_account(viewer, "worker-1")["id"],
            "worker-1",
        )
        with self.assertRaises(PermissionError):
            social_media_store.resolve_target_account(viewer, "worker-2")

    def test_workers_cannot_set_weekly_priorities(self):
        viewer = worker(
            permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
            user_id="worker-1",
        )

        with self.assertRaisesRegex(PermissionError, "administrator"):
            social_media_store.save_weekly_priority(
                viewer,
                payload={},
                request_key_value="weekly-priority-test",
            )

    def test_workers_cannot_approve_content_jobs(self):
        viewer = worker(
            permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
            user_id="worker-1",
        )
        payload = {
            "scheduled_date": "2026-07-31",
            "content_focus": "Community/fan conversation",
            "market": "Global",
            "sport": "Other",
            "format": "Static feed post",
            "series": "CAVE DEBATE",
            "platforms": ["Instagram"],
            "objective": "Engagement",
            "funnel_stage": "Warm",
            "hook": "Which sporting rivalry still divides the fanbase?",
            "cta": "Join the conversation.",
            "status": "Approved",
        }

        with self.assertRaisesRegex(PermissionError, "administrator"):
            social_media_store.save_content_job(
                viewer,
                payload=payload,
                request_key_value="content-approval-test",
            )

        self.assertIn("Approved", social_media_creator.WORK_STATUS_OPTIONS)

    def test_todays_assignment_only_loads_approved_or_active_work(self):
        source = inspect.getsource(social_media_store.get_current_assignment)

        self.assertIn("'Approved', 'In production', 'Scheduled', 'Published'", source)
        self.assertNotIn("'Submitted'", source)
        self.assertNotIn("'Draft'", source)

    def test_admin_can_only_select_active_authorised_social_staff(self):
        admin = {
            "id": "admin-1",
            "email": "admin@example.test",
            "display_name": "Admin",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }

        class Store:
            @staticmethod
            def list_users():
                return [
                    admin,
                    worker(
                        permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
                        user_id="worker-1",
                    ),
                    worker(permissions=["orders"], user_id="worker-2"),
                    worker(
                        permissions=[social_media.SOCIAL_MEDIA_PAGE_KEY],
                        active=False,
                        user_id="worker-3",
                    ),
                ]

        staff = social_media_store.authorised_social_staff(
            admin,
            account_store=Store(),
        )
        self.assertEqual([row["id"] for row in staff], ["admin-1", "worker-1"])
        with self.assertRaises(PermissionError):
            social_media_store.resolve_target_account(
                admin,
                "worker-2",
                account_store=Store(),
            )

    def test_action_request_keys_are_deterministic_and_payload_specific(self):
        first = social_media_store.request_key(
            "post-create",
            "worker-1",
            "2026-07-28",
            {"name": "Launch", "platforms": ["Instagram"]},
        )
        duplicate = social_media_store.request_key(
            "post-create",
            "worker-1",
            "2026-07-28",
            {"platforms": ["Instagram"], "name": "Launch"},
        )
        changed = social_media_store.request_key(
            "post-create",
            "worker-1",
            "2026-07-28",
            {"name": "Launch 2", "platforms": ["Instagram"]},
        )
        self.assertEqual(first, duplicate)
        self.assertNotEqual(first, changed)

    def test_team_overview_counts_each_live_platform_directly(self):
        overview = social_media_store.reporting_team_overview(
            {
                "one": {
                    "plan_status": "completed",
                    "posts_live": 2,
                    "posts_live_by_platform": {"Instagram": 1, "Facebook": 1},
                    "score": 8,
                    "mips_outstanding": 0,
                    "blockers": "",
                },
                "two": {
                    "plan_status": "draft",
                    "posts_live": 1,
                    "posts_live_by_platform": {"Instagram": 1},
                    "score": 6,
                    "mips_outstanding": 2,
                    "blockers": "Need help",
                },
            }
        )
        self.assertEqual(overview["posts_live"], 3)
        self.assertEqual(
            overview["posts_live_by_platform"],
            {"Instagram": 2, "Facebook": 1},
        )
        self.assertEqual(overview["average_score"], 7.0)
        self.assertEqual(overview["outstanding_mips"], 2)
        self.assertEqual(overview["blockers"], 1)


class SocialHubUiContractTests(unittest.TestCase):
    def test_hub_is_compact_safe_and_has_all_workflow_views(self):
        source = (ROOT / "social_media_page.py").read_text(encoding="utf-8")
        self.assertIn("Sports Cave Social Media", source)
        self.assertIn('"Create", "Plan", "Playbook", "Tracking"', source)
        self.assertIn("Today", source)
        self.assertIn("Post Tracker", source)
        self.assertIn("Weekly Check-In", source)
        self.assertIn("History", source)
        self.assertIn('target="_blank"', source)
        self.assertIn('rel="noopener noreferrer"', source)
        self.assertNotIn("<iframe", source.casefold())
        self.assertNotIn("oauth", source.casefold())
        self.assertNotIn("password", source.casefold())

    def test_only_selected_view_loads_its_data(self):
        module = __import__("social_media_page")
        source = inspect.getsource(module.render_page)
        tracking_source = inspect.getsource(module._render_tracking)
        self.assertIn('default="Create"', source)
        self.assertIn('elif view == "Tracking"', source)
        self.assertIn('if view == "Post Tracker"', tracking_source)
        self.assertIn('elif view == "Weekly Check-In"', tracking_source)
        self.assertIn('elif view == "History"', tracking_source)
        self.assertIn("_render_today(", tracking_source)

    def test_activity_logging_is_manual_and_idempotent(self):
        page_source = (ROOT / "social_media_page.py").read_text(encoding="utf-8")
        store_source = (ROOT / "social_media_store.py").read_text(encoding="utf-8")
        self.assertIn("event_key=activity[\"event_key\"]", page_source)
        self.assertIn("ON CONFLICT (request_key) DO NOTHING", store_source)
        self.assertNotIn("record_activity_log(", page_source.split("def _record_activity", 1)[0])


if __name__ == "__main__":
    unittest.main()
