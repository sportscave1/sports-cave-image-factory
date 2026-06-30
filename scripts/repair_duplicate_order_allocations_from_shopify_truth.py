import argparse
import json
import os
import sys
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supabase_backend


CONFIRM_FLAG = "--i-understand-this-deletes-duplicate-edition-rows"
KNOWN_KEEP_EDITIONS = {
    "#SC2880": 25,
    "#SC2881": 26,
    "#SC2882": 27,
    "#SC2883": 63,
}
SC2884_ORDER_NAME = "#SC2884"
SC2884_RENUMBER_FROM = 65
SC2884_RENUMBER_TO = 64
ORDERS_CACHE_PATH = ROOT / "output" / "_cache" / "orders_allocation_snapshot.json"
SHOPIFY_MIRROR_KEYS = [
    "sports_cave.edition_enabled",
    "sports_cave.edition_total",
    "sports_cave.edition_next_number",
    "sports_cave.edition_sold_count",
    "sports_cave.edition_remaining",
    "sports_cave.edition_status",
    "sports_cave.edition_label",
    "sports_cave.next_edition_number",
    "sports_cave.last_assigned_edition",
    "sports_cave.sold_count",
    "sports_cave.remaining_count",
    "sports_cave.is_sold_out",
    "sports_cave.edition_display_text",
]


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


def _order_name_key(value):
    text = _clean(value).upper()
    return text if text.startswith("#") else text


def _order_keys(shopify_order_id="", shopify_order_name=""):
    keys = []
    order_id = supabase_backend.canonical_shopify_id(shopify_order_id)
    if order_id:
        keys.append(f"id:{order_id}")
    order_name = _order_name_key(shopify_order_name)
    if order_name:
        keys.append(f"name:{order_name}")
    return keys


def _primary_order_key(row):
    keys = _order_keys(row.get("shopify_order_id"), row.get("shopify_order_name") or row.get("order_name"))
    return keys[0] if keys else ""


