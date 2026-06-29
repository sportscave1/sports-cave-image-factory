import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

import shopify_sync
import supabase_backend


def main():
    parser = argparse.ArgumentParser(
        description="Mirror Supabase edition product counters to Shopify product metafields."
    )
    parser.add_argument("--handle", action="append", default=[], help="Retry one product handle. May be repeated.")
    parser.add_argument("--search", default="", help="Optional Supabase product search for full reconciliation.")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum active mapped products to reconcile.")
    args = parser.parse_args()

    config = shopify_sync.get_config()
    if not config.get("configured"):
        print(json.dumps({"ok": False, "error": "Shopify Admin API is not configured."}, indent=2))
        return 2

    handles = [str(handle or "").strip() for handle in args.handle if str(handle or "").strip()]
    if handles:
        result = supabase_backend.sync_product_edition_metafields_for_handles(handles, config=config)
    else:
        result = supabase_backend.reconcile_shopify_edition_metafields(
            config=config,
            search=args.search,
            limit=args.limit,
        )

    print(json.dumps(result, indent=2, default=str))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
