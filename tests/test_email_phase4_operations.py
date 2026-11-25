"""Bounded metrics, admin diagnostics and durable restart/overlap fault injection."""
from datetime import datetime, timezone
from unittest.mock import Mock
import json
import pytest
import inbox_certificate_replies as replies
import inbox_companion as state
from support_email_operations import OperationalMetrics, report, browser_summary, backlog_progress, poll_delay, HealthMonitor
from test_email_companion_receipts import inbox
from test_inbox_certificate_replies import mail, database, offline, header, enable, row, MAILBOX, orders


@pytest.fixture(autouse=True)
def isolated_metrics(monkeypatch):
    metrics = OperationalMetrics()
    monkeypatch.setattr(replies, 'METRICS', metrics)
    return metrics


def test_metrics_are_bounded_private_and_ignore_admission_as_connection_failures():
    clock = [1000]
    metrics = OperationalMetrics(clock=lambda: clock[0])
    for i in range(1000):
        metrics.observe('queue_wait_ms', i)
        metrics.connection_failed('reset')
        metrics.poll('success', i, 30)
    for code in ('busy', 'pending', 'deferred', 'customer@example.test'):
        metrics.connection_failed(code)
    for value in (float('inf'), float('nan'), -1, True, 'secret'):
        metrics.observe('imap_read_ms', value)
    metrics.observe('secret@example.test', 1)
    result = metrics.snapshot()
    assert result['latency']['queue_wait_ms']['count'] == 200
    assert result['connection_failures_5m'] == 200
    assert result['latency']['imap_read_ms']['count'] == 0
    assert 'secret' not in json.dumps(result)
    clock[0] += 301
    assert metrics.snapshot()['connection_failures_5m'] == 0


def test_health_thresholds_do_not_claim_disabled_or_warming_worker_is_healthy():
    now = datetime(2026, 11, 25, 0, 10, tzinfo=timezone.utc).timestamp()
    assert report({}, {}, {}, now=now)['state'] == 'off'
    assert report({'enabled': True, 'changed_at': '2026-11-25T00:09:00+00:00'}, {}, {}, now=now)['state'] == 'warming_up'
    result = report({'enabled': True, 'checked_at': '2026-11-25T00:00:00+00:00',
                     'oldest_pending_received_at': '2026-11-25T00:00:00+00:00', 'actor': 'secret'},
                    {'oldest_queued_at': '2026-11-24T00:00:00+00:00', 'unknown_count': 1,
                     'oldest_copy_pending_at': '2026-11-24T00:00:00+00:00'},
                    {'connection_failures_5m': 3}, now=now)
    assert result['state'] == 'needs_attention'
    assert {a['code'] for a in result['alerts']} == {'poll_stale', 'backlog', 'queue_age',
                                                  'uncertain_delivery', 'sent_copy_lag', 'repeated_connection_failures'}
    assert 'secret' not in json.dumps(result)


def test_browser_aggregates_are_untrusted_and_whitelisted():
    result = browser_summary({'cold_body': {'count': 1, 'p50_ms': 55, 'p95_ms': float('inf'), 'message': 'secret'},
                              'cached_body': {'count': 999}, 'token': 'secret'})
    assert result == {'cold_body': {'count': 1, 'p50_ms': 55}}


def test_backlog_window_remains_explicit_without_uid_or_customer_identity():
    now = '2026-11-25T00:00:00+00:00'
    result = backlog_progress({}, {'uidvalidity': '10', 'last_uid': 50, 'uidnext': 100,
                                  'messages': [header('2'), header('3')]},
                              {'uidvalidity': '10', 'last_uid': 2}, now)
    assert result['pending_visible_count'] == 1 and result['pending_window_limited']
    assert result['oldest_pending_received_at'] == header()['received_at'].isoformat()
    assert all('uid' not in k for k in result)


def test_drop_after_queue_before_cursor_save_recovers_without_duplicate(mail, monkeypatch):
    enable(mail)
    original = state.save
    def interrupted(cur, key, value):
        if key == replies.SETTING:
            raise ConnectionError('synthetic process interruption')
        return original(cur, key, value)
    with monkeypatch.context() as patch:
        patch.setattr(state, 'save', interrupted)
        with pytest.raises(ConnectionError):
            replies.tick(mail.imap)
    assert row(mail)['status'] == 'queued'
    # A new registry/process resumes the durable operation, not a new send intent.
    from support_email_durable import DurableRegistry, MailStore
    restarted = DurableRegistry(MailStore(connect=state.prep.connect))
    monkeypatch.setattr('support_email_durable.REGISTRY', restarted)
    assert replies.tick(mail.imap)
    smtp = Mock()
    smtp.submit.return_value = {'status': 'accepted'}
    op = row(mail)['operation_id']
    restarted.submit_prepared(op, MAILBOX, smtp)
    restarted.submit_prepared(op, MAILBOX, smtp)
    assert smtp.submit.call_count == 1 and row(mail)['attempts'] == 1


