"""Read-only evidence for SC3148. Never allocates, migrates or mirrors data.

Run with the application's existing database configuration. Output deliberately
excludes customer details, raw order payloads and certificate URLs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supabase_backend as backend

ORDER_ID = "gid://shopify/Order/7408832905523"
LINE_ID = "gid://shopify/LineItem/17545899573555"
PRODUCT_ID = "gid://shopify/Product/10431944393011"
HANDLE = "the-first-shift-willie-o-ree-wall-art"


def query(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def audit(conn):
    """Use one consistent, database-enforced read-only snapshot."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '30s'")
        product_filter = "shopify_product_gid=%s OR shopify_product_id IN (%s, %s) OR shopify_handle=%s"
        identity = (PRODUCT_ID, PRODUCT_ID, PRODUCT_ID.rsplit('/', 1)[-1], HANDLE)
        order_identity = (ORDER_ID, ORDER_ID.rsplit('/', 1)[-1])
        products = query(cur, "SELECT id, shopify_product_gid, shopify_product_id, shopify_handle, "
                         "edition_total, next_edition_number, sold_count, remaining_count, "
                         "last_assigned_edition, active, sold_out, active_edition_run_id, "
                         "updated_at FROM edition_products WHERE " + product_filter, identity)
        runs = query(cur, "SELECT id, shopify_handle, edition_name, edition_total, next_edition_number, "
                     "status, allocation_baseline_sold_count, allocation_baseline_recorded_at, "
                     "allocation_baseline_reason, created_at, updated_at FROM edition_runs "
                     "WHERE shopify_handle=%s OR id IN "
                     "(SELECT active_edition_run_id FROM edition_products WHERE " + product_filter + ")",
                     (HANDLE, *identity))
        allocations = query(cur, "SELECT id, source_channel, external_order_id, external_line_item_id, "
                            "unit_ordinal, shopify_order_id, shopify_order_name, shopify_line_item_id, "
                            "shopify_product_gid, shopify_product_id, shopify_handle, shopify_variant_id, "
                            "edition_run_id, edition_number, edition_total, quantity, allocation_index, "
                            "identity_enforced, allocation_valid, status, certificate_status, "
                            "certificate_id, mirror_status, assigned_at FROM edition_orders WHERE "
                            + product_filter + " OR edition_run_id = ANY(%s) OR shopify_order_id IN (%s, %s) "
                            "ORDER BY edition_number, id", (*identity, [r['id'] for r in runs], *order_identity))
        tombstones = query(cur, "SELECT source_channel, external_order_id, external_line_item_id, "
                           "unit_ordinal, shopify_product_gid, former_edition_number, repair_key, created_at "
                           "FROM edition_allocation_tombstones WHERE shopify_product_gid=%s "
                           "OR external_order_id IN (%s, %s) ORDER BY former_edition_number",
                           (PRODUCT_ID, ORDER_ID, ORDER_ID.rsplit('/', 1)[-1]))
        adjustments = query(cur, "SELECT id, edition_product_id, edition_run_id, "
                            "old_next_edition_number, new_next_edition_number, old_edition_total, "
                            "new_edition_total, source, reason, created_at FROM edition_adjustments "
                            "WHERE shopify_product_id=%s OR shopify_handle=%s "
                            "OR edition_product_id = ANY(%s) ORDER BY created_at, id",
                            (PRODUCT_ID, HANDLE, [p['id'] for p in products]))
        lines = query(cur, "SELECT shopify_order_id, shopify_line_item_id, shopify_product_id, "
                      "shopify_handle, variant_title, sku, quantity, assignment_status, "
                      "(last_error LIKE '%%Atomic edition suffix is not contiguous%%') AS counter_contract_error, "
                      "md5(last_error) AS error_fingerprint FROM shopify_order_lines "
                      "WHERE shopify_order_id IN (%s, %s) ORDER BY shopify_line_item_id", order_identity)
        orders = query(cur, "SELECT shopify_order_id, order_name, financial_status, cancelled_at, "
                       "processed_at, synced_at FROM shopify_orders WHERE shopify_order_id IN (%s, %s)", order_identity)
        certificates = query(cur, "SELECT id, edition_order_id, related_edition_order_id, shopify_order_id, "
                             "shopify_line_item_id, line_item_unit_index, edition_number, edition_total, "
                             "shopify_file_status FROM certificates WHERE shopify_product_id IN (%s, %s) "
                             "OR shopify_handle=%s OR shopify_order_id IN (%s, %s) ORDER BY id",
                             (PRODUCT_ID, PRODUCT_ID.rsplit('/', 1)[-1], HANDLE, *order_identity))
        repairs = query(cur, "SELECT id, repair_key, mode, snapshot_sha256, created_at, applied_at, "
                        "rolled_back_at FROM edition_repair_audits WHERE product_gid=%s ORDER BY created_at", (PRODUCT_ID,))
        # Hash complete history without printing raw customer/certificate data.
        history = query(cur, "SELECT md5(COALESCE(jsonb_agg(to_jsonb(eo) ORDER BY eo.id)::text, '[]')) "
                        "AS history_fingerprint FROM edition_orders eo WHERE " + product_filter, identity)
        function = query(cur, "SELECT md5(pg_get_functiondef(p.oid)) AS definition_fingerprint "
                         "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                         "WHERE n.nspname='public' AND p.proname='allocate_edition_line_units_atomic'")
        other_errors = query(cur, "SELECT shopify_order_id, shopify_line_item_id, shopify_product_id, "
                             "shopify_handle, assignment_status FROM shopify_order_lines "
                             "WHERE assignment_status='Error' AND last_error LIKE %s "
                             "ORDER BY shopify_order_id, shopify_line_item_id",
                             ('%Atomic edition suffix is not contiguous%',))
    evidence = dict(products=products, runs=runs, allocations=allocations, tombstones=tombstones,
                    adjustments=adjustments, order=orders, lines=lines, history=history,
                    allocator=function, other_failed_lines=other_errors, certificates=certificates,
                    repairs=repairs)
    evidence['snapshot_sha256'] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()
    return evidence


def main():
    if not backend.is_configured():
        raise SystemExit("Database is not configured. Run in the existing OS environment; do not paste credentials.")
    with backend.connect() as conn:
        try:
            result = audit(conn)
        finally:
            conn.rollback()
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
