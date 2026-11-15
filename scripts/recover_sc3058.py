"""Evidence-bound recovery for the exact Shopify/eBay order #SC3058.

Dry-run is the default and writes a private Shopify payload snapshot plus a
PII-safe, hash-bound report.  Apply rechecks both Shopify and the product ledgers,
then invokes the normal targeted Shopify reconciliation pipeline.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import incident_repair  # noqa: E402
import shopify_sync  # noqa: E402
import supabase_backend  # noqa: E402


OUTPUT_ROOT = ROOT / "output" / "edition_ops_reconciliation"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def fetch_exact_order(config=None):
    orders = shopify_sync.fetch_orders_by_ids([incident_repair.SC3058_ORDER_GID], config=config)
    order = dict((orders or [{}])[0] or {})
    if not order:
        raise RuntimeError("Shopify did not return the immutable #SC3058 order GID.")
    return order


def _product_state(cur, product_gid):
    cur.execute(
        """
        SELECT to_jsonb(ep) AS row
        FROM edition_products ep
        WHERE CASE
                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_gid','') ~ '^gid://shopify/Product/[0-9]+$'
                      THEN to_jsonb(ep)->>'shopify_product_gid'
                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id','') ~ '^gid://shopify/Product/[0-9]+$'
                      THEN to_jsonb(ep)->>'shopify_product_id'
                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id','') ~ '^[0-9]+$'
                      THEN 'gid://shopify/Product/' || (to_jsonb(ep)->>'shopify_product_id')
                  ELSE NULL
              END=%s
        ORDER BY ep.updated_at DESC NULLS LAST
        """,
        (product_gid,),
    )
    products = [dict(row.get("row") or {}) for row in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT edition_number
        FROM edition_orders eo
        WHERE CASE
                  WHEN COALESCE(to_jsonb(eo)->>'shopify_product_gid','') ~ '^gid://shopify/Product/[0-9]+$'
                      THEN to_jsonb(eo)->>'shopify_product_gid'
                  WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id','') ~ '^gid://shopify/Product/[0-9]+$'
                      THEN to_jsonb(eo)->>'shopify_product_id'
                  WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id','') ~ '^[0-9]+$'
                      THEN 'gid://shopify/Product/' || (to_jsonb(eo)->>'shopify_product_id')
                  ELSE NULL
              END=%s
          AND COALESCE((to_jsonb(eo)->>'allocation_valid')::boolean, TRUE)
        ORDER BY edition_number
        """,
        (product_gid,),
    )
    numbers = [int(row.get("edition_number") or 0) for row in (cur.fetchall() or [])]
    product = products[0] if len(products) == 1 else {}
    return {
        "product_row_count": len(products),
        "edition_total": int(product.get("edition_total") or 100) if product else 100,
        "valid_numbers": numbers,
        "valid_count": len(numbers),
        "highest_valid": max(numbers, default=0),
        "next_from_ledger": max(numbers, default=0) + 1,
        "product_counter_next": product.get("next_edition_number"),
        "product_counter_sold": product.get("sold_count"),
        "product_counter_remaining": product.get("remaining_count"),
    }


def fetch_product_states():
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            return {
                "muhammad_ali": _product_state(cur, incident_repair.MUHAMMAD_ALI_PRODUCT_GID),
                "shane_warne": _product_state(cur, incident_repair.SHANE_WARNE_PRODUCT_GID),
            }


def build_dry_run(config=None):
    order = fetch_exact_order(config=config)
    safe_preview = supabase_backend.reconcile_single_shopify_order(
        shopify_order_id=incident_repair.SC3058_ORDER_GID,
        apply=False,
        config=config,
        ensure_schema_first=False,
    )
    states = fetch_product_states()
    report = incident_repair.build_sc3058_recovery_plan(
        order,
        states,
        mapping=safe_preview.get("mapping") or [],
        trace=safe_preview.get("trace_before") or {},
    )
    report["shopify_payload_sha256"] = incident_repair._sha256(order)
    report["database_state_sha256"] = incident_repair._sha256(states)
    report["safe_pipeline_preview"] = safe_preview
    report.pop("report_sha256", None)
    report["report_sha256"] = incident_repair._sha256(report)
    return order, states, report


def dry_run(config=None):
    order, _states, report = build_dry_run(config=config)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = OUTPUT_ROOT / f"{stamp}-sc3058-ebay-recovery"
    private_path = directory / "shopify_payload.private.json"
    report_path = directory / "report.json"
    _write_json(private_path, order)
    _write_json(report_path, report)
    return private_path, report_path, report


