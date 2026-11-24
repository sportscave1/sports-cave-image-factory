"""Explicit-order, assets-only repair. Dry-run by default; never allocates or replaces PDFs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import certificate_engine as engine
import shopify_sync


def repair_orders(order_ids, *, apply=False):
    config = shopify_sync.get_config()
    results = []
    for order_id in order_ids:
        state = engine.read_order_certificate_state(order_id, config=config)
        for certificate in state.get("certificates") or []:
            if not engine._certificate_has_pdf(certificate):
                continue
            record = dict(certificate)
            record["order_name"] = record.get("order_name") or record.get("shopify_order_name")
            record["handle"] = record.get("handle") or record.get("product_handle")
            record["edition_total"] = record.get("edition_total") or record.get("edition_limit")
            result = {"order": record["order_name"], "certificate_id": record.get("certificate_id"),
                      "edition": record.get("edition_number"), "missing": engine._certificate_missing_customer_assets(record)}
            if apply:
                repaired = engine.ensure_certificate_customer_assets(record, config=config, require_complete=False)
                saved = engine.save_certificate_record_to_order(repaired, config=config, ensure_schema_first=False)
                if not saved.get("metafields_synced") or repaired.get("asset_sync_status") != "ready":
                    raise RuntimeError(saved.get("metafield_error") or repaired.get("asset_sync_error") or "Repair incomplete")
                # Read back both authoritative metafields through the normal reader.
                fresh = engine.read_order_certificate_state(order_id, config=config)
                verified = engine.find_existing_certificate(fresh.get("certificates"), record)
                if engine._certificate_missing_customer_assets(verified) or not engine._certificate_has_pdf(verified):
                    raise RuntimeError("Account asset readback failed")
                if (verified.get("certificate_pdf_url") or verified.get("pdf_url")) != (record.get("certificate_pdf_url") or record.get("pdf_url")):
                    raise RuntimeError("Issued PDF changed unexpectedly")
                result["verified"] = True
            results.append(result)
            print(json.dumps(result), flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repair_orders(args.order_id, apply=args.apply)
