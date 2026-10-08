"""Create a disposable local PostgreSQL database, rehearse the reviewed runner.

Never accepts a remote host. No credentials or live customer rows are copied.
Usage: python scripts/rehearse_edition_postgres.py --port 55439 --user edition_test
"""
import argparse
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
import run_migrations


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--user',required=True)
    args=parser.parse_args();name='edition_rehearsal_'+uuid.uuid4().hex[:12]
    base=dict(host='127.0.0.1',port=args.port,user=args.user)
    with psycopg.connect(**base,dbname='postgres',autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    with psycopg.connect(**base,dbname=name,autocommit=True) as conn:
        for role in ('anon','authenticated'):
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        conn.execute(Path('tests/fixtures/edition_base.sql').read_text(encoding='utf-8').replace('CREATE ROLE anon; CREATE ROLE authenticated;',''))
        for filename in ('create_edition_runs_phase2.sql','20260825_atomic_edition_allocation_ledger.sql','20260912045939_independent_edition_cursor.sql'):
            conn.execute(Path('migrations',filename).read_text(encoding='utf-8'))
        conn.execute(Path('tests/fixtures/edition_live_allocator_20261008.sql').read_text(encoding='utf-8'))
        print(conn.execute('SELECT version()').fetchone()[0])
    os.environ['DATABASE_URL']=psycopg.conninfo.make_conninfo(**base,dbname=name)
    # The release runner accepts URI host validation. This URL contains no secret.
    os.environ['DATABASE_URL']=f'postgresql://{args.user}@127.0.0.1:{args.port}/{name}'
    run_migrations.run_edition_migrations()
    run_migrations.run_edition_migrations()  # Ledger replay must be a no-op.
    print('EDITION_REAL_POSTGRES_URL='+os.environ['DATABASE_URL'])


if __name__=='__main__':main()
