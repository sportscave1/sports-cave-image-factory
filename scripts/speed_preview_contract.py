"""Synthetic-only real PostgreSQL/API acceptance, copied into the no-network container."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg.rows import dict_row

DSN = 'postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Synthetic acceptance requires the network-isolated preview container.')
os.environ['DATABASE_URL'] = DSN
sys.path.insert(0, '/tmp/source')
import speed_optimisation as speed
import speed_optimisation_api as api


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


with connect() as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value JSONB,updated_at TIMESTAMPTZ DEFAULT now())')
    conn.execute("INSERT INTO app_settings(key,value) VALUES ('studio_speed_guard','{\"keep\":true}') ON CONFLICT DO NOTHING")
service = speed.Reports(connect)
import os_accounts
with connect() as conn:
    synthetic_user = conn.execute("SELECT id FROM os_users WHERE email=%s", ('preview@example.invalid',)).fetchone()
if synthetic_user:
    account = os_accounts.DEFAULT_STORE.get_user(str(synthetic_user['id']))
    assert os_accounts.account_is_active(account), 'Synthetic account refresh failed'
day = speed.sydney_day()
base = dict(id=str(uuid.uuid4()), date=day, section='Synthetic preview fixture',
            fingerprint='a' * 64, status='reviewed', summary='Synthetic acceptance report; no production performance claimed.',
            base_sha='a' * 40, measurements=[], tests=['Synthetic PostgreSQL and API contracts'],
            phases=['Verify owner-only report UI'], blockers=[], files=[],
            cleanup_checks=['No application code removed by the fixture.'],
            storage_checks=['Only Speed reports are eligible for expiry.'])
old = dict(base, date=(dt.date.fromisoformat(day) - dt.timedelta(days=100)).isoformat(), id=str(uuid.uuid4()))
with connect() as conn:
    conn.execute('INSERT INTO app_settings(key,value) VALUES (%s,%s::jsonb)',
                 (speed.PREFIX + old['date'] + ':' + old['id'], json.dumps(old)))
assert service.publish(base) == service.publish(base)
assert service.recent() == [base]
try:
    service.publish(dict(base, summary='Must not overwrite immutable evidence'))
except ValueError:
    pass
else:
    raise AssertionError('Conflicting report overwrite accepted')
with connect() as conn:
    assert conn.execute("SELECT value FROM app_settings WHERE key='studio_speed_guard'").fetchone()['value'] == {'keep': True}
storage = service.storage_review()
assert storage['speed_reports']['reports'] == 1 and not storage['application_data_deleted']

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
token = 'fixture-only-speed-report-credential-1234567890'
os.environ['SPEED_REPORT_TOKEN_SHA256'] = hashlib.sha256(token.encode()).hexdigest()
api.store = lambda: service
client = TestClient(Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES]))
assert client.get('/api/speed/companion').status_code == 403
headers = {'Authorization': 'Bearer ' + token}
response = client.post('/api/speed/companion', json=base, headers=headers)
assert response.status_code == 200 and response.json()['published'] == base['id']
assert client.get('/api/speed/companion', headers=headers).json()['reports'] == [base]
assert client.post('/api/speed/companion', json={'execute': 'forbidden'}, headers=headers).status_code == 400

# Reuse exactly the immutable entry guards without starting another application.
guards = Path('/opt/studio/entry.py').read_text().rsplit('runpy.run_path(', 1)[0]
exec(compile(guards, 'synthetic-entry-guards', 'exec'))
import importlib
for module in ('run_migrations', 'sports_cave_server', 'support_email_worker', 'webhooks'):
    try:
        importlib.import_module(module)
    except ImportError:
        pass
    else:
        raise AssertionError('Forbidden runtime import accepted: ' + module)
import requests
for url in ('https://synthetic.myshopify.com/orders.json', 'https://graph.facebook.com/ads', 'https://api.resend.com/emails'):
    try:
        requests.post(url, json={})
    except RuntimeError:
        pass
    else:
        raise AssertionError('Provider write accepted')
print('SPEED_ACCEPTANCE_RESULT=' + json.dumps({'postgres_contracts': True, 'api_contracts': True, 'retention_scope': True,
                  'provider_write_denial': True, 'worker_migration_denial': True,
                  'synthetic_report_id': base['id'], 'speed_report_bytes': storage['speed_reports']['bytes']}))