def _row_id_sort_value(value):
    text = _clean(value)
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def _int_value(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _allocation_key(row):
    key = _clean(row.get("allocation_key"))
    if key:
        return key
    order_id = supabase_backend.canonical_shopify_id(row.get("shopify_order_id"))
    line_id = supabase_backend.canonical_shopify_id(row.get("shopify_line_item_id"))
    if not order_id or not line_id:
        return ""
    return supabase_backend.allocation_identity_key(order_id, line_id, row.get("allocation_index") or 1)


def _exact_clone_key(row):
    order_identity = supabase_backend.canonical_shopify_id(row.get("shopify_order_id")) or _order_name_key(
        row.get("shopify_order_name") or row.get("order_name")
    )
    product_identity = _norm(row.get("shopify_handle")) or _norm(row.get("product_handle")) or _norm(row.get("product_title"))
    if not order_identity or not product_identity:
        return ()
    if row.get("edition_number") is None or row.get("edition_total") is None:
        return ()
    return (
        order_identity,
        supabase_backend.canonical_shopify_id(row.get("shopify_line_item_id")) or "",
        product_identity,
        supabase_backend.canonical_shopify_id(row.get("shopify_variant_id")) or _norm(row.get("variant_title")),
        _norm(row.get("customer_email")) or _norm(row.get("customer_name")),
        str(row.get("edition_number")),
        str(row.get("edition_total")),
    )


def _has_completed_work(row):
    status_text = " ".join(
        _clean(row.get(key)).lower()
        for key in ("certificate_status", "status", "certificate_asset_status", "prodigi_status")
    )
    if any(
        marker in status_text
        for marker in ("ready", "generated", "uploaded", "complete", "completed", "sent", "fulfilled", "locked")
    ):
        return True
    return bool(
        row.get("certificate_id")
        or row.get("shopify_file_url")
        or row.get("certificate_url")
        or row.get("prodigi_row_id")
    )


def _keep_sort_key(row):
    return (
        0 if _has_completed_work(row) else 1,
        _clean(row.get("created_at")) or _clean(row.get("assigned_at")) or "",
        _row_id_sort_value(row.get("id")),
    )


def _public_row(row):
    if not row:
        return {}
    return {
        "id": _clean(row.get("id")),
        "shopify_order_name": _clean(row.get("shopify_order_name") or row.get("order_name")),
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
        "certificate_url": _clean(row.get("shopify_file_url") or row.get("certificate_url")),
        "certificate_id": _clean(row.get("certificate_id")),
        "prodigi_status": _clean(row.get("prodigi_status")),
        "created_at": row.get("created_at"),
        "assigned_at": row.get("assigned_at"),
    }


def _decorate_delete_row(row, *, reason, keep=None, duplicate_type=""):
    payload = _public_row(row)
    payload["delete_reason"] = reason
    payload["duplicate_type"] = duplicate_type
    payload["kept_row_id"] = _clean((keep or {}).get("id"))
    payload["kept_edition_number"] = (keep or {}).get("edition_number")
    return payload


def _truth_key_for_line(row):
    order_id = supabase_backend.canonical_shopify_id(row.get("shopify_order_id"))
    line_id = supabase_backend.canonical_shopify_id(row.get("shopify_line_item_id"))
    if not order_id or not line_id:
        return ""
    return f"{order_id}:{line_id}"


def _build_truth_index(shopify_lines):
    truth_by_key = {}
    truth_by_line = {}
    for row in shopify_lines or []:
        if not row.get("eligible"):
            continue
        quantity = max(_int_value(row.get("quantity"), 1), 1)
        order_keys = _order_keys(row.get("shopify_order_id"), row.get("order_name"))
        if not order_keys:
            continue
        primary_key = order_keys[0]
        truth = truth_by_key.get(primary_key)
        if not truth:
            truth = {
                "order_key": primary_key,
                "shopify_order_id": _clean(row.get("shopify_order_id")),
                "shopify_order_name": _clean(row.get("order_name")),
                "expected_units": 0,
                "eligible_lines": [],
                "aliases": set(order_keys),
            }
        truth["expected_units"] += quantity
        truth["eligible_lines"].append(
            {
                "shopify_line_item_id": _clean(row.get("shopify_line_item_id")),
                "quantity": quantity,
                "product_title": _clean(row.get("product_title")),
                "variant_title": _clean(row.get("variant_title")),
                "shopify_handle": _clean(row.get("shopify_handle")),
            }
        )
        truth["aliases"].update(order_keys)
        for key in order_keys:
            truth_by_key[key] = truth
        line_key = _truth_key_for_line(row)
        if line_key:
            truth_by_line[line_key] = truth
    return truth_by_key, truth_by_line


def _row_truth(row, truth_by_key):
    for key in _order_keys(row.get("shopify_order_id"), row.get("shopify_order_name") or row.get("order_name")):
        truth = truth_by_key.get(key)
        if truth:
            return truth
    return None


def build_repair_plan(
    edition_rows,
    shopify_lines=None,
    *,
    include_sc2884_renumber=True,
    known_orders_only=False,
):
    truth_by_key, _truth_by_line = _build_truth_index(shopify_lines or [])
    delete_by_id = OrderedDict()
    matching_row_by_id = OrderedDict()
    keep_ids = set()
    groups = []
    known_reports = {}
    renumber_reports = []
    manual_review = []
    affected_products = OrderedDict()
    order_before_after = OrderedDict()

    def row_id(row):
        return _clean(row.get("id"))

    def note_matching(*rows):
        for row in rows:
            rid = row_id(row)
            if rid and rid not in matching_row_by_id:
                matching_row_by_id[rid] = _public_row(row)

    def mark_delete(row, *, reason, keep=None, duplicate_type=""):
        rid = row_id(row)
        if not rid or rid in keep_ids or rid in delete_by_id:
            return
        delete_by_id[rid] = _decorate_delete_row(row, reason=reason, keep=keep, duplicate_type=duplicate_type)
        handle = _clean(row.get("shopify_handle") or row.get("product_handle"))
        if handle:
            affected_products[handle] = True

    rows_by_name = {}
    for row in edition_rows or []:
        name_key = _order_name_key(row.get("shopify_order_name") or row.get("order_name"))
        if name_key:
            rows_by_name.setdefault(name_key, []).append(row)

    for order_name, keep_edition in KNOWN_KEEP_EDITIONS.items():
        name_key = _order_name_key(order_name)
        rows = rows_by_name.get(name_key) or []
        note_matching(*rows)
        keep_candidates = [row for row in rows if _int_value(row.get("edition_number")) == keep_edition]
        keep = sorted(keep_candidates, key=_keep_sort_key)[0] if keep_candidates else None
        if keep:
            keep_ids.add(row_id(keep))
        delete_rows = [row for row in rows if keep and row_id(row) != row_id(keep)]
        for row in delete_rows:
            mark_delete(
                row,
                reason=f"{order_name} is confirmed as one Shopify item; keep #{keep_edition:03d}/100 only.",
                keep=keep,
                duplicate_type="known_shopify_truth_override",
            )
        known_reports[order_name] = {
            "expected_keep_edition_number": keep_edition,
            "before_count": len(rows),
            "after_count": 1 if keep else 0,
            "keep": _public_row(keep),
            "delete": [delete_by_id[row_id(row)] for row in delete_rows if row_id(row) in delete_by_id],
            "error": "" if keep else f"No row found for required edition #{keep_edition}.",
        }
        order_before_after[order_name] = {
            "before": len(rows),
            "after": 1 if keep else 0,
            "expected_units": 1,
            "source": "known_shopify_truth_override",
        }

    def remaining(rows):
        return [row for row in rows if row_id(row) not in delete_by_id]

    if not known_orders_only:
        allocation_groups = {}
        for row in remaining(edition_rows or []):
            key = _allocation_key(row)
            if key:
                allocation_groups.setdefault(key, []).append(row)
        for key, rows in allocation_groups.items():
            if len(rows) <= 1:
                continue
            note_matching(*rows)
            sorted_rows = sorted(rows, key=_keep_sort_key)
            keep = sorted_rows[0]
            keep_ids.add(row_id(keep))
            delete_rows = sorted_rows[1:]
            for row in delete_rows:
                mark_delete(
                    row,
                    reason="Same allocation_key/order-line-unit was allocated more than once.",
                    keep=keep,
                    duplicate_type="allocation_key",
                )
            groups.append(
                {
                    "duplicate_type": "allocation_key",
                    "group_key": key,
                    "row_count": len(rows),
                    "keep": _public_row(keep),
                    "delete": [delete_by_id[row_id(row)] for row in delete_rows if row_id(row) in delete_by_id],
                }
            )

        exact_groups = {}
        for row in remaining(edition_rows or []):
            key = _exact_clone_key(row)
            if key:
                exact_groups.setdefault(key, []).append(row)
        for key, rows in exact_groups.items():
            if len(rows) <= 1:
                continue
            note_matching(*rows)
            sorted_rows = sorted(rows, key=_keep_sort_key)
            keep = sorted_rows[0]
            keep_ids.add(row_id(keep))
            delete_rows = sorted_rows[1:]
            for row in delete_rows:
                mark_delete(
                    row,
                    reason="Exact clone edition_order row repeated.",
                    keep=keep,
                    duplicate_type="exact_clone",
                )
            groups.append(
                {
                    "duplicate_type": "exact_clone",
                    "group_key": "|".join(key),
                    "row_count": len(rows),
                    "keep": _public_row(keep),
                    "delete": [delete_by_id[row_id(row)] for row in delete_rows if row_id(row) in delete_by_id],
                }
            )

        order_groups = {}
        for row in remaining(edition_rows or []):
            truth = _row_truth(row, truth_by_key)
            if truth:
                order_groups.setdefault(truth["order_key"], {"truth": truth, "rows": []})["rows"].append(row)
        for order_key, detail in order_groups.items():
            rows = remaining(detail["rows"])
            expected_units = int(detail["truth"].get("expected_units") or 0)
            if expected_units <= 0 or len(rows) <= expected_units:
                continue
            note_matching(*rows)
            sorted_rows = sorted(rows, key=_keep_sort_key)
            keep_rows = sorted_rows[:expected_units]
            for keep in keep_rows:
                keep_ids.add(row_id(keep))
            delete_rows = sorted_rows[expected_units:]
            for row in delete_rows:
                mark_delete(
                    row,
                    reason="Actual edition_orders count exceeds Shopify mirror expected eligible units.",
                    keep=keep_rows[0] if keep_rows else None,
                    duplicate_type="shopify_expected_units_overflow",
                )
            groups.append(
                {
                    "duplicate_type": "shopify_expected_units_overflow",
                    "group_key": order_key,
                    "expected_units": expected_units,
                    "actual_rows": len(rows),
                    "eligible_lines": detail["truth"].get("eligible_lines") or [],
                    "keep": [_public_row(row) for row in keep_rows],
                    "delete": [delete_by_id[row_id(row)] for row in delete_rows if row_id(row) in delete_by_id],
                }
            )
            order_name = detail["truth"].get("shopify_order_name") or order_key
            order_before_after[order_name] = {
                "before": len(rows),
                "after": expected_units,
                "expected_units": expected_units,
                "source": "shopify_mirror_expected_units",
            }

    if include_sc2884_renumber:
        valid_after_delete = [row for row in edition_rows or [] if row_id(row) not in delete_by_id]
        sc2884_rows = [
            row
            for row in valid_after_delete
            if _order_name_key(row.get("shopify_order_name") or row.get("order_name")) == SC2884_ORDER_NAME
        ]
        sc2884_65_rows = [
            row for row in sc2884_rows if _int_value(row.get("edition_number")) == SC2884_RENUMBER_FROM
        ]
        if sc2884_65_rows:
            candidate = sorted(sc2884_65_rows, key=_keep_sort_key)[0]
            handle = _clean(candidate.get("shopify_handle") or candidate.get("product_handle"))
            edition_64_owner = next(
                (
                    row
                    for row in valid_after_delete
                    if _clean(row.get("shopify_handle") or row.get("product_handle")) == handle
                    and _int_value(row.get("edition_number")) == SC2884_RENUMBER_TO
                    and row_id(row) != row_id(candidate)
                ),
                None,
            )
            if _has_completed_work(candidate):
                manual_review.append(
                    {
                        "order_name": SC2884_ORDER_NAME,
                        "reason": "#SC2884 already has certificate/Prodigi-visible work; do not renumber automatically.",
                        "row": _public_row(candidate),
                    }
                )
            elif edition_64_owner:
                manual_review.append(
                    {
                        "order_name": SC2884_ORDER_NAME,
                        "reason": "#064/100 is already owned by another valid order after duplicate deletions.",
                        "row": _public_row(candidate),
                        "blocking_owner": _public_row(edition_64_owner),
                    }
                )
            else:
                report = _public_row(candidate)
                report["old_edition_number"] = SC2884_RENUMBER_FROM
                report["new_edition_number"] = SC2884_RENUMBER_TO
                report["reason"] = "#SC2884 was allocated after fake #064 duplicate rows; #064 is free after repair."
                renumber_reports.append(report)
                if handle:
                    affected_products[handle] = True
                note_matching(candidate)

    delete_rows = list(delete_by_id.values())
    sc2884_result = "unchanged"
    if renumber_reports:
        sc2884_result = f"renumber #{SC2884_RENUMBER_FROM:03d}/100 -> #{SC2884_RENUMBER_TO:03d}/100"
    elif any(item.get("order_name") == SC2884_ORDER_NAME for item in manual_review):
        sc2884_result = "manual review required"
    return {
        "known_repairs": known_reports,
        "duplicate_groups": groups,
        "renumber_rows": renumber_reports,
        "manual_review": manual_review,
        "matching_rows_before": list(matching_row_by_id.values()),
        "delete_ids": list(delete_by_id.keys()),
        "rows_to_delete": delete_rows,
        "rows_to_keep": [group.get("keep") for group in groups if group.get("keep")],
        "affected_products": list(affected_products.keys()),
        "shopify_metafield_mirror_keys": SHOPIFY_MIRROR_KEYS,
        "expected_orders_page_result": {
            "#SC2880": "one row #025/100",
            "#SC2881": "one row #026/100",
            "#SC2882": "one row #027/100",
            "#SC2883": "one row #063/100",
            "#SC2884": sc2884_result,
        },
        "expected_before_after": {
            name: {"before": detail["before_count"], "after": detail["after_count"]}
            for name, detail in known_reports.items()
        },
        "order_before_after": order_before_after,
    }


def _table_exists(cur, table_name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table_name,))
    return bool((cur.fetchone() or {}).get("exists"))


