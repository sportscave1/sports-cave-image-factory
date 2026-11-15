import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import order_action_state
import order_allocator
import orders_page
import supabase_backend


def _raw_order_line(*, order_id="100", line_id="200", order_name="#SC100", source="Shopify", assignments=None):
    return {
        "shopify_order_id": f"gid://shopify/Order/{order_id}",
        "order_name": order_name,
        "shopify_line_item_id": f"gid://shopify/LineItem/{line_id}",
        "source_name": source,
        "product_title": f"Product {line_id}",
        "variant_title": "Black / L",
        "quantity": 1,
        "created_at": "2026-08-18T01:00:00Z",
        "assignments": list(assignments or []),
    }


def _assignment(*, assignment_id="edition-1", number=1, index=1, certificate_id="certificate-1"):
    return {
        "edition_order_id": assignment_id,
        "edition_number": number,
        "edition_total": 100,
        "allocation_index": index,
        "certificate_status": "Ready",
        "certificate_id": certificate_id,
    }


class OrdersCanonicalRowIdentityTests(unittest.TestCase):
    def test_ordinary_single_line_order_appears_once(self):
        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [_raw_order_line(assignments=[_assignment()])]
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("gid://shopify/LineItem/200", rows[0]["shopify_line_item_id"])

    def test_genuine_two_line_order_preserves_both_lines(self):
        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [
                _raw_order_line(line_id="201", assignments=[_assignment(assignment_id="edition-1", number=1)]),
                _raw_order_line(line_id="202", assignments=[_assignment(assignment_id="edition-2", number=2)]),
            ]
        )

        self.assertEqual(2, len(rows))
        self.assertEqual(
            {"gid://shopify/LineItem/201", "gid://shopify/LineItem/202"},
            {row["shopify_line_item_id"] for row in rows},
        )

    def test_duplicate_certificate_join_rows_collapse_to_one_canonical_unit(self):
        first = _assignment(certificate_id="certificate-old")
        second = {
            **_assignment(certificate_id="certificate-current"),
            "shopify_file_url": "https://cdn.example/current.pdf",
        }

        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [_raw_order_line(assignments=[first, second])]
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("https://cdn.example/current.pdf", rows[0]["certificate_pdf_url"])

    def test_distinct_shopify_etsy_and_manual_legacy_sources_remain_separate(self):
        common = {
            "order": "#100",
            "source_order_id": "source-order-100",
            "source_line_item_id": "source-line-1",
            "product": "Collector Print",
            "variant": "Black / L",
            "allocation_index": 1,
        }
        rows = order_allocator.canonicalize_fulfilment_rows(
            [
                {**common, "source_name": "Shopify"},
                {**common, "source_name": "Etsy"},
                {**common, "source_name": "Manual"},
            ]
        )

        self.assertEqual(3, len(rows))
        self.assertEqual(3, len({order_allocator.fulfilment_row_identity(row) for row in rows}))

    def test_quantity_units_and_separate_editions_are_not_merged(self):
        common = {
            "shopify_order_id": "gid://shopify/Order/100",
            "shopify_line_item_id": "gid://shopify/LineItem/200",
        }
        rows = order_allocator.canonicalize_fulfilment_rows(
            [
                {**common, "allocation_index": 1, "edition_number": 8},
                {**common, "allocation_index": 2, "edition_number": 9},
            ]
        )

        self.assertEqual(2, len(rows))
        self.assertNotEqual(
            order_allocator.fulfilment_row_identity(rows[0]),
            order_allocator.fulfilment_row_identity(rows[1]),
        )

    def test_legacy_assignments_without_unit_indexes_use_stable_edition_rows(self):
        first = _assignment(assignment_id="edition-a", number=8)
        second = _assignment(assignment_id="edition-b", number=9)
        first.pop("allocation_index")
        second.pop("allocation_index")

        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [_raw_order_line(assignments=[first, second])]
        )

        self.assertEqual(2, len(rows))
        self.assertEqual({"edition-a", "edition-b"}, {row["edition_order_id"] for row in rows})

    def test_snapshot_refresh_and_rerun_replace_instead_of_multiply(self):
        duplicate_rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [_raw_order_line(assignments=[_assignment(), _assignment()])]
        )
        fake_streamlit = SimpleNamespace(session_state={})
        payload = {"rows": duplicate_rows + duplicate_rows, "row_count": 4, "source": "test"}

        with patch.object(orders_page, "st", fake_streamlit):
            orders_page._apply_snapshot_payload(payload)
            orders_page._apply_snapshot_payload(payload)

        self.assertEqual(1, len(fake_streamlit.session_state[orders_page.ROWS_KEY]))
        self.assertEqual(1, fake_streamlit.session_state[orders_page.META_KEY]["row_count"])

    def test_selection_and_actions_retain_the_exact_canonical_line(self):
        row = order_allocator._snapshot_rows_from_supabase_order_rows(
            [_raw_order_line(line_id="777", assignments=[_assignment(assignment_id="edition-777", number=77)])]
        )[0]
        fake_streamlit = SimpleNamespace(
            session_state={
                orders_page.GRID_KEY: {"selection": {"rows": [0]}},
                orders_page.ROWS_KEY: [row],
            }
        )

        with patch.object(orders_page, "st", fake_streamlit):
            selected = orders_page._selected_rows_from_state([row])
            current = orders_page._current_row_for(selected[0])

        self.assertEqual("gid://shopify/LineItem/777", current["shopify_line_item_id"])
        self.assertEqual("edition-777", current["edition_order_id"])
        self.assertEqual(
            orders_page.files_window_launcher.files_window_href(orders_page.ORDERS_FILES_RELATIVE_FOLDER),
            orders_page._normalise_row(current)["file"],
        )

    def test_badge_and_pending_totals_ignore_duplicate_canonical_lines(self):
        completed = {
            "shopify_order_id": "gid://shopify/Order/100",
            "shopify_line_item_id": "gid://shopify/LineItem/200",
            "allocation_index": 1,
            "financial_status": "paid",
            "prodigi_status": "Complete",
        }
        pending = {
            "shopify_order_id": "gid://shopify/Order/101",
            "shopify_line_item_id": "gid://shopify/LineItem/201",
            "allocation_index": 1,
            "financial_status": "paid",
            "certificate_status": "Needs certificate",
        }
        canonical = order_allocator.canonicalize_fulfilment_rows(
            [completed, completed, pending, pending]
        )

        self.assertEqual(2, len(canonical))
        self.assertEqual(1, sum(order_action_state.row_requires_action(row) for row in canonical))
        self.assertEqual(1, order_action_state.count_orders_requiring_action(canonical))


class OrdersReaderJoinBoundaryTests(unittest.TestCase):
    def test_orders_readers_select_one_certificate_per_edition(self):
        for reader in (supabase_backend.list_hybrid_order_rows, supabase_backend.list_orders):
            source = inspect.getsource(reader)
            self.assertIn("LEFT JOIN LATERAL", source)
            self.assertIn("FROM certificates certificate", source)
            self.assertIn("certificate.updated_at DESC NULLS LAST", source)
            self.assertNotIn("LEFT JOIN certificates c ON", source)

    def test_known_line_never_falls_back_to_another_lines_allocations(self):
        source = inspect.getsource(supabase_backend.list_hybrid_order_rows)

        self.assertIn("if line_id:", source)
        self.assertIn('merged["assignments"] = assignments_by_line.get(line_id) or []', source)


if __name__ == "__main__":
    unittest.main()
