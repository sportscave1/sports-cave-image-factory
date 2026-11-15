import csv
import io
import unittest
from datetime import datetime, timedelta, timezone

import daily_activity_reporting as reporting


OWNER_EMAIL = "owner@sportscave.test"


def account(
    user_id,
    name,
    *,
    email="",
    role="worker",
    active=True,
    timezone_name="Asia/Manila",
):
    return {
        "id": user_id,
        "username": email.split("@", 1)[0] if email else name.casefold().replace(" ", ""),
        "email": email,
        "display_name": name,
        "role": role,
        "country": "Australia" if timezone_name == "Australia/Sydney" else "Philippines",
        "timezone": timezone_name,
        "is_active": active,
    }


def activity(
    row_id,
    created_at,
    action,
    actor_id,
    actor_name,
    *,
    message="",
    status="success",
    source="Files",
    metadata=None,
):
    combined_metadata = {
        "actor_id": actor_id,
        "actor_display": actor_name,
        "status": status,
        "result": status,
        "source_user_initiated": True,
        **(metadata or {}),
    }
    return {
        "id": row_id,
        "event_type": action,
        "activity_action_type": action,
        "activity_message": message or action.replace("_", " ").title(),
        "activity_page": source,
        "activity_metadata": combined_metadata,
        "actor": actor_name,
        "source": source,
        "created_at": created_at,
        "entity_type": "test",
        "entity_id": str((metadata or {}).get("entity_id") or ""),
    }


