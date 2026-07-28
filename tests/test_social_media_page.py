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
    def test_default_today_view_and_all_shortcuts_render(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual([item.value for item in app.subheader], ["Today"])
        markup = "\n".join(item.value for item in app.markdown)
        self.assertIn("Sports Cave Social Media", markup)
        for platform in ("Instagram", "Facebook", "Pinterest", "TikTok", "YouTube"):
            self.assertIn(platform, markup)
        self.assertIn('target="_blank"', markup)
        self.assertIn('rel="noopener noreferrer"', markup)
        self.assertNotIn("\n            <a", markup)
        self.assertEqual(
            [button.label for button in app.button],
            ["Save today's plan", "Complete day"],
        )

    def test_each_compact_view_renders_without_loading_other_history(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)

        for view in ("Post Tracker", "Weekly Check-In", "History"):
            with self.subTest(view=view):
                app.segmented_control[0].set_value(view).run(timeout=15)
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


if __name__ == "__main__":
    unittest.main()
