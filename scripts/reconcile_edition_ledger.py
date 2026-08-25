"""Read-only-by-default Edition Ops reconciliation and reversible repair.

Examples:
    python scripts/reconcile_edition_ledger.py --product-gid gid://shopify/Product/8116473790771
    python scripts/reconcile_edition_ledger.py --apply --approved-report output/.../report.json
    python scripts/reconcile_edition_ledger.py --rollback-repair-key <repair-key>

The apply and rollback modes require an exact report hash confirmation.  This
script never calls a Shopify mutation.  It emits the metafield values that must
be mirrored only after the database transaction succeeds.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import edition_ledger  # noqa: E402
import supabase_backend  # noqa: E402


OUTPUT_ROOT = ROOT / "output" / "edition_ops_reconciliation"
CUSTOMER_FACING_CERTIFICATE_STATUSES = {
    "certificate ready",
    "ready",
    "generated",
    "uploaded",
}

ALLOCATION_SNAPSHOT_FIELDS = {
    "id", "source_channel", "external_order_id", "external_line_item_id", "unit_ordinal",
    "allocation_key", "shopify_order_id", "shopify_order_name", "shopify_line_item_id",
    "shopify_product_gid", "shopify_product_id", "shopify_variant_id", "shopify_handle",
    "product_handle", "product_title", "edition_run_id", "edition_number", "edition_total",
    "allocation_index", "quantity", "assigned_at", "certificate_status", "certificate_id",
    "shopify_file_id", "shopify_file_status", "certificate_file_url", "status", "source",
    "allocation_valid", "invalidated_at", "invalidation_reason", "mirror_status",
    "mirror_attempted_at", "mirror_error", "created_at", "updated_at",
}


def _only_fields(payload, allowed):
    return {key: value for key, value in dict(payload or {}).items() if key in allowed}


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha256(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _ledger_fingerprint(snapshot):
    return _sha256(
        {
            key: snapshot.get(key) or []
            for key in (
                "edition_products",
                "edition_runs",
                "allocations",
                "unresolved_identity_allocations",
                "certificates",
                "marketplace_mappings",
            )
        }
    )


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _merge_certificate_evidence(allocations, certificates):
    certificate_statuses_by_allocation = defaultdict(list)
    for certificate in certificates or []:
        related_id = str(
            certificate.get("related_edition_order_id")
            or certificate.get("edition_order_id")
            or ""
        )
        if related_id:
            certificate_statuses_by_allocation[related_id].append(
                str(
                    certificate.get("certificate_status")
                    or certificate.get("status")
                    or certificate.get("shopify_file_status")
                    or ""
                ).strip()
            )
    for allocation in allocations or []:
        statuses = [
            status
            for status in certificate_statuses_by_allocation.get(
                str(allocation.get("id") or ""),
                [],
            )
            if status
        ]
        if statuses:
            allocation["certificate_status"] = statuses[-1]
    return allocations


def _fetch_snapshot(product_gid):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT to_jsonb(ep) AS row
                FROM edition_products ep
                WHERE CASE
                    WHEN COALESCE(to_jsonb(ep)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                        THEN to_jsonb(ep)->>'shopify_product_gid'
                    WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                        THEN to_jsonb(ep)->>'shopify_product_id'
                    WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^[0-9]+$'
                        THEN 'gid://shopify/Product/' || (to_jsonb(ep)->>'shopify_product_id')
                    ELSE NULL
                END=%s
                ORDER BY ep.updated_at DESC NULLS LAST
                """,
                (product_gid,),
            )
            products = [dict(row.get("row") or {}) for row in cur.fetchall()]
            product_handles = [str(row.get("shopify_handle") or "") for row in products]
            cur.execute(
                """
                SELECT to_jsonb(er) AS row
                FROM edition_runs er
                WHERE er.shopify_product_id=%s
                   OR er.edition_product_id IN (
                       SELECT ep.id FROM edition_products ep
                       WHERE CASE
                           WHEN COALESCE(to_jsonb(ep)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                               THEN to_jsonb(ep)->>'shopify_product_gid'
                           WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                               THEN to_jsonb(ep)->>'shopify_product_id'
                           WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^[0-9]+$'
                               THEN 'gid://shopify/Product/' || (to_jsonb(ep)->>'shopify_product_id')
                           ELSE NULL
                       END=%s
                   )
                ORDER BY er.created_at, er.id
                """,
                (product_gid, product_gid),
            )
            runs = [dict(row.get("row") or {}) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT to_jsonb(eo) AS allocation_row,
                       to_jsonb(so) AS order_row,
                       to_jsonb(li) AS line_row
                FROM edition_orders eo
                LEFT JOIN shopify_orders so ON so.shopify_order_id=eo.shopify_order_id
                LEFT JOIN shopify_order_lines li ON li.shopify_line_item_id=eo.shopify_line_item_id
                WHERE CASE
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                              THEN to_jsonb(eo)->>'shopify_product_gid'
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                              THEN to_jsonb(eo)->>'shopify_product_id'
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id', '') ~ '^[0-9]+$'
                              THEN 'gid://shopify/Product/' || (to_jsonb(eo)->>'shopify_product_id')
                          ELSE NULL
                      END=%s
                   OR eo.edition_run_id IN (
                       SELECT er.id
                       FROM edition_runs er
                       WHERE er.edition_product_id IN (
                           SELECT ep.id FROM edition_products ep
                           WHERE CASE
                               WHEN COALESCE(to_jsonb(ep)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                                   THEN to_jsonb(ep)->>'shopify_product_gid'
                               WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                                   THEN to_jsonb(ep)->>'shopify_product_id'
                               WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^[0-9]+$'
                                   THEN 'gid://shopify/Product/' || (to_jsonb(ep)->>'shopify_product_id')
                               ELSE NULL
                           END=%s
                       )
                   )
                ORDER BY eo.edition_number, eo.assigned_at, eo.id
                """,
                (product_gid, product_gid),
            )
            allocations = []
            for result in cur.fetchall():
                allocation = _only_fields(result.get("allocation_row") or {}, ALLOCATION_SNAPSHOT_FIELDS)
                order = dict(result.get("order_row") or {})
                line = dict(result.get("line_row") or {})
                allocation.update(
                    {
                        "id": str(allocation.get("id") or ""),
                        "source_channel": allocation.get("source_channel") or edition_ledger.source_channel_for_order(order),
                        "external_order_id": allocation.get("external_order_id") or edition_ledger.external_order_id_for_order(order),
                        "external_line_item_id": allocation.get("external_line_item_id") or edition_ledger.external_line_item_id_for_line(order, line),
                        "unit_ordinal": allocation.get("unit_ordinal") or allocation.get("allocation_index") or 1,
                        "shopify_product_gid": allocation.get("shopify_product_gid") or allocation.get("shopify_product_id") or product_gid,
                        "allocation_valid": allocation.get("allocation_valid", True),
                        "source_name": order.get("source_name") or "",
                        "financial_status": order.get("financial_status") or "",
                        "fulfillment_status": order.get("fulfillment_status") or "",
                        "cancelled_at": order.get("cancelled_at"),
                        "test": order.get("test", False),
                        "processed_at": order.get("processed_at"),
                        "order_created_at": order.get("created_at"),
                        "line_quantity": line.get("quantity"),
                        "mapping_method": line.get("mapping_method") or "",
                        "mapping_identities": edition_ledger.marketplace_mapping_identity_candidates(line),
                    }
                )
                allocations.append(allocation)
            cur.execute(
                """
                SELECT to_jsonb(eo) AS row
                FROM edition_orders eo
                WHERE eo.shopify_handle = ANY(%s)
                  AND NOT (
                      CASE
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                              THEN to_jsonb(eo)->>'shopify_product_gid'
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                              THEN to_jsonb(eo)->>'shopify_product_id'
                          WHEN COALESCE(to_jsonb(eo)->>'shopify_product_id', '') ~ '^[0-9]+$'
                              THEN 'gid://shopify/Product/' || (to_jsonb(eo)->>'shopify_product_id')
                          ELSE NULL
                      END IS NOT DISTINCT FROM %s
                      OR eo.edition_run_id IN (
                          SELECT er.id
                          FROM edition_runs er
                          WHERE er.edition_product_id IN (
                              SELECT ep.id FROM edition_products ep
                              WHERE CASE
                                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                                      THEN to_jsonb(ep)->>'shopify_product_gid'
                                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                                      THEN to_jsonb(ep)->>'shopify_product_id'
                                  WHEN COALESCE(to_jsonb(ep)->>'shopify_product_id', '') ~ '^[0-9]+$'
                                      THEN 'gid://shopify/Product/' || (to_jsonb(ep)->>'shopify_product_id')
                                  ELSE NULL
                              END=%s
                          )
                      )
                  )
                ORDER BY eo.assigned_at, eo.id
                """,
                (
                    product_handles,
                    product_gid,
                    product_gid,
                ),
            )
            unresolved_identity_allocations = [
                {
                    **_only_fields(row.get("row") or {}, ALLOCATION_SNAPSHOT_FIELDS),
                    "identity_warning": (
                        "Handle-only candidate was not attached to this product; canonical Shopify product GID mapping is required."
                    ),
                }
                for row in cur.fetchall()
            ]
            cur.execute("SELECT to_regclass('public.edition_marketplace_mappings') AS table_name")
            mapping_table_exists = bool((cur.fetchone() or {}).get("table_name"))
            mappings = []
            if mapping_table_exists:
                cur.execute(
                    """
                    SELECT source_channel, identity_type, external_identity,
                           shopify_product_gid, active, created_at, updated_at
                    FROM edition_marketplace_mappings
                    WHERE shopify_product_gid=%s
                    ORDER BY source_channel, identity_type, external_identity
                    """,
                    (product_gid,),
                )
                mappings = [dict(row) for row in cur.fetchall()]
            allocation_ids = [str(row.get("id") or "") for row in allocations if row.get("id")]
            certificates = []
            if allocation_ids:
                cur.execute(
                    """
                    SELECT to_jsonb(c) AS row
                    FROM certificates c
                    WHERE COALESCE(
                        to_jsonb(c)->>'related_edition_order_id',
                        to_jsonb(c)->>'edition_order_id'
                    ) = ANY(%s)
                    ORDER BY c.updated_at, c.id
                    """,
                    (allocation_ids,),
                )
                certificate_fields = {
                    "id", "edition_order_id", "related_edition_order_id", "shopify_order_id",
                    "shopify_order_name", "shopify_line_item_id", "shopify_product_id",
                    "shopify_handle", "product_handle", "product_title", "certificate_id",
                    "edition_number", "edition_total", "line_item_unit_index", "pdf_filename",
                    "local_file_path", "shopify_file_id", "shopify_file_status",
                    "shopify_file_url", "certificate_file_url", "certificate_pdf_url",
                    "certificate_print_jpg_url", "certificate_preview_image_url",
                    "certificate_r2_bucket", "certificate_r2_key", "certificate_status",
                    "asset_sync_status", "asset_sync_error", "sync_status", "last_sync_error",
                    "generated_at", "status", "created_at", "updated_at",
                }
                certificates = [
                    _only_fields(row.get("row") or {}, certificate_fields)
                    for row in cur.fetchall()
                ]
                _merge_certificate_evidence(allocations, certificates)
            cur.execute(
                "SELECT value FROM app_settings WHERE key=%s",
                (supabase_backend.EDITION_TRACKING_START_KEY,),
            )
            tracking_row = cur.fetchone() or {}
    shopify_snapshot = {"metafields": [], "error": ""}
    try:
        shopify_snapshot = supabase_backend._fetch_public_edition_metafields(product_gid)
    except Exception as error:
        shopify_snapshot = {"metafields": [], "error": str(error)}
    return {
        "schema_version": 1,
        "product_gid": product_gid,
        "captured_at": datetime.now(timezone.utc),
        "edition_products": products,
        "edition_runs": runs,
        "allocations": allocations,
        "unresolved_identity_allocations": unresolved_identity_allocations,
        "certificates": certificates,
        "marketplace_mappings": mappings,
        "shopify_edition_metafields": shopify_snapshot.get("metafields") or [],
        "shopify_metafield_read_error": shopify_snapshot.get("error") or "",
        "edition_tracking_start_at": tracking_row.get("value") or "",
    }


def _allocation_source_key(row):
    return (
        str(row.get("source_channel") or "shopify").casefold(),
        str(row.get("external_order_id") or row.get("shopify_order_id") or ""),
        str(row.get("external_line_item_id") or row.get("shopify_line_item_id") or ""),
        int(row.get("unit_ordinal") or row.get("allocation_index") or 1),
    )


def _marketplace_mapping_exists(snapshot, row):
    channel = str(row.get("source_channel") or "").casefold()
    if channel not in edition_ledger.MARKETPLACE_SOURCE_CHANNELS:
        return True
    identities = {
        (str(identity_type), str(external_identity))
        for identity_type, external_identity in (row.get("mapping_identities") or [])
    }
    return bool(identities) and any(
        mapping.get("source_channel") == channel
        and mapping.get("shopify_product_gid") == snapshot["product_gid"]
        and bool(mapping.get("active"))
        and (str(mapping.get("identity_type")), str(mapping.get("external_identity"))) in identities
        for mapping in snapshot.get("marketplace_mappings") or []
    )


def build_report(snapshot):
    tracking_start = edition_ledger.parse_datetime(snapshot.get("edition_tracking_start_at"))
    source_seen = {}
    edition_seen = {}
    source_line_rows = defaultdict(list)
    for row in snapshot.get("allocations") or []:
        source_key = _allocation_source_key(row)
        source_line_rows[source_key[:3]].append(row)
    source_line_problems = {}
    for source_line_key, rows in source_line_rows.items():
        expected_quantities = {
            int(row.get("line_quantity") or row.get("quantity") or 1)
            for row in rows
            if int(row.get("line_quantity") or row.get("quantity") or 1) > 0
        }
        expected_quantity = max(expected_quantities, default=1)
        ordinals = sorted(int(row.get("unit_ordinal") or row.get("allocation_index") or 0) for row in rows)
        problems = []
        if len(expected_quantities) > 1:
            problems.append("conflicting_source_line_quantities")
        if len(rows) != expected_quantity:
            problems.append(f"source_line_row_count_{len(rows)}_expected_{expected_quantity}")
        if ordinals != list(range(1, expected_quantity + 1)):
            problems.append("source_line_unit_ordinals_do_not_match_quantity")
        source_line_problems[source_line_key] = problems
    legitimate = []
    invalid = []
    manual_review = []
    for row in snapshot.get("allocations") or []:
        source_key = _allocation_source_key(row)
        edition_key = (snapshot["product_gid"], int(row.get("edition_number") or 0))
        reasons = []
        reasons.extend(source_line_problems.get(source_key[:3]) or [])
        if not source_key[1] or not source_key[2] or source_key[3] < 1:
            reasons.append("missing_or_invalid_durable_source_identity")
        if source_key in source_seen:
            reasons.append(f"duplicate_source_unit_of:{source_seen[source_key]}")
        else:
            source_seen[source_key] = row["id"]
        if edition_key in edition_seen:
            reasons.append(f"duplicate_product_edition_of:{edition_seen[edition_key]}")
        else:
            edition_seen[edition_key] = row["id"]
        financial = str(row.get("financial_status") or "").upper()
        if financial != "PAID":
            reasons.append(f"ineligible_financial_status:{financial or 'missing'}")
        if row.get("cancelled_at"):
            reasons.append("cancelled_order")
        if bool(row.get("test")):
            reasons.append("test_order")
        if str(row.get("shopify_product_gid") or row.get("shopify_product_id") or "") != snapshot["product_gid"]:
            reasons.append("wrong_canonical_product_gid")
        if row.get("allocation_valid") is False:
            reasons.append("allocation_already_invalidated")
        edition_number = int(row.get("edition_number") or 0)
        edition_total = int(row.get("edition_total") or 100)
        if edition_number < 1 or edition_number > edition_total or edition_total > 100:
            reasons.append("edition_number_or_total_out_of_range")
        if not _marketplace_mapping_exists(snapshot, row):
            reasons.append("marketplace_mapping_missing")
        order_at = edition_ledger.parse_datetime(row.get("order_created_at") or row.get("processed_at"))
        if tracking_start and order_at and order_at < tracking_start:
            reasons.append("historical_order_not_explicitly_backfilled")
        certificate_status = str(row.get("certificate_status") or "").strip().casefold()
        customer_facing = certificate_status in CUSTOMER_FACING_CERTIFICATE_STATUSES
        evidence = {
            "edition_order_id": row["id"],
            "source_channel": source_key[0],
            "external_order_id": source_key[1],
            "external_line_item_id": source_key[2],
            "unit_ordinal": source_key[3],
            "shopify_order_id": row.get("shopify_order_id") or "",
            "shopify_order_name": row.get("shopify_order_name") or "",
            "shopify_line_item_id": row.get("shopify_line_item_id") or "",
            "edition_number": row.get("edition_number"),
            "financial_status": financial,
            "fulfillment_status": row.get("fulfillment_status") or "",
            "certificate_status": row.get("certificate_status") or "",
            "assigned_at": row.get("assigned_at"),
            "reasons": reasons,
        }
        if reasons and customer_facing:
            evidence["repair_blocker"] = "Customer-facing certificate may already have been issued; preserve until manually verified."
            manual_review.append(evidence)
        elif reasons:
            invalid.append(evidence)
        else:
            legitimate.append(evidence)

    valid_numbers = sorted(int(row["edition_number"]) for row in legitimate if row.get("edition_number"))
    highest = max(valid_numbers, default=0)
    sold = len(valid_numbers)
    total = int((snapshot.get("edition_products") or [{}])[0].get("edition_total") or 100)
    missing_before_highest = sorted(set(range(1, highest + 1)).difference(valid_numbers))
    apply_blockers = []
    if manual_review:
        apply_blockers.append("Customer-facing allocations require explicit human verification.")
    if missing_before_highest:
        apply_blockers.append("The preserved allocation sequence contains gaps; automatic renumbering is forbidden.")
    if len(snapshot.get("edition_products") or []) != 1:
        apply_blockers.append("The Shopify product GID does not resolve to exactly one Edition Ops product row.")
    if snapshot.get("unresolved_identity_allocations"):
        apply_blockers.append(
            "Handle-only allocation candidates require explicit canonical Shopify product GID mapping."
        )
    sequence_is_contiguous = not missing_before_highest and (not valid_numbers or valid_numbers[0] == 1)
    next_number = highest + 1 if sequence_is_contiguous else None
    allocation_blocked = not sequence_is_contiguous
    report = {
        "mode": "dry_run",
        "product_gid": snapshot["product_gid"],
        "snapshot_sha256": _sha256(snapshot),
        "ledger_fingerprint_sha256": _ledger_fingerprint(snapshot),
        "rollback_state": {
            "edition_products": snapshot.get("edition_products") or [],
            "edition_runs": snapshot.get("edition_runs") or [],
            "edition_order_ids": [
                str(row.get("id") or "")
                for row in (snapshot.get("allocations") or [])
                if row.get("id")
            ],
        },
        "allocation_counts": {
            "total_rows": len(snapshot.get("allocations") or []),
            "verified_legitimate": len(legitimate),
            "confidently_invalid": len(invalid),
            "manual_review": len(manual_review),
        },
        "authoritative_state": {
            "edition_total": total,
            "sold_count": sold,
            "remaining_count": max(total - sold, 0),
            "highest_preserved_edition": highest,
            "next_edition_number": next_number,
            "allocation_blocked": allocation_blocked,
            "allocation_block_reason": (
                "Preserved issued editions are not a contiguous #001-up sequence; automatic allocation must remain frozen."
                if allocation_blocked
                else ""
            ),
            "missing_numbers_before_next": missing_before_highest,
        },
        "verified_legitimate_allocations": legitimate,
        "invalid_allocations_proposed_for_archive": invalid,
        "manual_review_allocations": manual_review,
        "unresolved_identity_allocations": snapshot.get("unresolved_identity_allocations") or [],
        "apply_blockers": apply_blockers,
        "shopify_metafield_plan_after_database_commit": (
            {
                "blocked": False,
                "edition_total": total,
                "edition_next_number": next_number,
                "edition_sold_count": sold,
                "edition_remaining": max(total - sold, 0),
                "next_edition_number": next_number,
                "last_assigned_edition": highest,
                "sold_count": sold,
                "remaining_count": max(total - sold, 0),
                "is_sold_out": sold >= total,
            }
            if not allocation_blocked
            else {
                "blocked": True,
                "reason": "No storefront next-edition value is safe until the preserved sequence gap is manually resolved.",
            }
        ),
    }
    report["report_sha256"] = _sha256(report)
    return report


def dry_run(product_gid):
    snapshot = _fetch_snapshot(product_gid)
    report = build_report(snapshot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = OUTPUT_ROOT / f"{stamp}-{product_gid.rsplit('/', 1)[-1]}"
    snapshot_path = directory / "snapshot.json"
    report_path = directory / "report.json"
    _write_json(snapshot_path, snapshot)
    _write_json(report_path, report)
    return snapshot_path, report_path, report


def _ensure_repair_tables(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_repair_audits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            repair_key TEXT NOT NULL UNIQUE,
            product_gid TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'apply', 'rollback')),
            snapshot_sha256 TEXT NOT NULL,
            report JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            applied_at TIMESTAMPTZ,
            rolled_back_at TIMESTAMPTZ,
            actor TEXT NOT NULL DEFAULT 'local_reconciliation_script'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_repair_archive (
            repair_key TEXT NOT NULL,
            edition_order_id TEXT NOT NULL,
            row_snapshot JSONB NOT NULL,
            archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (repair_key, edition_order_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_allocation_tombstones (
            source_channel TEXT NOT NULL,
            external_order_id TEXT NOT NULL,
            external_line_item_id TEXT NOT NULL,
            unit_ordinal INTEGER NOT NULL,
            shopify_product_gid TEXT NOT NULL,
            former_edition_number INTEGER NOT NULL,
            repair_key TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT 'invalid allocation archived',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (source_channel, external_order_id, external_line_item_id, unit_ordinal)
        )
        """
    )


def apply_report(report_path, confirmation):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    expected = report.get("report_sha256") or ""
    if confirmation != expected:
        raise ValueError("--confirm must exactly match report_sha256 from the approved dry-run report.")
    if report.get("apply_blockers"):
        raise ValueError("Repair is blocked: " + "; ".join(report["apply_blockers"]))
    current_snapshot = _fetch_snapshot(report["product_gid"])
    if _ledger_fingerprint(current_snapshot) != report.get("ledger_fingerprint_sha256"):
        raise RuntimeError("Edition ledger changed after dry-run; create and approve a new report.")
    invalid_ids = [row["edition_order_id"] for row in report.get("invalid_allocations_proposed_for_archive") or []]
    invalid_evidence_by_id = {
        str(row.get("edition_order_id") or ""): row
        for row in report.get("invalid_allocations_proposed_for_archive") or []
    }
    product_rows = report.get("rollback_state", {}).get("edition_products") or []
    if len(product_rows) != 1 or not product_rows[0].get("id"):
        raise RuntimeError("Approved report does not contain exactly one immutable Edition Ops product row ID.")
    edition_product_id = str(product_rows[0]["id"])
    repair_key = f"edition-repair-{uuid.uuid4()}"
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                _ensure_repair_tables(cur)
                cur.execute("SELECT set_config('sports_cave.edition_repair_key', %s, TRUE)", (repair_key,))
                cur.execute("SELECT * FROM edition_orders WHERE id::text = ANY(%s) FOR UPDATE", (invalid_ids,))
                rows = [dict(row) for row in cur.fetchall()]
                if len(rows) != len(invalid_ids):
                    raise RuntimeError("Approved allocation set changed after dry-run; create a new report.")
                for row in rows:
                    evidence = invalid_evidence_by_id.get(str(row.get("id") or "")) or {}
                    cur.execute(
                        "INSERT INTO edition_repair_archive(repair_key, edition_order_id, row_snapshot) VALUES (%s,%s,%s::jsonb)",
                        (repair_key, str(row["id"]), _canonical_json(row)),
                    )
                    cur.execute(
                        """
                        INSERT INTO edition_allocation_tombstones(
                            source_channel, external_order_id, external_line_item_id,
                            unit_ordinal, shopify_product_gid, former_edition_number,
                            repair_key, reason
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            evidence.get("source_channel") or row.get("source_channel"),
                            evidence.get("external_order_id") or row.get("external_order_id"),
                            evidence.get("external_line_item_id") or row.get("external_line_item_id"),
                            evidence.get("unit_ordinal") or row.get("unit_ordinal") or row.get("allocation_index") or 1,
                            row.get("shopify_product_gid") or report["product_gid"],
                            evidence.get("edition_number") or row.get("edition_number"),
                            repair_key,
                            "Invalid allocation archived by approved hash-bound repair.",
                        ),
                    )
                if invalid_ids:
                    cur.execute("DELETE FROM edition_orders WHERE id::text = ANY(%s)", (invalid_ids,))
                state = report["authoritative_state"]
                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=%s, last_assigned_edition=%s, sold_count=%s,
                        remaining_count=%s, sold_out=%s, is_sold_out=%s, updated_at=now()
                    WHERE id::text=%s
                    """,
                    (
                        state["next_edition_number"], state["highest_preserved_edition"], state["sold_count"],
                        state["remaining_count"], state["highest_preserved_edition"] >= state["edition_total"],
                        state["highest_preserved_edition"] >= state["edition_total"], edition_product_id,
                    ),
                )
                cur.execute(
                    """
                    UPDATE edition_runs er
                    SET next_edition_number=%s,
                        status=CASE WHEN %s THEN 'sold_out' ELSE 'active' END,
                        updated_at=now()
                    WHERE er.edition_product_id::text=%s
                    """,
                    (
                        state["next_edition_number"],
                        state["sold_count"] >= state["edition_total"],
                        edition_product_id,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO edition_repair_audits(repair_key, product_gid, mode, snapshot_sha256, report, applied_at)
                    VALUES (%s,%s,'apply',%s,%s::jsonb,now())
                    """,
                    (repair_key, report["product_gid"], report["snapshot_sha256"], _canonical_json(report)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return repair_key


def rollback_repair(repair_key, confirmation):
    if confirmation != repair_key:
        raise ValueError("Rollback requires --confirm to exactly match --rollback-repair-key.")
    with supabase_backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                _ensure_repair_tables(cur)
                cur.execute(
                    "SELECT product_gid, report, rolled_back_at FROM edition_repair_audits WHERE repair_key=%s FOR UPDATE",
                    (repair_key,),
                )
                audit = cur.fetchone()
                if not audit:
                    raise ValueError("Unknown repair key.")
                if audit.get("rolled_back_at"):
                    raise ValueError("Repair has already been rolled back.")
                cur.execute("SELECT set_config('sports_cave.edition_repair_key', %s, TRUE)", (repair_key,))
                product_gid = audit["product_gid"]
                stored_report = audit.get("report") or {}
                if isinstance(stored_report, str):
                    stored_report = json.loads(stored_report)
                rollback_state = stored_report.get("rollback_state") or {}
                original_products = rollback_state.get("edition_products") or []
                if len(original_products) != 1 or not original_products[0].get("id"):
                    raise RuntimeError("Rollback snapshot does not contain exactly one Edition Ops product row ID.")
                original = original_products[0]
                edition_product_id = str(original["id"])
                original_order_ids = {
                    str(value)
                    for value in (rollback_state.get("edition_order_ids") or [])
                    if value
                }
                cur.execute(
                    "SELECT edition_order_id FROM edition_repair_archive WHERE repair_key=%s",
                    (repair_key,),
                )
                archived_order_ids = {
                    str(row.get("edition_order_id") or "")
                    for row in (cur.fetchall() or [])
                    if row.get("edition_order_id")
                }
                cur.execute(
                    """
                    SELECT id::text AS id
                    FROM edition_orders
                    WHERE CASE
                              WHEN COALESCE(to_jsonb(edition_orders)->>'shopify_product_gid', '') ~ '^gid://shopify/Product/[0-9]+$'
                                  THEN to_jsonb(edition_orders)->>'shopify_product_gid'
                              WHEN COALESCE(to_jsonb(edition_orders)->>'shopify_product_id', '') ~ '^gid://shopify/Product/[0-9]+$'
                                  THEN to_jsonb(edition_orders)->>'shopify_product_id'
                              WHEN COALESCE(to_jsonb(edition_orders)->>'shopify_product_id', '') ~ '^[0-9]+$'
                                  THEN 'gid://shopify/Product/' || (to_jsonb(edition_orders)->>'shopify_product_id')
                              ELSE NULL
                          END=%s
                       OR edition_run_id IN (
                           SELECT id FROM edition_runs WHERE edition_product_id::text=%s
                       )
                    """,
                    (audit["product_gid"], edition_product_id),
                )
                current_order_ids = {
                    str(row.get("id") or "")
                    for row in (cur.fetchall() or [])
                    if row.get("id")
                }
                expected_current_ids = original_order_ids.difference(archived_order_ids)
                if current_order_ids != expected_current_ids:
                    raise RuntimeError(
                        "The product ledger changed after repair; rollback is blocked to preserve later allocations."
                    )
                cur.execute(
                    """
                    INSERT INTO edition_orders
                    SELECT (jsonb_populate_record(NULL::edition_orders, era.row_snapshot)).*
                    FROM edition_repair_archive era
                    WHERE era.repair_key=%s
                    """,
                    (repair_key,),
                )
                cur.execute(
                    "DELETE FROM edition_allocation_tombstones WHERE repair_key=%s",
                    (repair_key,),
                )
                cur.execute(
                    """
                    UPDATE edition_products
                    SET next_edition_number=%s, last_assigned_edition=%s, sold_count=%s,
                        remaining_count=%s, sold_out=%s, is_sold_out=%s, updated_at=now()
                    WHERE id::text=%s
                    """,
                    (
                        original.get("next_edition_number"), original.get("last_assigned_edition"),
                        original.get("sold_count"), original.get("remaining_count"),
                        bool(original.get("sold_out")), bool(original.get("is_sold_out")), edition_product_id,
                    ),
                )
                for original_run in rollback_state.get("edition_runs") or []:
                    cur.execute(
                        """
                        UPDATE edition_runs
                        SET next_edition_number=%s, status=%s, updated_at=now()
                        WHERE id::text=%s
                        """,
                        (
                            original_run.get("next_edition_number"),
                            original_run.get("status"),
                            str(original_run.get("id") or ""),
                        ),
                    )
                cur.execute(
                    "UPDATE edition_repair_audits SET rolled_back_at=now() WHERE repair_key=%s",
                    (repair_key,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rolled_back": True, "repair_key": repair_key, "shopify_mutated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-gid")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-report")
    parser.add_argument("--rollback-repair-key")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.rollback_repair_key:
        print(json.dumps(rollback_repair(args.rollback_repair_key, args.confirm), indent=2))
        return
    if args.apply:
        if not args.approved_report:
            parser.error("--apply requires --approved-report and --confirm")
        repair_key = apply_report(args.approved_report, args.confirm)
        print(json.dumps({"applied": True, "repair_key": repair_key, "shopify_mutated": False}, indent=2))
        return
    if not args.product_gid:
        parser.error("dry-run mode requires --product-gid")
    snapshot_path, report_path, report = dry_run(args.product_gid)
    print(json.dumps({
        "mode": "dry_run",
        "snapshot": str(snapshot_path),
        "report": str(report_path),
        "report_sha256": report["report_sha256"],
        "apply_blockers": report["apply_blockers"],
        "production_mutated": False,
    }, indent=2))


if __name__ == "__main__":
    main()
