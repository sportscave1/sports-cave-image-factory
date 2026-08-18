"""Stable, session-local progressive pagination for compact SEO result pages."""

from __future__ import annotations

import hashlib
import json


def pagination_signature(values):
    """Return a deterministic reset key for filters, sort, source, and page size."""
    payload = json.dumps(values or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def initial_state(signature, page_size=25):
    return {
        "signature": str(signature or ""),
        "page_size": max(1, int(page_size or 25)),
        "rows": [],
        "seen": [],
        "cursor": None,
        "total": 0,
        "complete": False,
    }


def state_for(session_state, key, *, signature, page_size=25):
    state = dict(session_state.get(key) or {})
    if (
        state.get("signature") != signature
        or int(state.get("page_size") or 0) != int(page_size)
    ):
        state = initial_state(signature, page_size)
        session_state[key] = state
    return state


def append_page(state, page, *, identity="query"):
    """Append only unseen rows and retain the server-provided stable cursor."""
    state = dict(state or {})
    rows = list(state.get("rows") or [])
    seen = set(state.get("seen") or [])
    received = list((page or {}).get("rows") or [])
    for row in received:
        row_id = str(row.get(identity) or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        rows.append(dict(row))
    total = max(0, int((page or {}).get("total") or state.get("total") or 0))
    cursor = (page or {}).get("next_cursor")
    state.update(
        rows=rows,
        seen=sorted(seen),
        cursor=cursor,
        total=total,
        complete=not cursor or len(rows) >= total,
    )
    return state


def visible_count_label(state, noun="keywords"):
    state = dict(state or {})
    return f"Showing {len(state.get('rows') or []):,} of {int(state.get('total') or 0):,} {noun}"
