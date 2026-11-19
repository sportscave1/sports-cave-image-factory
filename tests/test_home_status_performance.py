"""Offline concurrency, failure and data-isolation contracts; no app startup."""
from datetime import date, datetime
from threading import Event
from time import perf_counter, sleep
from unittest.mock import Mock
import pytest

from display_snapshot import Snapshots


def settled(cache, key, loader):
    end = perf_counter() + 3
    while perf_counter() < end:
        value = cache.read(key, loader)
        if value['state'] in ('ready', 'unavailable'):
            return value
        sleep(.005)
    raise AssertionError('Synthetic cache did not settle')


def test_refresh_is_nonblocking_single_flight_and_retains_last_success():
    clock = [10]
    cache = Snapshots(workers=1, ttl=2, retry=2, max_age=20, clock=lambda: clock[0])
    release, started = Event(), Event()
    try:
        assert settled(cache, 'a', lambda: {'count': 7})['value'] == {'count': 7}
        clock[0] += 3
        def slow():
            started.set()
            assert release.wait(3)
            raise RuntimeError('synthetic outage')
        before = perf_counter()
        for _ in range(1000):
            assert cache.read('a', slow)['value'] == {'count': 7}
        assert perf_counter() - before < .25
        assert started.wait(1)
        assert len(cache.pool._threads) == 1
        release.set()
        end = perf_counter() + 2
        while cache.rows['a']['loading'] and perf_counter() < end:
            sleep(.005)
        assert cache.read('a', slow)['state'] == 'stale'
        clock[0] += 25
        assert cache.read('a', lambda: {'count': 8})['value'] is None
        assert settled(cache, 'a', lambda: {'count': 8})['value'] == {'count': 8}
    finally:
        release.set()
        cache.close()


def test_saturation_has_no_backlog_and_does_not_block_another_lane():
    busy = Snapshots(workers=1, limit=2)
    home = Snapshots(workers=1)
    release = Event()
    calls = []
    try:
        busy.read('active', lambda: release.wait(3) or {})
        for i in range(1000):
            busy.read(str(i), lambda: calls.append(True) or {})
        assert len(busy.rows) <= 2
        assert busy.pool._work_queue.qsize() == 0
        assert not calls
        assert settled(home, 'home', lambda: {'brief': 'saved'})['value']['brief'] == 'saved'
    finally:
        release.set()
        busy.close()
        home.close()


def test_snapshot_copy_isolation_budget_and_invalidation():
    cache = Snapshots(workers=2, limit=2, byte_limit=200)
    release = Event()
    try:
        first = settled(cache, ('alice', 1), lambda: {'rows': [1]})
        first['value']['rows'].append(2)
        assert cache.read(('alice', 1), lambda: {})['value'] == {'rows': [1]}
        assert settled(cache, ('bob', 1), lambda: {'rows': [3]})['value'] == {'rows': [3]}
        assert settled(cache, 'large', lambda: {'huge': 'x' * 200})['state'] == 'unavailable'
        cache.read('old', lambda: release.wait(3) and {'old': True})
        cache.invalidate('old')
        assert settled(cache, 'old', lambda: {'new': True})['value'] == {'new': True}
        release.set()
    finally:
        release.set()
        cache.close()


def test_planner_failure_is_unknown_not_empty(monkeypatch):
    import top_bar_api as api
    import supabase_backend as db
    monkeypatch.setattr(db, 'is_configured', lambda: True)
    monkeypatch.setattr(db, 'reconcile_daily_execution_timers', Mock(side_effect=TimeoutError))
    result = api.load_daily_planner_status({'sub': 'fixture', 'can_manage_daily_planner': True})
    assert result['available'] is False
    assert 'timer' not in result


def test_home_loaders_only_read_saved_sources(monkeypatch):
    import home_fast
    import home_sports_morning_brief as sports
    import home_meta_morning_brief as meta
    import morning_design_queue
    today = date(2026, 11, 18)
    saved = dict(date=str(today), recommendations=[dict(title='Synthetic', recommendation='Saved brief', links=[])])
    monkeypatch.setattr(sports, 'get_app_setting', lambda *a, **k: saved)
    monkeypatch.setattr(sports, 'archive_page', lambda *a, **k: ([], None))
    statuses = Mock(return_value=[])
    monkeypatch.setattr(morning_design_queue, 'list_jobs', statuses)
    assert home_fast.sports_data(today)['saved'] == saved
    statuses.assert_called_once_with(str(today), display_only=True)
    monkeypatch.setattr(meta, 'get_app_setting', lambda *a, **k: {'saved': True})
    monkeypatch.setattr(meta.home_design_refresh, 'render_html', lambda *a: '<p>Saved</p>')
    monkeypatch.setattr(meta, 'account_roas', Mock(side_effect=AssertionError('live provider')))
    assert home_fast.meta_data(today)['refresh'] == '<p>Saved</p>'


def test_display_design_read_has_no_claim_lock_reconcile_or_network(monkeypatch):
    import morning_design_queue as queue
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchall.return_value = []
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.cursor.return_value = cursor
    monkeypatch.setattr(queue, 'connect', lambda: connection)
    for name in ('_release_delivered', '_deleted_designs'):
        monkeypatch.setattr(queue, name, Mock(side_effect=AssertionError(name)))
    monkeypatch.setattr(queue, '_published_designs', lambda *a: set())
    monkeypatch.setattr(queue, '_posted_designs', lambda *a: set())
    assert queue.list_jobs(display_only=True) == []
    assert all('FOR UPDATE' not in call.args[0] for call in cursor.execute.call_args_list)
