"""Saved GA4 report execution, quality metadata and reconciliation helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import uuid

import analytics_contracts
import google_seo
import google_seo_import


BASE_DIR = Path(__file__).resolve().parent
ANALYTICS_MIGRATION = "20260817_analytics_seo_blog_rebuild.sql"
WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
PAGE_SIZE = 100_000
COMMON_PRESETS = ("Last 7 days", "Last 28 days", "Last 30 days", "Last 90 days")


class AnalyticsReportingError(RuntimeError):
    def __init__(self, message, *, code="analytics_reporting_error", retryable=True):
        super().__init__(str(message or "Analytics reporting could not complete."))
        self.public_message = str(message or "Analytics reporting could not complete.")[:300]
        self.code = str(code or "analytics_reporting_error")[:100]
        self.retryable = bool(retryable)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _number(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def response_quality(metadata, *, complete, returned_rows, expected_rows):
    metadata = dict(metadata or {})
    sampled = bool(metadata.get("samplingMetadatas"))
    thresholded = bool(metadata.get("subjectToThresholding"))
    other_loss = bool(metadata.get("dataLossFromOtherRow"))
    restricted = bool(metadata.get("schemaRestrictionResponse"))
    pagination_complete = bool(complete and returned_rows >= max(0, int(expected_rows or 0)))
    if not pagination_complete or restricted:
        status = "Unavailable"
    elif sampled or thresholded or other_loss:
        status = "Qualified"
    else:
        status = "GA4 verified"
    return {
        "status": status,
        "sampled": sampled,
        "thresholded": thresholded,
        "data_loss_from_other": other_loss,
        "restricted": restricted,
        "pagination_complete": pagination_complete,
        "sampling_percentage": sampling_percentage(metadata),
        "property_quota": dict(metadata.get("propertyQuota") or {}),
        "empty_response_reason": "verified_empty_response" if pagination_complete and expected_rows == 0 else "",
    }


def sampling_percentage(metadata):
    samples = list((metadata or {}).get("samplingMetadatas") or [])
    if not samples:
        return None
    used = sum((_number(row.get("samplesReadCount")) for row in samples), Decimal("0"))
    space = sum((_number(row.get("samplingSpaceSize")) for row in samples), Decimal("0"))
    return None if not space else (used / space) * Decimal("100")


class CanonicalGA4Client:
    def __init__(self, access_token, *, reporting_client=None):
        self.client = reporting_client or google_seo_import.GoogleSEOReportingClient(access_token)
        self._compatibility_cache = {}

    @staticmethod
    def _property(property_id):
        clean = str(property_id or "").strip()
        return clean if clean.startswith("properties/") else f"properties/{clean}"

    def property_metadata(self, property_id):
        return self.client.ga4_property_metadata(self._property(property_id))

    def compatibility(self, property_id, contract, *, metric_override=""):
        contract = analytics_contracts.report_contract(contract) if isinstance(contract, str) else contract
        if contract.realtime:
            return {"compatible": True, "incompatible_dimensions": [], "incompatible_metrics": []}
        metrics = (metric_override,) if metric_override else contract.metrics
        cache_key = (self._property(property_id), contract.key, tuple(metrics))
        if cache_key in self._compatibility_cache:
            return dict(self._compatibility_cache[cache_key])
        payload = self.client._post(
            f"{google_seo.GA4_DATA_ENDPOINT}/{self._property(property_id)}:checkCompatibility",
            {
                "dimensions": [{"name": name} for name in contract.dimensions],
                "metrics": [{"name": name} for name in metrics],
                **(
                    {"dimensionFilter": analytics_contracts.filter_expression(contract.filters)}
                    if contract.filters else {}
                ),
            },
            stage=f"ga4_compatibility_{contract.key}",
        )
        dimension_status = {
            str(((row or {}).get("dimensionMetadata") or {}).get("apiName") or ""):
            str((row or {}).get("compatibility") or "")
            for row in payload.get("dimensionCompatibilities") or []
        }
        metric_status = {
            str(((row or {}).get("metricMetadata") or {}).get("apiName") or ""):
            str((row or {}).get("compatibility") or "")
            for row in payload.get("metricCompatibilities") or []
        }
        bad_dimensions = [name for name in contract.dimensions if dimension_status.get(name) != "COMPATIBLE"]
        bad_metrics = [name for name in metrics if metric_status.get(name) != "COMPATIBLE"]
        result = {
            "compatible": not bad_dimensions and not bad_metrics,
            "incompatible_dimensions": bad_dimensions,
            "incompatible_metrics": bad_metrics,
        }
        self._compatibility_cache[cache_key] = dict(result)
        return result

    def fetch_report(
        self,
        property_id,
        contract,
        start_date,
        end_date,
        *,
        filters=(),
        metric_override="",
        currency="",
    ):
        contract = analytics_contracts.report_contract(contract) if isinstance(contract, str) else contract
        property_id = self._property(property_id)
        compatibility = self.compatibility(property_id, contract, metric_override=metric_override)
        if not compatibility["compatible"]:
            reasons = [
                *(f"dimension:{name}" for name in compatibility["incompatible_dimensions"]),
                *(f"metric:{name}" for name in compatibility["incompatible_metrics"]),
            ]
            raise AnalyticsReportingError(
                f"GA4 report {contract.label} is unavailable: {', '.join(reasons)}",
                code="ga4_contract_incompatible",
                retryable=False,
            )

        spec = analytics_contracts.request_spec(
            contract,
            start_date,
            end_date,
            filters=filters,
            metric_override=metric_override,
        )
        metrics = tuple(spec["metrics"])
        endpoint_method = "runRealtimeReport" if contract.realtime else "runReport"
        endpoint = f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:{endpoint_method}"
        rows_out = []
        metadata = {}
        expected_rows = 0
        offset = 0
        while True:
            request = {
                "dimensions": [{"name": name} for name in contract.dimensions],
                "metrics": [{"name": name} for name in metrics],
                "limit": str(min(PAGE_SIZE, contract.row_limit)),
                "offset": str(offset),
                "keepEmptyRows": False,
                "returnPropertyQuota": True,
            }
            if not contract.realtime:
                request["dateRanges"] = [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}]
            expression = analytics_contracts.filter_expression((*contract.filters, *tuple(filters or ())))
            if expression:
                request["dimensionFilter"] = expression
            if contract.ordering:
                request["orderBys"] = [
                    (
                        {"metric": {"metricName": field}, "desc": bool(desc)}
                        if field in metrics
                        else {"dimension": {"dimensionName": field}, "desc": bool(desc)}
                    )
                    for field, desc in contract.ordering
                    if field in metrics or field in contract.dimensions
                ]
            payload = self.client._post(endpoint, request, stage=f"ga4_contract_{contract.key}")
            metadata = {
                **dict(payload.get("metadata") or metadata),
                **{
                    key: payload.get(key)
                    for key in (
                        "dataLossFromOtherRow", "samplingMetadatas",
                        "schemaRestrictionResponse", "subjectToThresholding", "propertyQuota",
                    )
                    if key in payload
                },
            }
            expected_rows = int(payload.get("rowCount") or 0)
            dimension_headers = [str(row.get("name") or "") for row in payload.get("dimensionHeaders") or []]
            metric_headers = [str(row.get("name") or "") for row in payload.get("metricHeaders") or []]
            page_rows = list(payload.get("rows") or [])
            for row in page_rows:
                dimensions = [str((value or {}).get("value") or "") for value in row.get("dimensionValues") or []]
                metric_values = [str((value or {}).get("value") or "0") for value in row.get("metricValues") or []]
                rows_out.append(
                    {
                        "dimensions": dict(zip(dimension_headers, dimensions)),
                        "metrics": dict(zip(metric_headers, metric_values)),
                    }
                )
            offset += len(page_rows)
            if not page_rows or offset >= expected_rows or offset >= contract.row_limit:
                break

        complete = expected_rows <= contract.row_limit and len(rows_out) >= expected_rows
        quality = response_quality(
            metadata,
            complete=complete,
            returned_rows=len(rows_out),
            expected_rows=expected_rows,
        )
        return {
            "id": str(uuid.uuid4()),
            "workspace_key": WORKSPACE_KEY,
            "property_id": property_id,
            "contract_key": contract.key,
            "request_hash": analytics_contracts.request_hash(property_id, spec, currency=currency),
            "request_spec": spec,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": str(metadata.get("currencyCode") or currency or ""),
            "property_timezone": str(metadata.get("timeZone") or ""),
            "rows": rows_out,
            "metadata": metadata,
            "quality": quality,
            "row_count": len(rows_out),
            "expected_row_count": expected_rows,
            "complete": complete,
            "fetched_at": utc_now().isoformat().replace("+00:00", "Z"),
        }


class PostgresAnalyticsStore:
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
        migration = BASE_DIR / "migrations" / ANALYTICS_MIGRATION
        if not migration.is_file():
            raise AnalyticsReportingError("Analytics storage migration is unavailable.", code="migration_missing")
        try:
            with self._backend().connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(migration.read_text(encoding="utf-8"))
                conn.commit()
        except Exception as error:
            raise AnalyticsReportingError("Analytics storage is unavailable.", code="storage_unavailable") from error
        self._schema_ready = True

    def save_report(self, report):
        report = dict(report or {})
        if not report.get("complete"):
            raise AnalyticsReportingError(
                "An incomplete GA4 response cannot replace the last-good snapshot.",
                code="incomplete_report",
                retryable=False,
            )
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_ga4_report_snapshots(
                        id, workspace_key, property_id, contract_key, request_hash,
                        request_spec, start_date, end_date, property_timezone, property_currency,
                        response_rows, response_metadata, quality_status, row_count,
                        expected_row_count, pagination_complete, fetched_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s, %s, TRUE, %s
                    )
                    ON CONFLICT (workspace_key, property_id, request_hash) DO UPDATE SET
                        id=EXCLUDED.id, request_spec=EXCLUDED.request_spec,
                        response_rows=EXCLUDED.response_rows,
                        response_metadata=EXCLUDED.response_metadata,
                        quality_status=EXCLUDED.quality_status,
                        row_count=EXCLUDED.row_count,
                        expected_row_count=EXCLUDED.expected_row_count,
                        pagination_complete=TRUE, fetched_at=EXCLUDED.fetched_at
                    RETURNING *
                    """,
                    (
                        report.get("id") or str(uuid.uuid4()), WORKSPACE_KEY,
                        report.get("property_id"), report.get("contract_key"), report.get("request_hash"),
                        json.dumps(report.get("request_spec") or {}, default=str),
                        report.get("start_date"), report.get("end_date"),
                        report.get("property_timezone"), report.get("currency"),
                        json.dumps(report.get("rows") or [], default=str),
                        json.dumps({**dict(report.get("metadata") or {}), "quality": report.get("quality") or {}}, default=str),
                        (report.get("quality") or {}).get("status") or "Unavailable",
                        int(report.get("row_count") or 0), int(report.get("expected_row_count") or 0),
                        report.get("fetched_at") or utc_now(),
                    ),
                )
                saved = cur.fetchone() or {}
            conn.commit()
        return dict(saved)

    def record_failure(self, *, property_id, contract_key, request_hash, error):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_ga4_sync_failures(
                        id, workspace_key, property_id, contract_key, request_hash,
                        error_code, error_summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), WORKSPACE_KEY, property_id, contract_key, request_hash,
                        str(getattr(error, "code", "ga4_report_failed"))[:100],
                        str(getattr(error, "public_message", "GA4 report refresh failed."))[:300],
                    ),
                )
            conn.commit()

    def get_report(self, property_id, request_hash):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM analytics_ga4_report_snapshots
                    WHERE workspace_key=%s AND property_id=%s AND request_hash=%s
                      AND pagination_complete=TRUE
                    """,
                    (WORKSPACE_KEY, property_id, request_hash),
                )
                row = cur.fetchone()
        return dict(row or {})

    def latest_report(self, property_id, contract_key):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM analytics_ga4_report_snapshots
                    WHERE workspace_key=%s AND property_id=%s AND contract_key=%s
                      AND pagination_complete=TRUE
                    ORDER BY fetched_at DESC LIMIT 1
                    """,
                    (WORKSPACE_KEY, property_id, contract_key),
                )
                row = cur.fetchone()
        return dict(row or {})

    def report_for_period(self, property_id, contract_key, start_date, end_date):
        """Return only an exact, complete contract/date match."""
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM analytics_ga4_report_snapshots
                    WHERE workspace_key=%s AND property_id=%s AND contract_key=%s
                      AND start_date=%s AND end_date=%s AND pagination_complete=TRUE
                    ORDER BY fetched_at DESC LIMIT 1
                    """,
                    (WORKSPACE_KEY, property_id, contract_key, start_date, end_date),
                )
                row = cur.fetchone()
        return dict(row or {})

    def queue_report(
        self,
        property_id,
        contract_key,
        start_date,
        end_date,
        *,
        currency="",
        requested_by="",
    ):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_ga4_report_queue(
                        id, workspace_key, property_id, contract_key, start_date,
                        end_date, property_currency, requested_by
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (workspace_key, property_id, contract_key, start_date, end_date)
                    DO UPDATE SET
                        status=CASE WHEN analytics_ga4_report_queue.status='completed'
                                    THEN 'completed' ELSE 'queued' END,
                        requested_by=EXCLUDED.requested_by,
                        error_summary='', requested_at=now()
                    RETURNING *
                    """,
                    (
                        str(uuid.uuid4()), WORKSPACE_KEY, property_id, contract_key,
                        start_date, end_date, str(currency or ""), str(requested_by or "")[:200],
                    ),
                )
                row = cur.fetchone() or {}
            conn.commit()
        return dict(row)

    def claim_report_queue(self, limit=20):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE analytics_ga4_report_queue
                    SET status='queued', started_at=NULL,
                        error_summary='Recovered after an interrupted worker.'
                    WHERE workspace_key=%s AND status='running'
                      AND started_at < now() - interval '15 minutes'
                    """,
                    (WORKSPACE_KEY,),
                )
                cur.execute(
                    """
                    WITH candidates AS (
                        SELECT id FROM analytics_ga4_report_queue
                        WHERE workspace_key=%s AND status='queued'
                        ORDER BY requested_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE analytics_ga4_report_queue AS request
                    SET status='running', started_at=now(), error_summary=''
                    FROM candidates WHERE request.id=candidates.id
                    RETURNING request.*
                    """,
                    (WORKSPACE_KEY, int(limit)),
                )
                rows = cur.fetchall() or []
            conn.commit()
        return [dict(row) for row in rows]

    def complete_report_request(self, request_id, *, error=""):
        status = "failed" if error else "completed"
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE analytics_ga4_report_queue
                    SET status=%s, error_summary=%s, completed_at=now()
                    WHERE id=%s RETURNING *
                    """,
                    (status, str(error or "")[:300], request_id),
                )
                row = cur.fetchone() or {}
            conn.commit()
        return dict(row)


