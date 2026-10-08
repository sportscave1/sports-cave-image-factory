"""Bounded Shopify order reconciliation owned by the webhook service.

This module deliberately has no import-time database or Shopify work. The
isolated child starts only when explicitly enabled or when running as the Render
webhook service.
"""

import json
import os
import threading
import time
import subprocess
import sys
from pathlib import Path


_stop = threading.Event()
_process = None


def _log(event, **fields):
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value not in (None, "")})
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def enabled():
    configured = str(os.getenv("SHOPIFY_ORDER_RECONCILIATION_ENABLED") or "").strip().casefold()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_NAME")) and (
        str(os.getenv("SPORTS_CAVE_SERVICE_ROLE") or "webhook").strip().casefold() == "webhook"
    )


def interval_seconds():
    try:
        return max(300, int(os.getenv("SHOPIFY_ORDER_RECONCILIATION_INTERVAL_SECONDS") or "900"))
    except (TypeError, ValueError):
        return 900


def run_once():
    started_at = time.perf_counter()
    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            _log("shopify_order_reconciliation_skipped", reason="database_not_configured")
            return {"status": "skipped", "reason": "database_not_configured"}
        # Resume durable edition transitions even when there are no new orders.
        from edition_versions import resume_pending
        try:
            resume_pending()
        except Exception as exc:
            _log("edition_sync_recovery_failed", error=str(exc))
        with supabase_backend.shopify_order_reconciliation_lease() as lease_acquired:
            if not lease_acquired:
                _log("shopify_order_reconciliation_already_running", reason="durable_lease_held")
                return {
                    "status": "already_running",
                    "sync_blocked": True,
                    "block_reason": "Another full reconciliation holds the durable database lease.",
                }
            result = supabase_backend.sync_latest_paid_orders_to_supabase(
                limit=50,
                lookback_days=14,
                ensure_schema_first=False,
                allow_unrelated_allocation_duplicates=True,
            )
        if result.get("sync_blocked"):
            _log(
                "shopify_order_reconciliation_blocked",
                reason=result.get("block_reason") or "unknown",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 1),
            )
            return result
        _log(
            "shopify_order_reconciliation_completed",
            orders_examined=result.get("shopify_orders_fetched", 0),
            orders_inserted=result.get("new_orders_inserted", 0),
            orders_updated=result.get("orders_updated", 0),
            orders_requiring_mapping=result.get("orders_requiring_mapping", 0),
            orders_rejected=result.get("orders_rejected", 0),
            retryable_errors=result.get("orders_retryable_errors", 0),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 1),
        )
        return result
    except Exception as error:
        _log(
            "shopify_order_reconciliation_failed",
            error_type=error.__class__.__name__,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 1),
        )
        return {"status": "failed", "error_type": error.__class__.__name__}


def _loop():
    initial_delay = 60
    try:
        initial_delay = max(0, int(os.getenv("SHOPIFY_ORDER_RECONCILIATION_INITIAL_DELAY_SECONDS") or "60"))
    except (TypeError, ValueError):
        pass
    if _stop.wait(initial_delay):
        return
    while not _stop.is_set():
        run_once()
        if _stop.wait(interval_seconds()):
            return


def start():
    global _process
    if not enabled():
        return False
    if _process and _process.poll() is None:
        return False
    # Same bounded reconciliation, separate interpreter and DB connection pool.
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    try:_process=subprocess.Popen([sys.executable,str(Path(__file__).resolve())],**kwargs)
    except OSError as exc:
        _log('shopify_order_reconciliation_start_failed',error_type=type(exc).__name__)
        return False
    _log("shopify_order_reconciliation_started", interval_seconds=interval_seconds())
    return True


def stop():
    _stop.set()
    if _process and _process.poll() is None:
        _process.terminate()
        try:_process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _log('shopify_order_reconciliation_shutdown_timeout')
            _process.kill();_process.wait(timeout=5)


if __name__=='__main__':
    import signal
    signal.signal(signal.SIGTERM,lambda *_:_stop.set())
    signal.signal(signal.SIGINT,lambda *_:_stop.set())
    _loop()
