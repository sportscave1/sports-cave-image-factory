import unittest
from unittest.mock import Mock, patch
import analytics_page as page
import analytics_reporting


class Tab:
    def __init__(self, selected): self.open = selected
    def __enter__(self): return self
    def __exit__(self, *_): pass


class AnalyticsFragmentTests(unittest.TestCase):
    def test_only_selected_tab_reads_and_error_retries_without_parent_render(self):
        store, st = Mock(), Mock()
        store.report_for_period.return_value = {"rows": []}
        period = {"start_date": "2026-10-01", "end_date": "2026-10-07"}
        render = page._overview_breakdowns.__wrapped__
        for selected, expected in enumerate(("pages_screens", "traffic_acquisition", "countries", "devices")):
            store.reset_mock()
            st.tabs.return_value = [Tab(i == selected) for i in range(4)]
            with patch.object(page, "st", st), patch.object(page, "_metric_cards", side_effect=AssertionError("parent render")):
                render(store, "property", period)
            store.report_for_period.assert_called_once_with("property", expected, "2026-10-01", "2026-10-07")
        store.report_for_period.side_effect = analytics_reporting.AnalyticsReportingError("Unavailable")
        with patch.object(page, "st", st): render(store, "property", period)
        st.error.assert_called_once()
        store.report_for_period.side_effect = None
        with patch.object(page, "st", st): render(store, "property", period)
        self.assertEqual(st.error.call_count, 1)


if __name__ == "__main__": unittest.main()
