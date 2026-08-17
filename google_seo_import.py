"""Durable, database-backed historical imports for Google SEO reporting data."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
import requests

from activity_log import record_activity_log
import google_seo
import os_accounts


SEO_IMPORT_MIGRATION = "20260813_google_seo_phase3_storage.sql"
WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
SOURCES = ("GSC", "GA4")
MODES = ("historical", "daily", "manual")
ACTIVE_STATUSES = ("queued", "running")
GSC_SEARCH_TYPE = "web"
GSC_PAGE_SIZE = 25_000
GSC_DAILY_ROW_LIMIT = 50_000
GA4_PAGE_SIZE = 250_000
LEASE_SECONDS = 10 * 60
MAX_SLICE_RETRIES = 3
GA4_REVENUE_BASIS = "GA4 attributed/unconfirmed"
BASE_DIR = Path(__file__).resolve().parent

GSC_DETAIL_DIMENSIONS = ("query", "page", "country", "device")
GA4_REQUIRED_DIMENSIONS = (
    "date",
    "landingPagePlusQueryString",
    "countryId",
    "deviceCategory",
    "sessionDefaultChannelGroup",
)
GA4_OPTIONAL_DIMENSION = "hostname"
GA4_METRICS = (
    "sessions",
    "engagedSessions",
    "engagementRate",
    "userEngagementDuration",
    "transactions",
    "purchaseRevenue",
)


class SEOImportError(RuntimeError):
    def __init__(self, message, *, code="seo_import_error", retryable=True):
        super().__init__(str(message or "SEO import could not be completed."))
        self.public_message = str(message or "SEO import could not be completed.")[:300]
        self.code = str(code or "seo_import_error")[:100]
        self.retryable = bool(retryable)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as error:
        raise SEOImportError(
            "The stored import date is invalid.",
            code="invalid_import_date",
            retryable=False,
        ) from error


def _iso(value):
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clean_property_id(value):
    clean = str(value or "").strip()
    return clean if clean.startswith("properties/") else f"properties/{clean}"


def dimension_key_hash(*values):
    payload = json.dumps(
        [str(value or "") for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def date_sequence(start_date, end_date):
    current = _as_date(start_date)
    end = _as_date(end_date)
    while current and end and current <= end:
        yield current
        current += timedelta(days=1)


def daily_refresh_range(earliest, latest_available, latest_stored, *, recheck_days=7):
    earliest = _as_date(earliest)
    latest_available = _as_date(latest_available)
    latest_stored = _as_date(latest_stored)
    if not earliest or not latest_available or earliest > latest_available:
        return None, None
    correction_start = max(earliest, latest_available - timedelta(days=max(1, recheck_days) - 1))
    new_data_start = earliest if not latest_stored else latest_stored + timedelta(days=1)
    return min(correction_start, new_data_start), latest_available


def sanitize_import_error(error):
    if isinstance(error, SEOImportError):
        return error.code, error.public_message
    if isinstance(error, google_seo.GoogleSEOError):
        return str(error.code or "google_error")[:100], str(error.public_message)[:300]
    return "seo_import_failed", "The Google SEO import could not be completed. It will be safe to retry."


def _log_import_failure(*, run_id, source, error_code, slice_date=None):
    context = {
        "run_id": str(run_id or "")[:100],
        "source": str(source or "")[:20],
        "error_code": str(error_code or "seo_import_failed")[:100],
        "slice_date": _iso(slice_date),
    }
    logging.warning("Google SEO import failed: %s", json.dumps(context, sort_keys=True))
    try:
        import supabase_backend

        supabase_backend.log_app_error(
            "google_seo_import_failed",
            "Google SEO import failed.",
            context,
        )
    except Exception:
        pass


class GoogleSEOReportingClient:
    def __init__(self, access_token, *, request_get=requests.get, request_post=requests.post):
        self.access_token = str(access_token or "")
        self.request_get = request_get
        self.request_post = request_post

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint, *, stage):
        response = google_seo._request_with_retries(
            lambda: self.request_get(
                endpoint,
                headers=self.headers,
                timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS,
            ),
            stage=stage,
        )
        return google_seo._response_json(response, stage=stage)

    def _post(self, endpoint, payload, *, stage):
        response = google_seo._request_with_retries(
            lambda: self.request_post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS,
            ),
            stage=stage,
        )
        return google_seo._response_json(response, stage=stage)

    @staticmethod
    def _gsc_endpoint(site_url):
        from urllib.parse import quote

        return (
            f"{google_seo.GSC_SITES_ENDPOINT}/{quote(str(site_url), safe='')}"
            "/searchAnalytics/query"
        )

    def discover_gsc_range(self, site_url, *, today=None):
        today = _as_date(today) or utc_now().date()
        payload = self._post(
            self._gsc_endpoint(site_url),
            {
                "startDate": "2006-01-01",
                "endDate": today.isoformat(),
                "dimensions": ["date"],
                "type": GSC_SEARCH_TYPE,
                "rowLimit": GSC_PAGE_SIZE,
                "startRow": 0,
                "dataState": "final",
            },
            stage="gsc_history_discovery",
        )
        dates = sorted(
            parsed
            for parsed in (
                _as_date(((row or {}).get("keys") or [""])[0])
                for row in payload.get("rows") or []
            )
            if parsed
        )
        return (dates[0], dates[-1]) if dates else (None, None)

    def fetch_gsc_date(self, site_url, slice_date):
        slice_date = _as_date(slice_date)
        endpoint = self._gsc_endpoint(site_url)
        details = []
        start_row = 0
        while start_row < GSC_DAILY_ROW_LIMIT:
            payload = self._post(
                endpoint,
                {
                    "startDate": slice_date.isoformat(),
                    "endDate": slice_date.isoformat(),
                    "dimensions": list(GSC_DETAIL_DIMENSIONS),
                    "type": GSC_SEARCH_TYPE,
                    "rowLimit": GSC_PAGE_SIZE,
                    "startRow": start_row,
                    "dataState": "final",
                },
                stage="gsc_daily_details",
            )
            rows = list(payload.get("rows") or [])
            if not rows:
                break
            for row in rows:
                keys = list((row or {}).get("keys") or []) + ["", "", "", ""]
                details.append(
                    {
                        "query": str(keys[0] or ""),
                        "page_url": str(keys[1] or ""),
                        "country_code": str(keys[2] or ""),
                        "device": str(keys[3] or ""),
                        "clicks": _decimal((row or {}).get("clicks")),
                        "impressions": _decimal((row or {}).get("impressions")),
                        "ctr": _decimal((row or {}).get("ctr")),
                        "average_position": _decimal((row or {}).get("position")),
                    }
                )
            start_row += len(rows)
            if len(rows) < GSC_PAGE_SIZE:
                break

        totals_payload = self._post(
            endpoint,
            {
                "startDate": slice_date.isoformat(),
                "endDate": slice_date.isoformat(),
                "type": GSC_SEARCH_TYPE,
                "rowLimit": 1,
                "startRow": 0,
                "dataState": "final",
            },
            stage="gsc_daily_totals",
        )
        total_row = ((totals_payload.get("rows") or [{}])[0]) or {}
        truncated = len(details) >= GSC_DAILY_ROW_LIMIT
        return {
            "date": slice_date,
            "total": {
                "clicks": _decimal(total_row.get("clicks")),
                "impressions": _decimal(total_row.get("impressions")),
                "ctr": _decimal(total_row.get("ctr")),
                "average_position": _decimal(total_row.get("position")),
                "is_final": True,
                "is_complete": not truncated,
                "is_truncated": truncated,
            },
            "details": details,
            "rows_received": len(details) + 1,
        }

    def ga4_property_metadata(self, property_id):
        property_id = _clean_property_id(property_id)
        endpoint = f"https://analyticsadmin.googleapis.com/v1beta/{property_id}"
        payload = self._get(endpoint, stage="ga4_property_metadata")
        return {
            "property_id": property_id,
            "name": str(payload.get("displayName") or property_id),
            "timezone": str(payload.get("timeZone") or "UTC"),
            "currency": str(payload.get("currencyCode") or ""),
        }

    @staticmethod
    def _organic_filter():
        return {
            "filter": {
                "fieldName": "sessionDefaultChannelGroup",
                "stringFilter": {"matchType": "EXACT", "value": "Organic Search"},
            }
        }

    def compatible_ga4_dimensions(self, property_id):
        property_id = _clean_property_id(property_id)
        dimensions = (*GA4_REQUIRED_DIMENSIONS, GA4_OPTIONAL_DIMENSION)
        payload = self._post(
            f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:checkCompatibility",
            {
                "dimensions": [{"name": name} for name in dimensions],
                "metrics": [{"name": name} for name in GA4_METRICS],
                "dimensionFilter": self._organic_filter(),
            },
            stage="ga4_compatibility",
        )
        compatible_dimensions = {
            str(((row or {}).get("dimensionMetadata") or {}).get("apiName") or "")
            for row in payload.get("dimensionCompatibilities") or []
            if str((row or {}).get("compatibility") or "") == "COMPATIBLE"
        }
        compatible_metrics = {
            str(((row or {}).get("metricMetadata") or {}).get("apiName") or "")
            for row in payload.get("metricCompatibilities") or []
            if str((row or {}).get("compatibility") or "") == "COMPATIBLE"
        }
        if not set(GA4_REQUIRED_DIMENSIONS).issubset(compatible_dimensions):
            raise SEOImportError(
                "The selected Analytics property does not support the required organic dimensions.",
                code="ga4_dimensions_incompatible",
                retryable=False,
            )
        if not set(GA4_METRICS).issubset(compatible_metrics):
            raise SEOImportError(
                "The selected Analytics property does not support the required organic metrics.",
                code="ga4_metrics_incompatible",
                retryable=False,
            )
        return (*GA4_REQUIRED_DIMENSIONS, *(
            (GA4_OPTIONAL_DIMENSION,) if GA4_OPTIONAL_DIMENSION in compatible_dimensions else ()
        ))

    def discover_ga4_earliest_date(self, property_id, latest_date):
        property_id = _clean_property_id(property_id)
        payload = self._post(
            f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:runReport",
            {
                "dateRanges": [{"startDate": "2015-08-14", "endDate": _as_date(latest_date).isoformat()}],
                "dimensions": [{"name": "date"}],
                "metrics": [{"name": "sessions"}],
                "dimensionFilter": self._organic_filter(),
                "orderBys": [{"dimension": {"dimensionName": "date"}, "desc": False}],
                "limit": "1",
                "offset": "0",
            },
            stage="ga4_history_discovery",
        )
        rows = payload.get("rows") or []
        if not rows:
            return None
        raw = str((((rows[0] or {}).get("dimensionValues") or [{}])[0]).get("value") or "")
        return _as_date(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}") if len(raw) == 8 else None

    def fetch_ga4_date(self, property_id, slice_date, *, dimensions, currency=""):
        property_id = _clean_property_id(property_id)
        slice_date = _as_date(slice_date)
        endpoint = f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:runReport"
        rows_out = []
        offset = 0
        row_count = None
        response_metadata = {}
        while row_count is None or offset < row_count:
            payload = self._post(
                endpoint,
                {
                    "dateRanges": [{"startDate": slice_date.isoformat(), "endDate": slice_date.isoformat()}],
                    "dimensions": [{"name": name} for name in dimensions],
                    "metrics": [{"name": name} for name in GA4_METRICS],
                    "dimensionFilter": self._organic_filter(),
                    "limit": str(GA4_PAGE_SIZE),
                    "offset": str(offset),
                    "keepEmptyRows": False,
                },
                stage="ga4_daily_landing_pages",
            )
            response_metadata = dict(payload.get("metadata") or response_metadata)
            row_count = _integer(payload.get("rowCount"))
            rows = list(payload.get("rows") or [])
            if not rows:
                break
            dimension_headers = [str(row.get("name") or "") for row in payload.get("dimensionHeaders") or []]
            metric_headers = [str(row.get("name") or "") for row in payload.get("metricHeaders") or []]
            for row in rows:
                dim_values = [str((value or {}).get("value") or "") for value in (row or {}).get("dimensionValues") or []]
                metric_values = [str((value or {}).get("value") or "0") for value in (row or {}).get("metricValues") or []]
                dims = dict(zip(dimension_headers, dim_values))
                metrics = dict(zip(metric_headers, metric_values))
                rows_out.append(
                    {
                        "landing_page_path_query": dims.get("landingPagePlusQueryString", ""),
                        "hostname": dims.get("hostname", ""),
                        "country_id": dims.get("countryId", ""),
                        "device_category": dims.get("deviceCategory", ""),
                        "session_channel_group": dims.get("sessionDefaultChannelGroup", "Organic Search"),
                        "sessions": _decimal(metrics.get("sessions")),
                        "engaged_sessions": _decimal(metrics.get("engagedSessions")),
                        "engagement_rate": _decimal(metrics.get("engagementRate")),
                        "user_engagement_duration": _decimal(metrics.get("userEngagementDuration")),
                        "transactions": _decimal(metrics.get("transactions")),
                        "purchase_revenue": _decimal(metrics.get("purchaseRevenue")),
                    }
                )
            offset += len(rows)
        metadata_currency = str(response_metadata.get("currencyCode") or currency or "")
        return {
            "date": slice_date,
            "rows": rows_out,
            "rows_received": len(rows_out),
            "currency": metadata_currency,
            "timezone": str(response_metadata.get("timeZone") or ""),
            "is_thresholded": bool(response_metadata.get("subjectToThresholding")),
        }


def _clean_run(row):
    row = dict(row or {})
    for field in (
        "requested_start_date", "requested_end_date", "completed_start_date",
        "completed_end_date", "active_slice_date", "checkpoint_date", "latest_stored_data_date",
        "started_at", "completed_at", "lease_expires_at", "created_at", "updated_at",
    ):
        row[field] = _iso(row.get(field))
    for field in ("rows_received", "rows_inserted", "rows_replaced", "rows_rejected", "attempt_count"):
        row[field] = _integer(row.get(field))
    return row


class PostgresSEOImportStore:
    def __init__(self, backend=None):
        self.backend = backend
        self._schema_ready = False

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend

        return supabase_backend

    def ensure_schema(self):
        if self._schema_ready:
            return
        migration = BASE_DIR / "migrations" / SEO_IMPORT_MIGRATION
        if not migration.is_file():
            raise SEOImportError("SEO import storage is unavailable.", code="migration_missing")
        try:
            with self._backend().connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(migration.read_text(encoding="utf-8"))
                conn.commit()
        except Exception as error:
            raise SEOImportError("SEO import storage could not be prepared.", code="storage_unavailable") from error
        self._schema_ready = True

    def queue_run(self, source, mode, *, property_identifier, requested_by="", start_date=None, end_date=None):
        source = str(source or "").upper()
        mode = str(mode or "").lower()
        if source not in SOURCES or mode not in MODES:
            raise SEOImportError("The requested SEO import is invalid.", code="invalid_import_request", retryable=False)
        self.ensure_schema()
        run_id = str(uuid.uuid4())
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"seo-import:{WORKSPACE_KEY}:{source}",))
                cur.execute(
                    """
                    SELECT * FROM seo_sync_runs
                    WHERE workspace_key=%s AND source=%s AND status IN ('queued', 'running')
                    ORDER BY created_at LIMIT 1
                    """,
                    (WORKSPACE_KEY, source),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """
                        INSERT INTO seo_sync_runs(
                            id, workspace_key, source, property_identifier, mode, status,
                            requested_start_date, requested_end_date, requested_by
                        ) VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            run_id, WORKSPACE_KEY, source, str(property_identifier or "")[:500], mode,
                            _as_date(start_date), _as_date(end_date), str(requested_by or "")[:200],
                        ),
                    )
                    row = cur.fetchone()
            conn.commit()
        return _clean_run(row)

    def claim_next_run(self, lease_owner, *, source="", now=None, lease_seconds=LEASE_SECONDS):
        self.ensure_schema()
        now = now or utc_now()
        params = [now]
        source_clause = ""
        if source:
            source_clause = " AND source=%s"
            params.append(str(source).upper())
        params.extend([str(lease_owner or "")[:200], now, now + timedelta(seconds=lease_seconds)])
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH candidate AS (
                        SELECT id FROM seo_sync_runs
                        WHERE status IN ('queued', 'running')
                          AND (status='queued' OR lease_expires_at IS NULL OR lease_expires_at < %s)
                          {source_clause}
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE seo_sync_runs AS run
                    SET status='running', lease_owner=%s,
                        started_at=COALESCE(started_at, %s), lease_expires_at=%s,
                        attempt_count=attempt_count + 1, updated_at=now()
                    FROM candidate
                    WHERE run.id=candidate.id
                    RETURNING run.*
                    """,
                    params,
                )
                row = cur.fetchone()
            conn.commit()
        return _clean_run(row) if row else None

    def renew_lease(self, run_id, lease_owner, *, active_slice_date=None, lease_seconds=LEASE_SECONDS):
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_sync_runs SET lease_expires_at=%s, active_slice_date=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING id
                    """,
                    (utc_now() + timedelta(seconds=lease_seconds), _as_date(active_slice_date), run_id, lease_owner),
                )
                renewed = bool(cur.fetchone())
            conn.commit()
        return renewed

    def prepare_run_range(self, run_id, lease_owner, start_date, end_date):
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_sync_runs
                    SET requested_start_date=%s, requested_end_date=%s,
                        active_slice_date=COALESCE(active_slice_date, %s), updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING *
                    """,
                    (_as_date(start_date), _as_date(end_date), _as_date(start_date), run_id, lease_owner),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")
        return _clean_run(row)

    def latest_stored_date(self, source, property_identifier):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT latest_stored_date AS latest FROM seo_data_inventories
                    WHERE workspace_key=%s AND source=%s AND property_identifier=%s
                    """,
                    (WORKSPACE_KEY, str(source or "").upper(), property_identifier),
                )
                row = cur.fetchone() or {}
        return _as_date(row.get("latest"))

    def replace_gsc_date(self, site_url, slice_data):
        slice_date = _as_date(slice_data["date"])
        details = list(slice_data.get("details") or [])
        total = dict(slice_data.get("total") or {})
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM seo_gsc_daily_details
                         WHERE workspace_key=%s AND gsc_site_url=%s AND date=%s AND search_type=%s) AS detail_count,
                        EXISTS(
                            SELECT 1 FROM seo_gsc_daily_totals
                            WHERE workspace_key=%s AND gsc_site_url=%s AND date=%s AND search_type=%s
                        ) AS has_total
                    """,
                    (
                        WORKSPACE_KEY, site_url, slice_date, GSC_SEARCH_TYPE,
                        WORKSPACE_KEY, site_url, slice_date, GSC_SEARCH_TYPE,
                    ),
                )
                previous_row = cur.fetchone() or {}
                previous = _integer(previous_row.get("detail_count"))
                previous_rows = previous + int(bool(previous_row.get("has_total")))
                cur.execute(
                    "DELETE FROM seo_gsc_daily_details WHERE workspace_key=%s AND gsc_site_url=%s AND date=%s AND search_type=%s",
                    (WORKSPACE_KEY, site_url, slice_date, GSC_SEARCH_TYPE),
                )
                cur.execute(
                    "DELETE FROM seo_gsc_daily_totals WHERE workspace_key=%s AND gsc_site_url=%s AND date=%s AND search_type=%s",
                    (WORKSPACE_KEY, site_url, slice_date, GSC_SEARCH_TYPE),
                )
                cur.execute(
                    """
                    INSERT INTO seo_gsc_daily_totals(
                        workspace_key, gsc_site_url, date, search_type, clicks, impressions,
                        ctr, average_position, is_final, is_complete, is_truncated
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        WORKSPACE_KEY, site_url, slice_date, GSC_SEARCH_TYPE,
                        total.get("clicks", 0), total.get("impressions", 0), total.get("ctr", 0),
                        total.get("average_position", 0), bool(total.get("is_final", True)),
                        bool(total.get("is_complete", True)), bool(total.get("is_truncated", False)),
                    ),
                )
                if details:
                    cur.executemany(
                        """
                        INSERT INTO seo_gsc_daily_details(
                            workspace_key, gsc_site_url, date, dimension_key_hash,
                            query, page_url, country_code,
                            device, search_type, clicks, impressions, ctr, average_position,
                            is_final, is_complete, is_truncated
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                        """,
                        [
                            (
                                WORKSPACE_KEY, site_url, slice_date,
                                dimension_key_hash(
                                    row.get("query", ""), row.get("page_url", ""),
                                    row.get("country_code", ""), row.get("device", ""), GSC_SEARCH_TYPE,
                                ),
                                row.get("query", ""),
                                row.get("page_url", ""), row.get("country_code", ""), row.get("device", ""),
                                GSC_SEARCH_TYPE, row.get("clicks", 0), row.get("impressions", 0),
                                row.get("ctr", 0), row.get("average_position", 0),
                                bool(total.get("is_complete", True)), bool(total.get("is_truncated", False)),
                            )
                            for row in details
                        ],
                    )
                cur.execute(
                    """
                    INSERT INTO seo_data_inventories(
                        workspace_key, source, property_identifier, rows_stored,
                        earliest_stored_date, latest_stored_date
                    ) VALUES (%s, 'GSC', %s, %s, %s, %s)
                    ON CONFLICT (workspace_key, source, property_identifier) DO UPDATE SET
                        rows_stored=GREATEST(seo_data_inventories.rows_stored + %s - %s, 0),
                        earliest_stored_date=LEAST(
                            COALESCE(seo_data_inventories.earliest_stored_date, %s), %s
                        ),
                        latest_stored_date=GREATEST(
                            COALESCE(seo_data_inventories.latest_stored_date, %s), %s
                        ),
                        updated_at=now()
                    """,
                    (
                        WORKSPACE_KEY, site_url, len(details) + 1, slice_date, slice_date,
                        len(details) + 1, previous_rows, slice_date, slice_date, slice_date, slice_date,
                    ),
                )
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET gsc_earliest_stored_date=(
                            SELECT earliest_stored_date FROM seo_data_inventories
                            WHERE workspace_key=%s AND source='GSC' AND property_identifier=%s
                        ),
                        gsc_data_through_date=(
                            SELECT latest_stored_date FROM seo_data_inventories
                            WHERE workspace_key=%s AND source='GSC' AND property_identifier=%s
                        ),
                        gsc_import_status='running', gsc_import_error='', updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (
                        WORKSPACE_KEY, site_url, WORKSPACE_KEY, site_url, WORKSPACE_KEY,
                    ),
                )
            conn.commit()
        return {"inserted": len(details) + 1, "replaced": previous_rows}

    def replace_ga4_date(self, property_id, slice_data, *, property_timezone="", property_currency=""):
        slice_date = _as_date(slice_data["date"])
        rows = list(slice_data.get("rows") or [])
        currency = str(slice_data.get("currency") or property_currency or "")[:20]
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS count FROM seo_ga4_daily_landing_pages WHERE workspace_key=%s AND ga4_property_id=%s AND date=%s",
                    (WORKSPACE_KEY, property_id, slice_date),
                )
                previous = _integer((cur.fetchone() or {}).get("count"))
                cur.execute(
                    "DELETE FROM seo_ga4_daily_landing_pages WHERE workspace_key=%s AND ga4_property_id=%s AND date=%s",
                    (WORKSPACE_KEY, property_id, slice_date),
                )
                if rows:
                    cur.executemany(
                        """
                        INSERT INTO seo_ga4_daily_landing_pages(
                            workspace_key, ga4_property_id, date, dimension_key_hash,
                            landing_page_path_query, hostname,
                            country_id, device_category, session_channel_group, sessions, engaged_sessions,
                            engagement_rate, user_engagement_duration, transactions, purchase_revenue,
                            property_currency, revenue_basis, is_complete, is_thresholded
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                        """,
                        [
                            (
                                WORKSPACE_KEY, property_id, slice_date,
                                dimension_key_hash(
                                    row.get("landing_page_path_query", ""), row.get("hostname", ""),
                                    row.get("country_id", ""), row.get("device_category", ""),
                                    row.get("session_channel_group", "Organic Search"),
                                ),
                                row.get("landing_page_path_query", ""), row.get("hostname", ""),
                                row.get("country_id", ""), row.get("device_category", ""),
                                row.get("session_channel_group", "Organic Search"), row.get("sessions", 0),
                                row.get("engaged_sessions", 0), row.get("engagement_rate", 0),
                                row.get("user_engagement_duration", 0), row.get("transactions", 0),
                                row.get("purchase_revenue", 0), currency, GA4_REVENUE_BASIS,
                                bool(slice_data.get("is_thresholded", False)),
                            )
                            for row in rows
                        ],
                    )
                cur.execute(
                    """
                    INSERT INTO seo_data_inventories(
                        workspace_key, source, property_identifier, rows_stored,
                        earliest_stored_date, latest_stored_date
                    ) VALUES (%s, 'GA4', %s, %s, %s, %s)
                    ON CONFLICT (workspace_key, source, property_identifier) DO UPDATE SET
                        rows_stored=GREATEST(seo_data_inventories.rows_stored + %s - %s, 0),
                        earliest_stored_date=LEAST(
                            COALESCE(seo_data_inventories.earliest_stored_date, %s), %s
                        ),
                        latest_stored_date=GREATEST(
                            COALESCE(seo_data_inventories.latest_stored_date, %s), %s
                        ),
                        updated_at=now()
                    """,
                    (
                        WORKSPACE_KEY, property_id, len(rows), slice_date, slice_date,
                        len(rows), previous, slice_date, slice_date, slice_date, slice_date,
                    ),
                )
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET ga4_earliest_stored_date=(
                            SELECT earliest_stored_date FROM seo_data_inventories
                            WHERE workspace_key=%s AND source='GA4' AND property_identifier=%s
                        ),
                        ga4_data_through_date=(
                            SELECT latest_stored_date FROM seo_data_inventories
                            WHERE workspace_key=%s AND source='GA4' AND property_identifier=%s
                        ),
                        ga4_property_timezone=%s, ga4_property_currency=%s,
                        ga4_import_status='running', ga4_import_error='', updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (
                        WORKSPACE_KEY, property_id, WORKSPACE_KEY, property_id,
                        str(property_timezone or slice_data.get("timezone") or "")[:100],
                        currency, WORKSPACE_KEY,
                    ),
                )
            conn.commit()
        return {"inserted": len(rows), "replaced": previous}

    def checkpoint_date(self, run_id, lease_owner, slice_date, *, received, inserted, replaced, rejected=0):
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_sync_runs
                    SET checkpoint_date=GREATEST(COALESCE(checkpoint_date, %s), %s),
                        active_slice_date=%s,
                        completed_start_date=LEAST(COALESCE(completed_start_date, %s), %s),
                        completed_end_date=GREATEST(COALESCE(completed_end_date, %s), %s),
                        latest_stored_data_date=GREATEST(COALESCE(latest_stored_data_date, %s), %s),
                        rows_received=rows_received + %s, rows_inserted=rows_inserted + %s,
                        rows_replaced=rows_replaced + %s, rows_rejected=rows_rejected + %s,
                        lease_expires_at=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING id
                    """,
                    (
                        slice_date, slice_date, slice_date,
                        slice_date, slice_date,
                        slice_date, slice_date,
                        slice_date, slice_date,
                        received, inserted, replaced, rejected,
                        utc_now() + timedelta(seconds=LEASE_SECONDS), run_id, lease_owner,
                    ),
                )
                ok = bool(cur.fetchone())
            conn.commit()
        if not ok:
            raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")

    def complete_run(self, run_id, lease_owner, source, *, status="completed"):
        source = str(source).upper()
        import_status_column = "gsc_import_status" if source == "GSC" else "ga4_import_status"
        error_column = "gsc_import_error" if source == "GSC" else "ga4_import_error"
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_sync_runs SET status=%s, completed_at=now(), active_slice_date=NULL,
                        lease_owner='', lease_expires_at=NULL, error_code='', error_summary='', updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING *
                    """,
                    (status, run_id, lease_owner),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        f"UPDATE seo_google_connections SET {import_status_column}=%s, {error_column}='', last_successful_sync_at=now(), updated_at=now() WHERE workspace_key=%s",
                        (status, WORKSPACE_KEY),
                    )
            conn.commit()
        clean = _clean_run(row)
        if clean:
            record_activity_log(
                "google_seo_import_completed",
                "SEO / Overview",
                f"{source} {clean.get('mode') or 'data'} import completed",
                entity_type="seo_sync_run",
                entity_id=run_id,
                metadata={
                    "source": source,
                    "mode": clean.get("mode"),
                    "rows_received": clean.get("rows_received", 0),
                    "rows_inserted": clean.get("rows_inserted", 0),
                    "rows_replaced": clean.get("rows_replaced", 0),
                    "latest_stored_data_date": clean.get("latest_stored_data_date", ""),
                },
                actor=str(clean.get("requested_by") or "seo_import_worker")[:200],
            )
        return clean

    def fail_run(self, run_id, lease_owner, source, *, slice_date, error_code, error_message, retry_count, partial=False):
        source = str(source).upper()
        error_id = str(uuid.uuid4())
        status = "partial" if partial else "failed"
        import_status_column = "gsc_import_status" if source == "GSC" else "ga4_import_status"
        error_column = "gsc_import_error" if source == "GSC" else "ga4_import_error"
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_sync_runs
                    SET status=%s, completed_at=now(), lease_owner='', lease_expires_at=NULL,
                        error_code=%s, error_summary=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING *
                    """,
                    (
                        status, str(error_code)[:100], str(error_message)[:300], run_id, lease_owner,
                    ),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        INSERT INTO seo_sync_errors(
                            id, sync_run_id, workspace_key, source, slice_date,
                            error_code, error_message, retry_count
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            error_id, run_id, WORKSPACE_KEY, source, _as_date(slice_date),
                            str(error_code or "seo_import_failed")[:100],
                            str(error_message or "SEO import failed.")[:300], int(retry_count or 0),
                        ),
                    )
                    cur.execute(
                        f"UPDATE seo_google_connections SET {import_status_column}=%s, {error_column}=%s, updated_at=now() WHERE workspace_key=%s",
                        (status, str(error_message or "SEO import failed.")[:300], WORKSPACE_KEY),
                    )
            conn.commit()
        clean = _clean_run(row)
        if clean:
            _log_import_failure(
                run_id=run_id,
                source=source,
                error_code=error_code,
                slice_date=slice_date,
            )
            record_activity_log(
                "google_seo_import_failed",
                "SEO / Overview",
                f"{source} import needs attention",
                entity_type="seo_sync_run",
                entity_id=run_id,
                metadata={
                    "source": source,
                    "mode": clean.get("mode"),
                    "status": clean.get("status"),
                    "error_code": str(error_code or "seo_import_failed")[:100],
                    "slice_date": _iso(slice_date),
                },
                actor=str(clean.get("requested_by") or "seo_import_worker")[:200],
            )
        return clean

    def recent_status(self):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (source) * FROM seo_sync_runs
                    WHERE workspace_key=%s
                      AND (
                          (source='GSC' AND property_identifier=(
                              SELECT gsc_site_url FROM seo_google_connections WHERE workspace_key=%s
                          ))
                          OR
                          (source='GA4' AND property_identifier=(
                              SELECT ga4_property_id FROM seo_google_connections WHERE workspace_key=%s
                          ))
                      )
                    ORDER BY source, created_at DESC
                    """,
                    (WORKSPACE_KEY, WORKSPACE_KEY, WORKSPACE_KEY),
                )
                runs = {_clean_run(row)["source"]: _clean_run(row) for row in cur.fetchall() or []}
                cur.execute(
                    """
                    SELECT source, rows_stored FROM seo_data_inventories
                    WHERE workspace_key=%s
                      AND (
                          (source='GSC' AND property_identifier=(
                              SELECT gsc_site_url FROM seo_google_connections WHERE workspace_key=%s
                          ))
                          OR
                          (source='GA4' AND property_identifier=(
                              SELECT ga4_property_id FROM seo_google_connections WHERE workspace_key=%s
                          ))
                      )
                    """,
                    (WORKSPACE_KEY, WORKSPACE_KEY, WORKSPACE_KEY),
                )
                counts = {str(row.get("source") or ""): _integer(row.get("rows_stored")) for row in cur.fetchall() or []}
        for source in SOURCES:
            runs.setdefault(source, {})
        runs["GSC"]["rows_stored"] = counts.get("GSC", 0)
        runs["GA4"]["rows_stored"] = counts.get("GA4", 0)
        return runs

    def retry_run(self, run_id, *, requested_by):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM seo_sync_runs WHERE id=%s AND status IN ('partial', 'failed')", (run_id,))
                prior = cur.fetchone() or {}
        if not prior:
            raise SEOImportError("The failed import could not be found.", code="import_run_missing", retryable=False)
        retry_start = _as_date(prior.get("checkpoint_date"))
        if retry_start:
            retry_start += timedelta(days=1)
        else:
            retry_start = _as_date(prior.get("requested_start_date"))
        return self.queue_run(
            prior.get("source"), prior.get("mode"), property_identifier=prior.get("property_identifier"),
            requested_by=requested_by, start_date=retry_start, end_date=prior.get("requested_end_date"),
        )


