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


APPLY_CONFIRM_FLAG = "--i-understand-this-deletes-duplicate-edition-rows"


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


def _norm(value):
    return " ".join(_clean(value).lower().split())


def _canon_shopify_id(value):
    return supabase_backend.canonical_shopify_id(value)


def _row_id_sort_value(value):
    text = _clean(value)
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def _allocation_group_key(row):
    allocation_key = _clean(row.get("allocation_key"))
    if allocation_key:
        return allocation_key
    order_id = _canon_shopify_id(row.get("shopify_order_id"))
    line_id = _canon_shopify_id(row.get("shopify_line_item_id"))
    if not order_id or not line_id:
        return ""
    return supabase_backend.allocation_identity_key(
        order_id,
        line_id,
        row.get("allocation_index") or 1,
    )


def _exact_clone_key(row):
    order_identity = _canon_shopify_id(row.get("shopify_order_id")) or _norm(row.get("shopify_order_name"))
    product_identity = (
        _norm(row.get("shopify_handle"))
        or _norm(row.get("product_handle"))
        or _norm(row.get("product_title"))
    )
    if not order_identity or not product_identity:
        return ()
    edition_number = row.get("edition_number")
    edition_total = row.get("edition_total")
    if edition_number is None or edition_total is None:
        return ()
    return (
        order_identity,
        _canon_shopify_id(row.get("shopify_line_item_id")) or "",
        product_identity,
        _canon_shopify_id(row.get("shopify_variant_id")) or _norm(row.get("variant_title")),
        _norm(row.get("customer_email")) or _norm(row.get("customer_name")),
        str(edition_number),
        str(edition_total),
    )


def _has_completed_work(row):
    status_text = " ".join(
        _clean(row.get(key)).lower()
        for key in (
            "certificate_status",
            "status",
            "certificate_asset_status",
            "prodigi_status",
        )
    )
    if any(marker in status_text for marker in ("ready", "uploaded", "complete", "completed", "sent", "fulfilled")):
        return True
    return bool(row.get("certificate_id") or row.get("shopify_file_url") or row.get("prodigi_row_id"))


def _keep_sort_key(row):
    return (
        0 if _has_completed_work(row) else 1,
        _clean(row.get("created_at")) or _clean(row.get("assigned_at")) or "",
        _row_id_sort_value(row.get("id")),
    )


def _public_row(row):
    return {
        "id": _clean(row.get("id")),
        "shopify_order_name": _clean(row.get("shopify_order_name")),
        "shopify_order_id": _clean(row.get("shopify_order_id")),
        "shopify_line_item_id": _clean(row.get("shopify_line_item_id")),
        "allocation_key": _clean(row.get("allocation_key")),
        "allocation_index": row.get("allocation_index"),
        "shopify_handle": _clean(row.get("shopify_handle") or row.get("product_handle")),
        "product_title": _clean(row.get("product_title")),
        "variant_title": _clean(row.get("variant_title")),
        "customer_email": _clean(row.get("customer_email")),
        "customer_name": _clean(row.get("customer_name")),
        "edition_number": row.get("edition_number"),
        "edition_total": row.get("edition_total"),
        "certificate_status": _clean(row.get("certificate_status")),
        "certificate_id": _clean(row.get("certificate_id")),
        "prodigi_status": _clean(row.get("prodigi_status")),
        "created_at": row.get("created_at"),
        "assigned_at": row.get("assigned_at"),
    }


def build_repair_plan(rows):
    exact_groups = {}
    allocation_groups = {}
    for row in rows:
        exact_key = _exact_clone_key(row)
        if exact_key:
            exact_groups.setdefault(exact_key, []).append(row)
        allocation_key = _allocation_group_key(row)
        if allocation_key:
            allocation_groups.setdefault(allocation_key, []).append(row)

    duplicate_groups = []
    delete_by_id = {}
    affected_products = {}
    for key, group_rows in exact_groups.items():
        if len(group_rows) <= 1:
            continue
        sorted_rows = sorted(group_rows, key=_keep_sort_key)
        keep = sorted_rows[0]
        delete_rows = sorted_rows[1:]
        for row in delete_rows:
            delete_by_id[_clean(row.get("id"))] = row
            handle = _clean(row.get("shopify_handle") or row.get("product_handle"))
            if handle:
                affected_products[handle] = True
        duplicate_groups.append(
            {
                "duplicate_type": "exact_clone",
                "group_key": "|".join(key),
                "row_count": len(group_rows),
                "keep": _public_row(keep),
                "delete": [_public_row(row) for row in delete_rows],
            }
        )

    allocation_risk_groups = []
    for key, group_rows in allocation_groups.items():
        if len(group_rows) <= 1:
            continue
        edition_numbers = {str(row.get("edition_number")) for row in group_rows}
        allocation_risk_groups.append(
            {
                "duplicate_type": "allocation_key",
                "group_key": key,
                "row_count": len(group_rows),
                "edition_numbers": sorted(edition_numbers),
                "rows": [_public_row(row) for row in sorted(group_rows, key=_keep_sort_key)],
                "delete_proposed": len(edition_numbers) == 1,
            }
        )

    return {
        "duplicate_groups": duplicate_groups,
        "allocation_risk_groups": allocation_risk_groups,
        "delete_rows": [_public_row(row) for row in delete_by_id.values()],
        "delete_ids": sorted(delete_by_id),
        "affected_products": sorted(affected_products),
    }


