"""Isolated loopback PostgreSQL adapter. Never reads application credentials."""
import os
import psycopg
from psycopg.rows import dict_row
from pathlib import Path
import re

def connect():
    return psycopg.connect(host='127.0.0.1',port=int(os.getenv('CRM_TEST_PG_PORT','55479')),user='campaign_test',
        dbname='campaign_hardening',row_factory=dict_row,
        options='-c statement_timeout=15000 -c lock_timeout=10000')

def initialize(*,reset=False):
    with psycopg.connect(host='127.0.0.1',port=int(os.getenv('CRM_TEST_PG_PORT','55479')),user='campaign_test',dbname='postgres',autocommit=True) as c:
        if reset:c.execute('DROP DATABASE IF EXISTS campaign_hardening WITH (FORCE)')
        c.execute('CREATE DATABASE campaign_hardening')
    with connect() as c:
        for role in ('anon','authenticated'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():c.execute('CREATE ROLE '+role)
        source=Path('tests/crm_postgres_server.mjs').read_text()
        for filename in re.findall(r"readFileSync\('(migrations/[^']+)'",source):
            c.execute(Path(filename).read_text(encoding='utf-8'))
        c.execute('CREATE TABLE edition_orders(id bigserial primary key,shopify_customer_id text,customer_email text,edition_number int,edition_total int,product_title text,variant_title text,certificate_file_url text,shopify_order_name text)')

if __name__=='__main__':
    import sys
    initialize(reset='--reset' in sys.argv)
