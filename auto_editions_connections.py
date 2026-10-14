"""Small transaction pool for order-time editions; no cached account/row data."""
import threading

_lock=threading.Lock()
_pool=None
_configuration=None


def connect():
    global _pool,_configuration
    import supabase_backend as db
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    configuration=(db._database_url_with_ssl(),db._db_statement_timeout_ms())
    with _lock:
        if _pool is None or configuration!=_configuration:
            previous=_pool
            _pool=ConnectionPool(configuration[0],min_size=0,max_size=3,
                timeout=8,max_waiting=8,max_idle=60,max_lifetime=300,
                check=ConnectionPool.check_connection,open=True,
                kwargs=dict(row_factory=dict_row,connect_timeout=8,prepare_threshold=None,
                    options=f'-c statement_timeout={configuration[1]} -c idle_in_transaction_session_timeout={configuration[1]}'))
            _configuration=configuration
            if previous:previous.close()
        pool=_pool
    # Psycopg commits/rolls back each context and discards broken connections.
    # Never retry a transaction here: durable job writes own their idempotency.
    return pool.connection()
