"""Evidence-bound plans for the 25 August 2026 Edition Ops incident.

The functions in this module are deliberately pure.  Production readers and
writers live in ``scripts/repair_shane_warne_editions.py``; tests can therefore
exercise the complete decision policy without a database or Shopify mutation.
"""

from __future__ import annotations

import hashlib
import json

import edition_ledger


SHANE_WARNE_PRODUCT_GID = "gid://shopify/Product/8116473790771"
MICHAEL_JORDAN_SC3056_LINE_GID = "gid://shopify/LineItem/17475132293427"
SC3058_ORDER_GID = "gid://shopify/Order/7373639811379"
SC3058_ORDER_NAME = "#SC3058"
SC3058_LINE_GID = "gid://shopify/LineItem/17476720886067"
MUHAMMAD_ALI_PRODUCT_GID = "gid://shopify/Product/8887274373427"
MUHAMMAD_ALI_VARIANT_GID = "gid://shopify/ProductVariant/48821710029107"
MUHAMMAD_ALI_SKU = "MALIAMOTIVATIONALA4B"

# This is not a title-derived guess.  It is the immutable Shopify chronology
# read from production for the nine units in the explicitly authorised active
# sequence.  The production dry run still verifies paid status, quantity,
# product GID, line identity, active run, and all competing allocations.
SHANE_WARNE_AUTHORISED_SEQUENCE = (
    {
        "order_name": "#SC2964",
        "order_gid": "gid://shopify/Order/7313555456307",
        "line_gid": "gid://shopify/LineItem/17370930610483",
        "edition_number": 1,
    },
    {
        "order_name": "#SC3034",
        "order_gid": "gid://shopify/Order/7360091095347",
        "line_gid": "gid://shopify/LineItem/17451635048755",
        "edition_number": 2,
    },
    {
        "order_name": "#SC3038",
        "order_gid": "gid://shopify/Order/7366416498995",
        "line_gid": "gid://shopify/LineItem/17463561519411",
        "edition_number": 3,
    },
    {
        "order_name": "#SC3041",
        "order_gid": "gid://shopify/Order/7366779830579",
        "line_gid": "gid://shopify/LineItem/17464233689395",
        "edition_number": 4,
    },
    {
        "order_name": "#SC3043",
        "order_gid": "gid://shopify/Order/7367208042803",
        "line_gid": "gid://shopify/LineItem/17464949997875",
        "edition_number": 5,
    },
    {
        "order_name": "#SC3047",
        "order_gid": "gid://shopify/Order/7368742928691",
        "line_gid": "gid://shopify/LineItem/17467698807091",
        "edition_number": 6,
    },
    {
        "order_name": "#SC3050",
        "order_gid": "gid://shopify/Order/7370333913395",
        "line_gid": "gid://shopify/LineItem/17470527865139",
        "edition_number": 7,
    },
    {
        "order_name": "#SC3055",
        "order_gid": "gid://shopify/Order/7372735545651",
        "line_gid": "gid://shopify/LineItem/17475102212403",
        "edition_number": 8,
    },
    {
        "order_name": "#SC3056",
        "order_gid": "gid://shopify/Order/7372755468595",
        "line_gid": "gid://shopify/LineItem/17475132326195",
        "edition_number": 9,
    },
)


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _line_gid(row):
    return edition_ledger.canonical_shopify_gid(
        "LineItem",
        row.get("shopify_line_item_id")
        or row.get("external_line_item_id")
        or row.get("line_gid"),
    )


def _order_gid(row):
    return edition_ledger.canonical_shopify_gid(
        "Order",
        row.get("shopify_order_id")
        or row.get("external_order_id")
        or row.get("order_gid"),
    )


def _product_gid(row):
    return edition_ledger.canonical_shopify_gid(
        "Product",
        row.get("shopify_product_gid") or row.get("shopify_product_id"),
    )


