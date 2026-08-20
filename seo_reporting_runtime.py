"""Fast, database-only SEO read model for interactive Streamlit rendering.

Compact ``seo_reporting_*`` rows are preferred. When that cache is missing or
stale, the reader performs bounded, database-side aggregation over the saved
canonical GSC v2 rows for the requested period. It never calls Google, refreshes
a snapshot, or reads the large legacy GSC detail history during page rendering.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import logging
import time

import google_seo
import seo_live_analytics


WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
MARKET_CODES = {
    "Australia": "AU",
    "United States": "US",
    "United Kingdom": "UK",
    "Canada": "CA",
    "New Zealand": "NZ",
}
MARKET_COUNTRIES = {
    "Australia": ("AU", "AUS"),
    "United States": ("US", "USA"),
    "United Kingdom": ("GB", "GBR", "UK"),
    "Canada": ("CA", "CAN"),
    "New Zealand": ("NZ", "NZL"),
}


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None


def _empty_metrics():
    return {
        "organic_clicks": None,
        "organic_impressions": None,
        "ctr": None,
        "average_position": None,
    }


class PostgresSEOInteractiveReader:
    """Read compact reporting rows with one connection per logical operation."""

    def __init__(self, backend=None):
        self.backend = backend
        self.reset_diagnostics()

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend

        return supabase_backend

    def reset_diagnostics(self):
        self.diagnostics = {
            "query_count": 0,
            "query_ms": 0.0,
            "rows_returned": 0,
            "queries": [],
            "raw_fallback": False,
            "raw_fallback_ms": 0.0,
            "canonical_fallback": False,
        }

    def _execute(self, cursor, name, sql, params=(), *, one=False):
        started = time.perf_counter()
        cursor.execute(sql, params)
        if one:
            value = dict(cursor.fetchone() or {})
            count = int(bool(value))
        else:
            value = [dict(row) for row in cursor.fetchall() or []]
            count = len(value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.diagnostics["query_count"] += 1
        self.diagnostics["query_ms"] += elapsed_ms
        self.diagnostics["rows_returned"] += count
        self.diagnostics["queries"].append(
            {"name": str(name), "duration_ms": round(elapsed_ms, 2), "rows": count}
        )
        return value

    def reporting_context(self):
        """Choose a current snapshot or a saved-canonical GSC read path."""
        started = time.perf_counter()
        self.reset_diagnostics()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                row = self._execute(
                    cursor,
                    "reporting_context",
                    """
                    SELECT latest.status AS latest_status,
                           latest.error_code AS latest_error_code,
                           latest.error_summary AS latest_error_summary,
                           completed.id AS snapshot_id,
                           completed.gsc_reporting_through_date,
                           completed.common_reporting_date,
                           completed.gsc_source_revision AS snapshot_revision,
                           completed.refreshed_at,
                           COALESCE(connection.gsc_canonical_revision, 0) AS source_revision,
                           connection.gsc_site_url,
                           COALESCE(settings.brand_terms, '[]'::jsonb) AS brand_terms,
                           canonical.canonical_through_dates
                    FROM seo_google_connections AS connection
                    LEFT JOIN seo_reporting_settings AS settings
                      ON settings.workspace_key=connection.workspace_key
                    LEFT JOIN LATERAL (
                        SELECT status, error_code, error_summary
                        FROM seo_reporting_snapshot_runs
                        WHERE workspace_key=connection.workspace_key
                        ORDER BY refreshed_at DESC
                        LIMIT 1
                    ) AS latest ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT id, gsc_reporting_through_date,
                               common_reporting_date, gsc_source_revision, refreshed_at
                        FROM seo_reporting_snapshot_runs
                        WHERE workspace_key=connection.workspace_key AND status='completed'
                          AND COALESCE(gsc_reporting_through_date, common_reporting_date) IS NOT NULL
                        ORDER BY COALESCE(gsc_reporting_through_date, common_reporting_date) DESC,
                                 refreshed_at DESC
                        LIMIT 1
                    ) AS completed ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT jsonb_object_agg(source.search_type, source.through_date)
                                   AS canonical_through_dates
                        FROM (
                            SELECT total.search_type, MAX(total.source_date) AS through_date
                            FROM seo_gsc_property_totals_v2 AS total
                            WHERE total.workspace_key=connection.workspace_key
                              AND total.property_id=connection.gsc_site_url
                              AND total.data_state='final'
                              AND total.is_complete=TRUE
                            GROUP BY total.search_type
                        ) AS source
                    ) AS canonical ON TRUE
                    WHERE connection.workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                    one=True,
                )
        snapshot_through = row.get("gsc_reporting_through_date") or row.get("common_reporting_date")
        snapshot_available = bool(row.get("snapshot_id") and snapshot_through)
        source_revision = _integer(row.get("source_revision"))
        snapshot_revision = _integer(row.get("snapshot_revision"))
        canonical_through_dates = {
            str(key or "").casefold(): _iso(value)
            for key, value in dict(row.get("canonical_through_dates") or {}).items()
            if key and value
        }
        canonical_through = canonical_through_dates.get("web", "")
        snapshot_stale = (
            str(row.get("latest_status") or "") in {"failed", "partial"}
            or (snapshot_available and snapshot_revision < source_revision)
            or (
                snapshot_available
                and bool(canonical_through)
                and (_as_date(snapshot_through) or date.min) < (_as_date(canonical_through) or date.min)
            )
        )
        snapshot_current = snapshot_available and not snapshot_stale
        canonical_available = bool(canonical_through)
        if snapshot_current:
            reader_path = "snapshot"
            through_date = snapshot_through
            status = "ready"
        elif canonical_available:
            reader_path = "canonical"
            through_date = canonical_through
            status = "canonical_fallback"
        elif snapshot_available:
            reader_path = "snapshot"
            through_date = snapshot_through
            status = "stale_last_good"
        else:
            reader_path = "unavailable"
            through_date = ""
            status = "snapshot_unavailable"
        available = reader_path != "unavailable"
        watermark = "|".join(
            (
                reader_path,
                str(row.get("snapshot_id") or "none"),
                _iso(through_date),
                str(source_revision),
                canonical_through,
            )
        )
        result = {
            "available": available,
            "status": status,
            "reader_path": reader_path,
            "snapshot_available": snapshot_available,
            "snapshot_current": snapshot_current,
            "canonical_available": canonical_available,
            "canonical_through_dates": canonical_through_dates,
            "through_date": _iso(through_date),
            "refreshed_at": _iso(row.get("refreshed_at")),
            "watermark": watermark,
            "source_revision": source_revision,
            "snapshot_revision": snapshot_revision,
            "error_code": str(row.get("latest_error_code") or ""),
            "error_summary": str(row.get("latest_error_summary") or ""),
            "gsc_site_url": str(row.get("gsc_site_url") or ""),
            "brand_terms": [
                str(value or "").strip().casefold()
                for value in row.get("brand_terms") or []
                if str(value or "").strip()
            ],
        }
        logging.info(
            "SEO_REPORTING_CONTEXT property=%s reader_path=%s snapshot_found=%s "
            "snapshot_current=%s canonical_available=%s canonical_through=%s "
            "source_revision=%s snapshot_revision=%s duration_ms=%.2f queries=%s query_ms=%.2f rows=%s",
            result["gsc_site_url"],
            reader_path,
            snapshot_available,
            snapshot_current,
            canonical_available,
            canonical_through or "none",
            source_revision,
            snapshot_revision,
            (time.perf_counter() - started) * 1000,
            self.diagnostics["query_count"],
            self.diagnostics["query_ms"],
            self.diagnostics["rows_returned"],
        )
        return result

    @staticmethod
    def period(filters, context):
        return seo_live_analytics.matching_period(
            preset=filters.get("preset") or "Last 28 days",
            through_date=context.get("through_date"),
            custom_start=filters.get("custom_start"),
            custom_end=filters.get("custom_end"),
            comparison=filters.get("comparison") or ("Previous period" if filters.get("compare") else "Off"),
        )

    @staticmethod
    def _search_class(filters):
        return {
            "Branded": "brand",
            "Non-branded": "nonbrand",
        }.get(str(filters.get("query_class") or ""), "all")

    @staticmethod
    def _scope(filters, *, summary=False, alias=""):
        prefix = f"{alias}." if alias else ""
        market = MARKET_CODES.get(str(filters.get("market") or ""), "")
        device = str(filters.get("device") or "")
        clauses = []
        params = []
        if summary and not market and device == "All devices":
            return [f"{prefix}country_code=''", f"{prefix}device_category='all'"], []
        if summary:
            clauses.extend([f"{prefix}country_code<>''", f"{prefix}device_category<>'all'"])
        if market:
            clauses.append(f"{prefix}market_code=%s")
            params.append(market)
        if device and device != "All devices":
            clauses.append(f"LOWER({prefix}device_category)=%s")
            params.append(device.casefold())
        return clauses, params

    @staticmethod
    def _canonical_scope(filters, *, alias=""):
        prefix = f"{alias}." if alias else ""
        market = MARKET_COUNTRIES.get(str(filters.get("market") or ""), ())
        device = str(filters.get("device") or "")
        clauses = []
        params = []
        if market:
            clauses.append(f"UPPER({prefix}country_code)=ANY(%s)")
            params.append(list(market))
        if device and device != "All devices":
            clauses.append(f"LOWER({prefix}device)=%s")
            params.append(device.casefold())
        return clauses, params

    @staticmethod
    def _canonical_query_class(filters, context, column_name):
        search_class = PostgresSEOInteractiveReader._search_class(filters)
        if search_class == "all":
            return [], []
        terms = [
            str(value or "").strip().casefold()
            for value in context.get("brand_terms") or []
            if str(value or "").strip()
        ]
        if not terms:
            return (["FALSE"], []) if search_class == "brand" else ([], [])
        expression = " OR ".join(f"LOWER({column_name}) LIKE %s" for _term in terms)
        clause = f"({expression})" if search_class == "brand" else f"NOT ({expression})"
        return [clause], [f"%{term}%" for term in terms]

    @staticmethod
    def _effective_context(filters, context):
        effective = dict(context or {})
        search_type = str(filters.get("search_type") or "web").strip().casefold()
        if (
            search_type == "web"
            and effective.get("available")
            and effective.get("reader_path") in (None, "", "snapshot")
        ):
            effective.setdefault("reader_path", "snapshot")
            return effective
        canonical_dates = dict(effective.get("canonical_through_dates") or {})
        canonical_through = canonical_dates.get(search_type, "")
        if canonical_through and effective.get("gsc_site_url"):
            effective.update(
                {
                    "available": True,
                    "status": "canonical_fallback",
                    "reader_path": "canonical",
                    "through_date": _iso(canonical_through),
                    "watermark": "|".join(
                        (
                            str(effective.get("watermark") or "none"),
                            search_type,
                            _iso(canonical_through),
                        )
                    ),
                }
            )
            return effective
        effective.update(
            {
                "available": False,
                "status": "snapshot_unavailable",
                "reader_path": "unavailable",
                "through_date": "",
            }
        )
        return effective

    @staticmethod
    def _period_payload(filters, context):
        if not context.get("available"):
            return None
        return PostgresSEOInteractiveReader.period(filters, context)

    def _canonical_where(
        self,
        filters,
        context,
        *,
        start_date,
        end_date,
        alias="",
        query_rows=False,
    ):
        prefix = f"{alias}." if alias else ""
        clauses = [
            f"{prefix}workspace_key=%s",
            f"{prefix}property_id=%s",
            f"{prefix}source_date BETWEEN %s AND %s",
            f"{prefix}search_type=%s",
            f"{prefix}data_state='final'",
            f"{prefix}is_complete=TRUE",
        ]
        params = [
            WORKSPACE_KEY,
            str(context.get("gsc_site_url") or ""),
            start_date,
            end_date,
            str(filters.get("search_type") or "web").strip().casefold(),
        ]
        scope, scope_params = self._canonical_scope(filters, alias=alias)
        clauses.extend(scope)
        params.extend(scope_params)
        if query_rows:
            query_class, query_params = self._canonical_query_class(
                filters,
                context,
                f"{prefix}raw_query",
            )
            clauses.extend(query_class)
            params.extend(query_params)
        return clauses, params

    def overview_base(self, filters, *, context=None):
        """Read only visible overview metrics, trend, and rank-quality scalar."""
        self.reset_diagnostics()
        context = self._effective_context(filters, dict(context or self.reporting_context()))
        period = self._period_payload(filters, context)
        if not period:
            return self._unavailable_snapshot(filters, context)
        if context.get("reader_path") == "canonical":
            return self._canonical_overview_base(filters, context, period)
        search_class = self._search_class(filters)
        # Only the all-query class has property-level summary rows. Brand and
        # non-brand metrics aggregate the saved detail rows instead.
        summary_scope, summary_params = self._scope(
            filters,
            summary=search_class == "all",
        )
        detail_scope, detail_params = self._scope(filters)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                metrics = self._execute(
                    cursor,
                    "overview_metrics",
                    f"""
                    SELECT
                        COALESCE(SUM(organic_clicks) FILTER (WHERE date BETWEEN %s AND %s), 0) AS current_clicks,
                        COALESCE(SUM(organic_impressions) FILTER (WHERE date BETWEEN %s AND %s), 0) AS current_impressions,
                        COALESCE(SUM(position_weight) FILTER (WHERE date BETWEEN %s AND %s), 0) AS current_weight,
                        COALESCE(SUM(source_gsc_rows) FILTER (WHERE date BETWEEN %s AND %s), 0) AS current_rows,
                        COALESCE(SUM(organic_clicks) FILTER (WHERE date BETWEEN %s AND %s), 0) AS previous_clicks,
                        COALESCE(SUM(organic_impressions) FILTER (WHERE date BETWEEN %s AND %s), 0) AS previous_impressions,
                        COALESCE(SUM(position_weight) FILTER (WHERE date BETWEEN %s AND %s), 0) AS previous_weight,
                        COALESCE(SUM(source_gsc_rows) FILTER (WHERE date BETWEEN %s AND %s), 0) AS previous_rows
                    FROM seo_reporting_daily_metrics
                    WHERE workspace_key=%s AND search_class=%s
                      AND date BETWEEN %s AND %s
                      {' AND ' if summary_scope else ''}{' AND '.join(summary_scope)}
                    """,
                    (
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period["previous_start_date"], period["previous_end_date"],
                        period["previous_start_date"], period["previous_end_date"],
                        period["previous_start_date"], period["previous_end_date"],
                        period["previous_start_date"], period["previous_end_date"],
                        WORKSPACE_KEY, search_class,
                        period["previous_start_date"], period["end_date"],
                        *summary_params,
                    ),
                    one=True,
                )
                trend = self._execute(
                    cursor,
                    "overview_trend",
                    f"""
                    SELECT date, SUM(organic_clicks) AS organic_clicks,
                           SUM(organic_impressions) AS organic_impressions,
                           SUM(position_weight) AS position_weight
                    FROM seo_reporting_daily_metrics
                    WHERE workspace_key=%s AND search_class=%s
                      AND date BETWEEN %s AND %s
                      {' AND ' if summary_scope else ''}{' AND '.join(summary_scope)}
                    GROUP BY date ORDER BY date
                    """,
                    (WORKSPACE_KEY, search_class, period["start_date"], period["end_date"], *summary_params),
                )
                rank = self._execute(
                    cursor,
                    "rank_quality",
                    f"""
                    WITH query_metrics AS (
                        SELECT query, SUM(organic_clicks) AS clicks,
                               SUM(organic_impressions) AS impressions,
                               CASE WHEN SUM(organic_impressions)>0
                                    THEN SUM(position_weight)/SUM(organic_impressions) ELSE 0 END AS position
                        FROM seo_reporting_query_daily
                        WHERE workspace_key=%s AND search_class=%s
                          AND date BETWEEN %s AND %s AND query<>''
                          {' AND ' if detail_scope else ''}{' AND '.join(detail_scope)}
                        GROUP BY query
                    )
                    SELECT
                        COALESCE(SUM(clicks), 0) AS known_clicks,
                        COALESCE(SUM(impressions), 0) AS known_impressions,
                        COALESCE(SUM(
                            impressions * CASE
                                WHEN position BETWEEN 1 AND 3 THEN 1
                                WHEN position BETWEEN 4 AND 10 THEN 0.75
                                WHEN position BETWEEN 11 AND 20 THEN 0.40
                                WHEN position BETWEEN 21 AND 50 THEN 0.10
                                ELSE 0
                            END
                        ), 0) AS quality_weight
                    FROM query_metrics
                    """,
                    (WORKSPACE_KEY, search_class, period["start_date"], period["end_date"], *detail_params),
                    one=True,
                )
        current = self._metrics(metrics, "current")
        previous = self._metrics(metrics, "previous") if filters.get("compare") else {}
        known = _decimal(rank.get("known_impressions"))
        weighted = _decimal(rank.get("quality_weight"))
        daily = []
        for row in trend:
            impressions = _decimal(row.get("organic_impressions"))
            daily.append({
                "date": _iso(row.get("date")),
                "organic_clicks": _decimal(row.get("organic_clicks")),
                "organic_impressions": impressions,
                "average_position": _decimal(row.get("position_weight")) / impressions if impressions else None,
            })
        ready = bool(_integer(metrics.get("current_rows")))
        return {
            "ready": ready,
            "reason": "" if ready else "no_saved_gsc_data_for_range",
            "health": self._health(context),
            "filters": dict(filters),
            "period": {key: _iso(value) for key, value in period.items()},
            "current": current,
            "previous": previous,
            "daily_trend": daily,
            "rank_quality": {
                "score": Decimal("100") * weighted / known if known else None,
                "distribution": {},
                "impressions": known,
            },
            "known_query_clicks": _decimal(rank.get("known_clicks")),
            "known_query_impressions": known,
            "watermark": context.get("watermark") or "",
            "fallback_mode": False,
            "diagnostics": dict(self.diagnostics),
        }

    def _canonical_overview_base(self, filters, context, period):
        """Aggregate only the requested current/comparison GSC date windows."""
        search_class = self._search_class(filters)
        scope, _scope_params = self._canonical_scope(filters)
        use_property_totals = search_class == "all" and not scope
        first_date = period.get("previous_start_date") or period["start_date"]
        if use_property_totals:
            table = "seo_gsc_property_totals_v2"
            position_weight = "average_position * impressions"
            where, where_params = self._canonical_where(
                filters,
                context,
                start_date=first_date,
                end_date=period["end_date"],
            )
            where.append("aggregation_type='property'")
        else:
            table = "seo_gsc_query_daily_v2"
            position_weight = "position_weight"
            where, where_params = self._canonical_where(
                filters,
                context,
                start_date=first_date,
                end_date=period["end_date"],
                query_rows=True,
            )
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                metrics = self._execute(
                    cursor,
                    "canonical_overview_metrics",
                    f"""
                    SELECT
                        COALESCE(SUM(clicks) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS current_clicks,
                        COALESCE(SUM(impressions) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS current_impressions,
                        COALESCE(SUM({position_weight}) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS current_weight,
                        COUNT(*) FILTER (WHERE source_date BETWEEN %s AND %s) AS current_rows,
                        COALESCE(SUM(clicks) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS previous_clicks,
                        COALESCE(SUM(impressions) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS previous_impressions,
                        COALESCE(SUM({position_weight}) FILTER (WHERE source_date BETWEEN %s AND %s), 0) AS previous_weight,
                        COUNT(*) FILTER (WHERE source_date BETWEEN %s AND %s) AS previous_rows
                    FROM {table}
                    WHERE {' AND '.join(where)}
                    """,
                    (
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period["start_date"], period["end_date"],
                        period.get("previous_start_date"), period.get("previous_end_date"),
                        period.get("previous_start_date"), period.get("previous_end_date"),
                        period.get("previous_start_date"), period.get("previous_end_date"),
                        period.get("previous_start_date"), period.get("previous_end_date"),
                        *where_params,
                    ),
                    one=True,
                )
                trend = self._execute(
                    cursor,
                    "canonical_overview_trend",
                    f"""
                    SELECT source_date AS date, SUM(clicks) AS organic_clicks,
                           SUM(impressions) AS organic_impressions,
                           SUM({position_weight}) AS position_weight
                    FROM {table}
                    WHERE {' AND '.join(where)}
                      AND source_date BETWEEN %s AND %s
                    GROUP BY source_date ORDER BY source_date
                    """,
                    (*where_params, period["start_date"], period["end_date"]),
                )
                rank_where, rank_params = self._canonical_where(
                    filters,
                    context,
                    start_date=period["start_date"],
                    end_date=period["end_date"],
                    query_rows=True,
                )
                rank = self._execute(
                    cursor,
                    "canonical_rank_quality",
                    f"""
                    WITH query_metrics AS (
                        SELECT normalized_query,
                               SUM(clicks) AS clicks,
                               SUM(impressions) AS impressions,
                               CASE WHEN SUM(impressions)>0
                                    THEN SUM(position_weight)/SUM(impressions) ELSE 0 END AS position
                        FROM seo_gsc_query_daily_v2
                        WHERE {' AND '.join(rank_where)} AND normalized_query<>''
                        GROUP BY normalized_query
                    )
                    SELECT COALESCE(SUM(clicks), 0) AS known_clicks,
                           COALESCE(SUM(impressions), 0) AS known_impressions,
                           COALESCE(SUM(
                               impressions * CASE
                                   WHEN position BETWEEN 1 AND 3 THEN 1
                                   WHEN position BETWEEN 4 AND 10 THEN 0.75
                                   WHEN position BETWEEN 11 AND 20 THEN 0.40
                                   WHEN position BETWEEN 21 AND 50 THEN 0.10
                                   ELSE 0
                               END
                           ), 0) AS quality_weight
                    FROM query_metrics
                    """,
                    rank_params,
                    one=True,
                )
        self.diagnostics["canonical_fallback"] = True
        current = self._metrics(metrics, "current")
        previous = self._metrics(metrics, "previous") if filters.get("compare") else {}
        known = _decimal(rank.get("known_impressions"))
        weighted = _decimal(rank.get("quality_weight"))
        daily = []
        for row in trend:
            impressions = _decimal(row.get("organic_impressions"))
            daily.append(
                {
                    "date": _iso(row.get("date")),
                    "organic_clicks": _decimal(row.get("organic_clicks")),
                    "organic_impressions": impressions,
                    "average_position": (
                        _decimal(row.get("position_weight")) / impressions
                        if impressions
                        else None
                    ),
                }
            )
        logging.info(
            "SEO_CANONICAL_FALLBACK operation=overview property=%s search_type=%s "
            "start=%s end=%s rows=%s query_ms=%.2f",
            context.get("gsc_site_url") or "",
            str(filters.get("search_type") or "web"),
            period["start_date"],
            period["end_date"],
            self.diagnostics["rows_returned"],
            self.diagnostics["query_ms"],
        )
        ready = bool(_integer(metrics.get("current_rows")))
        return {
            "ready": ready,
            "reason": "" if ready else "no_saved_gsc_data_for_range",
            "health": self._health(context),
            "filters": dict(filters),
            "period": {key: _iso(value) for key, value in period.items()},
            "current": current,
            "previous": previous,
            "daily_trend": daily,
            "rank_quality": {
                "score": Decimal("100") * weighted / known if known else None,
                "distribution": {},
                "impressions": known,
            },
            "known_query_clicks": _decimal(rank.get("known_clicks")),
            "known_query_impressions": known,
            "watermark": context.get("watermark") or "",
            "fallback_mode": True,
            "diagnostics": dict(self.diagnostics),
        }

    def rank_distribution(self, filters, *, context=None):
        """Read rank buckets only when the visible Overview view needs them."""
        self.reset_diagnostics()
        context = self._effective_context(filters, dict(context or self.reporting_context()))
        period = self._period_payload(filters, context)
        if not period:
            return {"distribution": {}, "unavailable": True, "diagnostics": dict(self.diagnostics)}
        if context.get("reader_path") == "canonical":
            where, params = self._canonical_where(
                filters,
                context,
                start_date=period["start_date"],
                end_date=period["end_date"],
                query_rows=True,
            )
            with self._backend().connect() as connection:
                with connection.cursor() as cursor:
                    rank = self._execute(
                        cursor,
                        "canonical_rank_distribution",
                        f"""
                        WITH query_metrics AS (
                            SELECT normalized_query,
                                   SUM(impressions) AS impressions,
                                   CASE WHEN SUM(impressions)>0
                                        THEN SUM(position_weight)/SUM(impressions) ELSE 0 END AS position
                            FROM seo_gsc_query_daily_v2
                            WHERE {' AND '.join(where)} AND normalized_query<>''
                            GROUP BY normalized_query
                        )
                        SELECT
                            COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 1 AND 3), 0) AS positions_1_3,
                            COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 4 AND 10), 0) AS positions_4_10,
                            COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 11 AND 20), 0) AS positions_11_20,
                            COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 21 AND 50), 0) AS positions_21_50,
                            COALESCE(SUM(impressions) FILTER (WHERE position>50), 0) AS positions_51_plus
                        FROM query_metrics
                        """,
                        params,
                        one=True,
                    )
            self.diagnostics["canonical_fallback"] = True
            return self._rank_distribution_result(rank)
        scope, scope_params = self._scope(filters)
        search_class = self._search_class(filters)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                rank = self._execute(
                    cursor,
                    "rank_distribution",
                    f"""
                    WITH query_metrics AS (
                        SELECT query, SUM(organic_impressions) AS impressions,
                               CASE WHEN SUM(organic_impressions)>0
                                    THEN SUM(position_weight)/SUM(organic_impressions) ELSE 0 END AS position
                        FROM seo_reporting_query_daily
                        WHERE workspace_key=%s AND search_class=%s
                          AND date BETWEEN %s AND %s AND query<>''
                          {' AND ' if scope else ''}{' AND '.join(scope)}
                        GROUP BY query
                    )
                    SELECT
                        COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 1 AND 3), 0) AS positions_1_3,
                        COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 4 AND 10), 0) AS positions_4_10,
                        COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 11 AND 20), 0) AS positions_11_20,
                        COALESCE(SUM(impressions) FILTER (WHERE position BETWEEN 21 AND 50), 0) AS positions_21_50,
                        COALESCE(SUM(impressions) FILTER (WHERE position>50), 0) AS positions_51_plus
                    FROM query_metrics
                    """,
                    (WORKSPACE_KEY, search_class, period["start_date"], period["end_date"], *scope_params),
                    one=True,
                )
        return self._rank_distribution_result(rank)

    def _rank_distribution_result(self, rank):
        return {
            "distribution": {
                "Positions 1-3": _decimal(rank.get("positions_1_3")),
                "Positions 4-10": _decimal(rank.get("positions_4_10")),
                "Positions 11-20": _decimal(rank.get("positions_11_20")),
                "Positions 21-50": _decimal(rank.get("positions_21_50")),
                "Above 50": _decimal(rank.get("positions_51_plus")),
            },
            "unavailable": False,
            "diagnostics": dict(self.diagnostics),
        }

    @staticmethod
    def _metrics(row, prefix):
        impressions = _decimal(row.get(f"{prefix}_impressions"))
        clicks = _decimal(row.get(f"{prefix}_clicks"))
        available = _integer(row.get(f"{prefix}_rows")) > 0
        if not available:
            return _empty_metrics()
        return {
            "organic_clicks": clicks,
            "organic_impressions": impressions,
            "ctr": clicks / impressions if impressions else Decimal("0"),
            "average_position": _decimal(row.get(f"{prefix}_weight")) / impressions if impressions else Decimal("0"),
        }

    @staticmethod
    def _health(context):
        canonical = context.get("reader_path") == "canonical"
        return {
            "gsc": {
                "available": bool(context.get("available")),
                "status": context.get("status") or "snapshot_unavailable",
                "through_date": context.get("through_date") or "",
                "identifier": context.get("gsc_site_url") or "",
                "cache_revision": context.get("source_revision") or 0,
                "reader_path": context.get("reader_path") or "unavailable",
                "source_label": (
                    "Saved Google Search Console data"
                    if canonical
                    else "Saved SEO reporting snapshot"
                ),
                "snapshot_pending": canonical,
            },
            "snapshot": dict(context),
        }

    def _unavailable_snapshot(self, filters, context):
        reason = (
            "reporting_snapshot_unavailable"
            if str(filters.get("search_type") or "web").casefold() == "web"
            else "search_type_snapshot_unavailable"
        )
        return {
            "ready": False,
            "reason": reason,
            "health": self._health(context),
            "filters": dict(filters),
            "current": _empty_metrics(),
            "previous": {},
            "daily_trend": [],
            "rank_quality": {"score": None, "distribution": {}, "impressions": Decimal("0")},
            "watermark": context.get("watermark") or "",
            "fallback_mode": False,
            "diagnostics": dict(self.diagnostics),
        }

    @staticmethod
    def _view_clause(view):
        return {
            "Quick wins": "average_position BETWEEN 4 AND 20",
            "Rising": "ranking_change>0",
            "Declining": "ranking_change<0",
            "New": "previous_impressions=0",
            "Top 3": "average_position>0 AND average_position<=3",
            "Positions 4-10": "average_position BETWEEN 4 AND 10",
            "Positions 11-20": "average_position BETWEEN 11 AND 20",
            "Unmapped": "canonical_page_key=''",
            "Opportunities": "average_position BETWEEN 4 AND 20",
        }.get(str(view or ""), "TRUE")

    @staticmethod
    def _sort_expression(view):
        if view == "Rising":
            return "ranking_change"
        if view == "Declining":
            return "-ranking_change"
        if view in {"Quick wins", "Opportunities"}:
            return "opportunity_score"
        if view == "New":
            return "impressions"
        return "clicks"

    def query_page(
        self,
        filters,
        *,
        view="All",
        search="",
        limit=25,
        cursor=None,
        context=None,
        excluded_queries=(),
        _export_all=False,
    ):
        """Return one deterministic keyset page from compact or canonical rows."""
        self.reset_diagnostics()
        context = self._effective_context(filters, dict(context or self.reporting_context()))
        period = self._period_payload(filters, context)
        if not period:
            return {"rows": [], "total": 0, "next_cursor": None, "unavailable": True, "diagnostics": dict(self.diagnostics)}
        if context.get("reader_path") == "canonical":
            current_where, current_params = self._canonical_where(
                filters,
                context,
                start_date=period["start_date"],
                end_date=period["end_date"],
                query_rows=True,
            )
            previous_where, previous_params = self._canonical_where(
                filters,
                context,
                start_date=period.get("previous_start_date") or period["start_date"],
                end_date=period.get("previous_end_date") or period["end_date"],
                query_rows=True,
            )
            current_where.append("normalized_query<>''")
            previous_where.append("normalized_query<>''")
            current_cte = f"""
                SELECT normalized_query AS query_key,
                       MIN(raw_query) AS query,
                       MIN(query_hash) AS query_hash,
                       ''::TEXT AS canonical_page_key,
                       0::BIGINT AS mapped_page_count,
                       SUM(clicks) AS clicks,
                       SUM(impressions) AS impressions,
                       SUM(position_weight) AS position_weight,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT UPPER(country_code)), '') AS market_mix,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT LOWER(device)), '') AS device_mix
                FROM seo_gsc_query_daily_v2
                WHERE {' AND '.join(current_where)}
                GROUP BY normalized_query
            """
            previous_cte = f"""
                SELECT normalized_query AS query_key,
                       SUM(clicks) AS previous_clicks,
                       SUM(impressions) AS previous_impressions,
                       SUM(position_weight) AS previous_position_weight
                FROM seo_gsc_query_daily_v2
                WHERE {' AND '.join(previous_where)}
                GROUP BY normalized_query
            """
        else:
            scope, scope_params = self._scope(filters)
            search_class = self._search_class(filters)
            current_where = ["workspace_key=%s", "search_class=%s", "date BETWEEN %s AND %s", "query<>''", *scope]
            previous_where = ["workspace_key=%s", "search_class=%s", "date BETWEEN %s AND %s", "query<>''", *scope]
            current_params = [WORKSPACE_KEY, search_class, period["start_date"], period["end_date"], *scope_params]
            previous_params = [WORKSPACE_KEY, search_class, period["previous_start_date"], period["previous_end_date"], *scope_params]
            current_cte = f"""
                SELECT query AS query_key, query,
                       MIN(query_hash) AS query_hash,
                       COALESCE(MIN(NULLIF(canonical_page_key, '')), '') AS canonical_page_key,
                       COUNT(DISTINCT NULLIF(canonical_page_key, '')) AS mapped_page_count,
                       SUM(organic_clicks) AS clicks,
                       SUM(organic_impressions) AS impressions,
                       SUM(position_weight) AS position_weight,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT market_code), '') AS market_mix,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT device_category), '') AS device_mix
                FROM seo_reporting_query_daily
                WHERE {' AND '.join(current_where)}
                GROUP BY query
            """
            previous_cte = f"""
                SELECT query AS query_key,
                       SUM(organic_clicks) AS previous_clicks,
                       SUM(organic_impressions) AS previous_impressions,
                       SUM(position_weight) AS previous_position_weight
                FROM seo_reporting_query_daily
                WHERE {' AND '.join(previous_where)}
                GROUP BY query
            """
        filters_sql = [self._view_clause(view)]
        filtered_params = []
        if str(search or "").strip():
            filters_sql.append("LOWER(query) LIKE %s")
            filtered_params.append(f"%{str(search).strip().casefold()}%")
        excluded_queries = sorted({str(item or "").strip().casefold() for item in excluded_queries if str(item or "").strip()})
        if view in {"Unmapped", "Opportunities"} and excluded_queries:
            filters_sql.append("NOT (LOWER(query)=ANY(%s))")
            filtered_params.append(excluded_queries)
        sort_expression = self._sort_expression(view)
        cursor_sql = ""
        cursor_params = []
        if cursor:
            cursor_sql = """
                WHERE sort_score < %s
                   OR (sort_score=%s AND impressions<%s)
                   OR (sort_score=%s AND impressions=%s AND query>%s)
            """
            cursor_params = [
                cursor.get("sort_score"), cursor.get("sort_score"), cursor.get("impressions"),
                cursor.get("sort_score"), cursor.get("impressions"), cursor.get("query"),
            ]
        limit_sql = "" if _export_all else "LIMIT %s"
        sql = f"""
            WITH current_metrics AS (
                {current_cte}
            ), previous_metrics AS (
                {previous_cte}
            ), enriched AS (
                SELECT current_metrics.*,
                       COALESCE(previous_metrics.previous_clicks, 0) AS previous_clicks,
                       COALESCE(previous_metrics.previous_impressions, 0) AS previous_impressions,
                       COALESCE(previous_metrics.previous_position_weight, 0) AS previous_position_weight,
                       CASE WHEN current_metrics.impressions>0
                            THEN current_metrics.clicks/current_metrics.impressions ELSE 0 END AS ctr,
                       CASE WHEN current_metrics.impressions>0
                            THEN current_metrics.position_weight/current_metrics.impressions ELSE 0 END AS average_position,
                       current_metrics.clicks-COALESCE(previous_metrics.previous_clicks, 0) AS click_change,
                       CASE WHEN COALESCE(previous_metrics.previous_impressions, 0)>0
                            THEN previous_metrics.previous_position_weight/previous_metrics.previous_impressions ELSE NULL END AS previous_position,
                       CASE WHEN COALESCE(previous_metrics.previous_impressions, 0)>0
                            THEN previous_metrics.previous_position_weight/previous_metrics.previous_impressions
                                 - current_metrics.position_weight/NULLIF(current_metrics.impressions, 0)
                            ELSE NULL END AS ranking_change
                FROM current_metrics
                LEFT JOIN previous_metrics USING (query_key)
            ), scored AS (
                SELECT *,
                       LEAST(100,
                           LEAST(35, impressions/40)
                           + CASE WHEN average_position BETWEEN 4 AND 20
                                  THEN 30-ABS(average_position-10) ELSE 0 END
                           + LEAST(15, GREATEST(0, 0.05-ctr)*300)
                           + LEAST(10, GREATEST(0, click_change))
                           + CASE WHEN canonical_page_key IS NULL THEN 15 ELSE 0 END
                       )
                       AS opportunity_score
                FROM enriched
            ), filtered AS (
                SELECT *, COALESCE({sort_expression}, 0) AS sort_score
                FROM scored
                WHERE {' AND '.join(filters_sql)}
            ), counted AS (
                SELECT *, COUNT(*) OVER() AS total_count
                FROM filtered
            )
            SELECT * FROM counted
            {cursor_sql}
            ORDER BY sort_score DESC, impressions DESC, query ASC
            {limit_sql}
        """
        params = [*current_params, *previous_params, *filtered_params, *cursor_params]
        if not _export_all:
            params.append(max(1, min(int(limit or 25), 100)))
        with self._backend().connect() as connection:
            with connection.cursor() as db_cursor:
                rows = self._execute(db_cursor, f"query_page:{view}", sql, params)
        if context.get("reader_path") == "canonical":
            self.diagnostics["canonical_fallback"] = True
            logging.info(
                "SEO_CANONICAL_FALLBACK operation=query_page property=%s search_type=%s "
                "start=%s end=%s returned=%s total=%s",
                context.get("gsc_site_url") or "",
                str(filters.get("search_type") or "web"),
                period["start_date"],
                period["end_date"],
                len(rows),
                _integer(rows[0].get("total_count")) if rows else 0,
            )
        total = _integer(rows[0].get("total_count")) if rows else 0
        for row in rows:
            row["current_page"] = row.get("canonical_page_key") or ""
            row["market_mix"] = sorted(str(value) for value in row.get("market_mix") or [] if value)
            row["device_mix"] = sorted(str(value).title() for value in row.get("device_mix") or [] if value)
        next_cursor = None
        if not _export_all and rows and len(rows) < total:
            last = rows[-1]
            next_cursor = {
                "sort_score": last.get("sort_score"),
                "impressions": last.get("impressions"),
                "query": last.get("query"),
            }
        return {
            "rows": rows,
            "total": total,
            "next_cursor": next_cursor,
            "unavailable": False,
            "diagnostics": dict(self.diagnostics),
        }

    def query_export(
        self,
        filters,
        *,
        view="All",
        search="",
        context=None,
        excluded_queries=(),
    ):
        """Return the complete filtered aggregate for an explicit CSV export."""
        return self.query_page(
            filters,
            view=view,
            search=search,
            context=context,
            excluded_queries=excluded_queries,
            _export_all=True,
        )

    def landing_pages(self, filters, *, limit=25, context=None):
        self.reset_diagnostics()
        context = self._effective_context(filters, dict(context or self.reporting_context()))
        period = self._period_payload(filters, context)
        if not period:
            return {"rows": [], "total": 0, "unavailable": True, "diagnostics": dict(self.diagnostics)}
        if context.get("reader_path") == "canonical":
            where, params = self._canonical_where(
                filters,
                context,
                start_date=period["start_date"],
                end_date=period["end_date"],
            )
            with self._backend().connect() as connection:
                with connection.cursor() as cursor:
                    rows = self._execute(
                        cursor,
                        "canonical_landing_pages",
                        f"""
                        WITH gsc_metrics AS (
                            SELECT page_url,
                                   SUM(clicks) AS clicks,
                                   SUM(impressions) AS impressions,
                                   SUM(position_weight) AS position_weight
                            FROM seo_gsc_page_daily_v2
                            WHERE {' AND '.join(where)} AND page_url<>''
                            GROUP BY page_url
                        )
                        SELECT gsc.page_url AS canonical_url,
                               COALESCE(page.title, '') AS title,
                               COALESCE(page.page_type, '') AS page_type,
                               gsc.clicks, gsc.impressions, gsc.position_weight,
                               0::NUMERIC AS sessions,
                               0::NUMERIC AS engaged_sessions,
                               COUNT(*) OVER() AS total_count
                        FROM gsc_metrics AS gsc
                        LEFT JOIN seo_canonical_pages AS page
                          ON page.workspace_key=%s AND page.canonical_url=gsc.page_url
                        ORDER BY gsc.clicks DESC, gsc.impressions DESC, gsc.page_url ASC
                        LIMIT %s
                        """,
                        (
                            *params,
                            WORKSPACE_KEY,
                            max(1, min(int(limit), 100)),
                        ),
                    )
            self.diagnostics["canonical_fallback"] = True
            return self._landing_page_result(rows)
        scope, scope_params = self._scope(filters)
        metric_scope = [
            item.replace("market_code", "metric.market_code").replace(
                "device_category", "metric.device_category"
            )
            for item in scope
        ]
        gsc_where = [
            "metric.workspace_key=%s", "metric.date BETWEEN %s AND %s", *metric_scope,
        ]
        enrichment_where = [
            "enrichment.workspace_key=%s", "enrichment.date BETWEEN %s AND %s",
            *[
                item.replace("market_code", "enrichment.market_code").replace(
                    "device_category", "enrichment.device_category"
                )
                for item in scope
            ],
        ]
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                rows = self._execute(
                    cursor,
                    "landing_pages",
                    f"""
                    WITH gsc_metrics AS (
                        SELECT page_url,
                               SUM(organic_clicks) AS clicks,
                               SUM(organic_impressions) AS impressions,
                               SUM(position_weight) AS position_weight
                        FROM seo_reporting_page_daily AS metric
                        WHERE {' AND '.join(gsc_where)}
                        GROUP BY page_url
                    ), enrichment_metrics AS (
                        SELECT page.canonical_url AS page_url,
                               SUM(enrichment.organic_sessions) AS sessions,
                               SUM(enrichment.engaged_sessions) AS engaged_sessions
                        FROM seo_reporting_landing_page_daily AS enrichment
                        JOIN seo_canonical_pages AS page
                          ON page.page_key=enrichment.canonical_page_key
                        WHERE {' AND '.join(enrichment_where)}
                        GROUP BY page.canonical_url
                    )
                    SELECT gsc.page_url AS canonical_url,
                           COALESCE(page.title, '') AS title,
                           COALESCE(page.page_type, '') AS page_type,
                           gsc.clicks, gsc.impressions, gsc.position_weight,
                           COALESCE(enrichment.sessions, 0) AS sessions,
                           COALESCE(enrichment.engaged_sessions, 0) AS engaged_sessions,
                           COUNT(*) OVER() AS total_count
                    FROM gsc_metrics AS gsc
                    LEFT JOIN seo_canonical_pages AS page ON page.canonical_url=gsc.page_url
                    LEFT JOIN enrichment_metrics AS enrichment ON enrichment.page_url=gsc.page_url
                    ORDER BY gsc.clicks DESC, gsc.impressions DESC, gsc.page_url ASC
                    LIMIT %s
                    """,
                    (
                        WORKSPACE_KEY, period["start_date"], period["end_date"], *scope_params,
                        WORKSPACE_KEY, period["start_date"], period["end_date"], *scope_params,
                        max(1, min(int(limit), 100)),
                    ),
                )
        return self._landing_page_result(rows)

    def _landing_page_result(self, rows):
        for row in rows:
            impressions = _decimal(row.get("impressions"))
            clicks = _decimal(row.get("clicks"))
            row["ctr"] = clicks / impressions if impressions else Decimal("0")
            row["average_position"] = _decimal(row.get("position_weight")) / impressions if impressions else None
        return {
            "rows": rows,
            "total": _integer(rows[0].get("total_count")) if rows else 0,
            "unavailable": False,
            "diagnostics": dict(self.diagnostics),
        }


def default_reader():
    return PostgresSEOInteractiveReader()


def log_diagnostics(route, operation, diagnostics, *, cache="miss"):
    diagnostics = dict(diagnostics or {})
    logging.info(
        "SEO_PERF route=%s operation=%s cache=%s queries=%s query_ms=%.2f rows=%s "
        "raw_fallback=%s raw_fallback_ms=%.2f canonical_fallback=%s",
        route,
        operation,
        cache,
        _integer(diagnostics.get("query_count")),
        float(diagnostics.get("query_ms") or 0),
        _integer(diagnostics.get("rows_returned")),
        bool(diagnostics.get("raw_fallback")),
        float(diagnostics.get("raw_fallback_ms") or 0),
        bool(diagnostics.get("canonical_fallback")),
    )
