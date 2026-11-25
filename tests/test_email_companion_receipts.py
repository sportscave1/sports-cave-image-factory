"""Automatic-send attribution against disposable SQL and fabricated mail only."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock
import uuid

import pytest
import support_email_store as store
import support_email_workspace as workspace
from support_email_compose import default_settings, build_mime, new_draft
from support_email_smtp import SendRegistry
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp
from tests.test_support_email import CONFIG, MAILBOX, USER
from tests.test_support_email_v2 import SMTP_CONFIG
from test_inbox_certificate_replies import database, mail, enable
import inbox_certificate_replies as replies
import inbox_companion as state


def sql_receipts(monkeypatch):
    @contextmanager
    def cursor(write=False):
        assert not write
        with state.prep.connect() as c, c.cursor() as q:
            yield q
    monkeypatch.setattr(store, 'cursor', cursor)


def test_certificate_receipt_requires_exact_request_and_actual_acceptance(mail, monkeypatch):
    sql_receipts(monkeypatch)
    config = enable(mail)
    source = mail.imap.headers[0]
    mailbox = mail.imap.configuration.address
    replies.handle(mail.imap, source, config)
    op = replies.operation(replies.identity(mailbox, source))
    frozen = mail.registry.store.get(mailbox, op)
    ids = [source['message_id'], frozen['message_id'], '<unanswered@example.test>']
    for status in ['queued', 'in_progress', 'unknown', 'rejected']:
        mail.sql.execute("UPDATE support_email_outbox SET status=%s,accepted_at=now()", (status,))
        assert store.load_companion_receipts(mailbox, ids) == {}
    mail.sql.execute("UPDATE support_email_outbox SET status='accepted',accepted_at=NULL")
    assert store.load_companion_receipts(mailbox, ids) == {}
    mail.sql.execute("UPDATE support_email_outbox SET accepted_at=now(),copy_status='failed'")
    receipts = store.load_companion_receipts(mailbox.upper(), ids)
    assert set(receipts) == {source['message_id'], frozen['message_id']}
    assert all(r['status'] == 'sent' for r in receipts.values())
    assert store.load_companion_receipts('another@example.test', ids) == {}
    key = replies.identity(mailbox, source)
    mail.sql.execute("UPDATE app_settings SET value=value-'operation_id' WHERE key=%s", (key,))
    assert store.load_companion_receipts(mailbox, ids) == {}
    # A manual accepted reply is not enough to invent Companion attribution.
    assert mail.registry.store.get(mailbox, op)['attempts'] == 0


def test_existing_address_confirmation_also_has_authoritative_attribution(mail, monkeypatch):
    sql_receipts(monkeypatch)
    source = mail.imap.headers[0]
    mailbox = mail.imap.configuration.address
    key = state.PREFIX + state.prep.digest([mailbox.casefold(), source['message_id']])
    op = str(uuid.uuid5(uuid.NAMESPACE_URL, 'sports-cave-inbox:' + key))
    draft = new_draft(mailbox, mode='reply', header=source)
    draft.update(id=op, operation_id=op)
    frozen = build_mime(draft, mailbox, 'Fixture', default_settings()['signatures'])
    mail.registry.store.prepare(mailbox, op, frozen)
    mail.sql.execute("UPDATE support_email_outbox SET status='accepted',accepted_at=now()")
    value = dict(key=key, kind='address', header=source)
    with state.prep.connect() as c, c.cursor() as q:
        state.save(q, key, value)
    receipts = store.load_companion_receipts(mailbox, [source['message_id']])
    assert set(receipts) == {source['message_id'], frozen['message_id']}
    mail.sql.execute("UPDATE app_settings SET value=jsonb_set(value,'{kind}','\"hold\"') WHERE key=%s", (key,))
    assert store.load_companion_receipts(mailbox, [source['message_id']]) == {}


def test_lookup_is_bounded_one_metadata_query_without_mime_or_credentials(monkeypatch):
    query = Mock()
    query.fetchall.return_value = []
    @contextmanager
    def cursor():
        yield query
    monkeypatch.setattr(store, 'cursor', cursor)
    assert store.load_companion_receipts(MAILBOX, ['', None, 'x' * 999]) == {}
    query.execute.assert_not_called()
    ids = [f'<message-{i}@example.test>' for i in range(2100)]
    assert store.load_companion_receipts(MAILBOX, ids + ids) == {}
    query.execute.assert_called_once()
    sql, params = query.execute.call_args.args
    import json
    assert len(json.loads(params[0])) == 2000 and params[1] == MAILBOX
    assert 'payload' not in sql and 'bytes' not in sql


def test_receipt_cache_refreshes_without_provider_calls_and_survives_metadata_outage(monkeypatch):
    w = object.__new__(workspace.Workspace)
    w.state, w.config, w.durable = {}, CONFIG, True
    clock = [100.0]
    monkeypatch.setattr(workspace.time, 'monotonic', lambda: clock[0])
    receipt = {'status': 'sent', 'accepted_at': datetime.now(timezone.utc)}
    loader = Mock(return_value={'<source@example.test>': receipt, '<sent@example.test>': receipt})
    monkeypatch.setattr(store, 'load_companion_receipts', loader)
    sent = {'message_id': '<sent@example.test>', 'in_reply_to': ('<source@example.test>',)}
    assert w._companion_receipts([sent])['<sent@example.test>'] == receipt
    assert set(loader.call_args.args[1]) == {'<source@example.test>', '<sent@example.test>'}
    clock[0] += 29
    w._companion_receipts([sent])
    assert loader.call_count == 1
    clock[0] += 2
    loader.side_effect = store.SupportStorageError('fixture unavailable')
    assert w._companion_receipts([sent])['<sent@example.test>'] == receipt
    assert loader.call_count == 2
    assert w._companion_receipts([{'message_id': '<different@example.test>'}]) == {}


@pytest.fixture
def inbox(monkeypatch):
    monkeypatch.setattr(store, 'load_email_settings', lambda *a: (default_settings(), None))
    monkeypatch.setattr(store, 'load_metadata', lambda *a: {})
    monkeypatch.setattr(store, 'load_orders', lambda *a, **kw: [])
    monkeypatch.setattr(store, 'load_assignees', lambda: [USER])
    monkeypatch.setattr(store, 'audit', Mock())
    imap = MailboxFixture(count=3)
    w = workspace.Workspace({}, USER, CONFIG, SMTP_CONFIG, imap=imap, smtp=fixture_smtp(), registry=SendRegistry())
    w.load()
    return w, imap


def test_inbox_and_message_badges_leave_new_followup_unanswered(inbox, monkeypatch):
    w, imap = inbox
    source = w.state['threads'][0]['messages'][-1]
    receipt = {'status': 'sent', 'accepted_at': datetime(2026, 11, 25, 1, 40, tzinfo=timezone.utc)}
    lookup = Mock(return_value={source['message_id']: receipt})
    monkeypatch.setattr(w, '_companion_receipts', lookup)
    w.open_thread(w.state['threads'][0]['thread_key'])
    calls = list(imap.calls)
    model = w.model()
    marked = next(t for t in model['threads'] if t['key'] == w.state['selected'])
    assert marked['companion'] == {'status': 'sent', 'time': '25 Nov · 12:40 PM'}
    assert next(m for m in model['messages'] if m['key'] == workspace.reference_key(source))['companion'] == marked['companion']
    assert not any(t.get('companion') for t in model['threads'] if t['key'] != marked['key'])
    assert w.model()['threads'] is model['threads']
    assert imap.calls == calls
    assert 'companion' not in w.state['list_model'][0]
    followup = deepcopy(source)
    followup.update(uid='999', message_id='<new-question@example.test>', in_reply_to=(source['message_id'],))
    w.state['threads'][0]['messages'].append(followup)
    model = w.model()
    assert not next(t for t in model['threads'] if t['key'] == marked['key']).get('companion')
    assert any(m['companion'] for m in model['messages'])


def test_permission_revocation_performs_no_receipt_lookup(inbox, monkeypatch):
    w, _ = inbox
    loader = Mock()
    monkeypatch.setattr(w, '_companion_receipts', loader)
    monkeypatch.setattr(workspace.os_accounts, 'can_access_page', lambda *a: False)
    assert not any(t.get('companion') for t in w.model()['threads'])
    loader.assert_not_called()