def report_metric(report, metric):
    rows = list((report or {}).get("response_rows") or (report or {}).get("rows") or [])
    if not rows:
        return None
    return _number((rows[0].get("metrics") or {}).get(metric))


def reconcile_layers(direct_report, stored_report, rendered_values):
    direct_rows = list((direct_report or {}).get("rows") or [])
    stored_rows = list((stored_report or {}).get("response_rows") or (stored_report or {}).get("rows") or [])
    rendered_values = dict(rendered_values or {})
    result = {
        "direct_request_hash": (direct_report or {}).get("request_hash") or "",
        "stored_request_hash": (stored_report or {}).get("request_hash") or "",
        "divergence": "none",
        "details": "Direct, stored and rendered values match.",
    }
    if result["direct_request_hash"] != result["stored_request_hash"] or direct_rows != stored_rows:
        result.update(divergence="database_save", details="The saved rows differ from the exact direct GA4 response.")
        return result
    expected = direct_rows[0].get("metrics") if direct_rows else {}
    for metric, value in expected.items():
        rendered = rendered_values.get(metric)
        tolerance = Decimal("0.01") if "revenue" in metric.casefold() else Decimal("0")
        numeric_match = abs(_number(rendered) - _number(value)) <= tolerance
        if rendered is None or not numeric_match:
            result.update(
                divergence="application_reader_or_renderer",
                details=f"Rendered {metric}={rendered_values.get(metric)!r}; saved/direct value={value!r}.",
            )
            return result
    return result


