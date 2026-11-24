"""Use synthetic leases/cursors; no database or provider connection."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import unittest

import supabase_backend as db


class DatabaseTimingTests(unittest.TestCase):
    def test_success_exposes_existing_connection_and_query_diagnostics(self):
        conn = MagicMock()
        clock = [10.]
        @contextmanager
        def lease():
            clock[0] += .025
            yield conn
        def read(cur):
            clock[0] += .040
            return ["synthetic"]
        with patch.object(db.time, "perf_counter", side_effect=lambda: clock[0]), \
                patch.object(db, "_rollback_read_connection"), patch("builtins.print") as output:
            value, diagnostic = db._run_read_operation("fixture.startup", read, connection_factory=lease)
        self.assertEqual(value, ["synthetic"])
        text = output.call_args.args[0]
        self.assertIn(f"connection_ms={diagnostic['connection_ms']}", text)
        self.assertIn(f"query_ms={diagnostic['query_ms']}", text)
        self.assertGreater(diagnostic["connection_ms"], 20)
        self.assertGreater(diagnostic["query_ms"], 35)
        self.assertNotIn("synthetic", text)

    def test_shared_read_has_no_second_connection_and_logs_existing_query_time(self):
        cursor = MagicMock()
        with db._shared_database_read_cursor(cursor), patch("builtins.print") as output:
            value, diagnostic = db._run_read_operation("fixture.shared", lambda cur: [1])
        self.assertEqual(value, [1])
        self.assertEqual(diagnostic["connection_ms"], 0)
        self.assertIn("connection_ms=0", output.call_args.args[0])
        self.assertIn("query_ms=", output.call_args.args[0])

    def test_failure_timing_preserves_error_and_does_not_log_payloads(self):
        conn = MagicMock()
        @contextmanager
        def lease():
            yield conn
        def read(cur):
            raise TimeoutError("private customer payload")
        with patch.object(db, "_rollback_read_connection"), patch("builtins.print") as output:
            with self.assertRaises(db.DatabaseReadError) as error:
                db._run_read_operation("fixture.failure", read, connection_factory=lease)
        self.assertEqual(error.exception.diagnostic["category"], "request_timeout")
        warning = next(call.args[0] for call in output.call_args_list if call.args[0].startswith("WARN"))
        self.assertIn("connection_ms=", warning)
        self.assertIn("query_ms=", warning)
        self.assertNotIn("private customer payload", warning)


if __name__ == "__main__":
    unittest.main()
