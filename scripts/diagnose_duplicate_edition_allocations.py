import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

import supabase_backend


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run duplicate edition allocation diagnostics."
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reserved for a separately approved repair. No changes are made by this script today.",
    )
    args = parser.parse_args()

    diagnostics = supabase_backend.edition_allocation_duplicate_diagnostics(limit=args.limit)
    suggestions = []
    for group in diagnostics.get("groups") or []:
        ids = [str(value) for value in group.get("edition_order_ids") or [] if value]
        edition_numbers = group.get("edition_numbers") or []
        suggestions.append(
            {
                "allocation_key": group.get("allocation_key"),
                "order": group.get("shopify_order_name") or group.get("shopify_order_id"),
                "line_item_id": group.get("shopify_line_item_id"),
                "product": group.get("product_title") or group.get("shopify_handle"),
                "variant": group.get("variant_title"),
                "actual_allocation_count": group.get("actual_allocation_count"),
                "expected_quantity": group.get("expected_quantity"),
                "edition_numbers": edition_numbers,
                "keep_candidate": ids[:1],
                "later_duplicate_candidates": ids[1:],
            }
        )

    report = {
        "mode": "dry_run",
        "apply_requested": bool(args.apply),
        "changes_made": False,
        "edition_orders_total": diagnostics.get("edition_orders_total"),
        "duplicate_group_count": diagnostics.get("duplicate_group_count"),
        "duplicate_row_count": diagnostics.get("duplicate_row_count"),
        "suggestions": suggestions,
    }
    if args.apply:
        report["apply_status"] = (
            "No changes made. Apply mode requires a separately reviewed repair implementation."
        )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
