import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fulfilment_handoff
import orders_page
import os_pages


class FulfilmentHandoffTests(unittest.TestCase):
    def test_start_qa_requires_exactly_one_valid_order_reference(self):
        valid_needs_certificate = {"order": "#SC3096", "prodigi": "Needs certificate"}

        self.assertEqual("", orders_page._fulfilment_qa_order_reference([]))
        self.assertEqual(
            "#SC3096",
            orders_page._fulfilment_qa_order_reference([valid_needs_certificate]),
        )
        self.assertEqual(
            "",
            orders_page._fulfilment_qa_order_reference(
                [valid_needs_certificate, {"order": "#SC3095"}]
            ),
        )
        self.assertEqual(
            "",
            orders_page._fulfilment_qa_order_reference([{"order": "Etsy 3096"}]),
        )

    def test_selected_order_is_queued_with_a_unique_request_identity(self):
        state = {
            fulfilment_handoff.LOOKUP_MATCHES_KEY: [{"row_id": "old"}],
            fulfilment_handoff.LOOKUP_LAST_QUERY_KEY: "#SC1",
        }

        target = fulfilment_handoff.queue_order_handoff(
            state,
            "#SC3096",
            request_id="qa-request-3096",
        )

        self.assertEqual("#SC3096", target)
        self.assertEqual("#SC3096", state[fulfilment_handoff.ORDER_INPUT_KEY])
        self.assertEqual("Prodigi", state["pending_page"])
        self.assertEqual(
            {
                "request_id": "qa-request-3096",
                "order_reference": "#SC3096",
            },
            state[fulfilment_handoff.HANDOFF_REQUEST_KEY],
        )
        self.assertEqual([], state[fulfilment_handoff.LOOKUP_MATCHES_KEY])
        self.assertEqual("", state[fulfilment_handoff.LOOKUP_LAST_QUERY_KEY])

    def test_handoff_lookup_is_consumed_and_executed_exactly_once(self):
        state = {}
        fulfilment_handoff.queue_order_handoff(
            state,
            "#SC3096",
            request_id="qa-request-3096",
        )
        finder = Mock(return_value=([{"row_id": "line-3096"}], []))

        first = os_pages._prodigi_prepare_entry_state(state=state, finder=finder)
        second = os_pages._prodigi_prepare_entry_state(state=state, finder=finder)

        self.assertEqual("#SC3096", first)
        self.assertEqual("", second)
        finder.assert_called_once_with("#SC3096")
        self.assertNotIn(fulfilment_handoff.HANDOFF_REQUEST_KEY, state)
        self.assertEqual(
            "qa-request-3096",
            state[fulfilment_handoff.HANDOFF_CONSUMED_REQUEST_KEY],
        )
        self.assertEqual("#SC3096", state[fulfilment_handoff.ORDER_INPUT_KEY])
        self.assertEqual("#SC3096", state[fulfilment_handoff.LOOKUP_LAST_QUERY_KEY])
        self.assertEqual("line-3096", state[fulfilment_handoff.LOOKUP_SELECTED_ROW_KEY])

    def test_a_genuinely_new_handoff_can_lookup_the_same_order_again(self):
        state = {}
        finder = Mock(return_value=([{"row_id": "line-3096"}], []))

        fulfilment_handoff.queue_order_handoff(
            state,
            "#SC3096",
            request_id="qa-request-first",
        )
        os_pages._prodigi_prepare_entry_state(state=state, finder=finder)
        fulfilment_handoff.queue_order_handoff(
            state,
            "#SC3096",
            request_id="qa-request-second",
        )
        os_pages._prodigi_prepare_entry_state(state=state, finder=finder)

        self.assertEqual(2, finder.call_count)
        self.assertEqual(
            "qa-request-second",
            state[fulfilment_handoff.HANDOFF_CONSUMED_REQUEST_KEY],
        )

    def test_failed_lookup_cannot_leave_a_repeating_trigger(self):
        state = {}
        fulfilment_handoff.queue_order_handoff(
            state,
            "#SC3096",
            request_id="qa-request-failure",
        )
        failing_finder = Mock(side_effect=RuntimeError("lookup unavailable"))

        with self.assertRaisesRegex(RuntimeError, "lookup unavailable"):
            os_pages._prodigi_prepare_entry_state(state=state, finder=failing_finder)

        self.assertNotIn(fulfilment_handoff.HANDOFF_REQUEST_KEY, state)
        retry_finder = Mock()
        self.assertEqual(
            "",
            os_pages._prodigi_prepare_entry_state(state=state, finder=retry_finder),
        )
        retry_finder.assert_not_called()

    def test_direct_navigation_clears_stale_handoff_and_lookup_state(self):
        state = {
            "navigation_transition": {
                "status": "pending",
                "from": "Orders",
                "to": "Prodigi",
                "source": "sidebar",
            },
            fulfilment_handoff.HANDOFF_REQUEST_KEY: {
                "request_id": "stale-request",
                "order_reference": "#SC3000",
            },
            fulfilment_handoff.ORDER_INPUT_KEY: "#SC3000",
            fulfilment_handoff.LOOKUP_MATCHES_KEY: [{"row_id": "old"}],
            fulfilment_handoff.LOOKUP_EXISTING_ROWS_KEY: [{"id": "old"}],
            fulfilment_handoff.LOOKUP_LAST_QUERY_KEY: "#SC3000",
            fulfilment_handoff.LOOKUP_SELECTED_ROW_KEY: "old",
        }
        finder = Mock()

        self.assertEqual(
            "",
            os_pages._prodigi_prepare_entry_state(state=state, finder=finder),
        )

        finder.assert_not_called()
        self.assertNotIn(fulfilment_handoff.HANDOFF_REQUEST_KEY, state)
        self.assertEqual("", state[fulfilment_handoff.ORDER_INPUT_KEY])
        self.assertEqual([], state[fulfilment_handoff.LOOKUP_MATCHES_KEY])
        self.assertEqual("", state[fulfilment_handoff.LOOKUP_LAST_QUERY_KEY])

    def test_existing_inline_shortcut_and_toolbar_share_the_same_open_helper(self):
        inline_source = inspect.getsource(orders_page._render_inline_prodigi_actions)
        toolbar_source = inspect.getsource(orders_page._render_top_actions)

        self.assertIn("on_click=_open_prodigi_for_row", inline_source)
        self.assertIn("_open_prodigi_for_row(selected_rows[0])", toolbar_source)

        fake_st = SimpleNamespace(session_state={})
        with patch.object(orders_page, "st", fake_st):
            orders_page._open_prodigi_for_row({"order": "#SC3096"})

        self.assertEqual("#SC3096", fake_st.session_state[fulfilment_handoff.ORDER_INPUT_KEY])
        self.assertIn(fulfilment_handoff.HANDOFF_REQUEST_KEY, fake_st.session_state)

    def test_manual_lookup_remains_independent_of_handoff_state(self):
        state = {}
        finder = Mock(return_value=([{"row_id": "manual-line"}], []))

        matches, existing = os_pages._prodigi_apply_order_lookup(
            "#SC3096",
            state=state,
            finder=finder,
        )

        finder.assert_called_once_with("#SC3096")
        self.assertEqual([{"row_id": "manual-line"}], matches)
        self.assertEqual([], existing)
        self.assertNotIn(fulfilment_handoff.HANDOFF_REQUEST_KEY, state)


if __name__ == "__main__":
    unittest.main()
