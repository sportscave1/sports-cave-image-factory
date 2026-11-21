import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import uuid

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import speed_optimisation as speed
import speed_optimisation_api as api

ROOT = Path(__file__).resolve().parents[1]


def report(**changes):
    value = dict(id=str(uuid.uuid4()), date=speed.sydney_day(), section='Orders',
                 fingerprint='a' * 64, status='blocked', summary='Workflow parity unavailable.',
                 base_sha='a' * 40, measurements=[], tests=[], phases=['Measure Orders'],
                 blockers=['Synthetic preview disabled'], files=[])
    value.update(changes)
    return value


def test_sydney_date_across_dst():
    assert speed.sydney_day(dt.datetime(2026, 1, 1, 14, 15, tzinfo=dt.timezone.utc)) == '2026-01-02'
    assert speed.sydney_day(dt.datetime(2026, 7, 1, 14, 15, tzinfo=dt.timezone.utc)) == '2026-07-02'


def test_release_needs_revision_and_actual_live_samples():
    with pytest.raises(ValueError):
        speed.validate_report(report(status='released', candidate_sha='b' * 40, live_sha='c' * 40))
    with pytest.raises(ValueError):
        speed.validate_report(report(status='released', candidate_sha='b' * 40, live_sha='b' * 40))
    measurements = [dict(workflow='All 75 rows usable', environment='live', revision='b' * 40,
                         samples_ms=[500, 510, 490])]
    assert speed.validate_report(report(status='released', candidate_sha='b' * 40,
                                         live_sha='b' * 40, measurements=measurements))['status'] == 'released'
    for samples in ([1], [1, 2, float('nan')], [True, 2, 3], [0, 2, 3]):
        measurements[0]['samples_ms'] = samples
        with pytest.raises(ValueError):
            speed.validate_report(report(measurements=measurements))


def test_new_changed_and_old_sections_rotate():
    sections = [dict(name=n, fingerprint=h * 64) for n, h in [('Orders', 'a'), ('New page', 'b'), ('Changed', 'c')]]
    history = [report(section='Orders', fingerprint='a' * 64, date='2026-11-19'),
               report(section='Changed', fingerprint='d' * 64, date='2026-11-20')]
    ranked = speed.prioritise(sections, history)
    assert {s['name'] for s in ranked[:2]} == {'Changed', 'New page'}
    assert ranked[-1]['name'] == 'Orders'
    with pytest.raises(ValueError):
        speed.fingerprint(ROOT, ['../outside.py'])


def test_discover_new_pages_without_importing_application(tmp_path):
    (tmp_path / 'new_feature_page.py').write_text("raise RuntimeError('must not import')\n")
    spec = importlib.util.spec_from_file_location('speed_review', ROOT / 'scripts/speed_review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sections = module.discover(tmp_path)
    assert [s['name'] for s in sections] == ['New Feature']
    old = sections[0]['fingerprint']
    (tmp_path / 'new_feature_page.py').write_text("raise RuntimeError('changed source')\n")
    assert module.discover(tmp_path)[0]['fingerprint'] != old


def test_daily_run_claim_prevents_duplicates_and_wrong_completion(tmp_path):
    spec = importlib.util.spec_from_file_location('speed_daily', ROOT / 'scripts/speed_daily.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    claim = module.begin(tmp_path)
    with pytest.raises(RuntimeError, match='already claimed'):
        module.begin(tmp_path)
    value = report(id=claim['id'], date=claim['date'])
    with pytest.raises(ValueError, match='exact claimed'):
        module.complete(tmp_path, str(uuid.uuid4()), value)
    assert (tmp_path / 'active.json').exists()
    module.complete(tmp_path, claim['id'], value)
    assert not (tmp_path / 'active.json').exists()
    assert module.begin(tmp_path)['status'] == 'already_reported'


class SqliteCursor:
    """Execute the small app_settings contract against a real isolated SQL store.

    Only parameter/JSON syntax differs; this does not replace a Postgres check.
    """
    def __init__(self, conn):
        self.cur = conn.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cur.close()
    def execute(self, sql, args):
        if sql.startswith('SELECT pg_advisory_xact_lock'):
            return self.cur.execute('SELECT 1')
        return self.cur.execute(sql.replace('%s::jsonb', '?').replace('%s', '?').replace('now()', 'CURRENT_TIMESTAMP'), args)
    def fetchone(self):
        row = self.cur.fetchone()
        if row is None: return None
        result = dict(zip([c[0] for c in self.cur.description], row))
        if 'value' in result: result['value'] = json.loads(result['value'])
        return result
    def fetchall(self):
        return [{'value': json.loads(row[0])} for row in self.cur.fetchall()]


class SqliteConnection:
    def __init__(self, path): self.conn = sqlite3.connect(path)
    def __enter__(self): return self
    def __exit__(self, kind, *args):
        if kind: self.conn.rollback()
        self.conn.close()
    def cursor(self): return SqliteCursor(self.conn)
    def commit(self): self.conn.commit()


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'synthetic.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
    return speed.Reports(lambda: SqliteConnection(path))


def test_report_persistence_retry_conflict_and_bounded_history(store):
    original = report()
    assert store.publish(original) == store.publish(copy.deepcopy(original))
    with pytest.raises(ValueError, match='different evidence'):
        store.publish(dict(original, summary='Do not overwrite evidence'))
    assert store.recent() == [original]
    store.publish(report(section='Website'))
    assert len(store.recent(1)) == 1
    assert len(store.recent(10000)) == 2


def test_history_uses_report_day_then_publication_time_not_random_ids(store):
    older = report(id='ffffffff-ffff-4fff-bfff-ffffffffffff', section='Initial setup')
    newer = report(id='00000000-0000-4000-8000-000000000001', section='Completed installation', status='reviewed')
    backfill = report(date=(dt.date.fromisoformat(newer['date']) - dt.timedelta(days=1)).isoformat())
    for value in (older, newer, backfill):
        store.publish(value)
    with store.connect() as conn:
        with conn.cursor() as cur:
            for value, at in [(older, '2026-11-21 00:00:00'), (newer, '2026-11-21 00:00:01'), (backfill, '2026-11-21 00:00:02')]:
                cur.execute('UPDATE app_settings SET updated_at=%s WHERE key=%s',
                            (at, speed.PREFIX + value['date'] + ':' + value['id']))
        conn.commit()
    assert store.recent() == [newer, older, backfill]
    assert store.recent(1) == [newer]
    assert store.publish(older) == older
    assert store.recent()[0] == newer, 'A delivery retry must not make the old blocker current again'


def speed_page(reports):
    # Keep native dataframe modules outside the fixture's sys.modules scope.
    importlib.import_module('pandas')
    from streamlit.testing.v1 import AppTest
    source = f'''
import sys, types
from unittest.mock import patch
from speed_optimisation import Reports
from speed_optimisation_page import render_page
def no_database(): raise AssertionError('Page fixture must not connect to any database')
with patch.dict(sys.modules, {{'supabase_backend': types.SimpleNamespace(connect=no_database)}}), patch('os_accounts.can_access_page',return_value=True), patch.object(Reports,'recent',return_value={reports!r}):
    render_page({{'role':'admin','is_active':True}})
'''
    return AppTest.from_string(source, default_timeout=15).run()


def test_page_separates_latest_result_from_old_blocked_snapshot():
    latest = report(section='Installation', status='released', candidate_sha='a' * 40, live_sha='a' * 40)
    older = report(section='Initial setup', status='blocked')
    page = speed_page([latest, older])
    assert not page.exception
    assert page.success[0].value == 'Latest report: Released'
    assert not page.warning
    assert page.dataframe[0].value['Status'].tolist() == ['Released']
    assert page.dataframe[1].value['Status'].tolist() == ['Blocked (historical)']
    history = next(row for row in page.expander if row.label == 'Earlier reports (1)')
    assert not history.proto.expanded


def test_page_keeps_a_genuine_latest_blocker_visible():
    page = speed_page([report(status='blocked'), report(status='released')])
    assert not page.exception
    assert page.warning[0].value == 'Latest report: Blocked'
    assert not page.success


@pytest.fixture
def client(monkeypatch, store):
    import files_upload_api
    import os_accounts
    monkeypatch.setattr(api, 'store', lambda: store)
    monkeypatch.setattr(files_upload_api, '_request_user', lambda r, **kw: {'role': 'admin', 'is_active': True, 'email': 'owner@fixture.invalid'})
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda user: user.get('email') == 'owner@fixture.invalid')
    return TestClient(Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES]))


