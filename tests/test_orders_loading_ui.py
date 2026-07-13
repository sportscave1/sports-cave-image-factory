import inspect
import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import edition_ops
import order_allocator
import os_pages
import orders_page
import shopify_sync
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]


class EditionOpsUiTests(unittest.TestCase):
    def test_app_routes_to_edition_ops_not_old_orders_or_limited_pages(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Edition Ops"', source)
        self.assertIn('"Orders"', source)
        self.assertIn("get_edition_ops().render_page()", source)
        self.assertIn("get_orders_page().render_page()", source)
        self.assertNotIn('"Certificates"', source)
        self.assertNotIn("get_certificates_page", source)
        self.assertNotIn("certificates_page", source)
        self.assertNotIn('"Limited Editions",', source)
        self.assertNotIn("render_limited_editions_page", source)
        self.assertNotIn("render_edition_orders_page", source)
        self.assertNotIn("render_edition_integrity_check_page", source)
        self.assertIn('current_page in {"Dashboard", "Products", "Edition Ops", "Orders", "Developer", "Settings"}', source)
        self.assertIn("DEVELOPER_PAGE_PASSWORD", source)
        self.assertIn("developer_unlocked", source)

    def test_edition_ops_uses_one_editor_and_no_old_data_sources(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")
        render_source = inspect.getsource(edition_ops.render_page)

        self.assertIn("st.data_editor", source)
        self.assertIn("edition_ops_products_snapshot.json", source)
        self.assertIn("_load_supabase_snapshot", source)
        self.assertIn("backend.list_edition_products", source)
        self.assertIn("backend.update_edition_product", source)
        self.assertIn("Save Changes", source)
        self.assertIn("_render_advanced_controls", render_source)
        self.assertIn("backend.sync_new_shopify_products_to_edition_ops", source)
        self.assertNotIn("backend.sync_shopify_products_to_supabase", render_source)
        self.assertNotIn("Save Changed Rows", render_source)
        self.assertNotIn("Push Metafield", render_source)
        self.assertIn("Export CSV Backup", source)
        self.assertIn("Import CSV and Replace Table", source)
        self.assertIn("edition_sold_count", source)
        self.assertIn("edition_remaining", source)
        self.assertIn("edition_status", source)
        self.assertIn("_rows_to_save", source)
        self.assertIn("_hydrate_from_snapshot_once()", source)
        self.assertIn("_write_snapshot", source)
        self.assertNotIn("edition_ops_orders_snapshot.json", source)
        self.assertNotIn("Refresh Orders", source)
        self.assertNotIn("Refresh Products From Shopify", source)
        self.assertNotIn("shipping_method", source)
        self.assertNotIn("certificate_display", source)
        self.assertNotIn("default_paid_unfulfilled_filter=False", source)
        self.assertNotIn("_hydrate_orders_snapshot_once", source)
        self.assertNotIn("_render_orders_table", source)
        self.assertNotIn("Clear Table", source)
        self.assertNotIn("Refresh Unfulfilled Orders", source)
        self.assertNotIn("Open Shopify Orders", source)
        self.assertNotIn("Shopify is the permanent record", source)
        self.assertNotIn("Shopify Metafield Setup", source)
        self.assertNotIn("Check Metafield Definitions", source)
        self.assertNotIn("Create Missing Metafield Definitions", source)
        self.assertNotIn("import google", source.casefold())
        self.assertNotIn("fetch_orders", source)

    def test_developer_keeps_edition_ops_metafield_setup(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Edition Ops Diagnostics"', source)
        self.assertIn("Load Edition Ops Diagnostics", source)
        self.assertIn('"Shopify Limited Edition Setup"', source)
        self.assertIn("Check Product Metafield Definitions", source)
        self.assertIn("Create Missing Product Metafield Definitions", source)
        self.assertIn('"Order Metafield Setup"', source)
        self.assertIn("Check Order Metafield Definition", source)
        self.assertIn("Create Missing Order Metafield Definition", source)
        self.assertIn('"Allocation Repair Tools"', source)
        self.assertIn("View allocation settings", source)
        self.assertIn("Re-capture product baselines", source)
        self.assertIn("Allocate Missing Recent Paid Orders", source)
        self.assertIn("Historical Backfill Selected Orders", source)
        self.assertIn("process_shopify_orders_for_editions", source)
        self.assertIn("historical_backfill_order_rows", source)

    def test_developer_lazy_loaders_do_not_reuse_widget_keys_as_state(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        helper = source[
            source.index("def _developer_section_enabled") : source.index("\n\ndef _developer_section_error")
        ]

        self.assertIn('state_key = f"{key}-enabled"', helper)
        self.assertIn('button_key = f"{key}-button"', helper)
        self.assertIn("st.session_state[state_key] = True", helper)
        self.assertNotIn("key=key", helper)
        self.assertNotIn("st.session_state[key] = True", helper)
        self.assertIn("def _developer_section_error", source)
        self.assertIn("def _developer_action_error", source)
        self.assertIn("The rest of Developer is still available", source)

    def test_developer_allocation_repair_uses_utc_datetime_sorting(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        helper = source[
            source.index("def _historical_backfill_candidates") : source.index("\n\ndef _mark_orders_snapshot_for_reload")
        ]

        self.assertIn("allocator.normalize_datetime_utc", helper)
        self.assertNotIn("datetime.fromisoformat", helper)
        self.assertNotIn("datetime.min", helper)

    def test_prodigi_dispatch_page_is_search_first_and_lightweight(self):
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")
        prodigi_page = source[
            source.index("def render_prodigi_page():") : source.index("\n\ndef fetch_latest_shopify_products")
        ]

        self.assertIn("Prodigi Dispatch Log", prodigi_page)
        self.assertIn("Search an order, confirm the Prodigi checks, then save it to the dispatch log.", prodigi_page)
        self.assertIn("Open Prodigi Dashboard", prodigi_page)
        self.assertIn("Prodigi Reference", prodigi_page)
        self.assertIn("prodigi_reference_table_html", prodigi_page)
        self.assertIn("Enter Shopify Order #", prodigi_page)
        self.assertIn('placeholder="#"', prodigi_page)
        self.assertNotIn('placeholder="#SC2843"', prodigi_page)
        self.assertIn("Find Order", prodigi_page)
        self.assertIn("Order lines found", source)
        self.assertIn("_prodigi_order_line_table(matches, existing_dispatch_rows, selected_id)", prodigi_page)
        self.assertIn("_prodigi_selected_line_summary(selected_row)", prodigi_page)
        self.assertIn("QA checklist", prodigi_page)
        self.assertIn("Prodigi product/variant", prodigi_page)
        self.assertIn("Does the Prodigi product/variant exactly match", prodigi_page)
        self.assertIn("Artwork upload quality", prodigi_page)
        self.assertIn("Has the final artwork been uploaded to Prodigi in excellent print quality?", prodigi_page)
        self.assertIn("Artwork crop / orientation", prodigi_page)
        self.assertIn("Is the artwork crop, orientation, and full image preview correct?", prodigi_page)
        self.assertIn("Frame colour", prodigi_page)
        self.assertIn("Does the Prodigi size match the Shopify size", prodigi_page)
        self.assertIn("Is shipping set correctly to", prodigi_page)
        self.assertIn("Final error check", prodigi_page)
        self.assertIn("Save Issue", prodigi_page)
        self.assertIn("Generate + Upload Certificate", prodigi_page)
        self.assertIn("certificate_result = prodigi_generate_upload_certificate_for_row(completion_row)", prodigi_page)
        self.assertIn('status="Complete"', prodigi_page)
        self.assertIn("Submitted Dispatch Log", prodigi_page)
        self.assertIn("Last 7 Days", prodigi_page)
        self.assertNotIn("Copy Prodigi Details", prodigi_page)
        self.assertNotIn("Order Summary", prodigi_page)
        self.assertNotIn("Select Artwork Line", prodigi_page)
        self.assertNotIn("Prodigi Product Confirmation", prodigi_page)
        self.assertNotIn("Prodigi Details", prodigi_page)
        self.assertNotIn("Dispatch QA", prodigi_page)
        self.assertIn("Order not found. Sync New Orders first, then try again.", prodigi_page)
        self.assertIn("Already submitted on", prodigi_page)
        self.assertIn("Last tracker save", prodigi_page)
        self.assertIn("Dispatch rows saved", prodigi_page)
        self.assertIn("prodigi_find_order_rows_from_cache", prodigi_page)
        self.assertIn("prodigi_load_dispatch_rows", prodigi_page)
        self.assertIn("Expected Prodigi code", source)
        self.assertNotIn("Copy Prodigi Variant", prodigi_page)
        self.assertIn("Prodigi Shopify fetch skipped on initial load", prodigi_page)
        self.assertIn("Prodigi full order snapshot skipped on initial load", prodigi_page)
        self.assertNotIn("order_allocator.load_orders_snapshot()", prodigi_page)
        self.assertNotIn("orders_snapshot = order_allocator.load_orders_snapshot()", prodigi_page)
        self.assertNotIn("Prodigi size:", prodigi_page)
        self.assertNotIn("Ready to Send", prodigi_page)
        self.assertNotIn("Active Rows", prodigi_page)
        self.assertNotIn("Open Checklist", prodigi_page)
        self.assertNotIn("progress_text", prodigi_page)
        self.assertNotIn("Export Selected CSV", prodigi_page)
        self.assertNotIn("st.data_editor", prodigi_page)
        self.assertIn('PRODIGI_SUPPORT_EMAIL = "pro@prodigi.com"', source)
        self.assertNotIn("support@prodigi.com", source)

    def test_prodigi_page_load_is_lazy_and_does_not_sync_or_load_all_orders(self):
        class FakeContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeColumn:
            def button(self, *args, **kwargs):
                return False

            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

            def write(self, *args, **kwargs):
                return None

            def markdown(self, *args, **kwargs):
                return None

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {}
                self.dataframes = []

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def link_button(self, *args, **kwargs):
                return None

            def expander(self, *args, **kwargs):
                return FakeContext()

            def markdown(self, *args, **kwargs):
                return None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def text_input(self, *args, **kwargs):
                return ""

            def radio(self, *args, **kwargs):
                options = args[1] if len(args) > 1 else kwargs.get("options", [])
                return options[0] if options else ""

            def divider(self):
                return None

            def subheader(self, *args, **kwargs):
                return None

            def dataframe(self, rows, **kwargs):
                self.dataframes.append(rows)

            def info(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def error(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        with patch.object(os_pages, "st", fake_st), patch.object(
            os_pages.supabase_backend,
            "is_configured",
            return_value=True,
        ), patch.object(
            os_pages.supabase_backend,
            "list_prodigi_dispatch_rows",
            return_value=[],
        ) as list_dispatch, patch.object(
            os_pages.supabase_backend,
            "get_prodigi_dispatch_summary",
            side_effect=AssertionError("Prodigi page load should not run a dispatch summary count."),
        ), patch.object(
            os_pages.supabase_backend,
            "sync_latest_paid_orders_to_supabase",
            side_effect=AssertionError("Prodigi page load must not sync orders."),
        ), patch.object(
            os_pages.supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Prodigi page load must not run schema DDL."),
        ), patch.object(
            os_pages.shopify_sync,
            "iter_order_pages",
            side_effect=AssertionError("Prodigi page load must not call Shopify orders."),
        ), patch.object(
            os_pages.shopify_sync,
            "fetch_latest_paid_orders",
            side_effect=AssertionError("Prodigi page load must not call Shopify latest-paid fetch."),
        ), patch.object(
            order_allocator,
            "load_orders_snapshot",
            side_effect=AssertionError("Prodigi page load must not load the full Orders snapshot."),
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Prodigi page load must not reload Orders."),
        ), patch.object(
            os_pages,
            "prodigi_generate_upload_certificate_for_row",
            side_effect=AssertionError("Prodigi page load must not generate certificates."),
        ):
            os_pages.render_prodigi_page()

        list_dispatch.assert_called_once()
        self.assertEqual(list_dispatch.call_args.kwargs["limit"], 50)

    def test_orders_page_has_copy_order_number_button(self):
        source = (ROOT / "orders_page.py").read_text(encoding="utf-8")
        render_table = inspect.getsource(orders_page._render_orders_table)
        display_rows = orders_page._display_rows([{"order": "#SC2858"}])
        copy_handler_html = orders_page._order_copy_click_handler_html()

        self.assertEqual(display_rows[0]["order"], f"{orders_page.COPY_ORDER_ICON} #SC2858")
        self.assertNotIn("order_copy", orders_page.VISIBLE_COLUMNS)
        self.assertNotIn("copy_order", orders_page.VISIBLE_COLUMNS)
        self.assertEqual(display_rows[0]["order"].count("#SC2858"), 1)
        self.assertEqual(display_rows[0]["order"].count(orders_page.COPY_ORDER_ICON), 1)
        self.assertNotIn("_render_order_copy_buttons", source)
        self.assertNotIn("_render_order_copy_overlay", source)
        self.assertNotIn("_render_inline_orders_table", source)
        self.assertNotIn("sports-cave-orders-copy-overlay", source)
        self.assertNotIn("copy-order-row", source)
        self.assertNotIn("ROW_SELECT_KEY_PREFIX", source)
        self.assertNotIn("Copy order</span>", source)
        self.assertIn("st.dataframe", render_table)
        self.assertIn("selection_mode=\"multi-row\"", render_table)
        self.assertIn("components.html", source)
        self.assertIn("_render_order_copy_click_handler()", render_table)
        self.assertIn("parentWindow.navigator", copy_handler_html)
        self.assertIn("clipboard.writeText(value)", copy_handler_html)
        self.assertIn("Copy order number", copy_handler_html)

    def test_orders_inline_copy_cells_are_one_per_rendered_order_row(self):
        rows = [
            {"order": "#SC2860"},
            {"order": "#SC2859"},
            {"order": "#SC2858"},
        ]
        display_rows = orders_page._display_rows(rows)

        self.assertEqual(len(display_rows), len(rows))
        for row, display_row in zip(rows, display_rows):
            self.assertEqual(display_row["order"].count(orders_page.COPY_ORDER_ICON), 1)
            self.assertEqual(display_row["order"].count(row["order"]), 1)
            self.assertEqual(set(display_row), set(orders_page.VISIBLE_COLUMNS))

    def test_prodigi_reference_contains_all_16_code_mappings(self):
        rows = os_pages.prodigi_reference_rows()

        self.assertEqual(len(rows), 16)
        self.assertEqual(
            set(rows[0]),
            {
                "Sports Cave Variant",
                "Sports Cave Frame",
                "Sports Cave Size",
                "Prodigi Product",
                "Prodigi Code",
                "Prodigi Frame Colour",
            },
        )
        self.assertIn("GLOBAL-CFP-A1", {row["Prodigi Code"] for row in rows})
        self.assertIn("GLOBAL-FAP-A4", {row["Prodigi Code"] for row in rows})
        self.assertEqual(
            next(row for row in rows if row["Sports Cave Frame"] == "Oak" and row["Sports Cave Size"].startswith("L "))["Prodigi Frame Colour"],
            "Natural",
        )
        self.assertIn("prodigi-code-cell", os_pages.prodigi_reference_table_html(rows))

    def test_prodigi_variant_mapping_uses_canonical_reference(self):
        cases = [
            (
                "Black / XL - 62 \u00d7 87 cm (24.4 \u00d7 34.3 in)",
                "GLOBAL-CFP-A1",
                'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
                "Black",
            ),
            (
                "Oak / L - 45 \u00d7 62 cm (17.7 \u00d7 24.4 in)",
                "GLOBAL-CFP-A2",
                'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm/16.5x23.4" (A2)',
                "Natural",
            ),
            (
                "White / S- 21 \u00d7 30 cm (8.3 \u00d7 11.8 in)",
                "GLOBAL-CFP-A4",
                'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 21x29.7cm / 8.3x11.7" (A4)',
                "White",
            ),
            (
                "Unframed / M - 30 \u00d7 45 cm (11.8 \u00d7 17.7 in)",
                "GLOBAL-FAP-A3",
                'EMA, Enhanced Matte Art Paper, 200gsm, 29.7x42cm / 11.7x16.5" (A3)',
                "No frame",
            ),
        ]

        for variant, code, product, frame_colour in cases:
            row = os_pages.prodigi_tracker_row_from_order(
                {
                    "order": "#SC1",
                    "customer": "Test Customer",
                    "product": "Test Wall Art",
                    "variant": variant,
                    "edition_number": 1,
                    "shipping": "Standard",
                }
            )
            self.assertEqual(row["prodigi_code"], code)
            self.assertEqual(row["prodigi_product_name"], product)
            self.assertEqual(row["prodigi_frame_colour"], frame_colour)
            self.assertIn(code, os_pages.prodigi_required_confirmation_question(row))
            self.assertIn(product, os_pages.prodigi_variant_copy_text(row))

    def test_prodigi_tracker_builds_multiline_order_rows(self):
        order_rows = [
            {
                "order": "#SC2843",
                "date": "2026-06-23",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 94,
                "edition_total": 100,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
                "edition_offset": 0,
            },
            {
                "order": "#SC2843",
                "date": "2026-06-23",
                "customer": "Ashkan Zand",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Unframed / M",
                "edition_number": 37,
                "edition_total": 100,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8432",
                "shopify_product_id": "gid://shopify/Product/9002",
                "edition_offset": 0,
            },
        ]

        rows = os_pages.build_prodigi_tracker_rows(order_rows)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["prodigi_code"], "GLOBAL-CFP-A2")
        self.assertEqual(rows[1]["prodigi_code"], "GLOBAL-FAP-A3")
        self.assertTrue(all(row["prodigi_status"] == "Ready to Send" for row in rows))

    def test_prodigi_copy_details_contains_fulfilment_fields(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
            }
        )

        copied = os_pages.prodigi_copy_details(row)

        self.assertIn("Shopify Order #: #SC2843", copied)
        self.assertIn("Edition #: #050", copied)
        self.assertIn("Prodigi Code: GLOBAL-CFP-A2", copied)
        self.assertIn("Classic Frame, EMA 200gsm Fine Art Print", copied)
        self.assertIn("Shipping: US Standard Tracked Shipping", copied)

    def test_prodigi_dispatch_search_finds_only_matching_order_lines(self):
        order_rows = [
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
            },
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "Legends Never Die Messi vs Ronaldo Wall Art",
                "variant": "Black / M",
                "edition_number": 37,
                "shipping": "US Standard Tracked Shipping",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8432",
                "shopify_product_id": "gid://shopify/Product/9002",
            },
            {
                "order": "#SC2844",
                "customer": "Someone Else",
                "product": "Other Wall Art",
                "variant": "Black / L",
                "edition_number": 1,
            },
        ]

        rows = os_pages.prodigi_find_order_rows(order_rows, "#SC2843")

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["shopify_order_name"] for row in rows}, {"#SC2843"})
        self.assertEqual({row["product_title"] for row in rows}, {"GOAT Debate Wall Art", "Legends Never Die Messi vs Ronaldo Wall Art"})

    def test_prodigi_find_order_uses_supabase_direct_lookup_not_full_snapshot(self):
        raw_rows = [
            {
                "shopify_order_id": "gid://shopify/Order/2843",
                "order_name": "#SC2843",
                "customer_name": "Ashkan Zand",
                "customer_email": "ashkan@example.com",
                "processed_at": "2026-06-23T10:00:00Z",
                "created_at": "2026-06-23T09:55:00Z",
                "order_raw_json": {"shipping_lines": [{"title": "US Standard Tracked Shipping"}]},
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
                "product_title": "GOAT Debate Wall Art",
                "variant_title": "Black / XL - 62 \u00d7 87 cm",
                "quantity": 1,
                "assignments": [
                    {
                        "edition_number": 50,
                        "edition_total": 100,
                        "allocation_index": 1,
                        "certificate_status": "Uploaded",
                    }
                ],
            }
        ]
        existing_rows = [{"row_id": "existing", "shopify_order_name": "#SC2843", "source": "prodigi_dispatch_log"}]

        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_hybrid_order_rows",
            return_value=raw_rows,
        ) as list_hybrid_order_rows, patch.object(
            os_pages,
            "prodigi_load_dispatch_rows",
            return_value=existing_rows,
        ) as load_dispatch, patch.object(
            order_allocator,
            "load_orders_snapshot",
            side_effect=AssertionError("Prodigi lookup should not load the full order snapshot when Supabase is available."),
        ):
            rows, existing = os_pages.prodigi_find_order_rows_from_cache("#SC2843")

        list_hybrid_order_rows.assert_called_once_with(search="#SC2843", limit=50)
        load_dispatch.assert_called_once_with("Search", search_text="#SC2843", limit=100)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["shopify_order_name"], "#SC2843")
        self.assertEqual(rows[0]["prodigi_code"], "GLOBAL-CFP-A1")
        self.assertEqual(existing, existing_rows)

    def test_prodigi_lookup_keeps_multiple_allocations_for_same_variant(self):
        raw_rows = [
            {
                "shopify_order_id": "gid://shopify/Order/2906",
                "order_name": "#SC2906",
                "customer_name": "Guy Fairclough",
                "customer_email": "guy@example.com",
                "processed_at": "2026-07-09T10:00:00Z",
                "created_at": "2026-07-09T09:55:00Z",
                "order_raw_json": {"shipping_lines": [{"title": "Standard Tracked Shipping"}]},
                "shopify_line_item_id": "gid://shopify/LineItem/9061",
                "shopify_product_id": "gid://shopify/Product/31031",
                "product_title": "Greg Murphy Lap of the Gods Wall Art",
                "variant_title": "Oak / XL",
                "quantity": 1,
                "assignments": [
                    {
                        "edition_order_id": "eo-greg-031",
                        "edition_number": 31,
                        "edition_total": 100,
                        "allocation_index": 1,
                        "certificate_status": "Uploaded",
                    }
                ],
            },
            {
                "shopify_order_id": "gid://shopify/Order/2906",
                "order_name": "#SC2906",
                "customer_name": "Guy Fairclough",
                "customer_email": "guy@example.com",
                "processed_at": "2026-07-09T10:00:00Z",
                "created_at": "2026-07-09T09:55:00Z",
                "order_raw_json": {"shipping_lines": [{"title": "Standard Tracked Shipping"}]},
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "shopify_product_id": "gid://shopify/Product/31080",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "variant_title": "Black / M",
                "quantity": 2,
                "assignments": [
                    {
                        "edition_order_id": "eo-six-080",
                        "edition_number": 80,
                        "edition_total": 100,
                        "allocation_index": 1,
                        "certificate_status": "Uploaded",
                    }
                ],
            },
        ]
        edition_rows = [
            {
                "id": "eo-greg-031",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9061",
                "shopify_product_id": "gid://shopify/Product/31031",
                "product_title": "Greg Murphy Lap of the Gods Wall Art",
                "variant_title": "Oak / XL",
                "customer_name": "Guy Fairclough",
                "customer_email": "guy@example.com",
                "edition_number": 31,
                "edition_total": 100,
                "allocation_index": 1,
                "certificate_status": "Uploaded",
            },
            {
                "id": "eo-six-080",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "shopify_product_id": "gid://shopify/Product/31080",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "variant_title": "Black / M",
                "customer_name": "Guy Fairclough",
                "customer_email": "guy@example.com",
                "edition_number": 80,
                "edition_total": 100,
                "allocation_index": 1,
                "certificate_status": "Uploaded",
            },
            {
                "id": "eo-six-081",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "shopify_product_id": "gid://shopify/Product/31080",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "variant_title": "Black / M",
                "customer_name": "Guy Fairclough",
                "customer_email": "guy@example.com",
                "edition_number": 81,
                "edition_total": 100,
                "allocation_index": 2,
                "certificate_status": "Certificate Missing",
            },
        ]
        raw_rows[1]["assignments"].append(
            {
                "edition_order_id": "eo-six-081",
                "edition_number": 81,
                "edition_total": 100,
                "allocation_index": 2,
                "certificate_status": "Certificate Missing",
            }
        )
        existing_rows = [
            {
                "row_id": "gid://shopify/Order/2906|gid://shopify/LineItem/9062|1",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "edition_number": 80,
                "prodigi_status": "Complete",
                "source": "prodigi_dispatch_log",
            }
        ]

        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_hybrid_order_rows",
            return_value=raw_rows,
        ), patch.object(
            os_pages,
            "prodigi_load_dispatch_rows",
            return_value=existing_rows,
        ):
            rows, existing = os_pages.prodigi_find_order_rows_from_cache("2906")
            rows_again, _ = os_pages.prodigi_find_order_rows_from_cache("2906")

        self.assertEqual(len(edition_rows), 3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sorted(row["edition_number"] for row in rows), [31, 80, 81])
        six_laps = sorted(
            [row for row in rows if row["product_title"] == "Six Laps Ahead Peter Brock Wall Art"],
            key=lambda row: row["edition_number"],
        )
        self.assertEqual([row["edition_number"] for row in six_laps], [80, 81])
        self.assertEqual([row["allocation_index"] for row in six_laps], [1, 2])
        self.assertEqual(six_laps[0]["row_id"], "gid://shopify/Order/2906|gid://shopify/LineItem/9062|1")
        self.assertEqual(six_laps[0]["prodigi_status"], "Complete")
        self.assertEqual(six_laps[1]["row_id"], "edition-order|eo-six-081")
        self.assertEqual(six_laps[1]["prodigi_status"], "Ready to Send")
        self.assertEqual(len({row["row_id"] for row in rows}), 3)
        self.assertEqual([row["row_id"] for row in rows_again], [row["row_id"] for row in rows])
        self.assertEqual(existing, existing_rows)

    def test_prodigi_dispatch_save_is_independent_per_allocation_unit(self):
        base = {
            "order": "#SC2906",
            "customer": "Guy Fairclough",
            "product": "Six Laps Ahead Peter Brock Wall Art",
            "variant": "Black / M",
            "edition_total": 100,
            "shipping": "Standard Tracked Shipping",
            "certificate": "Uploaded",
            "shopify_order_id": "gid://shopify/Order/2906",
            "shopify_line_item_id": "gid://shopify/LineItem/9062",
            "shopify_product_id": "gid://shopify/Product/31080",
        }
        first = os_pages.prodigi_tracker_row_from_order(
            {**base, "edition_order_id": "eo-six-080", "edition_number": 80, "allocation_index": 1}
        )
        second = os_pages.prodigi_tracker_row_from_order(
            {**base, "edition_order_id": "eo-six-081", "edition_number": 81, "allocation_index": 2}
        )
        answers = {
            "certificate": "Yes",
            "artwork_upload": "Yes",
            "product_option": "Yes",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        saved_rows, saved_first = os_pages.prodigi_upsert_dispatch_row([second], first, status="Complete", notes="First done", qa_answers=answers)

        self.assertEqual(len(saved_rows), 2)
        self.assertEqual(saved_first["prodigi_status"], "Complete")
        untouched_second = next(row for row in saved_rows if row["edition_number"] == 81)
        self.assertEqual(untouched_second["prodigi_status"], "Ready to Send")

        saved_rows, saved_second = os_pages.prodigi_upsert_dispatch_row(saved_rows, second, status="Complete", notes="Second done", qa_answers=answers)
        saved_rows, _ = os_pages.prodigi_upsert_dispatch_row(saved_rows, first, status="Complete", notes="First done again", qa_answers=answers)
        saved_rows, _ = os_pages.prodigi_upsert_dispatch_row(saved_rows, second, status="Complete", notes="Second done again", qa_answers=answers)

        self.assertEqual(len(saved_rows), 2)
        self.assertEqual(sorted(row["edition_number"] for row in saved_rows), [80, 81])
        self.assertEqual(len({row["row_id"] for row in saved_rows}), 2)
        self.assertNotEqual(saved_first["row_id"], saved_second["row_id"])

    def test_prodigi_quantity_one_lookup_still_works_with_edition_overlay(self):
        raw_rows = [
            {
                "shopify_order_id": "gid://shopify/Order/2908",
                "order_name": "#SC2908",
                "customer_name": "John Millard",
                "customer_email": "john@example.com",
                "processed_at": "2026-07-09T10:00:00Z",
                "created_at": "2026-07-09T09:55:00Z",
                "order_raw_json": {"shipping_lines": [{"title": "Standard Tracked Shipping"}]},
                "shopify_line_item_id": "gid://shopify/LineItem/9081",
                "shopify_product_id": "gid://shopify/Product/39076",
                "product_title": "Justin Gaethje Undisputed Wall Art",
                "variant_title": "Black / L",
                "quantity": 1,
                "assignments": [
                    {
                        "edition_order_id": "eo-gaethje-076",
                        "edition_number": 76,
                        "edition_total": 100,
                        "allocation_index": 1,
                        "certificate_status": "Uploaded",
                    }
                ],
            }
        ]
        edition_rows = [
            {
                "id": "eo-gaethje-076",
                "shopify_order_id": "gid://shopify/Order/2908",
                "shopify_order_name": "#SC2908",
                "shopify_line_item_id": "gid://shopify/LineItem/9081",
                "shopify_product_id": "gid://shopify/Product/39076",
                "product_title": "Justin Gaethje Undisputed Wall Art",
                "variant_title": "Black / L",
                "customer_name": "John Millard",
                "customer_email": "john@example.com",
                "edition_number": 76,
                "edition_total": 100,
                "allocation_index": 1,
                "certificate_status": "Uploaded",
            }
        ]

        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_hybrid_order_rows",
            return_value=raw_rows,
        ), patch.object(
            os_pages,
            "prodigi_load_dispatch_rows",
            return_value=[],
        ):
            rows, _ = os_pages.prodigi_find_order_rows_from_cache("#SC2908")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["edition_number"], 76)
        self.assertEqual(rows[0]["allocation_index"], 1)
        self.assertEqual(rows[0]["row_id"], "edition-order|eo-gaethje-076")
        self.assertEqual(rows[0]["prodigi_code"], "GLOBAL-CFP-A2")

    def test_prodigi_dispatch_save_writes_single_persistent_supabase_row(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / XL - 62 \u00d7 87 cm",
                "edition_number": 50,
                "edition_total": 100,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Uploaded",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
            }
        )
        answers = {
            "certificate": "Yes",
            "artwork_upload": "Yes",
            "product_option": "Yes",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "upsert_prodigi_dispatch_row",
            return_value={"upserted": 1},
        ) as upsert_row:
            saved = os_pages.prodigi_save_dispatch_row(row, status="Submitted", notes="Sent", qa_answers=answers)

        upsert_row.assert_called_once()
        persisted = upsert_row.call_args.args[0]
        self.assertEqual(persisted["row_id"], saved["row_id"])
        self.assertEqual(persisted["prodigi_status"], "Submitted")
        self.assertEqual(persisted["prodigi_product_code"], "GLOBAL-CFP-A1")
        self.assertTrue(persisted["qa_confirmed"])

    def test_prodigi_issue_save_writes_needs_review_row(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
            }
        )
        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "upsert_prodigi_dispatch_row",
            return_value={"upserted": 1},
        ) as upsert_row:
            saved = os_pages.prodigi_save_dispatch_row(
                row,
                status="Needs Review",
                notes="Certificate missing",
                qa_answers={"certificate": "No", "product_option": "No"},
            )

        persisted = upsert_row.call_args.args[0]
        self.assertEqual(saved["prodigi_status"], "Needs Review")
        self.assertEqual(persisted["prodigi_status"], "Needs Review")
        self.assertIn("Certificate missing", persisted["notes"])

    def test_prodigi_dispatch_final_certificate_action_upserts_single_row(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "edition_total": 100,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
            }
        )
        answers = {
            "certificate": "No",
            "artwork_upload": "Yes",
            "product_option": "Yes",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        blockers = os_pages.prodigi_dispatch_blockers(row, answers)
        self.assertNotIn("Generate/upload certificate before dispatch completion.", blockers)
        saved_rows, saved = os_pages.prodigi_upsert_dispatch_row([], row, status="Needs Review", notes="Cert missing", qa_answers=answers)
        saved_rows, saved_again = os_pages.prodigi_upsert_dispatch_row(saved_rows, row, status="Needs Review", notes="Still missing", qa_answers=answers)

        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved["prodigi_status"], "Needs Review")
        self.assertEqual(saved_again["shopify_order_number"], "#SC2843")
        self.assertEqual(saved_again["shopify_variant_title"], "Black / L")
        self.assertEqual(saved_again["sports_cave_frame"], "Black")
        self.assertEqual(saved_again["prodigi_product_code"], "GLOBAL-CFP-A2")
        self.assertEqual(saved_again["prodigi_frame_colour"], "Black")
        self.assertFalse(saved_again["qa_confirmed"])
        self.assertEqual(saved_again["notes"], "Still missing")
        self.assertIn("Certificate not uploaded", saved_again["issue_reason"])

    def test_prodigi_complete_status_is_per_line_and_confirmed(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "edition_total": 100,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Uploaded",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
            }
        )
        other_line = {
            **row,
            "row_id": "other-line",
            "product_title": "Legends Never Die Messi vs Ronaldo Wall Art",
            "edition_number": 41,
            "shopify_line_item_id": "gid://shopify/LineItem/8432",
            "prodigi_status": "",
        }
        answers = {
            "certificate": "Yes",
            "artwork_upload": "Yes",
            "product_option": "Yes",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        saved_rows, saved = os_pages.prodigi_upsert_dispatch_row([other_line], row, status="Complete", notes="Done", qa_answers=answers)

        self.assertEqual(len(saved_rows), 2)
        self.assertEqual(saved["prodigi_status"], "Complete")
        self.assertTrue(saved["qa_confirmed"])
        self.assertEqual(other_line["prodigi_status"], "")

    def test_prodigi_final_qa_generates_certificate_after_confirmation(self):
        source = inspect.getsource(os_pages.render_prodigi_page)

        self.assertIn("Is this order error-free and ready to finalise?", source)
        self.assertIn("Generate + Upload Certificate", source)
        self.assertIn("prodigi_generate_upload_certificate_for_row(completion_row)", source)
        self.assertIn('status="Complete"', source)

    def test_prodigi_dispatch_recent_log_filters_last_7_days_and_searches_history(self):
        today = os_pages.date(2026, 6, 24)
        rows = [
            {
                "row_id": "recent",
                "prodigi_status": "Submitted",
                "date_sent_to_prodigi": "2026-06-23",
                "shopify_order_name": "#SC2843",
                "customer_name": "Ashkan Zand",
                "product_title": "GOAT Debate Wall Art",
                "source": "prodigi_dispatch_log",
            },
            {
                "row_id": "old",
                "prodigi_status": "Submitted",
                "date_sent_to_prodigi": "2026-05-01",
                "shopify_order_name": "#SC2000",
                "customer_name": "Old Customer",
                "product_title": "Old Wall Art",
                "source": "prodigi_dispatch_log",
            },
        ]

        recent = os_pages.prodigi_dispatch_rows_for_tab(rows, "Last 7 Days", today=today)
        history = os_pages.prodigi_dispatch_rows_for_tab(rows, "History", today=today)
        searched = os_pages.prodigi_dispatch_rows_for_tab(rows, "Last 7 Days", "#SC2000", today=today)

        self.assertEqual([row["row_id"] for row in recent], ["recent"])
        self.assertEqual([row["row_id"] for row in history], ["old"])
        self.assertEqual([row["row_id"] for row in searched], ["old"])

    def test_prodigi_dispatch_log_views_query_limited_supabase_rows(self):
        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_prodigi_dispatch_rows",
            return_value=[],
        ) as list_rows:
            os_pages.prodigi_load_dispatch_rows("Last 7 Days", limit=50)
            os_pages.prodigi_load_dispatch_rows("Needs Review", limit=25)
            os_pages.prodigi_load_dispatch_rows("Submitted", limit=25)
            os_pages.prodigi_load_dispatch_rows("History", limit=25)

        self.assertEqual(list_rows.call_args_list[0].kwargs["days"], 7)
        self.assertEqual(list_rows.call_args_list[0].kwargs["limit"], 50)
        self.assertEqual(list_rows.call_args_list[1].kwargs["status"], "Needs Review")
        self.assertEqual(list_rows.call_args_list[2].kwargs["status"], "Submitted")
        self.assertEqual(list_rows.call_args_list[2].kwargs["days"], 7)
        self.assertEqual(list_rows.call_args_list[3].kwargs["older_than_days"], 7)

    def test_prodigi_dispatch_rows_remain_after_rerun_and_order_sync_does_not_delete(self):
        saved_row = {
            "row_id": "stable-row",
            "prodigi_status": "Submitted",
            "shopify_order_name": "#SC2843",
            "source": "prodigi_dispatch_log",
        }

        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_prodigi_dispatch_rows",
            return_value=[saved_row],
        ):
            first_load = os_pages.prodigi_load_dispatch_rows("Last 7 Days")
            second_load = os_pages.prodigi_load_dispatch_rows("Last 7 Days")

        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertEqual(first_load, [saved_row])
        self.assertEqual(second_load, [saved_row])
        self.assertNotIn("DELETE FROM prodigi_dispatch_rows", backend_source)
        self.assertNotIn("TRUNCATE prodigi_dispatch_rows", backend_source)

    def test_prodigi_duplicate_complete_upsert_keeps_one_row(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / XL",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Uploaded",
            }
        )
        answers = {
            "certificate": "Yes",
            "artwork_upload": "Yes",
            "product_option": "Yes",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        saved_rows, _ = os_pages.prodigi_upsert_dispatch_row([], row, status="Submitted", notes="First", qa_answers=answers)
        saved_rows, saved_again = os_pages.prodigi_upsert_dispatch_row(saved_rows, row, status="Submitted", notes="Second", qa_answers=answers)

        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_again["notes"], "Second")

    def test_prodigi_variant_confirmation_blocks_completion_until_yes(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / XL",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Uploaded",
            }
        )
        answers = {
            "certificate": "Yes",
            "artwork_upload": "Yes",
            "product_option": "No",
            "frame": "Yes",
            "size": "Yes",
            "edition_number": "Yes",
            "shipping": "Yes",
            "sent_to_production": "Yes",
            "final_check": "Yes",
        }

        self.assertIn("Prodigi variant not confirmed", os_pages.prodigi_dispatch_blockers(row, answers))

    def test_prodigi_submission_blocks_missing_code_and_duplicate_submit(self):
        missing = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC1",
                "customer": "Test",
                "product": "Unknown Wall Art",
                "variant": "Unknown",
                "edition_number": 1,
                "shipping": "Standard",
                "shopify_order_id": "gid://shopify/Order/1",
                "shopify_line_item_id": "gid://shopify/LineItem/1",
                "shopify_product_id": "gid://shopify/Product/1",
            }
        )
        submitted = os_pages.prodigi_tracker_row_from_order(
            {
                **missing,
                "variant": "Black / L",
                "prodigi_order_id": "P123",
                "date_sent_to_prodigi": "2026-06-23T10:00:00Z",
            },
            {
                **missing,
                "variant": "Black / L",
                "prodigi_order_id": "P123",
                "date_sent_to_prodigi": "2026-06-23T10:00:00Z",
            },
        )

        self.assertIn("Missing Prodigi code", os_pages.prodigi_submission_blockers(missing))
        self.assertIn("Already submitted", os_pages.prodigi_submission_blockers(submitted))
        result = os_pages.apply_prodigi_bulk_action([submitted], [submitted["row_id"]], "submitted")
        self.assertTrue(result["errors"])

    def test_prodigi_checklist_progress_and_submission_gates(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
            }
        )

        progress = os_pages.prodigi_progress_text(row)
        self.assertIn("Edition", progress)
        self.assertIn("Cert", progress)
        self.assertIn("Submitted", progress)
        self.assertIn("Tracking", progress)
        section_names = [section for section, _ in os_pages.prodigi_checklist_sections(row)]
        self.assertEqual(
            section_names,
            [
                "Edition QA",
                "Certificate QA",
                "Prodigi QA",
                "Shipping QA",
                "Submission QA",
                "Tracking / Shopify Fulfilment QA",
            ],
        )
        self.assertIn("Frame colour not checked", os_pages.prodigi_manual_submit_blockers(row))
        ready = {
            **row,
            "frame_colour_checked": True,
            "prodigi_option_checked": True,
            "shipping_checked": True,
            "submitted_confirmed": True,
        }
        self.assertEqual(os_pages.prodigi_manual_submit_blockers(ready), [])

    def test_prodigi_fulfillment_blocks_missing_tracking_and_certificate(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "US Standard Tracked Shipping",
                "certificate": "Generate",
                "shopify_order_id": "gid://shopify/Order/2843",
                "shopify_line_item_id": "gid://shopify/LineItem/8431",
                "shopify_product_id": "gid://shopify/Product/9001",
                "date_sent_to_prodigi": "2026-06-23T10:00:00Z",
            },
            {
                "date_sent_to_prodigi": "2026-06-23T10:00:00Z",
                "prodigi_status": "Submitted to Prodigi",
            },
        )

        blockers = os_pages.prodigi_fulfillment_blockers(row)
        self.assertIn("Tracking missing", blockers)
        self.assertIn("Certificate not uploaded", blockers)

    def test_prodigi_csv_import_matches_existing_rows_and_export_roundtrips(self):
        rows = os_pages.build_prodigi_tracker_rows(
            [
                {
                    "order": "#SC2843",
                    "date": "2026-06-23",
                    "customer": "Ashkan Zand",
                    "product": "GOAT Debate Wall Art",
                    "variant": "Black / L",
                    "edition_number": 50,
                    "edition_total": 100,
                    "shipping": "US Standard Tracked Shipping",
                    "shopify_order_id": "gid://shopify/Order/2843",
                    "shopify_line_item_id": "gid://shopify/LineItem/8431",
                    "shopify_product_id": "gid://shopify/Product/9001",
                }
            ]
        )
        csv_text = (
            "Date Sent,Shopify Order #,Customer Name,Edition Name,Edition No.,Frame,Size,Prodigi Product Option,Shipping,Status,Notes\n"
            "2026-06-23,#SC2843,Ashkan Zand,GOAT Debate Wall Art,50,Black,L,Classic Frame,Express,Submitted to Prodigi,Sent manually\n"
        )

        result = os_pages.import_prodigi_tracker_csv(csv_text, rows)
        exported = os_pages.export_prodigi_tracker_csv(result["rows"]).decode("utf-8-sig")

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["rows"][0]["prodigi_status"], "Submitted")
        self.assertEqual(result["rows"][0]["shipping_method"], "Express")
        self.assertIn("Sent manually", result["rows"][0]["notes"])
        self.assertIn("prodigi_order_id", exported.splitlines()[0])

    def test_prodigi_unmatched_csv_import_creates_needs_review_row(self):
        csv_text = (
            "Date Sent,Shopify Order #,Customer Name,Edition Name,Edition No.,Frame,Size,Prodigi Product Option,Shipping,Status,Notes\n"
            "2026-06-23,#SC9999,No Match,Unknown Wall Art,1,Black,L,Classic Frame,Standard,Submitted,Legacy row\n"
        )

        result = os_pages.import_prodigi_tracker_csv(csv_text, [])

        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["rows"][0]["prodigi_status"], "Needs Review")

    def test_prodigi_notes_and_tracking_persist(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC1",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 1,
                "shipping": "Standard",
            },
            {"tracking_number": "TRACK123", "notes": "Leave on tracker"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "prodigi.json"
            os_pages.save_prodigi_tracker_rows([row], path=path)
            loaded = os_pages.load_prodigi_tracker_state(path=path)

        self.assertEqual(loaded["rows"][0]["tracking_number"], "TRACK123")
        self.assertEqual(loaded["rows"][0]["notes"], "Leave on tracker")

    def test_prodigi_dispatch_log_uses_supabase_when_configured(self):
        row = os_pages.prodigi_tracker_row_from_order(
            {
                "order": "#SC2843",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "shipping": "Standard",
            },
            {"notes": "Submitted safely", "source": "prodigi_dispatch_log"},
        )
        with patch.object(os_pages.supabase_backend, "is_configured", return_value=True), patch.object(
            os_pages.supabase_backend,
            "list_prodigi_dispatch_rows",
            return_value=[row],
        ) as list_rows, patch.object(
            os_pages.supabase_backend,
            "upsert_prodigi_dispatch_rows",
            return_value={"upserted": 1},
        ) as upsert_rows:
            loaded = os_pages.load_prodigi_tracker_state()
            saved = os_pages.save_prodigi_tracker_rows(loaded["rows"])

        list_rows.assert_called_once()
        upsert_rows.assert_called_once_with([row])
        self.assertEqual(loaded["source"], "supabase")
        self.assertEqual(saved["source"], "supabase")
        self.assertEqual(loaded["rows"][0]["notes"], "Submitted safely")

    def test_render_main_service_uses_direct_streamlit_and_webhook_service_is_separate(self):
        source = (ROOT / "render.yaml").read_text(encoding="utf-8")

        self.assertIn("name: sports-cave-image-factory", source)
        self.assertIn("startCommand: streamlit run app.py", source)
        self.assertIn("--server.fileWatcherType none", source)
        self.assertIn("--server.runOnSave false", source)
        self.assertIn("--browser.gatherUsageStats false", source)
        self.assertIn("healthCheckPath: /_stcore/health", source)
        self.assertIn("name: sports-cave-os-webhooks", source)
        self.assertIn("startCommand: python webhook_server.py", source)
        self.assertIn("healthCheckPath: /healthz", source)
        self.assertNotIn("startCommand: python server.py", source)

    def test_lightweight_webhook_service_route_remains_available_without_streamlit_proxy(self):
        source = (ROOT / "webhook_server.py").read_text(encoding="utf-8")

        self.assertIn('@app.get("/healthz")', source)
        self.assertIn('/webhooks/shopify/orders-paid', source)
        self.assertIn("process_order_paid_webhook", source)
        self.assertIn("verify_shopify_webhook_hmac", source)
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("streamlit run", source)
        self.assertNotIn("start_streamlit", source)
        self.assertNotIn("websockets.connect", source)
        self.assertNotIn("ensure_schema", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("prodigi", source.lower())
        self.assertNotIn("certificate_engine", source)
        self.assertNotIn("certificate_job", source)
        self.assertNotIn("generate_missing_certificates_for_order", source)
        self.assertNotIn("require_cutover=True", source)

    def test_orders_paid_webhook_diagnostic_script_is_read_only(self):
        source = (ROOT / "scripts" / "diagnose_shopify_orders_paid_webhooks.py").read_text(encoding="utf-8")

        self.assertIn("list_orders_paid_webhook_subscriptions", source)
        self.assertIn("duplicate_orders_paid_webhook_subscription", source)
        self.assertNotIn("ensure_orders_paid_webhook_subscription", source)
        self.assertNotIn("webhookSubscriptionDelete", source)
        self.assertNotIn("delete", source.lower())

    def test_server_py_is_not_a_streamlit_proxy(self):
        source = (ROOT / "server.py").read_text(encoding="utf-8")

        self.assertIn("from webhook_server import app", source)
        self.assertNotIn("streamlit run", source.lower())
        self.assertNotIn("start_streamlit", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("websockets.connect", source)
        self.assertNotIn('@app.api_route("/{path:path}"', source)
        self.assertNotIn('@app.websocket("/{path:path}")', source)

    def test_prompt_editing_is_password_gated_and_backend_persisted(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        os_pages_source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        self.assertIn("import prompt_store", app_source)
        self.assertIn("import prompt_store", os_pages_source)
        self.assertIn("def render_prompt_edit_controls", app_source)
        self.assertIn("def render_prompt_edit_controls", os_pages_source)
        self.assertIn("Developer password", app_source)
        self.assertIn("DEVELOPER_PAGE_PASSWORD", app_source)
        self.assertIn('label="✎"', app_source)
        self.assertIn('div[data-testid="stButton"] button', app_source)
        self.assertIn("prompt_store.save_prompt", app_source)
        self.assertIn("prompt_store.save_prompt", os_pages_source)

    def test_mockups_prompt_cards_use_compact_modal_prompt_actions(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        prompt_cards = source[
            source.index("def render_prompt_cards") : source.index("\n\ndef render_optional_package_controls")
        ]
        mockup_actions = source[
            source.index("def render_mockup_prompt_editor") : source.index("\n\ndef prime_asset_selection_state")
        ]

        self.assertIn("render_mockup_prompt_action_row", prompt_cards)
        self.assertIn("Upload image from ChatGPT", prompt_cards)
        self.assertIn("Add To ZIP", prompt_cards)
        self.assertNotIn("View Prompt", prompt_cards)
        self.assertNotIn("st.expander", prompt_cards)
        self.assertNotIn("render_copyable_prompt", prompt_cards)
        self.assertIn("render_mockup_prompt_bar", mockup_actions)
        self.assertIn("st.container(border=True)", mockup_actions)
        self.assertIn("st.text_area", mockup_actions)
        self.assertIn("Prompt saved", mockup_actions)
        self.assertIn("Prompt copied", mockup_actions)
        self.assertIn("prompt_store.save_prompt", mockup_actions)
        self.assertIn("Developer password", mockup_actions)
        self.assertIn("mockup_prompt_edit", mockup_actions)
        self.assertIn("prompt_edit", mockup_actions)
        self.assertIn("mockup-prompt-edit-button", mockup_actions)
        self.assertIn("_mockup_prompt_edit_key(prompt_id)", mockup_actions)
        self.assertIn("window.parent.location.href", mockup_actions)
        self.assertIn("encodeURIComponent(promptId)", mockup_actions)
        self.assertIn("stopPropagation", mockup_actions)
        self.assertIn("show_edit=True", mockup_actions)
        self.assertIn('target="_parent"', mockup_actions)
        self.assertNotIn("Preview", mockup_actions)
        self.assertNotIn("preview", mockup_actions.casefold())
        self.assertNotIn("mockup-preview", mockup_actions)
        self.assertNotIn("Read-only preview", mockup_actions)

    def test_product_uploads_shows_only_two_embedded_product_prompts(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        product_uploads = source[
            source.index("def render_product_uploads_page():") : source.index("\n\ndef test_google_drive_connection")
        ]

        self.assertEqual(product_uploads.count("render_copyable_prompt("), 2)
        self.assertIn("New Shopify Product Prompt", product_uploads)
        self.assertIn("Update Existing Product Prompt", product_uploads)
        self.assertNotIn("Image Alt Text Prompt", product_uploads)
        self.assertNotIn("Meta Title / Description Prompt", product_uploads)
        self.assertNotIn("Final QA Checklist Prompt", product_uploads)
        self.assertNotIn("Only two product prompts are shown here. Nothing on this page queries products, Shopify, or generated runs.", product_uploads)
        self.assertIn('st.expander("How to", expanded=False)', product_uploads)
        self.assertIn("image alt text, SEO meta tags, and final QA checklist instructions are already embedded", product_uploads)
        self.assertIn("def build_product_upload_prompt", source)
        self.assertIn("PRODUCT_UPLOAD_ALT_TEXT_PROMPT.strip()", source)
        self.assertIn("PRODUCT_UPLOAD_META_PROMPT.strip()", source)
        self.assertIn("PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT.strip()", source)

    def test_orders_page_is_snapshot_based_and_lightweight(self):
        source = (ROOT / "orders_page.py").read_text(encoding="utf-8")
        top_actions = inspect.getsource(orders_page._render_top_actions)
        render_page = inspect.getsource(orders_page.render_page)
        list_orders = inspect.getsource(supabase_backend.list_orders)
        upsert_order_lines = inspect.getsource(supabase_backend._upsert_order_lines)
        product_lookup = inspect.getsource(supabase_backend._lookup_product_by_handle_or_id)

        self.assertEqual(
            orders_page.VISIBLE_COLUMNS,
            (
                "order",
                "edition",
                "certificate",
                "customer",
                "product",
                "variant",
                "shipping",
                "date",
                "prodigi",
            ),
        )
        self.assertIn("orders_allocation_snapshot.json", source)
        self.assertIn("_read_orders_snapshot", source)
        self.assertIn("HYBRID_FAST_ORDERS_ENABLED = True", source)
        self.assertIn("load_hybrid_orders_snapshot", source)
        self.assertIn("_display_table_payload", source)
        self.assertIn("_compact_variant_label", source)
        self.assertIn("selection_mode=\"multi-row\"", source)
        self.assertIn("DEFAULT_VISIBLE_ROW_LIMIT = 50", source)
        self.assertIn("_render_orders_search_form", render_page)
        self.assertIn("Search orders", inspect.getsource(orders_page._render_orders_search_form))
        self.assertNotIn("Show all rows", render_page)
        self.assertNotIn("_render_admin_panel", render_page)
        self.assertIn("Check New Paid Orders", top_actions)
        self.assertIn("Backfill Latest Paid", top_actions)
        self.assertIn("Backfill latest paid orders", top_actions)
        self.assertIn("Preview Certificate", top_actions)
        self.assertIn("Generate + Upload Certificate", top_actions)
        self.assertIn("Reupload Certificate", top_actions)
        self.assertIn("Open Certificate", top_actions)
        self.assertIn("Start Prodigi QA", top_actions)
        self.assertNotIn("Start Prodigi Dispatch", top_actions)
        self.assertNotIn("Open Shopify Admin", top_actions)
        self.assertNotIn("customer_email", orders_page.VISIBLE_COLUMNS)
        self.assertNotIn("edition_total", orders_page.VISIBLE_COLUMNS)
        self.assertIn("Select an order, complete QA, then generate and upload the certificate.", render_page)
        self.assertIn("Assign edition number before certificate generation.", top_actions)
        self.assertIn("Source: Shopify mirror + Supabase edition ledger", render_page)
        self.assertIn("Edition source: Supabase", render_page)
        self.assertIn("Shopify mirror last synced:", render_page)
        self.assertNotIn("li.shopify_variant_id", list_orders)
        self.assertIn("li.raw_json->>'variant_id'", list_orders)
        self.assertIn("column_exists(cur, \"shopify_order_lines\", \"shopify_variant_id\")", upsert_order_lines)
        self.assertIn("variant_column", upsert_order_lines)
        set_line_status = inspect.getsource(supabase_backend._set_order_line_status)
        self.assertIn("column_exists(cur, \"shopify_order_lines\", \"shopify_variant_id\")", set_line_status)
        self.assertIn("variant_update_sql", set_line_status)
        self.assertNotIn("REGEXP_REPLACE", product_lookup)
        self.assertNotIn("REPLACE(REPLACE", product_lookup)
        return

        self.assertEqual(
            orders_page.VISIBLE_COLUMNS,
            (
                "order",
                "date",
                "customer",
                "customer_email",
                "edition",
                "edition_total",
                "certificate",
                "shipping",
                "product",
                "variant",
                "admin_url",
            ),
        )
        self.assertIn("orders_allocation_snapshot.json", source)
        self.assertIn("Sync New Orders", source)
        self.assertIn("_read_orders_snapshot", source)
        self.assertIn("load_supabase_orders_snapshot", source)
        self.assertIn("_render_orders_table", source)
        self.assertIn("st.dataframe", source)
        self.assertIn("selection_mode=\"multi-row\"", source)
        self.assertIn("Generate Selected Certificates", source)
        self.assertIn("Upload Selected to Shopify", source)
        self.assertIn("PERF Orders", source)
        self.assertIn('"load snapshot"', source)
        self.assertIn('"render table"', source)
        self.assertIn("DEFAULT_VISIBLE_ROW_LIMIT = 150", source)
        self.assertIn("Orders load cached rows:", source)
        self.assertIn("Shopify fetch skipped on initial load", source)
        self.assertIn("Allocation skipped on initial load", source)
        self.assertIn("Metafield sync skipped on initial load", source)
        self.assertIn("Certificate status load skipped on initial load", source)
        self.assertIn("Table render:", source)
        self.assertIn("Generate + Upload Selected", source)
        self.assertIn("Open Selected PDF", source)
        self.assertIn("Upload", source)
        self.assertIn("Operational orders ledger. Edition numbers load from Supabase first.", source)
        self.assertIn("Enable Stage 4B order sync controls", source)
        self.assertIn("Dry run only — show what would be imported.", source)
        self.assertIn("Backfill Missing Details", source)
        self.assertIn("I understand this will import new paid Shopify orders into Supabase.", source)
        self.assertIn("I understand this will backfill missing Shopify order details in Supabase.", source)
        self.assertIn("Tip: scroll sideways to view all fulfilment fields.", source)
        self.assertNotIn("Save Changed Order Editions", source)
        self.assertNotIn("Allocate Selected From Product Counter", source)
        self.assertNotIn("Overwrite Selected Order Allocation", source)
        self.assertNotIn("Override Selected Order Allocation", source)
        self.assertNotIn("Manual Allocation", source)
        self.assertNotIn("Edition Allocation", source)
        self.assertNotIn("Activate Live Allocation", source)
        self.assertNotIn("Advanced Allocation Tools", source)
        self.assertNotIn("Enable Live Allocation From Now", source)
        self.assertNotIn("Capture Product Baselines", source)
        self.assertNotIn("Allocate Missing Paid Orders", source)
        self.assertNotIn("Allocate Missing Recent Paid Orders", source)
        self.assertNotIn("Historical Backfill Selected Orders", source)
        self.assertNotIn("Confirm allocation repair", source)
        self.assertNotIn("Confirm historical backfill", source)
        self.assertNotIn("baseline", source.casefold())
        self.assertNotIn("cutover", source.casefold())
        self.assertNotIn("fetch_edition_ops_active_products", source)
        self.assertNotIn("st.data_editor", source)
        self.assertIn("sync_order_allocation_metafield", source)
        self.assertNotIn('"qty"', source)
        self.assertNotIn('"allocation_status"', source)
        self.assertNotIn('"sync_status"', source)
        self.assertIn('"admin_url"', source)
        self.assertIn("_configured_supabase_backend", source)

    def test_orders_main_toolbar_only_contains_daily_actions(self):
        top_actions = inspect.getsource(orders_page._render_top_actions)

        for label in (
            "Check New Paid Orders",
            "Backfill Latest Paid",
            "Preview Certificate",
            "Generate + Upload Certificate",
            "Reupload Certificate",
            "Open Certificate",
            "Start Prodigi QA",
        ):
            self.assertIn(label, top_actions)

        for label in (
            "Open Shopify Admin",
            "Show all rows",
        ):
            self.assertNotIn(label, top_actions)
        return

    def test_orders_normalise_row_uses_clean_va_status_labels(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC2848",
                "customer": "Nathan Baker",
                "product": "GOAT Debate Wall Art",
                "variant": "",
                "edition": "Historical backfill",
                "edition_number": "",
                "shipping": "",
                "certificate_status": "",
                "certificate_pdf_path": "",
                "certificate_pdf_url": "",
                "prodigi_status": "",
            }
        )

        self.assertEqual(row["edition"], "Needs edition")
        self.assertEqual(row["variant"], "Missing variant")
        self.assertEqual(row["shipping"], "Missing shipping")
        self.assertEqual(row["certificate"], "Needs certificate")
        self.assertEqual(row["prodigi"], "Needs certificate")

        compact = orders_page._normalise_row(
            {
                "variant": "Black / XL - 62 × 87 cm (24.4 × 34.3 in)",
            }
        )
        self.assertEqual(compact["variant"], "Black / XL")
        self.assertEqual(compact["variant_full"], "Black / XL - 62 × 87 cm (24.4 × 34.3 in)")

        uploaded = orders_page._normalise_row(
            {
                "order": "#SC2843",
                "customer": "Ashkan Zand",
                "product": "GOAT Debate Wall Art",
                "variant": "Black / L",
                "edition_number": 50,
                "edition_total": 100,
                "certificate_pdf_url": "https://cdn.example/cert.pdf",
            }
        )
        self.assertEqual(uploaded["edition"], "#050/100")
        self.assertEqual(uploaded["certificate"], "Uploaded")
        self.assertEqual(uploaded["prodigi"], "Ready to dispatch")

    def test_shopify_sync_preserves_purchase_time_edition_snapshots(self):
        query_source = "\n".join(
            (
                shopify_sync.ORDERS_QUERY,
                shopify_sync.ORDERS_SAFE_QUERY,
                shopify_sync.ORDERS_BY_IDS_QUERY,
            )
        )
        normalize_graphql = inspect.getsource(shopify_sync.normalize_order)
        normalize_rest = inspect.getsource(supabase_backend.normalize_rest_order)

        self.assertIn("customAttributes", query_source)
        self.assertIn("note", query_source)
        self.assertIn('"custom_attributes": custom_attributes', normalize_graphql)
        self.assertIn('"properties": custom_attributes', normalize_graphql)
        self.assertIn('"note_attributes": node.get("customAttributes")', normalize_graphql)
        self.assertIn('"properties": properties', normalize_rest)
        self.assertIn('"note_attributes": payload.get("note_attributes")', normalize_rest)

    def test_promised_edition_hint_reads_order_metafield_and_line_attributes(self):
        line_id = "gid://shopify/LineItem/555"
        order_hint = supabase_backend.promised_edition_hint_for_order_line(
            {
                "metafields": [
                    {
                        "namespace": "sports_cave",
                        "key": "edition_allocations",
                        "value": json.dumps(
                            {
                                "line_items": {
                                    line_id: {
                                        "edition_numbers": [42],
                                        "edition_total": 100,
                                    }
                                }
                            }
                        ),
                    }
                ]
            },
            {"shopify_line_item_id": line_id},
            1,
        )
        self.assertEqual(order_hint["edition_number"], 42)
        self.assertEqual(order_hint["edition_total"], 100)
        self.assertEqual(order_hint["source"], "shopify_order_metafield")

        attribute_hint = supabase_backend.promised_edition_hint_for_order_line(
            {},
            {
                "shopify_line_item_id": "gid://shopify/LineItem/556",
                "custom_attributes": [{"key": "edition_number", "value": "#043/100"}],
            },
            1,
        )
        self.assertEqual(attribute_hint["edition_number"], 43)
        self.assertEqual(attribute_hint["edition_total"], 100)
        self.assertEqual(attribute_hint["source"], "shopify_line_or_order_attribute")

    def test_allocation_uses_promised_snapshot_before_sequential_fallback(self):
        process_source = inspect.getsource(supabase_backend.process_paid_order)
        allocation_source = inspect.getsource(supabase_backend.allocate_edition_for_order_line)

        self.assertIn("promised_edition_hint_for_order_line(order, line_item, allocation_index)", process_source)
        self.assertIn("promised_edition_number=promised_hint.get(\"edition_number\")", process_source)
        self.assertIn("promised_edition_total=promised_hint.get(\"edition_total\")", process_source)
        self.assertIn("assignment_source=promised_hint.get(\"source\")", process_source)
        self.assertIn("promised_edition_existing_mismatch", allocation_source)
        self.assertIn("promised_edition_conflict", allocation_source)
        self.assertIn("target_number = _int_value(promised_edition_number, 0)", allocation_source)
        self.assertIn("target_number = next_number", allocation_source)
        self.assertIn("incremented_next = max(next_number, target_number + 1)", allocation_source)
        self.assertIn("edition_order_purchase_snapshot_allocation", allocation_source)

    def test_known_missing_edition_repair_targets_current_paid_rows(self):
        targets = supabase_backend.KNOWN_MISSING_EDITION_REPAIRS
        preview_source = inspect.getsource(supabase_backend.preview_known_missing_edition_repair)
        apply_source = inspect.getsource(supabase_backend.apply_known_missing_edition_repair)
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")

        expected = {
            ("#SC2848", "Paul Grubb", "Legends Never Die Messi vs Ronaldo Wall Art", 42),
            ("#SC2849", "Elle Hosking", "Greg Murphy Lap of the Gods Wall Art", 17),
            ("#SC2849", "Elle Hosking", "Peter Brock Tribute Wall Art", 67),
            ("#SC2850", "Daniel Brearley", "Lionel Messi The Final Crown Wall Art", 30),
            ("#SC2851", "Scott Tasler", "Legends Never Die Messi vs Ronaldo Wall Art", 43),
            ("#SC2852", "Marco Da Cruz", "Legends Never Die Messi vs Ronaldo Wall Art", 44),
            ("#SC2853", "Angelo Hiotis", "Legends Never Die Messi vs Ronaldo Wall Art", 45),
        }
        actual = {
            (
                target["order_name"],
                target["customer_name"],
                target["product_title"],
                target["edition_number"],
            )
            for target in targets
        }

        self.assertEqual(actual, expected)
        self.assertIn("target_rows", preview_source)
        self.assertIn("blocked_conflict", inspect.getsource(supabase_backend._known_missing_edition_repair_plan))
        self.assertIn("allocate_edition_for_order_line", apply_source)
        self.assertIn("promised_edition_number=target.get(\"edition_number\")", apply_source)
        self.assertIn("assignment_source=\"known_missing_truth_20260625\"", apply_source)
        self.assertIn("Preview Known Missing Edition Repair", app_source)
        self.assertIn("Apply Known Missing Edition Repair", app_source)

    def test_dashboard_uses_fulfilment_label_for_prodigi_readiness(self):
        dashboard_source = inspect.getsource(os_pages.render_supabase_dashboard_page)

        self.assertIn("Open Fulfilment", dashboard_source)
        self.assertNotIn("Open Prodigi", dashboard_source)

    def test_edition_ops_normal_view_shows_supabase_source_without_old_help_copy(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")
        render_page = source[source.index("def render_page():") :]

        self.assertIn('st.title("Edition Ops")', render_page)
        self.assertIn("Manage edition limits, next numbers, and active limited-edition products.", render_page)
        self.assertIn("Source: Supabase ledger", render_page)
        self.assertIn("_cached_supabase_products_snapshot", source)
        self.assertIn("_invalidate_edition_ops_cache", source)
        self.assertNotIn("Supabase connected", render_page)
        self.assertNotIn("Refresh products when new products are added.", render_page)
        self.assertNotIn("Import CSV and Replace Table when you have a new spreadsheet.", render_page)
        self.assertNotIn("Edit Enabled, Edition Total, and Next Edition Number.", render_page)
        self.assertNotIn("Export a CSV backup after major edits.", render_page)

    def test_edition_ops_render_does_not_write_local_snapshot(self):
        original = edition_ops._normalise_row(
            {
                "edition_product_id": "101",
                "handle": "goat-debate-wall-art",
                "edition_total": 100,
                "edition_next_number": 52,
            }
        )
        edited = dict(original)
        edited["edition_next_number"] = 53

        class FakePopover:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeColumn:
            def button(self, *args, **kwargs):
                return False

            def download_button(self, *args, **kwargs):
                return None

            def popover(self, *args, **kwargs):
                return FakePopover()

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {
                    edition_ops.SNAPSHOT_LOADED_KEY: True,
                    edition_ops.ROWS_KEY: [original],
                    edition_ops.ORIGINAL_ROWS_KEY: [original],
                    edition_ops.META_KEY: {},
                    edition_ops.ERRORS_KEY: {},
                    edition_ops.IMPORT_WARNINGS_KEY: [],
                    edition_ops.NOTICE_KEY: "",
                    edition_ops.EDITOR_VERSION_KEY: 0,
                }
                self.column_config = SimpleNamespace(
                    TextColumn=lambda *args, **kwargs: None,
                    NumberColumn=lambda *args, **kwargs: None,
                    CheckboxColumn=lambda *args, **kwargs: None,
                    LinkColumn=lambda *args, **kwargs: None,
                )

            def markdown(self, *args, **kwargs):
                return None

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def data_editor(self, *args, **kwargs):
                return [edited]

            def form(self, *args, **kwargs):
                return FakePopover()

            def form_submit_button(self, *args, **kwargs):
                return False

            def file_uploader(self, *args, **kwargs):
                return None

            def button(self, *args, **kwargs):
                return False

        fake_st = FakeStreamlit()
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_write_snapshot", side_effect=AssertionError("Edition Ops render must not write local JSON.")
        ), patch.object(
            edition_ops.shopify_sync,
            "fetch_edition_ops_active_products",
            side_effect=AssertionError("Edition Ops render must not call Shopify."),
        ), patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Edition Ops render must not run schema DDL."),
        ):
            edition_ops.render_page()

        self.assertEqual(fake_st.session_state[edition_ops.ROWS_KEY][0]["edition_next_number"], 52)

    def test_edition_ops_save_changes_updates_supabase_and_shopify_once(self):
        class FakeContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeBackend:
            def __init__(self):
                self.supabase_calls = 0
                self.shopify_calls = 0

            def update_edition_products_batch(self, rows, reason=""):
                self.supabase_calls += 1
                self.saved_rows = rows
                return [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}]

            def sync_edition_ops_metafields_for_rows(self, rows, config=None, ensure_schema_first=True):
                self.shopify_calls += 1
                self.mirrored_rows = rows
                return {
                    "attempted": 1,
                    "synced": 1,
                    "skipped": 0,
                    "errors": [],
                    "results": [
                        {
                            "row_key": rows[0]["row_key"],
                            "handle": rows[0]["handle"],
                            "status": "updated",
                            "ok": True,
                        }
                    ],
                }

        class FakeColumn:
            def __init__(self, fake_st):
                self.fake_st = fake_st

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def button(self, label, *args, **kwargs):
                return False

            def download_button(self, *args, **kwargs):
                return None

            def popover(self, *args, **kwargs):
                return FakeContext()

        class FakeSlot:
            def __init__(self, fake_st):
                self.fake_st = fake_st

            def caption(self, message):
                self.fake_st.captions.append(message)

            def button(self, label, *args, **kwargs):
                return False

            def container(self):
                return FakeContext()

        class FakeStreamlit:
            def __init__(self):
                self.clicked = False
                self.buttons = []
                self.captions = []
                self.column_config = SimpleNamespace(
                    TextColumn=lambda *args, **kwargs: None,
                    CheckboxColumn=lambda *args, **kwargs: None,
                    NumberColumn=lambda *args, **kwargs: None,
                    LinkColumn=lambda *args, **kwargs: None,
                )
                self.session_state = {
                    edition_ops.SNAPSHOT_LOADED_KEY: True,
                    edition_ops.ROWS_KEY: [
                        {
                            "edition_product_id": "ep-1",
                            "shopify_product_gid": "gid://shopify/Product/100",
                            "product_title": "Wall Art",
                            "handle": "wall-art",
                            "edition_enabled": True,
                            "edition_total": 100,
                            "edition_next_number": 10,
                            "edition_sold_count": 9,
                            "edition_remaining": 91,
                            "edition_status": "Limited Edition",
                            "sync_status": "Loaded",
                            "sync_error": "",
                        }
                    ],
                    edition_ops.ORIGINAL_ROWS_KEY: [
                        {
                            "edition_product_id": "ep-1",
                            "shopify_product_gid": "gid://shopify/Product/100",
                            "product_title": "Wall Art",
                            "handle": "wall-art",
                            "edition_enabled": True,
                            "edition_total": 100,
                            "edition_next_number": 9,
                            "edition_sold_count": 8,
                            "edition_remaining": 92,
                            "edition_status": "Limited Edition",
                            "sync_status": "Loaded",
                            "sync_error": "",
                        }
                    ],
                    edition_ops.META_KEY: {},
                    edition_ops.ERRORS_KEY: {},
                    edition_ops.IMPORT_WARNINGS_KEY: [],
                    edition_ops.NOTICE_KEY: "",
                    edition_ops.NOTICE_LEVEL_KEY: "success",
                    edition_ops.EDITOR_VERSION_KEY: 0,
                }

            def markdown(self, *args, **kwargs):
                return None

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

            def error(self, *args, **kwargs):
                return None

            def columns(self, spec):
                return [FakeColumn(self) for _ in spec]

            def empty(self):
                return FakeSlot(self)

            def data_editor(self, rows, *args, **kwargs):
                return rows

            def form(self, *args, **kwargs):
                return FakeContext()

            def form_submit_button(self, label, *args, **kwargs):
                self.buttons.append((label, kwargs))
                if label == "Save Changes" and not self.clicked:
                    self.clicked = True
                    return True
                return False

            def spinner(self, *args, **kwargs):
                return FakeContext()

            def rerun(self):
                raise AssertionError("Edition Ops save should not force a rerun.")

        fake_st = FakeStreamlit()
        fake_backend = FakeBackend()
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops,
            "_configured_supabase_backend",
            return_value=fake_backend,
        ), patch.object(
            edition_ops.shopify_sync,
            "get_config",
            return_value={"configured": True},
        ), patch.object(edition_ops, "_write_snapshot"), patch.object(edition_ops, "_invalidate_edition_ops_cache"):
            edition_ops.render_page()

        self.assertEqual(fake_backend.supabase_calls, 1)
        self.assertEqual(fake_backend.shopify_calls, 1)
        self.assertEqual(fake_backend.saved_rows[0]["next_edition_number"], 10)
        self.assertEqual(fake_backend.mirrored_rows[0]["edition_next_number"], 10)
        self.assertIn(("Save Changes", {"type": "primary", "use_container_width": True, "disabled": False, "key": "edition-ops-save-changes"}), fake_st.buttons)

    def test_orders_page_open_renders_snapshot_without_shopify_or_allocation_work(self):
        class FakeContainer:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeColumn:
            def button(self, *args, **kwargs):
                return False

            def link_button(self, *args, **kwargs):
                return None

            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

            def checkbox(self, *args, **kwargs):
                return False

            def checkbox(self, *args, **kwargs):
                return False

            def checkbox(self, *args, **kwargs):
                return False

            def caption(self, *args, **kwargs):
                return None

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {}
                self.column_config = SimpleNamespace(
                    TextColumn=lambda *args, **kwargs: None,
                    NumberColumn=lambda *args, **kwargs: None,
                    LinkColumn=lambda *args, **kwargs: None,
                )
                self.rendered_rows = None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def container(self, *args, **kwargs):
                return FakeContainer()

            def dataframe(self, rows, **kwargs):
                self.rendered_rows = rows

            def checkbox(self, label, value=False, key=None, **kwargs):
                if key is not None and key not in self.session_state:
                    self.session_state[key] = value
                return self.session_state.get(key, value)

            def text_input(self, label, value="", key=None, **kwargs):
                if key is not None and key not in self.session_state:
                    self.session_state[key] = value
                return self.session_state.get(key, value)

            def expander(self, *args, **kwargs):
                return FakeContainer()

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

            def markdown(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        snapshot = {
            "rows": [
                {
                    "order": "#SC1234",
                    "date": "2026-06-22",
                    "customer": "John",
                    "edition": "#013",
                    "certificate": "Generate",
                    "shipping": "Standard",
                    "product": "Justin Gaethje",
                    "variant": "Black",
                    "shopify_order_id": "gid://shopify/Order/1",
                    "shopify_line_item_id": "gid://shopify/LineItem/1",
                    "shopify_product_id": "gid://shopify/Product/1",
                }
            ],
            "last_refreshed": "2026-06-22T10:00:00Z",
            "saved_at": "2026-06-22T10:00:01Z",
        }

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page.order_allocator,
            "load_orders_snapshot",
            return_value=snapshot,
        ), patch.object(
            orders_page.order_allocator,
            "load_cutover_state",
            side_effect=AssertionError("Orders page open must not read allocation settings."),
        ), patch.object(
            orders_page.shopify_sync,
            "iter_order_pages",
            side_effect=AssertionError("Orders page open must not fetch Shopify orders."),
        ), patch.object(
            orders_page.shopify_sync,
            "fetch_metafields",
            side_effect=AssertionError("Orders page open must not fetch metafields."),
        ), patch.object(
            orders_page.order_allocator,
            "process_shopify_orders_for_editions",
            side_effect=AssertionError("Orders page open must not allocate."),
        ), patch.object(
            orders_page.certificate_engine,
            "read_order_certificate_state",
            side_effect=AssertionError("Orders page open must not fetch certificates."),
        ), patch.object(
            orders_page.shopify_sync,
            "fetch_edition_ops_active_products",
            side_effect=AssertionError("Orders page open must not fetch product baselines."),
        ):
            orders_page.render_page()

        self.assertEqual(fake_st.rendered_rows[0]["order"], f"{orders_page.COPY_ORDER_ICON} #SC1234")
        self.assertEqual(set(fake_st.rendered_rows[0]), set(orders_page.VISIBLE_COLUMNS))

    def test_orders_page_prefers_supabase_ledger_rows_when_available(self):
        class FakeContainer:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeColumn:
            def button(self, *args, **kwargs):
                return False

            def link_button(self, *args, **kwargs):
                return None

            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

            def checkbox(self, *args, **kwargs):
                return False

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {}
                self.column_config = SimpleNamespace(
                    TextColumn=lambda *args, **kwargs: None,
                    NumberColumn=lambda *args, **kwargs: None,
                    LinkColumn=lambda *args, **kwargs: None,
                )
                self.rendered_rows = None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def container(self, *args, **kwargs):
                return FakeContainer()

            def dataframe(self, rows, **kwargs):
                self.rendered_rows = rows

            def checkbox(self, label, value=False, key=None, **kwargs):
                if key is not None and key not in self.session_state:
                    self.session_state[key] = value
                return self.session_state.get(key, value)

            def text_input(self, label, value="", key=None, **kwargs):
                if key is not None and key not in self.session_state:
                    self.session_state[key] = value
                return self.session_state.get(key, value)

            def expander(self, *args, **kwargs):
                return FakeContainer()

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

            def markdown(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        snapshot = {
            "source": "supabase",
            "order_count": 95,
            "rows": [
                {
                    "order": "#SC2843",
                    "date": "2026-06-23",
                    "customer": "Ashkan Zand",
                    "edition": "#050",
                    "certificate": "Generate",
                    "shipping": "US Standard Tracked Shipping",
                    "product": "GOAT Debate Wall Art",
                    "variant": "Black / L",
                    "shopify_order_id": "gid://shopify/Order/2843",
                    "shopify_line_item_id": "gid://shopify/LineItem/1",
                    "shopify_product_id": "gid://shopify/Product/1",
                }
            ],
            "last_refreshed": "2026-06-25T08:00:00Z",
            "saved_at": "2026-06-25T08:00:01Z",
        }

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=object(),
        ), patch.object(
            orders_page.order_allocator,
            "load_hybrid_orders_snapshot",
            return_value=snapshot,
        ), patch.object(
            orders_page.order_allocator,
            "load_supabase_orders_snapshot",
            side_effect=AssertionError("Orders page should use hybrid read when enabled."),
        ), patch.object(
            orders_page.order_allocator,
            "load_orders_snapshot",
            side_effect=AssertionError("Orders page should not fall back when Supabase ledger is available."),
        ), patch.object(
            orders_page,
            "_render_ledger_diagnostics",
            return_value=None,
        ):
            orders_page.render_page()

        self.assertEqual(fake_st.rendered_rows[0]["order"], f"{orders_page.COPY_ORDER_ICON} #SC2843")
        self.assertEqual(fake_st.rendered_rows[0]["edition"], "#050")

    def test_orders_reads_hybrid_supabase_directly_without_shopify(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.LOAD_ERROR_KEY: "",
            }
        )
        payload = {
            "source": "supabase",
            "rows": [{"order": "#SC2843", "edition_number": 50}],
            "saved_at": "2026-06-25T08:01:00Z",
        }

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=object(),
        ), patch.object(
            orders_page.order_allocator,
            "load_hybrid_orders_snapshot",
            return_value=payload,
        ) as direct_read:
            payload = orders_page._read_orders_snapshot()

        direct_read.assert_called_once_with(limit=50, search="")
        self.assertEqual(payload["rows"][0]["order"], "#SC2843")

    def test_hybrid_orders_overlay_protects_goat_supabase_editions(self):
        class FakeSupabase:
            def list_hybrid_order_rows(self, **kwargs):
                self.kwargs = kwargs
                return [
                    {
                        "shopify_order_id": "gid://shopify/Order/2843",
                        "order_name": "#SC2843",
                        "customer_name": "Ashkan Zand",
                        "customer_email": "ashkan@example.com",
                        "processed_at": "2026-06-23T10:00:00Z",
                        "created_at": "2026-06-23T09:55:00Z",
                        "order_raw_json": {
                            "shipping_method": "US Standard Tracked Shipping",
                            "line_items": [
                                {
                                    "shopify_line_item_id": "gid://shopify/LineItem/goat",
                                    "product_title": "GOAT Debate Wall Art",
                                    "variant_title": "Black / L",
                                    "custom_attributes": [
                                        {"key": "edition_number", "value": "#094/100"},
                                        {"key": "edition_number", "value": "#095/100"},
                                    ],
                                }
                            ],
                        },
                        "shopify_line_item_id": "gid://shopify/LineItem/goat",
                        "shopify_product_id": "gid://shopify/Product/goat",
                        "shopify_handle": "goat-debate-wall-art",
                        "product_title": "GOAT Debate Wall Art",
                        "variant_title": "Black / L",
                        "quantity": 2,
                        "assignments": [
                            {
                                "edition_order_id": "eo-50",
                                "edition_number": 50,
                                "edition_total": 100,
                                "allocation_index": 1,
                                "assignment_status": "assigned",
                            },
                            {
                                "edition_order_id": "eo-51",
                                "edition_number": 51,
                                "edition_total": 100,
                                "allocation_index": 2,
                                "assignment_status": "assigned",
                            },
                        ],
                    }
                ]

            def get_sync_state_read_only(self):
                return {"last_successful_order_fetch_at": "2026-06-25T08:00:00Z"}

        fake_backend = FakeSupabase()
        with patch.object(order_allocator, "_configured_supabase_backend", return_value=fake_backend):
            snapshot = order_allocator.load_hybrid_orders_snapshot(limit=1000)

        editions = [orders_page._normalise_row(row)["edition"] for row in snapshot["rows"]]
        self.assertEqual(editions, ["#051/100", "#050/100"])
        self.assertNotIn("#094/100", editions)
        self.assertNotIn("#095/100", editions)
        self.assertEqual(snapshot["source"], "shopify_mirror_supabase_edition_ledger")

    def test_orders_normal_render_does_not_call_shopify_or_schema_writes(self):
        class FakeContainer:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeColumn:
            def button(self, *args, **kwargs):
                return False

            def link_button(self, *args, **kwargs):
                return None

            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {}
                self.column_config = SimpleNamespace(TextColumn=lambda *args, **kwargs: None)
                self.rendered_rows = None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def container(self, *args, **kwargs):
                return FakeContainer()

            def dataframe(self, rows, **kwargs):
                self.rendered_rows = rows

            def text_input(self, label, value="", key=None, **kwargs):
                if key is not None and key not in self.session_state:
                    self.session_state[key] = value
                return self.session_state.get(key, value)

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        snapshot = {
            "source": "shopify_mirror_supabase_edition_ledger",
            "rows": [
                {
                    "order": "#SC2843",
                    "edition_number": 50,
                    "edition_total": 100,
                    "customer": "Ashkan Zand",
                    "product": "GOAT Debate Wall Art",
                    "variant": "Black / L",
                    "shipping": "Standard",
                }
            ],
        }

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page, "_configured_supabase_backend", return_value=object()
        ), patch.object(
            orders_page.order_allocator, "load_hybrid_orders_snapshot", return_value=snapshot
        ), patch.object(
            orders_page.shopify_sync,
            "iter_order_pages",
            side_effect=AssertionError("Orders render must not call Shopify."),
        ), patch.object(
            supabase_backend,
            "ensure_order_read_schema",
            side_effect=AssertionError("Orders render must not run schema DDL."),
        ), patch.object(
            supabase_backend,
            "ensure_schema",
            side_effect=AssertionError("Orders render must not run full schema."),
        ):
            orders_page.render_page()

        self.assertEqual(fake_st.rendered_rows[0]["edition"], "#050/100")

    def test_pure_read_loaders_do_not_run_schema_or_repair_guards(self):
        hybrid_source = inspect.getsource(supabase_backend.list_hybrid_order_rows)
        edition_source = inspect.getsource(supabase_backend.list_edition_products_read_only)

        self.assertNotIn("ensure_order_read_schema", hybrid_source)
        self.assertNotIn("ensure_schema", hybrid_source)
        self.assertNotIn("_ensure_active_edition_runs_for_products", hybrid_source)
        self.assertNotIn("ensure_schema", edition_source)
        self.assertNotIn("_ensure_active_edition_runs_for_products", edition_source)

    def test_orders_supabase_read_error_is_not_reported_as_empty_ledger(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [{"order": "#old"}],
                orders_page.META_KEY: {},
                orders_page.LOAD_ERROR_KEY: "",
            }
        )

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=object(),
        ), patch.object(
            orders_page.order_allocator,
            "load_hybrid_orders_snapshot",
            side_effect=RuntimeError("connection dropped"),
        ), patch.object(orders_page.order_allocator, "load_orders_snapshot", return_value=None):
            orders_page._load_snapshot_once()

        self.assertEqual(fake_st.session_state[orders_page.ROWS_KEY], [])
        self.assertEqual(fake_st.session_state[orders_page.META_KEY]["source"], "supabase_error")
        self.assertIn("connection dropped", fake_st.session_state[orders_page.META_KEY]["error"])
        self.assertIn("connection dropped", fake_st.session_state[orders_page.LOAD_ERROR_KEY])

    def test_orders_missing_ledger_fields_use_placeholder_and_count(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC9999",
                "date": "2026-06-25",
                "customer": "",
                "customer_email": "",
                "edition_total": 100,
                "shipping": "",
                "product": "",
                "variant": "",
            }
        )

        counts = orders_page._missing_data_counts([row])

        self.assertEqual(row["customer"], "Missing from ledger")
        self.assertEqual(row["shipping"], "Missing shipping")
        self.assertEqual(row["product"], "Missing from ledger")
        self.assertEqual(row["variant"], "Missing variant")
        self.assertEqual(row["prodigi"], "Needs certificate")
        self.assertEqual(counts["missing_customer"], 1)
        self.assertEqual(counts["missing_shipping"], 1)
        self.assertEqual(counts["missing_product"], 1)
        self.assertEqual(counts["missing_variant"], 1)
        self.assertEqual(counts["missing_edition_number"], 1)

    def test_order_allocator_loads_orders_snapshot_from_supabase_cache(self):
        class FakeSupabase:
            def list_orders(self, **kwargs):
                self.kwargs = kwargs
                return [
                    {
                        "shopify_order_id": "gid://shopify/Order/2843",
                        "order_name": "#SC2843",
                        "customer_name": "Ashkan Zand",
                        "customer_email": "ashkan@example.com",
                        "processed_at": "2026-06-23T10:00:00Z",
                        "created_at": "2026-06-23T09:55:00Z",
                        "order_raw_json": {"shipping_method": "US Standard Tracked Shipping"},
                        "shopify_line_item_id": "gid://shopify/LineItem/1",
                        "shopify_product_id": "gid://shopify/Product/1",
                        "shopify_handle": "goat-debate-wall-art",
                        "product_title": "GOAT Debate Wall Art",
                        "variant_title": "Black / L",
                        "quantity": 1,
                        "assignments": [
                            {
                                "edition_number": 50,
                                "edition_total": 100,
                                "allocation_index": 1,
                                "certificate_status": "Certificate Missing",
                            }
                        ],
                    }
                ]

            def get_sync_state(self):
                return {"last_successful_order_fetch_at": "2026-06-24T01:00:00Z"}

            def get_order_summary(self):
                self.summary_called = True
                return {"orders_synced": 12}

        fake_backend = FakeSupabase()
        with patch.object(order_allocator, "_configured_supabase_backend", return_value=fake_backend):
            snapshot = order_allocator.load_supabase_orders_snapshot(limit=150)

        self.assertEqual(snapshot["source"], "supabase")
        self.assertEqual(snapshot["order_count"], 12)
        self.assertEqual(snapshot["last_refreshed"], "2026-06-24T01:00:00Z")
        self.assertEqual(snapshot["rows"][0]["edition"], "#050")
        self.assertEqual(snapshot["rows"][0]["certificate_status"], "")
        self.assertEqual(fake_backend.kwargs["limit"], 150)
        self.assertTrue(fake_backend.summary_called)

    def test_order_allocator_loads_orders_snapshot_without_summary_for_fast_orders_page(self):
        class FakeSupabase:
            def __init__(self):
                self.summary_called = False

            def list_orders(self, **kwargs):
                return [
                    {
                        "shopify_order_id": "gid://shopify/Order/2843",
                        "order_name": "#SC2843",
                        "customer_name": "Ashkan Zand",
                        "customer_email": "ashkan@example.com",
                        "processed_at": "2026-06-23T10:00:00Z",
                        "created_at": "2026-06-23T09:55:00Z",
                        "shopify_line_item_id": "gid://shopify/LineItem/1",
                        "shopify_product_id": "gid://shopify/Product/1",
                        "shopify_handle": "goat-debate-wall-art",
                        "product_title": "GOAT Debate Wall Art",
                        "variant_title": "Black / L",
                        "quantity": 1,
                        "assignments": [],
                    }
                ]

            def get_sync_state(self):
                return {"last_successful_order_fetch_at": "2026-06-24T01:00:00Z"}

            def get_order_summary(self):
                self.summary_called = True
                return {"orders_synced": 12}

        fake_backend = FakeSupabase()
        with patch.object(order_allocator, "_configured_supabase_backend", return_value=fake_backend):
            snapshot = order_allocator.load_supabase_orders_snapshot(limit=150, include_summary=False)

        self.assertEqual(snapshot["order_count"], 1)
        self.assertFalse(fake_backend.summary_called)

    def test_refresh_orders_dry_run_uses_supabase_preview_only(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def __init__(self):
                self.preview_calls = []

            def preview_latest_paid_orders_sync(self, **kwargs):
                self.preview_calls.append(kwargs)
                return {
                    "mode": "latest_paid_dry_run",
                    "shopify_orders_fetched": 3,
                    "new_orders_inserted": 2,
                    "edition_allocations_created": 4,
                }

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Dry-run should not reload rows from a write path."),
        ):
            orders_page._preview_latest_paid_orders(limit=25)

        self.assertEqual(backend.preview_calls, [{"limit": 25}])
        self.assertEqual(fake_st.session_state[orders_page.LATEST_FETCH_PREVIEW_KEY]["mode"], "latest_paid_dry_run")
        self.assertIn("fetched preview for 3 latest paid shopify order(s)", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        return

    def test_refresh_orders_apply_uses_supabase_sync_path_and_refreshes_changed_rows(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def __init__(self):
                self.sync_calls = []

            def sync_latest_paid_orders_to_supabase(self, **kwargs):
                self.sync_calls.append(kwargs)
                return {
                    "shopify_orders_fetched": 5,
                    "new_orders_inserted": 1,
                    "new_lines_inserted": 1,
                    "existing_orders_skipped": 4,
                    "edition_allocations_created": 2,
                    "missing_mapping_skipped": 0,
                    "affected_order_names": ["#SC2879"],
                    "affected_shopify_order_ids": ["gid://shopify/Order/2879"],
                    "errors": [],
                }

        def fake_reload():
            fake_st.session_state[orders_page.ROWS_KEY] = [
                {
                    "order": "#SC2879",
                    "shopify_order_id": "gid://shopify/Order/2879",
                    "edition_number": 35,
                    "edition_total": 100,
                }
            ]

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=fake_reload,
        ) as reload_rows:
            orders_page._refresh_orders(max_orders=25)

        self.assertEqual(
            backend.sync_calls,
            [{"limit": 25, "backfill_latest_paid": False, "ensure_schema_first": False}],
        )
        reload_rows.assert_called_once()
        self.assertIn("cursor check complete", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        self.assertIn("new orders imported: 1", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        self.assertIn("table refresh: refreshed", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        self.assertEqual(fake_st.session_state[orders_page.SYNC_RESULT_KEY]["affected_rows_merged_count"], 1)
        self.assertEqual(fake_st.session_state[orders_page.ROWS_KEY][0]["order"], "#SC2879")
        return

    def test_refresh_orders_no_changes_defers_table_reload(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def sync_latest_paid_orders_to_supabase(self, **kwargs):
                self.kwargs = kwargs
                return {
                    "shopify_orders_fetched": 1,
                    "new_orders_inserted": 0,
                    "new_lines_inserted": 0,
                    "existing_orders_skipped": 1,
                    "edition_allocations_created": 0,
                    "missing_mapping_skipped": 0,
                    "errors": [],
                }

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Unchanged sync should not reload the table."),
        ):
            orders_page._refresh_orders(max_orders=25)

        self.assertEqual(
            backend.kwargs,
            {"limit": 25, "backfill_latest_paid": False, "ensure_schema_first": False},
        )
        self.assertIn("table refresh: deferred", fake_st.session_state[orders_page.NOTICE_KEY].lower())

    def test_refresh_orders_timeout_returns_retry_message_and_clears_state(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def sync_latest_paid_orders_to_supabase(self, **kwargs):
                return {}

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=FakeBackend(),
        ), patch.object(
            orders_page,
            "_run_sync_with_timeout",
            side_effect=TimeoutError("Orders sync failed: sync timed out at backend_sync. You can retry."),
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Timed out sync must not reload rows."),
        ):
            orders_page._refresh_orders(max_orders=25)

        self.assertIn("sync timed out at backend_sync", fake_st.session_state[orders_page.NOTICE_KEY])
        self.assertIn("retry", fake_st.session_state[orders_page.NOTICE_KEY].casefold())

    def test_orders_live_refresh_checks_supabase_only_and_reloads_on_marker_change(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ORDERS_SUPABASE_LIVE_MARKER_KEY: "1|2026-06-29T01:00:00Z",
                orders_page.CERTIFICATE_ACTION_LOADING_KEY: False,
                orders_page.CERTIFICATE_ACTION_STATE_KEY: {},
            },
            rerun=Mock(),
        )

        class FakeBackend:
            def orders_visibility_marker(self, **kwargs):
                self.kwargs = kwargs
                return {"marker": "2|2026-06-29T02:00:00Z"}

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
        ) as reload_rows, patch.object(
            shopify_sync,
            "fetch_latest_paid_orders",
            side_effect=AssertionError("Orders live refresh must not call Shopify."),
        ):
            orders_page._check_orders_supabase_live_refresh()

        self.assertEqual(backend.kwargs, {"ensure_schema_first": False})
        reload_rows.assert_called_once()
        fake_st.rerun.assert_called_once()
        self.assertEqual(
            fake_st.session_state[orders_page.ORDERS_SUPABASE_LIVE_MARKER_KEY],
            "2|2026-06-29T02:00:00Z",
        )

    def test_refresh_orders_backfill_mode_is_explicit(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def __init__(self):
                self.sync_calls = []

            def sync_latest_paid_orders_to_supabase(self, **kwargs):
                self.sync_calls.append(kwargs)
                return {
                    "shopify_orders_fetched": 5,
                    "new_orders_inserted": 0,
                    "new_lines_inserted": 0,
                    "existing_orders_skipped": 5,
                    "edition_allocations_created": 0,
                    "missing_mapping_skipped": 0,
                    "errors": [],
                }

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Backfill sync should still defer the full table reload by default."),
        ):
            orders_page._refresh_orders(max_orders=25, backfill_latest_paid=True)

        self.assertEqual(
            backend.sync_calls,
            [{"limit": 25, "backfill_latest_paid": True, "ensure_schema_first": False}],
        )
        self.assertIn("backfill complete", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        self.assertIn("table refresh: deferred", fake_st.session_state[orders_page.NOTICE_KEY].lower())
        return

    def test_sync_diagnostics_hidden_on_normal_orders_page(self):
        class FakeColumn:
            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {
                    orders_page.ROWS_KEY: [{"order": "#SC3002", "edition_number": 62}],
                    orders_page.META_KEY: {"last_refreshed": "2026-06-29T06:00:00Z"},
                    orders_page.SYNC_RESULT_KEY: {"shopify_orders_fetched": 2},
                    orders_page.NOTICE_KEY: "",
                }

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def info(self, *args, **kwargs):
                return None

            def error(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page, "_load_snapshot_once"
        ), patch.object(
            orders_page, "_configured_supabase_backend", return_value=object()
        ), patch.object(
            orders_page, "_render_top_actions"
        ), patch.object(
            orders_page, "_render_orders_table"
        ), patch.object(
            orders_page,
            "_render_sync_diagnostics",
            side_effect=AssertionError("Normal Orders page must not show detailed sync diagnostics."),
        ) as diagnostics:
            orders_page.render_page()

        diagnostics.assert_not_called()

    def test_sync_diagnostics_available_when_developer_unlocked(self):
        class FakeColumn:
            def text_input(self, *args, **kwargs):
                return ""

            def caption(self, *args, **kwargs):
                return None

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {
                    orders_page.ROWS_KEY: [{"order": "#SC3002", "edition_number": 62}],
                    orders_page.META_KEY: {"last_refreshed": "2026-06-29T06:00:00Z"},
                    orders_page.SYNC_RESULT_KEY: {"shopify_orders_fetched": 2},
                    orders_page.NOTICE_KEY: "",
                    "developer_unlocked": True,
                }

            def title(self, *args, **kwargs):
                return None

            def caption(self, *args, **kwargs):
                return None

            def columns(self, spec):
                return [FakeColumn() for _ in spec]

            def info(self, *args, **kwargs):
                return None

            def error(self, *args, **kwargs):
                return None

            def success(self, *args, **kwargs):
                return None

        fake_st = FakeStreamlit()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page, "_load_snapshot_once"
        ), patch.object(
            orders_page, "_configured_supabase_backend", return_value=object()
        ), patch.object(
            orders_page, "_render_top_actions"
        ), patch.object(
            orders_page, "_render_orders_table"
        ), patch.object(
            orders_page, "_render_sync_diagnostics"
        ) as diagnostics:
            orders_page.render_page()

        diagnostics.assert_called_once_with({"shopify_orders_fetched": 2})

    def test_latest_paid_sync_allocates_without_historical_tracking_guard(self):
        latest_sync_source = inspect.getsource(supabase_backend.sync_latest_paid_orders_to_supabase)
        preview_source = inspect.getsource(supabase_backend.preview_latest_paid_orders_sync)
        general_sync_source = inspect.getsource(supabase_backend.sync_shopify_orders_to_supabase)
        perf_log_source = inspect.getsource(supabase_backend._sync_perf_log)

        self.assertIn("_latest_paid_order_needs_sync", latest_sync_source)
        self.assertIn("list_existing_shopify_order_states", latest_sync_source)
        self.assertIn(
            "apply_known_missing_edition_repair(ensure_schema_first=ensure_schema_first)",
            latest_sync_source,
        )
        self.assertIn("process_shopify_order_for_editions", latest_sync_source)
        self.assertIn("fetch_missing_products=False", latest_sync_source)
        self.assertIn("assign_editions=True", latest_sync_source)
        self.assertIn("generate_certificates=False", latest_sync_source)
        self.assertIn("sync_product_metafields=False", latest_sync_source)
        self.assertIn("PERF Sync Orders:", perf_log_source)
        self.assertIn("Supabase existing-order lookup time", latest_sync_source)
        self.assertIn("Shopify metafield mirror/update time", latest_sync_source)
        self.assertNotIn("sync_shopify_orders_to_supabase(", latest_sync_source)
        self.assertIn("respect_tracking_start=False", preview_source)
        self.assertIn("_sync_perf_log", preview_source)
        self.assertIn("respect_tracking_start=True", general_sync_source)

    def test_missing_edition_repair_preview_is_chronological(self):
        source = inspect.getsource(supabase_backend._missing_edition_candidate_rows)
        repair_source = inspect.getsource(supabase_backend.repair_missing_edition_orders)

        self.assertIn("COALESCE(o.created_at, o.processed_at, o.synced_at) ASC", source)
        self.assertIn("o.order_name ASC", source)
        self.assertNotIn("o.order_name DESC", source)
        self.assertIn("respect_tracking_start=False", repair_source)

    def test_backfill_missing_order_details_dry_run_is_read_only(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [],
                orders_page.META_KEY: {"last_refreshed": "", "saved_at": ""},
                orders_page.NOTICE_KEY: "",
                orders_page.SYNC_RESULT_KEY: {},
                orders_page.BACKFILL_RESULT_KEY: {},
            }
        )

        class FakeBackend:
            def backfill_missing_shopify_order_details(self, **kwargs):
                self.kwargs = kwargs
                return {
                    "mode": "dry_run",
                    "orders_updated": 2,
                    "variant_rows_filled": 6,
                    "shipping_rows_filled": 2,
                }

        backend = FakeBackend()
        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            orders_page,
            "_reload_orders_from_source",
            side_effect=AssertionError("Dry-run backfill should not reload rows from a write path."),
        ):
            orders_page._backfill_missing_order_details(dry_run=True, limit=50)

        self.assertEqual(backend.kwargs, {"limit": 50, "dry_run": True})
        self.assertEqual(fake_st.session_state[orders_page.BACKFILL_RESULT_KEY]["mode"], "dry_run")
        self.assertIn("dry-run", fake_st.session_state[orders_page.NOTICE_KEY].lower())

    def test_orders_page_formats_single_edition_numbers(self):
        self.assertEqual(orders_page._format_edition("50"), "#050")
        self.assertEqual(orders_page._format_edition("#50"), "#050")
        self.assertEqual(orders_page._format_edition("050"), "#050")
        self.assertEqual(orders_page._format_edition("#050/100"), "#050")
        self.assertEqual(orders_page._format_edition(""), "")

    def test_orders_page_splits_quantity_rows_into_one_artwork_per_edition(self):
        line_item_id = "gid://shopify/LineItem/1"
        order = {
            "order_name": "#SC1234",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Express Shipping",
            "metafields": [
                {
                    "namespace": "sports_cave",
                    "key": "edition_allocations",
                    "value": json.dumps({"line_items": {line_item_id: {"edition_numbers": [50, 51]}}}),
                }
            ],
        }
        line_item = {
            "shopify_line_item_id": line_item_id,
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 2,
        }

        rows = orders_page._rows_from_order_line(order, line_item, {"edition_next_number": 91})

        self.assertEqual([row["edition"] for row in rows], ["#050/100", "#051/100"])
        self.assertTrue(all("qty" not in {column.lower() for column in orders_page.VISIBLE_COLUMNS} for _ in rows))

    def test_orders_page_does_not_use_product_next_number_when_no_saved_allocation(self):
        order = {
            "order_name": "#SC1235",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Standard Shipping",
            "metafields": [],
        }
        line_item = {
            "shopify_line_item_id": "gid://shopify/LineItem/2",
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 2,
        }

        rows = orders_page._rows_from_order_line(order, line_item, {"edition_next_number": 91})

        self.assertEqual([row["edition"] for row in rows], ["Needs edition", "Needs edition"])
        self.assertEqual([row["certificate"] for row in rows], ["Needs certificate", "Needs certificate"])

    def test_orders_page_marks_unallocated_sold_out_rows_for_review(self):
        order = {
            "order_name": "#SC1235",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Standard Shipping",
            "metafields": [],
        }
        line_item = {
            "shopify_line_item_id": "gid://shopify/LineItem/2",
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 1,
        }

        rows = orders_page._rows_from_order_line(
            order,
            line_item,
            {
                "edition_total": 100,
                "edition_next_number": 100,
                "edition_sold_count": 100,
                "edition_remaining": 0,
            },
        )

        self.assertEqual(rows[0]["edition"], "Needs Review - Sold Out")
        self.assertEqual(rows[0]["certificate"], "Needs Review - Sold Out")

    def test_orders_page_restores_certificate_local_paths_from_saved_metafield(self):
        line_item_id = "gid://shopify/LineItem/1"
        order = {
            "order_name": "#SC1234",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Express Shipping",
            "metafields": [
                {
                    "namespace": "sports_cave",
                    "key": "edition_allocations",
                    "value": json.dumps({"line_items": {line_item_id: {"edition_numbers": [50]}}}),
                },
                {
                    "namespace": "sports_cave",
                    "key": "certificates",
                    "value": json.dumps(
                        [
                            {
                                "line_item_id": line_item_id,
                                "line_item_unit_index": 1,
                                "edition_number": 50,
                                "status": "Ready",
                                "pdf_url": "https://cdn.example/certificate.pdf",
                                "local_pdf_path": "C:/certificates/certificate.pdf",
                                "preview_path": "C:/certificates/certificate.png",
                            }
                        ]
                    ),
                },
            ],
        }
        line_item = {
            "shopify_line_item_id": line_item_id,
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 1,
        }

        rows = orders_page._rows_from_order_line(order, line_item, {"edition_next_number": 91})

        self.assertEqual(rows[0]["certificate"], "Uploaded")
        self.assertEqual(rows[0]["certificate_pdf_url"], "https://cdn.example/certificate.pdf")
        self.assertEqual(rows[0]["certificate_pdf_path"], "C:/certificates/certificate.pdf")
        self.assertEqual(rows[0]["certificate_preview_path"], "C:/certificates/certificate.png")

    def test_orders_page_preserves_local_certificate_paths_when_refresh_has_remote_pdf_url(self):
        line_item_id = "gid://shopify/LineItem/1"
        refreshed = orders_page._rows_from_order_line(
            {
                "order_name": "#SC1234",
                "processed_at": "2026-06-22T10:00:00Z",
                "customer_name": "John",
                "metafields": [
                    {
                        "namespace": "sports_cave",
                        "key": "edition_allocations",
                        "value": json.dumps({"line_items": {line_item_id: {"edition_numbers": [50]}}}),
                    },
                    {
                        "namespace": "sports_cave",
                        "key": "certificates",
                        "value": json.dumps(
                            [
                                {
                                    "line_item_id": line_item_id,
                                    "line_item_unit_index": 1,
                                    "edition_number": 50,
                                    "status": "Ready",
                                    "pdf_url": "https://cdn.example/certificate.pdf",
                                }
                            ]
                        ),
                    },
                ],
            },
            {
                "shopify_line_item_id": line_item_id,
                "shopify_product_id": "gid://shopify/Product/1",
                "product_title": "Shane Warne Tribute Wall Art",
                "variant_title": "Black / XL",
                "quantity": 1,
            },
            {"edition_next_number": 91},
        )
        existing = [
            {
                **refreshed[0],
                "certificate_pdf_path": "C:/certificates/certificate.pdf",
                "certificate_preview_path": "C:/certificates/certificate.png",
            }
        ]

        merged = orders_page._merge_local_certificate_fields(refreshed, existing)

        self.assertEqual(merged[0]["certificate_pdf_url"], "https://cdn.example/certificate.pdf")
        self.assertEqual(merged[0]["certificate_pdf_path"], "C:/certificates/certificate.pdf")
        self.assertEqual(merged[0]["certificate_preview_path"], "C:/certificates/certificate.png")

    def test_orders_page_certificate_record_uses_exact_visible_row_edition(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC1234",
                "date": "2026-06-22",
                "customer": "Greg Collector",
                "customer_email": "greg@example.com",
                "product": "Greg Murphy Lap of the Gods Wall Art",
                "variant": "Black / XL",
                "edition_number": 16,
                "edition_total": 100,
                "shopify_order_id": "gid://shopify/Order/1234",
                "shopify_line_item_id": "gid://shopify/LineItem/555",
                "shopify_product_id": "gid://shopify/Product/777",
                "variant_id": "gid://shopify/ProductVariant/888",
                "product_handle": "greg-murphy-lap-of-the-gods-wall-art",
                "edition_offset": 0,
            }
        )

        record = orders_page.certificate_engine.certificate_record_from_order_row(row)

        self.assertEqual(record["edition_number"], 16)
        self.assertEqual(record["edition_display"], "#016/100")
        self.assertEqual(record["line_item_unit_index"], 1)
        self.assertIn("SC-SC1234-GREG-MURPHY-LAP-OF-THE-GODS-WALL-ART-EDITION-016", record["certificate_id"])

    def test_generate_lock_saves_visible_edition_before_certificate_generation(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC1234",
                "product": "Greg Murphy Lap of the Gods Wall Art",
                "variant": "Black / XL",
                "edition_number": 16,
                "edition_total": 100,
                "edition_offset": 1,
                "line_quantity": 2,
                "shopify_order_id": "gid://shopify/Order/1234",
                "shopify_line_item_id": "gid://shopify/LineItem/555",
                "shopify_product_id": "gid://shopify/Product/777",
                "variant_id": "gid://shopify/ProductVariant/888",
                "product_handle": "greg-murphy-lap-of-the-gods-wall-art",
            }
        )
        synced = []

        with patch.object(
            orders_page.order_allocator,
            "read_order_allocation_state",
            return_value={"payload": {"line_items": {}}, "compare_digest": "digest-1"},
        ), patch.object(
            orders_page.shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_id, payload, compare_digest=None, config=None: synced.append(payload),
        ):
            allocation = orders_page._lock_allocation_for_row(row, {"configured": True})

        self.assertEqual(allocation["edition_numbers"], [None, 16])
        self.assertEqual(allocation["edition_number"], 16)
        self.assertEqual(synced[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [None, 16])

    def test_limited_edition_inputs_use_only_calculated_mvp_metafields(self):
        inputs = shopify_sync.limited_edition_metafield_inputs(
            "gid://shopify/Product/1",
            {
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 65,
                "edition_label": "Numbered Edition",
            },
        )
        keys = {item["key"]: item["value"] for item in inputs}

        self.assertEqual(
            set(keys),
            {
                "edition_enabled",
                "edition_total",
                "edition_next_number",
                "edition_sold_count",
                "edition_remaining",
                "edition_status",
                "edition_label",
            },
        )
        self.assertEqual(keys["edition_sold_count"], "64")
        self.assertEqual(keys["edition_remaining"], "36")
        self.assertEqual(keys["edition_status"], "Limited Edition")

    def test_edition_ops_export_uses_required_csv_columns(self):
        row = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "legacy_resource_id": "1",
                "product_title": "All Rise Wall Art",
                "handle": "all-rise-wall-art",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 53,
                "admin_url": "https://admin.shopify.com/store/sports-cave/products/1",
                "online_store_url": "https://sportscaveshop.com/products/all-rise-wall-art",
            }
        )

        exported = edition_ops._export_csv([row]).decode("utf-8-sig").splitlines()

        self.assertEqual(exported[0].split(","), list(edition_ops.CSV_COLUMNS))
        self.assertIn("48", exported[1])
        self.assertIn("Limited Edition", exported[1])

    def test_edition_ops_supabase_row_uses_stored_counters(self):
        row = edition_ops._row_from_supabase_product(
            {
                "shopify_product_id": "gid://shopify/Product/77",
                "shopify_handle": "goat-debate-wall-art",
                "product_title": "GOAT Debate Wall Art",
                "edition_total": 100,
                "next_edition_number": 96,
                "sold_count": 50,
                "remaining_count": 50,
                "active": True,
                "status": "active",
            }
        )

        self.assertEqual(row["edition_next_number"], 96)
        self.assertEqual(row["edition_sold_count"], 50)
        self.assertEqual(row["edition_remaining"], 50)
        self.assertEqual(row["sync_status"], "Loaded from Supabase")

    def test_edition_ops_changed_rows_only_consider_editable_fields(self):
        original = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "handle": "legends-never-die",
                "edition_total": 100,
                "edition_next_number": 1,
                "sync_status": "Loaded",
            }
        )
        changed = dict(original)
        changed["sync_status"] = "Unsaved"
        changed["edition_next_number"] = 2
        unchanged_status_only = dict(original)
        unchanged_status_only["sync_status"] = "Unsaved"

        self.assertEqual(edition_ops._changed_rows([changed], [original]), [changed])
        self.assertEqual(edition_ops._changed_rows([unchanged_status_only], [original]), [])

    def test_edition_ops_uses_stable_handle_key_when_product_gid_missing(self):
        original = edition_ops._normalise_row(
            {
                "handle": "legends-never-die",
                "edition_total": 100,
                "edition_next_number": 41,
            }
        )
        same_values = edition_ops._normalise_row(
            {
                "handle": "legends-never-die",
                "edition_total": "100",
                "edition_next_number": "41",
                "edition_sold_count": 88,
                "edition_remaining": 12,
                "edition_status": "Final Editions",
            }
        )

        self.assertEqual(edition_ops._changed_rows([same_values], [original]), [])

    def test_edition_ops_page_load_starts_with_zero_dirty_rows(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "edition_product_id": "101",
                    "handle": "goat-debate-wall-art",
                    "edition_total": 100,
                    "edition_next_number": 52,
                }
            )
        ]

        self.assertEqual(edition_ops._rows_to_save(rows, rows), [])

    def test_edition_ops_row_order_changes_do_not_mark_rows_dirty(self):
        original_a = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "goat-debate-wall-art", "edition_total": 100, "edition_next_number": 52}
        )
        original_b = edition_ops._normalise_row(
            {"edition_product_id": "102", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 46}
        )

        self.assertEqual(edition_ops._changed_rows([original_b, original_a], [original_a, original_b]), [])

    def test_edition_ops_string_bool_and_int_values_compare_equal(self):
        original = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_enabled": True, "edition_total": 100, "edition_next_number": 42}
        )
        editor_row = {
            "edition_product_id": "101",
            "handle": "legends-never-die",
            "edition_enabled": "true",
            "edition_total": "100",
            "edition_next_number": "42",
        }

        self.assertEqual(edition_ops._changed_rows([editor_row], [original]), [])

    def test_edition_ops_derived_fields_do_not_mark_row_dirty(self):
        original = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 42}
        )
        changed = dict(original)
        changed["edition_sold_count"] = 99
        changed["edition_remaining"] = 1
        changed["edition_status"] = "Final Editions"

        self.assertEqual(edition_ops._changed_rows([changed], [original]), [])

    def test_edition_ops_reload_products_uses_supabase_and_clears_dirty_state(self):
        row = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 42}
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [],
                edition_ops.ORIGINAL_ROWS_KEY: [],
                edition_ops.META_KEY: {},
                edition_ops.ERRORS_KEY: {},
                edition_ops.IMPORT_WARNINGS_KEY: [],
            }
        )
        snapshot = {"rows": [row], "original_rows": [row], "saved_at": "2026-06-25T10:00:00Z"}

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=object()
        ), patch.object(edition_ops, "_invalidate_edition_ops_cache") as invalidate_cache, patch.object(
            edition_ops, "_load_supabase_snapshot", return_value=snapshot
        ), patch.object(edition_ops, "_write_snapshot") as write_snapshot, patch.object(
            edition_ops, "_bump_editor_version"
        ) as bump_editor:
            edition_ops._reload_products_from_supabase()

        self.assertEqual(edition_ops._rows_to_save(fake_st.session_state[edition_ops.ROWS_KEY], fake_st.session_state[edition_ops.ORIGINAL_ROWS_KEY]), [])
        invalidate_cache.assert_called_once()
        write_snapshot.assert_called_once()
        bump_editor.assert_called_once()

    def test_csv_import_accepts_visible_headers_and_excel_numbers(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "handle": "all-rise-wall-art",
                    "edition_enabled": False,
                    "edition_total": 100,
                    "edition_next_number": 1,
                }
            )
        ]
        csv_text = "Handle,Enabled,Edition total,Next edition number\nall-rise-wall-art,TRUE,150.0,72.0\n"

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertTrue(updated_rows[0]["edition_enabled"])
        self.assertEqual(updated_rows[0]["edition_total"], 150)
        self.assertEqual(updated_rows[0]["edition_next_number"], 72)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 71)
        self.assertEqual(updated_rows[0]["edition_remaining"], 79)
        self.assertEqual(updated_rows[0]["edition_status"], "Limited Edition")
        self.assertEqual(updated_rows[0]["sync_status"], "Needs Sync")

    def test_csv_import_action_is_clickable_and_readable(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")
        render_page = source[source.index("def render_page():") :]

        self.assertIn("_render_import_popover_styles()", render_page)
        self.assertIn('if st.button("Replace Table From CSV", use_container_width=True):', source)
        self.assertNotIn("disabled=uploaded_csv is None", render_page)
        self.assertIn("background: #FFFFFF", source)
        self.assertIn("color: #FFFFFF", source)
        self.assertIn("-webkit-text-fill-color: #FFFFFF", source)

    def test_apply_csv_import_updates_session_rows(self):
        row = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "handle": "all-rise-wall-art",
                "edition_enabled": False,
                "edition_total": 100,
                "edition_next_number": 1,
            }
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [row],
                edition_ops.ORIGINAL_ROWS_KEY: [row],
            }
        )
        upload = SimpleNamespace(
            name="edition-ops-backup.csv",
            getvalue=lambda: b"Handle,Enabled,Edition total,Next edition number\nall-rise-wall-art,TRUE,150,72\n",
        )

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_write_snapshot"
        ) as write_snapshot, patch.object(edition_ops, "_bump_editor_version") as bump_version:
            result = edition_ops._apply_csv_import(upload)

        self.assertTrue(result)
        self.assertEqual(fake_st.session_state[edition_ops.IMPORT_WARNINGS_KEY], [])
        self.assertEqual(fake_st.session_state[edition_ops.ROWS_KEY][0]["edition_total"], 150)
        self.assertEqual(fake_st.session_state[edition_ops.ROWS_KEY][0]["edition_next_number"], 72)
        self.assertEqual(fake_st.session_state[edition_ops.ROWS_KEY][0]["sync_status"], "Needs Sync")
        write_snapshot.assert_called_once()
        bump_version.assert_called_once()

    def test_csv_import_overwrites_current_next_number_even_when_lower(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "handle": "jalen-brunson-knicks-wall-art",
                    "edition_enabled": True,
                    "edition_total": 100,
                    "edition_next_number": 49,
                }
            )
        ]
        csv_text = (
            "shopify_product_gid,handle,edition_enabled,edition_total,edition_next_number\n"
            "gid://shopify/Product/1,jalen-brunson-knicks-wall-art,true,100,25\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 25)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 24)
        self.assertEqual(updated_rows[0]["edition_remaining"], 76)

    def test_csv_import_replaces_with_authoritative_derived_fields(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/99",
                    "product_title": "Greg Murphy Lap of the Gods Wall Art",
                    "handle": "greg-murphy-lap-of-the-gods-wall-art",
                    "edition_enabled": True,
                    "edition_total": 100,
                    "edition_next_number": 32,
                    "edition_sold_count": 31,
                    "edition_remaining": 69,
                }
            )
        ]
        csv_text = (
            "product_title,handle,edition_enabled,edition_total,edition_next_number,"
            "edition_sold_count,edition_remaining,edition_status\n"
            "Greg Murphy Lap of the Gods Wall Art,greg-murphy-lap-of-the-gods-wall-art,"
            "true,100,16,15,85,Limited Edition\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 16)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 15)
        self.assertEqual(updated_rows[0]["edition_remaining"], 85)
        self.assertEqual(updated_rows[0]["edition_status"], "Limited Edition")
        self.assertEqual(updated_rows[0]["sync_status"], "Needs Sync")

    def test_csv_import_supports_old_remaining_and_widget_status_headers(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "product_title": "Legacy Wall Art",
                    "handle": "legacy-wall-art",
                }
            )
        ]
        csv_text = (
            "Product title,Handle,Enabled,Edition total,Next edition number,remaining,widget_status\n"
            "Legacy Wall Art,legacy-wall-art,true,100,96,5,Final Editions\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 96)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 95)
        self.assertEqual(updated_rows[0]["edition_remaining"], 5)
        self.assertEqual(updated_rows[0]["edition_status"], "Final Editions")

    def test_csv_import_unchanged_rows_do_not_get_marked_needs_sync(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "edition_product_id": "101",
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "handle": "legacy-wall-art",
                    "edition_enabled": True,
                    "edition_total": 100,
                    "edition_next_number": 96,
                }
            )
        ]
        csv_text = (
            "shopify_product_gid,handle,edition_enabled,edition_total,edition_next_number\n"
            "gid://shopify/Product/1,legacy-wall-art,true,100,96\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 0)
        self.assertEqual(changed_rows, [])
        self.assertEqual(updated_rows[0]["sync_status"], "Loaded")

    def test_rows_to_save_only_includes_dirty_rows(self):
        original = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "edition_total": 100,
                "edition_next_number": 16,
                "sync_status": "Synced",
            }
        )
        imported = dict(original)
        imported["sync_status"] = "Needs Sync"

        self.assertEqual(edition_ops._rows_to_save([imported], [original]), [])

    def test_save_changed_rows_updates_only_changed_rows(self):
        original = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 42}
        )
        changed = dict(original)
        changed["edition_next_number"] = 43
        untouched = edition_ops._normalise_row(
            {"edition_product_id": "102", "handle": "goat-debate-wall-art", "edition_total": 100, "edition_next_number": 52}
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [changed, untouched],
                edition_ops.ORIGINAL_ROWS_KEY: [original, untouched],
                edition_ops.NOTICE_KEY: "",
                edition_ops.NOTICE_LEVEL_KEY: "success",
            }
        )
        saved_batches = []
        fake_backend = SimpleNamespace(
            update_edition_products_batch=lambda rows, reason=None: saved_batches.append(rows)
            or [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}],
        )

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=fake_backend
        ), patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": False}), patch.object(
            edition_ops, "_write_snapshot"
        ):
            edition_ops._save_changed_rows()

        self.assertEqual(len(saved_batches), 1)
        self.assertEqual(len(saved_batches[0]), 1)
        self.assertEqual(saved_batches[0][0]["row_key"], "edition_product:101")
        self.assertEqual(saved_batches[0][0]["next_edition_number"], 43)
        self.assertIn("Supabase saved, Shopify mirror failed / retry needed", fake_st.session_state[edition_ops.NOTICE_KEY])

    def test_save_changed_rows_archives_when_enabled_is_unchecked(self):
        original = edition_ops._normalise_row(
            {
                "edition_product_id": "101",
                "shopify_product_gid": "gid://shopify/Product/1",
                "product_title": "Legends Never Die Wall Art",
                "handle": "legends-never-die",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 42,
                "edition_sold_count": 41,
                "edition_remaining": 59,
                "edition_status": "Limited Edition",
            }
        )
        changed = dict(original)
        changed["edition_enabled"] = False
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [changed],
                edition_ops.ORIGINAL_ROWS_KEY: [original],
                edition_ops.NOTICE_KEY: "",
                edition_ops.NOTICE_LEVEL_KEY: "success",
            }
        )
        saved_batches = []
        fake_backend = SimpleNamespace(
            update_edition_products_batch=lambda rows, reason=None: saved_batches.append(rows)
            or [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}],
        )

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=fake_backend
        ), patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": False}), patch.object(
            edition_ops, "_write_snapshot"
        ):
            edition_ops._save_changed_rows()

        saved = saved_batches[0][0]
        self.assertFalse(saved["active"])
        self.assertTrue(saved["sold_out"])
        self.assertEqual(saved["next_edition_number"], 101)
        self.assertEqual(saved["reason"], "Edition archived from Edition Ops")
        display_row = fake_st.session_state[edition_ops.ROWS_KEY][0]
        self.assertEqual(display_row["edition_remaining"], 0)
        self.assertEqual(display_row["edition_status"], "Sold Out Archive")

    def test_reenabling_archived_row_requires_next_number_inside_total(self):
        original = edition_ops._normalise_row(
            {
                "edition_product_id": "101",
                "handle": "legends-never-die",
                "edition_enabled": False,
                "edition_total": 100,
                "edition_next_number": 101,
            }
        )
        changed = dict(original)
        changed["edition_enabled"] = True

        message = edition_ops._save_validation_error(changed, original)

        self.assertEqual(
            message,
            "This edition is archived. To reopen it, set Next edition number back within the edition total first.",
        )

    def test_manual_lower_below_assigned_history_warns_without_blocking(self):
        original = edition_ops._normalise_row(
            {
                "edition_product_id": "101",
                "handle": "legends-never-die",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 95,
                "edition_sold_count": 94,
            }
        )
        changed = dict(original)
        changed["edition_next_number"] = 80

        self.assertEqual(edition_ops._save_validation_error(changed, original), "")
        self.assertEqual(
            edition_ops._manual_lower_warning(changed, original),
            "Warning: this product has assigned editions above this next number. Manual correction saved.",
        )

    def test_save_changed_rows_allows_manual_lower_and_warns(self):
        original = edition_ops._normalise_row(
            {
                "edition_product_id": "101",
                "shopify_product_gid": "gid://shopify/Product/1",
                "product_title": "Legends Never Die Wall Art",
                "handle": "legends-never-die",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 95,
                "edition_sold_count": 94,
                "edition_remaining": 6,
            }
        )
        changed = dict(original)
        changed["edition_next_number"] = 80
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [changed],
                edition_ops.ORIGINAL_ROWS_KEY: [original],
                edition_ops.NOTICE_KEY: "",
                edition_ops.NOTICE_LEVEL_KEY: "success",
            }
        )
        saved_batches = []
        fake_backend = SimpleNamespace(
            update_edition_products_batch=lambda rows, reason=None: saved_batches.append(rows)
            or [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}],
        )

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=fake_backend
        ), patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": False}), patch.object(
            edition_ops, "_write_snapshot"
        ):
            edition_ops._save_changed_rows()

        saved = saved_batches[0][0]
        self.assertEqual(saved["next_edition_number"], 80)
        self.assertEqual(saved["reason"], "manual_next_number_lowered")
        self.assertTrue(saved["manual_next_number_lowered"])
        self.assertEqual(saved["highest_assigned_edition"], 94)
        self.assertIn(
            "Warning: this product has assigned editions above this next number. Manual correction saved.",
            fake_st.session_state[edition_ops.NOTICE_KEY],
        )
        self.assertEqual(fake_st.session_state[edition_ops.NOTICE_LEVEL_KEY], "warning")

    def test_repeated_saves_use_latest_editor_widget_state(self):
        row_a = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 10}
        )
        row_b = edition_ops._normalise_row(
            {"edition_product_id": "102", "handle": "goat-debate-wall-art", "edition_total": 100, "edition_next_number": 20}
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [row_a, row_b],
                edition_ops.ORIGINAL_ROWS_KEY: [row_a, row_b],
                edition_ops.NOTICE_KEY: "",
                edition_ops.NOTICE_LEVEL_KEY: "success",
            }
        )
        saved_batches = []
        fake_backend = SimpleNamespace(
            update_edition_products_batch=lambda rows, reason=None: saved_batches.append(rows)
            or [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}],
        )

        first_submit = [dict(row_a, edition_next_number=11), row_b]
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=fake_backend
        ), patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": False}), patch.object(
            edition_ops, "_write_snapshot"
        ):
            edition_ops._save_changed_rows(first_submit)
            fake_st.session_state[edition_ops.EDITOR_KEY] = {
                "edited_rows": {"1": {"edition_next_number": 21}}
            }
            stale_submit = deepcopy(fake_st.session_state[edition_ops.ROWS_KEY])
            edition_ops._save_changed_rows(stale_submit)

        self.assertEqual(len(saved_batches), 2)
        self.assertEqual(saved_batches[0][0]["row_key"], "edition_product:101")
        self.assertEqual(saved_batches[0][0]["next_edition_number"], 11)
        self.assertEqual(saved_batches[1][0]["row_key"], "edition_product:102")
        self.assertEqual(saved_batches[1][0]["next_edition_number"], 21)
        self.assertNotEqual(fake_st.session_state[edition_ops.NOTICE_KEY], "No changes to save.")
        self.assertEqual(
            fake_st.session_state[edition_ops.ORIGINAL_ROWS_KEY][1]["edition_next_number"],
            21,
        )
        self.assertEqual(
            fake_st.session_state[edition_ops.EDITOR_ROWS_KEY][1]["edition_next_number"],
            21,
        )

    def test_same_row_can_save_twice_without_page_reload(self):
        row = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 10}
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [row],
                edition_ops.ORIGINAL_ROWS_KEY: [row],
                edition_ops.NOTICE_KEY: "",
                edition_ops.NOTICE_LEVEL_KEY: "success",
            }
        )
        saved_batches = []
        fake_backend = SimpleNamespace(
            update_edition_products_batch=lambda rows, reason=None: saved_batches.append(rows)
            or [{"ok": True, "handle": rows[0]["handle"], "key": rows[0]["row_key"]}],
        )

        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=fake_backend
        ), patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": False}), patch.object(
            edition_ops, "_write_snapshot"
        ):
            edition_ops._save_changed_rows([dict(row, edition_next_number=11)])
            fake_st.session_state[edition_ops.EDITOR_KEY] = {
                "edited_rows": {0: {"edition_next_number": 12}}
            }
            edition_ops._save_changed_rows(deepcopy(fake_st.session_state[edition_ops.ROWS_KEY]))

        self.assertEqual([batch[0]["next_edition_number"] for batch in saved_batches], [11, 12])
        self.assertEqual(fake_st.session_state[edition_ops.ORIGINAL_ROWS_KEY][0]["edition_next_number"], 12)

    def test_editor_key_remains_stable(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")
        render_page = source[source.index("def render_page():") :]

        self.assertIn('EDITOR_KEY = "edition_ops_editor_v3"', source)
        self.assertIn("key=EDITOR_KEY", render_page)
        self.assertNotIn('key=f"edition-ops-editor-', render_page)

    def test_save_changed_rows_reports_no_changes(self):
        row = edition_ops._normalise_row(
            {"edition_product_id": "101", "handle": "legends-never-die", "edition_total": 100, "edition_next_number": 42}
        )
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: [row],
                edition_ops.ORIGINAL_ROWS_KEY: [row],
                edition_ops.NOTICE_KEY: "",
            }
        )

        with patch.object(edition_ops, "st", fake_st):
            edition_ops._save_changed_rows()

        self.assertEqual(fake_st.session_state[edition_ops.NOTICE_KEY], "No changes to save.")

    def test_editor_changes_recalculate_derived_fields_without_order_data(self):
        source = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "edition_total": 100,
                "edition_next_number": 16,
                "edition_sold_count": 15,
                "edition_remaining": 85,
            }
        )

        merged = edition_ops._merge_visible_rows(
            [{"edition_total": 100, "edition_next_number": 20}],
            [source],
        )

        self.assertEqual(merged[0]["edition_sold_count"], 19)
        self.assertEqual(merged[0]["edition_remaining"], 81)

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        shopify_source = (ROOT / "shopify_sync.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        for field in (
            "shopify_customer_id",
            "customer_email",
            "customer_name",
            "shopify_order_name",
            "shopify_line_item_id",
            "shopify_product_id",
            "shopify_variant_id",
            "product_handle",
            "edition_limit",
            "edition_display",
            "display_edition",
            "shopify_file_status",
            "certificate_pdf_url",
            "certificate_status",
            "sync_status",
            "last_sync_error",
            "purchase_date",
            "created_at",
            "updated_at",
        ):
            self.assertIn(field, source)
        self.assertIn("def upsert_certificate_metadata", source)
        self.assertIn("def backfill_ready_certificate_order_metafields", source)
        self.assertIn("Retry Certificate Metafield Push", app_source)
        self.assertIn('"key": "certificates_json"', shopify_source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)


