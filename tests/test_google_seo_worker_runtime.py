import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from psycopg.errors import DeadlockDetected

import google_seo_import
import google_seo_phase4


ROOT = Path(__file__).resolve().parents[1]


class _IdleWorker:
    worker_id = "test-worker"

    def run_once(self):
        return None


class _StopLoop(BaseException):
    pass


class GoogleSEOWorkerRuntimeTests(unittest.TestCase):
    def test_render_start_command_arguments_reach_the_bounded_worker_loop(self):
        with patch.object(
            google_seo_import,
            "_validate_worker_startup",
        ) as validate, patch.object(
            google_seo_import,
            "_run_worker_loop",
            return_value=0,
        ) as run_loop:
            result = google_seo_import.main(["worker", "--poll-seconds", "15"])

        self.assertEqual(result, 0)
        validate.assert_called_once_with()
        self.assertEqual(run_loop.call_args.kwargs, {"once": False, "poll_seconds": 15})

    def test_entrypoint_import_is_offline_and_does_not_load_ui_or_shopify_modules(self):
        script = """
import json
import socket
import sys

def blocked(*_args, **_kwargs):
    raise AssertionError("network request during worker import")

socket.create_connection = blocked
socket.socket.connect = blocked
before = set(sys.modules)
import google_seo_import
loaded = set(sys.modules) - before
forbidden = [
    "streamlit",
    "seo_page",
    "seo_blog_workflow",
    "shopify_sync",
    "edition_manager",
]
print(json.dumps({"forbidden_loaded": [name for name in forbidden if name in loaded]}))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"forbidden_loaded": []})

    def test_reporting_claim_deadlock_is_contained_and_other_boundary_still_runs(self):
        error = DeadlockDetected("deadlock detected")
        with patch.object(
            google_seo_phase4,
            "process_queued_reporting_repair",
            side_effect=error,
        ), self.assertLogs(level="ERROR") as logs:
            result, repair, errors = google_seo_import._run_worker_cycle(_IdleWorker())

        self.assertIsNone(result)
        self.assertIsNone(repair)
        self.assertEqual(errors, [("reporting_repair", error)])
        self.assertIn("stage=reporting_repair", "\n".join(logs.output))
        self.assertIn("DeadlockDetected", "\n".join(logs.output))

    def test_empty_reporting_claim_returns_none_instead_of_a_truthy_blank_job(self):
        class Cursor:
            def execute(self, _sql, _params=()):
                return None

            def fetchone(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Backend:
            def connect(self):
                return Connection()

        store = google_seo_phase4.PostgresSEOPhase4Store(Backend())
        store._schema_ready = True

        self.assertIsNone(store.claim_reporting_repair("test-worker"))

    def test_long_running_worker_sleeps_after_deadlock_instead_of_exiting(self):
        error = DeadlockDetected("deadlock detected")
        with patch.object(
            google_seo_phase4,
            "process_queued_reporting_repair",
            side_effect=error,
        ), patch.object(
            google_seo_import.time,
            "sleep",
            side_effect=_StopLoop,
        ), self.assertLogs(level="ERROR"):
            with self.assertRaises(_StopLoop):
                google_seo_import._run_worker_loop(
                    _IdleWorker(), once=False, poll_seconds=15
                )

    def test_once_mode_does_not_mask_deadlock(self):
        error = DeadlockDetected("deadlock detected")
        with patch.object(
            google_seo_phase4,
            "process_queued_reporting_repair",
            side_effect=error,
        ), self.assertLogs(level="ERROR"):
            with self.assertRaises(DeadlockDetected):
                google_seo_import._run_worker_loop(_IdleWorker(), once=True)

    def test_phase3_failure_does_not_prevent_reporting_boundary(self):
        class FailedImportWorker:
            worker_id = "phase3-failure"

            def run_once(self):
                raise ConnectionError("temporary database connection failure")

        with patch.object(
            google_seo_phase4,
            "process_queued_reporting_repair",
            return_value={"status": "completed"},
        ) as process_repair, self.assertLogs(level="ERROR"):
            result, repair, errors = google_seo_import._run_worker_cycle(
                FailedImportWorker()
            )

        self.assertIsNone(result)
        self.assertEqual(repair, {"status": "completed"})
        self.assertEqual(errors[0][0], "google_import")
        process_repair.assert_called_once_with(
            worker_id="phase3-failure-reporting"
        )

    def test_missing_database_configuration_fails_startup_clearly(self):
        with patch("supabase_backend.is_configured", return_value=False):
            with self.assertRaises(google_seo_import.SEOImportError) as raised:
                google_seo_import._validate_worker_startup()

        self.assertEqual(raised.exception.code, "worker_database_not_configured")
        self.assertFalse(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