_DEFAULT_IMPORT_STORE = None


def default_import_store():
    global _DEFAULT_IMPORT_STORE
    if _DEFAULT_IMPORT_STORE is None:
        _DEFAULT_IMPORT_STORE = PostgresSEOImportStore()
    return _DEFAULT_IMPORT_STORE


def queue_imports(user, mode, *, import_store=None, connection_store=None):
    google_seo.require_admin(user)
    import_store = import_store or default_import_store()
    connection_store = connection_store or google_seo.default_store()
    connection = connection_store.get_connection_secret()
    if not connection.get("encrypted_refresh_token"):
        raise SEOImportError("Connect Google before importing SEO data.", code="google_connection_required", retryable=False)
    properties = {
        "GSC": str(connection.get("gsc_site_url") or ""),
        "GA4": str(connection.get("ga4_property_id") or ""),
    }
    if not all(properties.values()):
        raise SEOImportError("Select both Google properties before importing.", code="property_selection_required", retryable=False)
    runs = [
        import_store.queue_run(
            source,
            mode,
            property_identifier=properties[source],
            requested_by=str(user.get("id") or "")[:200],
        )
        for source in SOURCES
    ]
    record_activity_log(
        "google_seo_import_queued",
        "SEO / Overview",
        f"Google SEO {mode} import queued",
        entity_type="seo_sync_run",
        entity_id=",".join(str(row.get("id") or "") for row in runs),
        metadata={
            "actor_id": user.get("id") or "",
            "actor_email": user.get("email") or "",
            "actor_role": user.get("role") or "",
            "actor_timezone": os_accounts.timezone_for_user(user),
            "mode": mode,
            "sources": list(SOURCES),
        },
        actor=str(user.get("display_name") or user.get("id") or "sports_cave_os")[:200],
    )
    return runs


