"""Run SQL integration with DESIGN_V4_TEST_PG=1 against the isolated fixture only."""
import os
import unittest
from unittest.mock import patch

import psycopg
import design_schedule as schedule
import sports_cave_dashboard as dashboard
import supabase_backend as backend
from tests import design_v4_fixture as fixture


@unittest.skipUnless(os.environ.get("DESIGN_V4_TEST_PG") == "1", "isolated PostgreSQL fixture not enabled")
class DesignDeletionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.initialize()

    def setUp(self):
        self.context = fixture.local_backend()
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        dashboard.clear_task_cache()

    def record(self, task_id):
        with fixture.connect() as conn:
            return conn.execute("SELECT * FROM dashboard_tasks WHERE id=%s", (task_id,)).fetchone()

    def test_original_parameter_error_and_single_delete_persist(self):
        with fixture.connect() as conn:
            with self.assertRaises(psycopg.errors.IndeterminateDatatype):
                conn.execute("SELECT jsonb_build_object('deleted_by', %s)", ("Fixture User",))
        task_id = fixture.seed("Single deletion")
        before = self.record(task_id)
        result = dashboard.delete_design_task(task_id, user=fixture.USER)
        self.assertEqual(result["id"], task_id)
        after = self.record(task_id)  # A fresh connection proves commit, not just RETURNING.
        self.assertEqual(after["status"], "deleted")
        self.assertEqual(after["metadata"]["deleted_by"], "Fixture User")
        for key, value in before["metadata"].items():
            self.assertEqual(after["metadata"][key], value)
        self.assertIsNone(dashboard.delete_design_task(task_id, user=fixture.USER))
        with fixture.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM audit_logs WHERE entity_id=%s AND event_type='task_deleted'", (task_id,)).fetchone()["n"], 1)

    def test_bulk_commits_exact_ids_and_invalidates_cached_count(self):
        ids = [fixture.seed("Bulk A"), fixture.seed("Bulk B")]
        other = fixture.seed("Untouched upload", section=dashboard.UPLOAD_TASK_GROUP)
        completed = fixture.seed("Untouched complete", status="complete")
        snapshots = [self.record(other), self.record(completed)]
        before = dashboard.list_tasks(section=dashboard.DESIGN_TASK_GROUP, limit=5000)
        result = dashboard.delete_design_tasks(ids + ids, user=fixture.USER)
        self.assertEqual({task["id"] for task in result}, set(ids))
        self.assertTrue(all(self.record(task_id)["status"] == "deleted" for task_id in ids))
        after = dashboard.list_tasks(section=dashboard.DESIGN_TASK_GROUP, limit=5000)
        self.assertEqual(len(before) - len(after), 2)
        self.assertEqual([self.record(other), self.record(completed)], snapshots)

    def test_ineligible_member_rolls_back_every_task(self):
        for kwargs in ({"section": dashboard.UPLOAD_TASK_GROUP}, {"status": "complete"}):
            good = fixture.seed("Must remain active")
            bad = fixture.seed("Ineligible", **kwargs)
            with self.assertRaisesRegex(dashboard.DashboardStorageError, "No designs were deleted"):
                dashboard.delete_design_tasks([good, bad], user=fixture.USER)
            self.assertEqual(self.record(good)["status"], "open")

    def test_audit_failure_rolls_back_single_and_bulk(self):
        for bulk in (False, True):
            task_id = fixture.seed("Audit failure")
            with patch.object(backend, "_insert_audit_log", side_effect=RuntimeError("fixture audit failure")):
                with self.assertRaises(dashboard.DashboardStorageError):
                    if bulk:
                        dashboard.delete_design_tasks([task_id], user=fixture.USER)
                    else:
                        dashboard.delete_design_task(task_id, user=fixture.USER)
            self.assertEqual(self.record(task_id)["status"], "open")


class DesignSelectionTests(unittest.TestCase):
    def test_permission_denied_before_backend_call(self):
        with patch.object(dashboard, "get_supabase_backend") as get_backend:
            with self.assertRaises(PermissionError):
                dashboard.delete_design_tasks(["one"], user={})
            get_backend.assert_not_called()

    def test_partial_backend_confirmation_is_not_success(self):
        with patch.object(dashboard, "get_supabase_backend") as get_backend:
            get_backend.return_value.delete_dashboard_tasks.return_value = [{"id": "one"}]
            with self.assertRaisesRegex(dashboard.DashboardStorageError, "did not confirm every"):
                dashboard.delete_design_tasks(["one", "two"], user=fixture.USER)

    def test_active_schedule_loads_beyond_first_5000(self):
        first = [{"id": str(i)} for i in range(5000)]
        last = [{"id": "5000"}]
        with patch.object(dashboard, "list_tasks", side_effect=[first, last]) as read, patch.object(dashboard, "task_table_rows", return_value=[]):
            tasks, _ = schedule._load_view_tasks("Active Designs")
        self.assertEqual(len(tasks), 5001)
        self.assertEqual(read.call_args.kwargs["offset"], 5000)


if __name__ == "__main__":
    unittest.main()
