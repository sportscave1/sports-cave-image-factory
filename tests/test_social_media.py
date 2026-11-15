import math
import unittest
from datetime import date, datetime, timezone

import social_media


class SocialMediaProfileTests(unittest.TestCase):
    def test_profile_urls_are_exact_and_centralised(self):
        self.assertEqual(
            social_media.SOCIAL_PROFILE_URLS,
            {
                "Instagram": "https://www.instagram.com/sportscaveshop/",
                "Facebook": "https://www.facebook.com/profile.php?id=100090408036260",
                "Pinterest": "https://au.pinterest.com/SportsCaveShop/",
                "TikTok": "https://www.tiktok.com/@sportscaveshop",
                "YouTube": "https://www.youtube.com/channel/UCDZjmaJrIXMvh7z6r123lig",
            },
        )

    def test_public_post_urls_require_https_and_the_selected_platform(self):
        self.assertEqual(
            social_media.validate_public_url(
                "https://www.instagram.com/p/example/#details",
                platform="Instagram",
            ),
            "https://www.instagram.com/p/example/",
        )
        for url in (
            "http://instagram.com/p/example/",
            "https://user:password@instagram.com/p/example/",
            "https://example.com/p/example/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(social_media.SocialValidationError):
                    social_media.validate_public_url(url, platform="Instagram")


class SocialMediaDateTests(unittest.TestCase):
    def test_sydney_date_uses_timezone_aware_timestamp(self):
        self.assertEqual(
            social_media.sydney_today(
                datetime(2026, 7, 27, 14, 30, tzinfo=timezone.utc)
            ),
            date(2026, 7, 28),
        )
        with self.assertRaises(social_media.SocialValidationError):
            social_media.sydney_today(datetime(2026, 7, 28, 8, 0))

    def test_sydney_week_is_monday_through_sunday(self):
        self.assertEqual(
            social_media.sydney_week_bounds(date(2026, 7, 28)),
            (date(2026, 7, 27), date(2026, 8, 2)),
        )


class SocialDailyPlanTests(unittest.TestCase):
    def test_top_priority_and_content_plan_are_required(self):
        with self.assertRaisesRegex(
            social_media.SocialValidationError,
            "Top priority is required",
        ):
            social_media.validate_daily_plan(
                {"content_plan": "Create a collector reel", "priorities": []}
            )
        with self.assertRaisesRegex(
            social_media.SocialValidationError,
            "Content plan is required",
        ):
            social_media.validate_daily_plan(
                {"content_plan": "", "priorities": [{"task": "Post reel"}]}
            )

    def test_only_three_priorities_are_accepted(self):
        plan = social_media.normalise_daily_plan(
            {
                "content_plan": "Today",
                "priorities": [
                    {"task": "One"},
                    {"task": "Two"},
                    {"task": "Three"},
                    {"task": "Four"},
                ],
            }
        )
        self.assertEqual([row["task"] for row in plan["priorities"]], ["One", "Two", "Three"])

    def test_completion_requires_the_short_review(self):
        payload = {
            "content_plan": "Post the new release",
            "priorities": [{"task": "Publish launch reel", "completed": True}],
        }
        with self.assertRaisesRegex(
            social_media.SocialValidationError,
            "four end-of-day",
        ):
            social_media.validate_daily_plan(payload, completing=True)

    def test_top_priority_is_weighted_twice_and_review_adds_two_points(self):
        priorities = [
            {"task": "Top", "completed": True},
            {"task": "Second", "completed": False},
            {"task": "Third", "completed": False},
        ]
        review = {
            "what_worked": "A",
            "what_learned": "B",
            "improve_next": "C",
            "blockers": "None",
        }
        self.assertEqual(social_media.calculate_daily_score(priorities, {}), 4.0)
        self.assertEqual(social_media.calculate_daily_score(priorities, review), 6.0)

    def test_fewer_priorities_are_scaled_fairly(self):
        self.assertEqual(
            social_media.calculate_daily_score(
                [{"task": "Only task", "completed": True}],
                {},
            ),
            8.0,
        )
        self.assertEqual(
            social_media.calculate_daily_score(
                [
                    {"task": "Top", "completed": True},
                    {"task": "Second", "completed": False},
                ],
                {},
            ),
            5.3,
        )

    def test_platforms_and_post_volume_do_not_change_the_score(self):
        base = {
            "priorities": [{"task": "Top", "completed": True}],
            "content_plan": "Create",
        }
        quiet = social_media.normalise_daily_plan(base)
        busy = social_media.normalise_daily_plan(
            {
                **base,
                "planned_platforms": social_media.PLATFORMS,
                "planned_post_count": 100,
            }
        )
        self.assertEqual(quiet["score"], busy["score"])
        self.assertGreaterEqual(busy["score"], 0)
        self.assertLessEqual(busy["score"], 10)


class SocialPostTests(unittest.TestCase):
    def test_one_content_item_can_hold_multiple_platform_rows(self):
        post = social_media.normalise_post(
            {
                "content_name": "New release",
                "content_format": "Carousel",
                "market": "Australia",
                "created_date": "2026-07-28",
                "platforms": {
                    "Instagram": {
                        "status": "Live",
                        "public_url": "https://instagram.com/p/example/",
                    },
                    "Facebook": {"status": "Scheduled"},
                },
            }
        )
        self.assertEqual(post["created_date"], date(2026, 7, 28))
        self.assertEqual(
            {row["platform"] for row in post["platforms"]},
            {"Instagram", "Facebook"},
        )

    def test_optional_metrics_remain_missing_instead_of_zero(self):
        post = social_media.normalise_post(
            {
                "content_name": "A reel",
                "platforms": {"TikTok": {"status": "Planned"}},
            }
        )
        platform = post["platforms"][0]
        self.assertIsNone(platform["reach_views"])
        self.assertIsNone(platform["engagements"])
        self.assertIsNone(platform["link_clicks"])
        self.assertIsNone(platform["saves_shares"])

    def test_invalid_metric_and_empty_platform_fail_safely(self):
        with self.assertRaises(social_media.SocialValidationError):
            social_media.normalise_post(
                {"content_name": "A post", "platforms": {}}
            )
        with self.assertRaises(social_media.SocialValidationError):
            social_media.normalise_post(
                {
                    "content_name": "A post",
                    "platforms": {"YouTube": {"reach_views": -1}},
                }
            )


class SocialWeeklyTests(unittest.TestCase):
    def test_blank_weekly_metrics_stay_blank(self):
        report = social_media.normalise_weekly_report(
            {
                "week_start": "2026-07-28",
                "platform_metrics": {
                    "Instagram": {
                        "audience_total": math.nan,
                        "reach_views": "",
                    }
                },
            }
        )
        self.assertEqual(report["week_start"], date(2026, 7, 27))
        self.assertEqual(report["platform_metrics"], [])

    def test_platform_comparisons_are_absolute_and_platform_specific(self):
        comparisons = social_media.weekly_comparisons(
            [
                {
                    "platform": "Instagram",
                    "audience_total": 120,
                    "reach_views": 900,
                    "engagements": 75,
                },
                {
                    "platform": "YouTube",
                    "audience_total": 50,
                    "reach_views": None,
                    "engagements": 3,
                },
            ],
            [
                {
                    "platform": "Instagram",
                    "audience_total": 100,
                    "reach_views": 700,
                    "engagements": 80,
                },
                {
                    "platform": "YouTube",
                    "audience_total": None,
                    "reach_views": 400,
                    "engagements": 1,
                },
            ],
        )
        instagram, youtube = comparisons
        self.assertEqual(instagram["audience_change"], 20)
        self.assertEqual(instagram["reach_views_change"], 200)
        self.assertEqual(instagram["engagements_change"], -5)
        self.assertIsNone(youtube["audience_change"])
        self.assertIsNone(youtube["reach_views_change"])
        self.assertEqual(youtube["engagements_change"], 2)

    def test_weekly_summary_preserves_best_post_and_execution_totals(self):
        report = {
            "platform_metrics": [
                {
                    "platform": "Instagram",
                    "posts_published": 3,
                    "audience_total": 120,
                    "reach_views": 900,
                    "engagements": 75,
                    "best_post_url": "https://instagram.com/p/best/",
                    "best_post_result": "Collector comments",
                },
                {
                    "platform": "Pinterest",
                    "posts_published": 2,
                    "audience_total": 80,
                    "reach_views": 300,
                    "engagements": 20,
                },
            ]
        }
        summary = social_media.weekly_summary(
            report,
            [
                {"platform": "Instagram", "audience_total": 100},
                {"platform": "Pinterest", "audience_total": 85},
            ],
        )
        self.assertEqual(summary["total_posts"], 5)
        self.assertEqual(summary["total_audience_growth"], 15)
        self.assertEqual(summary["strongest_platform"], "Instagram")
        self.assertEqual(summary["best_post_result"], "Collector comments")


if __name__ == "__main__":
    unittest.main()
