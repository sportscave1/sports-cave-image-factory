import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
os.environ.setdefault("SUPABASE_STATEMENT_TIMEOUT_MS", "30000")

import shopify_sync
import supabase_backend


def progress(message, **details):
    suffix = ""
    if details:
        suffix = " " + " ".join(
            f"{key}={value}" for key, value in details.items() if value not in (None, "")
        )
    print(f"[edition-metafields] {message}{suffix}", flush=True)


def print_json(payload):
    print(json.dumps(payload, indent=2, default=str), flush=True)


def main():
    progress("script started")
    parser = argparse.ArgumentParser(
        description="Mirror Supabase edition product counters to Shopify product metafields."
    )
    parser.add_argument("--handle", action="append", default=[], help="Retry one product handle. May be repeated.")
    parser.add_argument("--search", default="", help="Optional Supabase product search for full reconciliation.")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum active mapped products to reconcile.")
    args = parser.parse_args()

    config = shopify_sync.get_config()
    if not config.get("configured"):
        print_json(
            {
                "ok": False,
                "error": (
                    "Shopify Admin API is not configured. Add SHOPIFY_CLIENT_ID and "
                    "SHOPIFY_CLIENT_SECRET, or add SHOPIFY_ADMIN_ACCESS_TOKEN."
                ),
                "auth_mode": config.get("auth_mode"),
            }
        )
        return 2
    progress(
        "env checked",
        auth_mode=config.get("auth_mode"),
        has_client_credentials=bool(config.get("client_id") and config.get("client_secret")),
        has_admin_access_token=bool(config.get("access_token")),
        store_domain=config.get("store_domain"),
        api_version=config.get("api_version"),
    )

    try:
        token_details = shopify_sync.get_shopify_access_token_details(config=config, timeout=10)
        progress(
            "Shopify auth checked",
            auth_mode=token_details.get("auth_mode") or config.get("auth_mode"),
            cached=bool(token_details.get("cached")),
        )
        progress("schema check skipped", ensure_schema=False, alter_table=False)

        handles = [str(handle or "").strip() for handle in args.handle if str(handle or "").strip()]
        progress(
            "loading Supabase edition truth",
            mode="handles" if handles else "reconcile",
            count=len(handles) if handles else "",
            search=args.search or "",
            limit=args.limit if not handles else "",
        )
        progress("Shopify lookup started")
        progress("metafields write started")
        if handles:
            result = supabase_backend.sync_product_edition_metafields_for_handles(
                handles,
                config=config,
                ensure_schema_first=False,
                progress_callback=lambda index, total, handle: progress(
                    "metafields write finished",
                    index=index,
                    total=total,
                    handle=handle,
                ),
            )
        else:
            result = supabase_backend.reconcile_shopify_edition_metafields(
                config=config,
                search=args.search,
                limit=args.limit,
                ensure_schema_first=False,
                progress_callback=lambda index, total, handle: progress(
                    "metafields write finished",
                    index=index,
                    total=total,
                    handle=handle,
                ),
            )
        progress("script complete")
        print_json(result)
        return 1 if result.get("errors") else 0
    except Exception as error:
        print_json(
            {
                "ok": False,
                "error_type": error.__class__.__name__,
                "error": str(error),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
