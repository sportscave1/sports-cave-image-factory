import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone


_CERTIFICATE_LOG_CONTEXT = ContextVar("certificate_log_context", default={})


def set_certificate_log_context(**context):
    current = dict(_CERTIFICATE_LOG_CONTEXT.get() or {})
    current.update({key: value for key, value in context.items() if value not in (None, "")})
    return _CERTIFICATE_LOG_CONTEXT.set(current)


def reset_certificate_log_context(token):
    if token is not None:
        _CERTIFICATE_LOG_CONTEXT.reset(token)


def certificate_stage_log(stage, status, *, started_at=None, error="", **details):
    context = dict(_CERTIFICATE_LOG_CONTEXT.get() or {})
    context.update({key: value for key, value in details.items() if value not in (None, "")})
    payload = {
        "event": "certificate_stage",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_page": str(context.get("source_page") or ""),
        "order_name": str(context.get("order_name") or context.get("order") or ""),
        "edition_order_id": str(context.get("edition_order_id") or ""),
        "stage": str(stage or ""),
        "status": str(status or ""),
    }
    if started_at is not None:
        payload["duration_seconds"] = round(max(time.perf_counter() - float(started_at), 0.0), 3)
    if error:
        payload["error"] = str(error)[:1000]
    for key in ("shopify_file_status", "attempt", "attempts", "timeout_seconds", "db_stage", "schema_mode"):
        if context.get(key) not in (None, ""):
            payload[key] = context.get(key)
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


@contextmanager
def certificate_stage(stage, **details):
    started_at = time.perf_counter()
    certificate_stage_log(stage, "started", **details)
    try:
        yield
    except Exception as error:
        certificate_stage_log(stage, "failed", started_at=started_at, error=error, **details)
        raise
    else:
        certificate_stage_log(stage, "completed", started_at=started_at, **details)
