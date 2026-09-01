import inspect
from pathlib import Path
import unittest
from unittest import mock

import order_action_state
import order_allocator
import supabase_backend
import top_bar
import top_bar_api


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "components" / "sports_cave_top_bar" / "index.html"


def action_row(order_id, **overrides):
    row = {
        "shopify_order_id": order_id,
        "order_name": f"#SC{order_id}",
        "financial_status": "paid",
        "cancelled_at": "",
        "shopify_line_item_id": f"line-{order_id}",
        "line_quantity": 1,
        "assignments_count": 1,
        "edition_order_id": f"edition-{order_id}",
        "certificate_status": "Uploaded",
        "prodigi_status": "Complete",
    }
    row.update(overrides)
    return row


class OrderActionStateTests(unittest.TestCase):
    def test_mapping_rows_are_never_boolean_coerced(self):
        class AmbiguousRow(dict):
            def __bool__(self):
                raise ValueError("ambiguous mapping truth value")

        row = AmbiguousRow(action_row("0"))
        self.assertTrue(order_action_state.certificate_step_is_complete(row))
        self.assertTrue(order_action_state.fulfilment_step_is_complete(row))
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_one_unfinished_order_counts_once(self):
        rows = [action_row("1", prodigi_status="Needs certificate")]
        self.assertEqual(1, order_action_state.count_orders_requiring_action(rows))

    def test_fifteen_distinct_unfinished_orders_count_as_fifteen(self):
        rows = [
            action_row(str(index), prodigi_status="In production")
            for index in range(15)
        ]
        self.assertEqual(15, order_action_state.count_orders_requiring_action(rows))
        self.assertEqual("15", order_action_state.badge_label(15))

    def test_multi_line_order_is_counted_once(self):
        rows = [
            action_row("10", shopify_line_item_id="line-a"),
            action_row(
                "10",
                shopify_line_item_id="line-b",
                prodigi_status="Needs certificate",
            ),
        ]
        self.assertEqual(1, order_action_state.count_orders_requiring_action(rows))

    def test_one_incomplete_row_and_two_complete_rows_count_once(self):
        rows = [
            action_row("11", shopify_line_item_id="line-a"),
            action_row("11", shopify_line_item_id="line-b"),
            action_row(
                "11",
                shopify_line_item_id="line-c",
                prodigi_status="In production",
            ),
        ]
        self.assertEqual(1, order_action_state.count_orders_requiring_action(rows))

    def test_ready_certificate_with_unfinished_fulfilment_remains_counted(self):
        row = action_row(
            "20",
            certificate_status="Uploaded",
            prodigi_status="Submitted to Prodigi",
        )
        self.assertTrue(order_action_state.row_requires_action(row))

    def test_nonterminal_dispatch_is_not_overridden_by_order_fulfilment(self):
        row = action_row(
            "201",
            prodigi_status="In production",
            fulfillment_status="fulfilled",
        )
        self.assertTrue(order_action_state.row_requires_action(row))

    def test_terminal_sports_cave_fulfilment_preserves_legacy_completion(self):
        row = action_row(
            "21",
            certificate_status="Needs certificate",
            prodigi_status="Complete",
            assignments_count=0,
            edition_order_id="",
            certificate_pdf_url="",
            certificate_shopify_file_id="",
        )
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_historical_ready_certificate_and_terminal_fulfilment_stay_complete(self):
        row = action_row(
            "22",
            certificate_status="Ready",
            prodigi_status="Complete",
            fulfillment_status="unfulfilled",
        )

        self.assertTrue(order_action_state.certificate_step_is_complete(row))
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_historical_fulfilled_etsy_payload_stays_complete(self):
        row = action_row(
            "225",
            source_name="Etsy",
            certificate_status="Certificate Missing",
            prodigi_status="",
            fulfillment_status="",
            order_raw_json={"source_display": "Etsy", "fulfillment_status": "FULFILLED"},
        )

        self.assertEqual("FULFILLED", order_action_state.canonical_order_fulfilment_status(row))
        self.assertEqual("Complete", order_action_state.final_fulfilment_status(row))
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_terminal_marketplace_completion_overrides_shopify_unfulfilled(self):
        row = action_row(
            "226",
            source_name="Etsy",
            certificate_status="Ready",
            prodigi_status="",
            fulfillment_status="UNFULFILLED",
            order_raw_json={"marketplace_fulfilment_status": "Complete"},
        )

        self.assertEqual("Complete", order_action_state.canonical_order_fulfilment_status(row))
        self.assertEqual("Complete", order_action_state.final_fulfilment_status(row))
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_future_unfulfilled_etsy_order_remains_actionable(self):
        row = action_row(
            "227",
            source_name="Etsy",
            certificate_status="Certificate Missing",
            prodigi_status="",
            fulfillment_status="UNFULFILLED",
        )

        self.assertEqual("Needs certificate", order_action_state.final_fulfilment_status(row))
        self.assertTrue(order_action_state.row_requires_action(row))
        self.assertNotIn("etsy", inspect.getsource(order_action_state.final_fulfilment_status).casefold())

    def test_missing_certificate_precedes_nonterminal_dispatch_label(self):
        row = action_row(
            "228",
            certificate_status="Certificate Missing",
            prodigi_status="Not started",
            fulfillment_status="UNFULFILLED",
        )

        self.assertEqual("Needs certificate", order_action_state.final_fulfilment_status(row))
        self.assertTrue(order_action_state.row_requires_action(row))

    def test_shopify_fulfilled_is_terminal_only_without_conflicting_prodigi_state(self):
        completed = action_row("23", prodigi_status="", fulfillment_status="fulfilled")
        in_progress = action_row(
            "24",
            prodigi_status="In production",
            fulfillment_status="fulfilled",
        )

        self.assertFalse(order_action_state.row_requires_action(completed))
        self.assertTrue(order_action_state.row_requires_action(in_progress))

    def test_every_required_step_complete_removes_order(self):
        unfinished = action_row("30", prodigi_status="Needs certificate")
        completed = action_row(
            "30",
            certificate_status="Uploaded",
            prodigi_status="Fulfilled in Shopify",
        )
        self.assertEqual(1, order_action_state.count_orders_requiring_action([unfinished]))
        self.assertEqual(0, order_action_state.count_orders_requiring_action([completed]))
        self.assertEqual("", order_action_state.badge_label(0))

    def test_uploaded_certificate_and_complete_fulfilment_remove_order(self):
        row = action_row(
            "31",
            line_quantity=3,
            assignments_count=0,
            edition_order_id="",
            certificate_status="Uploaded",
            prodigi_status="Complete",
        )
        self.assertFalse(order_action_state.row_requires_action(row))

    def test_screenshot_state_counts_exactly_one_not_99_plus(self):
        rows = [
            action_row(
                "3000",
                order_name="#SC3000",
                prodigi_status="Needs certificate",
            )
        ]
        rows.extend(
            action_row(
                str(order_number),
                order_name=f"#SC{order_number}",
                prodigi_status="Complete",
                assignments_count=0,
                edition_order_id="",
                certificate_status="Ready",
            )
            for order_number in range(2800, 3000)
        )
        count = order_action_state.count_orders_requiring_action(rows)
        self.assertEqual(1, count)
        self.assertEqual("1", order_action_state.badge_label(count))

    def test_production_equivalent_marketplace_fixture_counts_only_sc3026(self):
        rows = [
            action_row(
                "gid://shopify/Order/7339668635955",
                order_name="#SC2989",
                shopify_line_item_id="gid://shopify/LineItem/17414822297907",
                certificate_status="Ready",
                prodigi_status="Complete",
                fulfillment_status="UNFULFILLED",
            ),
            action_row(
                "gid://shopify/Order/7341353337139",
                order_name="#SC2994",
                shopify_line_item_id="gid://shopify/LineItem/17418011476275",
                certificate_status="Ready",
                prodigi_status="Complete",
                fulfillment_status="PARTIALLY_FULFILLED",
            ),
            action_row(
                "gid://shopify/Order/7342818132275",
                order_name="#SC2998",
                source_name="2329312",
                shopify_line_item_id="gid://shopify/LineItem/17420335710515",
                certificate_status="Ready",
                prodigi_status="Complete",
                fulfillment_status="UNFULFILLED",
            ),
            action_row(
                "gid://shopify/Order/7358223745331",
                order_name="#SC3026",
                source_name="Online Store",
                shopify_line_item_id="gid://shopify/LineItem/17448334524723",
                certificate_status="Certificate Missing",
                prodigi_status="",
                fulfillment_status="UNFULFILLED",
            ),
        ]

        self.assertEqual(
            {"gid://shopify/Order/7358223745331"},
            {
                row["shopify_order_id"]
                for row in rows
                if order_action_state.row_requires_action(row)
            },
        )
        self.assertEqual(1, order_action_state.count_orders_requiring_action(rows))
        self.assertEqual("1", order_action_state.badge_label(1))

    def test_shared_final_status_matches_orders_fulfilment_labels(self):
        self.assertEqual(
            "Needs certificate",
            order_action_state.final_fulfilment_status(
                action_row("32", prodigi_status="Needs certificate")
            ),
        )
        self.assertEqual(
            "Complete",
            order_action_state.final_fulfilment_status(
                action_row(
                    "33",
                    prodigi_status="Complete",
                    certificate_status="Uploaded",
                    assignments_count=0,
                    edition_order_id="",
                )
            ),
        )

    def test_count_is_not_limited_to_latest_fifty_and_caps_badge_at_99_plus(self):
        rows = [
            action_row(str(index), prodigi_status="Not started")
            for index in range(120)
        ]
        self.assertEqual(120, order_action_state.count_orders_requiring_action(rows))
        self.assertEqual("99+", order_action_state.badge_label(120))

    def test_cancelled_or_unpaid_orders_do_not_count(self):
        rows = [
            action_row("40", financial_status="refunded", prodigi_status="Not started"),
            action_row("41", cancelled_at="2026-08-12T00:00:00Z", prodigi_status="Not started"),
        ]
        self.assertEqual(0, order_action_state.count_orders_requiring_action(rows))


