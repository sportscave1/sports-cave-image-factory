"""Preview missing ACTIVE collector products; --apply registers only missing rows.

Uses existing OS Shopify/Supabase configuration. No schema setup or backfills.
Default mode opens a READ ONLY transaction. Run --apply only after reviewing it.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shopify_sync
import supabase_backend as backend


def preview(config=None):
    catalogue = shopify_sync.fetch_edition_ops_active_products(max_products=None, config=config)
    if not catalogue.get("complete"):
        raise RuntimeError("Shopify catalogue scan is incomplete; reconciliation refused.")
    # Never use a creation-time watermark: activation can happen months later.
    products = [shopify_sync.fetch_product_by_shopify_id(p["shopify_product_id"], config=config)
                for p in catalogue.get("products") or []]
    report, candidates = [], []
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT * FROM edition_products")
            existing = list(cur.fetchall())
            for product in products:
                decision = shopify_sync.edition_registration_eligibility(product)
                row = {"product_id": product["shopify_product_id"], "handle": product.get("handle"),
                       "status": product.get("status"), "action": "skipped", "reason": decision["reason"]}
                if decision["eligible"]:
                    action = backend._plan_edition_product_incremental_sync([product], existing)[0]
                    if action["action"] == "error":
                        row.update(action="review_required", reason=action.get("error"))
                    elif action["action"] == "insert":
                        try:
                            backend._assert_new_edition_product_safe(cur, action["fields"])
                        except RuntimeError as error:
                            row.update(action="review_required", reason=str(error))
                        else:
                            row.update(action="would_create", reason="eligible_missing_product")
                            candidates.append(product)
                    elif (action.get("existing") or {}).get("metafields_sync_status") == "Pending automatic mirror":
                        row.update(action="would_resume_initial_mirror", reason="unfinished_new_registration")
                        candidates.append(product)
                    else:
                        row.update(reason="existing_edition_preserved")
                report.append(row)
    return report, candidates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Register previewed missing products and resume unfinished initial mirrors.")
    args = parser.parse_args(argv)
    config = shopify_sync.get_config()
    shopify_sync.validate_config(config)
    report, candidates = preview(config)
    for row in report:
        print(json.dumps(row), flush=True)
    if args.apply:
        for candidate in candidates:
            # Refetch again after preview; final identity/history checks run under
            # the existing transaction lock. A racing webhook wins harmlessly.
            backend.register_shopify_products_for_edition_ops(
                [{"shopify_product_id": candidate["shopify_product_id"]}],
                source="missing_product_reconciliation", config=config, missing_only=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