class ReportPeriodTests(unittest.TestCase):
    def test_sydney_start_boundary_handles_dst(self):
        summer = reporting.build_report_period(
            datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
        )
        winter = reporting.build_report_period(
            datetime(2026, 7, 15, 7, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(
            summer.start_utc,
            datetime(2026, 1, 14, 13, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            winter.start_utc,
            datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc),
        )

    def test_period_is_midnight_through_actual_generation_time(self):
        now = datetime(2026, 7, 28, 8, 17, 31, tzinfo=timezone.utc)
        period = reporting.build_report_period(now)

        self.assertEqual(period.report_date.isoformat(), "2026-07-28")
        self.assertEqual(period.start_local.hour, 0)
        self.assertEqual(period.end_utc, now)
        self.assertEqual(period.end_local.hour, 18)
        self.assertEqual(period.end_local.minute, 17)

    def test_delayed_same_day_run_is_ready_without_backlog_date(self):
        configuration = reporting.DigestConfiguration(
            enabled=True,
            timezone_name="Australia/Sydney",
            send_hour=17,
        )
        ready = reporting.production_run_decision(
            datetime(2026, 7, 28, 8, 30, tzinfo=timezone.utc),
            configuration=configuration,
        )
        early = reporting.production_run_decision(
            datetime(2026, 7, 28, 5, 30, tzinfo=timezone.utc),
            configuration=configuration,
        )

        self.assertEqual(ready, (True, "ready", ready[2]))
        self.assertEqual(ready[2].isoformat(), "2026-07-28")
        self.assertEqual(early[0:2], (False, "before_send_hour"))
        self.assertEqual(early[2].isoformat(), "2026-07-28")

    def test_disabled_run_exits_cleanly(self):
        decision = reporting.production_run_decision(
            datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc),
            configuration=reporting.DigestConfiguration(
                enabled=False,
                timezone_name="Australia/Sydney",
                send_hour=17,
            ),
        )
        self.assertEqual(decision[0:2], (False, "disabled"))


class StaffReportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
        self.period = reporting.build_report_period(self.now)
        self.owner = account(
            "owner-1",
            "Nathan",
            email=OWNER_EMAIL,
            role="admin",
            timezone_name="Australia/Sydney",
        )
        self.worker = account(
            "worker-1",
            "VA One",
            email="va@sportscave.test",
        )
        self.quiet = account(
            "worker-2",
            "VA Quiet",
            email="quiet@sportscave.test",
        )
        self.inactive = account(
            "inactive-1",
            "Inactive",
            email="inactive@sportscave.test",
            active=False,
        )

    def build(self, rows, sheet=None):
        return reporting.build_report_snapshot(
            period=self.period,
            accounts=[self.owner, self.worker, self.quiet, self.inactive],
            activity_rows=rows,
            daily_execution_sheet=sheet,
            owner_email=OWNER_EMAIL,
            recipient="reports@sportscave.test",
        )

    def test_every_active_staff_member_appears_and_inactive_is_excluded(self):
        snapshot = self.build([])

        self.assertEqual(
            [member["display_name"] for member in snapshot["staff"]],
            ["Nathan", "VA One", "VA Quiet"],
        )
        self.assertTrue(snapshot["staff"][0]["is_owner"])
        self.assertTrue(
            all(
                member["work_lines"] == []
                for member in snapshot["staff"]
            )
        )
        self.assertIn("No recorded activity for this report period", snapshot["html"])

    def test_meaningful_counts_grouping_failures_and_time_bounds(self):
        rows = [
            activity(
                "upload-1",
                self.period.start_utc + timedelta(hours=2),
                "files_uploaded",
                "worker-1",
                "VA One",
                message="Uploaded file: product.jpg",
                metadata={"filename": "product.jpg"},
            ),
            activity(
                "upload-2",
                self.period.start_utc + timedelta(hours=3),
                "files_uploaded",
                "worker-1",
                "VA One",
                message="Uploaded file: product.jpg",
                metadata={"filename": "product.jpg"},
            ),
            activity(
                "failed",
                self.period.start_utc + timedelta(hours=4),
                "certificate_upload_failed",
                "owner-1",
                "Nathan",
                message="Certificate upload failed",
                status="failed",
                source="Orders",
            ),
            activity(
                "system",
                self.period.start_utc + timedelta(hours=5),
                "webhook_received",
                "worker-1",
                "VA One",
                message="Webhook received",
            ),
            activity(
                "previous",
                self.period.start_utc - timedelta(seconds=1),
                "files_uploaded",
                "worker-1",
                "VA One",
            ),
            activity(
                "future",
                self.period.end_utc + timedelta(seconds=1),
                "files_uploaded",
                "worker-1",
                "VA One",
            ),
        ]
        snapshot = self.build(rows)
        by_name = {member["display_name"]: member for member in snapshot["staff"]}

        self.assertEqual(by_name["VA One"]["total_actions"], 2)
        self.assertEqual(by_name["VA One"]["completed_actions"], 2)
        self.assertEqual(by_name["Nathan"]["failed_actions"], 1)
        self.assertEqual(snapshot["summary"]["total_actions"], 3)
        self.assertEqual(snapshot["summary"]["failed_actions"], 1)
        self.assertEqual(by_name["VA One"]["work_lines"][0]["count"], 2)
        self.assertIn("(x2)", by_name["VA One"]["work_lines"][0]["label"])
        self.assertTrue(any("Nathan" in line for line in snapshot["attention"]))

    def test_actor_id_prevents_daily_work_being_attributed_by_duplicate_name(self):
        duplicate = account(
            "worker-3",
            "Nathan",
            email="duplicate@sportscave.test",
        )
        row = activity(
            "daily",
            self.period.start_utc + timedelta(hours=2),
            "daily_execution_mip_completed",
            "owner-1",
            "Nathan",
            source="Dashboard",
        )
        snapshot = reporting.build_report_snapshot(
            period=self.period,
            accounts=[self.owner, duplicate],
            activity_rows=[row],
            owner_email=OWNER_EMAIL,
            recipient="reports@sportscave.test",
        )
        by_id = {member["id"]: member for member in snapshot["staff"]}

        self.assertEqual(by_id["owner-1"]["total_actions"], 1)
        self.assertEqual(by_id["worker-3"]["total_actions"], 0)

    def test_daily_execution_uses_sheet_status_and_counts_all_tasks(self):
        sheet = {
            "user_id": "owner-1",
            "sheet_date": "2026-07-28",
            "status": "active",
            "top_tasks": [
                {"task": "Launch product", "status": "done", "why": "Revenue"},
                {"task": "Review ads", "status": "couldnt_finish", "why": "Campaign"},
                {"task": "Approve artwork", "completed": True},
            ],
            "additional_items": [
                {"task": "Reply to supplier", "status": "done", "details": "Confirm stock"}
            ],
            "review_data": {"could_not_finish": "Waiting for creative"},
            "planning_data": {"carried_forward": [{"task": "Review ads"}]},
        }
        snapshot = self.build([], sheet=sheet)
        daily = snapshot["daily_execution"]

        self.assertTrue(daily["exists"])
        self.assertEqual(daily["task_count"], 4)
        self.assertEqual(daily["completed_count"], 4)
        self.assertEqual(daily["successful_count"], 3)
        self.assertEqual(daily["could_not_finish_count"], 1)
        self.assertEqual(daily["outstanding_count"], 0)
        self.assertEqual(daily["completion_percentage"], 100)
        self.assertEqual([task["task"] for task in daily["mips"]], [
            "Launch product",
            "Review ads",
            "Approve artwork",
        ])
        self.assertEqual(daily["moved_tasks"][0]["task"], "Review ads")
        self.assertIn("Waiting for creative", daily["notes"])

    def test_missing_daily_execution_is_clear(self):
        snapshot = self.build([])
        self.assertFalse(snapshot["daily_execution"]["exists"])
        self.assertTrue(
            any("No Daily Execution sheet" in item for item in snapshot["attention"])
        )

    def test_daily_execution_sheet_for_another_user_is_not_attributed_to_owner(self):
        snapshot = self.build(
            [],
            sheet={
                "user_id": "worker-1",
                "sheet_date": "2026-07-28",
                "top_tasks": [{"task": "Worker task", "status": "done"}],
            },
        )

        self.assertFalse(snapshot["daily_execution"]["exists"])
        self.assertNotIn("Worker task", snapshot["html"])

    def test_email_and_csv_are_compact_safe_and_complete(self):
        rows = [
            activity(
                "formula",
                self.period.start_utc + timedelta(hours=2),
                "files_uploaded",
                "worker-1",
                "VA One",
                message="Uploaded file: =SUM(A1:A2)",
                metadata={"filename": "=SUM(A1:A2)"},
            ),
            activity(
                "secret",
                self.period.start_utc + timedelta(hours=3),
                "certificate_upload_failed",
                "owner-1",
                "Nathan",
                message="password=hunter2 Traceback (most recent call last): private",
                status="failed",
                source="Orders",
            ),
        ]
        snapshot = self.build(rows)
        csv_rows = list(csv.DictReader(io.StringIO(snapshot["csv_content"])))

        self.assertIn('meta name="viewport"', snapshot["html"])
        self.assertIn("max-width:680px", snapshot["html"])
        self.assertIn("Nathan", snapshot["html"])
        self.assertIn("VA Quiet", snapshot["text"])
        self.assertNotIn("hunter2", snapshot["html"])
        self.assertNotIn("Traceback (most recent call last)", snapshot["csv_content"])
        self.assertEqual(len(csv_rows), 2)
        formula_row = next(row for row in csv_rows if row["Staff Member"] == "VA One")
        self.assertTrue(formula_row["Item or Product"].startswith("'="))

    def test_production_idempotency_is_deterministic_and_test_is_separate(self):
        production = self.build([])
        test_snapshot = {**production, "is_test": True}

        first = reporting.deterministic_idempotency_key(production)
        second = reporting.deterministic_idempotency_key(production)
        test_key = reporting.deterministic_idempotency_key(test_snapshot, nonce="one")

        self.assertEqual(first, second)
        self.assertNotEqual(first, test_key)
        self.assertLessEqual(len(first), 256)


if __name__ == "__main__":
    unittest.main()
