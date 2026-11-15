"""Hash-bound, reversible Shane Warne active-sequence repair.

Dry-run is the default.  Apply requires the exact report SHA emitted by the dry
run and refuses to proceed when any paid/product/run/certificate ambiguity is
present.  Shopify is never mutated before the database transaction commits.

Examples:
    python scripts/repair_shane_warne_editions.py
    python scripts/repair_shane_warne_editions.py --apply --approved-report output/.../report.json --confirm <sha>
    python scripts/repair_shane_warne_editions.py --rollback-repair-key <key> --confirm <key>
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import edition_ledger  # noqa: E402
import incident_repair  # noqa: E402
import supabase_backend  # noqa: E402
from scripts import reconcile_edition_ledger  # noqa: E402


OUTPUT_ROOT = ROOT / "output" / "edition_ops_reconciliation"
ORDER_FIELDS = {
    "shopify_order_id", "order_name", "shopify_order_name", "financial_status",
    "fulfillment_status", "created_at", "processed_at", "cancelled_at", "source_name",
    "ingestion_status", "ingestion_method", "ingestion_result",
}
LINE_FIELDS = {
    "shopify_line_item_id", "shopify_order_id", "shopify_product_id",
    "shopify_variant_id", "shopify_handle", "product_title", "variant_title", "sku",
    "quantity", "assignment_status", "mapping_method", "last_error", "created_at", "updated_at",
}


def _only_fields(row, allowed):
    return {key: value for key, value in dict(row or {}).items() if key in allowed}


def _target_order_ids():
    return [row["order_gid"] for row in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE]


def _target_line_ids(*, include_michael=True):
    values = [row["line_gid"] for row in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE]
    if include_michael:
        values.append(incident_repair.MICHAEL_JORDAN_SC3056_LINE_GID)
    return values


def fetch_snapshot():
    snapshot = reconcile_edition_ledger._fetch_snapshot(incident_repair.SHANE_WARNE_PRODUCT_GID)
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_jsonb(so) AS row FROM shopify_orders so WHERE so.shopify_order_id=ANY(%s) ORDER BY so.created_at, so.shopify_order_id",
                (_target_order_ids(),),
            )
            snapshot["orders"] = [
                _only_fields(row.get("row") or {}, ORDER_FIELDS)
                for row in (cur.fetchall() or [])
            ]
            cur.execute(
                "SELECT to_jsonb(li) AS row FROM shopify_order_lines li WHERE li.shopify_line_item_id=ANY(%s) ORDER BY li.shopify_order_id, li.shopify_line_item_id",
                (_target_line_ids(),),
            )
            snapshot["order_lines"] = [
                _only_fields(row.get("row") or {}, LINE_FIELDS)
                for row in (cur.fetchall() or [])
            ]
            cur.execute(
                "SELECT to_jsonb(eo) AS row FROM edition_orders eo WHERE eo.shopify_line_item_id=%s ORDER BY eo.id",
                (incident_repair.MICHAEL_JORDAN_SC3056_LINE_GID,),
            )
            michael_rows = [
                reconcile_edition_ledger._only_fields(
                    row.get("row") or {},
                    reconcile_edition_ledger.ALLOCATION_SNAPSHOT_FIELDS,
                )
                for row in (cur.fetchall() or [])
            ]
    existing_ids = {str(row.get("id") or "") for row in snapshot.get("allocations") or []}
    snapshot["allocations"] = list(snapshot.get("allocations") or []) + [
        row for row in michael_rows if str(row.get("id") or "") not in existing_ids
    ]
    snapshot["michael_jordan_sc3056_fingerprint"] = incident_repair._sha256(michael_rows)
    return snapshot


def dry_run():
    snapshot = fetch_snapshot()
    report = incident_repair.build_shane_warne_authorised_plan(snapshot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = OUTPUT_ROOT / f"{stamp}-shane-warne-authorised"
    snapshot_path = directory / "snapshot.json"
    report_path = directory / "report.json"
    reconcile_edition_ledger._write_json(snapshot_path, snapshot)
    reconcile_edition_ledger._write_json(report_path, report)
    return snapshot_path, report_path, report


def _ensure_incident_archive(cur):
    reconcile_edition_ledger._ensure_repair_tables(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_incident_repair_archive (
            repair_key TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id TEXT NOT NULL,
            row_snapshot JSONB NOT NULL,
            archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (repair_key, table_name, row_id)
        )
        """
    )


