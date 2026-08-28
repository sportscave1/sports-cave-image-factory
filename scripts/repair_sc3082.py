#!/usr/bin/env python3
"""Guarded normal atomic allocation retry for Shopify order #SC3082.

The default mode is read-only. Applying requires the exact SHA-256 emitted by
the current dry run. The allocation and stored-error clear share one database
transaction and the normal allocator locks; a post-commit retry proves replay
idempotency.
"""

import argparse
import hashlib
import json

import edition_ledger
import supabase_backend


TARGET = {
    "order_name": "#SC3082",
    "order_id": "gid://shopify/Order/7379807207731",
    "line_item_id": "gid://shopify/LineItem/17487375302963",
    "product_gid": "gid://shopify/Product/8141604290867",
    "variant_gid": "gid://shopify/ProductVariant/52547827794227",
    "sku": "LMESSIA1",
    "handle": "lionel-messi-framed-wall-art-print-a1-a2",
}


def _json_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _snapshot_sha256(report):
    encoded = json.dumps(
        _json_value(report), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return dict(cur.fetchone() or {})


def _state(cur, *, lock=False):
    lock_sql = "FOR UPDATE OF o, li, ep, er" if lock else ""
    return _one(
        cur,
        f"""
        SELECT
            o.order_name,
            o.shopify_order_id,
            o.financial_status,
            o.fulfillment_status,
            li.shopify_line_item_id,
            li.shopify_product_id AS line_product_gid,
            COALESCE(NULLIF(to_jsonb(li)->>'shopify_variant_id', ''),
                     NULLIF(li.raw_json->>'shopify_variant_id', ''),
                     NULLIF(li.raw_json->>'variant_id', '')) AS variant_gid,
            li.sku, li.shopify_handle, li.product_title, li.variant_title,
            li.quantity, li.assignment_status, COALESCE(li.last_error, '') AS last_error,
            ep.id::text AS edition_product_id,
            COALESCE(NULLIF(ep.shopify_product_gid, ''),
                     NULLIF(ep.shopify_product_id, '')) AS product_gid,
            ep.shopify_handle AS canonical_handle,
            ep.product_title AS canonical_product_title,
            COALESCE(ep.sold_count, 0) AS sold_count,
            COALESCE(ep.remaining_count, 0) AS remaining_count,
            COALESCE(ep.next_edition_number, 1) AS next_edition_number,
            COALESCE(ep.last_assigned_edition, 0) AS last_assigned_edition,
            COALESCE(ep.edition_total, 100) AS edition_total,
            COALESCE(ep.sold_out, FALSE) OR COALESCE(ep.is_sold_out, FALSE) AS sold_out,
            COALESCE(ep.active, TRUE) AND COALESCE(ep.is_active, TRUE) AS product_active,
            er.id::text AS edition_run_id,
            COALESCE(er.status, '') AS edition_run_status,
            COALESCE(er.next_edition_number, 1) AS run_next_edition_number,
            COALESCE(er.allocation_baseline_sold_count, 0) AS stored_baseline,
            (SELECT COUNT(*) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.allocation_valid
               AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS all_run_rows,
            (SELECT MIN(eo.edition_number) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.allocation_valid
               AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS all_run_min,
            (SELECT MAX(eo.edition_number) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.allocation_valid
               AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS all_run_max,
            (SELECT COUNT(*) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.identity_enforced
               AND eo.allocation_valid AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS enforced_run_rows,
            (SELECT MIN(eo.edition_number) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.identity_enforced
               AND eo.allocation_valid AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS enforced_min,
            (SELECT MAX(eo.edition_number) FROM edition_orders eo
             WHERE eo.edition_run_id=er.id AND eo.identity_enforced
               AND eo.allocation_valid AND COALESCE(eo.status, '') NOT IN
                   ('voided','refunded','cancelled','superseded')) AS enforced_max,
            (SELECT COUNT(*) FROM edition_orders eo
             WHERE
                   (eo.external_line_item_id=%s OR eo.shopify_line_item_id=%s))
                AS line_ledger_row_count,
            (SELECT COUNT(*) FROM edition_orders eo
             WHERE eo.allocation_valid AND
                   (eo.external_line_item_id=%s OR eo.shopify_line_item_id=%s))
                AS valid_line_allocation_count,
            COALESCE(pg_get_functiondef(to_regprocedure(
                'allocate_edition_line_units_atomic(text,text,text,text,integer,text,text,text,text,text,text,text,text,text,text)'
            )), '') AS allocator_definition
        FROM shopify_orders o
        JOIN shopify_order_lines li
          ON li.shopify_order_id=o.shopify_order_id
         AND li.shopify_line_item_id=%s
        JOIN edition_products ep
          ON COALESCE(NULLIF(ep.shopify_product_gid, ''),
                      NULLIF(ep.shopify_product_id, ''))=%s
        JOIN edition_runs er ON er.id=ep.active_edition_run_id
        WHERE o.shopify_order_id=%s
        {lock_sql}
        """,
        (
            TARGET["line_item_id"],
            TARGET["line_item_id"],
            TARGET["line_item_id"],
            TARGET["line_item_id"],
            TARGET["line_item_id"],
            TARGET["product_gid"],
            TARGET["order_id"],
        ),
    )


def _canonical_gid(resource, value):
    return edition_ledger.canonical_shopify_gid(resource, value)


def _validate_state(row, *, allow_allocated):
    if not row:
        raise RuntimeError("Messi order line or canonical edition series was not found.")
    exact = {
        "order_name": TARGET["order_name"],
        "shopify_order_id": TARGET["order_id"],
        "shopify_line_item_id": TARGET["line_item_id"],
        "sku": TARGET["sku"],
        "canonical_handle": TARGET["handle"],
    }
    for key, expected in exact.items():
        if str(row.get(key) or "") != expected:
            raise RuntimeError(
                f"Messi {key} mismatch: expected {expected}, found {row.get(key)}."
            )
    if _canonical_gid("Product", row.get("line_product_gid")) != TARGET["product_gid"]:
        raise RuntimeError("Messi order line product identity does not match.")
    if _canonical_gid("Product", row.get("product_gid")) != TARGET["product_gid"]:
        raise RuntimeError("Messi canonical product identity does not match.")
    if _canonical_gid("ProductVariant", row.get("variant_gid")) != TARGET["variant_gid"]:
        raise RuntimeError("Messi variant identity does not match.")
    if int(row.get("quantity") or 0) != 1:
        raise RuntimeError("Messi target quantity is not exactly one.")
    if str(row.get("financial_status") or "").strip().casefold() != "paid":
        raise RuntimeError("Messi order is not paid.")
    fulfillment = str(row.get("fulfillment_status") or "").strip().casefold()
    if fulfillment not in ("unfulfilled", "none"):
        raise RuntimeError(
            f"Messi order is not explicitly unfulfilled: {fulfillment or 'missing'}."
        )
    if not bool(row.get("product_active")) or bool(row.get("sold_out")):
        raise RuntimeError("Messi design is not active and available.")
    if str(row.get("edition_run_status") or "").casefold() != "active":
        raise RuntimeError("Messi active edition run is not active.")
    if int(row.get("edition_total") or 0) != 100:
        raise RuntimeError("Messi edition total is no longer 100.")
    ledger_row_count = int(row.get("line_ledger_row_count") or 0)
    allocation_count = int(row.get("valid_line_allocation_count") or 0)
    if allow_allocated:
        if allocation_count != 1 or ledger_row_count != 1:
            raise RuntimeError(
                "Messi expected exactly one valid ledger allocation, found "
                f"{allocation_count} valid of {ledger_row_count} total."
            )
        if str(row.get("assignment_status") or "").strip().casefold() != "assigned":
            raise RuntimeError("Messi allocated line is not marked Assigned.")
        if str(row.get("last_error") or "").strip():
            raise RuntimeError("Messi allocation error was not cleared.")
    else:
        if allocation_count or ledger_row_count:
            raise RuntimeError(
                "Messi line already has a ledger row or valid allocation; refusing a new one."
            )
        failure = " ".join(
            [str(row.get("assignment_status") or ""), str(row.get("last_error") or "")]
        ).casefold()
        if not any(
            token in failure
            for token in ("not contiguous", "atomic edition suffix", "active edition run")
        ):
            raise RuntimeError(
                "Messi stored error does not match the audited contiguity defect: "
                f"{failure or 'missing failure detail'}."
            )
    definition = str(row.get("allocator_definition") or "")
    if "eo.identity_enforced" not in definition or "v_expected_baseline" not in definition:
        raise RuntimeError("The corrected sparse-legacy allocator is not installed.")
    count = int(row.get("enforced_run_rows") or 0)
    sold = int(row.get("sold_count") or 0)
    expected_baseline = sold - count
    if expected_baseline < 0:
        raise RuntimeError("Identity-enforced row count exceeds the sold counter.")
    if count and (
        int(row.get("enforced_min") or 0) != expected_baseline + 1
        or int(row.get("enforced_max") or 0) != sold
        or int(row.get("enforced_max") or 0)
        - int(row.get("enforced_min") or 0)
        + 1
        != count
    ):
        raise RuntimeError("Messi identity-enforced suffix is not contiguous.")
    if int(row.get("last_assigned_edition") or 0) != sold:
        raise RuntimeError("Messi last-issued counter does not match sold count.")
    if int(row.get("next_edition_number") or 0) != sold + 1:
        raise RuntimeError("Messi product next counter is inconsistent.")
    if int(row.get("run_next_edition_number") or 0) != sold + 1:
        raise RuntimeError("Messi run next counter is inconsistent.")


def build_dry_run(cur):
    state = _state(cur)
    _validate_state(state, allow_allocated=False)
    report = {
        "mode": "dry_run",
        "target": TARGET,
        "production_state": state,
        "expected_allocations": 1,
        "expected_status_rows_updated": 1,
    }
    report["snapshot_sha256"] = _snapshot_sha256(report)
    return report


def _allocate_locked(cur, before):
    quantity = int(before.get("quantity") or 1)
    cur.execute(
        """
        SELECT result->'allocation' AS allocation,
               (result->>'was_created')::boolean AS was_created
        FROM allocate_edition_line_units_atomic(
            'shopify', %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, 'assigned'
        ) AS result
        ORDER BY ((result->'allocation'->>'unit_ordinal')::integer)
        """,
        (
            TARGET["order_id"], TARGET["line_item_id"], TARGET["product_gid"], quantity,
            TARGET["order_id"], TARGET["order_name"], TARGET["line_item_id"],
            TARGET["variant_gid"],
            before.get("canonical_product_title") or before.get("product_title") or "Lionel Messi Wall Art",
            before.get("variant_title") or "", TARGET["sku"], "", "",
        ),
    )
    results = list(cur.fetchall() or [])
    created = [row for row in results if bool(row.get("was_created"))]
    if len(results) != quantity or len(created) != quantity:
        raise RuntimeError(f"Messi atomic allocation returned an unexpected result: {results}.")
    value = created[0].get("allocation") or {}
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value)


