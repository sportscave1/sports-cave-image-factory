import unittest
from datetime import datetime, timezone

import daily_activity_reporting as reporting


class SocialMediaReportingTests(unittest.TestCase):
    def setUp(self):
        self.period = reporting.build_report_period(
            datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
        )
        self.accounts = [
            {
                "id": "owner-1",
                "email": "owner@example.test",
                "display_name": "Nathan",
                "role": "admin",
                "country": "Australia",
                "timezone": "Australia/Sydney",
                "is_active": True,
            },
            {
                "id": "worker-1",
                "email": "worker@example.test",
                "display_name": "Social VA",
                "role": "worker",
                "country": "Philippines",
                "timezone": "Asia/Manila",
                "is_active": True,
            },
        ]

    def test_social_actions_are_meaningful_and_classified_centrally(self):
        row = {
            "event_type": "social_post_marked_live",
            "activity_action_type": "social_post_marked_live",
            "activity_message": "Launch post marked live",
            "activity_page": "Social Media",
            "activity_metadata": {
                "actor_id": "worker-1",
                "actor_display": "Social VA",
                "source_user_initiated": True,
                "result": "success",
            },
            "created_at": self.period.end_utc,
        }
        classified = reporting.classify_activity(row)
        self.assertEqual(classified["category"], "Social media work")
        self.assertEqual(classified["status"], "success")

    def test_staff_report_contains_compact_social_section_without_mixing_daily_execution(self):
        social = {
            "worker-1": {
                "plan_status": "completed",
                "mips_completed": 2,
                "mips_outstanding": 1,
                "posts_logged": 3,
                "posts_live": 2,
                "platforms": ["Instagram", "TikTok"],
                "posts_live_by_platform": {"Instagram": 1, "TikTok": 1},
                "score": 8.5,
                "improvement_test": "Test a shorter opening.",
                "main_learning": "Collector detail shots held attention.",
                "blockers": "",
                "weekly_status": "submitted",
                "weekly_headline": "8 posts, 12000 total audience",
                "weekly_platforms": [],
            }
        }
        snapshot = reporting.build_report_snapshot(
            period=self.period,
            accounts=self.accounts,
            activity_rows=[],
            daily_execution_sheet=None,
            social_summaries=social,
            owner_email="owner@example.test",
            recipient="reports@example.test",
        )
        owner, worker = snapshot["staff"]

        self.assertIsNone(owner["social_media"])
        self.assertEqual(worker["social_media"]["score"], 8.5)
        self.assertIn("<strong>Social Media</strong>", snapshot["html"])
        self.assertIn("Execution score: 8.5/10", snapshot["html"])
        self.assertIn("Social Media:", snapshot["text"])
        self.assertIn("Posts: 3 logged / 2 live", snapshot["text"])
        self.assertIn("Latest weekly check-in", snapshot["text"])
        self.assertIsNotNone(owner["daily_execution"])
        self.assertIsNone(worker["daily_execution"])

    def test_reporting_team_summary_includes_platform_counts_and_attention(self):
        social = {
            "owner-1": {
                "plan_status": "completed",
                "mips_completed": 1,
                "mips_outstanding": 0,
                "posts_logged": 1,
                "posts_live": 1,
                "platforms": ["Facebook"],
                "posts_live_by_platform": {"Facebook": 1},
                "score": 10,
                "blockers": "",
            },
            "worker-1": {
                "plan_status": "draft",
                "mips_completed": 0,
                "mips_outstanding": 2,
                "posts_logged": 1,
                "posts_live": 1,
                "platforms": ["Instagram"],
                "posts_live_by_platform": {"Instagram": 1},
                "score": 4,
                "blockers": "Waiting for artwork approval",
            },
        }
        snapshot = reporting.build_report_snapshot(
            period=self.period,
            accounts=self.accounts,
            activity_rows=[],
            social_summaries=social,
            owner_email="owner@example.test",
            recipient="reports@example.test",
        )
        overview = snapshot["social_media"]

        self.assertEqual(overview["completed_days"], 1)
        self.assertEqual(overview["posts_live"], 2)
        self.assertEqual(
            overview["posts_live_by_platform"],
            {"Facebook": 1, "Instagram": 1},
        )
        self.assertEqual(overview["average_score"], 7.0)
        self.assertTrue(
            any("Social Media blocker" in item for item in snapshot["attention"])
        )
        self.assertNotIn("Traceback", snapshot["html"])


if __name__ == "__main__":
    unittest.main()
