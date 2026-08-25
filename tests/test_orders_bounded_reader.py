import time
import unittest
from unittest.mock import patch

import order_allocator
import supabase_backend


class ProductionCardinalityDatabase:
    """SQL-aware read fake whose response size is independent of table size."""

    def __init__(self, order_count=100_000, lines_per_order=2):
        self.order_count = order_count
        self.lines_per_order = lines_per_order
        self.statements = []
        self.connections = []

    def connect(self):
        connection = self.Connection(self)
        self.connections.append(connection)
        return connection

    class Connection:
        def __init__(self, database):
            self.database = database
            self.closed = False
            self.rollback_calls = 0

        def cursor(self):
            return ProductionCardinalityDatabase.Cursor(self.database)

        def rollback(self):
            self.rollback_calls += 1

        def close(self):
            self.closed = True

    class Cursor:
        def __init__(self, database):
            self.database = database
            self.sql = ""
            self.params = ()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            self.sql = str(sql)
            self.params = tuple(params or ())
            self.database.statements.append((self.sql, self.params))

        def fetchall(self):
            if "SELECT o.shopify_order_id" in self.sql and "FROM shopify_orders o" in self.sql:
                requested = int(self.params[-1])
                return [
                    {"shopify_order_id": f"gid://shopify/Order/{self.database.order_count - offset}"}
                    for offset in range(requested)
                ]
            if "FROM shopify_orders o" in self.sql and "LEFT JOIN shopify_order_lines li" in self.sql:
                rows = []
                for order_offset, order_gid in enumerate(self.params[0]):
                    number = self.database.order_count - order_offset
                    for line_offset in range(self.database.lines_per_order):
                        line_number = number * 10 + line_offset
                        order_name = f"#SC{number}"
                        title = "Fixture Wall Art"
                        edition = (order_offset * self.database.lines_per_order + line_offset) % 100 + 1
                        if order_offset == 0 and line_offset == 0:
                            order_name, title, edition = "#SC3058", "Muhammad Ali Live Like a Champion Wall Art", 76
                        elif order_offset == 1 and line_offset == 0:
                            order_name, title, edition = "#SC3056", "Shane Warne Tribute Wall Art", 9
                        elif order_offset == 2 and line_offset == 0:
                            order_name, title, edition = "#SC3055", "Shane Warne Tribute Wall Art", 8
                        rows.append(
                            {
                                "shopify_order_id": order_gid,
                                "order_name": order_name,
                                "shopify_line_item_id": f"gid://shopify/LineItem/{line_number}",
                                "order_line_id": line_number,
                                "product_title": title,
                                "variant_title": "Black / XL",
                                "quantity": 1,
                                "source_name": "eBay Australia" if order_offset == 0 else (
                                    "Etsy" if order_offset == 3 else "Online Store"
                                ),
                                "fulfillment_status": "",
                                "assignment_status": "Assigned",
                                "_fixture_edition": edition,
                            }
                        )
                return rows
            if "FROM prodigi_dispatch_rows" in self.sql:
                return [
                    {
                        "row_id": f"dispatch-{line_id}",
                        "shopify_line_item_id": line_id,
                        "prodigi_status": "Complete" if index % 3 == 0 else "",
                    }
                    for index, line_id in enumerate(self.params[0])
                ]
            if "WITH selected_edition_ids AS" in self.sql:
                return [
                    {
                        "edition_order_id": f"edition-{line_id.rsplit('/', 1)[-1]}",
                        "shopify_line_item_id": line_id,
                        "edition_number": (
                            76 if line_id.endswith("0") and line_id.startswith("gid://shopify/LineItem/3058")
                            else 9 if line_id.endswith("0") and line_id.startswith("gid://shopify/LineItem/3057")
                            else 8 if line_id.endswith("0") and line_id.startswith("gid://shopify/LineItem/3056")
                            else index % 100 + 1
                        ),
                        "edition_total": 100,
                        "allocation_index": 1,
                    }
                    for index, line_id in enumerate(self.params[0])
                    if line_id.startswith("gid://shopify/LineItem/")
                ]
            if "FROM order_line_edition_overrides" in self.sql:
                return []
            return []

        def fetchone(self):
            if "WITH latest_orders AS" in self.sql:
                return {"order_count": 0, "latest_order_update": None}
            return None


