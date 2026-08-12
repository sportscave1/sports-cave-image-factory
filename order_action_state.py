"""Shared completion and notification rules for synced Sports Cave orders."""

from __future__ import annotations

from datetime import datetime, timezone


PAID_ORDER_STATUSES = frozenset({"paid", "partially paid", "partially_paid"})
CERTIFICATE_TERMINAL_STATUSES = frozenset({"uploaded", "complete", "completed"})
FULFILMENT_TERMINAL_STATUSES = frozenset(
    {"complete", "completed", "fulfilled", "fulfilled in shopify"}
)


def canonical_status(value):
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def stable_order_id(row):
    row = {} if row is None else row
    return str(
        row.get("shopify_order_id")
        or row.get("order_id")
        or row.get("order")
        or row.get("order_name")
        or ""
    ).strip()


def order_is_relevant(row):
    row = {} if row is None else row
    status = canonical_status(row.get("financial_status") or "paid")
    cancelled = str(row.get("cancelled_at") or "").strip()
    return status in PAID_ORDER_STATUSES and not cancelled


def certificate_step_is_complete(row):
    row = {} if row is None else row
    if any(
        str(row.get(key) or "").strip()
        for key in (
            "certificate_pdf_url",
            "shopify_file_url",
            "certificate_file_url",
            "certificate_shopify_file_id",
            "shopify_file_id",
            "shopify_pdf_file_id",
        )
    ):
        return True
    return canonical_status(
        row.get("certificate_status") or row.get("certificate")
    ) in CERTIFICATE_TERMINAL_STATUSES


def fulfilment_step_is_complete(row):
    row = {} if row is None else row
    dispatch_status = row.get("prodigi_status") or row.get("prodigi")
    if str(dispatch_status or "").strip():
        return canonical_status(dispatch_status) in FULFILMENT_TERMINAL_STATUSES
    order_status = row.get("fulfillment_status") or row.get("fulfilment_status")
    return canonical_status(order_status) in FULFILMENT_TERMINAL_STATUSES


def row_requires_action(row):
    row = {} if row is None else row
    if not order_is_relevant(row):
        return False
    try:
        required_units = max(int(row.get("line_quantity") or 1), 1)
    except (TypeError, ValueError):
        required_units = 1
    try:
        assigned_units = int(
            row.get("assignments_count")
            if row.get("assignments_count") is not None
            else (1 if row.get("edition_order_id") else 0)
        )
    except (TypeError, ValueError):
        assigned_units = 0
    if assigned_units < required_units:
        return True
    return not (
        certificate_step_is_complete(row)
        and fulfilment_step_is_complete(row)
    )


def order_ids_requiring_action(rows):
    action_ids = set()
    for row in rows or ():
        order_id = stable_order_id(row)
        if order_id and row_requires_action(row):
            action_ids.add(order_id)
    return action_ids


def count_orders_requiring_action(rows):
    return len(order_ids_requiring_action(rows))


def badge_label(count):
    value = max(int(count or 0), 0)
    if value <= 0:
        return ""
    return "99+" if value > 99 else str(value)


def _event_marker(event):
    processed_at = event.get("processed_at") or event.get("received_at") or ""
    if isinstance(processed_at, datetime):
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=timezone.utc)
        processed_at = processed_at.astimezone(timezone.utc).isoformat()
    return f"{processed_at}|{str(event.get('webhook_id') or '').strip()}"


def select_new_order_events(events, *, after_marker="", seen_order_ids=()):
    """Return unseen eligible events, deduplicated by stable Shopify order ID."""
    seen_ids = {str(value or "").strip() for value in seen_order_ids if str(value or "").strip()}
    eligible = []
    for raw in events or ():
        event = dict(raw or {})
        order_id = stable_order_id(event)
        marker = _event_marker(event)
        if not order_id or order_id in seen_ids or not event.get("new_order_inserted"):
            continue
        if after_marker and marker <= after_marker:
            continue
        eligible.append((marker, event))
    eligible.sort(key=lambda item: item[0])
    selected_by_order = {}
    for marker, event in eligible:
        selected_by_order.setdefault(stable_order_id(event), (marker, event))
    selected = [item[1] for item in selected_by_order.values()]
    selected.sort(key=_event_marker)
    newest_marker = eligible[-1][0] if eligible else str(after_marker or "")
    return selected, newest_marker


def new_order_notification(events):
    source = list(events or ())
    if not source:
        return {}
    if len(source) == 1:
        order_name = str(source[0].get("shopify_order_name") or "").strip()
        message = f"New order received — {order_name}" if order_name else "New order received"
    else:
        message = f"{len(source)} new orders received"
    return {
        "count": len(source),
        "message": message,
        "route_key": "orders",
        "shopify_order_ids": [stable_order_id(event) for event in source],
    }