def prewarm_common_reports(
    client,
    store,
    *,
    property_id,
    property_timezone,
    property_currency="",
    today=None,
):
    written = 0
    failures = []
    contract_keys = tuple(key for key in analytics_contracts.GA4_REPORT_CONTRACTS if key != "realtime")
    seen_ranges = set()
    for preset in COMMON_PRESETS:
        period = analytics_contracts.resolve_date_range(
            preset,
            timezone_name=property_timezone,
            comparison="Previous period",
            today=today,
        )
        ranges = (
            (period["start_date"], period["end_date"], preset),
            (period["previous_start_date"], period["previous_end_date"], f"{preset} comparison"),
        )
        for start_date, end_date, range_label in ranges:
            if (start_date, end_date) in seen_ranges:
                continue
            seen_ranges.add((start_date, end_date))
            for contract_key in contract_keys:
                try:
                    report = client.fetch_report(
                        property_id,
                        contract_key,
                        start_date,
                        end_date,
                        currency=property_currency,
                    )
                    store.save_report(report)
                    written += 1
                except Exception as error:
                    spec = analytics_contracts.request_spec(contract_key, start_date, end_date)
                    digest = analytics_contracts.request_hash(property_id, spec, currency=property_currency)
                    store.record_failure(
                        property_id=property_id,
                        contract_key=contract_key,
                        request_hash=digest,
                        error=error,
                    )
                    failures.append({"preset": range_label, "contract": contract_key, "error": str(error)[:300]})
    realtime_day = analytics_contracts.property_today(property_timezone) if today is None else today
    try:
        report = client.fetch_report(
            property_id,
            "realtime",
            realtime_day,
            realtime_day,
            currency=property_currency,
        )
        store.save_report(report)
        written += 1
    except Exception as error:
        spec = analytics_contracts.request_spec("realtime", realtime_day, realtime_day)
        store.record_failure(
            property_id=property_id,
            contract_key="realtime",
            request_hash=analytics_contracts.request_hash(property_id, spec, currency=property_currency),
            error=error,
        )
        failures.append({"preset": "Realtime", "contract": "realtime", "error": str(error)[:300]})
    return {"status": "partial" if failures else "completed", "written": written, "failures": failures}


