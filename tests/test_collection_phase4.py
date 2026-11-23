import logging
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import collector_vault as vault
import collector_vault_api as api
from collection_performance import validate_samples
from collector_preview_cache import ByteCache

APP = Starlette(routes=[Route(path, handler, methods=methods) for path, handler, methods in api.COLLECTOR_VAULT_ROUTES])
HEADERS = {'Authorization': 'Bearer synthetic', 'X-Sports-Cave-Request': api.REQUEST_MARKER}
SAMPLE = {'operation': 'bootstrap', 'duration_ms': 123.4, 'outcome': 'ok'}


@pytest.mark.parametrize('body', [None, {}, {'samples': []}, {'samples': [SAMPLE]*13},
    {'samples': [dict(SAMPLE, customer='private')]}, {'samples': [dict(SAMPLE, operation='private title')]},
    {'samples': [dict(SAMPLE, duration_ms=True)]}, {'samples': [dict(SAMPLE, duration_ms=float('nan'))]},
    {'samples': [dict(SAMPLE, duration_ms=-1)]}, {'samples': [dict(SAMPLE, duration_ms=120001)]},
    {'samples': [dict(SAMPLE, outcome='private error message')]}])
def test_reports_accept_only_fixed_nonpersonal_bounded_fields(body):
    with pytest.raises(ValueError):
        validate_samples(body)


def test_client_metrics_are_authenticated_and_never_log_owner_or_token(caplog):
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': 'private-owner'}), caplog.at_level(logging.INFO):
        response = TestClient(APP).post('/api/collector-vault/performance', headers=HEADERS, json={'samples': [SAMPLE]})
    assert response.status_code == 200 and response.json() == {'ok': True}
    assert 'source=client operation=bootstrap outcome=ok duration_ms=123' in caplog.text
    assert 'private-owner' not in caplog.text and 'synthetic' not in caplog.text
    assert response.headers['cache-control'] == 'no-store'
    assert TestClient(APP).post('/api/collector-vault/performance', headers={'X-Sports-Cave-Request': api.REQUEST_MARKER}, json={'samples': [SAMPLE]}).status_code == 401
    assert TestClient(APP).post('/api/collector-vault/performance', json={'samples': [SAMPLE]}).status_code == 403


def test_oversized_or_partly_invalid_batch_logs_no_samples(caplog):
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': 'fixture'}), caplog.at_level(logging.INFO):
        client = TestClient(APP)
        assert client.post('/api/collector-vault/performance', headers=HEADERS, content=' '*4097).status_code == 400
        assert client.post('/api/collector-vault/performance', headers=HEADERS, json={'samples': [SAMPLE, dict(SAMPLE, email='private')]}).status_code == 400
    assert 'source=client' not in caplog.text
    assert 'private' not in caplog.text


def test_server_timing_is_available_for_success_and_auth_failure_without_changing_body():
    with patch.object(vault, 'verify_shopify_session_token', return_value={'shopify_customer_id': 'fixture'}), \
         patch.object(vault, 'build_vault_payload', return_value={'certificates': []}):
        response = TestClient(APP).get('/api/collector-vault/bootstrap?include_review=false', headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['certificates'] == []
    assert response.headers['server-timing'].startswith('app;dur=')
    assert 'Server-Timing' in response.headers['access-control-expose-headers']
    unauthenticated = TestClient(APP).get('/api/collector-vault/bootstrap')
    assert unauthenticated.status_code == 401
    assert 'server-timing' in unauthenticated.headers


def test_cache_diagnostics_are_totals_only_and_do_not_change_existing_stats():
    c = ByteCache(max_bytes=100, max_entries=3)
    c.get_or_load('private-key', lambda: b'private-issued-source')
    c.get_or_load('private-key', lambda: b'not used')
    def fail():
        raise ValueError('synthetic')
    with pytest.raises(ValueError):
        c.get_or_load('failure', fail)
    assert c.diagnostics() == dict(hits=1, misses=2, waits=0, failures=1, busy=0)
    assert c.stats() == dict(bytes=21, entries=1, pending=0)
    assert 'private' not in str(c.diagnostics())