def test_same_origin_owner_publication_and_readback(client):
    original = report()
    assert client.post('/ops/speed/publish', json=original).status_code == 403
    assert client.post('/ops/speed/publish', json=original, headers={'Origin': 'https://evil.invalid'}).status_code == 403
    good = {'Origin': 'http://testserver'}
    response = client.post('/ops/speed/publish', json=original, headers=good)
    assert response.status_code == 200
    assert response.json()['published'] == original['id']
    assert client.get('/api/speed/reports').json()['reports'] == [original]
    assert client.post('/ops/speed/publish', data={'report': json.dumps(original)}, headers=good).status_code == 200
    assert client.post('/ops/speed/publish', json={'bad': True}, headers=good).status_code == 400
    assert client.post('/ops/speed/publish', content='x' * (speed.MAX_BYTES * 4 + 1), headers=good).status_code == 413


def test_non_owner_cannot_read_or_write(client, monkeypatch):
    import files_upload_api
    monkeypatch.setattr(files_upload_api, '_request_user', lambda r, **kw: {'role': 'admin', 'is_active': True, 'email': 'other@fixture.invalid'})
    assert client.get('/api/speed/reports').status_code == 403
    assert client.get('/ops/speed/publish').status_code == 403
    assert client.post('/ops/speed/publish', json=report(), headers={'Origin': 'http://testserver'}).status_code == 403


def test_session_failure_is_denied_and_checks_speed_permission(client, monkeypatch):
    import files_upload_api
    def missing_session(request, *, required_page):
        assert required_page == 'Speed Optimisation'
        raise files_upload_api.FilesUploadError('Sign in required', status_code=401)
    monkeypatch.setattr(files_upload_api, '_request_user', missing_session)
    assert client.get('/api/speed/reports').status_code == 403


def test_speed_sidebar_and_staff_permissions(monkeypatch):
    import os_accounts
    from streamlit.testing.v1 import AppTest
    page = AppTest.from_file(str(ROOT / 'tests/worker_health_nav_fixture.py'), default_timeout=15)
    page.query_params['page'] = 'Speed Optimisation'
    page.run()
    assert not page.exception
    assert page.button(key='sidebar-child::Speed Optimisation').proto.type == 'primary'
    assert not os_accounts.can_access_page({'role': 'worker', 'is_active': True,
                                            'page_permissions': ['speed_optimisation']}, 'Speed Optimisation')
    assert not os_accounts.can_access_page({'role': 'admin', 'is_active': False}, 'Speed Optimisation')
