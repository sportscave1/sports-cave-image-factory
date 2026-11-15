import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import human_work
import sports_cave_dashboard


ROOT = Path(__file__).resolve().parents[1]


def audit_row(
    action,
    *,
    actor_id="staff-1",
    actor_display="Nathan",
    role="admin",
    page="Mockups",
    entity_type="record",
    entity_id="record-1",
    message="Work completed",
    created_at="2026-08-10T01:00:00Z",
    metadata=None,
    event_key="event-1",
    actor=None,
):
    clean_metadata = {
        "actor_id": actor_id,
        "actor_display": actor_display,
        "actor_role": role,
        "actor_timezone": "Australia/Sydney",
        "origin": "human",
        "status": "success",
        "result": "success",
        "event_key": event_key,
        **dict(metadata or {}),
    }
    return {
        "id": event_key,
        "event_type": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source": page,
        "actor": actor if actor is not None else actor_display,
        "created_at": created_at,
        "new_value": {
            "message": message,
            "page": page,
            "action_type": action,
            "metadata": clean_metadata,
        },
    }


class HumanWorkTrackingTests(unittest.TestCase):
    def test_required_human_actions_project_to_one_attributed_event(self):
        cases = (
            ("mockups_saved_dropbox", "Mockups", "mockups_saved", "Mockups saved"),
            ("product_created", "Products", "product_created", "New product created"),
            ("product_updated", "Products", "product_updated", "Existing product updated"),
            ("new_product_prompt_generated", "Product Uploads", "product_upload_completed", "Product upload completed"),
            ("ad_images_saved", "Ads", "ad_creative_saved", "Ad creative saved"),
            ("keyword_updated", "SEO", "seo_keyword_mapping_updated", "SEO keyword mapping updated"),
            ("order_fulfilled_certificate_generated", "Orders", "order_fulfilled_certificate_generated", "Order fulfilled"),
            ("manual_fulfilment_override", "Orders", "manual_fulfilment_override", "Manual fulfilment override"),
            ("daily_planner_task_completed", "Daily Planner", "daily_planner_task_completed", "Planner task completed"),
        )
        for action, area, canonical, label in cases:
            with self.subTest(action=action):
                row = audit_row(
                    action,
                    page=area,
                    message=f"{label}: Steel Curtain",
                    metadata={"product_name": "Steel Curtain", "task": "Book supplier"},
                    event_key=f"{action}:steel-curtain",
                )
                first = human_work.activity_to_human_work_event(row)
                duplicate = human_work.activity_to_human_work_event({**row, "id": f"{action}-retry"})

                self.assertIsNotNone(first)
                self.assertEqual("staff-1", first["user_id"])
                self.assertEqual("Nathan", first["staff_display_name"])
                self.assertEqual(area, first["area"])
                self.assertEqual(canonical, first["action_type"])
                self.assertEqual("completed", first["outcome"])
                self.assertTrue(first["description"])
                unique = {event["correlation_key"]: event for event in (first, duplicate)}
                self.assertEqual(1, len(unique))

    def test_two_staff_members_are_attributed_from_authenticated_metadata(self):
        nathan = human_work.activity_to_human_work_event(
            audit_row("product_created", actor_id="admin-1", actor_display="Nathan", role="admin", event_key="product:nathan")
        )
        reina = human_work.activity_to_human_work_event(
            audit_row("product_updated", actor_id="worker-1", actor_display="Reina", role="worker", event_key="product:reina")
        )

        self.assertEqual(("admin-1", "Nathan", "admin"), (nathan["user_id"], nathan["staff_display_name"], nathan["staff_role"]))
        self.assertEqual(("worker-1", "Reina", "worker"), (reina["user_id"], reina["staff_display_name"], reina["staff_role"]))

    def test_system_noise_and_unauthenticated_rows_are_not_human_work(self):
        noisy = (
            audit_row("shopify_product_metafield_mirror", message="Metafield mirror updated"),
            audit_row("webhook_orders_paid", message="Webhook processed"),
            audit_row("daily_planner_task_time_up", page="Daily Planner", message="Time up"),
            audit_row("files_downloaded", page="Files", message="Downloaded file"),
            audit_row("product_created", actor_id="", actor_display="", actor="sports_cave_os"),
        )

        self.assertTrue(all(human_work.activity_to_human_work_event(row) is None for row in noisy))

    def test_failed_operations_do_not_count_as_completed_work(self):
        failed = human_work.activity_to_human_work_event(
            audit_row(
                "certificate_generation_failed",
                page="Orders",
                message="Certificate generation failed",
                metadata={"status": "failed", "result": "failed"},
                event_key="certificate:failed",
            )
        )

        self.assertEqual("failed", failed["outcome"])
        self.assertFalse(human_work.event_counts_as_completed(failed))

    def test_home_and_reporting_use_same_canonical_weekly_records(self):
        now = datetime(2026, 8, 12, 12, 0, tzinfo=ZoneInfo("Australia/Sydney"))
        users = [
            {
                "id": "admin-1",
                "display_name": "Nathan",
                "username": "nathan",
                "email": "nathan@example.com",
                "role": "admin",
                "is_active": True,
                "account_status": "active",
            }
        ]
        sheets = [
            {
                "id": "sheet-a",
                "user_id": "admin-1",
                "user_name": "Nathan",
                "sheet_date": "2026-08-10",
                "status": "active",
                "top_tasks": [
                    {
                        "task": "Publish campaign",
                        "time_blocked": "30 minutes",
                        "status": "done",
                        "completed_at": "2026-08-10T02:00:00Z",
                    }
                ],
                "additional_items": [],
            }
        ]
        timers = [
            {
                "sheet_id": "sheet-a",
                "task_type": "top",
                "task_index": 0,
                "outcome": "completed",
                "outcome_at": "2026-08-10T02:00:00Z",
                "actual_elapsed_seconds": 900,
            }
        ]
        inside = human_work.activity_to_human_work_event(
            audit_row(
                "product_created",
                actor_id="admin-1",
                actor_display="Nathan",
                page="Products",
                entity_type="product",
                entity_id="purple-reign",
                message="New product created: Purple Reign",
                event_key="product:purple-reign",
                created_at="2026-08-10T00:15:00Z",
            )
        )
        outside = human_work.activity_to_human_work_event(
            audit_row(
                "ad_images_saved",
                actor_id="admin-1",
                actor_display="Nathan",
                page="Ads",
                entity_type="ad",
                entity_id="last-week",
                message="Ad creative saved: Last week",
                event_key="ad:last-week",
                created_at="2026-08-09T13:59:00Z",
            )
        )
        failed = human_work.activity_to_human_work_event(
            audit_row(
                "certificate_upload_failed",
                actor_id="admin-1",
                actor_display="Nathan",
                page="Orders",
                message="Certificate upload failed",
                metadata={"status": "failed", "result": "failed"},
                event_key="certificate:failed-week",
                created_at="2026-08-10T03:00:00Z",
            )
        )

        class Backend:
            def load_home_weekly_work_bundle(self, user_id, week_start, week_end, start_utc, end_utc, *, include_team):
                return {
                    "users": users,
                    "sheets": sheets,
                    "timers": timers,
                    "human_work": [inside, outside, failed],
                    "query_count": 1,
                }

        account = {**users[0], "timezone": "Australia/Sydney", "page_permissions": []}
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=Backend()):
            home = sports_cave_dashboard.build_home_weekly_work_snapshot(account, now)
            reporting = sports_cave_dashboard.build_reporting_staff_week_snapshot(account, now.date())

        self.assertEqual("2026-08-10", home["week_start"])
        self.assertEqual(2, home["metrics"]["tasks_completed"])
        self.assertEqual(1, home["metrics"]["planner_tasks_completed"])
        self.assertEqual(1, home["metrics"]["meaningful_actions"])
        self.assertEqual(100.0, home["metrics"]["completion_percentage"])
        self.assertEqual(2, len(home["completed_work"]))
        self.assertFalse(any("Last week" in row["work"] for row in home["completed_work"]))
        self.assertFalse(any(row["status"] == "Failed" for row in home["completed_work"]))
        self.assertEqual(2, reporting["staff_rows"][0]["Weekly total"])
        self.assertEqual(reporting["staff_rows"][0]["Weekly total"], len(reporting["details"]))

    def test_schema_and_backend_enforce_idempotent_canonical_storage(self):
        migration = (ROOT / "migrations" / "20260817_human_work_events.sql").read_text(encoding="utf-8")
        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS human_work_events", migration)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_human_work_events_correlation_key", migration)
        self.assertIn("ON CONFLICT (correlation_key)", migration)
        self.assertIn("_record_human_work_from_audit_row(cur, row)", backend_source)
        self.assertIn("def record_human_work_event", backend_source)


if __name__ == "__main__":
    unittest.main()
