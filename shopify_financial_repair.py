"""Read-only financial recovery planning. Deliberately contains no apply handler."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from shopify_order_financials import money_pair

FINANCIAL_QUERY = """
query SportsCaveFinancialRead($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on Order {
      id
      updatedAt
      processedAt
      totalPriceSet { shopMoney { amount currencyCode } }
    }
  }
}
"""
ACCESS_QUERY = """
query SportsCaveOrderReadAccess {
  currentAppInstallation { app { title } accessScopes { handle } }
}
"""

LEDGER_QUERY = """
SELECT shopify_order_id,total_price,currency,remote_updated_at,processed_at,synced_at,updated_at,
    raw_json->'total_price' AS raw_json_amount,raw_json->'currency' AS raw_json_currency,
    raw->'total_price' AS raw_amount,raw->'currency' AS raw_currency,
    md5((to_jsonb(o) - ARRAY['total_price','currency','raw_json','raw','updated_at']
        || jsonb_build_object('raw_json',coalesce(raw_json,'{}'::jsonb)-'total_price'-'currency',
                              'raw',coalesce(raw,'{}'::jsonb)-'total_price'-'currency'))::text) AS protected_hash
FROM shopify_orders o WHERE shopify_order_id=ANY(%s) ORDER BY shopify_order_id
"""


def validate_ids(ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids):
        raise ValueError("Supply 1–50 unique explicit order IDs.")
    if any(not re.fullmatch(r"gid://shopify/Order/[0-9]+", str(value)) for value in ids):
        raise ValueError("Only immutable Shopify Order GIDs are supported.")
    return sorted(ids)


def capture_ledger(connection, ids):
    ids = validate_ids(ids)
    connection.execute("SET TRANSACTION READ ONLY")
    connection.execute("SET LOCAL statement_timeout='8000ms'")
    return connection.execute(LEDGER_QUERY, (ids,)).fetchall()


def capture_provider(ids, *, config=None):
    import shopify_sync
    data, served = shopify_sync.graphql_request(FINANCIAL_QUERY, {"ids": validate_ids(ids)}, config=config)
    return {"rows": data["nodes"], "captured_at": datetime.now(timezone.utc).isoformat(),
            "served_api_version": served, "credential_context": "OS Shopify server integration"}


def timestamp(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamps must include a timezone.")
    return parsed


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def preview(ids, ledger, provider):
    ids = validate_ids(ids)
    timestamp(ledger["captured_at"])
    timestamp(provider["captured_at"])
    local = {str(row["shopify_order_id"]): row for row in ledger["rows"]}
    remote = {str(row["id"]): row for row in provider["rows"] if row}
    if (len(local) != len(ledger["rows"]) or len(remote) != len(provider["rows"])
            or set(local) != set(ids) or set(remote) != set(ids)):
        raise ValueError("Incomplete, duplicate or unexpected source IDs; no repair is prepared.")
    changes = []
    for identifier in ids:
        row, source = local[identifier], remote[identifier]
        money = (source.get("totalPriceSet") or {}).get("shopMoney") or {}
        pair = money_pair(money.get("amount"), money.get("currencyCode"))
        if pair is None:
            raise ValueError("Provider financial pair is incomplete or invalid.")
        source_updated = timestamp(source["updatedAt"])
        existing = money_pair(row.get("total_price"), row.get("currency"))
        state = "proposed"
        if row.get("remote_updated_at") and source_updated < timestamp(row["remote_updated_at"]):
            state = "blocked_stale_provider"
        elif existing:
            state = "already_matches" if (Decimal(existing[0]) == Decimal(pair[0]) and existing[1] == pair[1]) else "blocked_existing_financial_conflict"
        elif str(row.get("currency") or "").strip() and row["currency"] != pair[1]:
            state = "blocked_existing_currency_conflict"
        elif row.get("total_price") is not None and str(row["total_price"]).strip():
            observed = money_pair(row["total_price"], pair[1])
            if observed is None or Decimal(observed[0]) != Decimal(pair[0]):
                state = "blocked_existing_amount_conflict"
        if not row.get("protected_hash"):
            raise ValueError("Protected-field fingerprint is required.")
        changes.append({"shopify_order_id": identifier, "status": state,
            "before": {key: row.get(key) for key in ("total_price", "currency", "raw_json_amount",
                       "raw_json_currency", "raw_amount", "raw_currency")},
            "proposed_after": {"total_price": pair[0], "currency": pair[1]},
            "source_times": {"provider_updated_at": source["updatedAt"],
                            "provider_processed_at": source["processedAt"],
                            "ledger_remote_updated_at": row.get("remote_updated_at"),
                            "ledger_synced_at": row.get("synced_at"), "ledger_updated_at": row.get("updated_at")},
            "protected_hash": row["protected_hash"]})
    return {"schema": 1, "mode": "dry_run_only", "apply_supported": False,
        "production_authorized": False, "operation_hash": digest(changes), "changes": changes,
        "ledger_captured_at": ledger["captured_at"], "provider_captured_at": provider["captured_at"],
        "credential_context": provider.get("credential_context", "unspecified"),
        "served_api_version": provider.get("served_api_version"),
        "permitted_future_fields": ["total_price", "currency", "raw_json.total_price", "raw_json.currency",
                                    "raw.total_price", "raw.currency", "updated_at"],
        "protected": ["edition allocations/counters", "fulfilment", "refund/workflow/shipping overrides",
                      "order lines", "customers", "all other fields"],
        "requires": ["Fresh before-images and provider reads immediately before apply",
                     "Exact manifest and release approval", "Conditional transaction and durable audit",
                     "A separately reviewed apply handler; this module cannot write"]}