def retry_import(user, run_id, *, import_store=None):
    google_seo.require_admin(user)
    return (import_store or default_import_store()).retry_run(
        run_id,
        requested_by=str(user.get("id") or "")[:200],
    )


class SEOImportWorker:
    def __init__(
        self,
        *,
        import_store=None,
        connection_store=None,
        config_loader=google_seo.load_config,
        access_token_loader=google_seo.access_token_for_connection,
        client_factory=GoogleSEOReportingClient,
        worker_id="",
        sleep=time.sleep,
    ):
        self.import_store = import_store or default_import_store()
        self.connection_store = connection_store or google_seo.default_store()
        self.config_loader = config_loader
        self.access_token_loader = access_token_loader
        self.client_factory = client_factory
        self.worker_id = str(worker_id or f"seo-worker-{secrets.token_hex(6)}")[:200]
        self.sleep = sleep

    def run_once(self, *, source=""):
        run = self.import_store.claim_next_run(self.worker_id, source=source)
        if not run:
            return None
        return self._process(run)

    def _process(self, run):
        source = str(run.get("source") or "").upper()
        property_identifier = str(run.get("property_identifier") or "")
        try:
            config = self.config_loader()
            access_token, connection = self.access_token_loader(self.connection_store, config)
            selected = str(
                (connection.get("gsc_site_url") if source == "GSC" else connection.get("ga4_property_id"))
                or ""
            )
            if property_identifier != selected:
                raise SEOImportError(
                    "The selected Google property changed after this import was queued.",
                    code="queued_property_changed",
                    retryable=False,
                )
            client = self.client_factory(access_token)
            if source == "GSC":
                return self._process_gsc(run, client, property_identifier)
            if source == "GA4":
                return self._process_ga4(run, client, property_identifier)
            raise SEOImportError("The SEO import source is unsupported.", code="source_unsupported", retryable=False)
        except Exception as error:
            code, message = sanitize_import_error(error)
            return self.import_store.fail_run(
                run["id"], self.worker_id, source, slice_date=run.get("active_slice_date"),
                error_code=code, error_message=message, retry_count=0,
                partial=bool(run.get("checkpoint_date")),
            )

    def _resolved_start(self, run, earliest, latest, latest_stored):
        requested_start = _as_date(run.get("requested_start_date"))
        requested_end = _as_date(run.get("requested_end_date"))
        if requested_start and requested_end:
            start_date, end_date = requested_start, requested_end
        elif run.get("mode") == "historical":
            start_date, end_date = earliest, latest
        else:
            start_date, end_date = daily_refresh_range(earliest, latest, latest_stored)
        checkpoint = _as_date(run.get("checkpoint_date"))
        if checkpoint:
            start_date = max(start_date, checkpoint + timedelta(days=1))
        return start_date, end_date

    def _fetch_with_retry(self, fetch):
        last_error = None
        for attempt in range(1, MAX_SLICE_RETRIES + 1):
            try:
                return fetch(), attempt
            except Exception as error:
                last_error = error
                if isinstance(error, SEOImportError) and not error.retryable:
                    break
                if attempt < MAX_SLICE_RETRIES:
                    self.sleep(min(2 ** (attempt - 1), 4))
        raise last_error

    def _process_gsc(self, run, client, site_url):
        earliest, latest = client.discover_gsc_range(site_url)
        latest_stored = self.import_store.latest_stored_date("GSC", site_url)
        start_date, end_date = self._resolved_start(run, earliest, latest, latest_stored)
        if not start_date or not end_date or start_date > end_date:
            return self.import_store.complete_run(run["id"], self.worker_id, "GSC")
        run = self.import_store.prepare_run_range(run["id"], self.worker_id, start_date, end_date)
        for slice_date in date_sequence(start_date, end_date):
            if not self.import_store.renew_lease(run["id"], self.worker_id, active_slice_date=slice_date):
                raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")
            try:
                slice_data, _attempts = self._fetch_with_retry(lambda: client.fetch_gsc_date(site_url, slice_date))
                if not self.import_store.renew_lease(run["id"], self.worker_id, active_slice_date=slice_date):
                    raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")
                result = self.import_store.replace_gsc_date(site_url, slice_data)
                self.import_store.checkpoint_date(
                    run["id"], self.worker_id, slice_date,
                    received=slice_data.get("rows_received", 0), inserted=result["inserted"], replaced=result["replaced"],
                )
                run["checkpoint_date"] = slice_date
            except Exception as error:
                code, message = sanitize_import_error(error)
                return self.import_store.fail_run(
                    run["id"], self.worker_id, "GSC", slice_date=slice_date,
                    error_code=code, error_message=message, retry_count=MAX_SLICE_RETRIES,
                    partial=bool(run.get("checkpoint_date")),
                )
        return self.import_store.complete_run(run["id"], self.worker_id, "GSC")

    def _process_ga4(self, run, client, property_id):
        metadata = client.ga4_property_metadata(property_id)
        try:
            property_today = datetime.now(ZoneInfo(metadata["timezone"])).date()
        except ZoneInfoNotFoundError:
            property_today = utc_now().date()
        latest = property_today - timedelta(days=1)
        earliest = client.discover_ga4_earliest_date(property_id, latest)
        latest_stored = self.import_store.latest_stored_date("GA4", property_id)
        start_date, end_date = self._resolved_start(run, earliest, latest, latest_stored)
        if not start_date or not end_date or start_date > end_date:
            return self.import_store.complete_run(run["id"], self.worker_id, "GA4")
        dimensions = client.compatible_ga4_dimensions(property_id)
        run = self.import_store.prepare_run_range(run["id"], self.worker_id, start_date, end_date)
        for slice_date in date_sequence(start_date, end_date):
            if not self.import_store.renew_lease(run["id"], self.worker_id, active_slice_date=slice_date):
                raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")
            try:
                slice_data, _attempts = self._fetch_with_retry(
                    lambda: client.fetch_ga4_date(
                        property_id, slice_date, dimensions=dimensions, currency=metadata["currency"],
                    )
                )
                if not self.import_store.renew_lease(run["id"], self.worker_id, active_slice_date=slice_date):
                    raise SEOImportError("The SEO import lease was lost.", code="import_lease_lost")
                result = self.import_store.replace_ga4_date(
                    property_id, slice_data,
                    property_timezone=metadata["timezone"], property_currency=metadata["currency"],
                )
                self.import_store.checkpoint_date(
                    run["id"], self.worker_id, slice_date,
                    received=slice_data.get("rows_received", 0), inserted=result["inserted"], replaced=result["replaced"],
                )
                run["checkpoint_date"] = slice_date
            except Exception as error:
                code, message = sanitize_import_error(error)
                return self.import_store.fail_run(
                    run["id"], self.worker_id, "GA4", slice_date=slice_date,
                    error_code=code, error_message=message, retry_count=MAX_SLICE_RETRIES,
                    partial=bool(run.get("checkpoint_date")),
                )
        return self.import_store.complete_run(run["id"], self.worker_id, "GA4")