def _archive_rows(cur, repair_key, table_name, id_expression, where_sql, params):
    cur.execute(
        f"""
        INSERT INTO edition_incident_repair_archive(repair_key, table_name, row_id, row_snapshot)
        SELECT %s, %s, ({id_expression})::text, to_jsonb(t)
        FROM {table_name} t
        WHERE {where_sql}
        ON CONFLICT (repair_key, table_name, row_id) DO NOTHING
        """,
        (repair_key, table_name, *params),
    )


def _assert_repair_prerequisites(cur):
    required_columns = (
        ("edition_orders", "source_channel"),
        ("edition_orders", "external_order_id"),
        ("edition_orders", "external_line_item_id"),
        ("edition_orders", "unit_ordinal"),
        ("edition_orders", "shopify_product_gid"),
        ("edition_orders", "allocation_valid"),
        ("edition_orders", "mirror_status"),
        ("edition_products", "shopify_product_gid"),
    )
    missing = []
    for table_name, column_name in required_columns:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s) AS present",
            (table_name, column_name),
        )
        if not bool((cur.fetchone() or {}).get("present")):
            missing.append(f"{table_name}.{column_name}")
    cur.execute("SELECT to_regprocedure('allocate_edition_line_units_atomic(text,text,text,text,integer,text,text,text,text,text,text,text,text,text,text)') AS function_name")
    function_exists = bool((cur.fetchone() or {}).get("function_name"))
    if missing or not function_exists:
        detail = ", ".join(missing) or "allocate_edition_line_units_atomic"
        raise RuntimeError(
            "The atomic ledger migration must be reviewed and installed before this repair. Missing: " + detail
        )


def _live_order_line(cur, target):
    cur.execute(
        """
        SELECT to_jsonb(so) AS order_row, to_jsonb(li) AS line_row
        FROM shopify_orders so
        JOIN shopify_order_lines li ON li.shopify_order_id=so.shopify_order_id
        WHERE so.shopify_order_id=%s AND li.shopify_line_item_id=%s
        FOR UPDATE OF so, li
        """,
        (target["order_gid"], target["line_gid"]),
    )
    row = cur.fetchone() or {}
    if not row:
        raise RuntimeError(f"{target['order_name']} exact order/line disappeared after dry-run.")
    order = dict(row.get("order_row") or {})
    line = dict(row.get("line_row") or {})
    if str(order.get("financial_status") or "").upper() != "PAID" or order.get("cancelled_at"):
        raise RuntimeError(f"{target['order_name']} is no longer an eligible paid order.")
    if int(line.get("quantity") or 0) != 1:
        raise RuntimeError(f"{target['order_name']} quantity changed after dry-run.")
    if edition_ledger.canonical_shopify_gid("Product", line.get("shopify_product_id")) != incident_repair.SHANE_WARNE_PRODUCT_GID:
        raise RuntimeError(f"{target['order_name']} product identity changed after dry-run.")
    return order, line


