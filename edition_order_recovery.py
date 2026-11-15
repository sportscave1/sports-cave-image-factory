"""Explicit late-product recovery; previews never allocate or call Shopify."""
from table_design import TABLE_ROW_HEIGHT
import json
import logging
import uuid

import supabase_backend as backend
import edition_ledger

REASON = "Late Edition Ops product mapping/backfill for paid order that arrived before edition product existed"
LOG = logging.getLogger(__name__)


def suffix(value):
    return str(value or "").rsplit("/", 1)[-1]


def validate_mapping(order, line, product, confirmation=""):
    if edition_ledger.source_channel_for_order({**(order.get("raw_json") or {}), **order}) != 'shopify':
        raise ValueError("This recovery action supports Shopify orders only")
    policy = backend.shopify_order_eligibility({**(order.get("raw_json") or {}), **order}, allow_historical=True)
    if not policy.get("eligible"):
        raise ValueError("Order is not eligible: " + str(policy.get("reason") or policy))
    gid = product.get("shopify_product_gid") or product.get("shopify_product_id")
    if not gid or not str(gid).startswith("gid://shopify/Product/"):
        raise ValueError("Product lacks a canonical Shopify identity")
    if line.get("shopify_product_id"):
        if suffix(line["shopify_product_id"]) != suffix(gid):
            raise ValueError("Wrong product: order line Shopify ID differs")
    elif line.get("shopify_handle"):
        if line["shopify_handle"] != product.get("shopify_handle"):
            raise ValueError("Wrong product: order line handle differs")
    elif confirmation != f"{order['order_name']}:{line['shopify_line_item_id']}:{product['id']}":
        raise ValueError("Missing stable product identity; exact admin mapping confirmation required")
    if not 1 <= int(line.get("quantity") or 0) <= 100:
        raise ValueError("Invalid purchased quantity")
    return gid


def load(cur, order_name, line_id, product_id, lock=False):
    ending = " FOR UPDATE" if lock else ""
    cur.execute("SELECT * FROM edition_products WHERE id=%s" + ending, (product_id,))
    product = cur.fetchone()
    cur.execute("SELECT * FROM shopify_orders WHERE order_name=%s" + ending, (order_name,))
    orders = cur.fetchall()
    if not product or len(orders) != 1:
        raise ValueError("Exact product and unique order required")
    order = orders[0]
    cur.execute("SELECT * FROM shopify_order_lines WHERE shopify_order_id=%s AND shopify_line_item_id=%s" + ending,
                (order["shopify_order_id"], line_id))
    lines = cur.fetchall()
    if len(lines) != 1:
        raise ValueError("Exact unique order line required")
    return dict(order), dict(lines[0]), dict(product)


def preview(order_name, line_id, product_id):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        order, line, product = load(cur, order_name, line_id, product_id)
    return {"order": order["order_name"], "line_id": line_id, "line_title": line["product_title"],
            "sku": line.get("sku"), "quantity": line["quantity"], "product_id": product["id"],
            "product": product["product_title"], "handle": product["shopify_handle"],
            "next": product["next_edition_number"], "sold": product["sold_count"],
            "remaining": product["remaining_count"], "confirmation": f"{order_name}:{line_id}:{product_id}"}


def candidates(order_name):
    """Operator-scoped discovery, including lines with no product identity."""
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("""SELECT l.shopify_line_item_id,l.product_title,l.sku,l.quantity,
                       l.shopify_product_id,l.shopify_handle,l.assignment_status
            FROM shopify_order_lines l JOIN shopify_orders o USING(shopify_order_id)
            WHERE o.order_name=%s AND UPPER(o.financial_status)='PAID' AND o.cancelled_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM edition_orders e WHERE e.source_channel='shopify'
                AND e.external_order_id=l.shopify_order_id AND e.external_line_item_id=l.shopify_line_item_id)
            ORDER BY l.shopify_line_item_id""", (order_name,))
        return [dict(row) for row in cur.fetchall()]