def queue_daily_source(source, *, import_store=None, connection_store=None, requested_by="render-cron"):
    import_store = import_store or default_import_store()
    connection_store = connection_store or google_seo.default_store()
    connection = connection_store.get_connection_secret()
    source = str(source or "").upper()
    if source not in SOURCES:
        raise SEOImportError("The requested Google source is invalid.", code="source_invalid")
    properties = {
        "GSC": str(connection.get("gsc_site_url") or ""),
        "GA4": str(connection.get("ga4_property_id") or ""),
    }
    if not connection.get("encrypted_refresh_token"):
        raise SEOImportError("Google must be connected before analytics can refresh.", code="google_connection_required")
    if not properties[source]:
        raise SEOImportError(
            f"Select the {source} property before refreshing that source.",
            code="property_selection_required",
        )
    return import_store.queue_run(
        source, "daily", property_identifier=properties[source], requested_by=requested_by,
    )


def queue_daily_runs(*, import_store=None, connection_store=None, requested_by="render-cron"):
    return [
        queue_daily_source(
            source,
            import_store=import_store,
            connection_store=connection_store,
            requested_by=requested_by,
        )
        for source in SOURCES
    ]


def run_complete_daily_pipeline():
    if os.getenv("SEO_GOOGLE_IMPORT_DAILY_ONLY", "").strip() == "1":
        queue_daily_runs()
        worker = SEOImportWorker()
        for source in SOURCES:
            worker.run_once(source=source)
        return {"status": "legacy_google_daily_only"}
    import seo_growth_intelligence

    return seo_growth_intelligence.run_daily_analytics_refresh(requested_by="render-cron")


def _run_worker_loop(worker, *, once=False, poll_seconds=15):
    while True:
        result = worker.run_once()
        if once:
            return 0
        if result is None:
            time.sleep(max(2, int(poll_seconds)))


def main(argv=None):
    load_dotenv(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Sports Cave SEO import worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker_parser = subparsers.add_parser("worker", help="Process queued SEO imports")
    worker_parser.add_argument("--once", action="store_true")
    worker_parser.add_argument("--poll-seconds", type=int, default=15)
    subparsers.add_parser("daily", help="Queue and process the daily GSC and GA4 refresh")
    args = parser.parse_args(argv)
    worker = SEOImportWorker()
    if args.command == "daily":
        run_complete_daily_pipeline()
        return 0
    return _run_worker_loop(worker, once=args.once, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
