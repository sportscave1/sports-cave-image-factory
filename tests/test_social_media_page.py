import unittest

from streamlit.testing.v1 import AppTest


READY_PAGE = r'''
import social_media_page

user = {
    "id": "worker-1",
    "email": "worker@example.test",
    "display_name": "Social VA",
    "role": "worker",
    "country": "Philippines",
    "timezone": "Asia/Manila",
    "is_active": True,
    "page_permissions": ["social_media"],
}

class FakeSocialStore:
    @staticmethod
    def schema_status():
        return {"ready": True}

    @staticmethod
    def authorised_social_staff(viewer, account_store=None):
        return [viewer]

    @staticmethod
    def get_daily_snapshot(viewer, **kwargs):
        return {
            "plan": {},
            "priorities": [],
            "posts": [],
            "plan_date": "2026-07-28",
            "summary": {
                "plan_status": "not_started",
                "priorities_completed": 0,
                "priorities_total": 0,
                "posts_live": 0,
                "platforms_used": [],
                "score": 0.0,
            },
        }

    @staticmethod
    def list_posts(viewer, **kwargs):
        return []

    @staticmethod
    def get_weekly_snapshot(viewer, **kwargs):
        return {
            "report": {},
            "platform_metrics": [],
            "previous_platform_metrics": [],
            "aggregates": {},
            "week_start": "2026-07-27",
            "week_end": "2026-08-02",
        }

    @staticmethod
    def list_history(viewer, **kwargs):
        return {
            "daily_plans": [],
            "posts": [],
            "weekly_reports": [],
            "limit": 15,
            "offset": 0,
        }

social_media_page.render_page(user, store=FakeSocialStore)
'''


class SocialMediaPageTests(unittest.TestCase):
    def test_default_create_view_and_all_shortcuts_render(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.segmented_control[0].value, "Create")
        markup = "\n".join(item.value for item in app.markdown)
        self.assertIn("Sports Cave Social Media", markup)
        self.assertIn("Today's assignment", markup)
        for platform in ("Instagram", "Facebook", "Pinterest", "TikTok", "YouTube"):
            self.assertIn(platform, markup)
        self.assertIn('target="_blank"', markup)
        self.assertIn('rel="noopener noreferrer"', markup)
        self.assertNotIn("\n            <a", markup)
        labels = [button.label for button in app.button]
        self.assertIn("Create this", labels)
        self.assertIn("Build Content Prompt", labels)

    def test_tracking_preserves_each_existing_compact_view(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)
        app.segmented_control[0].set_value("Tracking").run(timeout=15)
        self.assertEqual([item.value for item in app.subheader], ["Today"])

        for view in ("Post Tracker", "Weekly Check-In", "History"):
            with self.subTest(view=view):
                app.segmented_control[1].set_value(view).run(timeout=15)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual([item.value for item in app.subheader], [view])

    def test_direct_render_is_denied_without_social_permission(self):
        app = AppTest.from_string(
            r'''
import social_media_page
user = {
    "id": "worker-1",
    "role": "worker",
    "is_active": True,
    "page_permissions": ["orders"],
}
social_media_page.render_page(user)
'''
        ).run(timeout=15)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual([item.value for item in app.title], ["Access not approved"])
        self.assertNotIn("Sports Cave Social Media", "\n".join(
            item.value for item in app.markdown
        ))

    def test_genuine_storage_outage_is_retryable_without_the_old_setup_warning(self):
        app = AppTest.from_string(
            r'''
import streamlit as st
import social_media_page

user = {
    "id": "worker-1",
    "role": "worker",
    "is_active": True,
    "page_permissions": ["social_media"],
}

class UnavailableStore:
    @staticmethod
    def schema_status(force=False):
        if force:
            st.session_state["forced-social-retry"] = True
        return {
            "ready": bool(st.session_state.get("forced-social-retry")),
            "reason": "storage_unavailable",
        }

    @staticmethod
    def authorised_social_staff(viewer, account_store=None):
        return [viewer]

    @staticmethod
    def get_daily_snapshot(viewer, **kwargs):
        return {
            "plan": {},
            "priorities": [],
            "posts": [],
            "plan_date": "2026-07-28",
            "summary": {
                "plan_status": "not_started",
                "priorities_completed": 0,
                "priorities_total": 0,
                "posts_live": 0,
                "platforms_used": [],
                "score": 0.0,
            },
        }

social_media_page.render_page(user, store=UnavailableStore)
'''
        ).run(timeout=15)

        self.assertEqual(len(app.exception), 0)
        self.assertIn("temporarily unavailable", app.warning[0].value)
        self.assertNotIn(
            "tracking is not ready yet",
            " ".join(item.value for item in app.info),
        )
        app.button[0].click().run(timeout=15)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.segmented_control[0].value, "Create")


if __name__ == "__main__":
    unittest.main()