def _eligible_line(order, line):
    reasons = []
    financial = str(order.get("financial_status") or line.get("financial_status") or "").upper()
    if financial != "PAID":
        reasons.append(f"financial_status_{financial.casefold() or 'missing'}")
    if order.get("cancelled_at") or line.get("cancelled_at"):
        reasons.append("cancelled_order")
    if bool(order.get("test") or line.get("test")):
        reasons.append("test_order")
    quantity = int(line.get("quantity") or line.get("line_quantity") or 0)
    if quantity != 1:
        reasons.append(f"quantity_{quantity}_expected_1")
    if _product_gid(line) != SHANE_WARNE_PRODUCT_GID:
        reasons.append("wrong_product_gid")
    return reasons


def build_shane_warne_authorised_plan(snapshot):
    """Build a hash-bound proposal and refuse every unverified assumption.

    A valid plan changes only the exact Shane line IDs above.  Other paid Shane
    allocations are preserved when they belong to a distinct archived run; an
    active/product-wide conflict is a blocker requiring production evidence.
    """

    snapshot = dict(snapshot or {})
    products = list(snapshot.get("edition_products") or [])
    runs = list(snapshot.get("edition_runs") or [])
    allocations = list(snapshot.get("allocations") or [])
    orders = {_order_gid(row): row for row in (snapshot.get("orders") or []) if _order_gid(row)}
    lines = {_line_gid(row): row for row in (snapshot.get("order_lines") or []) if _line_gid(row)}
    active_allocations = [row for row in allocations if row.get("allocation_valid", True)]
    target_by_line = {row["line_gid"]: row for row in SHANE_WARNE_AUTHORISED_SEQUENCE}
    target_lines = set(target_by_line)
    blockers = []
    changes = []
    preserved_outside_active_sequence = []

    matching_products = [row for row in products if _product_gid(row) == SHANE_WARNE_PRODUCT_GID]
    if len(matching_products) != 1:
        blockers.append("The Shane Warne product GID must resolve to exactly one Edition Ops row.")
    product = matching_products[0] if len(matching_products) == 1 else {}
    active_run_id = str(product.get("active_edition_run_id") or "")
    if not active_run_id:
        active_runs = [row for row in runs if str(row.get("status") or "").casefold() == "active"]
        if len(active_runs) == 1:
            active_run_id = str(active_runs[0].get("id") or "")
    if not active_run_id:
        blockers.append("The active Shane Warne edition run could not be identified.")

    allocation_by_line = {}
    for row in allocations:
        line_gid = _line_gid(row)
        if not line_gid:
            continue
        allocation_by_line.setdefault(line_gid, []).append(row)

    desired_numbers = set(range(1, 10))
    for target in SHANE_WARNE_AUTHORISED_SEQUENCE:
        line_gid = target["line_gid"]
        order_gid = target["order_gid"]
        order = orders.get(order_gid) or {}
        line = lines.get(line_gid) or {}
        existing = allocation_by_line.get(line_gid) or []
        if not line and existing:
            line = existing[0]
        if not order and existing:
            order = existing[0]
        if _order_gid(order) != order_gid:
            blockers.append(f"{target['order_name']} is missing its exact Shopify order record.")
        if _line_gid(line) != line_gid:
            blockers.append(f"{target['order_name']} is missing its exact Shane Warne line record.")
        eligibility_reasons = _eligible_line(order, line) if order and line else []
        if eligibility_reasons:
            blockers.append(f"{target['order_name']} is not a verified paid unit: {','.join(eligibility_reasons)}.")
        if len(existing) > 1:
            blockers.append(f"{target['order_name']} has duplicate active allocation rows.")
            continue
        current_number = int(existing[0].get("edition_number") or 0) if existing else None
        if not existing:
            operation = "insert"
        elif not existing[0].get("allocation_valid", True):
            operation = "reactivate_and_renumber"
        elif current_number == target["edition_number"]:
            operation = "no_op"
        else:
            operation = "renumber"
        changes.append(
            {
                "operation": operation,
                "order_name": target["order_name"],
                "order_gid": order_gid,
                "line_gid": line_gid,
                "edition_order_id": str(existing[0].get("id") or "") if existing else "",
                "before_edition_number": current_number,
                "after_edition_number": target["edition_number"],
                "edition_total": 100,
                "active_run_id": active_run_id,
                "certificate_action": "preserve_record_and_regenerate_if_number_changed",
            }
        )

    for row in allocations:
        if _product_gid(row) != SHANE_WARNE_PRODUCT_GID:
            continue
        line_gid = _line_gid(row)
        if line_gid in target_lines:
            continue
        row_run_id = str(row.get("edition_run_id") or "")
        evidence = {
            "edition_order_id": str(row.get("id") or ""),
            "order_name": row.get("shopify_order_name") or "",
            "order_gid": _order_gid(row),
            "line_gid": line_gid,
            "edition_number": row.get("edition_number"),
            "edition_run_id": row_run_id,
            "certificate_status": row.get("certificate_status") or "",
        }
        if not row.get("allocation_valid", True):
            preserved_outside_active_sequence.append(evidence)
        else:
            blockers.append(
                "A valid Shane Warne allocation outside the authorised nine-unit active sequence "
                f"requires review: {evidence['order_name'] or evidence['order_gid'] or evidence['edition_order_id']}."
            )

    # The database uniqueness barrier covers archived/invalid rows too: an
    # edition number is never silently reused.  A wrong source unit occupying a
    # desired number must therefore be reviewed, not ignored.
    for row in allocations:
        if _product_gid(row) != SHANE_WARNE_PRODUCT_GID:
            continue
        number = int(row.get("edition_number") or 0)
        if number not in desired_numbers:
            continue
        line_gid = _line_gid(row)
        expected = target_by_line.get(line_gid)
        if not expected or expected["edition_number"] != number:
            blockers.append(f"Edition #{number:03d} is already held by a different active Shane Warne source unit.")

    michael_rows = [
        row for row in allocations
        if _line_gid(row) == MICHAEL_JORDAN_SC3056_LINE_GID
    ]
    michael_fingerprint = _sha256(michael_rows)
    if snapshot.get("michael_jordan_sc3056_fingerprint") and snapshot["michael_jordan_sc3056_fingerprint"] != michael_fingerprint:
        blockers.append("The #SC3056 Michael Jordan allocation fingerprint is inconsistent.")

    report = {
        "mode": "dry_run",
        "incident": "2026-08-25-shane-warne-authorised-active-sequence",
        "product_gid": SHANE_WARNE_PRODUCT_GID,
        "snapshot_sha256": _sha256(snapshot),
        "active_run_id": active_run_id,
        "apply_blockers": sorted(set(blockers)),
        "changes": changes,
        "preserved_outside_active_sequence": preserved_outside_active_sequence,
        "michael_jordan_sc3056": {
            "line_gid": MICHAEL_JORDAN_SC3056_LINE_GID,
            "row_count": len(michael_rows),
            "fingerprint_sha256": michael_fingerprint,
            "proposed_changes": 0,
        },
        "authoritative_active_state": {
            "edition_total": 100,
            "sold_count": 9,
            "remaining_count": 91,
            "last_assigned_edition": 9,
            "next_edition_number": 10,
            "numbers": list(range(1, 10)),
        },
        "shopify_metafield_plan_after_database_commit": {
            "edition_next_number": 10,
            "edition_sold_count": 9,
            "edition_remaining": 91,
            "next_edition_number": 10,
            "last_assigned_edition": 9,
            "sold_count": 9,
            "remaining_count": 91,
            "is_sold_out": False,
        },
    }
    report["report_sha256"] = _sha256(report)
    return report