class OrdersBoundedReaderRegressionTests(unittest.TestCase):
    def setUp(self):
        self.original_override_capability = supabase_backend._ORDER_OVERRIDE_READ_CAPABILITY
        supabase_backend._ORDER_OVERRIDE_READ_CAPABILITY = False

    def tearDown(self):
        supabase_backend._ORDER_OVERRIDE_READ_CAPABILITY = self.original_override_capability

    def _load(self, order_count=100_000):
        database = ProductionCardinalityDatabase(order_count=order_count)
        started = time.perf_counter()
        with patch.object(supabase_backend, "connect", side_effect=database.connect):
            rows = supabase_backend.list_hybrid_order_rows(limit=50)
        return database, rows, (time.perf_counter() - started) * 1000

    def test_latest_window_is_selected_before_every_enrichment(self):
        database, rows, _elapsed_ms = self._load()

        self.assertEqual(100, len(rows))
        self.assertEqual(4, len(database.statements))
        id_sql, id_params = database.statements[0]
        self.assertIn("SELECT o.shopify_order_id", id_sql)
        self.assertIn("ORDER BY o.created_at DESC", id_sql)
        self.assertIn("LIMIT %s", id_sql)
        self.assertEqual(50, id_params[-1])
        for expanded_table in (
            "shopify_order_lines",
            "edition_orders",
            "certificates",
            "prodigi_dispatch_rows",
        ):
            self.assertNotIn(expanded_table, id_sql)
        self.assertIn("WHERE o.shopify_order_id=ANY", database.statements[1][0])
        self.assertIn("WHERE shopify_line_item_id=ANY", database.statements[2][0])
        self.assertIn("WITH selected_edition_ids AS", database.statements[3][0])
        self.assertTrue(all(connection.closed for connection in database.connections))
        self.assertTrue(all(connection.rollback_calls == 1 for connection in database.connections))

    def test_query_count_and_output_are_constant_as_history_grows(self):
        small_db, small_rows, _ = self._load(order_count=1_000)
        large_db, large_rows, _ = self._load(order_count=1_000_000)

        self.assertEqual(len(small_db.statements), len(large_db.statements))
        self.assertEqual(4, len(large_db.statements))
        self.assertEqual(100, len(small_rows))
        self.assertEqual(100, len(large_rows))
        self.assertEqual(50, len({row["shopify_order_id"] for row in large_rows}))
        self.assertEqual(100, len({row["shopify_line_item_id"] for row in large_rows}))

    def test_multi_line_rows_keep_channel_psd_certificate_and_fulfilment_inputs(self):
        _database, rows, _ = self._load()
        snapshot_rows = order_allocator._snapshot_rows_from_supabase_order_rows(rows)

        self.assertEqual(100, len(snapshot_rows))
        row_identities = {
            (row["shopify_order_id"], row["shopify_line_item_id"], row["allocation_index"])
            for row in snapshot_rows
        }
        self.assertEqual(100, len(row_identities))
        channels = {row.get("source_name") for row in rows}
        self.assertTrue({"Online Store", "Etsy", "eBay Australia"}.issubset(channels))
        self.assertTrue(any(row.get("prodigi_status") == "Complete" for row in rows))
        self.assertTrue(all("assignments" in row for row in rows))

    def test_real_incident_regression_fixtures_remain_product_specific(self):
        _database, rows, _ = self._load(order_count=3058)
        snapshot_rows = order_allocator._snapshot_rows_from_supabase_order_rows(rows)

        by_order = {}
        for row in snapshot_rows:
            by_order.setdefault(row.get("order"), []).append(row)
        ali = next(row for row in by_order["#SC3058"] if row["product"].startswith("Muhammad Ali"))
        shane_3056 = next(row for row in by_order["#SC3056"] if row["product"].startswith("Shane Warne"))
        shane_3055 = next(row for row in by_order["#SC3055"] if row["product"].startswith("Shane Warne"))
        self.assertEqual(76, ali["edition_number"])
        self.assertEqual(9, shane_3056["edition_number"])
        self.assertEqual(8, shane_3055["edition_number"])

    def test_production_cardinality_reader_benchmark_stays_bounded(self):
        _cold_db, _cold_rows, cold_ms = self._load(order_count=1_000_000)
        _warm_db, _warm_rows, warm_ms = self._load(order_count=1_000_000)

        # This benchmark measures reader orchestration/merge cost, not a live
        # Supabase network round trip. It catches cardinality-dependent Python
        # or N+1 regressions deterministically.
        self.assertLess(cold_ms, 500)
        self.assertLess(warm_ms, 500)

    def test_visibility_marker_is_also_limited_before_aggregation(self):
        database = ProductionCardinalityDatabase()
        with patch.object(supabase_backend, "connect", side_effect=database.connect):
            marker = supabase_backend.orders_visibility_marker(ensure_schema_first=False)

        self.assertIn("WITH latest_orders AS", database.statements[0][0])
        self.assertIn("LIMIT 50", database.statements[0][0])
        self.assertNotIn("FROM shopify_order_lines", database.statements[0][0])
        self.assertEqual("0|", marker["marker"])

    def test_optional_override_schema_is_absent_safe_and_present_bounded(self):
        absent_db, absent_rows, _ = self._load()
        self.assertEqual(100, len(absent_rows))
        self.assertFalse(any("order_line_edition_overrides" in sql for sql, _ in absent_db.statements))

        supabase_backend._ORDER_OVERRIDE_READ_CAPABILITY = True
        present_db, present_rows, _ = self._load()
        self.assertEqual(100, len(present_rows))
        self.assertEqual(5, len(present_db.statements))
        override_sql, override_params = present_db.statements[-1]
        self.assertIn("FROM order_line_edition_overrides", override_sql)
        self.assertIn("WHERE mo.shopify_line_item_gid=ANY", override_sql)
        self.assertLessEqual(len(override_params[0]), 100)


if __name__ == "__main__":
    unittest.main()
