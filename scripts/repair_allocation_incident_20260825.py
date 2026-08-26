"""Guarded recovery for the 2026-08-25 missing atomic-allocation incident.

Dry-run is the default.  Production apply requires a durable database snapshot,
the exact snapshot SHA, and the compatible migration in this repository.
Customer and shipping data are retained inside the backup row but never printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import edition_ledger  # noqa: E402
import supabase_backend  # noqa: E402


MIGRATION = ROOT / "migrations" / "20260825_atomic_edition_allocation_ledger.sql"
INCIDENT_STARTED_AT = "2026-08-25T00:00:00Z"
EXPECTED_LINES = {
    ("#SC3060", "gid://shopify/Product/8116473790771"): "Shane Warne Tribute Wall Art",
    ("#SC3061", "gid://shopify/Product/10180244439347"): "Legends Never Die Kobe vs Jordan Wall Art",
    ("#SC3062", "gid://shopify/Product/10180244439347"): "Legends Never Die Kobe vs Jordan Wall Art",
    ("#SC3063", "gid://shopify/Product/10155674403123"): "All Rise Aaron Judge Wall Art",
    ("#SC3064", "gid://shopify/Product/10155674403123"): "All Rise Aaron Judge Wall Art",
}
PRESERVED_ORDER_NAMES = ("#SC3056", "#SC3058", "#SC3059")
PRESERVED_ORDER_EDITIONS = {
    "#SC3056": [9, 91],
    "#SC3058": [76],
    "#SC3059": [36],
}
MISSING_FUNCTION_TEXT = "function allocate_edition_line_units_atomic"
REQUIRED_LEDGER_COLUMNS = frozenset(
    {
        "source_channel",
        "external_order_id",
        "external_line_item_id",
        "unit_ordinal",
        "shopify_product_gid",
        "allocation_valid",
        "identity_enforced",
    }
)


def _json_default(value):
    if isinstance(value, (datetime, Path)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    return str(value)


def _stable_json(payload):
    return json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":"))


def _sha256(payload):
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _query(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(row) for row in (cur.fetchall() or [])]


def fetch_candidates(cur):
    return _query(
        cur,
        """
        SELECT o.order_name, o.shopify_order_id,
               COALESCE(o.processed_at, o.created_at, o.synced_at) AS paid_at,
               o.financial_status, o.fulfillment_status,
               li.shopify_line_item_id, li.shopify_product_id,
               li.shopify_handle, li.product_title, li.variant_title,
               li.sku, li.quantity, li.assignment_status, li.last_error,
               o.raw_json
        FROM shopify_order_lines li
        JOIN shopify_orders o ON o.shopify_order_id=li.shopify_order_id
        WHERE li.assignment_status='Error'
          AND li.last_error LIKE %s
          AND LOWER(COALESCE(o.financial_status, '')) IN ('paid', 'partially_paid', 'partially paid')
          AND o.cancelled_at IS NULL
          AND LOWER(COALESCE(o.raw_json->>'test', 'false')) NOT IN ('true', '1')
          AND COALESCE(o.processed_at, o.created_at, o.synced_at) >= %s::timestamptz
        ORDER BY COALESCE(o.processed_at, o.created_at, o.synced_at),
                 o.order_name, li.shopify_line_item_id
        """,
        (f"%{MISSING_FUNCTION_TEXT}%", INCIDENT_STARTED_AT),
    )


def _active_product_state(cur, product_gid):
    rows = _query(
        cur,
        """
        SELECT ep.id AS edition_product_id, ep.shopify_product_gid,
               ep.shopify_product_id, ep.shopify_handle, ep.product_title,
               ep.edition_total, ep.sold_count, ep.remaining_count,
               ep.last_assigned_edition, ep.next_edition_number,
               ep.sold_out, ep.is_sold_out, ep.active_edition_run_id,
               er.edition_total AS run_total,
               er.next_edition_number AS run_next,
               er.status AS run_status,
               COALESCE((to_jsonb(er)->>'allocation_baseline_sold_count')::integer,
                        GREATEST(COALESCE(ep.sold_count, 0) - COUNT(eo.id), 0)) AS baseline,
               ARRAY_AGG(eo.edition_number ORDER BY eo.edition_number)
                   FILTER (WHERE eo.id IS NOT NULL) AS active_numbers
        FROM edition_products ep
        JOIN edition_runs er ON er.id=ep.active_edition_run_id
        LEFT JOIN edition_orders eo
          ON eo.edition_run_id=er.id
         AND COALESCE((to_jsonb(eo)->>'allocation_valid')::boolean, TRUE)
         AND COALESCE(eo.status, '') NOT IN ('voided', 'refunded', 'cancelled', 'superseded')
        WHERE COALESCE(NULLIF(ep.shopify_product_gid, ''), NULLIF(ep.shopify_product_id, ''))=%s
        GROUP BY ep.id, er.id
        """,
        (product_gid,),
    )
    if len(rows) != 1:
        raise RuntimeError(f"Product GID {product_gid} resolved to {len(rows)} active Edition Ops rows.")
    state = rows[0]
    numbers = [int(value) for value in (state.get("active_numbers") or [])]
    sold = int(state.get("sold_count") or 0)
    baseline = int(state.get("baseline") or 0)
    expected_tail = list(range(baseline + 1, sold + 1))
    if numbers != expected_tail:
        raise RuntimeError(
            f"Active run is not contiguous for {product_gid}: baseline={baseline}; "
            f"numbers={numbers}; sold={sold}."
        )
    if int(state.get("last_assigned_edition") or 0) != sold:
        raise RuntimeError(f"Last-assigned mismatch for {product_gid}.")
    if int(state.get("next_edition_number") or 1) != sold + 1:
        raise RuntimeError(f"Product next-edition mismatch for {product_gid}.")
    if int(state.get("run_next") or 1) != sold + 1:
        raise RuntimeError(f"Active-run next-edition mismatch for {product_gid}.")
    return state


def _validate_candidate_identity(row):
    order_name = str(row.get("order_name") or "")
    product_gid = edition_ledger.canonical_shopify_gid("Product", row.get("shopify_product_id"))
    expected_title = EXPECTED_LINES.get((order_name, product_gid))
    if (order_name, product_gid) in EXPECTED_LINES:
        if str(row.get("product_title") or "") != expected_title:
            raise RuntimeError(f"{order_name} product title did not match the approved product GID.")
    return product_gid


def build_plan(cur, candidates=None):
    candidates = list(candidates if candidates is not None else fetch_candidates(cur))
    discovered = {
        (str(row.get("order_name") or ""), _validate_candidate_identity(row))
        for row in candidates
    }
    missing_expected = sorted(set(EXPECTED_LINES) - discovered)
    unexpected = sorted(discovered - set(EXPECTED_LINES))
    if missing_expected or unexpected:
        raise RuntimeError(
            f"Incident scope mismatch; missing_expected={missing_expected}; unexpected={unexpected}."
        )
    states = {}
    cursors = {}
    planned = []
    for row in candidates:
        product_gid = _validate_candidate_identity(row)
        if product_gid not in states:
            states[product_gid] = _active_product_state(cur, product_gid)
            cursors[product_gid] = int(states[product_gid]["next_edition_number"])
        quantity = max(int(row.get("quantity") or 1), 1)
        first = cursors[product_gid]
        last = first + quantity - 1
        total = int(states[product_gid].get("edition_total") or 100)
        if last > total:
            raise RuntimeError(f"Edition limit would be exceeded for {product_gid}.")
        planned.append(
            {
                "order_name": row["order_name"],
                "shopify_order_id": row["shopify_order_id"],
                "shopify_line_item_id": edition_ledger.canonical_shopify_gid(
                    "LineItem", row["shopify_line_item_id"]
                ),
                "product_gid": product_gid,
                "product_title": row["product_title"],
                "quantity": quantity,
                "edition_numbers": list(range(first, last + 1)),
                "paid_at": row["paid_at"],
                "source_channel": edition_ledger.source_channel_for_order(row.get("raw_json") or {}),
            }
        )
        cursors[product_gid] = last + 1
    products = {}
    for product_gid, state in states.items():
        allocated = sum(item["quantity"] for item in planned if item["product_gid"] == product_gid)
        sold_after = int(state["sold_count"] or 0) + allocated
        total = int(state["edition_total"] or 100)
        products[product_gid] = {
            "product_title": state["product_title"],
            "before": {
                "sold": int(state["sold_count"] or 0),
                "remaining": int(state["remaining_count"] or 0),
                "last": int(state["last_assigned_edition"] or 0),
                "next": int(state["next_edition_number"] or 1),
                "baseline": int(state["baseline"] or 0),
            },
            "after": {
                "sold": sold_after,
                "remaining": total - sold_after,
                "last": sold_after,
                "next": sold_after + 1,
                "sold_out": sold_after >= total,
            },
        }
    return {
        "mode": "dry_run",
        "incident_started_at": INCIDENT_STARTED_AT,
        "candidate_count": len(candidates),
        "orders": planned,
        "products": products,
    }


def _snapshot_payload(cur, plan):
    order_ids = sorted({item["shopify_order_id"] for item in plan["orders"]})
    product_gids = sorted(plan["products"])
    snapshot = {
        "captured_at": datetime.now(timezone.utc),
        "plan": plan,
        "edition_orders": _query(cur, "SELECT to_jsonb(eo) AS row FROM edition_orders eo ORDER BY eo.id"),
        "edition_products": _query(cur, "SELECT to_jsonb(ep) AS row FROM edition_products ep ORDER BY ep.id"),
        "edition_runs": _query(cur, "SELECT to_jsonb(er) AS row FROM edition_runs er ORDER BY er.id"),
        "affected_orders": _query(
            cur,
            "SELECT to_jsonb(o) AS row FROM shopify_orders o WHERE o.shopify_order_id=ANY(%s) ORDER BY o.shopify_order_id",
            (order_ids,),
        ),
        "affected_lines": _query(
            cur,
            "SELECT to_jsonb(li) AS row FROM shopify_order_lines li WHERE li.shopify_order_id=ANY(%s) ORDER BY li.id",
            (order_ids,),
        ),
        "affected_certificates": _query(
            cur,
            "SELECT to_jsonb(c) AS row FROM certificates c WHERE c.shopify_order_id=ANY(%s) ORDER BY c.id",
            (order_ids,),
        ),
        "preserved_rows": _query(
            cur,
            """
            SELECT eo.shopify_order_name, eo.shopify_line_item_id, eo.shopify_product_id,
                   eo.product_title, eo.edition_number, eo.edition_total, eo.status,
                   eo.certificate_status, eo.id
            FROM edition_orders eo
            WHERE eo.shopify_order_name=ANY(%s)
            ORDER BY eo.shopify_order_name, eo.shopify_line_item_id, eo.allocation_index
            """,
            (list(PRESERVED_ORDER_NAMES),),
        ),
        "affected_product_gids": product_gids,
    }
    return snapshot


def create_backup(cur, repair_key, plan):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS edition_allocation_incident_backups (
            repair_key TEXT PRIMARY KEY,
            snapshot_sha256 TEXT NOT NULL,
            snapshot JSONB NOT NULL,
            dry_run JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            applied_at TIMESTAMPTZ,
            apply_result JSONB NOT NULL DEFAULT '{}'::jsonb,
            verification JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    snapshot = _snapshot_payload(cur, plan)
    snapshot_sha256 = _sha256(snapshot)
    cur.execute(
        """
        INSERT INTO edition_allocation_incident_backups(
            repair_key, snapshot_sha256, snapshot, dry_run
        ) VALUES (%s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (repair_key) DO NOTHING
        RETURNING repair_key
        """,
        (repair_key, snapshot_sha256, _stable_json(snapshot), _stable_json(plan)),
    )
    if not cur.fetchone():
        cur.execute(
            "SELECT snapshot_sha256 FROM edition_allocation_incident_backups WHERE repair_key=%s",
            (repair_key,),
        )
        existing = cur.fetchone() or {}
        if existing.get("snapshot_sha256") != snapshot_sha256:
            raise RuntimeError("Repair key already exists with a different production snapshot.")
    return snapshot_sha256


def _migration_capability(cur):
    cur.execute(
        """
        SELECT to_regprocedure(
            'allocate_edition_line_units_atomic(text,text,text,text,integer,text,text,text,text,text,text,text,text,text,text)'
        )::text AS function_name,
        to_regclass('public.order_line_edition_overrides')::text AS override_table
        """
    )
    capability = dict(cur.fetchone() or {})
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='edition_orders'
          AND column_name=ANY(%s)
        ORDER BY column_name
        """,
        (sorted(REQUIRED_LEDGER_COLUMNS),),
    )
    present = {str(row.get("column_name") or "") for row in cur.fetchall()}
    capability["missing_columns"] = sorted(
        REQUIRED_LEDGER_COLUMNS - present
    )
    capability["ready"] = bool(capability.get("function_name")) and not capability["missing_columns"]
    return capability