def build_sc3058_recovery_plan(order, product_states, *, mapping=None, trace=None):
    """Validate the exact Shopify/eBay order and derive its next ledger number."""

    order = dict(order or {})
    states = dict(product_states or {})
    mapping = list(mapping or [])
    trace = dict(trace or {})
    blockers = []
    order_gid = edition_ledger.canonical_shopify_gid(
        "Order", order.get("shopify_order_id") or order.get("id")
    )
    if order_gid != SC3058_ORDER_GID:
        blockers.append("The immutable Shopify order GID is not #SC3058.")
    order_name = str(order.get("order_name") or order.get("name") or "")
    if order_name != SC3058_ORDER_NAME:
        blockers.append("The Shopify display order name is not #SC3058.")
    if edition_ledger.source_channel_for_order(order) != edition_ledger.SOURCE_CHANNEL_EBAY:
        blockers.append("The order source does not normalize to eBay.")
    policy = edition_ledger.paid_order_eligibility(order)
    if not policy.get("eligible"):
        blockers.append("The order is not allocation-eligible: " + str(policy.get("reason") or "unknown"))
    lines = list(order.get("line_items") or [])
    if len(lines) != 1:
        blockers.append(f"#SC3058 has {len(lines)} line items; exactly one was expected from production evidence.")
    line = lines[0] if len(lines) == 1 else {}
    if _line_gid(line) != SC3058_LINE_GID:
        blockers.append("The immutable Shopify line-item GID does not match #SC3058.")
    if _product_gid(line) != MUHAMMAD_ALI_PRODUCT_GID:
        blockers.append("The #SC3058 line is not the exact Muhammad Ali Shopify product GID.")
    variant_gid = edition_ledger.canonical_shopify_gid(
        "ProductVariant", line.get("shopify_variant_id") or line.get("variant_id")
    )
    if variant_gid != MUHAMMAD_ALI_VARIANT_GID:
        blockers.append("The #SC3058 line is not the exact Muhammad Ali Shopify variant GID.")
    if str(line.get("sku") or "") != MUHAMMAD_ALI_SKU:
        blockers.append("The #SC3058 line SKU does not match the verified Muhammad Ali SKU.")
    if int(line.get("quantity") or 0) != 1:
        blockers.append("#SC3058 quantity is not exactly one.")
    if mapping:
        mapped = mapping[0] if len(mapping) == 1 else {}
        if mapped.get("mapping_status") != "matched":
            blockers.append("The #SC3058 line does not have an exact canonical product match.")
        mapped_gid = edition_ledger.canonical_shopify_gid(
            "Product", mapped.get("mapped_product_gid") or mapped.get("shopify_product_id")
        )
        if mapped_gid and mapped_gid != MUHAMMAD_ALI_PRODUCT_GID:
            blockers.append("The #SC3058 mapping resolves to the wrong product GID.")

    ali = dict(states.get("muhammad_ali") or {})
    numbers = sorted(int(value) for value in (ali.get("valid_numbers") or []) if int(value) > 0)
    if numbers != list(range(1, len(numbers) + 1)):
        blockers.append("Muhammad Ali's valid allocation ledger is not contiguous from #001.")
    next_number = len(numbers) + 1
    if next_number > int(ali.get("edition_total") or 100):
        blockers.append("Muhammad Ali has reached its edition limit.")
    existing = list(trace.get("allocations") or [])
    if existing:
        existing_units = sum(int(row.get("operational_units") or 0) for row in existing)
        if existing_units != 1:
            blockers.append("#SC3058 already has an unexpected allocation-unit count.")
        existing_number = int(existing[0].get("first_edition_number") or 0)
        if existing_number:
            next_number = existing_number

    report = {
        "mode": "dry_run",
        "incident": "2026-08-25-sc3058-ebay-recovery",
        "shopify_order_id": SC3058_ORDER_GID,
        "order_name": SC3058_ORDER_NAME,
        "source_channel": "ebay",
        "source_display": edition_ledger.source_display_name(
            order.get("source_name") or order.get("source_display"),
            tags=order.get("tags") or [],
        ),
        "line_item_id": SC3058_LINE_GID,
        "product_gid": MUHAMMAD_ALI_PRODUCT_GID,
        "variant_gid": MUHAMMAD_ALI_VARIANT_GID,
        "sku": MUHAMMAD_ALI_SKU,
        "quantity": 1,
        "expected_edition_number": next_number,
        "already_stored": bool(trace.get("order_stored")),
        "already_allocated": bool(existing),
        "before_product_states": states,
        "apply_blockers": sorted(set(blockers)),
        "idempotency_identity": {
            "source_channel": "ebay",
            "external_order_id": SC3058_ORDER_GID,
            "external_line_item_id": SC3058_LINE_GID,
            "unit_ordinal": 1,
        },
    }
    report["report_sha256"] = _sha256(report)
    return report