def process_custom_report_queue(client, store, *, limit=20):
    written = 0
    failures = []
    for request in store.claim_report_queue(limit=limit):
        try:
            report = client.fetch_report(
                request["property_id"],
                request["contract_key"],
                request["start_date"],
                request["end_date"],
                currency=request.get("property_currency") or "",
            )
            store.save_report(report)
            store.complete_report_request(request["id"])
            written += 1
        except Exception as error:
            store.complete_report_request(request["id"], error=str(error))
            failures.append({
                "contract": request.get("contract_key") or "",
                "start_date": str(request.get("start_date") or ""),
                "end_date": str(request.get("end_date") or ""),
                "error": str(error)[:300],
            })
    return {"written": written, "failures": failures}


def refresh_saved_report_contracts(*, connection_store=None, store=None, config=None):
    """Refresh canonical GA4 snapshots from a background worker only."""
    connection_store = connection_store or google_seo.default_store()
    store = store or PostgresAnalyticsStore()
    config = config or google_seo.load_config()
    access_token, connection = google_seo.access_token_for_connection(connection_store, config)
    property_id = str(connection.get("ga4_property_id") or "").strip()
    if not property_id:
        raise AnalyticsReportingError("No GA4 property is selected.", code="ga4_property_missing", retryable=False)
    client = CanonicalGA4Client(access_token)
    metadata = client.property_metadata(property_id)
    result = prewarm_common_reports(
        client,
        store,
        property_id=metadata["property_id"],
        property_timezone=metadata["timezone"],
        property_currency=metadata["currency"],
    )
    custom = process_custom_report_queue(client, store)
    result["written"] += custom["written"]
    result["failures"].extend(custom["failures"])
    result["status"] = "partial" if result["failures"] else "completed"
    return {
        **result,
        "rows_written": result["written"],
        "data_through_date": analytics_contracts.property_today(metadata["timezone"]).isoformat(),
        "property_id": metadata["property_id"],
        "property_timezone": metadata["timezone"],
        "property_currency": metadata["currency"],
    }
