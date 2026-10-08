from datetime import datetime, timedelta
import unittest
from unittest.mock import Mock, patch

from crm_cache import DisplayCache
import analytics_page
import workspace_display_cache as display


class DisplayReadTests(unittest.TestCase):
    def setUp(self):
        self.user = {"id": "a", "role": "worker", "session_version": 1,
                     "is_active": True, "page_permissions": ["dashboard", "analytics"]}

    def test_scope_includes_account_status_revision_role_and_permissions(self):
        state = {}
        original = display.session_cache(state, "display", self.user)
        original.put("private", {"owner": "a"}, 30)
        self.assertIs(display.session_cache(state, "display", dict(self.user)), original)
        for change in ({"id": "b"}, {"session_version": 2}, {"role": "admin"},
                       {"page_permissions": []}, {"is_active": False}, {"account_status": "removed"}):
            with self.subTest(change=change):
                new = display.session_cache(state, "display", {**self.user, **change})
                self.assertIsNone(new.get("private"))

    def test_ttl_copy_isolation_size_bound_and_failure_retry(self):
        clock = Mock(return_value=0)
        cache = DisplayCache(limit=2, byte_limit=128, clock=clock)
        read = Mock(return_value={"value": [1]})
        display.read_display(cache, "a", read)["value"].append(2)
        self.assertEqual(display.read_display(cache, "a", read), {"value": [1]})
        read.assert_called_once()
        clock.return_value = 31
        display.read_display(cache, "a", read)
        self.assertEqual(read.call_count, 2)
        broken = Mock(side_effect=[ValueError("temporary"), {"ok": True}])
        with self.assertRaises(ValueError): display.read_display(cache, "bad", broken)
        self.assertEqual(display.read_display(cache, "bad", broken), {"ok": True})
        for i in range(10): cache.put(str(i), {"i": i}, 30)
        self.assertLessEqual(len(cache.rows), 2)
        self.assertLessEqual(cache.bytes, 128)

    def test_home_reads_once_and_refresh_or_date_invalidates(self):
        state, now, read = {}, datetime(2026, 10, 8), Mock(return_value={"metrics": {"tasks": 5}})
        for _ in range(5): display.home_weekly_snapshot(state, self.user, now, read)
        read.assert_called_once()
        display.invalidate_home(state)
        display.home_weekly_snapshot(state, self.user, now, read)
        display.home_weekly_snapshot(state, self.user, now + timedelta(days=1), read)
        self.assertEqual(read.call_count, 3)

    def test_report_cache_keys_dates_property_contract_and_explicit_queue(self):
        store = Mock()
        store.report_for_period.return_value = {"value": 1}
        store.latest_report.return_value = {"value": 2}
        reader = analytics_page._ReportDisplayStore(store, DisplayCache())
        for _ in range(3): reader.report_for_period("p", "overview", "1", "2")
        store.report_for_period.assert_called_once()
        for args in (("q", "overview", "1", "2"), ("p", "devices", "1", "2"), ("p", "overview", "1", "3")):
            reader.report_for_period(*args)
        self.assertEqual(store.report_for_period.call_count, 4)
        reader.queue_report("p", "overview", "1", "2", requested_by="a")
        store.queue_report.assert_called_once()
        reader.report_for_period("p", "overview", "1", "2")
        self.assertEqual(store.report_for_period.call_count, 5)

    def test_store_reused_in_session_and_recreated_on_permission_change(self):
        fake_st = Mock(session_state={})
        with patch.object(analytics_page, "st", fake_st), patch.object(analytics_page.analytics_reporting, "PostgresAnalyticsStore") as cls:
            first = analytics_page._session_report_store(self.user)
            self.assertIs(analytics_page._session_report_store(self.user), first)
            cls.assert_called_once()
            self.assertIsNot(analytics_page._session_report_store({**self.user, "session_version": 2}), first)


if __name__ == "__main__": unittest.main()
