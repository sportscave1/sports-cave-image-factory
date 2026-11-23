"""Browser contact persists even when a subsequent queue claim cannot start."""
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import design_publish_ad as ads
import product_upload_staff_queue as uploads
from test_product_upload_staff_queue import database, store


def test_claim_outage_does_not_rollback_authenticated_contact(store, monkeypatch):
    token = uploads.pair({'id': 'desktop'})
    calls = 0

    @contextmanager
    def failing_claim():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Queue capacity temporarily unavailable')
        with store() as conn:
            yield conn

    monkeypatch.setattr(ads, 'connect', failing_claim)
    with pytest.raises(RuntimeError, match='capacity'):
        ads.tick(token, {})
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT value,updated_at FROM app_settings WHERE key=%s', (ads.HEARTBEAT_KEY,))
        row = cur.fetchone()
    assert row['value'] is True
    assert (datetime.now(timezone.utc)-row['updated_at']).total_seconds() < 10


def test_unpaired_browser_cannot_report_contact_or_claim_work(store, monkeypatch):
    uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(ads, 'connect', store)
    with pytest.raises(PermissionError):
        ads.tick('x'*43, {})
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT key FROM app_settings WHERE key=%s', (ads.HEARTBEAT_KEY,))
        assert cur.fetchone() is None


def test_repeated_contact_is_throttled_without_extending_a_queue_lease(store, monkeypatch):
    from ads_companion_liveness import heartbeat
    token = uploads.pair({'id': 'desktop'})
    heartbeat(store, ads.digest(token), ads.HEARTBEAT_KEY)
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT updated_at FROM app_settings WHERE key=%s', (ads.HEARTBEAT_KEY,))
        first = cur.fetchone()['updated_at']
    heartbeat(store, ads.digest(token), ads.HEARTBEAT_KEY)
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT updated_at FROM app_settings WHERE key=%s', (ads.HEARTBEAT_KEY,))
        assert cur.fetchone()['updated_at'] == first
        cur.execute('SELECT key FROM app_settings WHERE key=%s', (ads.PREFIX+'lease',))
        assert cur.fetchone() is None


def test_contact_only_does_not_select_or_advance_a_job(store, monkeypatch):
    token = uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(ads, 'connect', store)
    monkeypatch.setattr(ads, '_step', lambda *_: pytest.fail('Heartbeat must never advance work'))
    assert ads.tick(token, {'heartbeat_only':True}) == {}
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (ads.HEARTBEAT_KEY,))
        assert cur.fetchone()['value'] is True
        cur.execute('SELECT key FROM app_settings WHERE key=%s', (ads.PREFIX+'lease',))
        assert cur.fetchone() is None
