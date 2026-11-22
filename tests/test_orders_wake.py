"""Synthetic committed-state notification and paired endpoint checks."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import orders_wake as wake
import prodigi_preparation as prep
import prodigi_preparation_api as api
from test_auto_editions_jobs import database


@pytest.fixture
def mirror(database,monkeypatch):
    factory=database[0].connect
    monkeypatch.setattr(prep,'connect',factory)
    monkeypatch.setattr(wake,'_cache',None)
    monkeypatch.setattr(wake,'CHECK_SECONDS',0)
    with factory() as conn,conn.cursor() as cur:
        cur.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
        cur.execute('CREATE TABLE shopify_orders(shopify_order_id int PRIMARY KEY,created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now(),synced_at timestamptz DEFAULT now())')
        cur.execute('CREATE TABLE edition_orders(id int PRIMARY KEY,assigned_at timestamptz DEFAULT now())')
    return factory


def sql(factory,query):
    with factory() as conn,conn.cursor() as cur:cur.execute(query)


def test_arrival_allocation_ready_jpg_and_actionable_reset_each_change_cursor(mirror):
    versions=[wake.version()]
    for query in (
        'INSERT INTO shopify_orders(shopify_order_id) VALUES(1)',
        'INSERT INTO edition_orders(id) VALUES(1)',
        "INSERT INTO auto_edition_jobs(id,status,payload,actor_id) VALUES(repeat('a',64),'Ready','{}','fixture')",
        "INSERT INTO app_settings(key,value) VALUES('prodigi_prepare:1','{\"status\":\"Queued\"}')",
        "UPDATE app_settings SET value='{\"status\":\"Awaiting browser upload\"}',updated_at=now() WHERE key='prodigi_prepare:1'",
    ):
        sql(mirror,query);versions.append(wake.version())
    assert len(set(versions))==6 and all(len(v)==64 for v in versions)


def test_heartbeat_and_waiting_jpg_updates_do_not_create_a_self_wake_loop(mirror):
    sql(mirror,"INSERT INTO app_settings(key,value) VALUES('orders_companion_seen','true'),('prodigi_prepare:1','{\"status\":\"Preparing JPG\"}')")
    before=wake.version()
    sql(mirror,'UPDATE app_settings SET updated_at=now()')
    assert wake.version()==before


def test_rolled_back_arrival_does_not_notify_and_cursor_survives_server_restart(mirror,monkeypatch):
    before=wake.version()
    with pytest.raises(ValueError):
        with mirror() as conn,conn.cursor() as cur:
            cur.execute('INSERT INTO shopify_orders(shopify_order_id) VALUES(1)')
            raise ValueError('Transaction rolled back')
    assert wake.version()==before
    sql(mirror,'INSERT INTO shopify_orders(shopify_order_id) VALUES(2)')
    committed=wake.version()
    monkeypatch.setattr(wake,'_cache',None)
    assert wake.version()==committed and committed!=before


def test_shared_snapshot_cache_avoids_repeated_database_reads(mirror,monkeypatch):
    calls=[]
    @contextmanager
    def counted():
        calls.append(True)
        with mirror() as conn:yield conn
    monkeypatch.setattr(prep,'connect',counted)
    monkeypatch.setattr(wake,'CHECK_SECONDS',2)
    assert wake.version()==wake.version() and len(calls)==1


def test_fifty_order_window_detects_changed_identity_even_with_identical_timestamps(mirror):
    sql(mirror,"INSERT INTO shopify_orders SELECT n,'2026-01-01','2026-01-01','2026-01-01' FROM generate_series(1,50) n")
    before=wake.version()
    sql(mirror,"INSERT INTO shopify_orders VALUES(0,'2026-01-01','2026-01-01','2026-01-01')")
    assert wake.version()!=before


def test_actionable_transition_with_same_timestamp_still_notifies(mirror):
    sql(mirror,"INSERT INTO app_settings(key,value) VALUES('prodigi_prepare:1','{\"status\":\"Queued\"}')")
    before=wake.version()
    sql(mirror,"UPDATE app_settings SET value='{\"status\":\"Awaiting browser upload\"}' WHERE key='prodigi_prepare:1'")
    assert wake.version()!=before


def test_long_wait_holds_no_database_transaction(mirror,monkeypatch):
    active=[];waits=[]
    @contextmanager
    def tracked():
        with mirror() as conn:
            active.append(True)
            try:yield conn
            finally:active.pop()
    monkeypatch.setattr(prep,'connect',tracked)
    before=wake.version()
    async def sleep(_):
        assert not active
        waits.append(True)
        sql(mirror,'INSERT INTO shopify_orders(shopify_order_id) VALUES(1)')
    monkeypatch.setattr(wake.asyncio,'sleep',sleep)
    async def connected():return False
    current,changed=asyncio.run(wake.changed(before,SimpleNamespace(is_disconnected=connected)))
    assert changed and current!=before and waits==[True] and not active


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setattr(api,'desktop',lambda _,**kw:None)
    monkeypatch.setattr(prep,'enabled',lambda:True)
    return TestClient(Starlette(routes=[Route('/notifications',wake.listen,methods=['GET'])]))


@pytest.mark.parametrize('after',['sku=ABC','https://fixture.invalid','a'*65,'../order'])
def test_invalid_cursors_cannot_supply_jobs_or_urls(endpoint,monkeypatch,after):
    monkeypatch.setattr(wake,'version',lambda:pytest.fail('Invalid requests must not read state'))
    assert endpoint.get('/notifications',params={'after':after},headers={'Authorization':'Bearer '+'a'*43}).status_code==409


def test_notification_is_paired_read_only_and_contains_only_opaque_version(endpoint,monkeypatch):
    monkeypatch.setattr(wake,'version',lambda:'b'*64)
    assert endpoint.get('/notifications').status_code==403
    response=endpoint.get('/notifications',headers={'Authorization':'Bearer '+'a'*43})
    assert response.status_code==200
    assert response.json()==dict(enabled=True,version='b'*64,changed=True)
    assert 'no-store' in response.headers['cache-control']


def test_excess_listeners_back_off_without_reading_state(endpoint,monkeypatch):
    monkeypatch.setattr(wake,'version',lambda:pytest.fail('Bounded listeners'))
    assert wake._waiters.acquire(False) and wake._waiters.acquire(False)
    try:
        response=endpoint.get('/notifications',headers={'Authorization':'Bearer '+'a'*43})
        assert response.status_code==429 and response.headers['retry-after']=='5'
    finally:
        wake._waiters.release();wake._waiters.release()


def test_idle_notification_returns_within_deadline_without_work(monkeypatch):
    monkeypatch.setattr(wake,'version',lambda:'a'*64)
    monkeypatch.setattr(wake,'WAIT_SECONDS',0.01)
    monkeypatch.setattr(wake,'CHECK_SECONDS',0.002)
    async def connected():return False
    assert asyncio.run(wake.changed('a'*64,SimpleNamespace(is_disconnected=connected)))==('a'*64,False)


def test_cancelled_request_releases_its_listener_slot(endpoint,monkeypatch):
    async def cancelled(*_):raise asyncio.CancelledError
    monkeypatch.setattr(wake,'changed',cancelled)
    request=SimpleNamespace(headers={'authorization':'Bearer '+'a'*43},query_params={})
    with pytest.raises(asyncio.CancelledError):asyncio.run(wake.listen(request))
    assert wake._waiters.acquire(False) and wake._waiters.acquire(False)
    wake._waiters.release();wake._waiters.release()


def test_notifications_authentication_does_not_take_native_poll_slot(monkeypatch):
    from unittest.mock import MagicMock
    from companion_poll_transaction import connection
    import os_accounts
    factory=MagicMock()
    cur=factory.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value={'actor_id':'fixture'}
    monkeypatch.setattr(prep,'connect',factory)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    monkeypatch.setattr(os_accounts,'DEFAULT_STORE',SimpleNamespace(get_user=lambda _:dict(id='fixture')))
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *_:True)
    with connection(factory,slots=api._orders_auth_slots):
        assert api.desktop('fixture-token',slots=wake._auth)==dict(id='fixture')
    assert factory.call_count==3
