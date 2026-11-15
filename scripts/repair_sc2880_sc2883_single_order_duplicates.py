import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supabase_backend


KEEP_EDITIONS = {
    "#SC2880": 25,
    "#SC2881": 26,
    "#SC2882": 27,
    "#SC2883": 63,
}
CONFIRM_FLAG = "--i-understand-this-removes-duplicate-order-rows"


def _load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _clean(value):
    return str(value or "").strip()


def _sort_id(value):
    text = _clean(value)
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def _public_row(row):
    return {
        "id": _clean(row.get("id")),
        "order_name": _clean(row.get("order_name")),
        "shopify_order_name": _clean(row.get("shopify_order_name")),
        "shopify_order_id": _clean(row.get("shopify_order_id")),
        "shopify_line_item_id": _clean(row.get("shopify_line_item_id")),
        "allocation_key": _clean(row.get("allocation_key")),
        "shopify_handle": _clean(row.get("shopify_handle") or row.get("product_handle")),
        "product_title": _clean(row.get("product_title")),
        "variant_title": _clean(row.get("variant_title")),
        "customer_name": _clean(row.get("customer_name")),
        "customer_email": _clean(row.get("customer_email")),
        "edition_number": row.get("edition_number"),
        "edition_total": row.get("edition_total"),
        "certificate_status": _clean(row.get("certificate_status")),
        "status": _clean(row.get("status")),
        "created_at": row.get("created_at"),
        "assigned_at": row.get("assigned_at"),
    }


def build_repair_plan(rows):
    rows_by_order = {}
    for row in rows:
        order_name = _clean(row.get("order_name") or row.get("shopify_order_name"))
        if order_name in KEEP_EDITIONS:
            rows_by_order.setdefault(order_name, []).append(row)

    orders = {}
    rows_to_delete = []
    rows_to_keep = []
    affected_products = set()
    for order_name, expected_edition in KEEP_EDITIONS.items():
        order_rows = sorted(
            rows_by_order.get(order_name, []),
            key=lambda row: (
                0 if int(row.get("edition_number") or 0) == expected_edition else 1,
                _clean(row.get("created_at")) or _clean(row.get("assigned_at")) or "",
                _sort_id(row.get("id")),
            ),
        )
        keep = next(
            (row for row in order_rows if int(row.get("edition_number") or 0) == expected_edition),
            None,
        )
        delete_rows = [row for row in order_rows if keep is None or _clean(row.get("id")) != _clean(keep.get("id"))]
        if keep:
            rows_to_keep.append(_public_row(keep))
            handle = _clean(keep.get("shopify_handle") or keep.get("product_handle"))
            if handle:
                affected_products.add(handle)
        for row in delete_rows:
            rows_to_delete.append(_public_row(row))
            handle = _clean(row.get("shopify_handle") or row.get("product_handle"))
            if handle:
                affected_products.add(handle)
        orders[order_name] = {
            "expected_keep_edition_number": expected_edition,
            "before_count": len(order_rows),
            "after_count": 1 if keep else 0,
            "keep": _public_row(keep) if keep else None,
            "delete": [_public_row(row) for row in delete_rows],
            "error": "" if keep else f"No row found for required edition #{expected_edition}.",
        }

    return {
        "orders": orders,
        "rows_to_keep": rows_to_keep,
        "rows_to_delete": rows_to_delete,
        "delete_ids": [_clean(row.get("id")) for row in rows_to_delete if _clean(row.get("id"))],
        "affected_products": sorted(affected_products),
    }


def _fetch_target_rows(cur):
    cur.execute(
        """
        SELECT eo.id::text AS id,
               COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS order_name,
               eo.shopify_order_name,
               eo.shopify_order_id,
               eo.shopify_line_item_id,
               eo.allocation_key,
               eo.shopify_handle,
               eo.product_handle,
               eo.product_title,
               eo.variant_title,
               eo.customer_name,
               eo.customer_email,
               eo.edition_number,
               eo.edition_total,
               eo.certificate_status,
               eo.status,
               eo.created_at,
               eo.assigned_at
        FROM edition_orders eo
        LEFT JOIN shopify_orders o ON o.shopify_order_id = eo.shopify_order_id
        WHERE COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) = ANY(%s)
        ORDER BY COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')),
                 eo.edition_number ASC NULLS LAST,
                 eo.created_at ASC NULLS LAST,
                 eo.id::text ASC
        """,
        (list(KEEP_EDITIONS.keys()),),
    )
    return [dict(row) for row in cur.fetchall()]