class NewOrderEventTests(unittest.TestCase):
    def test_webhook_retry_cannot_clear_new_order_notification_flag(self):
        source = inspect.getsource(supabase_backend._update_webhook_event_status)

        self.assertIn("COALESCE(new_order_inserted, FALSE) OR %s", source)

    def event(self, webhook_id, order_id, *, inserted=True, at="2026-08-12T10:00:00Z"):
        return {
            "webhook_id": webhook_id,
            "shopify_order_id": order_id,
            "shopify_order_name": f"#SC{order_id}",
            "processed_at": at,
            "new_order_inserted": inserted,
        }

    def test_existing_history_is_not_announced_on_initial_baseline(self):
        events = [self.event("old-1", "3000", inserted=False)]
        selected, marker = order_action_state.select_new_order_events(events)
        self.assertEqual([], selected)
        self.assertEqual("", marker)

    def test_historical_completed_etsy_order_does_not_replay_a_notification(self):
        historical = self.event("etsy-history", "2985", inserted=False)
        historical["source_name"] = "Etsy"

        selected, marker = order_action_state.select_new_order_events([historical])

        self.assertEqual([], selected)
        self.assertEqual("", marker)

    def test_new_order_uses_stable_id_and_duplicate_events_collapse(self):
        events = [
            self.event("delivery-1", "3001"),
            self.event("delivery-2", "3001", at="2026-08-12T10:00:01Z"),
        ]
        selected, _marker = order_action_state.select_new_order_events(events)
        self.assertEqual(["3001"], [event["shopify_order_id"] for event in selected])
        replay, _marker = order_action_state.select_new_order_events(
            events,
            seen_order_ids={"3001"},
        )
        self.assertEqual([], replay)

    def test_single_and_batched_notification_copy(self):
        single = order_action_state.new_order_notification([self.event("one", "3001")])
        batch = order_action_state.new_order_notification(
            [self.event("one", "3001"), self.event("two", "3002")]
        )
        self.assertEqual("New order received — #SC3001", single["message"])
        self.assertEqual("2 new orders received", batch["message"])
        self.assertEqual(["3001", "3002"], batch["shopify_order_ids"])

    def test_sync_event_enqueue_is_idempotent_by_stable_order_id(self):
        inserted_ids = set()

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                self.returned = None
                if "INSERT INTO webhook_events" not in sql:
                    return
                event_id = params[0]
                if event_id not in inserted_ids:
                    inserted_ids.add(event_id)
                    self.returned = {"webhook_id": event_id}

            def fetchone(self):
                return self.returned

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                return None

        orders = [
            {"shopify_order_id": "gid://shopify/Order/3001", "order_name": "#SC3001"},
            {"shopify_order_id": "gid://shopify/Order/3002", "order_name": "#SC3002"},
        ]
        with mock.patch.object(supabase_backend, "connect", side_effect=lambda: Connection()):
            self.assertEqual(2, supabase_backend.record_new_order_notification_events(orders))
            self.assertEqual(0, supabase_backend.record_new_order_notification_events(orders))

    @mock.patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set())
    @mock.patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @mock.patch.object(supabase_backend, "sync_product_edition_metafields_for_handles", return_value={"synced": 0, "errors": []})
    @mock.patch.object(
        supabase_backend,
        "process_shopify_order_for_editions",
        return_value={
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "changed_handles": [],
            "new_assignment_ids": ["edition-3001"],
            "errors": [],
        },
    )
    def test_webhook_marks_only_a_new_stable_order_as_inserted(
        self,
        _process,
        _mirror,
        _line_ids,
        _order_ids,
    ):
        order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "order_name": "#SC3001",
            "financial_status": "PAID",
            "cancelled_at": "",
            "line_items": [
                {"shopify_line_item_id": "gid://shopify/LineItem/30011"}
            ],
        }
        result = supabase_backend.process_single_paid_shopify_order_for_editions(
            order,
            config={"configured": True},
            ensure_schema_first=False,
        )
        self.assertTrue(result["new_order_inserted"])

    @mock.patch.object(
        supabase_backend,
        "list_existing_shopify_order_ids",
        return_value={"gid://shopify/Order/3001"},
    )
    @mock.patch.object(supabase_backend, "list_existing_shopify_line_item_ids", return_value=set())
    @mock.patch.object(supabase_backend, "sync_product_edition_metafields_for_handles", return_value={"synced": 0, "errors": []})
    @mock.patch.object(
        supabase_backend,
        "process_shopify_order_for_editions",
        return_value={
            "assignments_created": 1,
            "existing_assignments_skipped": 0,
            "changed_handles": [],
            "new_assignment_ids": ["edition-3001"],
            "errors": [],
        },
    )
    def test_new_line_on_existing_order_does_not_announce_a_new_order(
        self,
        _process,
        _mirror,
        _line_ids,
        _order_ids,
    ):
        order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "order_name": "#SC3001",
            "financial_status": "PAID",
            "cancelled_at": "",
            "line_items": [
                {"shopify_line_item_id": "gid://shopify/LineItem/30012"}
            ],
        }
        result = supabase_backend.process_single_paid_shopify_order_for_editions(
            order,
            config={"configured": True},
            ensure_schema_first=False,
        )
        self.assertFalse(result["new_order_inserted"])


