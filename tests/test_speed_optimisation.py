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