def _target_assignment_rows(cur, item):
    return _query(
        cur,
        """
        SELECT id, edition_number, edition_total, allocation_index, quantity,
               source_channel, external_order_id, external_line_item_id,
               unit_ordinal, shopify_product_gid, allocation_valid,
               identity_enforced, mirror_status, certificate_status
        FROM edition_orders
        WHERE source_channel=%s AND external_order_id=%s
          AND external_line_item_id=%s AND allocation_valid
        ORDER BY unit_ordinal
        """,
        (
            item["source_channel"],
            item["shopify_order_id"],
            item["shopify_line_item_id"],
        ),
    )


def _certificate_is_complete(cur, assignment_id):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM certificates c
            WHERE COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=%s
              AND (
                    COALESCE(NULLIF(c.certificate_pdf_url, ''), NULLIF(c.shopify_file_url, ''),
                             NULLIF(c.certificate_file_url, '')) IS NOT NULL
                 OR (COALESCE(c.certificate_r2_bucket, '') <> ''
                     AND COALESCE(c.certificate_r2_key, '') <> '')
              )
              AND LOWER(COALESCE(c.order_metafields_sync_status, ''))='synced'
        ) AS complete
        """,
        (str(assignment_id),),
    )
    return bool((cur.fetchone() or {}).get("complete"))


def _load_order_snapshots(cur, order_ids):
    rows = _query(
        cur,
        "SELECT shopify_order_id, raw_json FROM shopify_orders WHERE shopify_order_id=ANY(%s)",
        (sorted(order_ids),),
    )
    return {
        row["shopify_order_id"]: supabase_backend._normalize_cached_order_snapshot(row["raw_json"])
        for row in rows
    }


def _mirror_verified_product_state(product_gid, expected):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            state = _active_product_state(cur, product_gid)
            actual = {
                "sold": int(state["sold_count"]),
                "remaining": int(state["remaining_count"]),
                "last": int(state["last_assigned_edition"]),
                "next": int(state["next_edition_number"]),
                "sold_out": bool(state["sold_out"] or state["is_sold_out"]),
            }
            if actual != expected:
                raise RuntimeError(
                    f"Refusing Shopify mirror for {product_gid}: verified database state changed."
                )
            cur.execute(
                """
                SELECT ep.id AS edition_product_id, ep.shopify_handle,
                       ep.product_title, ep.edition_total,
                       NOT COALESCE(ep.is_active, ep.active, TRUE) AS is_archived,
                       er.id AS edition_run_id, er.edition_name
                FROM edition_products ep
                JOIN edition_runs er ON er.id=ep.active_edition_run_id
                WHERE ep.shopify_product_gid=%s
                  AND LOWER(COALESCE(er.status, ''))='active'
                """,
                (product_gid,),
            )
            product = dict(cur.fetchone() or {})
    if not product:
        raise RuntimeError(f"Active Edition Ops product disappeared before mirror: {product_gid}.")

    total = int(product.get("edition_total") or 100)
    status_values = supabase_backend.calculate_product_edition_metafield_values(
        {
            "edition_total": total,
            "highest_assigned_edition": expected["last"],
            "sold_count": expected["sold"],
        }
    )
    payload = {
        **product,
        "shopify_product_id": product_gid,
        "shopify_product_gid": product_gid,
        "edition_enabled": not bool(product.get("is_archived")),
        "edition_total": total,
        "edition_next_number": expected["next"],
        "edition_sold_count": expected["sold"],
        "edition_remaining": expected["remaining"],
        "edition_status": status_values["edition_status"],
        "edition_label": product.get("edition_name") or supabase_backend.DEFAULT_EDITION_NAME,
        "next_edition_number": expected["next"],
        "last_assigned_edition": expected["last"],
        "sold_count": expected["sold"],
        "remaining_count": expected["remaining"],
        "is_sold_out": expected["sold_out"],
        "edition_display_text": status_values["edition_display_text"],
    }
    before = supabase_backend._fetch_public_edition_metafields(product_gid)
    if before.get("error"):
        raise RuntimeError(f"Could not read Shopify metafields before mirror for {product_gid}.")
    response = supabase_backend.shopify_sync.sync_complete_product_edition_metafields(payload)
    after = supabase_backend._fetch_public_edition_metafields(product_gid)
    if after.get("error"):
        raise RuntimeError(f"Could not read Shopify metafields after mirror for {product_gid}.")
    after_values = supabase_backend._public_edition_metafield_values(after.get("metafields") or [])
    expected_values = supabase_backend._shopify_product_mirror_values_from_payload(payload)
    mismatches = {
        key: {"expected": str(value), "actual": str(after_values.get(key, ""))}
        for key, value in expected_values.items()
        if str(after_values.get(key, "")) != str(value)
    }
    if mismatches:
        raise RuntimeError(
            f"Shopify metafield readback did not match the verified database state for {product_gid}: {mismatches}"
        )
    supabase_backend._mark_product_metafields_sync(
        product["shopify_handle"], payload, "Synced", ""
    )
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE edition_orders
                SET mirror_status='synced', mirror_attempted_at=now(),
                    mirror_error='', updated_at=now()
                WHERE edition_run_id=%s
                  AND identity_enforced
                  AND allocation_valid
                  AND COALESCE(mirror_status, 'pending') IN ('pending', 'failed')
                """,
                (product["edition_run_id"],),
            )
        conn.commit()
    supabase_backend._record_product_metafield_mirror_audit(
        product["shopify_handle"],
        status="updated",
        payload=payload,
        before=before.get("metafields") or [],
        after=after.get("metafields") or [],
    )
    return {
        "handle": product["shopify_handle"],
        "confirmed_metafields": expected_values,
        "confirmed_count": int(response.get("count") or 0),
    }