def _allocation_function_insert(cur, target, product, order, line):
    raw_order = order.get("raw_json") or order.get("raw") or {}
    if isinstance(raw_order, str):
        try:
            raw_order = json.loads(raw_order)
        except json.JSONDecodeError:
            raw_order = {}
    source_order = {**dict(raw_order or {}), **order, "shopify_order_id": target["order_gid"]}
    channel = edition_ledger.source_channel_for_order(source_order)
    cur.execute(
        """
        SELECT result->'allocation' AS allocation, (result->>'was_created')::boolean AS was_created
        FROM allocate_edition_line_units_atomic(
            %s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,'assigned'
        ) AS result
        """,
        (
            channel,
            target["order_gid"],
            target["line_gid"],
            incident_repair.SHANE_WARNE_PRODUCT_GID,
            target["order_gid"],
            target["order_name"],
            target["line_gid"],
            line.get("shopify_variant_id") or "",
            line.get("product_title") or product.get("product_title") or "Shane Warne Tribute Wall Art",
            line.get("variant_title") or "",
            line.get("sku") or "",
            order.get("customer_name") or "Customer not shown",
            order.get("customer_email") or order.get("email") or "",
        ),
    )
    result = cur.fetchone() or {}
    allocation = result.get("allocation") or {}
    if isinstance(allocation, str):
        allocation = json.loads(allocation)
    if int(allocation.get("edition_number") or 0) != target["edition_number"]:
        raise RuntimeError(
            f"Atomic allocator returned #{allocation.get('edition_number')} for {target['order_name']}; expected #{target['edition_number']:03d}."
        )
    return allocation, bool(result.get("was_created"))


