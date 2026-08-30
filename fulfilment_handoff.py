"""One-shot Orders-to-Fulfilment navigation state.

The handoff request is UI workflow state only.  Order and fulfilment records
remain owned by their existing data sources and lookup functions.
"""

import re
import uuid


HANDOFF_REQUEST_KEY = "fulfilment_order_handoff_request"
HANDOFF_CONSUMED_REQUEST_KEY = "fulfilment_order_handoff_consumed_request_id"
ORDER_INPUT_KEY = "prodigi-dispatch-order-search"
LEGACY_AUTOLOAD_KEY = "prodigi_dispatch_autoload_query"
FULFILMENT_ROUTE = "Prodigi"

LOOKUP_MATCHES_KEY = "prodigi_dispatch_matches"
LOOKUP_EXISTING_ROWS_KEY = "prodigi_dispatch_existing_rows"
LOOKUP_LAST_QUERY_KEY = "prodigi_dispatch_last_query"
LOOKUP_SELECTED_ROW_KEY = "prodigi_dispatch_selected_row_id"


def canonical_order_reference(value):
    """Return the existing Sports Cave order-reference format when valid."""
    match = re.fullmatch(r"#?SC(\d+)", str(value or "").strip(), flags=re.IGNORECASE)
    return f"#SC{match.group(1)}" if match else ""


def clear_lookup_state(state, *, clear_input=True, clear_request=False):
    """Clear transient Fulfilment search state without touching business data."""
    state[LOOKUP_MATCHES_KEY] = []
    state[LOOKUP_EXISTING_ROWS_KEY] = []
    state[LOOKUP_LAST_QUERY_KEY] = ""
    state[LOOKUP_SELECTED_ROW_KEY] = ""
    state.pop(LEGACY_AUTOLOAD_KEY, None)
    if clear_input:
        state[ORDER_INPUT_KEY] = ""
    if clear_request:
        state.pop(HANDOFF_REQUEST_KEY, None)


def queue_order_handoff(state, order_reference, *, request_id=None):
    """Queue one validated request and navigate to the existing Fulfilment page."""
    target_order = canonical_order_reference(order_reference)
    if not target_order:
        return ""

    clear_lookup_state(state, clear_input=False)
    handoff_id = str(request_id or uuid.uuid4().hex).strip()
    state[HANDOFF_REQUEST_KEY] = {
        "request_id": handoff_id,
        "order_reference": target_order,
    }
    state[ORDER_INPUT_KEY] = target_order
    state["pending_page"] = FULFILMENT_ROUTE
    return target_order


def consume_order_handoff(state):
    """Atomically consume one new request before its lookup is attempted."""
    request = state.pop(HANDOFF_REQUEST_KEY, None)
    state.pop(LEGACY_AUTOLOAD_KEY, None)
    if not isinstance(request, dict):
        return ""

    request_id = str(request.get("request_id") or "").strip()
    target_order = canonical_order_reference(request.get("order_reference"))
    if not request_id or not target_order:
        return ""
    if state.get(HANDOFF_CONSUMED_REQUEST_KEY) == request_id:
        return ""

    # Mark consumed before the existing lookup runs.  A lookup exception can
    # therefore surface normally without leaving a trigger that loops forever.
    state[HANDOFF_CONSUMED_REQUEST_KEY] = request_id
    state[ORDER_INPUT_KEY] = target_order
    return target_order


def is_direct_fulfilment_entry(state):
    """Identify a new non-handoff navigation into the Fulfilment route."""
    transition = state.get("navigation_transition") or {}
    if not isinstance(transition, dict):
        return False
    return (
        transition.get("status") == "pending"
        and transition.get("to") == FULFILMENT_ROUTE
        and transition.get("from") not in (None, "", FULFILMENT_ROUTE)
        and transition.get("source") != "pending"
    )
