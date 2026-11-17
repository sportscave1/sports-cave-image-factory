"""Read-only server-context access checks. Never creates logs or writes to the DB."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check_shopify():
    import shopify_sync
    from shopify_financial_repair import ACCESS_QUERY
    config = shopify_sync.get_config()
    if not config.get("configured"):
        return {"status": "not_configured", "credential_context": "OS Shopify server integration"}
    try:
        data, served = shopify_sync.graphql_request(ACCESS_QUERY, config=config)
        app = data["currentAppInstallation"]
        scopes = {s["handle"] for s in app["accessScopes"]}
        return {"status": "read_succeeded", "app": app["app"]["title"],
                "read_orders": "read_orders" in scopes, "read_all_orders": "read_all_orders" in scopes,
                "requested_api_version": config["api_version"], "served_api_version": served,
                "credential_context": "OS Shopify server integration"}
    except Exception as error:
        # Do not emit arbitrary exception strings or credential-bearing URLs.
        return {"status": "failed", "error_type": type(error).__name__}


def check_meta():
    import meta_ads_client as meta
    import meta_review_sync
    config = meta.get_meta_config()
    if not config.get("configured"):
        return {"status": "not_configured", "credential_context": "OS Meta server integration"}
    try:
        payload = meta_review_sync.collect_reporting(days=1, config=config)
        return {"status": "read_succeeded", "account_id": payload["account_id"],
                "reporting": payload["reporting"], "daily_rows": len(payload["daily"]),
                "database_writes": 0, "credential_context": "OS Meta server integration"}
    except meta.MetaAdsApiError as error:
        return {"status": "failed", "error_code": error.error_code,
                "http_status": error.status_code, "error_subcode": error.error_subcode,
                "fbtrace_id": error.fbtrace_id,
                "message": meta.sanitize_meta_error(str(error))[:500]}
    except Exception as error:
        return {"status": "failed", "error_type": type(error).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("shopify", "meta", "both"), default="both")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "database_writes": 0}
    for name, check in (("shopify", check_shopify), ("meta", check_meta)):
        if args.provider in ("both", name):
            result[name] = check()
    if args.output:
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(result, target, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