def _table_exists(cur, table_name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table_name,))
    return bool((cur.fetchone() or {}).get("exists"))


def _fetch_rows(cur):
    has_certificates = _table_exists(cur, "certificates")
    has_prodigi = _table_exists(cur, "prodigi_dispatch_rows")
    certificate_select = """
        c.certificate_id,
        COALESCE(c.asset_sync_status, c.certificate_status, '') AS certificate_asset_status,
        COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url
    """ if has_certificates else "NULL AS certificate_id, NULL AS certificate_asset_status, NULL AS shopify_file_url"
    certificate_join = """
        LEFT JOIN LATERAL (
            SELECT certificate_id, asset_sync_status, certificate_status, shopify_file_url, certificate_file_url
            FROM certificates c
            WHERE COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
            ORDER BY c.generated_at DESC NULLS LAST, c.created_at DESC NULLS LAST
            LIMIT 1
        ) c ON TRUE
    """ if has_certificates else ""
    prodigi_select = "pd.row_id AS prodigi_row_id, pd.prodigi_status" if has_prodigi else "NULL AS prodigi_row_id, NULL AS prodigi_status"
    prodigi_join = """
        LEFT JOIN LATERAL (
            SELECT row_id, prodigi_status
            FROM prodigi_dispatch_rows pd
            WHERE pd.shopify_line_item_id = eo.shopify_line_item_id
              AND (pd.edition_number IS NULL OR pd.edition_number = eo.edition_number)
            ORDER BY pd.updated_at DESC NULLS LAST, pd.submitted_at DESC NULLS LAST
            LIMIT 1
        ) pd ON TRUE
    """ if has_prodigi else ""
    cur.execute(
        f"""
        SELECT eo.id::text AS id,
               eo.shopify_order_id,
               eo.shopify_order_name,
               eo.shopify_line_item_id,
               eo.shopify_product_id,
               eo.shopify_variant_id,
               eo.shopify_handle,
               eo.product_handle,
               eo.product_title,
               eo.variant_title,
               eo.customer_name,
               eo.customer_email,
               eo.edition_number,
               eo.edition_total,
               eo.allocation_index,
               eo.allocation_key,
               eo.certificate_status,
               eo.status,
               eo.created_at,
               eo.assigned_at,
               {certificate_select},
               {prodigi_select}
        FROM edition_orders eo
        {certificate_join}
        {prodigi_join}
        ORDER BY eo.created_at ASC NULLS LAST, eo.assigned_at ASC NULLS LAST, eo.id::text ASC
        """
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
              AND NOT (id::text = ANY(%s))
            """,
            (handle, delete_ids),
        )
        stats = cur.fetchone() or {}
        edition_total = max(int(product.get("edition_total") or 100), 1)
        current_next = max(int(product.get("next_edition_number") or 1), 1)
        assigned_count = int(stats.get("assigned_count") or 0)
        max_assigned = int(stats.get("max_assigned") or 0)
        proposed_next = max(current_next, max_assigned + 1)
        proposed_remaining = max(edition_total - assigned_count, 0)
        changes.append(
            {
                "shopify_handle": handle,
                "edition_product_id": product.get("id"),
                "edition_total": edition_total,
                "assigned_count_after": assigned_count,
                "max_assigned_after": max_assigned,
                "current_next_edition_number": current_next,
                "proposed_next_edition_number": proposed_next,
                "current_remaining_count": product.get("remaining_count"),
                "proposed_remaining_count": proposed_remaining,
            }
        )
    return changes


def _apply_repair(cur, plan, counter_changes):
    delete_ids = plan["delete_ids"]
    if delete_ids:
        cur.execute(
            """
            DELETE FROM edition_orders
            WHERE id::text = ANY(%s)
            """,
            (delete_ids,),
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
        cur.execute(
            """
            UPDATE edition_runs er
            SET next_edition_number=GREATEST(COALESCE(er.next_edition_number, 1), %s),
                updated_at=now()
            FROM edition_products ep
            WHERE ep.shopify_handle=%s
              AND ep.active_edition_run_id=er.id
            """,
            (
                change["proposed_next_edition_number"],
                change["shopify_handle"],
            ),
        )


def _install_db_protection(cur):
    cur.execute(
        """
        UPDATE edition_orders
        SET allocation_key =
            COALESCE(NULLIF(regexp_replace(shopify_order_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_order_id)
            || ':' ||
            COALESCE(NULLIF(regexp_replace(shopify_line_item_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_line_item_id)
            || ':' ||
            GREATEST(COALESCE(allocation_index, 1), 1)::text
        WHERE COALESCE(allocation_key, '') = ''
          AND COALESCE(shopify_order_id, '') <> ''
          AND COALESCE(shopify_line_item_id, '') <> ''
        """
    )
    cur.execute("DROP INDEX IF EXISTS idx_edition_orders_allocation_key_unique")
    cur.execute(
        """
        CREATE UNIQUE INDEX idx_edition_orders_allocation_key_unique
        ON edition_orders(allocation_key)
        WHERE COALESCE(allocation_key, '') <> ''
        """
    )
    cur.execute("DROP INDEX IF EXISTS idx_edition_orders_exact_clone_unique")
    cur.execute(
        """
        CREATE UNIQUE INDEX idx_edition_orders_exact_clone_unique
        ON edition_orders(
            LOWER(TRIM(COALESCE(
                NULLIF(regexp_replace(shopify_order_id, '^gid://shopify/[^/]+/', '', 'i'), ''),
                NULLIF(shopify_order_name, ''),
                shopify_order_id,
                ''
            ))),
            LOWER(TRIM(COALESCE(
                NULLIF(regexp_replace(shopify_line_item_id, '^gid://shopify/[^/]+/', '', 'i'), ''),
                ''
            ))),
            LOWER(TRIM(COALESCE(NULLIF(shopify_handle, ''), NULLIF(product_handle, ''), NULLIF(product_title, ''), ''))),
            LOWER(TRIM(COALESCE(
                NULLIF(regexp_replace(shopify_variant_id, '^gid://shopify/[^/]+/', '', 'i'), ''),
                NULLIF(variant_title, ''),
                ''
            ))),
            LOWER(TRIM(COALESCE(NULLIF(customer_email, ''), NULLIF(customer_name, ''), ''))),
            edition_number,
            edition_total
        )
        WHERE COALESCE(shopify_order_id, shopify_order_name, '') <> ''
          AND COALESCE(shopify_handle, product_handle, product_title, '') <> ''
          AND edition_number IS NOT NULL
          AND edition_total IS NOT NULL
        """
    )


def main():
    parser = argparse.ArgumentParser(description="Dry-run or apply duplicate edition_order repair.")
    parser.add_argument("--apply", action="store_true", help="Apply the repair.")
    parser.add_argument(
        APPLY_CONFIRM_FLAG,
        dest="confirmed",
        action="store_true",
        help="Required with --apply. Confirms duplicate edition rows may be deleted.",
    )
    args = parser.parse_args()
    _load_dotenv()

    if args.apply and not args.confirmed:
        raise SystemExit(f"Apply mode requires {APPLY_CONFIRM_FLAG}.")
    if not supabase_backend.is_configured():
        print(json.dumps({
            "mode": "apply" if args.apply else "dry_run",
            "configured": False,
            "error": "DATABASE_URL/Supabase is not configured in this environment.",
            "changes_made": False,
        }, indent=2))
        return 2

    report = {
        "mode": "apply" if args.apply else "dry_run",
        "changes_made": False,
        "apply_requested": bool(args.apply),
    }
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                rows = _fetch_rows(cur)
                plan = build_repair_plan(rows)
                counter_changes = _counter_plan(cur, plan["affected_products"], plan["delete_ids"])
                report.update({
                    "total_edition_orders_before": len(rows),
                    "duplicate_groups_found": len(plan["duplicate_groups"]),
                    "allocation_risk_groups_found": len(plan["allocation_risk_groups"]),
                    "rows_to_delete_count": len(plan["delete_ids"]),
                    "rows_to_keep": [group["keep"] for group in plan["duplicate_groups"]],
                    "rows_to_delete": plan["delete_rows"],
                    "affected_products": plan["affected_products"],
                    "proposed_counter_changes": counter_changes,
                    "allocation_risk_groups": plan["allocation_risk_groups"],
                    "total_edition_orders_after": len(rows) - len(plan["delete_ids"]),
                })
                if args.apply:
                    _apply_repair(cur, plan, counter_changes)
                    _install_db_protection(cur)
                    conn.commit()
                    report["changes_made"] = True
                    report["db_protection_added"] = True
                else:
                    conn.rollback()
                    report["db_protection_added"] = False
        except Exception as error:
            conn.rollback()
            report["error"] = str(error)
            report["changes_made"] = False
            print(json.dumps(report, indent=2, default=_json_default))
            return 1

    print(json.dumps(report, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
