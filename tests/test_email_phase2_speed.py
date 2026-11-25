"""Bounded read reuse, identity fences and scheduling. Synthetic IMAP only."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import threading
import time
import pytest

from support_email_provider import ImapProvider, MailboxError
from support_email_read_connection import ReadConnectionSlot
from support_email_reads import ReadService
from tests.test_support_email import CONFIG
from tests.test_support_email_v2 import WireImap
from test_email_companion_receipts import inbox


class ManualTimer:
    def __init__(self, delay, callback): self.delay, self.callback = delay, callback
    def start(self): pass
    def cancel(self): pass


@pytest.fixture
def pooled():
    wires = []
    def factory(*args, **kwargs):
        wire = WireImap()
        wires.append(wire)
        return wire
    p = ImapProvider(CONFIG, connection_factory=factory, reuse_reads=True)
    p._read_slot.timer_factory = ManualTimer
    yield p, wires
    p.close_read_connections()


def test_read_reuse_reselects_readonly_and_validates_uidvalidity(pooled):
    p, wires = pooled
    for folder in ['INBOX', 'Archive', 'INBOX']:
        with p._connection(folder, '500'): pass
    assert len(wires) == 1
    assert [c for c in wires[0].calls if c[0] == 'select'] == [
        ('select','INBOX',True),('select','\"Archive\"',True),('select','INBOX',True)]
    with pytest.raises(MailboxError, match='identifiers changed'):
        with p._connection('INBOX', '999'): pass
    assert ('logout',) in wires[0].calls
    with p._connection('INBOX','500'): pass
    assert len(wires) == 2


def test_write_discards_read_socket_and_never_retains_write_connection(pooled):
    p, wires = pooled
    with p._connection('INBOX','500'): pass
    with p._connection('INBOX','500',write=True): pass
    assert len(wires) == 2
    assert all(('logout',) in w.calls for w in wires)
    assert ('select','INBOX',False) in wires[1].calls
    with p._connection('INBOX','500'): pass
    assert len(wires) == 3


def test_read_failure_discards_wire_before_reconnect(pooled):
    p, wires = pooled
    with p._connection('INBOX','500'): pass
    wires[0].select = Mock(side_effect=ConnectionResetError('synthetic private text'))
    with pytest.raises(MailboxError) as caught:
        with p._connection('INBOX','500'): pass
    assert 'private' not in str(caught.value)
    assert ('logout',) in wires[0].calls
    with p._connection('INBOX','500'): pass
    assert len(wires) == 2


def test_stale_reused_socket_reconnects_safe_read_once(pooled):
    from tests.test_support_email import header
    p, wires = pooled
    first = p.read_message(header())
    wires[0].select = Mock(side_effect=ConnectionResetError('synthetic private peer'))
    assert p.read_message(header()) == first
    assert len(wires) == 2
    assert ('logout',) in wires[0].calls


def test_slot_idle_and_absolute_lifetime_and_stale_timer_cannot_close_borrowed_wire():
    now = [0]
    closed = []
    slot = ReadConnectionSlot(closed.append, clock=lambda:now[0], timer=ManualTimer)
    wire = object()
    with slot.lock:
        assert slot.take() is None
        assert slot.keep(wire)
        stale_timer = slot.timer
        now[0] = 5
        assert slot.take() is wire
        now[0] = 11
        stale_timer.callback()
        assert not closed
        assert slot.keep(wire)
        now[0] = 22
        assert slot.take() is None
        assert closed == [wire]
        assert slot.keep(wire)
        for moment in [30,38,46,54,62,70,78]:
            now[0] = moment
            assert slot.take() is wire
            assert slot.keep(wire)
        now[0] = 82
        assert slot.take() is None
        assert closed == [wire, wire]
    slot.close()


def test_idle_timer_closes_without_another_request():
    closed = threading.Event()
    slot = ReadConnectionSlot(lambda _:closed.set(), idle_seconds=.02)
    with slot.lock:
        slot.take()
        assert slot.keep(object())
    assert closed.wait(1)
    slot.close()


def test_shutdown_while_borrowed_does_not_retain_connection(pooled):
    p, wires = pooled
    entered, release = threading.Event(), threading.Event()
    def read():
        with p._connection('INBOX','500'):
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(read)
        assert entered.wait(2)
        p.close_read_connections()
        release.set()
        future.result(timeout=2)
    assert ('logout',) in wires[0].calls
    assert p._read_slot.idle is None


def test_concurrent_readers_never_share_active_socket(pooled):
    p, wires = pooled
    active = [0]; maximum = [0]
    def read(_):
        with p._connection('INBOX','500'):
            active[0] += 1; maximum[0] = max(maximum[0],active[0])
            time.sleep(.001)
            active[0] -= 1
    with ThreadPoolExecutor(4) as pool: list(pool.map(read,range(12)))
    assert maximum[0] == 1 and len(wires) == 1


def test_queued_history_yields_to_selected_body_and_metrics_exclude_identifiers(caplog):
    reads = ReadService(Mock(), Mock())
    reads.pool.shutdown(wait=True)
    reads.pool = Mock()
    from concurrent.futures import Future
    history = Future()
    reads.jobs[('related_headers_many','private-message-id')] = (history,999)
    done = Future(); done.set_result({'text':'synthetic'})
    reads.pool.submit.return_value = done
    assert reads.request(('read_message','private-message-id'),lambda:None) == {'text':'synthetic'}
    assert history.cancelled()
    reads.close()


def test_closed_slot_is_not_reused(pooled):
    p, wires = pooled
    with p._connection('INBOX','500'): pass
    p.close_read_connections()
    with p._connection('INBOX','500'): pass
    assert len(wires) == 2
    assert all(('logout',) in w.calls for w in wires)


def test_busy_history_retries_after_deadline_without_blocking_open_body(inbox, monkeypatch):
    w, imap = inbox
    w.open_thread(w.state['threads'][0]['thread_key'])
    selected, version = w.state['selected'], w.state['mailbox_version']
    original = imap.related_headers_many
    loader = Mock(side_effect=MailboxError('Busy', code='busy', retry_after=7))
    monkeypatch.setattr(imap, 'related_headers_many', loader)
    w.resolve_thread(selected, version)
    deadline = w.state['history_retry_at']
    assert w.state['history_pending']
    assert w.model()['history_retry_ms'] > 6000
    assert any(m['expanded'] for m in w.model()['messages'])
    w.resolve_thread(selected, version)
    assert loader.call_count == 1
    monkeypatch.setattr(imap, 'related_headers_many', original)
    monkeypatch.setattr('support_email_workspace.time.monotonic',lambda:deadline+1)
    w.resolve_thread(selected, version)
    assert not w.state['history_pending']


def test_queue_metrics_and_optional_history_admission_do_not_log_message_identity(caplog):
    import logging
    from support_email_runtime import _BACKGROUND
    reads = ReadService(Mock(), Mock())
    with caplog.at_level(logging.INFO, logger='support_email_reads'):
        result = reads.request(('related_headers_many','private-source@example.test'),
                               lambda:_BACKGROUND.get(), wait=True)
    reads.close()
    assert result is True
    assert 'email_read_queue stage=related_headers_many wait_ms=' in caplog.text
    assert 'private-source' not in caplog.text


def test_safe_read_retry_preserves_background_priority():
    from support_email_provider import _retry_read
    from support_email_runtime import operation, background_operation
    lanes = []
    class Provider:
        background = False
        @_retry_read
        def read(self):
            lanes.append(background_operation())
            if len(lanes) == 1:
                raise MailboxError('Synthetic peer dropped', code='reset', retryable=True)
            return 'reconnected'
    with operation(background=True):
        assert Provider().read() == 'reconnected'
    assert lanes == [True, True]