def _fetch_shopify_lines(cur):
    cur.execute(
        """
        SELECT o.shopify_order_id,
               o.order_name,
               li.shopify_line_item_id,
               GREATEST(COALESCE(li.quantity, 1), 1) AS quantity,
               li.shopify_handle,
               li.shopify_product_id,
               li.product_title,
               li.variant_title,
               (
                   ep.id IS NOT NULL
                   OR EXISTS (
                       SELECT 1
                       FROM edition_orders eo
                       WHERE (
                           eo.shopify_line_item_id = li.shopify_line_item_id
                           OR eo.shopify_order_id = o.shopify_order_id
                           OR UPPER(TRIM(COALESCE(eo.shopify_order_name, ''))) = UPPER(TRIM(COALESCE(o.order_name, '')))
                       )
                       AND LOWER(TRIM(COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(eo.product_handle, ''), NULLIF(eo.product_title, '')))) =
                           LOWER(TRIM(COALESCE(NULLIF(li.shopify_handle, ''), NULLIF(li.product_title, ''), '')))
                   )
               ) AS eligible
        FROM shopify_orders o
        LEFT JOIN shopify_order_lines li ON li.shopify_order_id = o.shopify_order_id
        LEFT JOIN edition_products ep
          ON (
              (COALESCE(li.shopify_handle, '') <> '' AND ep.shopify_handle = li.shopify_handle)
              OR (COALESCE(li.shopify_product_id, '') <> '' AND ep.shopify_product_id = li.shopify_product_id)
          )
         AND COALESCE(ep.active, ep.is_active, TRUE) IS NOT FALSE
        WHERE li.id IS NOT NULL
        ORDER BY o.order_name ASC NULLS LAST, li.id ASC
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_edition_rows(cur):
    has_certificates = _table_exists(cur, "certificates")
    has_prodigi = _table_exists(cur, "prodigi_dispatch_rows")
    certificate_select = (
        """
        c.certificate_id,
        COALESCE(c.asset_sync_status, c.certificate_status, '') AS certificate_asset_status,
        COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS shopify_file_url
        """
        if has_certificates
        else "NULL AS certificate_id, NULL AS certificate_asset_status, NULL AS shopify_file_url"
    )
    certificate_join = (
        """
        LEFT JOIN LATERAL (
            SELECT certificate_id, asset_sync_status, certificate_status, shopify_file_url, certificate_file_url
            FROM certificates c
            WHERE COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
            ORDER BY c.generated_at DESC NULLS LAST, c.created_at DESC NULLS LAST
            LIMIT 1
        ) c ON TRUE
        """
        if has_certificates
        else ""
    )
    prodigi_select = "pd.row_id AS prodigi_row_id, pd.prodigi_status" if has_prodigi else "NULL AS prodigi_row_id, NULL AS prodigi_status"
    prodigi_join = (
        """
        LEFT JOIN LATERAL (
            SELECT row_id, prodigi_status
            FROM prodigi_dispatch_rows pd
            WHERE pd.shopify_line_item_id = eo.shopify_line_item_id
              AND (pd.edition_number IS NULL OR pd.edition_number = eo.edition_number)
            ORDER BY pd.updated_at DESC NULLS LAST, pd.submitted_at DESC NULLS LAST
            LIMIT 1
        ) pd ON TRUE
        """
        if has_prodigi
        else ""
    )
    cur.execute(
        f"""
        SELECT eo.id::text AS id,
               eo.shopify_order_id,
               COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS shopify_order_name,
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
        LEFT JOIN shopify_orders o ON o.shopify_order_id = eo.shopify_order_id
        {certificate_join}
        {prodigi_join}
        ORDER BY eo.created_at ASC NULLS LAST, eo.assigned_at ASC NULLS LAST, eo.id::text ASC
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _counter_plan(cur, affected_products, delete_ids, renumber_rows=None):
    changes = []
    delete_id_set = {str(value) for value in delete_ids or []}
    renumber_by_id = {
        str(row.get("id")): _int_value(row.get("new_edition_number"))
        for row in renumber_rows or []
        if str(row.get("id") or "").strip()
    }
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
            SELECT id::text AS id, edition_number
            FROM edition_orders
            WHERE COALESCE(shopify_handle, product_handle, '')=%s
            """,
            (handle,),
        )
        after_numbers = [
            renumber_by_id.get(str(row.get("id")), _int_value(row.get("edition_number"), 0))
            for row in cur.fetchall()
            if str(row.get("id") or "") not in delete_id_set
        ]
        edition_total = max(_int_value(product.get("edition_total"), 100), 1)
        assigned_count = len([number for number in after_numbers if number])
        max_assigned = max(after_numbers or [0])
        proposed_next = max(max_assigned + 1, 1)
        changes.append(
            {
                "shopify_handle": handle,
                "edition_product_id": product.get("id"),
                "edition_total": edition_total,
                "assigned_count_before": _int_value(before_stats.get("assigned_count"), 0),
                "max_assigned_before": _int_value(before_stats.get("max_assigned"), 0),
                "assigned_count_after": assigned_count,
                "max_assigned_after": max_assigned,
                "current_next_edition_number": _int_value(product.get("next_edition_number"), 1),
                "proposed_next_edition_number": proposed_next,
                "current_remaining_count": product.get("remaining_count"),
                "proposed_remaining_count": max(edition_total - assigned_count, 0),
            }
        )
    return changes


def _audit_delete(cur, row):
    audit_reason = (
        row.get("audit_reason")
        or "duplicate allocation from bad resync/webhook retry, Shopify order has 1 item"
    )
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
            %s,
            'developer_repair_script',
            'repair_duplicate_order_allocations_from_shopify_truth'
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
                    "order_name": row.get("shopify_order_name"),
                    "deleted_row_id": row.get("id"),
                    "deleted_edition_number": row.get("edition_number"),
                    "kept_row_id": row.get("kept_row_id"),
                    "kept_edition_number": row.get("kept_edition_number"),
                    "product": row.get("product_title") or row.get("shopify_handle"),
                    "variant": row.get("variant_title"),
                    "duplicate_type": row.get("duplicate_type"),
                    "reason": audit_reason,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                default=_json_default,
            ),
            audit_reason,
        ),
    )


def _audit_renumber(cur, row):
    old_number = _int_value(row.get("old_edition_number"))
    new_number = _int_value(row.get("new_edition_number"))
    cur.execute(
        """
        INSERT INTO audit_logs(
            event_type, entity_type, entity_id,
            shopify_order_id, shopify_line_item_id, shopify_handle,
            old_value, new_value, reason, actor, source
        )
        VALUES (
            'repair_resequence_after_duplicate_allocation',
            'edition_order',
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s,
            'developer_repair_script',
            'repair_duplicate_order_allocations_from_shopify_truth'
        )
        """,
        (
            row.get("id"),
            row.get("shopify_order_id"),
            row.get("shopify_line_item_id"),
            row.get("shopify_handle"),
            json.dumps({"edition_number": old_number, "row": row}, default=_json_default),
            json.dumps({"edition_number": new_number, "row": row}, default=_json_default),
            row.get("reason") or "Resequence valid order after duplicate allocation repair.",
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
            status TEXT DEFAULT 'processed',
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
               'processed',
               'Backfilled after Shopify-truth duplicate allocation repair',
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
            status='processed',
            reason=COALESCE(NULLIF(edition_order_sync_locks.reason, ''), EXCLUDED.reason),
            updated_at=now()
        """
    )


