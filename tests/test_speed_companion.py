import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import speed_optimisation as speed
import speed_optimisation_api as api
from tests.test_speed_optimisation import report, store

ROOT = Path(__file__).resolve().parents[1]


def test_retention_only_expires_speed_reports(store):
    old = (dt.date.fromisoformat(speed.sydney_day()) - dt.timedelta(days=100)).isoformat()
    with store.connect() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s,%s)',
                        ('customer_orders', json.dumps({'keep': True}), old))
        conn.commit()
    store.publish(report(date=old))
    current = report()
    store.publish(current)
    assert store.recent() == [current]
    with store.connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT value FROM app_settings WHERE key=%s', ('customer_orders',))
            assert cur.fetchone()['value'] == {'keep': True}


def test_report_growth_is_bounded_and_existing_ids_remain_retryable(store):
    values = [report() for _ in range(speed.MAX_REPORTS_PER_DAY)]
    for value in values: store.publish(value)
    assert store.publish(values[0]) == values[0]
    with pytest.raises(ValueError, match='Daily Speed report limit'):
        store.publish(report())
    assert len(store.recent()) == speed.MAX_REPORTS_PER_DAY


def test_machine_credential_is_scoped_and_readback_verifies_report(monkeypatch, store):
    token = 'synthetic-fixture-speed-token-only-123456789'
    monkeypatch.setenv('SPEED_REPORT_TOKEN_SHA256', hashlib.sha256(token.encode()).hexdigest())
    monkeypatch.setattr(api, 'store', lambda: store)
    monkeypatch.setattr(store, 'storage_review', lambda: {'application_data_deleted': False})
    client = TestClient(Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES]))
    assert client.get('/api/speed/companion').status_code == 403
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/api/speed/companion', headers={'Authorization': 'Bearer ' + 'wrong' * 10}).status_code == 403
    value = report(cleanup_checks=['No dead code proven.'], storage_checks=['Aggregate review only.'])
    response = client.post('/api/speed/companion', headers=headers, json=value)
    assert response.status_code == 200 and response.json()['published'] == value['id']
    assert client.get('/api/speed/companion', headers=headers).json()['reports'] == [value]
    assert client.post('/api/speed/companion', headers=headers, json={'execute': 'anything'}).status_code == 400
    assert client.post('/api/speed/companion', headers={**headers, 'Content-Type': 'application/json'}, content='x' * (speed.MAX_BYTES + 1)).status_code == 413
    monkeypatch.delenv('SPEED_REPORT_TOKEN_SHA256')
    assert client.get('/api/speed/companion', headers=headers).status_code == 403


def companion():
    spec = importlib.util.spec_from_file_location('speed_companion', ROOT / 'scripts/speed_companion.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publisher_acks_only_matching_receipt_and_retries_safely(tmp_path, monkeypatch):
    module = companion()
    value = report()
    (tmp_path / (value['date'] + '.json')).write_text(json.dumps(value))
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    response = Mock()
    client.post.return_value = response
    response.json.return_value = {'published': 'wrong', 'date': value['date']}
    monkeypatch.setattr(module, 'session', lambda home: client)
    with pytest.raises(RuntimeError, match='receipt mismatch'):
        module.flush(tmp_path)
    assert not list((tmp_path / 'published').glob('*.json'))
    response.json.return_value = {'published': value['id'], 'date': value['date']}
    assert len(module.flush(tmp_path)) == 1
    assert module.flush(tmp_path) == []
    assert client.post.call_count == 2
    assert client.post.call_args.kwargs['allow_redirects'] is False
