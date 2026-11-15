"""Read-only edition conflict diagnosis. Does not run DDL or contact Shopify."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import supabase_backend as backend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search", nargs="*", default=["Jack Brabham", "Sam Kerr", "Shane Warne"])
    args = parser.parse_args()
    if not backend.is_configured():
        parser.exit(2, "Database is not configured; no records inspected or changed.\n")
    fields = (
        "shopify_handle", "product_title", "active_edition_run_id", "edition_run_id",
        "run_status", "next_edition_number", "run_next_edition_number", "sold_count",
        "last_assigned_edition", "allocation_baseline_sold_count", "allocation_blocked",
        "allocation_integrity_issue", "metafields_sync_status", "last_metafield_error",
    )
    for search in args.search:
        rows = backend.list_edition_products_read_only(search=search, limit=50)
        print(json.dumps({"search": search, "products": [
            {key: row.get(key) for key in fields} for row in rows
        ]}, default=str))


if __name__ == "__main__":
    main()
