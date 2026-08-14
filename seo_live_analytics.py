"""Source-specific, database-only analytics for the SEO Overview.

The reader deliberately does not construct Google, Shopify or OpenAI clients. It
uses compact SQL aggregates over saved reporting tables and the existing Sports
Cave operational Shopify ledger.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import google_seo_phase4


WORKSPACE_KEY = google_seo_phase4.WORKSPACE_KEY
KNOWN_LOCALE_PREFIXES = ("en-au", "en-us", "en-gb", "en-uk", "au", "us", "uk")
MARKET_COUNTRIES = {
    "AU": ("AU",),
    "Australia": ("AU",),
    "US": ("US",),
    "United States": ("US",),
    "UK": ("GB", "UK"),
    "United Kingdom": ("GB", "UK"),
}
MARKET_CURRENCIES = {
    "AU": ("AUD",),
    "Australia": ("AUD",),
    "US": ("USD",),
    "United States": ("USD",),
    "UK": ("GBP",),
    "United Kingdom": ("GBP",),
}


def _decimal(value):
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _iso(value):
    parsed = _as_date(value)
    return parsed.isoformat() if parsed else ""


def weighted_ctr(clicks, impressions):
    impressions = _decimal(impressions)
    if not impressions:
        return Decimal("0")
    return _decimal(clicks) / impressions


def impression_weighted_position(position_weight, impressions):
    impressions = _decimal(impressions)
    if not impressions:
        return Decimal("0")
    return _decimal(position_weight) / impressions


def matching_period(*, preset, through_date, custom_start=None, custom_end=None):
    """Return a source-specific current and previous matching period."""
    through = _as_date(through_date)
    if not through:
        return None
    if str(preset or "") in {"Custom range", "Custom dates"}:
        start = _as_date(custom_start)
        requested_end = _as_date(custom_end)
        if not start or not requested_end:
            return None
        end = min(requested_end, through)
    else:
        days = {
            "Last 28 days": 28,
            "Last 90 days": 90,
            "Last 12 months": 365,
        }.get(str(preset or ""), 28)
        end = through
        start = end - timedelta(days=days - 1)
    if start > end:
        return None
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return {
        "start_date": start,
        "end_date": end,
        "previous_start_date": previous_end - timedelta(days=length - 1),
        "previous_end_date": previous_end,
    }


def _empty_metrics():
    return {
        "store_revenue": None,
        "store_orders": None,
        "store_currency": "",
        "store_by_currency": [],
        "confirmed_organic_revenue": None,
        "organic_orders": None,
        "confirmed_organic_currency": "",
        "ga4_attributed_revenue": None,
        "ga4_attributed_purchases": None,
        "ga4_currency": "",
        "organic_sessions": None,
        "users": None,
        "engaged_sessions": None,
        "engagement_rate": None,
        "add_to_carts": None,
        "begin_checkouts": None,
        "conversion_rate": None,
        "organic_clicks": None,
        "organic_impressions": None,
        "ctr": None,
        "average_position": None,
    }


def _source_status(*, rows, identifier="", run_status=""):
    run_status = str(run_status or "").casefold()
    if _integer(rows) > 0:
        if run_status in {"queued", "running"}:
            return "import_running"
        if run_status in {"partial", "failed"}:
            return "partial_failure"
        return "ready"
    return "no_saved_rows" if identifier else "configuration_required"


def _page_type(path):
    parts = [part for part in str(path or "").strip("/").split("/") if part]
    if not parts:
        return "Home"
    return {
        "products": "Product",
        "collections": "Collection",
        "pages": "Page",
        "blogs": "Article" if len(parts) > 2 else "Blog",
    }.get(parts[0].casefold(), "Page")


class PostgresSEOLiveAnalyticsReader:
    """Read every available source independently from saved Postgres data."""

    def __init__(self, phase4_store=None):
        self.store = phase4_store or google_seo_phase4.default_phase4_store()
        self.read_errors = {}

    def _backend(self):
        return self.store._backend()

    def _query_all(self, source, sql, params=()):
        try:
            with self._backend().connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    return [dict(row) for row in cursor.fetchall() or []]
        except Exception:
            self.read_errors[str(source)] = "saved_data_unavailable"
            return []

    def _query_one(self, source, sql, params=()):
        rows = self._query_all(source, sql, params)
        return rows[0] if rows else {}

    def _selected_properties(self):
        row = self._query_one(
            "connection",
            """
            SELECT gsc_site_url, ga4_property_id
            FROM seo_google_connections
            WHERE workspace_key=%s
            """,
            (WORKSPACE_KEY,),
        )
        gsc = str(row.get("gsc_site_url") or "")
        ga4 = str(row.get("ga4_property_id") or "")
        if not gsc:
            fallback = self._query_one(
                "gsc",
                """
                SELECT gsc_site_url
                FROM seo_gsc_daily_totals
                WHERE workspace_key=%s
                GROUP BY gsc_site_url
                ORDER BY MAX(date) DESC, COUNT(*) DESC
                LIMIT 1
                """,
                (WORKSPACE_KEY,),
            )
            gsc = str(fallback.get("gsc_site_url") or "")
        if not ga4:
            fallback = self._query_one(
                "ga4",
                """
                SELECT ga4_property_id
                FROM seo_ga4_daily_landing_pages
                WHERE workspace_key=%s
                GROUP BY ga4_property_id
                ORDER BY MAX(date) DESC, COUNT(*) DESC
                LIMIT 1
                """,
                (WORKSPACE_KEY,),
            )
            ga4 = str(fallback.get("ga4_property_id") or "")
        return {"gsc": gsc, "ga4": ga4}

    def _latest_import_status(self, source, identifier):
        if not identifier:
            return {}
        return self._query_one(
            str(source).casefold(),
            """
            SELECT status, mode, latest_stored_data_date, completed_end_date,
                   error_code, error_summary, completed_at, updated_at
            FROM seo_sync_runs
            WHERE workspace_key=%s AND source=%s AND property_identifier=%s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (WORKSPACE_KEY, source, identifier),
        )

    def source_health(self):
        properties = self._selected_properties()
        gsc = self._query_one(
            "gsc",
            """
            SELECT MIN(date) AS earliest_date, MAX(date) AS latest_date,
                   (SELECT rows_stored FROM seo_data_inventories
                    WHERE workspace_key=%s AND source='GSC' AND property_identifier=%s) AS inventory_rows,
                   EXISTS(
                       SELECT 1 FROM seo_gsc_daily_details
                       WHERE workspace_key=%s AND gsc_site_url=%s AND is_complete=TRUE
                   ) AS has_detail_rows,
                   (SELECT MIN(date) FROM seo_gsc_daily_details
                    WHERE workspace_key=%s AND gsc_site_url=%s AND is_complete=TRUE) AS detail_earliest_date,
                   (SELECT MAX(date) FROM seo_gsc_daily_details
                    WHERE workspace_key=%s AND gsc_site_url=%s AND is_complete=TRUE) AS detail_latest_date
            FROM seo_gsc_daily_totals
            WHERE workspace_key=%s AND gsc_site_url=%s AND is_complete=TRUE
            """,
            (
                WORKSPACE_KEY, properties["gsc"],
                WORKSPACE_KEY, properties["gsc"],
                WORKSPACE_KEY, properties["gsc"],
                WORKSPACE_KEY, properties["gsc"],
                WORKSPACE_KEY, properties["gsc"],
            ),
        ) if properties["gsc"] else {}
        ga4 = self._query_one(
            "ga4",
            """
            SELECT MIN(date) AS earliest_date, MAX(date) AS latest_date,
                   (SELECT rows_stored FROM seo_data_inventories
                    WHERE workspace_key=%s AND source='GA4' AND property_identifier=%s) AS inventory_rows,
                   EXISTS(
                       SELECT 1 FROM seo_ga4_daily_landing_pages AS saved
                       WHERE saved.workspace_key=%s AND saved.ga4_property_id=%s
                         AND saved.is_complete=TRUE
                   ) AS has_saved_rows
            FROM seo_ga4_daily_landing_pages
            WHERE workspace_key=%s AND ga4_property_id=%s AND is_complete=TRUE
            """,
            (
                WORKSPACE_KEY, properties["ga4"],
                WORKSPACE_KEY, properties["ga4"],
                WORKSPACE_KEY, properties["ga4"],
            ),
        ) if properties["ga4"] else {}
        shopify = self._query_one(
            "shopify",
            """
            SELECT MIN(COALESCE(processed_at, created_at)::date) AS earliest_date,
                   MAX(COALESCE(processed_at, created_at)::date) AS latest_date,
                   COUNT(*) AS total_rows
            FROM shopify_orders
            WHERE cancelled_at IS NULL
              AND LOWER(COALESCE(financial_status, ''))='paid'
            """,
        )
        reconciliation = self._query_one(
            "reconciliation",
            """
            SELECT MIN(date) AS earliest_date, MAX(date) AS latest_date,
                   COALESCE(SUM(source_reconciliation_rows), 0) AS total_rows
            FROM seo_reporting_revenue_daily
            WHERE workspace_key=%s AND source_reconciliation_rows>0
            """,
            (WORKSPACE_KEY,),
        )
        snapshot = self._query_one(
            "snapshot",
            """
            SELECT status, common_reporting_date, refreshed_at, error_code, error_summary
            FROM seo_reporting_snapshot_runs
            WHERE workspace_key=%s
            ORDER BY refreshed_at DESC
            LIMIT 1
            """,
            (WORKSPACE_KEY,),
        )
        pipeline = self._query_one(
            "refresh",
            """
            SELECT status, completed_at, error_code, error_summary
            FROM seo_growth_pipeline_runs
            WHERE workspace_key=%s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (WORKSPACE_KEY,),
        )
        gsc_run = self._latest_import_status("GSC", properties["gsc"])
        ga4_run = self._latest_import_status("GA4", properties["ga4"])
        gsc_rows = _integer(gsc.get("inventory_rows")) or (
            1 if gsc.get("has_detail_rows") or gsc.get("latest_date") else 0
        )
        ga4_rows = _integer(ga4.get("inventory_rows")) or (
            1 if ga4.get("has_saved_rows") or ga4.get("latest_date") else 0
        )
        shopify_rows = _integer(shopify.get("total_rows"))
        reconciliation_rows = _integer(reconciliation.get("total_rows"))
        gsc_dates = [
            value for value in (
                _as_date(gsc.get("earliest_date")),
                _as_date(gsc.get("detail_earliest_date")),
            ) if value
        ]
        gsc_latest_dates = [
            value for value in (
                _as_date(gsc.get("latest_date")),
                _as_date(gsc.get("detail_latest_date")),
            ) if value
        ]
        return {
            "gsc": {
                "available": gsc_rows > 0,
                "status": _source_status(rows=gsc_rows, identifier=properties["gsc"], run_status=gsc_run.get("status")),
                "identifier": properties["gsc"],
                "earliest_date": min(gsc_dates).isoformat() if gsc_dates else "",
                "through_date": max(gsc_latest_dates).isoformat() if gsc_latest_dates else "",
                "rows": gsc_rows,
                "run_status": str(gsc_run.get("status") or "not_started"),
                "error_code": str(gsc_run.get("error_code") or ""),
                "source_label": "Google Search Console",
            },
            "ga4": {
                "available": ga4_rows > 0,
                "status": _source_status(rows=ga4_rows, identifier=properties["ga4"], run_status=ga4_run.get("status")),
                "identifier": properties["ga4"],
                "earliest_date": _iso(ga4.get("earliest_date")),
                "through_date": _iso(ga4.get("latest_date")),
                "rows": ga4_rows,
                "run_status": str(ga4_run.get("status") or "not_started"),
                "error_code": str(ga4_run.get("error_code") or ""),
                "source_label": "Google Analytics 4",
            },
            "shopify": {
                "available": shopify_rows > 0,
                "status": _source_status(rows=shopify_rows, identifier="operational-ledger", run_status="completed"),
                "identifier": "operational-ledger",
                "earliest_date": _iso(shopify.get("earliest_date")),
                "through_date": _iso(shopify.get("latest_date")),
                "rows": shopify_rows,
                "run_status": "saved_operational_data",
                "error_code": "",
                "source_label": "Shopify/Supabase operational data",
            },
            "reconciliation": {
                "available": reconciliation_rows > 0,
                "status": "ready" if reconciliation_rows > 0 else "no_saved_rows",
                "earliest_date": _iso(reconciliation.get("earliest_date")),
                "through_date": _iso(reconciliation.get("latest_date")),
                "rows": reconciliation_rows,
                "source_label": "Shopify-confirmed organic reconciliation",
            },
            "snapshot": {
                "available": str(snapshot.get("status") or "") == "completed",
                "status": str(snapshot.get("status") or "not_refreshed"),
                "through_date": _iso(snapshot.get("common_reporting_date")),
                "refreshed_at": str(snapshot.get("refreshed_at") or ""),
                "error_code": str(snapshot.get("error_code") or ""),
            },
            "refresh": {
                "status": str(pipeline.get("status") or "not_started"),
                "completed_at": str(pipeline.get("completed_at") or ""),
                "error_code": str(pipeline.get("error_code") or ""),
                "error_summary": str(pipeline.get("error_summary") or ""),
            },
        }

    @staticmethod
    def _detail_scope(market, device, *, country_column="country_code", device_column="device"):
        clauses = []
        params = []
        countries = MARKET_COUNTRIES.get(str(market or ""), ())
        if countries:
            clauses.append(f"UPPER({country_column})=ANY(%s)")
            params.append(list(countries))
        if str(device or "") != "All devices":
            clauses.append(f"UPPER({device_column})=%s")
            params.append(str(device).upper())
        return clauses, params

    def _gsc_where(self, identifier, period, market, device):
        clauses = ["workspace_key=%s", "gsc_site_url=%s", "date BETWEEN %s AND %s", "is_complete=TRUE"]
        params = [WORKSPACE_KEY, identifier, period["start_date"], period["end_date"]]
        scope, scope_params = self._detail_scope(market, device)
        return [*clauses, *scope], [*params, *scope_params]

    @staticmethod
    def _aggregate_gsc(rows):
        if not rows:
            return {
                "organic_clicks": None, "organic_impressions": None,
                "ctr": None, "average_position": None,
            }
        clicks = sum((_decimal(row.get("clicks")) for row in rows), Decimal("0"))
        impressions = sum((_decimal(row.get("impressions")) for row in rows), Decimal("0"))
        weight = sum((_decimal(row.get("position_weight")) for row in rows), Decimal("0"))
        return {
            "organic_clicks": clicks,
            "organic_impressions": impressions,
            "ctr": weighted_ctr(clicks, impressions),
            "average_position": impression_weighted_position(weight, impressions),
        }

    def _gsc_daily(self, identifier, period, market, device):
        scope, scope_params = self._detail_scope(market, device)
        use_totals = not scope
        if use_totals:
            sql = """
                SELECT date, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       SUM(average_position * impressions) AS position_weight,
                       COUNT(*) AS source_rows
                FROM seo_gsc_daily_totals
                WHERE workspace_key=%s AND gsc_site_url=%s
                  AND date BETWEEN %s AND %s AND is_complete=TRUE
                GROUP BY date ORDER BY date
            """
            params = (WORKSPACE_KEY, identifier, period["previous_start_date"], period["end_date"])
        else:
            sql = f"""
                SELECT date, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       SUM(average_position * impressions) AS position_weight,
                       COUNT(*) AS source_rows
                FROM seo_gsc_daily_details
                WHERE workspace_key=%s AND gsc_site_url=%s
                  AND date BETWEEN %s AND %s AND is_complete=TRUE
                  AND {' AND '.join(scope)}
                GROUP BY date ORDER BY date
            """
            params = [WORKSPACE_KEY, identifier, period["previous_start_date"], period["end_date"], *scope_params]
        return self._query_all("gsc", sql, params)

    def _gsc_top_queries(self, identifier, current_period, previous_period, market, device, limit=20):
        current_where, current_params = self._gsc_where(identifier, current_period, market, device)
        previous_where, previous_params = self._gsc_where(identifier, previous_period, market, device)
        return self._query_all(
            "gsc",
            f"""
            WITH current_metrics AS (
                SELECT query, UPPER(country_code) AS country_code, UPPER(device) AS device,
                       SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       SUM(average_position * impressions) AS position_weight
                FROM seo_gsc_daily_details
                WHERE {' AND '.join(current_where)} AND query<>''
                GROUP BY query, UPPER(country_code), UPPER(device)
            ), previous_metrics AS (
                SELECT query, UPPER(country_code) AS country_code, UPPER(device) AS device,
                       SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       SUM(average_position * impressions) AS position_weight
                FROM seo_gsc_daily_details
                WHERE {' AND '.join(previous_where)} AND query<>''
                GROUP BY query, UPPER(country_code), UPPER(device)
            )
            SELECT current_metrics.query, current_metrics.country_code, current_metrics.device,
                   current_metrics.clicks, current_metrics.impressions,
                   current_metrics.position_weight,
                   COALESCE(previous_metrics.clicks, 0) AS previous_clicks,
                   COALESCE(previous_metrics.impressions, 0) AS previous_impressions,
                   COALESCE(previous_metrics.position_weight, 0) AS previous_position_weight
            FROM current_metrics
            LEFT JOIN previous_metrics USING (query, country_code, device)
            ORDER BY current_metrics.clicks DESC, current_metrics.impressions DESC
            LIMIT %s
            """,
            [*current_params, *previous_params, int(limit)],
        )

    def _gsc_top_pages(self, identifier, current_period, previous_period, market, device, limit=30):
        current_where, current_params = self._gsc_where(identifier, current_period, market, device)
        previous_where, previous_params = self._gsc_where(identifier, previous_period, market, device)
        return self._query_all(
            "gsc",
            f"""
            WITH current_metrics AS (
                SELECT page_url, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                       SUM(average_position * impressions) AS position_weight
                FROM seo_gsc_daily_details
                WHERE {' AND '.join(current_where)} AND page_url<>''
                GROUP BY page_url
            ), previous_metrics AS (
                SELECT page_url, SUM(clicks) AS clicks
                FROM seo_gsc_daily_details
                WHERE {' AND '.join(previous_where)} AND page_url<>''
                GROUP BY page_url
            )
            SELECT current_metrics.*,
                   COALESCE(previous_metrics.clicks, 0) AS previous_clicks
            FROM current_metrics
            LEFT JOIN previous_metrics USING (page_url)
            ORDER BY current_metrics.clicks DESC, current_metrics.impressions DESC
            LIMIT %s
            """,
            [*current_params, *previous_params, int(limit)],
        )

    def _gsc_breakdowns(self, identifier, period, market, device):
        clauses, params = self._gsc_where(identifier, period, market, device)
        return self._query_all(
            "gsc",
            f"""
            SELECT UPPER(country_code) AS country_code, UPPER(device) AS device,
                   SUM(clicks) AS clicks, SUM(impressions) AS impressions
            FROM seo_gsc_daily_details
            WHERE {' AND '.join(clauses)}
            GROUP BY UPPER(country_code), UPPER(device)
            """,
            params,
        )

    def _gsc_bundle(self, health, period, market, device, compare):
        previous = {
            "start_date": period["previous_start_date"],
            "end_date": period["previous_end_date"],
        }
        rows = self._gsc_daily(health["identifier"], period, market, device)
        current_rows = [row for row in rows if period["start_date"] <= _as_date(row.get("date")) <= period["end_date"]]
        previous_rows = [
            row for row in rows
            if period["previous_start_date"] <= _as_date(row.get("date")) <= period["previous_end_date"]
        ] if compare else []
        daily = []
        previous_daily = []
        for row in current_rows:
            metrics = self._aggregate_gsc([row])
            daily.append({"date": _iso(row.get("date")), **metrics})
        for row in previous_rows:
            metrics = self._aggregate_gsc([row])
            previous_daily.append({"date": _iso(row.get("date")), **metrics})
        top_queries = self._gsc_top_queries(health["identifier"], period, previous, market, device)
        queries = []
        for row in top_queries:
            impressions = _decimal(row.get("impressions"))
            previous_impressions = _decimal(row.get("previous_impressions"))
            position = impression_weighted_position(row.get("position_weight"), impressions)
            previous_position = (
                impression_weighted_position(row.get("previous_position_weight"), previous_impressions)
                if previous_impressions else None
            )
            queries.append({
                **row,
                "ctr": weighted_ctr(row.get("clicks"), impressions),
                "average_position": position,
                "previous_position": previous_position,
                "click_change": _decimal(row.get("clicks")) - _decimal(row.get("previous_clicks")),
                "ranking_change": (previous_position - position) if previous_position is not None else None,
                "market": "UK" if row.get("country_code") == "GB" else (row.get("country_code") or "Other"),
            })
        return {
            "current": self._aggregate_gsc(current_rows),
            "previous": self._aggregate_gsc(previous_rows) if compare else {},
            "daily": daily,
            "previous_daily": previous_daily,
            "top_queries": queries,
            "top_pages": self._gsc_top_pages(health["identifier"], period, previous, market, device),
            "breakdowns": self._gsc_breakdowns(health["identifier"], period, market, device),
        }

    def _ga4_where(self, identifier, period, market, device):
        clauses = ["workspace_key=%s", "ga4_property_id=%s", "date BETWEEN %s AND %s", "is_complete=TRUE"]
        params = [WORKSPACE_KEY, identifier, period["start_date"], period["end_date"]]
        scope, scope_params = self._detail_scope(
            market, device, country_column="country_id", device_column="device_category",
        )
        return [*clauses, *scope], [*params, *scope_params]

    @staticmethod
    def _aggregate_ga4(rows):
        if not rows:
            return {
                "organic_sessions": None, "engaged_sessions": None,
                "engagement_rate": None, "ga4_attributed_purchases": None,
                "ga4_attributed_revenue": None, "ga4_currency": "",
                "conversion_rate": None,
            }
        sessions = sum((_decimal(row.get("sessions")) for row in rows), Decimal("0"))
        engaged = sum((_decimal(row.get("engaged_sessions")) for row in rows), Decimal("0"))
        transactions = sum((_decimal(row.get("transactions")) for row in rows), Decimal("0"))
        currencies = sorted({
            str(row.get("property_currency") or "").upper()
            for row in rows if row.get("property_currency")
        })
        revenue = (
            sum((_decimal(row.get("purchase_revenue")) for row in rows), Decimal("0"))
            if len(currencies) <= 1 else None
        )
        return {
            "organic_sessions": sessions,
            "engaged_sessions": engaged,
            "engagement_rate": engaged / sessions if sessions else Decimal("0"),
            "ga4_attributed_purchases": transactions,
            "ga4_attributed_revenue": revenue,
            "ga4_currency": currencies[0] if len(currencies) == 1 else "",
            "conversion_rate": transactions / sessions if sessions else Decimal("0"),
        }

    def _ga4_daily(self, identifier, period, market, device):
        span = {"start_date": period["previous_start_date"], "end_date": period["end_date"]}
        clauses, params = self._ga4_where(identifier, span, market, device)
        return self._query_all(
            "ga4",
            f"""
            SELECT date, property_currency,
                   SUM(sessions) AS sessions,
                   SUM(engaged_sessions) AS engaged_sessions,
                   SUM(transactions) AS transactions,
                   SUM(purchase_revenue) AS purchase_revenue,
                   COUNT(*) AS source_rows
            FROM seo_ga4_daily_landing_pages
            WHERE {' AND '.join(clauses)}
            GROUP BY date, property_currency
            ORDER BY date, property_currency
            """,
            params,
        )

    def _ga4_top_pages(self, identifier, current_period, previous_period, market, device, limit=30):
        current_where, current_params = self._ga4_where(identifier, current_period, market, device)
        previous_where, previous_params = self._ga4_where(identifier, previous_period, market, device)
        return self._query_all(
            "ga4",
            f"""
            WITH current_metrics AS (
                SELECT landing_page_path_query,
                       SUM(sessions) AS sessions,
                       SUM(engaged_sessions) AS engaged_sessions,
                       SUM(transactions) AS attributed_purchases,
                       SUM(purchase_revenue) AS attributed_revenue,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT property_currency), '') AS currencies
                FROM seo_ga4_daily_landing_pages
                WHERE {' AND '.join(current_where)} AND landing_page_path_query<>''
                GROUP BY landing_page_path_query
            ), previous_metrics AS (
                SELECT landing_page_path_query, SUM(sessions) AS sessions
                FROM seo_ga4_daily_landing_pages
                WHERE {' AND '.join(previous_where)} AND landing_page_path_query<>''
                GROUP BY landing_page_path_query
            )
            SELECT current_metrics.*,
                   COALESCE(previous_metrics.sessions, 0) AS previous_sessions
            FROM current_metrics
            LEFT JOIN previous_metrics USING (landing_page_path_query)
            ORDER BY current_metrics.sessions DESC, current_metrics.engaged_sessions DESC
            LIMIT %s
            """,
            [*current_params, *previous_params, int(limit)],
        )

    def _ga4_breakdowns(self, identifier, period, market, device):
        clauses, params = self._ga4_where(identifier, period, market, device)
        return self._query_all(
            "ga4",
            f"""
            SELECT UPPER(country_id) AS country_code, UPPER(device_category) AS device,
                   SUM(sessions) AS sessions, SUM(engaged_sessions) AS engaged_sessions
            FROM seo_ga4_daily_landing_pages
            WHERE {' AND '.join(clauses)}
            GROUP BY UPPER(country_id), UPPER(device_category)
            """,
            params,
        )

    def _ga4_bundle(self, health, period, market, device, compare):
        previous = {
            "start_date": period["previous_start_date"],
            "end_date": period["previous_end_date"],
        }
        rows = self._ga4_daily(health["identifier"], period, market, device)
        current_rows = [row for row in rows if period["start_date"] <= _as_date(row.get("date")) <= period["end_date"]]
        previous_rows = [
            row for row in rows
            if period["previous_start_date"] <= _as_date(row.get("date")) <= period["previous_end_date"]
        ] if compare else []
        daily = self._daily_groups(current_rows, self._aggregate_ga4)
        previous_daily = self._daily_groups(previous_rows, self._aggregate_ga4)
        return {
            "current": self._aggregate_ga4(current_rows),
            "previous": self._aggregate_ga4(previous_rows) if compare else {},
            "daily": daily,
            "previous_daily": previous_daily,
            "top_pages": self._ga4_top_pages(health["identifier"], period, previous, market, device),
            "breakdowns": self._ga4_breakdowns(health["identifier"], period, market, device),
        }

    @staticmethod
    def _aggregate_shopify(rows):
        if not rows:
            return {
                "store_orders": None, "store_revenue": None,
                "store_currency": "", "store_by_currency": [],
            }
        by_currency = {}
        for row in rows:
            currency = str(row.get("currency") or "").upper()
            bucket = by_currency.setdefault(currency, {"currency": currency, "orders": 0, "revenue": Decimal("0")})
            bucket["orders"] += _integer(row.get("orders"))
            bucket["revenue"] += _decimal(row.get("revenue"))
        values = list(by_currency.values())
        currencies = [row["currency"] for row in values if row["currency"]]
        return {
            "store_orders": sum((row["orders"] for row in values), 0),
            "store_revenue": sum((row["revenue"] for row in values), Decimal("0")) if len(currencies) <= 1 else None,
            "store_currency": currencies[0] if len(currencies) == 1 else "",
            "store_by_currency": values,
        }

    @staticmethod
    def _daily_groups(rows, aggregate):
        grouped = {}
        for row in rows or []:
            grouped.setdefault(_iso(row.get("date")), []).append(row)
        return [
            {"date": day, **aggregate(grouped[day])}
            for day in sorted(grouped)
        ]

    def _shopify_daily(self, period, market, device):
        if str(device or "") != "All devices":
            return []
        clauses = [
            "COALESCE(processed_at, created_at)::date BETWEEN %s AND %s",
            "cancelled_at IS NULL",
            "LOWER(COALESCE(financial_status, ''))='paid'",
        ]
        params = [period["previous_start_date"], period["end_date"]]
        currencies = MARKET_CURRENCIES.get(str(market or ""), ())
        if currencies:
            clauses.append("UPPER(currency)=ANY(%s)")
            params.append(list(currencies))
        return self._query_all(
            "shopify",
            f"""
            SELECT COALESCE(processed_at, created_at)::date AS date,
                   UPPER(COALESCE(currency, '')) AS currency,
                   COUNT(*) AS orders,
                   COALESCE(SUM(
                       CASE WHEN COALESCE(total_price, '') ~ '^[0-9]+([.][0-9]+)?$'
                            THEN total_price::numeric ELSE 0 END
                   ), 0) AS revenue
            FROM shopify_orders
            WHERE {' AND '.join(clauses)}
            GROUP BY COALESCE(processed_at, created_at)::date, UPPER(COALESCE(currency, ''))
            ORDER BY date, currency
            """,
            params,
        )

    def _shopify_bundle(self, period, market, device, compare):
        rows = self._shopify_daily(period, market, device)
        current_rows = [row for row in rows if period["start_date"] <= _as_date(row.get("date")) <= period["end_date"]]
        previous_rows = [
            row for row in rows
            if period["previous_start_date"] <= _as_date(row.get("date")) <= period["previous_end_date"]
        ] if compare else []
        return {
            "current": self._aggregate_shopify(current_rows),
            "previous": self._aggregate_shopify(previous_rows) if compare else {},
            "daily": self._daily_groups(current_rows, self._aggregate_shopify),
            "previous_daily": self._daily_groups(previous_rows, self._aggregate_shopify),
        }

    def _reconciliation_bundle(self, period, market, device, compare):
        if str(device or "") != "All devices":
            return {"current": {}, "previous": {}}
        clauses = ["workspace_key=%s", "date BETWEEN %s AND %s", "source_reconciliation_rows>0"]
        params = [WORKSPACE_KEY, period["previous_start_date"], period["end_date"]]
        countries = MARKET_COUNTRIES.get(str(market or ""), ())
        if countries:
            clauses.append("UPPER(country_code)=ANY(%s)")
            params.append(list(countries))
        rows = self._query_all(
            "reconciliation",
            f"""
            SELECT date, UPPER(currency) AS currency,
                   SUM(confirmed_organic_orders) AS orders,
                   SUM(confirmed_organic_revenue) AS revenue,
                   SUM(source_reconciliation_rows) AS source_rows
            FROM seo_reporting_revenue_daily
            WHERE {' AND '.join(clauses)}
            GROUP BY date, UPPER(currency)
            ORDER BY date, currency
            """,
            params,
        )

        def aggregate(selected):
            if not selected:
                return {}
            currencies = sorted({str(row.get("currency") or "") for row in selected if row.get("currency")})
            return {
                "organic_orders": sum((_decimal(row.get("orders")) for row in selected), Decimal("0")),
                "confirmed_organic_revenue": (
                    sum((_decimal(row.get("revenue")) for row in selected), Decimal("0"))
                    if len(currencies) <= 1 else None
                ),
                "confirmed_organic_currency": currencies[0] if len(currencies) == 1 else "",
            }

        current_rows = [row for row in rows if period["start_date"] <= _as_date(row.get("date")) <= period["end_date"]]
        previous_rows = [
            row for row in rows
            if period["previous_start_date"] <= _as_date(row.get("date")) <= period["previous_end_date"]
        ] if compare else []
        return {"current": aggregate(current_rows), "previous": aggregate(previous_rows)}

    @staticmethod
    def _primary_host(gsc_identifier):
        try:
            return str(urlsplit(str(gsc_identifier or "")).hostname or "")
        except ValueError:
            return ""

    @staticmethod
    def _page_key(raw_url, primary_host):
        normalized = google_seo_phase4.normalize_seo_url(
            raw_url,
            primary_host=primary_host,
            known_locale_prefixes=KNOWN_LOCALE_PREFIXES,
        )
        return normalized.get("canonical_path") or normalized.get("normalized_path") or str(raw_url or "")

    def _canonical_metadata(self, paths):
        paths = sorted({str(path or "") for path in paths if path})
        if not paths:
            return {}
        rows = self._query_all(
            "mapping",
            """
            SELECT normalized_path, canonical_url, title, page_type
            FROM seo_canonical_pages
            WHERE workspace_key=%s AND normalized_path=ANY(%s)
            """,
            (WORKSPACE_KEY, paths),
        )
        return {str(row.get("normalized_path") or ""): row for row in rows}

    def _merge_top_pages(self, gsc_rows, ga4_rows, primary_host):
        merged = {}
        for row in gsc_rows or []:
            key = self._page_key(row.get("page_url"), primary_host)
            target = merged.setdefault(key, {"path": key})
            impressions = _decimal(row.get("impressions"))
            target.update({
                "clicks": _decimal(row.get("clicks")),
                "impressions": impressions,
                "average_position": impression_weighted_position(row.get("position_weight"), impressions),
                "previous_clicks": _decimal(row.get("previous_clicks")),
            })
        for row in ga4_rows or []:
            key = self._page_key(row.get("landing_page_path_query"), primary_host)
            target = merged.setdefault(key, {"path": key})
            sessions = _decimal(row.get("sessions"))
            engaged = _decimal(row.get("engaged_sessions"))
            currencies = list(row.get("currencies") or [])
            target.update({
                "sessions": sessions,
                "engaged_sessions": engaged,
                "engagement_rate": engaged / sessions if sessions else Decimal("0"),
                "attributed_purchases": _decimal(row.get("attributed_purchases")),
                "attributed_revenue": _decimal(row.get("attributed_revenue")) if len(currencies) <= 1 else None,
                "currencies": currencies,
                "previous_sessions": _decimal(row.get("previous_sessions")),
            })
        metadata = self._canonical_metadata(merged)
        result = []
        for path, row in merged.items():
            saved = metadata.get(path, {})
            previous_basis = (
                row.get("previous_sessions")
                if row.get("sessions") is not None else row.get("previous_clicks")
            )
            current_basis = row.get("sessions") if row.get("sessions") is not None else row.get("clicks")
            row.update({
                "canonical_url": saved.get("canonical_url") or path,
                "title": saved.get("title") or path,
                "page_type": str(saved.get("page_type") or _page_type(path)).title(),
                "previous_change": (
                    _decimal(current_basis) - _decimal(previous_basis)
                    if current_basis is not None else None
                ),
                "confirmed_orders": None,
                "confirmed_revenue": None,
            })
            result.append(row)
        return sorted(
            result,
            key=lambda row: (
                _decimal(row.get("sessions")),
                _decimal(row.get("clicks")),
                _decimal(row.get("impressions")),
            ),
            reverse=True,
        )[:25]

    @staticmethod
    def _merge_breakdowns(gsc_rows, ga4_rows):
        country_buckets = {
            key: {
                "market": key,
                "gsc_clicks": Decimal("0"),
                "gsc_impressions": Decimal("0"),
                "ga4_sessions": Decimal("0"),
            }
            for key in ("AU", "US", "UK", "Other")
        }
        device_buckets = {
            key: {
                "device": key,
                "gsc_clicks": Decimal("0"),
                "gsc_impressions": Decimal("0"),
                "ga4_sessions": Decimal("0"),
            }
            for key in ("Desktop", "Mobile", "Tablet")
        }

        def country_key(value):
            value = str(value or "").upper()
            if value == "AU":
                return "AU"
            if value == "US":
                return "US"
            if value in {"GB", "UK"}:
                return "UK"
            return "Other"

        def device_key(value):
            value = str(value or "").title()
            return value if value in device_buckets else ""

        for row in gsc_rows or []:
            country = country_buckets[country_key(row.get("country_code"))]
            country["gsc_clicks"] += _decimal(row.get("clicks"))
            country["gsc_impressions"] += _decimal(row.get("impressions"))
            device = device_buckets.get(device_key(row.get("device")))
            if device:
                device["gsc_clicks"] += _decimal(row.get("clicks"))
                device["gsc_impressions"] += _decimal(row.get("impressions"))
        for row in ga4_rows or []:
            country_buckets[country_key(row.get("country_code"))]["ga4_sessions"] += _decimal(row.get("sessions"))
            device = device_buckets.get(device_key(row.get("device")))
            if device:
                device["ga4_sessions"] += _decimal(row.get("sessions"))
        return list(country_buckets.values()), list(device_buckets.values())

    @staticmethod
    def _combine_daily(*bundles, key):
        merged = {}
        for bundle in bundles:
            for row in (bundle or {}).get(key) or []:
                target = merged.setdefault(str(row.get("date") or ""), {"date": str(row.get("date") or "")})
                target.update({field: value for field, value in row.items() if field != "date"})
        return [merged[item] for item in sorted(merged)]

    def snapshot(
        self,
        *,
        preset="Last 28 days",
        market="All markets",
        device="All devices",
        compare=True,
        custom_start=None,
        custom_end=None,
        search=None,
        source_health=None,
    ):
        del search
        self.read_errors = {}
        health = dict(source_health or self.source_health())
        current = _empty_metrics()
        previous = _empty_metrics()
        periods = {}
        bundles = {}
        for source in ("gsc", "ga4", "shopify", "reconciliation"):
            source_health = health.get(source) or {}
            periods[source] = matching_period(
                preset=preset,
                through_date=source_health.get("through_date"),
                custom_start=custom_start,
                custom_end=custom_end,
            )
        if health["gsc"]["available"] and periods["gsc"]:
            bundles["gsc"] = self._gsc_bundle(health["gsc"], periods["gsc"], market, device, compare)
            current.update(bundles["gsc"]["current"])
            previous.update(bundles["gsc"]["previous"])
        if health["ga4"]["available"] and periods["ga4"]:
            bundles["ga4"] = self._ga4_bundle(health["ga4"], periods["ga4"], market, device, compare)
            current.update(bundles["ga4"]["current"])
            previous.update(bundles["ga4"]["previous"])
        if health["shopify"]["available"] and periods["shopify"] and str(device) == "All devices":
            bundles["shopify"] = self._shopify_bundle(periods["shopify"], market, device, compare)
            current.update(bundles["shopify"]["current"])
            previous.update(bundles["shopify"]["previous"])
        if health["reconciliation"]["available"] and periods["reconciliation"] and str(device) == "All devices":
            bundles["reconciliation"] = self._reconciliation_bundle(periods["reconciliation"], market, device, compare)
            current.update(bundles["reconciliation"]["current"])
            previous.update(bundles["reconciliation"]["previous"])

        primary_host = self._primary_host(health["gsc"].get("identifier"))
        top_pages = self._merge_top_pages(
            (bundles.get("gsc") or {}).get("top_pages"),
            (bundles.get("ga4") or {}).get("top_pages"),
            primary_host,
        )
        countries, devices = self._merge_breakdowns(
            (bundles.get("gsc") or {}).get("breakdowns"),
            (bundles.get("ga4") or {}).get("breakdowns"),
        )
        daily = self._combine_daily(
            bundles.get("gsc"), bundles.get("ga4"), bundles.get("shopify"), key="daily",
        )
        previous_daily = self._combine_daily(
            bundles.get("gsc"), bundles.get("ga4"), bundles.get("shopify"), key="previous_daily",
        ) if compare else []
        ready = any((health[source].get("available") for source in ("gsc", "ga4", "shopify")))
        raw_fallback = not bool((health.get("snapshot") or {}).get("available"))
        stale = str((health.get("refresh") or {}).get("status") or "") in {"partial", "failed"}
        return {
            "ready": ready,
            "reason": "" if ready else "no_saved_source_rows",
            "health": health,
            "filters": {
                "preset": preset,
                "market": market,
                "device": device,
                "compare": bool(compare),
                "custom_start": _iso(custom_start),
                "custom_end": _iso(custom_end),
            },
            "source_periods": {
                source: {key: _iso(value) for key, value in (period or {}).items()}
                for source, period in periods.items()
            },
            "current": current,
            "previous": previous,
            "daily_trend": daily,
            "previous_daily_trend": previous_daily,
            "top_pages": top_pages,
            "top_queries": (bundles.get("gsc") or {}).get("top_queries") or [],
            "countries": countries,
            "devices": devices,
            "fallback_mode": raw_fallback,
            "stale": stale,
            "read_errors": dict(self.read_errors),
        }


def default_reader():
    return PostgresSEOLiveAnalyticsReader()
