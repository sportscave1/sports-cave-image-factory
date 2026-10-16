"""Disposable lease adapter for existing SQL-aware connection fixtures."""
from contextlib import contextmanager, nullcontext
import supabase_backend as db


@contextmanager
def disposable_read_connection():
    conn = db.connect()
    if not hasattr(conn, 'pipeline'):
        conn.pipeline = nullcontext
        cursor = conn.cursor
        def owned_cursor():
            result = cursor()
            result.connection = conn
            return result
        conn.cursor = owned_cursor
    try:
        yield conn
    finally:
        db._close_read_connection(conn)
