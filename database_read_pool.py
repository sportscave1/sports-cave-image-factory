"""Bounded, exclusive read connections; never caches account or order data."""
import atexit
import logging
import threading
from contextlib import contextmanager

_lock = threading.Lock()
_pools = {}


def pool(database_url, *, statement_timeout_ms=8000, connect_timeout=8):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # Separate account validation's shorter deadline from Orders reads.
    key = (database_url, statement_timeout_ms, connect_timeout)
    with _lock:
        result = _pools.get(key)
        if result is None:
            result = ConnectionPool(
                database_url, min_size=1, max_size=3, timeout=connect_timeout,
                max_waiting=8, max_idle=60, max_lifetime=300, open=True,
                kwargs=dict(row_factory=dict_row, connect_timeout=connect_timeout,
                            prepare_threshold=None, autocommit=True,
                            options=(f'-c statement_timeout={statement_timeout_ms} '
                                     f'-c idle_in_transaction_session_timeout={statement_timeout_ms}')),
            )
            # The real SELECT is checked under the caller's cancellation
            # watchdog. A separate network preflight could block outside it.
            _pools[key] = result
        return result


@contextmanager
def connection(database_url, *, statement_timeout_ms=8000, connect_timeout=8):
    current = pool(database_url, statement_timeout_ms=statement_timeout_ms,
                   connect_timeout=connect_timeout)
    with current.connection(timeout=connect_timeout) as conn:
        yield conn


def close():
    with _lock:
        previous = list(_pools.values())
        _pools.clear()
    for current in previous:
        current.close()


def warm_application_reads():
    """Start transport setup in pool workers without blocking app startup.

    No account, order, certificate or edition records are read or cached.
    Normal authentication and migration readiness checks still run unchanged.
    """
    import os_accounts
    import supabase_backend as db
    try:
        if db.is_configured():
            pool(db._database_url_with_ssl(), statement_timeout_ms=db._db_statement_timeout_ms())
        if os_accounts.DEFAULT_STORE.is_configured():
            pool(os_accounts.DEFAULT_STORE._database_url(), statement_timeout_ms=4000, connect_timeout=4)
    except Exception as error:
        # Warming is optional; foreground reads retain their usual error path.
        logging.warning('Read transport warmup unavailable: %s', type(error).__name__)


def stats():
    """Credential-free process diagnostics for focused performance checks."""
    with _lock:
        return [current.get_stats() for current in _pools.values()]


atexit.register(close)
