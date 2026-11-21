"""Disposable native PostgreSQL fixture, restricted to the offline preview image."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def disposable_database():
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from auto_editions_jobs import Jobs

    if (not Path('/opt/studio/entry.py').is_file()
            or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}):
        raise RuntimeError('Requires the network-isolated preview container')
    base = 'host=127.0.0.1 port=55432 user=studio sslmode=disable'
    name = 'status_test_' + uuid4().hex
    with psycopg.connect(base + ' dbname=postgres', autocommit=True) as admin:
        for role in ('anon', 'authenticated', 'service_role'):
            if not admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                admin.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            def connect():
                return psycopg.connect(base + ' dbname=' + name, row_factory=dict_row)
            with psycopg.connect(base + ' dbname=' + name, autocommit=True, row_factory=dict_row) as raw:
                migration = Path(__file__).resolve().parents[1] / 'migrations/20261014004209_auto_editions_v6.sql'
                raw.execute(migration.read_text(encoding='utf-8'))
                with raw.cursor() as cursor:
                    yield Jobs(connect), cursor
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