def apply_repair(repair_key, expected_snapshot_sha256, migration_path=MIGRATION):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT snapshot_sha256, dry_run FROM edition_allocation_incident_backups WHERE repair_key=%s FOR UPDATE",
                (repair_key,),
            )
            backup = cur.fetchone()
            if not backup:
                raise RuntimeError("The required production backup row does not exist.")
            if backup["snapshot_sha256"] != expected_snapshot_sha256:
                raise RuntimeError("Snapshot SHA confirmation did not match the durable backup.")
            plan = dict(backup["dry_run"] or {})
        conn.commit()

    migration_applied = False
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            capability_before = _migration_capability(cur)
    if not capability_before["ready"]:
        migration_sql = Path(migration_path).read_text(encoding="utf-8")
        with supabase_backend.connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(migration_sql)
                conn.commit()
                migration_applied = True
            except Exception:
                conn.rollback()
                raise

    results = []
    touched_handles = set()
    order_ids = {item["shopify_order_id"] for item in plan["orders"]}
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            capability = _migration_capability(cur)
            if not capability["ready"]:
                raise RuntimeError(f"Atomic migration did not install cleanly: {capability}")
            snapshots = _load_order_snapshots(cur, order_ids)

    for item in plan["orders"]:
        allocation_was_created = False
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                existing = _target_assignment_rows(cur, item)
        expected_numbers = [int(number) for number in item["edition_numbers"]]
        existing_numbers = [int(row["edition_number"]) for row in existing]
        if existing and existing_numbers != expected_numbers:
            raise RuntimeError(
                f"Existing allocation for {item['order_name']} changed since dry-run: {existing_numbers}."
            )
        if not existing:
            order = snapshots.get(item["shopify_order_id"])
            if not order:
                raise RuntimeError(f"Stored order snapshot missing for {item['order_name']}.")
            result = supabase_backend.process_paid_order(
                order,
                fetch_missing_products=False,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
                ingestion_method="atomic_allocation_incident_repair",
            )
            if result.get("errors") or int(result.get("assignments_created") or 0) != item["quantity"]:
                raise RuntimeError(f"Allocation failed for {item['order_name']}: {result}")
            allocation_was_created = True
            with supabase_backend.connect() as conn:
                with conn.cursor() as cur:
                    existing = _target_assignment_rows(cur, item)
            existing_numbers = [int(row["edition_number"]) for row in existing]
            if existing_numbers != expected_numbers:
                raise RuntimeError(f"Allocated editions did not match dry-run for {item['order_name']}.")
        generated = 0
        for assignment in existing:
            with supabase_backend.connect() as conn:
                with conn.cursor() as cur:
                    complete = _certificate_is_complete(cur, assignment["id"])
            if not complete:
                supabase_backend.generate_certificate_for_edition_order(
                    assignment["id"],
                    force=False,
                    source_page="Atomic allocation incident repair",
                    ensure_schema_first=False,
                )
                generated += 1
        if generated:
            sync_result = supabase_backend.sync_order_certificate_metafields(
                item["shopify_order_id"], ensure_schema_first=False
            )
            if sync_result.get("failed"):
                raise RuntimeError(f"Order certificate metafield sync failed for {item['order_name']}.")
        touched_handles.add(item["product_gid"])
        results.append(
            {
                "order_name": item["order_name"],
                "edition_numbers": expected_numbers,
                "assignment_ids": [str(row["id"]) for row in existing],
                "allocations_created": item["quantity"] if allocation_was_created else 0,
                "certificates_generated": generated,
            }
        )

    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ep.shopify_handle
                FROM edition_products ep
                JOIN edition_orders eo ON eo.shopify_product_gid=ep.shopify_product_gid
                WHERE ep.shopify_product_gid=ANY(%s)
                  AND eo.identity_enforced AND eo.mirror_status<>'synced'
                """,
                (sorted(touched_handles),),
            )
            pending_handles = [row["shopify_handle"] for row in cur.fetchall()]
    mirror_results = []
    for handle in pending_handles:
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT shopify_product_gid FROM edition_products WHERE shopify_handle=%s",
                    (handle,),
                )
                product_gid = str((cur.fetchone() or {}).get("shopify_product_gid") or "")
        if product_gid not in plan["products"]:
            raise RuntimeError(f"Pending mirror escaped the approved product scope: {handle}.")
        mirror_results.append(
            _mirror_verified_product_state(product_gid, plan["products"][product_gid]["after"])
        )

    verification = verify(plan)
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            apply_result_json = _stable_json(
                {"orders": results, "mirrors": mirror_results, "migration_applied": migration_applied}
            )
            verification_json = _stable_json(verification)
            cur.execute(
                """
                UPDATE edition_allocation_incident_backups
                SET applied_at=COALESCE(applied_at, now()),
                    apply_result=%s::jsonb,
                    verification=%s::jsonb
                WHERE repair_key=%s
                  AND (
                        applied_at IS NULL
                     OR apply_result IS DISTINCT FROM %s::jsonb
                     OR verification IS DISTINCT FROM %s::jsonb
                  )
                """,
                (
                    apply_result_json,
                    verification_json,
                    repair_key,
                    apply_result_json,
                    verification_json,
                ),
            )
            audit_updated = int(cur.rowcount or 0)
        conn.commit()
    return {
        "orders": results,
        "mirrors": mirror_results,
        "migration_applied": migration_applied,
        "audit_updated": audit_updated,
        "verification": verification,
    }


def verify(plan):
    order_results = []
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            capability = _migration_capability(cur)
            for item in plan["orders"]:
                assignments = _target_assignment_rows(cur, item)
                cur.execute(
                    """
                    SELECT assignment_status, last_error
                    FROM shopify_order_lines
                    WHERE shopify_order_id=%s
                      AND shopify_line_item_id=ANY(%s)
                    """,
                    (
                        item["shopify_order_id"],
                        list(supabase_backend._shopify_id_candidates(
                            "LineItem", item["shopify_line_item_id"]
                        )),
                    ),
                )
                line = dict(cur.fetchone() or {})
                complete = all(_certificate_is_complete(cur, row["id"]) for row in assignments)
                order_results.append(
                    {
                        "order_name": item["order_name"],
                        "edition_numbers": [int(row["edition_number"]) for row in assignments],
                        "assignment_ids": [str(row["id"]) for row in assignments],
                        "identity_enforced": all(bool(row["identity_enforced"]) for row in assignments),
                        "assignment_status": line.get("assignment_status") or "",
                        "last_error_cleared": not bool(line.get("last_error")),
                        "certificate_complete": complete,
                    }
                )
            product_results = {}
            for product_gid, expected in plan["products"].items():
                state = _active_product_state(cur, product_gid)
                product_results[product_gid] = {
                    "sold": int(state["sold_count"]),
                    "remaining": int(state["remaining_count"]),
                    "last": int(state["last_assigned_edition"]),
                    "next": int(state["next_edition_number"]),
                    "sold_out": bool(state["sold_out"] or state["is_sold_out"]),
                    "expected": expected["after"],
                }
            preserved = _query(
                cur,
                """
                SELECT shopify_order_name, product_title, edition_number, edition_total
                FROM edition_orders WHERE shopify_order_name=ANY(%s)
                ORDER BY shopify_order_name, product_title, edition_number
                """,
                (list(PRESERVED_ORDER_NAMES),),
            )
    preserved_numbers = {
        order_name: sorted(
            int(row["edition_number"])
            for row in preserved
            if row["shopify_order_name"] == order_name
        )
        for order_name in PRESERVED_ORDER_NAMES
    }
    ok = capability["ready"]
    ok = ok and all(
        row["edition_numbers"] == item["edition_numbers"]
        and row["identity_enforced"]
        and row["assignment_status"] == "Assigned"
        and row["last_error_cleared"]
        and row["certificate_complete"]
        for row, item in zip(order_results, plan["orders"])
    )
    ok = ok and all(
        {key: value for key, value in result.items() if key in {"sold", "remaining", "last", "next", "sold_out"}}
        == result["expected"]
        for result in product_results.values()
    )
    ok = ok and preserved_numbers == PRESERVED_ORDER_EDITIONS
    return {
        "ok": ok,
        "capability": capability,
        "orders": order_results,
        "products": product_results,
        "preserved": preserved,
        "preserved_numbers": preserved_numbers,
    }


def _redacted_plan(plan):
    return {
        **plan,
        "orders": [
            {
                key: value
                for key, value in item.items()
                if key not in {"shopify_order_id", "shopify_line_item_id"}
            }
            for item in plan["orders"]
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repair-key", default="")
    parser.add_argument("--snapshot-sha256", default="")
    parser.add_argument("--migration", default=str(MIGRATION))
    args = parser.parse_args(argv)
    if args.apply:
        if not args.repair_key or not args.snapshot_sha256:
            raise SystemExit("--apply requires --repair-key and --snapshot-sha256")
        result = apply_repair(args.repair_key, args.snapshot_sha256, Path(args.migration))
        print(_stable_json(result))
        return 0
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            plan = build_plan(cur)
            backup_sha = ""
            if args.backup:
                if not args.repair_key:
                    raise SystemExit("--backup requires --repair-key")
                backup_sha = create_backup(cur, args.repair_key, plan)
        if args.backup:
            conn.commit()
    print(_stable_json({"plan": _redacted_plan(plan), "snapshot_sha256": backup_sha}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
