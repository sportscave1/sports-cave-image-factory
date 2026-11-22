"""Bound polling transactions without changing database-wide or CRM settings."""
from contextlib import contextmanager
from threading import BoundedSemaphore

_slots = BoundedSemaphore(2)


@contextmanager
def connection(factory):
    # Transaction-local settings reach the actual backend behind Supavisor.
    # Preserve all existing claim locks and atomic commit/rollback semantics.
    # Bound demand even while Supavisor is waiting to assign a backend. Existing
    # route error handling returns 503; the desktop retains and retries its event.
    if not _slots.acquire(blocking=False):
        raise RuntimeError('Companion polling is busy; retry the saved event shortly.')
    try:
        with factory() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='750ms'")
                cur.execute("SET LOCAL statement_timeout='8s'")
                cur.execute("SET LOCAL idle_in_transaction_session_timeout='8s'")
            yield conn
    finally:
        _slots.release()


def authenticate_and_touch(cur, token_hash):
    """Authenticate every request; a heartbeat never queues behind a job claim."""
    cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton AND token_hash=%s', (token_hash,))
    row = cur.fetchone()
    if row:
        cur.execute('''WITH available AS (
            SELECT singleton FROM product_upload_desktop
            WHERE singleton AND token_hash=%s
              AND (seen_at IS NULL OR seen_at<now()-interval '20 seconds')
            FOR UPDATE SKIP LOCKED)
            UPDATE product_upload_desktop d SET seen_at=now()
            FROM available a WHERE d.singleton=a.singleton''', (token_hash,))
    return row
