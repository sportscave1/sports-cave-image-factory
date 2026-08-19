"""Read-only audit of the live Search Console to SEO Overview data path.

Run this from the Render shell with the production environment loaded. The
command never prints OAuth tokens, encryption keys, database credentials or
raw query text.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import google_seo  # noqa: E402
import google_seo_import  # noqa: E402
import run_migrations  # noqa: E402
import seo_live_analytics  # noqa: E402
import seo_reporting_runtime  # noqa: E402


WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
PIPELINE_MIGRATIONS = tuple(google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS)
TABLE_SPECS = {
    "seo_gsc_daily_totals": {
        "date": "date", "property": "gsc_site_url", "search_type": "search_type",
    },
    "seo_gsc_daily_details": {
        "date": "date", "property": "gsc_site_url", "search_type": "search_type",
    },
    "seo_gsc_property_totals_v2": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
    "seo_gsc_query_daily_v2": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
    "seo_gsc_page_daily_v2": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
    "seo_gsc_query_page_daily_v2": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
    "seo_gsc_search_appearance_daily_v2": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
    "seo_gsc_canonical_date_status": {
        "date": "source_date", "property": "property_id", "search_type": "search_type",
        "data_state": "data_state",
    },
}
REPORTING_TABLES = {
    "seo_reporting_daily_metrics": "date",
    "seo_reporting_query_daily": "date",
    "seo_reporting_page_daily": "date",
    "seo_reporting_landing_page_daily": "date",
    "seo_reporting_opportunities": "measurement_date",
}


class ReadOnlyConnectionStore:
    def __init__(self, connection):
        self.connection = dict(connection or {})

    def get_connection_secret(self):
        return dict(self.connection)


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, tuple):
        return list(value)
    return value


def _clean_row(row):
    return {key: _json_value(value) for key, value in dict(row or {}).items()}


def _table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS present", (f"public.{table}",))
    return bool((cur.fetchone() or {}).get("present"))


def _column_exists(cur, table, column):
    cur.execute(
        """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name=%s
        ) AS present
        """,
        (table, column),
    )
    return bool((cur.fetchone() or {}).get("present"))


def _connection_row(cur):
    if not _table_exists(cur, "seo_google_connections"):
        return {}
    cur.execute(
        "SELECT * FROM seo_google_connections WHERE workspace_key=%s",
        (WORKSPACE_KEY,),
    )
    return dict(cur.fetchone() or {})


def _migration_report(cur):
    applied = []
    if _table_exists(cur, "schema_migrations"):
        cur.execute(
            "SELECT filename FROM schema_migrations WHERE filename=ANY(%s) ORDER BY filename",
            (list(PIPELINE_MIGRATIONS),),
        )
        applied = [str(row.get("filename") or "") for row in cur.fetchall() or []]
    effective = {
        google_seo.GOOGLE_SEO_MIGRATION: _table_exists(cur, "seo_google_connections"),
        "20260813_google_seo_phase3_storage.sql": all(
            _table_exists(cur, table)
            for table in ("seo_gsc_daily_totals", "seo_gsc_daily_details", "seo_sync_runs")
        ),
        "20260817_analytics_seo_blog_rebuild.sql": all(
            _table_exists(cur, table)
            for table in (
                "seo_gsc_property_totals_v2", "seo_gsc_query_daily_v2",
                "seo_gsc_page_daily_v2", "seo_gsc_query_page_daily_v2",
            )
        ),
        "20260817_gsc_canonical_pipeline_repair.sql": (
            _table_exists(cur, "seo_gsc_canonical_date_status")
            and _column_exists(cur, "seo_gsc_property_totals_v2", "property_key")
            and _column_exists(cur, "seo_google_connections", "gsc_canonical_revision")
        ),
    }
    return {
        "applied": applied,
        "effective_schema": effective,
        "pending": [name for name in PIPELINE_MIGRATIONS if not effective.get(name)],
        "unrecorded_but_present": [
            name for name in PIPELINE_MIGRATIONS if effective.get(name) and name not in applied
        ],
    }


def _table_report(cur, table, spec):
    if not _table_exists(cur, table):
        return {"exists": False, "rows": 0}
    date_column = spec["date"]
    property_column = spec["property"]
    search_column = spec["search_type"]
    state_column = spec.get("data_state")
    state_select = (
        f", ARRAY_AGG(DISTINCT {state_column} ORDER BY {state_column}) AS data_states"
        if state_column and _column_exists(cur, table, state_column)
        else ""
    )
    key_select = (
        ", ARRAY_AGG(DISTINCT property_key ORDER BY property_key) AS property_keys"
        if _column_exists(cur, table, "property_key")
        else ""
    )
    cur.execute(
        f"""
        SELECT COUNT(*) AS rows, MIN({date_column}) AS earliest_date,
               MAX({date_column}) AS latest_date,
               ARRAY_AGG(DISTINCT {property_column} ORDER BY {property_column}) AS property_ids,
               ARRAY_AGG(DISTINCT {search_column} ORDER BY {search_column}) AS search_types
               {state_select} {key_select}
        FROM {table}
        WHERE workspace_key=%s
        """,
        (WORKSPACE_KEY,),
    )
    return {"exists": True, **_clean_row(cur.fetchone() or {})}


def _saved_range_totals(cur, property_id, start_date, end_date):
    table = "seo_gsc_property_totals_v2"
    if not _table_exists(cur, table):
        return {"available": False, "reason": "canonical_totals_table_missing"}
    has_key = _column_exists(cur, table, "property_key")
    property_key = google_seo.canonical_gsc_property_key(property_id)
    property_sql = "(property_id=%s OR property_key=%s)" if has_key else "property_id=%s"
    params = [WORKSPACE_KEY, property_id]
    if has_key:
        params.append(property_key)
    params.extend([start_date, end_date])
    cur.execute(
        f"""
        SELECT COUNT(*) AS source_dates,
               COALESCE(SUM(clicks), 0) AS clicks,
               COALESCE(SUM(impressions), 0) AS impressions,
               CASE WHEN COALESCE(SUM(impressions), 0)=0 THEN 0
                    ELSE SUM(clicks) / SUM(impressions) END AS ctr,
               CASE WHEN COALESCE(SUM(impressions), 0)=0 THEN 0
                    ELSE SUM(average_position * impressions) / SUM(impressions) END AS average_position,
               ARRAY_AGG(DISTINCT aggregation_type ORDER BY aggregation_type) AS aggregation_types
        FROM {table}
        WHERE workspace_key=%s AND {property_sql}
          AND source_date BETWEEN %s AND %s
          AND search_type='web' AND data_state='final' AND is_complete=TRUE
        """,
        tuple(params),
    )
    return {"available": True, **_clean_row(cur.fetchone() or {})}


def _sync_report(cur, property_id):
    report = {}
    if _table_exists(cur, "seo_sync_runs"):
        cur.execute(
            """
            SELECT status, mode, property_identifier, requested_start_date,
                   requested_end_date, checkpoint_date, latest_stored_data_date,
                   rows_received, rows_inserted, error_code, error_summary,
                   created_at, completed_at
            FROM seo_sync_runs
            WHERE workspace_key=%s AND source='GSC'
            ORDER BY created_at DESC LIMIT 1
            """,
            (WORKSPACE_KEY,),
        )
        report["latest_run"] = _clean_row(cur.fetchone() or {})
    if _table_exists(cur, "seo_gsc_canonical_date_status"):
        key = google_seo.canonical_gsc_property_key(property_id)
        cur.execute(
            """
            SELECT COUNT(*) AS slices,
                   COUNT(*) FILTER (WHERE canonical_complete=TRUE) AS complete_slices,
                   MIN(source_date) AS earliest_date, MAX(source_date) AS latest_date,
                   COALESCE(SUM(property_total_rows), 0) AS property_totals,
                   COALESCE(SUM(query_rows), 0) AS queries,
                   COALESCE(SUM(page_rows), 0) AS pages,
                   COALESCE(SUM(query_page_rows), 0) AS query_pages,
                   COALESCE(SUM(search_appearance_rows), 0) AS search_appearance
            FROM seo_gsc_canonical_date_status
            WHERE workspace_key=%s AND (property_id=%s OR property_key=%s)
              AND data_state='final'
            """,
            (WORKSPACE_KEY, property_id, key),
        )
        report["canonical_manifest"] = _clean_row(cur.fetchone() or {})
    return report


def _compact_reporting_report(cur):
    tables = {}
    for table, date_column in REPORTING_TABLES.items():
        if not _table_exists(cur, table):
            tables[table] = {"exists": False, "rows": 0}
            continue
        cur.execute(
            f"""
            SELECT COUNT(*) AS rows, MIN({date_column}) AS earliest_date,
                   MAX({date_column}) AS latest_date
            FROM {table} WHERE workspace_key=%s
            """,
            (WORKSPACE_KEY,),
        )
        tables[table] = {"exists": True, **_clean_row(cur.fetchone() or {})}
    snapshots = []
    if _table_exists(cur, "seo_reporting_snapshot_runs"):
        optional = {
            column: column if _column_exists(cur, "seo_reporting_snapshot_runs", column)
            else f"NULL AS {column}"
            for column in (
                "gsc_reporting_through_date", "gsc_source_revision",
                "trigger_source", "completed_at",
            )
        }
        cur.execute(
            f"""
            SELECT id, status, common_reporting_date,
                   {optional['gsc_reporting_through_date']},
                   {optional['gsc_source_revision']},
                   {optional['trigger_source']},
                   error_code, error_summary, refreshed_at,
                   {optional['completed_at']}
            FROM seo_reporting_snapshot_runs
            WHERE workspace_key=%s ORDER BY refreshed_at DESC LIMIT 10
            """,
            (WORKSPACE_KEY,),
        )
        snapshots = [_clean_row(row) for row in cur.fetchall() or []]
    return {"tables": tables, "recent_snapshot_runs": snapshots}


def _direct_google_report(connection, start_date, end_date):
    config = google_seo.load_config()
    store = ReadOnlyConnectionStore(connection)
    access_token, secret = google_seo.access_token_for_connection(store, config)
    properties = google_seo.list_gsc_properties(access_token)
    selected = str(secret.get("gsc_site_url") or "")
    match = next(
        (row for row in properties if google_seo.gsc_properties_match(selected, row.get("id"))),
        None,
    )
    if not match:
        raise google_seo.GoogleSEOError(
            "The selected Search Console property is not returned by Google.",
            code="gsc_property_permission_denied",
            stage="gsc_audit",
        )
    exact_site_url = str(match.get("id") or "")
    latest_final_date = google_seo.latest_gsc_data_date(access_token, exact_site_url)
    client = google_seo_import.GoogleSEOReportingClient(access_token)
    totals = client.fetch_gsc_property_totals(
        exact_site_url, start_date, end_date, data_state="final", search_type="web"
    )
    queries = client.fetch_gsc_query_range(
        exact_site_url, start_date, end_date, data_state="final", search_type="web"
    )
    query_probe = google_seo.gsc_search_analytics_request(
        access_token,
        exact_site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=("query",),
        search_type="web",
        data_state="final",
        row_limit=25,
        stage="gsc_audit_query_probe",
    )
    page_probe = google_seo.gsc_search_analytics_request(
        access_token,
        exact_site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=("page",),
        search_type="web",
        data_state="final",
        row_limit=25,
        stage="gsc_audit_page_probe",
    )
    query_page_probe = google_seo.gsc_search_analytics_request(
        access_token,
        exact_site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=("query", "page"),
        search_type="web",
        data_state="final",
        row_limit=25,
        stage="gsc_audit_query_page_probe",
    )
    scopes = list(secret.get("granted_scopes") or [])
    return {
        "refresh_token_exists": bool(secret.get("encrypted_refresh_token")),
        "refresh_exchange_succeeded": True,
        "granted_scopes": scopes,
        "required_readonly_scope_granted": google_seo.GOOGLE_SCOPES[0] in scopes,
        "properties": [
            {"site_url": row.get("id"), "permission_level": row.get("permission_level")}
            for row in properties
        ],
        "selected_property": selected,
        "exact_api_site_url": exact_site_url,
        "selected_permission_level": match.get("permission_level"),
        "latest_final_data_date": latest_final_date,
        "range": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "property_totals": _clean_row(totals),
        "query_row_count": int(queries.get("row_count") or 0),
        "query_pagination_truncated": bool(queries.get("truncated")),
        "query_data_state": queries.get("data_state"),
        "query_search_type": queries.get("search_type"),
        "query_probe_rows": len(query_probe.get("rows") or []),
        "page_probe_rows": len(page_probe.get("rows") or []),
        "query_page_probe_rows": len(query_page_probe.get("rows") or []),
    }


def _reader_report(start_date, end_date):
    reader = seo_reporting_runtime.default_reader()
    context = reader.reporting_context()
    snapshot = reader.overview_base(
        {
            "preset": "Custom range",
            "custom_start": start_date,
            "custom_end": end_date,
            "comparison": "Off",
            "compare": False,
            "search_type": "web",
            "query_class": "All known queries",
            "market": "All markets",
            "device": "All devices",
        },
        context=context,
    )
    current = dict(snapshot.get("current") or {})
    return {
        "context": context,
        "metrics": {
            key: _json_value(current.get(key))
            for key in ("organic_clicks", "organic_impressions", "ctr", "average_position")
        },
        "rank_quality": _json_value((snapshot.get("rank_quality") or {}).get("score")),
        "diagnostics": dict(snapshot.get("diagnostics") or {}),
    }


def _first_divergence(report):
    direct = dict(report.get("direct_google") or {})
    if direct.get("error"):
        return "google_token_property_or_search_analytics_request"
    database = dict(report.get("database") or {})
    migrations = dict(database.get("migrations") or {})
    if migrations.get("pending"):
        return "production_migration"
    tables = dict(database.get("tables") or {})
    legacy_rows = int((tables.get("seo_gsc_daily_details") or {}).get("rows") or 0)
    canonical_rows = int((tables.get("seo_gsc_property_totals_v2") or {}).get("rows") or 0)
    if legacy_rows and not canonical_rows:
        return "legacy_to_canonical_backfill_or_writer"
    saved = dict(database.get("selected_range_totals") or {})
    direct_totals = dict(direct.get("property_totals") or {})
    if direct_totals and (
        Decimal(str(direct_totals.get("clicks") or 0)) != Decimal(str(saved.get("clicks") or 0))
        or Decimal(str(direct_totals.get("impressions") or 0)) != Decimal(str(saved.get("impressions") or 0))
    ):
        return "canonical_property_totals_storage"
    reporting = dict(database.get("compact_reporting") or {})
    completed = [
        row for row in reporting.get("recent_snapshot_runs") or []
        if row.get("status") == "completed"
        and (row.get("gsc_reporting_through_date") or row.get("common_reporting_date"))
    ]
    if saved.get("source_dates") and not completed:
        return "canonical_gsc_to_compact_reporting_snapshot"
    reader = dict(report.get("seo_reader") or {}).get("metrics") or {}
    if saved.get("source_dates") and reader.get("organic_clicks") is None:
        return "canonical_seo_reader_filter_or_cache"
    if direct_totals and reader:
        if (
            Decimal(str(direct_totals.get("clicks") or 0))
            != Decimal(str(reader.get("organic_clicks") or 0))
            or Decimal(str(direct_totals.get("impressions") or 0))
            != Decimal(str(reader.get("organic_impressions") or 0))
        ):
            return "seo_reader_or_rendered_totals"
    return "no_divergence_detected_for_selected_range"


def run_audit(end_date):
    database_url, database_source = run_migrations.get_database_url()
    if not database_url:
        return {
            "ok": False,
            "live_verification": "not_run",
            "reason": (
                "No production database URL is available locally. Run this read-only audit "
                "from the Render shell with the production environment loaded."
            ),
            "render_shell_command": (
                "python scripts/audit_gsc_connection_and_data.py --end-date "
                f"{end_date.isoformat()}"
            ),
        }
    start_date = end_date - timedelta(days=6)
    report = {
        "ok": True,
        "live_verification": "attempted",
        "database_url_source": database_source,
        "workspace_key": WORKSPACE_KEY,
        "range": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    }
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as conn:
        with conn.cursor() as cur:
            connection = _connection_row(cur)
            safe_connection = {
                "refresh_token_exists": bool(connection.get("encrypted_refresh_token")),
                "selected_property": str(connection.get("gsc_site_url") or ""),
                "stored_property_key": str(connection.get("gsc_canonical_property_key") or ""),
                "granted_scopes": list(connection.get("granted_scopes") or []),
                "connection_status": str(connection.get("connection_status") or ""),
                "connection_test_status": str(connection.get("gsc_connection_test_status") or ""),
                "canonical_sync_status": str(connection.get("gsc_canonical_sync_status") or ""),
                "canonical_data_through_date": _json_value(
                    connection.get("gsc_canonical_data_through_date")
                ),
                "canonical_sync_error_code": str(
                    connection.get("gsc_canonical_sync_error_code") or ""
                ),
                "canonical_sync_error_message": str(
                    connection.get("gsc_canonical_sync_error_message") or ""
                ),
                "canonical_revision": int(connection.get("gsc_canonical_revision") or 0),
                "connection_tested_at": _json_value(
                    connection.get("gsc_connection_tested_at")
                ),
                "connection_permission_level": str(
                    connection.get("gsc_connection_permission_level") or ""
                ),
            }
            report["stored_connection"] = safe_connection
            report["database"] = {
                "migrations": _migration_report(cur),
                "tables": {
                    table: _table_report(cur, table, spec)
                    for table, spec in TABLE_SPECS.items()
                },
                "selected_range_totals": _saved_range_totals(
                    cur, safe_connection["selected_property"], start_date, end_date
                ),
                "sync": _sync_report(cur, safe_connection["selected_property"]),
                "compact_reporting": _compact_reporting_report(cur),
            }
    try:
        report["direct_google"] = _direct_google_report(connection, start_date, end_date)
    except Exception as error:
        code = getattr(error, "code", "gsc_audit_failed")
        message = getattr(error, "public_message", "The direct Search Console audit failed.")
        report["direct_google"] = {"error": {"code": str(code), "message": str(message)}}
    try:
        report["seo_reader"] = _reader_report(start_date, end_date)
    except Exception as error:
        report["seo_reader"] = {
            "error": {
                "code": getattr(error, "code", "seo_reader_audit_failed"),
                "message": getattr(error, "public_message", "The SEO reader audit failed."),
            }
        }
    report["first_divergence"] = _first_divergence(report)
    return report


def main(argv=None):
    load_dotenv(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Read-only GSC connection and data-path audit")
    parser.add_argument(
        "--end-date",
        default="2026-08-14",
        help="Finalised inclusive end date for the fixed seven-day audit range (YYYY-MM-DD).",
    )
    args = parser.parse_args(argv)
    try:
        end_date = date.fromisoformat(args.end_date)
    except ValueError as error:
        raise SystemExit("--end-date must use YYYY-MM-DD.") from error
    report = run_audit(end_date)
    print(json.dumps(report, indent=2, sort_keys=True, default=_json_value))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
