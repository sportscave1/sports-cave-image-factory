"""Register the Shopify ORDERS_PAID webhook for Sports Cave OS."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shopify_sync  # noqa: E402


def _parse_args():
    parser = argparse.ArgumentParser(description="Register the Sports Cave OS ORDERS_PAID webhook.")
    parser.add_argument(
        "--delete-old",
        action="store_true",
        help="Reserved for explicit old webhook cleanup. This script reports old URLs but does not delete by default.",
    )
    return parser.parse_args()


def _print(event, **fields):
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value not in (None, "")})
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def main():
    args = _parse_args()
    _print("script_started", script="register_shopify_orders_paid_webhook")
    try:
        config = shopify_sync.get_config()
        shopify_sync.validate_config(config)
        callback_url = shopify_sync.orders_paid_webhook_callback_url()
        if not callback_url:
            raise shopify_sync.ShopifyConfigurationError(
                "Webhook URL is missing. Set SPORTS_CAVE_WEBHOOK_BASE_URL, SPORTS_CAVE_OS_BASE_URL, "
                "PUBLIC_APP_URL, or RENDER_EXTERNAL_URL."
            )
        _print(
            "env_checked",
            store_domain=config.get("store_domain"),
            api_version=config.get("api_version"),
            auth_mode=config.get("auth_mode"),
            callback_url=callback_url,
            preferred_env="SPORTS_CAVE_WEBHOOK_BASE_URL",
        )
        _print("webhook_subscriptions_list_started", topic="ORDERS_PAID")
        existing = shopify_sync.list_orders_paid_webhook_subscriptions(config=config)
        main_app_url = shopify_sync.orders_paid_webhook_callback_url(shopify_sync.public_app_base_url())
        for subscription in existing.get("subscriptions") or []:
            endpoint = shopify_sync._webhook_callback_url(subscription)
            if (
                endpoint
                and main_app_url
                and endpoint.rstrip("/") == main_app_url.rstrip("/")
                and endpoint.rstrip("/") != callback_url.rstrip("/")
            ):
                _print(
                    "webhook_subscription_points_at_main_app",
                    id=subscription.get("id"),
                    topic=subscription.get("topic"),
                    callback_url=endpoint,
                    action="left_unchanged",
                    delete_old_requested=bool(args.delete_old),
                )
            if endpoint.rstrip("/") == callback_url.rstrip("/"):
                _print(
                    "webhook_subscription_exists",
                    id=subscription.get("id"),
                    topic=subscription.get("topic"),
                    callback_url=endpoint,
                    api_version=existing.get("api_version"),
                )
                _print("script_complete", status="already_registered")
                return 0
        if args.delete_old:
            _print(
                "delete_old_not_performed",
                reason="No automatic deletion is implemented in this safe registration script.",
            )
        _print("webhook_subscription_create_started", topic="ORDERS_PAID", callback_url=callback_url)
        result = shopify_sync.ensure_orders_paid_webhook_subscription(callback_url=callback_url, config=config)
        subscription = result.get("subscription") or {}
        _print(
            "webhook_subscription_create_finished",
            created=bool(result.get("created")),
            id=subscription.get("id"),
            topic=subscription.get("topic"),
            callback_url=shopify_sync._webhook_callback_url(subscription) or result.get("callback_url"),
            api_version=result.get("api_version"),
        )
        _print("script_complete", status="created" if result.get("created") else "already_registered")
        return 0
    except Exception as error:
        _print("script_failed", error_type=error.__class__.__name__, error=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
