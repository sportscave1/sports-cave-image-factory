import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import orders_page
import seo_workspace
import supabase_backend
import top_bar_api


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, *, one=None, rows=None):
        self.one = one or {}
        self.rows = list(rows or [])
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.queries.append((str(query), params))

    def fetchone(self):
        return dict(self.one)

    def fetchall(self):
        return [dict(row) for row in self.rows]


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


class SupabaseEgressQuickWinTests(unittest.TestCase):
    def tearDown(self):
        top_bar_api.clear_order_summary_display_cache()

    def test_top_bar_order_summary_cache_reuses_then_expires(self):
        backend = Mock()
        backend.get_order_action_summary.side_effect = (
            {"action_required_count": 4, "badge_label": "4"},
            {"action_required_count": 5, "badge_label": "5"},
        )
        top_bar_api.clear_order_summary_display_cache()

        first = top_bar_api._cached_order_action_summary(backend, now=100.0)
        first["action_required_count"] = 999
        second = top_bar_api._cached_order_action_summary(backend, now=129.9)
        fresh = top_bar_api._cached_order_action_summary(backend, now=130.0)

        self.assertEqual(second, {"action_required_count": 4, "badge_label": "4"})
        self.assertEqual(fresh, {"action_required_count": 5, "badge_label": "5"})
        self.assertEqual(backend.get_order_action_summary.call_count, 2)

    def test_top_bar_cache_only_covers_display_summary_not_notification_cursor(self):
        top_bar_api.clear_order_summary_display_cache()
        claims = {"allowed_routes": ["Orders"], "sub": "user-1"}
        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend,
            "get_order_action_summary",
            return_value={"action_required_count": 2, "badge_label": "2"},
        ) as summary_read, patch.object(
            supabase_backend,
            "consume_new_order_notifications",
            return_value=[],
        ) as notification_read:
            first = top_bar_api.load_order_status(claims)
            second = top_bar_api.load_order_status(claims)

        self.assertEqual(first, second)
        summary_read.assert_called_once_with()
        self.assertEqual(notification_read.call_count, 2)

    def test_top_bar_polling_and_orders_visibility_polling_are_bounded(self):
        component = (
            ROOT / "components" / "sports_cave_top_bar" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertEqual(orders_page.ORDERS_SUPABASE_LIVE_CHECK_SECONDS, 30)
        self.assertIn("const ORDER_STATUS_REFRESH_MS = 60000;", component)
        self.assertIn("const PLANNER_STATUS_REFRESH_MS = 30000;", component)
        self.assertIn("later(refreshOrderStatus, ORDER_STATUS_REFRESH_MS)", component)

    def test_notification_read_selects_only_fields_the_top_bar_consumes(self):
        cursor = _Cursor(
            one={"table_name": "audit_logs"},
            rows=[
                {
                    "event_type": "task_completed",
                    "entity_type": "task",
                    "entity_id": "task-1",
                    "source": "sports_cave_os",
                    "created_at": "2026-09-03T00:00:00Z",
                    "new_value": {"message": "Task completed"},
                }
            ],
        )
        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend,
            "connect",
            return_value=_Connection(cursor),
        ):
            rows, alerts = top_bar_api.load_notification_sources({})

        query = cursor.queries[-1][0]
        self.assertNotIn("to_jsonb(activity)", query)
        for field in ("event_type", "entity_type", "entity_id", "source", "created_at", "new_value"):
            self.assertIn(field, query)
        self.assertEqual(rows[0]["new_value"]["message"], "Task completed")
        self.assertEqual(alerts, [])

    def test_meta_insight_projection_excludes_only_unused_raw_json(self):
        columns = supabase_backend._ads_insight_read_columns(
            "i", ("publisher_platform", "platform_position")
        )

        self.assertNotIn("i.raw", columns)
        for column in (
            "i.id",
            "i.date",
            "i.spend",
            "i.purchases",
            "i.purchase_value",
            "i.publisher_platform",
            "i.platform_position",
            "i.synced_at",
            "i.created_at",
            "i.updated_at",
        ):
            self.assertIn(column, columns)

    def test_product_opportunities_reuse_mapping_rows_from_same_render(self):
        mapping_rows = [
            {
                "mapping_status": "confirmed",
                "product_handle": "peter-brock",
                "product_title": "Peter Brock",
                "spend": 12,
                "purchases": 1,
                "purchase_value": 100,
                "clicks": 10,
                "impressions": 1000,
            }
        ]
        with patch.object(
            supabase_backend,
            "list_ads_product_mapping_status",
            side_effect=AssertionError("mapping query must be reused"),
        ), patch.object(
            supabase_backend, "list_recent_product_sales_by_handle", return_value=[]
        ), patch.object(
            supabase_backend, "list_product_edition_summary", return_value=[]
        ):
            opportunities = supabase_backend.list_product_opportunities_from_ads(
                date_range="last_30_days",
                ad_rows=mapping_rows,
            )

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["product_handle"], "peter-brock")
        self.assertEqual(opportunities[0]["meta_spend"], 12.0)

    def test_ads_mapping_cte_no_longer_materialises_unused_raw_json(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        start = source.index("def list_ads_product_mapping_status")
        end = source.index("def suggest_ads_product_mappings", start)
        function_source = source[start:end]

        self.assertNotIn("SELECT *\n            FROM meta_ad_insights_daily", function_source)
        self.assertGreaterEqual(
            function_source.count(
                "SELECT ad_id, ad_name, campaign_name, adset_name,"
            ),
            2,
        )

    def test_seo_workspace_cache_reads_once_within_ttl_and_refreshes_after_expiry(self):
        clock = {"now": 100.0}
        source_state = seo_workspace.default_state()
        source_state["settings"]["data_migrations"][
            seo_workspace.LEGACY_CITATION_IMPORT_VERSION
        ] = {"completed": True}
        cursor = _Cursor(one={"payload": copy.deepcopy(source_state)})

        class Backend:
            def connect(self):
                return _Connection(cursor)

        store = seo_workspace.PostgresSEOStore(backend=Backend())
        store._schema_ready = True
        with patch.object(
            seo_workspace.time,
            "monotonic",
            side_effect=lambda: clock["now"],
        ):
            first = store.load()
            clock["now"] = 129.9
            second = store.load()
            clock["now"] = 130.0
            third = store.load()

        select_queries = [query for query, _params in cursor.queries if "SELECT payload" in query]
        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(len(select_queries), 2)
        self.assertEqual(seo_workspace.SEO_STORE_CACHE_SECONDS, 30.0)


if __name__ == "__main__":
    unittest.main()
