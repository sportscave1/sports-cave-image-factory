"""Disposable lease adapter for existing SQL-aware connection fixtures."""
from contextlib import contextmanager
import supabase_backend as db


@contextmanager
def disposable_read_connection():
    conn = db.connect()
    try:
        yield conn
    finally:
        db._close_read_connection(conn)