def _retry_existing(before):
    order = {
        "shopify_order_id": TARGET["order_id"],
        "order_name": TARGET["order_name"],
        "source_name": "Online Store",
    }
    line = {
        "shopify_line_item_id": TARGET["line_item_id"],
        "shopify_product_id": TARGET["product_gid"],
        "shopify_variant_id": TARGET["variant_gid"],
        "product_title": before.get("product_title") or "Lionel Messi Wall Art",
        "variant_title": before.get("variant_title") or "",
        "sku": TARGET["sku"],
        "quantity": 1,
    }
    product = {
        "shopify_product_id": TARGET["product_gid"],
        "handle": TARGET["handle"],
        "title": before.get("canonical_product_title") or "Lionel Messi Wall Art",
    }
    retry = supabase_backend.allocate_edition_line_units_atomic(
        order=order,
        line_item=line,
        product=product,
        quantity=1,
        allocation_status="assigned",
    )
    if int(retry.get("created") or 0) != 0 or int(retry.get("existing") or 0) != 1:
        raise RuntimeError(f"Messi retry was not idempotent: {retry}.")
    return retry


def _read_allocated_state():
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            state = _state(cur)
            _validate_state(state, allow_allocated=True)
        conn.rollback()
    return state


def verify_existing():
    """Resume only the post-commit idempotency and Shopify mirror checks."""
    before_retry = _read_allocated_state()
    retry = _retry_existing(before_retry)
    supabase_backend.sync_product_edition_metafields(TARGET["handle"])
    final = _read_allocated_state()
    return {
        "mode": "verified_existing",
        "target": TARGET,
        "before_retry": before_retry,
        "retry": retry,
        "final": final,
    }