class OrderStatusUiContractTests(unittest.TestCase):
    def test_backend_selector_uses_shared_rules_and_has_no_latest_fifty_limit(self):
        summary_source = inspect.getsource(supabase_backend.get_order_action_summary)
        query_source = supabase_backend.ORDER_ACTION_ROWS_SQL
        self.assertIn("order_action_state.FULFILMENT_TERMINAL_STATUSES", summary_source)
        self.assertIn("COUNT(DISTINCT shopify_order_id)", summary_source)
        self.assertNotIn("LIMIT 50", query_source)
        self.assertIn("shopify_order_id", query_source)
        self.assertIn("prodigi_status", query_source)
        self.assertNotIn("edition_orders", query_source)
        self.assertNotIn("certificates", query_source)
        self.assertNotIn("certificates_complete", query_source)

    def test_badge_matches_numeric_and_gid_line_item_dispatch_identities(self):
        query_source = supabase_backend.ORDER_ACTION_ROWS_SQL

        self.assertIn("dispatch.shopify_line_item_id = ANY", query_source)
        self.assertIn("REGEXP_REPLACE", query_source)
        self.assertIn("gid://shopify/LineItem/", query_source)
        self.assertIn("o.raw_json->>'fulfillment_status'", query_source)
        self.assertIn("o.raw_json->>'marketplace_fulfilment_status'", query_source)
        self.assertIn("WHEN LOWER(BTRIM(COALESCE(dispatch.prodigi_status, '')))", query_source)
        self.assertIn("THEN 0 ELSE 1", query_source)

    def test_orders_readers_use_the_same_canonical_dispatch_identity(self):
        hybrid_source = inspect.getsource(supabase_backend.list_hybrid_order_rows)
        fallback_source = inspect.getsource(supabase_backend.list_orders)

        self.assertIn("pd.shopify_line_item_id = ANY", hybrid_source)
        self.assertIn("gid://shopify/LineItem/", hybrid_source)
        self.assertIn("o.raw_json->>'fulfillment_status'", hybrid_source)
        self.assertIn("o.raw_json->>'marketplace_fulfilment_status'", hybrid_source)
        self.assertIn("WHEN LOWER(BTRIM(COALESCE(pd.prodigi_status, '')))", hybrid_source)
        self.assertIn("pd.shopify_line_item_id = ANY", fallback_source)
        self.assertIn("gid://shopify/LineItem/", fallback_source)
        self.assertIn("o.raw_json->>'fulfillment_status'", fallback_source)
        self.assertIn("o.raw_json->>'marketplace_fulfilment_status'", fallback_source)
        self.assertIn("WHEN LOWER(BTRIM(COALESCE(pd.prodigi_status, '')))", fallback_source)

    def test_orders_page_reuses_shared_certificate_and_fulfilment_helpers(self):
        source = (ROOT / "orders_page.py").read_text(encoding="utf-8")
        self.assertIn("order_action_state.final_fulfilment_status", source)

    def test_top_bar_status_is_permission_scoped(self):
        with mock.patch.object(top_bar_api, "order_action_state"):
            result = top_bar_api.load_order_status({"sub": "worker", "allowed_routes": ["Dashboard"]})
        self.assertEqual(0, result["action_required_count"])
        self.assertEqual({}, result["notification"])

    def test_status_loader_combines_real_count_and_new_order_event(self):
        event = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "shopify_order_name": "#SC3001",
            "new_order_inserted": True,
        }
        with mock.patch.object(supabase_backend, "is_configured", return_value=True), mock.patch.object(
            supabase_backend,
            "get_order_action_summary",
            return_value={"action_required_count": 1, "badge_label": "1"},
        ), mock.patch.object(
            supabase_backend,
            "consume_new_order_notifications",
            return_value=[event],
        ):
            result = top_bar_api.load_order_status(
                {"sub": "admin", "allowed_routes": ["Orders"]}
            )
        self.assertEqual(1, result["action_required_count"])
        self.assertEqual("New order received — #SC3001", result["notification"]["message"])

    def test_status_loader_returns_one_for_screenshot_fulfilment_state(self):
        rows = [action_row("3000", prodigi_status="Needs certificate")]
        rows.extend(
            action_row(
                str(order_number),
                prodigi_status="Complete",
                assignments_count=0,
                edition_order_id="",
                certificate_status="Uploaded",
            )
            for order_number in range(2800, 3000)
        )
        with mock.patch.object(supabase_backend, "is_configured", return_value=False), mock.patch.object(
            order_allocator,
            "load_orders_snapshot",
            return_value={"rows": rows},
        ):
            result = top_bar_api.load_order_status(
                {"sub": "admin", "allowed_routes": ["Orders"]}
            )
        self.assertEqual(1, result["action_required_count"])
        self.assertEqual("1", result["badge_label"])
        self.assertEqual({}, result["notification"])

    def test_notification_cursor_failure_does_not_discard_badge_count(self):
        with mock.patch.object(supabase_backend, "is_configured", return_value=True), mock.patch.object(
            supabase_backend,
            "get_order_action_summary",
            return_value={"action_required_count": 15, "badge_label": "15"},
        ), mock.patch.object(
            supabase_backend,
            "consume_new_order_notifications",
            side_effect=RuntimeError("cursor temporarily unavailable"),
        ):
            result = top_bar_api.load_order_status(
                {"sub": "admin", "allowed_routes": ["Orders"]}
            )
        self.assertEqual(15, result["action_required_count"])
        self.assertEqual({}, result["notification"])

    def test_top_bar_component_has_lightweight_badge_and_single_managed_toast(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")
        self.assertIn("sc-orders-action-badge", source)
        self.assertIn("right: 12px", source)
        self.assertIn("refreshOrderStatus", source)
        self.assertIn("later(refreshOrderStatus, 30000)", source)
        self.assertIn("TEMPORARY_TOAST_MS = 3000", source)
        self.assertIn("SportsCaveTemporaryToastRuntime", source)
        self.assertIn("current.identity === cleanIdentity", source)
        self.assertIn("current.expiresAt > now", source)
        self.assertIn('button.setAttribute("aria-label", "Orders")', source)
        self.assertNotIn("state.orderToastTimer = later", source)
        self.assertIn('temporaryToasts.show("orders"', source)
        self.assertIn('appendToastClose(toast, "orders", identity)', source)
        self.assertIn("shopify_order_ids.map(String).filter(Boolean)", source)
        self.assertIn("[...new Set(orderIds)].sort().join(\",\")", source)
        self.assertEqual(1, source.count('id="sc-os-order-toast-region"'))
        self.assertNotIn("st.rerun", source)

    def test_top_bar_config_exposes_one_same_origin_status_endpoint(self):
        config = top_bar.top_bar_config(
            {"id": "admin", "role": "admin", "is_active": True, "page_permissions": []},
            logo_src="logo",
            current_route="Dashboard",
        )
        self.assertEqual("/api/os/top-bar/order-status", config["orderStatusUrl"])
        self.assertEqual("/api/os/top-bar/daily-planner-status", config["dailyPlannerStatusUrl"])
        self.assertTrue(config["ordersEnabled"])
        self.assertTrue(config["dailyPlannerEnabled"])
        self.assertEqual(1, [path for path, *_rest in top_bar_api.TOP_BAR_ROUTE_HANDLERS].count(config["orderStatusUrl"]))
        self.assertEqual(1, [path for path, *_rest in top_bar_api.TOP_BAR_ROUTE_HANDLERS].count(config["dailyPlannerStatusUrl"]))


if __name__ == "__main__":
    unittest.main()
