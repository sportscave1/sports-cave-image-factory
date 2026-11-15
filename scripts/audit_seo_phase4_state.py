from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supabase_backend


WORKSPACE_KEY = "sports-cave"


TABLE_DATE_COLUMNS = {
    "seo_gsc_daily_totals": "date",
    "seo_gsc_daily_details": "date",
    "seo_ga4_daily_landing_pages": "date",
    "seo_ga4_transactions": "transaction_date",
    "seo_shopify_order_facts": "order_date",
    "seo_revenue_reconciliations": "transaction_date",
    "seo_canonical_pages": None,
    "seo_url_aliases": None,
    "seo_phase4_health": None,
    "seo_phase4_runs": None,
    "seo_phase4_source_state": None,
    "seo_data_inventories": None,
    "seo_sync_runs": None,
    "shopify_products": None,
    "shopify_orders": None,
}


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _print_rows(label, rows):
    print(f"\n## {label}")
    if not rows:
        print("(none)")
        return
    for row in rows:
        print(json.dumps(dict(row), sort_keys=True, default=_json_default))


def _table_exists(cursor, table_name):
    cursor.execute(
        "SELECT to_regclass(%s) IS NOT NULL AS exists",
        (f"public.{table_name}",),
    )
    return bool((cursor.fetchone() or {}).get("exists"))


def main():
    load_dotenv()
    print("DB source:", supabase_backend.get_database_url_source() or "missing")
    print("DB host:", supabase_backend.safe_database_reference())
    try:
        connection_context = supabase_backend.connect()
    except supabase_backend.SupabaseNotConfigured as error:
        print("Audit unavailable:", str(error))
        return 2
    with connection_context as connection:
        with connection.cursor() as cursor:
            if _table_exists(cursor, "schema_migrations"):
                cursor.execute(
                    """
                    SELECT filename, applied_at
                    FROM schema_migrations
                    WHERE filename LIKE %s OR filename LIKE %s
                    ORDER BY filename
                    """,
                    ("20260813_google_seo%", "20260812_seo%"),
                )
                _print_rows("SEO migration records", cursor.fetchall() or [])
            else:
                _print_rows("SEO migration records", [])

            cursor.execute(
                """
                SELECT connection_status, reconnect_required,
                       LENGTH(COALESCE(gsc_site_url, '')) > 0 AS has_gsc_site,
                       LENGTH(COALESCE(ga4_property_id, '')) > 0 AS has_ga4_property,
                       gsc_data_through_date, ga4_data_through_date,
                       shopify_data_through_date, gsc_import_status,
                       ga4_import_status, phase4_last_mapping_at,
                       phase4_last_reconciliation_at, phase4_error_code,
                       phase4_error_summary
                FROM seo_google_connections
                WHERE workspace_key=%s
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Connection/reporting fields", cursor.fetchall() or [])

            for table_name, date_column in TABLE_DATE_COLUMNS.items():
                if not _table_exists(cursor, table_name):
                    _print_rows(f"{table_name} count", [{"exists": False}])
                    continue
                if date_column:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) AS rows,
                               MIN({date_column}) AS earliest_date,
                               MAX({date_column}) AS latest_date
                        FROM {table_name}
                        """
                    )
                else:
                    cursor.execute(f"SELECT COUNT(*) AS rows FROM {table_name}")
                _print_rows(f"{table_name} count", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT source,
                       LENGTH(COALESCE(property_identifier, '')) > 0 AS has_property_identifier,
                       rows_stored, earliest_stored_date, latest_stored_date,
                       updated_at
                FROM seo_data_inventories
                WHERE workspace_key=%s AND source IN ('GSC', 'GA4')
                ORDER BY source
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Data inventories", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT DISTINCT ON (source)
                       source, mode, status, requested_start_date,
                       requested_end_date, completed_start_date,
                       completed_end_date, checkpoint_date,
                       latest_stored_data_date, active_slice_date,
                       rows_received, rows_inserted, rows_replaced,
                       rows_rejected, completed_at, error_code,
                       error_summary
                FROM seo_sync_runs
                WHERE workspace_key=%s AND source IN ('GSC', 'GA4')
                ORDER BY source, created_at DESC
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Latest Phase 3 sync runs", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT source, resource_type,
                       LENGTH(COALESCE(checkpoint_value, '')) > 0 AS has_checkpoint_value,
                       latest_completed_date, status, last_success_at,
                       error_code, error_summary
                FROM seo_phase4_source_state
                WHERE workspace_key=%s
                ORDER BY source, resource_type
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Phase 4 source state", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT DISTINCT ON (source)
                       source, mode, status, requested_start_date,
                       requested_end_date, checkpoint_date, rows_received,
                       rows_written, rows_rejected, completed_at,
                       error_code, error_summary
                FROM seo_phase4_runs
                WHERE workspace_key=%s
                ORDER BY source, created_at DESC
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Latest Phase 4 runs", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT source, mapping_status, COUNT(*) AS rows
                FROM seo_url_aliases
                WHERE workspace_key=%s
                GROUP BY source, mapping_status
                ORDER BY source, mapping_status
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("URL alias mapping counts", cursor.fetchall() or [])

            cursor.execute(
                """
                SELECT reconciliation_state, COUNT(*) AS rows,
                       COALESCE(SUM(shopify_confirmed_revenue), 0) AS confirmed_revenue
                FROM seo_revenue_reconciliations
                WHERE workspace_key=%s
                GROUP BY reconciliation_state
                ORDER BY reconciliation_state
                """,
                (WORKSPACE_KEY,),
            )
            _print_rows("Revenue reconciliation counts", cursor.fetchall() or [])

            cursor.execute(
                "SELECT * FROM seo_phase4_health WHERE workspace_key=%s",
                (WORKSPACE_KEY,),
            )
            _print_rows("Phase 4 health", cursor.fetchall() or [])


if __name__ == "__main__":
    raise SystemExit(main())