def _allocation_rows_for_sc3058():
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id, shopify_product_gid, edition_number, edition_total,
                       shopify_line_item_id,
                       COALESCE((to_jsonb(edition_orders)->>'allocation_valid')::boolean, TRUE) AS allocation_valid
                FROM edition_orders
                WHERE shopify_order_id=%s AND shopify_line_item_id=%s
                ORDER BY edition_number, id
                """,
                (incident_repair.SC3058_ORDER_GID, incident_repair.SC3058_LINE_GID),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def apply_report(report_path, confirmation, *, generate_certificate=False, config=None):
    approved = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if confirmation != approved.get("report_sha256"):
        raise ValueError("--confirm must exactly match report_sha256 from the approved #SC3058 dry-run.")
    if approved.get("shopify_order_id") != incident_repair.SC3058_ORDER_GID:
        raise ValueError("The approved report is not scoped to #SC3058.")
    if approved.get("apply_blockers"):
        raise ValueError("#SC3058 recovery is blocked: " + "; ".join(approved["apply_blockers"]))

    order = fetch_exact_order(config=config)
    states_before = fetch_product_states()
    if incident_repair._sha256(order) != approved.get("shopify_payload_sha256"):
        raise RuntimeError("The Shopify #SC3058 payload changed after dry-run; create and approve a new report.")
    if incident_repair._sha256(states_before) != approved.get("database_state_sha256"):
        raise RuntimeError("Muhammad Ali or Shane Warne ledger state changed after dry-run; create and approve a new report.")

    result = supabase_backend.reconcile_single_shopify_order(
        shopify_order_id=incident_repair.SC3058_ORDER_GID,
        apply=True,
        notify=True,
        config=config,
        ensure_schema_first=False,
    )
    if not result.get("applied") or result.get("errors"):
        raise RuntimeError("#SC3058 normal-pipeline ingestion did not complete cleanly: " + "; ".join(result.get("errors") or []))

    allocations = _allocation_rows_for_sc3058()
    if len(allocations) != 1:
        raise RuntimeError(f"#SC3058 has {len(allocations)} allocation rows after recovery; expected exactly one.")
    allocation = allocations[0]
    if allocation.get("shopify_product_gid") != incident_repair.MUHAMMAD_ALI_PRODUCT_GID:
        raise RuntimeError("#SC3058 was allocated to a non-Muhammad-Ali product; manual rollback is required.")
    expected = int(approved.get("expected_edition_number") or 0)
    if int(allocation.get("edition_number") or 0) != expected:
        raise RuntimeError(f"#SC3058 received edition {allocation.get('edition_number')}; approved next edition was {expected}.")

    certificate_result = {"requested": False, "status": "normal_fulfilment_workflow"}
    if generate_certificate:
        try:
            generated = supabase_backend.generate_certificate_for_edition_order(
                allocation["id"],
                force=False,
                source_page="Authorized #SC3058 recovery",
            )
            certificate_result = {"requested": True, "status": "generated", "result": generated}
        except Exception as error:
            certificate_result = {"requested": True, "status": "failed_retryable", "error": str(error)}

    states_after = fetch_product_states()
    if states_after.get("shane_warne") != states_before.get("shane_warne"):
        raise RuntimeError("Shane Warne state changed during #SC3058 recovery; investigate immediately.")
    expected_ali_numbers = list(states_before["muhammad_ali"].get("valid_numbers") or [])
    if not approved.get("already_allocated"):
        expected_ali_numbers.append(expected)
    if states_after["muhammad_ali"].get("valid_numbers") != expected_ali_numbers:
        raise RuntimeError("Muhammad Ali ledger readback does not match the single approved allocation.")

    trace_after = supabase_backend.get_shopify_order_ingestion_trace(
        incident_repair.SC3058_ORDER_GID,
        order_name=incident_repair.SC3058_ORDER_NAME,
        ensure_schema_first=False,
    )
    return {
        "applied": True,
        "shopify_order_id": incident_repair.SC3058_ORDER_GID,
        "order_name": incident_repair.SC3058_ORDER_NAME,
        "source_channel": "ebay",
        "edition_order_id": allocation["id"],
        "muhammad_ali_edition_number": allocation["edition_number"],
        "new_order_notification_events_created": result.get("new_order_notification_events_created", 0),
        "certificate": certificate_result,
        "trace_after": trace_after,
        "shane_warne_unchanged": True,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-report")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--generate-certificate", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.apply:
        if not args.approved_report:
            raise SystemExit("--apply requires --approved-report and --confirm.")
        result = apply_report(
            args.approved_report,
            args.confirm,
            generate_certificate=bool(args.generate_certificate),
        )
        print(json.dumps(result, indent=2, default=str))
        return 0
    private_path, report_path, report = dry_run()
    print(json.dumps({
        "mode": "dry_run",
        "private_shopify_payload_snapshot": str(private_path),
        "report": str(report_path),
        "report_sha256": report["report_sha256"],
        "expected_muhammad_ali_edition_number": report["expected_edition_number"],
        "apply_blockers": report["apply_blockers"],
    }, indent=2, default=str))
    return 2 if report["apply_blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

