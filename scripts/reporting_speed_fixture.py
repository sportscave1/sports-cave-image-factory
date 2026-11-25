"""Synthetic-only real PostgreSQL adapter; never import outside isolated preview."""
import os
from pathlib import Path
import time

if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Requires reviewed network-isolated preview')
DSN = 'postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
os.environ['DATABASE_URL'] = DSN
os.environ['SPORTS_CAVE_ADMIN_EMAIL'] = 'preview@example.invalid'
import psycopg
from psycopg.rows import dict_row
import supabase_backend

METER = dict(queries=0, sql_ms=0.)


class ReadCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        assert isinstance(query, str) and query.lstrip().upper().startswith(('SELECT', 'SET LOCAL')), 'Reporting wrote data'
        start = time.perf_counter()
        try:
            return super().execute(query, params, **kwargs)
        finally:
            METER['queries'] += 1
            METER['sql_ms'] += (time.perf_counter()-start)*1000


def connect():
    return psycopg.connect(DSN, row_factory=dict_row, cursor_factory=ReadCursor)


supabase_backend.connect = connect
# The private fixture creates only its own minimal schema; never run migrations.
supabase_backend.ensure_dashboard_schema = lambda: None


def backend():
    return supabase_backend
