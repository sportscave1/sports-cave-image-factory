"""Inspect product subscriptions by default; --apply explicitly creates missing ones."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shopify_sync


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create missing subscriptions; never delete existing ones.")
    parser.add_argument("--receipts", action="store_true", help="Read existing OS product webhook diagnostics without schema maintenance.")
    args = parser.parse_args(argv)
    base_url = os.getenv("SPORTS_CAVE_WEBHOOK_BASE_URL", "").strip().rstrip("/")
    if not base_url.startswith("https://") or "/webhooks/" in base_url:
        raise RuntimeError("Set SPORTS_CAVE_WEBHOOK_BASE_URL to the existing HTTPS webhook service base URL.")
    config = shopify_sync.get_config()
    shopify_sync.validate_config(config)
    for suffix in ("create", "update"):
        callback = getattr(shopify_sync, f"products_{suffix}_webhook_callback_url")(base_url)
        if not callback or not callback.startswith("https://"):
            raise RuntimeError("Set SPORTS_CAVE_WEBHOOK_BASE_URL to the existing HTTPS webhook service.")
        existing = getattr(shopify_sync, f"list_products_{suffix}_webhook_subscriptions")(config=config)
        subscriptions = existing.get("subscriptions") or []
        found = any(shopify_sync._webhook_callback_url(row).rstrip("/") == callback.rstrip("/") for row in subscriptions)
        result = {"topic": f"products/{suffix}", "callback_url": callback, "registered": found, "mode": "apply" if args.apply else "inspect"}
        # Subscriptions are app-scoped. Run with the OS app's configuration,
        # rather than interpreting another connector app's empty list as proof.
        result["visibility"] = "configured_shopify_app_only"
        result["observed_callbacks"] = []
        for row in subscriptions:
            parsed = urlsplit(shopify_sync._webhook_callback_url(row))
            result["observed_callbacks"].append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")))
        if args.apply:
            ensured = getattr(shopify_sync, f"ensure_products_{suffix}_webhook_subscription")(callback_url=callback, config=config)
            result["created"] = bool(ensured.get("created"))
        print(json.dumps(result), flush=True)
    if args.receipts:
        import supabase_backend
        diagnostics = supabase_backend.get_product_sync_diagnostics(ensure_schema_first=False)
        keys = ("last_webhook_event", "last_product_webhook_timestamp",
                "last_product_webhook_status", "last_product_webhook_handle",
                "last_product_webhook_error", "error")
        print(json.dumps({key: diagnostics.get(key) for key in keys}, default=str), flush=True)
        if diagnostics.get("supabase_connected"):
            with supabase_backend.connect() as conn:
                with conn.cursor() as cur:
                    for label, statuses in (("latest_success", ["processed", "success"]),
                                            ("latest_failure", ["failed", "rejected", "error"])):
                        cur.execute("""SELECT topic, webhook_id, status, received_at, processed_at, error_message
                            FROM webhook_events
                            WHERE LOWER(REPLACE(topic, '_', '/')) IN ('products/create', 'products/update')
                              AND LOWER(status) = ANY(%s)
                            ORDER BY received_at DESC LIMIT 1""", (statuses,))
                        print(json.dumps({label: cur.fetchone()}, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