def apply_report(report_path, confirmation, *, sync_shopify=False, regenerate_certificates=False):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if confirmation != report.get("report_sha256"):
        raise ValueError("--confirm must exactly match report_sha256 from the approved dry-run report.")
    if report.get("product_gid") != incident_repair.SHANE_WARNE_PRODUCT_GID:
        raise ValueError("Approved report is not scoped to the Shane Warne Shopify product GID.")
    if report.get("apply_blockers"):
        raise ValueError("Repair is blocked: " + "; ".join(report["apply_blockers"]))
    operations = [row for row in report.get("changes") or [] if row.get("operation") != "no_op"]
    if not operations:
        return {"applied": False, "already_consistent": True, "writes": 0}
    current_snapshot = fetch_snapshot()
    current_report = incident_repair.build_shane_warne_authorised_plan(current_snapshot)
    if current_report.get("snapshot_sha256") != report.get("snapshot_sha256"):
        raise RuntimeError("Production evidence changed after dry-run; create and approve a new report.")

    repair_key = f"shane-warne-authorised-{uuid.uuid4()}"
    target_lines = _target_line_ids(include_michael=False)
    changed_ids = []
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                _assert_repair_prerequisites(cur)
                _ensure_incident_archive(cur)
                cur.execute("SELECT set_config('sports_cave.edition_repair_key', %s, TRUE)", (repair_key,))
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                cur.execute(
                    """
                    SELECT ep.* FROM edition_products ep
                    WHERE COALESCE(NULLIF(ep.shopify_product_gid,''), NULLIF(ep.shopify_product_id,''))=%s
                    FOR UPDATE
                    """,
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                product_rows = list(cur.fetchall() or [])
                if len(product_rows) != 1:
                    raise RuntimeError("The Shane Warne product no longer resolves to exactly one Edition Ops row.")
                product = dict(product_rows[0])
                active_run_id = str(product.get("active_edition_run_id") or report.get("active_run_id") or "")
                cur.execute("SELECT * FROM edition_runs WHERE id::text=%s FOR UPDATE", (active_run_id,))
                run = cur.fetchone() or {}
                if not run:
                    raise RuntimeError("The approved active edition run no longer exists.")
                cur.execute(
                    "SELECT * FROM edition_orders WHERE shopify_product_gid=%s FOR UPDATE",
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                locked_allocations = list(cur.fetchall() or [])
                unexpected_valid = [
                    row for row in locked_allocations
                    if row.get("allocation_valid", True)
                    and str(row.get("shopify_line_item_id") or "") not in target_lines
                ]
                if unexpected_valid:
                    raise RuntimeError("A valid Shane Warne allocation outside the approved nine appeared after dry-run.")

                _archive_rows(cur, repair_key, "edition_products", "t.id", "t.id::text=%s", (str(product["id"]),))
                _archive_rows(cur, repair_key, "edition_runs", "t.id", "t.id::text=%s", (active_run_id,))
                _archive_rows(cur, repair_key, "shopify_order_lines", "t.shopify_line_item_id", "t.shopify_line_item_id=ANY(%s)", (target_lines,))
                _archive_rows(cur, repair_key, "edition_orders", "t.id", "t.shopify_line_item_id=ANY(%s)", (target_lines,))
                cur.execute(
                    "SELECT id::text AS id FROM edition_orders WHERE shopify_line_item_id=ANY(%s)",
                    (target_lines,),
                )
                preexisting_ids = [row["id"] for row in (cur.fetchall() or [])]
                if preexisting_ids:
                    _archive_rows(
                        cur,
                        repair_key,
                        "certificates",
                        "t.id",
                        "COALESCE(to_jsonb(t)->>'related_edition_order_id', to_jsonb(t)->>'edition_order_id')=ANY(%s)",
                        (preexisting_ids,),
                    )

                for target in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE:
                    order, line = _live_order_line(cur, target)
                    cur.execute(
                        "SELECT * FROM edition_orders WHERE shopify_line_item_id=%s ORDER BY id FOR UPDATE",
                        (target["line_gid"],),
                    )
                    existing = list(cur.fetchall() or [])
                    if len(existing) > 1:
                        raise RuntimeError(f"{target['order_name']} has duplicate allocation rows.")
                    if existing:
                        allocation_id = str(existing[0]["id"])
                        channel = edition_ledger.source_channel_for_order(
                            {**order, "shopify_order_id": target["order_gid"]}
                        )
                        cur.execute(
                            """
                            UPDATE edition_orders
                            SET source_channel=%s, external_order_id=%s, external_line_item_id=%s,
                                unit_ordinal=1, allocation_index=1,
                                allocation_key=%s, shopify_product_gid=%s, shopify_product_id=%s,
                                edition_run_id=%s, edition_number=%s, edition_total=100, quantity=1,
                                allocation_valid=TRUE, invalidated_at=NULL, invalidation_reason='',
                                certificate_status='Certificate Missing', status='assigned',
                                mirror_status='pending', mirror_error='', updated_at=now()
                            WHERE id::text=%s
                            """,
                            (
                                channel, target["order_gid"], target["line_gid"],
                                f"{channel}:{target['order_gid']}:{target['line_gid']}:1",
                                incident_repair.SHANE_WARNE_PRODUCT_GID,
                                incident_repair.SHANE_WARNE_PRODUCT_GID,
                                active_run_id, target["edition_number"], allocation_id,
                            ),
                        )
                    else:
                        allocation, _ = _allocation_function_insert(cur, target, product, order, line)
                        allocation_id = str(allocation.get("id") or "")
                    changed_ids.append(allocation_id)
                    cur.execute(
                        """
                        UPDATE shopify_order_lines
                        SET assignment_status='Assigned', last_error='',
                            mapping_method=CASE WHEN COALESCE(mapping_method,'')='' THEN 'authorized_gid_repair' ELSE mapping_method END,
                            updated_at=now()
                        WHERE shopify_line_item_id=%s
                        """,
                        (target["line_gid"],),
                    )
                    cur.execute(
                        """
                        UPDATE certificates
                        SET edition_number=%s, edition_total=100,
                            certificate_status='Certificate Missing', updated_at=now()
                        WHERE COALESCE(to_jsonb(certificates)->>'related_edition_order_id', to_jsonb(certificates)->>'edition_order_id')=%s
                        """,
                        (target["edition_number"], allocation_id),
                    )

                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=10, last_assigned_edition=9, sold_count=9,
                        remaining_count=91, sold_out=FALSE, is_sold_out=FALSE, updated_at=now()
                    WHERE id=%s
                    """,
                    (product["id"],),
                )
                cur.execute(
                    "UPDATE edition_runs SET next_edition_number=10, status='active', updated_at=now() WHERE id::text=%s",
                    (active_run_id,),
                )
                cur.execute(
                    """
                    SELECT COUNT(*) AS sold, COUNT(DISTINCT edition_number) AS distinct_sold,
                           MIN(edition_number) AS first_number, MAX(edition_number) AS last_number
                    FROM edition_orders
                    WHERE shopify_product_gid=%s AND allocation_valid
                    """,
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                state = cur.fetchone() or {}
                if (state.get("sold"), state.get("distinct_sold"), state.get("first_number"), state.get("last_number")) != (9, 9, 1, 9):
                    raise RuntimeError("Post-repair ledger assertion failed; transaction rolled back.")
                cur.execute(
                    """
                    INSERT INTO edition_repair_audits(repair_key, product_gid, mode, snapshot_sha256, report, applied_at)
                    VALUES (%s,%s,'apply',%s,%s::jsonb,now())
                    """,
                    (
                        repair_key,
                        incident_repair.SHANE_WARNE_PRODUCT_GID,
                        report["snapshot_sha256"],
                        reconcile_edition_ledger._canonical_json({**report, "changed_edition_order_ids": changed_ids}),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    post_commit = {"shopify_mirror": "pending", "certificates": "pending", "errors": []}
    if regenerate_certificates:
        certificate_results = []
        for edition_order_id in changed_ids:
            try:
                certificate_results.append(
                    supabase_backend.generate_certificate_for_edition_order(
                        edition_order_id,
                        force=True,
                        source_page="Authorized Shane Warne repair",
                    )
                )
            except Exception as error:
                post_commit["errors"].append(
                    {"stage": "certificate_regeneration", "edition_order_id": edition_order_id, "error": str(error)}
                )
        post_commit["certificates"] = {"regenerated": len(certificate_results)}
    if sync_shopify:
        try:
            post_commit["shopify_mirror"] = supabase_backend.sync_product_edition_metafields(
                "shane-warne-framed-art",
                ensure_schema_first=False,
            )
        except Exception as error:
            post_commit["shopify_mirror"] = "failed_retryable"
            post_commit["errors"].append({"stage": "shopify_product_metafield_mirror", "error": str(error)})
    return {
        "applied": True,
        "repair_key": repair_key,
        "changed_edition_order_ids": changed_ids,
        "database_state": report["authoritative_active_state"],
        "post_commit": post_commit,
    }


def rollback(repair_key, confirmation):
    if confirmation != repair_key:
        raise ValueError("Rollback --confirm must exactly match --rollback-repair-key.")
    target_lines = _target_line_ids(include_michael=False)
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                _ensure_incident_archive(cur)
                cur.execute(
                    "SELECT report, rolled_back_at FROM edition_repair_audits WHERE repair_key=%s FOR UPDATE",
                    (repair_key,),
                )
                audit = cur.fetchone() or {}
                if not audit:
                    raise ValueError("Unknown repair key.")
                if audit.get("rolled_back_at"):
                    return {"rolled_back": False, "already_rolled_back": True, "repair_key": repair_key}
                cur.execute("SELECT set_config('sports_cave.edition_repair_key', %s, TRUE)", (repair_key,))
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                cur.execute(
                    "SELECT id FROM edition_orders WHERE shopify_product_gid=%s FOR UPDATE",
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                cur.fetchall()
                cur.execute(
                    "SELECT COUNT(*) AS sold, COALESCE(MAX(edition_number),0) AS highest FROM edition_orders WHERE shopify_product_gid=%s AND allocation_valid",
                    (incident_repair.SHANE_WARNE_PRODUCT_GID,),
                )
                current = cur.fetchone() or {}
                if (current.get("sold"), current.get("highest")) != (9, 9):
                    raise RuntimeError("Later allocation activity exists; rollback is blocked.")
                stored_report = audit.get("report") or {}
                if isinstance(stored_report, str):
                    stored_report = json.loads(stored_report)
                changed_ids = [str(value) for value in stored_report.get("changed_edition_order_ids") or [] if value]
                if changed_ids:
                    cur.execute(
                        "DELETE FROM certificates WHERE COALESCE(to_jsonb(certificates)->>'related_edition_order_id', to_jsonb(certificates)->>'edition_order_id')=ANY(%s)",
                        (changed_ids,),
                    )
                cur.execute("DELETE FROM edition_orders WHERE shopify_line_item_id=ANY(%s)", (target_lines,))
                cur.execute(
                    """
                    INSERT INTO edition_orders
                    SELECT (jsonb_populate_record(NULL::edition_orders, row_snapshot)).*
                    FROM edition_incident_repair_archive
                    WHERE repair_key=%s AND table_name='edition_orders'
                    """,
                    (repair_key,),
                )
                cur.execute(
                    """
                    INSERT INTO certificates
                    SELECT (jsonb_populate_record(NULL::certificates, row_snapshot)).*
                    FROM edition_incident_repair_archive
                    WHERE repair_key=%s AND table_name='certificates'
                    """,
                    (repair_key,),
                )
                cur.execute(
                    """
                    UPDATE edition_products ep
                    SET next_edition_number=(a.row_snapshot->>'next_edition_number')::integer,
                        last_assigned_edition=(a.row_snapshot->>'last_assigned_edition')::integer,
                        sold_count=(a.row_snapshot->>'sold_count')::integer,
                        remaining_count=(a.row_snapshot->>'remaining_count')::integer,
                        sold_out=COALESCE((a.row_snapshot->>'sold_out')::boolean,FALSE),
                        is_sold_out=COALESCE((a.row_snapshot->>'is_sold_out')::boolean,FALSE), updated_at=now()
                    FROM edition_incident_repair_archive a
                    WHERE a.repair_key=%s AND a.table_name='edition_products' AND ep.id::text=a.row_id
                    """,
                    (repair_key,),
                )
                cur.execute(
                    """
                    UPDATE edition_runs er
                    SET next_edition_number=(a.row_snapshot->>'next_edition_number')::integer,
                        status=a.row_snapshot->>'status', updated_at=now()
                    FROM edition_incident_repair_archive a
                    WHERE a.repair_key=%s AND a.table_name='edition_runs' AND er.id::text=a.row_id
                    """,
                    (repair_key,),
                )
                cur.execute(
                    """
                    UPDATE shopify_order_lines li
                    SET assignment_status=a.row_snapshot->>'assignment_status',
                        last_error=COALESCE(a.row_snapshot->>'last_error',''),
                        mapping_method=COALESCE(a.row_snapshot->>'mapping_method',''), updated_at=now()
                    FROM edition_incident_repair_archive a
                    WHERE a.repair_key=%s AND a.table_name='shopify_order_lines'
                      AND li.shopify_line_item_id=a.row_id
                    """,
                    (repair_key,),
                )
                cur.execute("UPDATE edition_repair_audits SET rolled_back_at=now() WHERE repair_key=%s", (repair_key,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rolled_back": True, "repair_key": repair_key, "shopify_mirror_required": True}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-report")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--sync-shopify", action="store_true")
    parser.add_argument("--regenerate-certificates", action="store_true")
    parser.add_argument("--rollback-repair-key")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.rollback_repair_key:
        print(json.dumps(rollback(args.rollback_repair_key, args.confirm), indent=2, default=str))
        return 0
    if args.apply:
        if not args.approved_report:
            raise SystemExit("--apply requires --approved-report and --confirm.")
        result = apply_report(
            args.approved_report,
            args.confirm,
            sync_shopify=bool(args.sync_shopify),
            regenerate_certificates=bool(args.regenerate_certificates),
        )
        print(json.dumps(result, indent=2, default=str))
        return 0
    snapshot_path, report_path, report = dry_run()
    print(json.dumps({
        "mode": "dry_run",
        "snapshot": str(snapshot_path),
        "report": str(report_path),
        "report_sha256": report["report_sha256"],
        "apply_blockers": report["apply_blockers"],
        "proposed_changes": report["changes"],
    }, indent=2, default=str))
    return 2 if report["apply_blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