class OrdersDatabaseReadRepairTests(unittest.TestCase):
    class Cursor:
        def __init__(self, rows=None, error=None, statements=None):
            self.rows = list(rows or [])
            self.error = error
            self.statements = statements if statements is not None else []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            self.statements.append((str(sql), tuple(params or ())))
            if self.error:
                raise self.error

        def fetchall(self):
            return list(self.rows)

        def read(self):
            if self.error:
                raise self.error
            return list(self.rows)

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor
            self.closed = False
            self.rollback_calls = 0
            self.close_calls = 0

        def cursor(self):
            return self._cursor

        def rollback(self):
            self.rollback_calls += 1

        def close(self):
            self.close_calls += 1
            self.closed = True

    def test_closed_connection_is_discarded_and_read_retries_once(self):
        stale = self.Connection(self.Cursor(error=RuntimeError("EDBHANDLEREXITED connection to database closed")))
        fresh = self.Connection(self.Cursor(rows=[{"ok": 1}]))

        with patch.object(supabase_backend, "connect", side_effect=[stale, fresh]) as connect:
            value, diagnostic = supabase_backend._run_read_operation("orders.test", lambda cur: cur.read())

        self.assertEqual(value, [{"ok": 1}])
        self.assertEqual(connect.call_count, 2)
        self.assertTrue(diagnostic["recovered"])
        self.assertEqual(stale.close_calls, 1)
        self.assertEqual(fresh.close_calls, 1)
        self.assertEqual(fresh.rollback_calls, 1)

    def test_permanent_sql_error_is_not_retried_or_hidden(self):
        failed = self.Connection(self.Cursor(error=ValueError("syntax error near SELECT")))

        with patch.object(supabase_backend, "connect", return_value=failed) as connect:
            with self.assertRaises(supabase_backend.DatabaseReadError) as raised:
                supabase_backend._run_read_operation("orders.test", lambda cur: cur.read())

        self.assertEqual(connect.call_count, 1)
        self.assertIsInstance(raised.exception.__cause__, ValueError)
        self.assertEqual(raised.exception.diagnostic["category"], "sql_query_error")
        self.assertEqual(failed.close_calls, 1)
        self.assertEqual(failed.rollback_calls, 1)

    def test_latest_50_and_search_are_two_bulk_read_queries_without_writes(self):
        statements = []
        base_rows = [
            {
                "shopify_order_id": "gid://shopify/Order/2906",
                "order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "variant_title": "Black / M",
                "quantity": 2,
            }
        ]
        allocations = [
            {
                "edition_order_id": "eo-six-080",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "edition_number": 80,
                "edition_total": 100,
                "allocation_index": 1,
            },
            {
                "edition_order_id": "eo-six-081",
                "shopify_order_id": "gid://shopify/Order/2906",
                "shopify_order_name": "#SC2906",
                "shopify_line_item_id": "gid://shopify/LineItem/9062",
                "edition_number": 81,
                "edition_total": 100,
                "allocation_index": 2,
            },
        ]
        connections = [
            self.Connection(self.Cursor(rows=base_rows, statements=statements)),
            self.Connection(self.Cursor(rows=allocations, statements=statements)),
        ]

        with patch.object(supabase_backend, "connect", side_effect=connections) as connect:
            rows = supabase_backend.list_hybrid_order_rows(limit=50, search="#SC2906")

        self.assertEqual(connect.call_count, 2)
        self.assertEqual(len(statements), 2)
        self.assertIn("WITH selected_orders AS", statements[0][0])
        self.assertEqual(statements[0][1][-1], 50)
        self.assertIn("EXISTS", statements[0][0])
        self.assertNotIn("1000", statements[0][0])
        for sql, _ in statements:
            upper = sql.upper()
            for write_token in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "CREATE "):
                self.assertNotIn(write_token, upper)
        self.assertEqual(len(rows[0]["assignments"]), 2)
        snapshot_rows = order_allocator._snapshot_rows_from_supabase_order_rows(rows)
        self.assertEqual(sorted(row["edition_number"] for row in snapshot_rows), [80, 81])
        self.assertEqual(
            sorted(row["edition_order_id"] for row in snapshot_rows),
            ["eo-six-080", "eo-six-081"],
        )
        self.assertEqual(
            os_pages.prodigi_tracker_row_id(snapshot_rows[0]),
            f"edition-order|{snapshot_rows[0]['edition_order_id']}",
        )
        self.assertTrue(all(connection.closed for connection in connections))

    def test_orders_search_is_explicit_and_normal_render_skips_duplicate_audit(self):
        form_source = inspect.getsource(orders_page._render_orders_search_form)
        render_source = inspect.getsource(orders_page.render_page)

        self.assertIn('st.form("orders-search-form"', form_source)
        self.assertIn("form_submit_button", form_source)
        self.assertNotIn("_duplicate_diagnostics_snapshot", render_source)
        self.assertIn("_load_snapshot_once(search_text, force=True)", render_source)

    def test_failed_load_keeps_safe_error_state_without_local_fallback(self):
        error = supabase_backend.DatabaseReadError(
            "The database query failed. Check Developer diagnostics.",
            {
                "operation": "orders.latest_50.base",
                "category": "sql_query_error",
                "exception_class": "UndefinedColumn",
                "duration_ms": 12,
            },
        )
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [{"order": "#stale"}],
                orders_page.META_KEY: {},
                orders_page.LOAD_ERROR_KEY: "",
            }
        )

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page, "_read_orders_snapshot", side_effect=error
        ), patch.object(
            orders_page.order_allocator,
            "load_orders_snapshot",
            side_effect=AssertionError("Supabase failures must not use the local allocation snapshot."),
        ):
            orders_page._load_snapshot_once(force=True)

        self.assertEqual(fake_st.session_state[orders_page.ROWS_KEY], [])
        diagnostic = fake_st.session_state[orders_page.META_KEY]["database_read"]
        self.assertEqual(diagnostic["exception_class"], "UndefinedColumn")
        self.assertEqual(diagnostic["operation"], "orders.latest_50.base")
        self.assertIn("Developer diagnostics", fake_st.session_state[orders_page.LOAD_ERROR_KEY])


if __name__ == "__main__":
    unittest.main()
