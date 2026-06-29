"""List Shopify ORDERS_PAID webhook subscriptions without changing anything."""

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shopify_sync  # noqa: E402


def _print(event, **fields):
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value not in (None, "")})
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def main():
    _print("script_started", script="diagnose_shopify_orders_paid_webhooks")
    try:
        config = shopify_sync.get_config()
        shopify_sync.validate_config(config)
        _print(
            "env_checked",
            store_domain=config.get("store_domain"),
            api_version=config.get("api_version"),
            auth_mode=config.get("auth_mode"),
        )
        result = shopify_sync.list_orders_paid_webhook_subscriptions(config=config)
        subscriptions = result.get("subscriptions") or []
        api_version = result.get("api_version") or config.get("api_version")
        callback_groups = defaultdict(list)

        _print("orders_paid_webhook_subscriptions", count=len(subscriptions), api_version=api_version)
        for subscription in subscriptions:
            callback_url = shopify_sync._webhook_callback_url(subscription)
            if callback_url:
                callback_groups[callback_url.rstrip("/")].append(subscription)
            _print(
                "orders_paid_webhook_subscription",
                id=subscription.get("id"),
                topic=subscription.get("topic"),
                callback_url=callback_url,
                api_version=api_version,
                format=subscription.get("format"),
                created_at=subscription.get("createdAt"),
                updated_at=subscription.get("updatedAt"),
            )

        duplicate_count = 0
        for callback_url, grouped in callback_groups.items():
            if len(grouped) <= 1:
                continue
            duplicate_count += 1
            _print(
                "duplicate_orders_paid_webhook_subscription",
                callback_url=callback_url,
                count=len(grouped),
                ids=[subscription.get("id") for subscription in grouped],
            )

        _print("script_complete", status="ok", duplicate_callback_count=duplicate_count)
        return 0
    except Exception as error:
        _print("script_failed", error_type=error.__class__.__name__, error=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