def apply(cur, order_name, line_id, product_id, *, confirmation="", expected_next=None):
    # Same lock order as the canonical allocator: advisory product lock, then row.
    cur.execute("SELECT shopify_product_gid FROM edition_products WHERE id=%s", (product_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Edition product does not exist")
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (row["shopify_product_gid"],))
    order, line, product = load(cur, order_name, line_id, product_id, lock=True)
    gid = validate_mapping(order, line, product, confirmation)
    raw = line.get("raw_json") or {}
    variant = line.get("shopify_variant_id") or raw.get("shopify_variant_id") or raw.get("variant_id") or ""
    cur.execute("SELECT * FROM edition_orders WHERE source_channel='shopify' AND external_order_id=%s AND external_line_item_id=%s",
                (order["shopify_order_id"], line_id))
    existing = cur.fetchall()
    if not existing and expected_next is not None and product["next_edition_number"] != expected_next:
        raise ValueError("Next edition changed; preview again before allocating")
    cur.execute("SELECT result FROM allocate_edition_line_units_atomic(" + ",".join(["%s"] * 15) + ") result",
                ("shopify", order["shopify_order_id"], line_id, gid, line["quantity"],
                 order["shopify_order_id"], order_name, line_id, variant, product["product_title"],
                 line.get("variant_title") or "", line.get("sku") or "", order.get("customer_name") or "",
                 order.get("customer_email") or order.get("email") or "", "assigned"))
    results = [r["result"] for r in cur.fetchall()]
    allocations = [r["allocation"] for r in results]
    created = sum(bool(r["was_created"]) for r in results)
    if len(allocations) != line["quantity"]:
        raise ValueError("Incomplete allocation; rolling back")
    action_id = "late-edition-" + str(uuid.uuid4())
    if created:
        backend._set_order_line_status(cur, line_id, "Assigned", shopify_product_id=gid,
                                       shopify_handle=product["shopify_handle"], mapping_method="admin_late_product")
        audit = dict(action_id=action_id, reason=REASON, order=order_name,
                     order_id=order["shopify_order_id"], line_id=line_id, product_id=product_id,
                     handle=product["shopify_handle"], old_state=line["assignment_status"],
                     old_product_id=line.get("shopify_product_id"), mapping_confirmation=confirmation,
                     next_before=product["next_edition_number"], next_after=product["next_edition_number"] + created,
                     sold_before=product["sold_count"], sold_after=product["sold_count"] + created,
                     remaining_before=product["remaining_count"], remaining_after=product["remaining_count"] - created,
                     editions=[a["edition_number"] for a in allocations])
        cur.execute("""INSERT INTO edition_adjustments
            (edition_product_id,edition_run_id,shopify_product_id,shopify_handle,
             old_next_edition_number,new_next_edition_number,old_edition_total,new_edition_total,reason,source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'admin_late_product')""",
            (product_id, product["active_edition_run_id"], gid, product["shopify_handle"],
             product["next_edition_number"], product["next_edition_number"] + created,
             product["edition_total"], product["edition_total"], json.dumps(audit)))
    return dict(allocations=allocations, created=created, handle=product["shopify_handle"], action_id=action_id,
                next_before=product["next_edition_number"], next_after=product["next_edition_number"] + created)


def allocate(order_name, line_id, product_id, **kwargs):
    with backend.connect() as conn:
        try:
            with conn.cursor() as cur:
                result = apply(cur, order_name, line_id, product_id, **kwargs)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    # Normal product mirror owns persistent pending/error status and retries.
    try:
        result["mirror"] = backend.sync_product_edition_metafields_for_handles([result["handle"]], ensure_schema_first=False)
    except Exception:
        LOG.exception("late_edition_mirror_failed order=%s line=%s action=%s", order_name, line_id, result["action_id"])
        result["mirror"] = {"errors": ["Shopify mirror failed; committed allocation retained, retry normal mirror sync."]}
    return result


def render(backend_module, products):
    """Admin-only Edition Ops surface; no allocation until explicit submit."""
    import streamlit as st
    with st.expander("Allocate Existing Unallocated Order", expanded=False):
        order_name = st.text_input("Exact order number", placeholder="#SC3232", key="late-order")
        if st.button("Find unallocated order lines", disabled=not order_name.strip()):
            try:
                found = candidates(order_name.strip())
                if found:
                    st.dataframe(found, hide_index=True, row_height=TABLE_ROW_HEIGHT)
                else:
                    st.info("No paid unallocated lines found for this order.")
            except Exception as exc:
                st.error(str(exc))
        line_id = st.text_input("Exact Shopify line item ID", key="late-line")
        options = {str(p["edition_product_id"]): p for p in products if p.get("edition_product_id")}
        if not options:
            return
        product_id = st.selectbox("Edition Ops product", list(options), format_func=lambda k: options[k]["product_title"], key="late-product")
        if st.button("Preview allocation", disabled=not (order_name and line_id)):
            try:
                st.session_state["late-preview"] = preview(order_name.strip(), line_id.strip(), product_id)
            except Exception as exc:
                st.session_state.pop("late-preview", None)
                st.error(str(exc))
        value = st.session_state.get("late-preview")
        if not value or (value["order"], value["line_id"], str(value["product_id"])) != (order_name.strip(), line_id.strip(), product_id):
            return
        st.write({k: v for k, v in value.items() if k != "confirmation"})
        confirmed = st.checkbox("I verified this exact order line represents the selected artwork", key="late-confirm")
        if st.button("Allocate Existing Unallocated Order", disabled=not confirmed, key="late-apply"):
            try:
                result = allocate(value["order"], value["line_id"], value["product_id"], confirmation=value["confirmation"], expected_next=value["next"])
                from edition_ops import _invalidate_edition_ops_cache
                _invalidate_edition_ops_cache(bump_orders=True)
                st.success("Allocated " + ", ".join(f"#{a['edition_number']}/{a['edition_total']}" for a in result["allocations"]))
                if result["mirror"].get("errors"):
                    st.warning("Allocation saved. Shopify mirror needs retry.")
            except Exception as exc:
                st.error(str(exc))
