#!/usr/bin/env python3
"""Guarded repair for the four confirmed sold-out 2026-08-28 order lines.

Default mode is read-only. Applying requires the exact dry-run SHA-256 and an
active administrator email. All four inserts occur in one serializable
transaction and the database trigger independently repeats every eligibility
guard. No edition_orders row or edition counter is written by this script.
"""

import argparse
import hashlib
import json

import supabase_backend


EDITION_NUMBER = 100
EDITION_TOTAL = 100
REASON = (
    "Confirmed expired/sold-out order line purchased after edition 100; "
    "manual 100/100 Orders display and certificate value only."
)
TARGETS = (
    {
        "source_channel": "shopify",
        "order_name": "#SC3078",
        "order_id": "gid://shopify/Order/7379111280947",
        "line_item_id": "gid://shopify/LineItem/17486226522419",
        "product_gid": "gid://shopify/Product/9241140658483",
        "product_title": "Michael Jordans Last Shot Quote Wall Art",
    },
    {
        "source_channel": "shopify",
        "order_name": "#SC3075",
        "order_id": "gid://shopify/Order/7377596514611",
        "line_item_id": "gid://shopify/LineItem/17483709186355",
        "product_gid": "gid://shopify/Product/10048122552627",
        "product_title": "The Mentality Jordan vs Bryant Wall Art",
    },
    {
        "source_channel": "shopify",
        "order_name": "#SC3075",
        "order_id": "gid://shopify/Order/7377596514611",
        "line_item_id": "gid://shopify/LineItem/17483709153587",
        "product_gid": "gid://shopify/Product/8836822368563",
        "product_title": "Michael Jordan Six Rings Wall Art",
    },
    {
        "source_channel": "etsy",
        "order_name": "#SC3067",
        "order_id": "gid://shopify/Order/7376141025587",
        "line_item_id": "gid://shopify/LineItem/17481166717235",
        "product_gid": "gid://shopify/Product/10048122552627",
        "product_title": "The Mentality Jordan vs Bryant Wall Art",
    },
)