def _counter_plan(cur, affected_products, delete_ids):
    changes = []
    for handle in affected_products:
        cur.execute(
            """
            SELECT id::text AS id, shopify_handle, edition_total, next_edition_number, remaining_count
            FROM edition_products
            WHERE shopify_handle=%s
            """,
            (handle,),
        )
        product = cur.fetchone() or {}
        if not product:
            continue
        cur.execute(
            """
            SELECT COUNT(*) AS assigned_count,
                   COALESCE(MAX(edition_number), 0) AS max_assigned
            FROM edition_orders
            WHERE COALESCE(shopify_handle, product_handle, '')=%s
            """,
            (handle,),
        )
        before_stats = cur.fetchone() or {}
        cur.execute(
            """
            SELECT COUNT(*) AS assigned_count,
                   COALESCE(MAX(edition_number), 0) AS max_assigned
            FROM edition_orders
            WHERE COALESCE(shopify_handle, product_handle, '')=%s
              AND NOT (id::text = ANY(%s))
            """,
            (handle, delete_ids),
        )
        stats = cur.fetchone() or {}
        edition_total = max(int(product.get("edition_total") or 100), 1)
        current_next = max(int(product.get("next_edition_number") or 1), 1)
        assigned_count = int(stats.get("assigned_count") or 0)
        max_assigned = int(stats.get("max_assigned") or 0)
        proposed_next = max(max_assigned + 1, 1)
        changes.append(
            {
                "shopify_handle": handle,
                "edition_product_id": product.get("id"),
                "edition_total": edition_total,
                "assigned_count_before": int(before_stats.get("assigned_count") or 0),
                "max_assigned_before": int(before_stats.get("max_assigned") or 0),
                "assigned_count_after": assigned_count,
                "max_assigned_after": max_assigned,
                "current_next_edition_number": current_next,
                "proposed_next_edition_number": proposed_next,
                "current_remaining_count": product.get("remaining_count"),
                "proposed_remaining_count": max(edition_total - assigned_count, 0),
            }
        )
    return changes


