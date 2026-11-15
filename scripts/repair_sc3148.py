"""Explicit, narrowly scoped incident recovery in the existing OS environment.

Installs the reviewed allocator and repairs only SC3148 in ONE transaction.
Never generates certificates. Supabase backups stay in the existing audit table.
Re-execution validates existing units and retries only the normal product mirror.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import supabase_backend as backend
from scripts.audit_sc3148 import HANDLE, LINE_ID, ORDER_ID, PRODUCT_ID

REPAIR_KEY = "sc3148-independent-cursor-20260912"
APPROVAL = "9e15ed654a17b2670c69b032196dc3e7c544c4dba816960017a1cf508eec94d6"
RUN_ID = "9799b113-0ff2-4dd6-9185-381357d04748"
VARIANT_ID = "gid://shopify/ProductVariant/54020683989299"
MIGRATION = "20260912045939_independent_edition_cursor.sql"
OLD_FUNCTION = "1e5f260172220751170863b927f1f2a8"


def require(condition, reason):
    if not condition:
        raise ValueError("SC3148 repair stopped: " + reason)


def suffix(value):
    return str(value or "").rsplit("/", 1)[-1]


def validate_before(product, run, order, lines, allocations, tombstones, certificates, adjustments):
    require(product["id"] == 657 and product["shopify_product_gid"] == PRODUCT_ID
            and product["shopify_handle"] == HANDLE, "product identity conflict")
    require(str(product["active_edition_run_id"]) == RUN_ID and str(run["id"]) == RUN_ID,
            "active run changed")
    require((product["next_edition_number"], product["sold_count"], product["remaining_count"],
             product["edition_total"]) == (50, 0, 100, 100), "audited counters changed")
    require(product["active"] and not product["sold_out"] and not product.get("is_sold_out"),
            "product is closed")
    require(run["status"] == "active" and run["next_edition_number"] == 50
            and run["edition_total"] == 100 and run["allocation_baseline_sold_count"] == 0,
            "run state changed")
    require(order["order_name"] == "#SC3148" and str(order["financial_status"]).upper() == "PAID"
            and not order["cancelled_at"], "order is not the confirmed paid order")
    require(not allocations and not tombstones and not certificates, "allocation/reservation/certificate conflict")
    require(bool(lines) and len(lines) <= 2, "unexpected order lines")
    for line in lines:
        require(suffix(line["shopify_line_item_id"]) == suffix(LINE_ID)
                and suffix(line["shopify_product_id"]) == suffix(PRODUCT_ID)
                and line["quantity"] == 2 and line["sku"] == "FSWOA2B", "line identity/quantity changed")
        raw = line.get("raw_json") or {}
        variant = line.get("shopify_variant_id") or raw.get("shopify_variant_id") or raw.get("variant_id")
        if not variant and isinstance(raw.get("variant"), dict):
            variant = raw["variant"].get("id")
        require(suffix(variant) == suffix(VARIANT_ID), "variant identity is unverified")
    require(any(a["old_next_edition_number"] == 1 and a["new_next_edition_number"] == 50
                and a["source"] == "manual_app" for a in adjustments), "manual override evidence missing")


def validate_allocations(rows):
    require(len(rows) == 2, "expected exactly two purchased units")
    rows = sorted(rows, key=lambda r: r["unit_ordinal"])
    for ordinal, row in enumerate(rows, 1):
        require(row["unit_ordinal"] == ordinal and row["edition_number"] == 49 + ordinal
                and row["edition_total"] == 100 and row["quantity"] == 2
                and row["external_order_id"] == ORDER_ID and row["external_line_item_id"] == LINE_ID
                and row["shopify_product_gid"] == PRODUCT_ID and str(row["edition_run_id"]) == RUN_ID
                and suffix(row["shopify_variant_id"]) == suffix(VARIANT_ID)
                and row["allocation_valid"] and row["identity_enforced"]
                and row["status"] not in {"voided", "refunded", "cancelled", "superseded"},
                "existing unit differs from verified repair")


def apply(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        cur.execute("SET LOCAL statement_timeout = '60s'")
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (PRODUCT_ID,))
        cur.execute("SELECT * FROM edition_products WHERE shopify_product_gid=%s OR shopify_handle=%s FOR UPDATE",
                    (PRODUCT_ID, HANDLE))
        products = cur.fetchall()
        require(len(products) == 1, "product missing or duplicated")
        product = dict(products[0])
        cur.execute("SELECT * FROM edition_runs WHERE id=%s FOR UPDATE", (RUN_ID,))
        run = dict(cur.fetchone() or {})
        cur.execute("SELECT * FROM shopify_orders WHERE shopify_order_id IN (%s,%s) FOR UPDATE", (ORDER_ID, suffix(ORDER_ID)))
        orders = cur.fetchall()
        require(len(orders) == 1, "order missing or duplicated")
        order = dict(orders[0])
        cur.execute("SELECT * FROM shopify_order_lines WHERE shopify_order_id IN (%s,%s) FOR UPDATE", (ORDER_ID, suffix(ORDER_ID)))
        lines = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM edition_orders WHERE shopify_product_gid=%s OR shopify_handle=%s OR edition_run_id=%s OR shopify_order_id IN (%s,%s) ORDER BY id",
                    (PRODUCT_ID, HANDLE, RUN_ID, ORDER_ID, suffix(ORDER_ID)))
        allocations = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM edition_repair_audits WHERE repair_key=%s", (REPAIR_KEY,))
        previous = cur.fetchone()
        if previous and previous["applied_at"]:
            validate_allocations([r for r in allocations if r["external_order_id"] == ORDER_ID])
            return {"action": "already_repaired", "editions": [50, 51]}
        cur.execute("SELECT * FROM edition_allocation_tombstones WHERE shopify_product_gid=%s OR external_order_id IN (%s,%s)", (PRODUCT_ID, ORDER_ID, suffix(ORDER_ID)))
        tombstones = cur.fetchall()
        cur.execute("SELECT id FROM certificates WHERE shopify_handle=%s OR shopify_order_id IN (%s,%s)", (HANDLE, ORDER_ID, suffix(ORDER_ID)))
        certificates = cur.fetchall()
        cur.execute("SELECT * FROM edition_adjustments WHERE edition_product_id=657 ORDER BY created_at")
        adjustments = cur.fetchall()
        validate_before(product, run, order, lines, allocations, tombstones, certificates, adjustments)
        cur.execute("SELECT md5(pg_get_functiondef(p.oid)) fingerprint, pg_get_functiondef(p.oid) definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='allocate_edition_line_units_atomic'")
        functions = cur.fetchall()
        require(len(functions) == 1 and functions[0]["fingerprint"] == OLD_FUNCTION, "allocator definition changed since audit")
        snapshot = json.dumps(dict(product=product, run=run, order=order, lines=lines,
                                   allocations=allocations, adjustments=adjustments,
                                   previous_allocator=functions[0]["definition"]), default=str, sort_keys=True)
        cur.execute("INSERT INTO edition_repair_audits(repair_key,product_gid,mode,snapshot_sha256,report,actor) VALUES(%s,%s,'apply',%s,%s::jsonb,'Nathan-authorized-sc3148-repair')",
                    (REPAIR_KEY, PRODUCT_ID, hashlib.sha256(snapshot.encode()).hexdigest(), snapshot))
        # Same outer transaction: function installation, backup and units all roll
        # back if any assertion fails. No table-wide data migration is executed.
        sql = (Path(__file__).resolve().parents[1] / "migrations" / MIGRATION).read_text()
        sql = sql.replace("\nBEGIN;\n", "\n", 1).rsplit("COMMIT;", 1)[0]
        cur.execute(sql)
        line = lines[0]
        cur.execute("SELECT allocate_edition_line_units_atomic(" + ",".join(["%s"] * 15) + ") result",
                    ("shopify", ORDER_ID, LINE_ID, PRODUCT_ID, 2, ORDER_ID, "#SC3148", LINE_ID,
                     VARIANT_ID, line["product_title"], line["variant_title"], line["sku"],
                     backend._customer_name_for_storage(order), order.get("customer_email") or order.get("email") or "", "assigned"))
        created = [r["result"]["allocation"] for r in cur.fetchall()]
        validate_allocations(created)
        for line in lines:
            backend._set_order_line_status(cur, line["shopify_line_item_id"], "Assigned")
        cur.execute("SELECT next_edition_number,sold_count,remaining_count FROM edition_products WHERE id=657")
        final = dict(cur.fetchone())
        require(final == dict(next_edition_number=52, sold_count=2, remaining_count=98), "unexpected final counters")
        cur.execute("UPDATE edition_repair_audits SET applied_at=now() WHERE repair_key=%s", (REPAIR_KEY,))
        cur.execute("INSERT INTO schema_migrations(filename) VALUES(%s) ON CONFLICT DO NOTHING", (MIGRATION,))
        return {"action": "repaired", "editions": [50, 51], **final}


def finalize_ingestion():
    """Optional marketplace diagnostics are not installed in every OS database."""
    required = {"source_name", "ingestion_status", "ingestion_method", "ingestion_result",
                "ingestion_reason", "ingestion_duration_ms", "last_ingested_at", "updated_at"}
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='shopify_orders'")
            columns = {r["column_name"] for r in cur.fetchall()}
        conn.rollback()
    if not required.issubset(columns):
        return "not_applicable_legacy_schema"
    backend._set_order_ingestion_outcome(
        {"shopify_order_id": ORDER_ID, "order_name": "#SC3148"},
        ingestion_method="sc3148_verified_repair", ingestion_status="complete",
        import_result="repaired_existing_assignments", reason="",
    )
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ingestion_status, ingestion_reason FROM shopify_orders WHERE shopify_order_id=%s", (ORDER_ID,))
            ingestion = dict(cur.fetchone() or {})
        conn.rollback()
    require(ingestion.get("ingestion_status") == "complete" and not ingestion.get("ingestion_reason"),
            "order ingestion completion was not persisted")
    return "complete"


def run(approval):
    require(approval == APPROVAL, "explicit incident approval gate absent")
    with backend.connect() as conn:
        try:
            result = apply(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    # The ledger is durable before any external mirror; failure remains retryable.
    mirror = backend.sync_product_edition_metafields(HANDLE, ensure_schema_first=False)
    result["mirror_source"] = mirror["source_values"]
    result["metafields_after"] = mirror["metafields_after"]
    result["mirror_readback_error"] = mirror.get("metafields_after_error") or ""
    require(not result["mirror_readback_error"], "Shopify readback failed after committed repair")
    import order_allocator
    import orders_page
    import edition_ops
    raw_rows = backend.list_hybrid_order_rows(limit=5, search="#SC3148")
    rows = [orders_page._normalise_row(row) for row in
            order_allocator._snapshot_rows_from_supabase_order_rows(raw_rows)]
    # Report only fulfilment/edition state; omit customer and certificate URLs.
    allowed = {"edition_number", "edition_total", "edition_display", "edition",
               "assignment_status", "certificate_status", "certificate", "fulfilment_status",
               "line_item_unit_index", "shopify_line_item_id", "shopify_order_id"}
    result["orders_ui_rows"] = [{k: v for k, v in r.items() if k in allowed} for r in rows]
    require(len(rows) == 2 and sorted(int(r.get("edition_number") or 0) for r in rows) == [50, 51],
            "Orders loader did not return the two verified fulfilment units")
    result["ingestion_status"] = finalize_ingestion()
    product_rows = backend.list_edition_products_read_only(search=HANDLE, limit=5)
    result["edition_ops"] = [
        {key: value for key, value in edition_ops._row_from_supabase_product(row).items()
         if key in {"edition_next_number", "edition_sold_count", "edition_remaining", "edition_enabled", "sync_error"}}
        for row in product_rows if row.get("shopify_handle") == HANDLE
    ]
    return result
