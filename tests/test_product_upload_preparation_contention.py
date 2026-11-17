"""Busy preparation resumes automatically without holding the cache lock."""
import threading
from unittest.mock import Mock

import pytest

import product_upload_artwork as artwork
import product_upload_jobs as jobs


def test_busy_server_is_retryable_without_changing_the_intake(monkeypatch):
    row = {'data': {'workflow_version': 3}}
    store = Mock(read=Mock(return_value=row))
    monkeypatch.setattr(artwork, 'Intakes', lambda _: store)
    monkeypatch.setattr(artwork, '_slots', threading.BoundedSemaphore(1))
    artwork._slots.acquire()
    try:
        with pytest.raises(artwork.PreparationBusyError):
            artwork.prepare(None, None, 'new-design', 'actor')
        store.locked.assert_not_called()
    finally:
        artwork._slots.release()


def test_generation_waits_outside_cache_lock_then_leases_artwork(monkeypatch, tmp_path):
    row = {'id': 'exact-source'}
    ensure = Mock(side_effect=[artwork.PreparationBusyError('busy'), (row, tmp_path)])
    monkeypatch.setattr(artwork, 'ensure_ready', ensure)
    acquired = []

    def pause(_):
        # A different preparation thread must be able to finish its cache write.
        def writer():
            with artwork._cache_lock:
                acquired.append(True)
        thread = threading.Thread(target=writer)
        thread.start()
        thread.join(1)
        assert not thread.is_alive()

    monkeypatch.setattr(artwork, 'sleep', pause)
    progress = Mock()
    with artwork.prepared(row, None, None, progress=progress) as result:
        assert result == (row, tmp_path)
        assert artwork._cache_users[tmp_path] == 1
    assert tmp_path not in artwork._cache_users
    assert acquired == [True] and ensure.call_count == 2
    progress.assert_called_once_with('Waiting for source preparation')


def test_wait_is_bounded_and_does_not_retry_renderer_errors(monkeypatch, tmp_path):
    ensure = Mock(side_effect=artwork.PreparationBusyError('busy'))
    monkeypatch.setattr(artwork, 'ensure_ready', ensure)
    monkeypatch.setattr(artwork, 'monotonic', Mock(side_effect=[0, 301]))
    with pytest.raises(artwork.PreparationBusyError, match='still active'):
        with artwork.prepared({}, None, None):
            pytest.fail('busy artwork cannot be rendered')
    ensure.side_effect = None
    ensure.return_value = ({}, tmp_path)
    monkeypatch.setattr(artwork, 'monotonic', lambda: 0)
    with pytest.raises(artwork.PreparationBusyError, match='renderer'):
        with artwork.prepared({}, None, None):
            raise artwork.PreparationBusyError('renderer')
    assert ensure.call_count == 2
    assert tmp_path not in artwork._cache_users


def test_background_preparation_waits_for_same_source_instead_of_false_ready(monkeypatch):
    pending = {'data': {'server_artwork': {'state': 'Preparing'}}}
    ready = {'data': {'server_artwork': {'state': 'Ready'}}}
    process = Mock(side_effect=[pending, artwork.PreparationBusyError('other source'), ready])
    monkeypatch.setattr(artwork, 'prepare', process)
    monkeypatch.setattr('time.sleep', lambda _: None)
    progress = Mock()
    assert jobs._prepare_artwork(None, 'one', 'actor', None, progress) == ready
    assert process.call_count == 3 and progress.call_count == 2


def test_cache_recovery_does_not_consume_in_progress_same_source(monkeypatch):
    row = {'id': 'one', 'actor_id': 'actor', 'data': {}}
    pending = {**row, 'data': {'server_artwork': {'state': 'Preparing'}}}
    monkeypatch.setattr(artwork, 'current', Mock())
    monkeypatch.setattr(artwork, 'ready', Mock(side_effect=ValueError('expired')))
    monkeypatch.setattr(artwork, 'prepare', Mock(return_value=pending))
    with pytest.raises(artwork.PreparationBusyError):
        artwork.ensure_ready(row, None, None)
