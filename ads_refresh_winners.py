"""Read-only synced winner selection; performance is always ad-level."""
from decimal import Decimal, InvalidOperation


def aggregate_ad_roas(rows):
    """Use authoritative purchase value / spend, never average stored ratios."""
    spend = value = Decimal(0)
    complete = True
    for row in rows:
        for field in ("spend", "purchase_value"):
            try:
                number = Decimal(str(row.get(field)))
                if not number.is_finite() or number < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                complete = False
                continue
            if field == "spend":
                spend += number
            else:
                value += number
    return {"spend": spend, "purchase_value": value,
            "roas": value / spend if complete and spend > 0 else None}


def rank_winner_candidates(rows):
    candidates = []
    for row in rows or ():
        if not str(row.get("primary_text") or "").strip() or not str(row.get("headline") or "").strip():
            continue
        metrics = aggregate_ad_roas([row])
        if row.get("metrics_incomplete"):
            metrics["roas"] = None
        candidates.append({**row, **metrics})
    return sorted(candidates, key=lambda row: (
        row["roas"] is None, -(row["roas"] or 0), str(row.get("ad_id") or "")))


def apply_winner_selection(candidate, *, state, identity_key, primary_key, headline_key):
    """Hydrate only on a different explicit selection, preserving manual edits."""
    if not candidate:
        state.pop(identity_key, None)
        return False
    identity = (str(candidate.get("campaign_id")), str(candidate.get("ad_id")))
    if state.get(identity_key) == identity:
        return False
    state[primary_key] = str(candidate.get("primary_text") or "")
    state[headline_key] = str(candidate.get("headline") or "")
    state[identity_key] = identity
    return True