def test_deploy_overlap_stale_snapshot_cannot_create_another_intent(mail, monkeypatch):
    config = enable(mail)
    original = replies.inspect
    paused = [False]
    def overlapping(*args, **kwargs):
        result = original(*args, **kwargs)
        if not paused[0]:
            paused[0] = True
            # Another process finishes while the first still has an eligible snapshot.
            replies.handle(mail.imap, header(), dict(config))
        return result
    monkeypatch.setattr(replies, 'inspect', overlapping)
    replies.handle(mail.imap, header(), config)
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 1


def test_sustained_arrivals_catch_up_with_monotonic_cursor_and_one_intent_each(mail, monkeypatch, isolated_metrics):
    enable(mail)
    arrivals = [header(str(i)) for i in range(8, 20)]
    for i,h in enumerate(arrivals):h['sender']['email'] = f'customer{i}@example.test'
    mail.imap.headers.extend(arrivals)
    monkeypatch.setattr('support_email_store.load_orders', lambda emails: [{**orders()[0], 'customer_email': e} for e in emails])
    cursors = []
    for _ in range(15):
        assert replies.tick(mail.imap)
        cursors.append(int(state.read(replies.SETTING)['cursor']['last_uid']))
        if state.read(replies.SETTING).get('pending_visible_count'):
            assert poll_delay(state.read(replies.SETTING)) == 5
    assert cursors == sorted(cursors) and cursors[-1] == 19
    assert poll_delay(state.read(replies.SETTING)) == 30
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 13


def test_outbox_operational_ages_use_actual_sql_status_and_are_mailbox_scoped(mail):
    enable(mail)
    replies.tick(mail.imap)
    stats = mail.registry.store.diagnostics(MAILBOX)
    assert stats['oldest_queued_at'] and stats['unknown_count'] == 0
    mail.sql.execute("UPDATE support_email_outbox SET status='unknown'")
    assert mail.registry.store.diagnostics(MAILBOX)['unknown_count'] == 1
    assert mail.registry.store.diagnostics('other@example.test')['unknown_count'] == 0
    mail.sql.execute("UPDATE support_email_outbox SET status='accepted',accepted_at=now(),copy_status='failed'")
    stats = mail.registry.store.diagnostics(MAILBOX)
    assert stats['oldest_queued_at'] is None and stats['oldest_copy_pending_at'] and stats['copy_pending_count'] == 1


def test_worker_catchup_is_bounded_and_idle_cadence_is_preserved(monkeypatch):
    monkeypatch.setattr('support_email_provider.ImapProvider', Mock())
    def check(imap, *, progress):
        progress({'pending_visible_count': 2})
        return True
    monkeypatch.setattr(replies, 'tick', check)
    worker = replies.CertificateReplyWorker(Mock())
    worker.stop = Mock()
    worker.stop.is_set.side_effect = [False, True]
    worker.run()
    worker.stop.wait.assert_called_once_with(5)
    assert poll_delay({}) == 30


def test_health_monitor_is_rate_limited_private_and_cannot_stop_mail(caplog):
    clock = [1000]
    loader = Mock(return_value={'state': 'needs_attention', 'alerts': [{'code': 'poll_stale'}]})
    monitor = HealthMonitor(loader=loader, clock=lambda: clock[0])
    for _ in range(20):monitor.check('support@example.test')
    assert loader.call_count == 1
    assert 'poll_stale' in caplog.text and 'support@example.test' not in caplog.text
    clock[0] += 60
    loader.side_effect = RuntimeError('secret connection string')
    assert monitor.check('support@example.test') is None
    assert 'secret connection string' not in caplog.text


def test_operational_diagnostics_remain_admin_only(inbox, monkeypatch):
    import uuid
    import support_email_workspace as workspace
    w, _ = inbox
    loader = Mock()
    monkeypatch.setattr('support_email_operations.diagnostics', loader)
    monkeypatch.setattr(workspace.os_accounts, 'is_admin', lambda user: False)
    monkeypatch.setattr(workspace.os_accounts, 'can_access_page', lambda *args: True)
    w.handle({'id': str(uuid.uuid4()), 'action': 'mail_diagnostics', 'selection_metrics': {'token': 'must not survive'}})
    loader.assert_not_called()
    assert w.model()['admin_operations'] is None