def apply(snapshot_sha256):
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (TARGET["product_gid"],),
                )
                before_report = build_dry_run(cur)
                if before_report["snapshot_sha256"] != snapshot_sha256:
                    raise RuntimeError(
                        "Snapshot SHA does not match the current locked production state."
                    )
                before = _state(cur, lock=True)
                _validate_state(before, allow_allocated=False)
                allocation = _allocate_locked(cur, before)
                cur.execute(
                    """
                    UPDATE shopify_order_lines
                    SET assignment_status='Assigned', last_error='', updated_at=now()
                    WHERE shopify_order_id=%s
                      AND shopify_line_item_id=%s
                      AND EXISTS (
                          SELECT 1 FROM edition_orders eo
                          WHERE eo.allocation_valid
                            AND eo.source_channel='shopify'
                            AND eo.external_order_id=%s
                            AND eo.external_line_item_id=%s
                      )
                    """,
                    (
                        TARGET["order_id"], TARGET["line_item_id"],
                        TARGET["order_id"], TARGET["line_item_id"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        "Messi error clear did not update exactly one immutable line."
                    )
                after_locked = _state(cur)
                _validate_state(after_locked, allow_allocated=True)
                expected = int(before.get("next_edition_number") or 0)
                if int(allocation.get("edition_number") or 0) != expected:
                    raise RuntimeError(
                        f"Messi received {allocation.get('edition_number')}, expected locked next {expected}."
                    )
                if (
                    int(after_locked.get("sold_count") or 0),
                    int(after_locked.get("remaining_count") or 0),
                    int(after_locked.get("next_edition_number") or 0),
                ) != (
                    int(before.get("sold_count") or 0) + 1,
                    int(before.get("remaining_count") or 0) - 1,
                    expected + 1,
                ):
                    raise RuntimeError("Messi counters did not advance exactly once.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    retry = _retry_existing(before)
    supabase_backend.sync_product_edition_metafields(TARGET["handle"])
    final = _read_allocated_state()
    return {
        "mode": "applied",
        "target": TARGET,
        "before": before,
        "after_locked": after_locked,
        "final": final,
        "allocation": allocation,
        "retry": retry,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--snapshot-sha256", default="")
    args = parser.parse_args()
    if args.apply and args.verify_existing:
        parser.error("choose either --apply or --verify-existing")
    if args.apply and not args.snapshot_sha256:
        parser.error("--apply requires the exact --snapshot-sha256 from the dry run")
    if args.apply:
        result = apply(args.snapshot_sha256.strip())
    elif args.verify_existing:
        result = verify_existing()
    else:
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                result = build_dry_run(cur)
            conn.rollback()
    print(json.dumps(_json_value(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