def _audit_delete(cur, row, kept_row=None):
    cur.execute(
        """
        INSERT INTO audit_logs(
            event_type, entity_type, entity_id,
            shopify_order_id, shopify_line_item_id, shopify_handle,
            old_value, new_value, reason, actor, source
        )
        VALUES (
            'repair_duplicate_order_allocation',
            'edition_order',
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            'Shopify order has 1 item; duplicate allocation from resync',
            'developer_repair_script',
            'repair_sc2880_sc2883_single_order_duplicates'
        )
        """,
        (
            row.get("id"),
            row.get("shopify_order_id"),
            row.get("shopify_line_item_id"),
            row.get("shopify_handle"),
            json.dumps(row, default=_json_default),
            json.dumps(
                {
                    "action": "repair_duplicate_order_allocation",
                    "order_name": row.get("shopify_order_name") or row.get("order_name"),
                    "deleted_row_id": row.get("id"),
                    "deleted_edition_number": row.get("edition_number"),
                    "kept_row_id": (kept_row or {}).get("id"),
                    "kept_edition_number": (kept_row or {}).get("edition_number"),
                    "product": row.get("product_title") or row.get("shopify_handle"),
                    "variant": row.get("variant_title"),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                default=_json_default,
            ),
        ),
    )


def _apply_repair(cur, plan, counter_changes):
    kept_by_order = {
        row.get("shopify_order_name") or row.get("order_name"): row
        for row in plan["rows_to_keep"]
    }
    for row in plan["rows_to_delete"]:
        _audit_delete(cur, row, kept_by_order.get(row.get("shopify_order_name") or row.get("order_name")))
    if plan["delete_ids"]:
        cur.execute("DELETE FROM edition_orders WHERE id::text = ANY(%s)", (plan["delete_ids"],))
    for order_name, detail in plan["orders"].items():
        keep = detail.get("keep") or {}
        if not keep:
            continue
        allocation_key = supabase_backend.allocation_identity_key(
            keep.get("shopify_order_id"),
            keep.get("shopify_line_item_id") or f"{keep.get('shopify_order_id')}:line:1",
            1,
        )
        cur.execute(
            """
            UPDATE edition_orders
            SET allocation_index=1,
                allocation_key=COALESCE(NULLIF(allocation_key, ''), %s),
                updated_at=now()
            WHERE id::text=%s
            """,
            (allocation_key, keep.get("id")),
        )
    for change in counter_changes:
        cur.execute(
            """
            UPDATE edition_products
            SET next_edition_number=%s,
                remaining_count=%s,
                last_assigned_edition=GREATEST(COALESCE(last_assigned_edition, 0), %s),
                updated_at=now()
            WHERE shopify_handle=%s
            """,
            (
                change["proposed_next_edition_number"],
                change["proposed_remaining_count"],
                change["max_assigned_after"],
                change["shopify_handle"],
            ),
        )


def _ensure_order_sync_lock_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_order_sync_locks (
            id BIGSERIAL PRIMARY KEY,
            canonical_order_key TEXT UNIQUE NOT NULL,
            shopify_order_id TEXT,
            shopify_order_name TEXT,
            status TEXT DEFAULT 'allocated',
            reason TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_order_sync_locks_order_id ON edition_order_sync_locks(shopify_order_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_edition_order_sync_locks_order_name ON edition_order_sync_locks(shopify_order_name)")


def _backfill_order_sync_locks(cur):
    _ensure_order_sync_lock_table(cur)
    cur.execute(
        """
        INSERT INTO edition_order_sync_locks(
            canonical_order_key, shopify_order_id, shopify_order_name, status, reason, updated_at
        )
        SELECT DISTINCT ON (canonical_order_key)
               canonical_order_key,
               shopify_order_id,
               shopify_order_name,
               'allocated',
               'Backfilled after SC2880-SC2883 duplicate repair',
               now()
        FROM (
            SELECT CASE
                       WHEN COALESCE(eo.shopify_order_id, '') <> ''
                       THEN 'id:' || regexp_replace(eo.shopify_order_id, '^gid://shopify/[^/]+/', '', 'i')
                       WHEN COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) <> ''
                       THEN 'name:' || UPPER(TRIM(COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, ''))))
                       ELSE ''
                   END AS canonical_order_key,
                   eo.shopify_order_id,
                   COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS shopify_order_name,
                   eo.created_at,
                   eo.id::text AS row_id
            FROM edition_orders eo
            LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
        ) valid_orders
        WHERE canonical_order_key <> ''
        ORDER BY canonical_order_key, created_at ASC NULLS LAST, row_id ASC
        ON CONFLICT (canonical_order_key) DO UPDATE SET
            shopify_order_id=COALESCE(NULLIF(edition_order_sync_locks.shopify_order_id, ''), EXCLUDED.shopify_order_id),
            shopify_order_name=COALESCE(NULLIF(edition_order_sync_locks.shopify_order_name, ''), EXCLUDED.shopify_order_name),
            updated_at=now()
        """
    )


def _safe_create_exact_clone_index(cur):
    try:
        cur.execute("SAVEPOINT repair_exact_clone_index")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_exact_clone_unique
            ON edition_orders(
                LOWER(TRIM(COALESCE(shopify_order_name, ''))),
                LOWER(TRIM(COALESCE(shopify_order_id, ''))),
                LOWER(TRIM(COALESCE(shopify_line_item_id, ''))),
                LOWER(TRIM(COALESCE(shopify_handle, product_handle, product_title, ''))),
                LOWER(TRIM(COALESCE(variant_title, ''))),
                COALESCE(edition_number, 0),
                COALESCE(edition_total, 0)
            )
            WHERE COALESCE(shopify_order_name, shopify_order_id, '') <> ''
              AND edition_number IS NOT NULL
              AND edition_total IS NOT NULL
            """
        )
        cur.execute("RELEASE SAVEPOINT repair_exact_clone_index")
        return {"created": True, "error": ""}
    except Exception as error:
        cur.execute("ROLLBACK TO SAVEPOINT repair_exact_clone_index")
        cur.execute("RELEASE SAVEPOINT repair_exact_clone_index")
        return {"created": False, "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description="Repair SC2880-SC2883 to one edition_order per Shopify order.")
    parser.add_argument("--apply", action="store_true", help="Apply deletes and counter updates.")
    parser.add_argument(CONFIRM_FLAG, dest="confirmed", action="store_true", help="Required with --apply.")
    args = parser.parse_args()
    if args.apply and not args.confirmed:
        raise SystemExit(f"Apply mode requires {CONFIRM_FLAG}.")
    _load_dotenv()
    if not supabase_backend.is_configured():
        print(json.dumps({
            "mode": "apply" if args.apply else "dry_run",
            "configured": False,
            "error": "DATABASE_URL/Supabase is not configured in this environment.",
            "changes_made": False,
        }, indent=2))
        return 2

    report = {"mode": "apply" if args.apply else "dry_run", "changes_made": False}
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                rows = _fetch_target_rows(cur)
                plan = build_repair_plan(rows)
                counter_changes = _counter_plan(cur, plan["affected_products"], plan["delete_ids"])
                report.update({
                    "matching_rows_before": [_public_row(row) for row in rows],
                    "orders": plan["orders"],
                    "rows_to_keep": plan["rows_to_keep"],
                    "rows_to_delete": plan["rows_to_delete"],
                    "rows_to_delete_count": len(plan["delete_ids"]),
                    "affected_products": plan["affected_products"],
                    "proposed_counter_changes": counter_changes,
                    "before_counts": {name: detail["before_count"] for name, detail in plan["orders"].items()},
                    "after_counts": {name: detail["after_count"] for name, detail in plan["orders"].items()},
                    "order_sync_locks_backfilled": False,
                    "exact_clone_index": {"created": False, "error": ""},
                })
                if args.apply:
                    _apply_repair(cur, plan, counter_changes)
                    _backfill_order_sync_locks(cur)
                    report["exact_clone_index"] = _safe_create_exact_clone_index(cur)
                    conn.commit()
                    report["changes_made"] = True
                    report["order_sync_locks_backfilled"] = True
                else:
                    conn.rollback()
        except Exception as error:
            conn.rollback()
            report["error"] = str(error)
            print(json.dumps(report, indent=2, default=_json_default))
            return 1

    print(json.dumps(report, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