def _apply_repair(cur, plan, counter_changes):
    for row in plan["rows_to_delete"]:
        _audit_delete(cur, row)
    if plan["delete_ids"]:
        cur.execute("DELETE FROM edition_orders WHERE id::text = ANY(%s)", (plan["delete_ids"],))
    for row in plan.get("renumber_rows") or []:
        _audit_renumber(cur, row)
        new_number = _int_value(row.get("new_edition_number"))
        total = _int_value(row.get("edition_total"), 100)
        cur.execute(
            """
            UPDATE edition_orders
            SET edition_number=%s,
                edition_display=%s,
                updated_at=now()
            WHERE id::text=%s
            """,
            (new_number, f"#{new_number:03d}/{total}", str(row.get("id"))),
        )
    cur.execute(
        """
        UPDATE edition_orders
        SET allocation_key =
            COALESCE(NULLIF(regexp_replace(shopify_order_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_order_id)
            || ':' ||
            COALESCE(NULLIF(regexp_replace(shopify_line_item_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_line_item_id)
            || ':' ||
            GREATEST(COALESCE(allocation_index, 1), 1)::text,
            updated_at=now()
        WHERE COALESCE(allocation_key, '') = ''
          AND COALESCE(shopify_order_id, '') <> ''
          AND COALESCE(shopify_line_item_id, '') <> ''
        """
    )
    edition_product_columns = _table_columns(cur, "edition_products")
    for change in counter_changes:
        assignments = []
        params = []
        if "next_edition_number" in edition_product_columns:
            assignments.append("next_edition_number=%s")
            params.append(change["proposed_next_edition_number"])
        if "remaining_count" in edition_product_columns:
            assignments.append("remaining_count=%s")
            params.append(change["proposed_remaining_count"])
        if "sold_count" in edition_product_columns:
            assignments.append("sold_count=%s")
            params.append(change["assigned_count_after"])
        if "last_assigned_edition" in edition_product_columns:
            assignments.append("last_assigned_edition=%s")
            params.append(change["max_assigned_after"])
        if "updated_at" in edition_product_columns:
            assignments.append("updated_at=now()")
        if assignments:
            params.append(change["shopify_handle"])
            cur.execute(
                f"""
                UPDATE edition_products
                SET {", ".join(assignments)}
                WHERE shopify_handle=%s
                """,
                tuple(params),
            )
        cur.execute(
            """
            UPDATE edition_runs er
            SET next_edition_number=%s,
                updated_at=now()
            FROM edition_products ep
            WHERE ep.shopify_handle=%s
              AND ep.active_edition_run_id=er.id
            """,
            (change["proposed_next_edition_number"], change["shopify_handle"]),
        )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_allocation_key_unique
        ON edition_orders(allocation_key)
        WHERE COALESCE(allocation_key, '') <> ''
        """
    )
    _backfill_order_sync_locks(cur)


def _delete_blockers(rows):
    return [row for row in rows or [] if _has_completed_work(row)]


def _target_order_counts(cur):
    order_names = list(KNOWN_KEEP_EDITIONS.keys())
    cur.execute(
        """
        SELECT COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS order_name,
               eo.id::text AS id,
               eo.customer_name,
               eo.product_title,
               eo.variant_title,
               eo.edition_number,
               eo.edition_total,
               eo.created_at,
               eo.certificate_status,
               eo.allocation_key
        FROM edition_orders eo
        LEFT JOIN shopify_orders o ON o.shopify_order_id = eo.shopify_order_id
        WHERE UPPER(TRIM(COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')))) = ANY(%s)
        ORDER BY order_name ASC, eo.created_at ASC NULLS LAST, eo.id::text ASC
        """,
        ([name.upper() for name in order_names],),
    )
    rows = [dict(row) for row in cur.fetchall()]
    counts = OrderedDict()
    for name in order_names:
        matching = [
            _public_row(row)
            for row in rows
            if _order_name_key(row.get("order_name") or row.get("shopify_order_name")) == name
        ]
        counts[name] = {
            "count": len(matching),
            "editions": [row.get("edition_number") for row in matching],
            "rows": matching,
        }
    return counts


def _clear_orders_cache_file():
    try:
        if not ORDERS_CACHE_PATH.exists():
            return {"cleared": False, "path": str(ORDERS_CACHE_PATH), "reason": "cache file not present"}
        ORDERS_CACHE_PATH.unlink()
        return {"cleared": True, "path": str(ORDERS_CACHE_PATH)}
    except Exception as error:
        return {"cleared": False, "path": str(ORDERS_CACHE_PATH), "error": str(error)}


def _table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name=%s
        """,
        (table_name,),
    )
    return {str((row or {}).get("column_name") or "") for row in cur.fetchall()}


def run_repair(*, apply=False, include_sc2884_renumber=False, known_orders_only=True):
    if not supabase_backend.is_configured():
        return {
            "mode": "apply" if apply else "dry_run",
            "configured": False,
            "error": "DATABASE_URL/Supabase is not configured in this environment.",
            "changes_made": False,
        }
    report = {"mode": "apply" if apply else "dry_run", "configured": True, "changes_made": False}
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                edition_rows = _fetch_edition_rows(cur)
                shopify_lines = _fetch_shopify_lines(cur)
                target_counts_before = _target_order_counts(cur)
                plan = build_repair_plan(
                    edition_rows,
                    shopify_lines,
                    include_sc2884_renumber=include_sc2884_renumber,
                    known_orders_only=known_orders_only,
                )
                counter_changes = _counter_plan(cur, plan["affected_products"], plan["delete_ids"], plan["renumber_rows"])
                delete_blockers = _delete_blockers(plan["rows_to_delete"])
                report.update(
                    {
                        "total_edition_orders_before": len(edition_rows),
                        "shopify_line_rows_checked": len(shopify_lines),
                        "known_orders_only": known_orders_only,
                        "sc2884_renumber_enabled": include_sc2884_renumber,
                        "duplicate_groups_found": len(plan["duplicate_groups"]),
                        "rows_to_delete_count": len(plan["delete_ids"]),
                        "rows_to_delete": plan["rows_to_delete"],
                        "delete_blocked_by_certificate_or_prodigi": bool(delete_blockers),
                        "delete_blockers": delete_blockers,
                        "renumber_rows": plan["renumber_rows"],
                        "manual_review": plan["manual_review"],
                        "rows_to_keep": plan["rows_to_keep"],
                        "affected_products": plan["affected_products"],
                        "shopify_metafield_mirror_keys": plan["shopify_metafield_mirror_keys"],
                        "known_repairs": plan["known_repairs"],
                        "expected_before_after": plan["expected_before_after"],
                        "expected_orders_page_result": plan["expected_orders_page_result"],
                        "order_before_after": plan["order_before_after"],
                        "matching_rows_before": plan["matching_rows_before"],
                        "proposed_counter_changes": counter_changes,
                        "target_order_counts_before": target_counts_before,
                        "total_edition_orders_after": len(edition_rows) - len(plan["delete_ids"]),
                        "target_order_counts_after_actual": None,
                        "orders_cache_cleared": {"cleared": False, "reason": "dry run"},
                        "db_protection_added": False,
                        "order_sync_locks_backfilled": False,
                    }
                )
                if apply:
                    if delete_blockers:
                        report["error"] = "Apply blocked because one or more rows to delete has certificate or Prodigi completion state."
                        conn.rollback()
                        return report
                    _apply_repair(cur, plan, counter_changes)
                    report["target_order_counts_after_actual"] = _target_order_counts(cur)
                    conn.commit()
                    report["orders_cache_cleared"] = _clear_orders_cache_file()
                    report["changes_made"] = True
                    report["db_protection_added"] = True
                    report["order_sync_locks_backfilled"] = True
                else:
                    conn.rollback()
        except Exception as error:
            conn.rollback()
            report["error"] = str(error)
            report["changes_made"] = False
            return report
    return report


def main():
    parser = argparse.ArgumentParser(description="Repair duplicate edition orders using Shopify mirror quantities as truth.")
    parser.add_argument("--apply", action="store_true", help="Apply deletes and counter updates.")
    parser.add_argument(CONFIRM_FLAG, dest="confirmed", action="store_true", help="Required with --apply.")
    parser.add_argument(
        "--include-general-duplicates",
        action="store_true",
        help="Also plan general duplicate groups beyond the known SC2880-SC2883 emergency repair.",
    )
    parser.add_argument(
        "--include-sc2884-renumber",
        action="store_true",
        help="Allow the optional SC2884 resequence check. Off by default for this emergency delete-only pass.",
    )
    args = parser.parse_args()
    if args.apply and not args.confirmed:
        raise SystemExit(f"Apply mode requires {CONFIRM_FLAG}.")
    _load_dotenv()
    report = run_repair(
        apply=args.apply,
        include_sc2884_renumber=args.include_sc2884_renumber,
        known_orders_only=not args.include_general_duplicates,
    )
    print(json.dumps(report, indent=2, default=_json_default))
    return 1 if report.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
