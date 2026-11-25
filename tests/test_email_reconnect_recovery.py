"""Synthetic disconnects: no live mailbox, sends, credentials or app startup."""
from unittest.mock import Mock
import pytest
import inbox_certificate_replies as replies
from support_email_provider import MailboxError
from test_email_companion_receipts import inbox


def test_worker_coordination_never_accumulates_network_backoff():
    failures = 0
    for _ in range(30):
        failures, delay = replies.retry_delay(MailboxError('busy', code='busy'), failures)
        assert failures == 0 and delay == 5
    assert replies.retry_delay(MailboxError('cooldown', code='deferred', retry_after=47), 2) == (2, 47)
    assert replies.retry_delay(MailboxError('cooldown', code='deferred', retry_after=900), 2) == (2, 300)


def test_worker_reconnects_with_fresh_provider_and_resumes_automatically(monkeypatch):
    provider = Mock()
    monkeypatch.setattr('support_email_provider.ImapProvider', provider)
    tick = Mock(side_effect=[MailboxError('busy', code='busy'),
                            MailboxError('cooldown', code='deferred', retry_after=42), True])
    monkeypatch.setattr(replies, 'tick', tick)
    worker = replies.CertificateReplyWorker(Mock())
    worker.stop = Mock()
    worker.stop.is_set.side_effect = [False, False, False, True]
    worker.run()
    assert [c.args[0] for c in worker.stop.wait.call_args_list] == [5, 42, 30]
    assert provider.call_count == tick.call_count == 3
    assert all(c.kwargs == {'background': True} for c in provider.call_args_list)


def test_selected_body_recovers_without_refresh_reset_or_replaying_writes(inbox, monkeypatch):
    w, imap = inbox
    original = imap.read_message
    calls = [0]
    def interrupted(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise MailboxError('Connection lost', code='reset', retryable=True, retry_after=20)
        return original(*args, **kwargs)
    monkeypatch.setattr(imap, 'read_message', interrupted)
    w.handle({'id':'b1343a14-3d01-4c44-874f-274d313ce694', 'action':'open_thread', 'thread_key':w.state['threads'][0]['thread_key']})
    selected = w.state['active_message']
    assert w.state['recovery_state'] == 'waiting'
    assert selected in w.state['expanded']
    w.state['load_retry_at'] = 0  # Advance the scheduler deadline, not a user reset.
    w.reconnect()
    assert w.state['active_message'] == selected
    assert w.state['recovery_state'] == ''
    assert any(m['expanded'] for m in w.model()['messages'])
    assert not [c for c in imap.calls if c[0] in {'append','move','delete'}]


@pytest.mark.parametrize('code', ['authentication','tls','configuration'])
def test_credential_or_trust_failure_requires_attention(inbox, code):
    w, _ = inbox
    w._body_failed('fixture', MailboxError('Needs attention', code=code))
    assert w.state['recovery_state'] == 'stopped'


def test_missing_message_is_not_retried_as_connection_failure(inbox):
    w, _ = inbox
    w._body_failed('fixture', MailboxError('No longer in mailbox', code='operation'))
    assert not w.state.get('recovery_state')
