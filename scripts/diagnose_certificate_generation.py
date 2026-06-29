import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import certificate_job
from certificate_logging import certificate_stage_log, set_certificate_log_context


def _print_result(payload):
    print(json.dumps({"event": "certificate_result", **payload}, ensure_ascii=True, default=str), flush=True)


def _clean_order_name(value):
    return str(value or "").strip().replace("#", "").casefold()


def _row_from_database(*, order_name="", edition_order_id=""):
    import supabase_backend

    if not supabase_backend.is_configured():
        raise RuntimeError("Supabase DATABASE_URL is not configured.")
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            if edition_order_id:
                cur.execute(
                    """
                    SELECT eo.id AS edition_order_id,
                           eo.shopify_order_id,
                           COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS order_name,
                           eo.customer_name, eo.customer_email,
                           eo.product_title, eo.shopify_handle, eo.product_handle, eo.variant_title,
                           eo.edition_number, eo.edition_total,
                           eo.shopify_line_item_id, eo.shopify_product_id, eo.shopify_variant_id,
                           eo.allocation_index AS line_item_unit_index,
                           eo.purchase_date AS date,
                           c.local_file_path AS certificate_pdf_path,
                           COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS certificate_pdf_url,
                           c.shopify_file_id AS certificate_shopify_file_id,
                           c.generated_at AS certificate_generated_at
                    FROM edition_orders eo
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                    LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=eo.id::text
                    WHERE eo.id::text=%s
                    ORDER BY c.generated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (str(edition_order_id),),
                )
            else:
                cleaned = _clean_order_name(order_name)
                cur.execute(
                    """
                    SELECT eo.id AS edition_order_id,
                           eo.shopify_order_id,
                           COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, '')) AS order_name,
                           eo.customer_name, eo.customer_email,
                           eo.product_title, eo.shopify_handle, eo.product_handle, eo.variant_title,
                           eo.edition_number, eo.edition_total,
                           eo.shopify_line_item_id, eo.shopify_product_id, eo.shopify_variant_id,
                           eo.allocation_index AS line_item_unit_index,
                           eo.purchase_date AS date,
                           c.local_file_path AS certificate_pdf_path,
                           COALESCE(NULLIF(c.shopify_file_url, ''), NULLIF(c.certificate_file_url, '')) AS certificate_pdf_url,
                           c.shopify_file_id AS certificate_shopify_file_id,
                           c.generated_at AS certificate_generated_at
                    FROM edition_orders eo
                    LEFT JOIN shopify_orders o ON o.shopify_order_id=eo.shopify_order_id
                    LEFT JOIN certificates c ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text)=eo.id::text
                    WHERE REPLACE(LOWER(COALESCE(NULLIF(eo.shopify_order_name, ''), NULLIF(o.order_name, ''), '')), '#', '')=%s
                    ORDER BY COALESCE(eo.purchase_date, eo.assigned_at, eo.created_at) DESC NULLS LAST,
                             c.generated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (cleaned,),
                )
            row = cur.fetchone()
    if not row:
        target = edition_order_id or order_name
        raise ValueError(f"No edition order found for {target}.")
    return {
        **dict(row),
        "order": row.get("order_name") or "",
        "shopify_order_name": row.get("order_name") or "",
        "product": row.get("product_title") or "",
        "product_handle": row.get("product_handle") or row.get("shopify_handle") or "",
        "variant": row.get("variant_title") or "",
    }


def _load_row(args):
    if args.row_json_file:
        with Path(args.row_json_file).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    if args.edition_order_id or args.order_name:
        return _row_from_database(order_name=args.order_name, edition_order_id=args.edition_order_id)
    raise ValueError("Pass --order-name, --edition-order-id, or --row-json-file.")


def _worker_main(args):
    row = _load_row(args)
    source_page = args.source_page or "Diagnostic"
    set_certificate_log_context(
        source_page=source_page,
        order_name=row.get("order") or row.get("order_name") or row.get("shopify_order_name") or args.order_name,
        edition_order_id=row.get("edition_order_id") or args.edition_order_id,
    )
    try:
        result = certificate_job.run_certificate_job(
            row,
            source_page=source_page,
            upload=bool(args.upload),
            force=bool(args.force),
        )
        certificate_stage_log("certificate_action_finished", "completed")
        _print_result(result)
        return 0 if result.get("ok") else 1
    except Exception as error:
        certificate_stage_log("certificate_action_finished", "failed", error=error)
        _print_result(
            {
                "ok": False,
                "error": str(error),
                "order_name": row.get("order") or row.get("order_name") or row.get("shopify_order_name") or args.order_name,
                "edition_order_id": row.get("edition_order_id") or args.edition_order_id,
            }
        )
        return 1


def main():
    parser = argparse.ArgumentParser(description="Diagnose one Sports Cave certificate generation/upload.")
    parser.add_argument("--order-name", default="", help="Order name, for example SC2851 or #SC2851.")
    parser.add_argument("--edition-order-id", default="", help="Supabase edition_orders.id to diagnose.")
    parser.add_argument("--row-json-file", default="", help="Internal worker row payload file.")
    parser.add_argument("--source-page", default="Diagnostic", help="Source label for logs.")
    parser.add_argument("--upload", action="store_true", help="Upload to Shopify Files and save certificate metadata.")
    parser.add_argument("--force", action="store_true", help="Regenerate even when an existing certificate is present.")
    parser.add_argument("--timeout", type=int, default=certificate_job.certificate_job_timeout_seconds())
    parser.add_argument("--as-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.as_worker:
        return _worker_main(args)

    command = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--as-worker",
        "--source-page",
        args.source_page,
        "--timeout",
        str(args.timeout),
    ]
    if args.order_name:
        command.extend(["--order-name", args.order_name])
    if args.edition_order_id:
        command.extend(["--edition-order-id", args.edition_order_id])
    if args.row_json_file:
        command.extend(["--row-json-file", args.row_json_file])
    if args.upload:
        command.append("--upload")
    if args.force:
        command.append("--force")
    result = certificate_job._run_worker_command(
        command,
        timeout_seconds=args.timeout,
        source_page=args.source_page,
        row={"order": args.order_name, "edition_order_id": args.edition_order_id},
    )
    print(json.dumps({"summary": result}, indent=2, ensure_ascii=True, default=str), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