def _json_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _snapshot_sha256(report):
    payload = json.dumps(
        _json_value(report), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _actor(cur, email=""):
    clean_email = str(email or "").strip().casefold()
    params = []
    email_clause = ""
    if clean_email:
        email_clause = "AND LOWER(COALESCE(email, ''))=%s"
        params.append(clean_email)
    cur.execute(
        f"""
        SELECT id::text, email, display_name, username
        FROM os_users
        WHERE role='admin'
          AND is_active IS TRUE
          AND COALESCE(account_status, 'active') <> 'removed'
          {email_clause}
        ORDER BY created_at
        """,
        tuple(params),
    )
    rows = list(cur.fetchall() or [])
    if len(rows) != 1:
        raise RuntimeError(
            f"Expected exactly one matching active administrator, found {len(rows)}."
        )
    return dict(rows[0])


def _counter_snapshot(cur):
    product_gids = sorted({target["product_gid"] for target in TARGETS})
    cur.execute(
        """
        SELECT
            COALESCE(NULLIF(ep.shopify_product_gid, ''), NULLIF(ep.shopify_product_id, ''))
                AS product_gid,
            ep.product_title,
            ep.sold_count,
            ep.remaining_count,
            ep.next_edition_number,
            ep.last_assigned_edition,
            ep.sold_out,
            ep.is_sold_out,
            ep.active,
            ep.is_active,
            er.status AS run_status,
            er.next_edition_number AS run_next_edition_number
        FROM edition_products ep
        LEFT JOIN edition_runs er ON er.id=ep.active_edition_run_id
        WHERE COALESCE(NULLIF(ep.shopify_product_gid, ''), NULLIF(ep.shopify_product_id, ''))=ANY(%s)
        ORDER BY product_gid
        """,
        (product_gids,),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _ledger_counts(cur):
    line_ids = [
        supabase_backend.canonical_shopify_id(target["line_item_id"])
        for target in TARGETS
    ]
    cur.execute("SELECT COUNT(*) AS count FROM edition_orders")
    global_count = int((cur.fetchone() or {}).get("count") or 0)
    cur.execute(
        """
        SELECT COUNT(*) AS count
        FROM edition_orders
        WHERE REGEXP_REPLACE(
                COALESCE(external_line_item_id, ''),
                '^gid://shopify/LineItem/', ''
              )=ANY(%s)
           OR REGEXP_REPLACE(
                COALESCE(shopify_line_item_id, ''),
                '^gid://shopify/LineItem/', ''
              )=ANY(%s)
        """,
        (line_ids, line_ids),
    )
    target_count = int((cur.fetchone() or {}).get("count") or 0)
    return {"global": global_count, "targets": target_count}


def _non_target_allocations(cur):
    order_ids = sorted({target["order_id"] for target in TARGETS})
    target_line_ids = [
        supabase_backend.canonical_shopify_id(target["line_item_id"])
        for target in TARGETS
    ]
    cur.execute(
        """
        SELECT id::text, source_channel, external_order_id, external_line_item_id,
               shopify_order_id, shopify_line_item_id, product_title,
               edition_number, edition_total, allocation_valid
        FROM edition_orders
        WHERE (external_order_id=ANY(%s) OR shopify_order_id=ANY(%s))
          AND REGEXP_REPLACE(
                COALESCE(NULLIF(external_line_item_id, ''), shopify_line_item_id, ''),
                '^gid://shopify/LineItem/', ''
              ) <> ALL(%s)
        ORDER BY id
        """,
        (order_ids, order_ids, target_line_ids),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _manual_rows(cur):
    line_ids = [target["line_item_id"] for target in TARGETS]
    cur.execute(
        """
        SELECT id::text, source_channel, external_order_id, external_line_item_id,
               canonical_product_gid, edition_number, edition_total, reason,
               created_by_user_id::text, created_by_email,
               verified_order_name, verified_product_title,
               verified_assignment_status, verified_last_error,
               verified_series_status, verified_sold_count,
               verified_remaining_count, verified_next_edition_number,
               created_at, verified_at
        FROM manual_order_line_editions
        WHERE external_line_item_id=ANY(%s)
        ORDER BY external_order_id, external_line_item_id
        """,
        (line_ids,),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _target_report(cur, target):
    state = supabase_backend._manual_edition_state_with_cursor(
        cur,
        source_channel=target["source_channel"],
        external_order_id=target["order_id"],
        external_line_item_id=target["line_item_id"],
        expected_product_gid=target["product_gid"],
    )
    eligibility = supabase_backend._manual_edition_eligibility_from_state(state)
    return {
        **target,
        "stored_order_name": state.get("order_name") or target["order_name"],
        "stored_product_title": state.get("product_title") or target["product_title"],
        "assignment_status": state.get("assignment_status") or "",
        "last_error": state.get("last_error") or "",
        "valid_normal_allocation_count": int(
            state.get("valid_normal_allocation_count") or 0
        ),
        "existing_manual_id": str(state.get("manual_edition_id") or ""),
        "sold_count": int(state.get("sold_count") or 0),
        "remaining_count": int(state.get("remaining_count") or 0),
        "next_edition_number": int(state.get("next_edition_number") or 0),
        "series_status": state.get("series_status") or "",
        "eligible": bool(eligibility.get("eligible")),
        "eligibility_reason": eligibility.get("reason") or "",
    }


def _report(cur, admin_email=""):
    actor = _actor(cur, admin_email)
    targets = [_target_report(cur, target) for target in TARGETS]
    return {
        "actor": {
            "id": actor.get("id") or "",
            "email": actor.get("email") or "",
            "display_name": actor.get("display_name") or actor.get("username") or "",
        },
        "targets": targets,
        "counters": _counter_snapshot(cur),
        "edition_order_counts": _ledger_counts(cur),
        "non_target_allocations": _non_target_allocations(cur),
        "manual_rows": _manual_rows(cur),
    }


def _validate_before(report):
    if len(report.get("targets") or []) != len(TARGETS):
        raise RuntimeError("Target scope mismatch.")
    if report.get("manual_rows"):
        raise RuntimeError("One or more target lines already have a manual edition value.")
    for row in report["targets"]:
        if str(row.get("stored_order_name") or "") != row["order_name"]:
            raise RuntimeError(f"Order identity mismatch for {row['line_item_id']}.")
        if str(row.get("stored_product_title") or "").strip().casefold() != str(
            row["product_title"]
        ).strip().casefold():
            raise RuntimeError(f"Product title mismatch for {row['line_item_id']}.")
        if not row.get("eligible"):
            raise RuntimeError(
                f"Target is not eligible: {row['order_name']} {row['line_item_id']}: "
                f"{row.get('eligibility_reason') or 'unknown reason'}"
            )
        if (
            int(row.get("sold_count") or 0),
            int(row.get("remaining_count") or 0),
            int(row.get("next_edition_number") or 0),
        ) != (100, 0, 101):
            raise RuntimeError(
                f"Target series counters changed: {row['order_name']} {row['line_item_id']}."
            )


def _validate_after(before, after):
    rows = after.get("manual_rows") or []
    if len(rows) != len(TARGETS):
        raise RuntimeError(f"Expected four saved manual rows, found {len(rows)}.")
    if before.get("counters") != after.get("counters"):
        raise RuntimeError("Edition counters changed during the manual repair.")
    if before.get("edition_order_counts") != after.get("edition_order_counts"):
        raise RuntimeError("The normal edition allocation ledger changed during the manual repair.")
    if before.get("non_target_allocations") != after.get("non_target_allocations"):
        raise RuntimeError("A non-targeted allocation in the same orders changed during the repair.")
    expected = {(target["order_id"], target["line_item_id"]) for target in TARGETS}
    actual = {
        (str(row.get("external_order_id") or ""), str(row.get("external_line_item_id") or ""))
        for row in rows
    }
    if actual != expected:
        raise RuntimeError("Saved manual-row identities do not exactly match the four targets.")
    if any(
        (int(row.get("edition_number") or 0), int(row.get("edition_total") or 0))
        != (EDITION_NUMBER, EDITION_TOTAL)
        for row in rows
    ):
        raise RuntimeError("A saved manual row is not 100/100.")


def dry_run(admin_email=""):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            report = _report(cur, admin_email)
    _validate_before(report)
    return report


def apply(snapshot_sha256, admin_email):
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                for product_gid in sorted({target["product_gid"] for target in TARGETS}):
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (product_gid,),
                    )
                before = _report(cur, admin_email)
                _validate_before(before)
                actual_sha = _snapshot_sha256(before)
                if actual_sha != snapshot_sha256:
                    raise RuntimeError(
                        f"Dry-run snapshot changed: expected {snapshot_sha256}, actual {actual_sha}."
                    )
                actor_id = before["actor"]["id"]
                inserted = 0
                for target in TARGETS:
                    cur.execute(
                        """
                        INSERT INTO manual_order_line_editions (
                            source_channel, external_order_id, external_line_item_id,
                            canonical_product_gid, edition_number, edition_total, reason,
                            created_by_user_id, created_by_email, created_by_display_name,
                            verified_order_name, verified_product_title,
                            verified_assignment_status, verified_last_error,
                            verified_series_status, verified_sold_count,
                            verified_remaining_count, verified_next_edition_number
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            '', '', '', '', '', '', '', 0, 0, 0
                        )
                        RETURNING id
                        """,
                        (
                            target["source_channel"],
                            target["order_id"],
                            target["line_item_id"],
                            target["product_gid"],
                            EDITION_NUMBER,
                            EDITION_TOTAL,
                            REASON,
                            actor_id,
                        ),
                    )
                    if not (cur.fetchone() or {}).get("id"):
                        raise RuntimeError(
                            f"Insert did not return a row for {target['line_item_id']}."
                        )
                    inserted += 1
                if inserted != len(TARGETS):
                    raise RuntimeError(f"Expected four inserts, received {inserted}.")
                after = _report(cur, admin_email)
                _validate_after(before, after)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "mode": "applied",
        "rows_inserted": len(TARGETS),
        "before": before,
        "after": after,
        "post_commit_workflow": _workflow_verification(),
    }


def _workflow_verification():
    target_by_line = {target["line_item_id"]: target for target in TARGETS}
    display_rows = {}
    for order_name in sorted({target["order_name"] for target in TARGETS}):
        for row in supabase_backend.list_hybrid_order_rows(limit=100, search=order_name):
            line_id = str(row.get("shopify_line_item_id") or "")
            target = next(
                (
                    candidate
                    for candidate_id, candidate in target_by_line.items()
                    if supabase_backend.canonical_shopify_id(candidate_id)
                    == supabase_backend.canonical_shopify_id(line_id)
                ),
                None,
            )
            if not target:
                continue
            assignments = list(row.get("assignments") or [])
            manual = next(
                (
                    assignment
                    for assignment in assignments
                    if str(assignment.get("edition_order_id") or "").startswith(
                        supabase_backend.MANUAL_ORDER_LINE_EDITION_REFERENCE_PREFIX
                    )
                ),
                {},
            )
            display_rows[target["line_item_id"]] = {
                "order_name": row.get("order_name") or target["order_name"],
                "line_item_id": target["line_item_id"],
                "product_title": row.get("product_title") or target["product_title"],
                "edition_order_id": manual.get("edition_order_id") or "",
                "edition_number": int(manual.get("edition_number") or 0),
                "edition_total": int(manual.get("edition_total") or 0),
                "assignment_source": manual.get("assignment_source") or "",
            }

    expected_lines = set(target_by_line)
    if set(display_rows) != expected_lines:
        raise RuntimeError("Orders reader did not return every exact repaired line.")
    for line_id, row in display_rows.items():
        if (row["edition_number"], row["edition_total"]) != (
            EDITION_NUMBER,
            EDITION_TOTAL,
        ):
            raise RuntimeError(f"Orders reader did not display 100/100 for {line_id}.")

    certificate_inputs = []
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            for line_id in sorted(display_rows):
                reference = display_rows[line_id]["edition_order_id"]
                assignment = supabase_backend._manual_order_line_edition_assignment(
                    cur, reference
                )
                if (
                    int(assignment.get("edition_number") or 0),
                    int(assignment.get("edition_total") or 0),
                ) != (EDITION_NUMBER, EDITION_TOTAL):
                    raise RuntimeError(
                        f"Certificate input did not resolve 100/100 for {line_id}."
                    )
                certificate_inputs.append(
                    {
                        "line_item_id": line_id,
                        "edition_order_id": reference,
                        "edition_number": int(assignment.get("edition_number") or 0),
                        "edition_total": int(assignment.get("edition_total") or 0),
                        "product_title": assignment.get("product_title") or "",
                    }
                )
    return {
        "orders_display": [display_rows[line_id] for line_id in sorted(display_rows)],
        "certificate_inputs": certificate_inputs,
    }


def verify_existing(admin_email=""):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            report = _report(cur, admin_email)
    if len(report.get("manual_rows") or []) != len(TARGETS):
        raise RuntimeError("The four expected manual edition rows are not present.")
    if any(
        int(target.get("valid_normal_allocation_count") or 0)
        for target in report.get("targets") or []
    ):
        raise RuntimeError("A target now has a normal allocation; normal precedence must be reviewed.")
    return {
        "mode": "verified_existing",
        **report,
        "workflow": _workflow_verification(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--snapshot-sha256", default="")
    parser.add_argument("--admin-email", default="")
    args = parser.parse_args()
    if args.apply and args.verify_existing:
        parser.error("Choose --apply or --verify-existing, not both.")
    if args.apply:
        if not args.snapshot_sha256:
            parser.error("--apply requires --snapshot-sha256 from the current dry run.")
        if not args.admin_email:
            parser.error("--apply requires --admin-email for audit identity.")
        result = apply(args.snapshot_sha256, args.admin_email)
    elif args.verify_existing:
        result = verify_existing(args.admin_email)
    else:
        result = dry_run(args.admin_email)
        result = {
            "mode": "dry_run",
            "snapshot_sha256": _snapshot_sha256(result),
            **result,
        }
    print(json.dumps(_json_value(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
