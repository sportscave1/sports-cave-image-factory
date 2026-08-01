import inspect
import unittest

from streamlit.testing.v1 import AppTest

import social_media_creator
import social_media_workspace


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

    def test_create_form_is_compact_and_uses_editable_hook_and_cta_controls(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(item.value for item in app.markdown)
        self.assertNotIn("More details", [item.label for item in app.expander])
        self.assertEqual([item.label for item in app.text_area], [])
        labels = [item.label for item in app.text_input]
        for removed_label in (
            "Audience",
            "Proof asset available",
            "Accurate live edition count",
            "Price",
            "Shipping or delivery claim",
            "Restrictions",
            "Source-footage rights status",
            "Additional VA notes",
        ):
            self.assertNotIn(removed_label, labels)
        self.assertIn("Offer (optional)", labels)
        self.assertIn(
            "Offer end date (optional)",
            [item.label for item in app.date_input],
        )

        selectboxes = {item.label: item for item in app.selectbox}
        self.assertEqual(
            set(selectboxes["Hook or content angle"].options),
            set(social_media_creator.HOOK_OPTIONS),
        )
        self.assertEqual(
            set(selectboxes["One CTA"].options),
            set(social_media_creator.CTA_OPTIONS),
        )
        self.assertIn("ROOM, WALL & CAMERA", markup)
        self.assertIn("Product featured", markup)
        for label, options in (
            ("Room type", social_media_creator.ROOM_TYPE_OPTIONS),
            ("Wall colour", social_media_creator.WALL_COLOUR_OPTIONS),
            (
                "Wall material/finish",
                social_media_creator.WALL_MATERIAL_FINISH_OPTIONS,
            ),
            ("Camera angle", social_media_creator.CAMERA_ANGLE_OPTIONS),
            (
                "Shot distance / product prominence",
                social_media_creator.SHOT_DISTANCE_PROMINENCE_OPTIONS,
            ),
            ("Lighting style", social_media_creator.LIGHTING_STYLE_OPTIONS),
            (
                "Variation behaviour",
                social_media_creator.VARIATION_BEHAVIOUR_OPTIONS,
            ),
        ):
            with self.subTest(label=label):
                self.assertEqual(set(selectboxes[label].options), set(options))
        for hidden_custom_label in (
            "Custom room type",
            "Custom wall colour",
            "Custom wall material/finish",
            "Custom camera angle",
            "Custom lighting style",
        ):
            self.assertNotIn(hidden_custom_label, labels)
        helper_source = inspect.getsource(
            social_media_workspace._editable_selectbox
        )
        self.assertIn("accept_new_options=True", helper_source)
        self.assertIn('filter_mode="fuzzy"', helper_source)

    def test_scene_custom_inputs_only_appear_after_custom_selection(self):
        app = AppTest.from_string(READY_PAGE).run(timeout=15)
        selectboxes = {item.label: item for item in app.selectbox}

        selectboxes["Room type"].set_value("Custom").run(timeout=15)
        labels = [item.label for item in app.text_input]

        self.assertIn("Custom room type", labels)
        self.assertNotIn("Custom wall colour", labels)

    def test_custom_hook_and_cta_restore_in_editable_selectboxes(self):
        source = READY_PAGE.replace(
            "import social_media_page",
            (
                "import streamlit as st\n"
                'st.session_state["social-create-hook"] = "Custom restored angle"\n'
                'st.session_state["social-create-cta"] = "Custom restored CTA."\n'
                "import social_media_page"
            ),
            1,
        )
        app = AppTest.from_string(source).run(timeout=15)
        selectboxes = {item.label: item for item in app.selectbox}

        self.assertEqual(
            selectboxes["Hook or content angle"].value,
            "Custom restored angle",
        )
        self.assertIn(
            "Custom restored angle",
            selectboxes["Hook or content angle"].options,
        )
        self.assertEqual(selectboxes["One CTA"].value, "Custom restored CTA.")
        self.assertIn(
            "Custom restored CTA.",
            selectboxes["One CTA"].options,
        )

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
