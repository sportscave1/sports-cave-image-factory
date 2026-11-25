"""Synthetic mailbox and real disposable SQL; no production mail or customer fixtures."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
from email import policy as email_policy
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace
import json
import threading
import uuid

import pytest
import requests
import inbox_certificate_policy as policy
import inbox_certificate_replies as replies
import inbox_companion as state
from support_email_compose import default_settings
from support_email_durable import DurableRegistry, MailStore, decode
from test_auto_editions_jobs import database

MAILBOX = 'support@example.test'
ACTOR = {'id': 'fixture-admin', 'role': 'admin', 'is_active': True}


def header(uid='7'):
    return dict(uid=uid, uidvalidity='10', folder='INBOX', subject='Re: Your edition',
                sender={'name': 'Alex Fixture', 'email': 'customer@example.test'}, to=[{'name': '', 'email': MAILBOX}],
                cc=[], reply_to=[], message_id=f'<incoming-{uid}@example.test>', references=['<old@example.test>'],
                in_reply_to=['<old@example.test>'], received_at=datetime(2026, 1, 1, tzinfo=timezone.utc), automated=False)


def orders():
    return [dict(order_name='#SC123', customer_email='customer@example.test', fulfillment_status='FULFILLED',
                 editions=[{'certificate_status': 'Certificate Ready'}])]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import imaplib, smtplib
    def forbidden(*args, **kwargs):
        pytest.fail('External mail/network forbidden')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(imaplib, 'IMAP4_SSL', forbidden)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', forbidden)


@pytest.mark.parametrize('subject,text,is_reply', [
    ('My order', 'There was no package slip inside to access the certificate. Could you send it please?', False),
    ('Certificate missing', 'Please help', False),
    ('Re: Certificate missing', "I haven't received it", True),
    ('My order', 'Packing slip not received', False),
    ('My order', 'I did not get my certificate', False),
    ('My order', 'Could you please resend my certificate?', False),
    ('My order', 'Where can I access my certificate?', False),
    ('My order', 'My COA is missing', False),
    ('My order', 'There was no packing slip in the parcel', False),
    ('My order', 'How do I find the certificate?', False),
])
def test_missing_document_requests(subject, text, is_reply):
    assert policy.request(subject, text, is_reply=is_reply)


@pytest.mark.parametrize('subject,text,is_reply', [
    ('Re: Certificate missing', 'Thanks, all good!', True),
    ('My order', 'When will the parcel arrive?', False),
    ('My order', 'Thanks\nOn Tuesday someone wrote:\nMy certificate is missing', False),
    ('My order', '> My certificate is missing', False),
    ('My order', 'The certificate is not missing', False),
    ('My order', 'I already received my certificate, please send the frame', False),
    ('My order', 'My certificate is missing and the photo is damaged', False),
    ('My order', 'Certificate missing, please refund my order', False),
    ('My order', 'Certificate missing. Please change my shipping address', False),
    ('My order', 'The parcel is missing', False),
])
def test_quotes_thanks_and_other_issues_stay_manual(subject, text, is_reply):
    assert not policy.request(subject, text, is_reply=is_reply)


def test_customer_requires_exact_email_ready_certificate_and_named_order():
    assert policy.ready_customer(header(), 'certificate missing', orders())
    for changed in [dict(customer_email='different@example.test'), dict(fulfillment_status='cancelled'),
                    dict(editions=[{'certificate_status': 'Pending'}])]:
        assert not policy.ready_customer(header(), 'certificate missing', [{**orders()[0], **changed}])
    assert not policy.ready_customer(header(), 'Missing certificate SC124', orders())
    assert not policy.ready_customer(header(), 'Missing certificates SC123 and SC124', orders())


@pytest.mark.parametrize('change', [
    {'automated': True}, {'error': 'bad headers'}, {'message_id': ''},
    {'sender': {'email': MAILBOX}}, {'sender': {'email': 'no-reply@example.test'}},
    {'reply_to': [{'email': 'different@example.test'}]},
    {'to': [{'email': 'someone-else@example.test'}]},
])
def test_automated_and_redirected_senders_excluded(change):
    assert not policy.safe_sender({**header(), **change}, MAILBOX)


class Mailbox:
    configuration = SimpleNamespace(address=MAILBOX, configured=True)
    def __init__(self):
        self.headers = [header()]
        self.text = 'My certificate was not received. Can you send it please?'
        self.warnings = []
        self.sent = []
        self.reads = []
        self.validity = '10'
    def notification_snapshot(self, cursor):
        high = max([int(h['uid']) for h in self.headers] or [0])
        same = cursor and str(cursor['uidvalidity']) == self.validity
        return dict(uidvalidity=self.validity, last_uid=high,
                    messages=[deepcopy(h) for h in self.headers if same and int(h['uid']) > int(cursor['last_uid'])])
    def read_session(self):
        return nullcontext(self)
    def notification_target(self, uidvalidity, uid, message_id=''):
        return next((deepcopy(h) for h in self.headers if h['uidvalidity'] == str(uidvalidity)
                     and h['uid'] == str(uid) and (not message_id or h['message_id'] == message_id)), None)
    def read_message(self, h, **kwargs):
        assert kwargs == {'load_inline_images': False}
        self.reads.append(h['message_id'])
        return {'text': self.text, 'warnings': self.warnings}
    def discover_folders(self, **kwargs):
        return {'folders': [{'name': 'Sent', 'role': 'sent'}]}
    def related_headers(self, folder, identifiers, **kwargs):
        assert folder == 'Sent'
        return deepcopy(self.sent)


@pytest.fixture
def mail(database, monkeypatch):
    jobs, sql = database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    sql.execute((Path(__file__).resolve().parents[1] / 'migrations/20261006063028_support_email_durable_delivery.sql').read_text())
    jobs.connect.commit = lambda self: None
    monkeypatch.setattr(state.prep, 'connect', jobs.connect)
    monkeypatch.setattr(state.prep, 'require_user', lambda actor: None)
    monkeypatch.setattr('support_email_store.load_assignees', lambda: [ACTOR])
    monkeypatch.setattr('support_email_store.load_orders', lambda **kw: orders())
    monkeypatch.setattr('support_email_store.load_email_settings', lambda *a: (default_settings(), None))
    registry = DurableRegistry(MailStore(connect=jobs.connect))
    monkeypatch.setattr('support_email_durable.REGISTRY', registry)
    imap = Mailbox()
    monkeypatch.setattr('support_email_provider.ImapProvider', lambda *a, **kw: imap)
    monkeypatch.setattr('support_email_provider.load_configuration', lambda: imap.configuration)
    monkeypatch.setattr('support_email_smtp.load_smtp_configuration', lambda: SimpleNamespace(configured=True, address=MAILBOX))
    return SimpleNamespace(imap=imap, sql=sql, registry=registry)


def enable(mail, existing=True):
    replies.configure(ACTOR, True, existing=header() if existing else None)
    return state.read(replies.SETTING)


def row(mail):
    return mail.registry.store.get(MAILBOX, replies.operation(replies.identity(MAILBOX, header())))


def test_current_request_thread_signature_link_loop_headers_and_one_send(mail):
    enable(mail)
    assert replies.tick(mail.imap)
    frozen = row(mail)
    mime = decode(frozen['payload'])
    msg = BytesParser(policy=email_policy.default).parsebytes(mime['bytes'])
    plain = msg.get_body(preferencelist=('plain',)).get_content()
    assert msg['In-Reply-To'] == header()['message_id']
    assert msg['Auto-Submitted'] == 'auto-replied' and msg['X-Auto-Response-Suppress'] == 'All'
    assert mime['recipients'] == ['customer@example.test']
    assert policy.COLLECTION_URL in plain and 'log in to access your certificate' in plain
    assert 'Framing is also available if required.' in plain and 'review' in plain
    assert plain.count('Kind regards') == 1 and plain.count('Nathan Baker') == 1
    assert not [p for p in msg.walk() if p.get_content_disposition() == 'attachment']
    assert not any(p.get_content_type() == 'application/pdf' for p in msg.walk())
    smtp = SimpleNamespace(submit=lambda *a, **kw: {'status': 'accepted'})
    assert mail.registry.submit_prepared(frozen['operation_id'], MAILBOX, smtp)['status'] == 'accepted'
    assert replies.tick(mail.imap)
    assert row(mail)['attempts'] == 1


def test_crash_recovery_keeps_one_intent_and_never_resends_unknown(mail):
    config = enable(mail)
    replies.handle(mail.imap, header(), config)
    frozen = row(mail)
    mail.registry.store.claim(MAILBOX, frozen['operation_id'])
    mail.registry.store.finish(MAILBOX, frozen['operation_id'], {'status': 'unknown'})
    mail.sql.execute('DELETE FROM app_settings WHERE key=%s', (replies.identity(MAILBOX, header()),))
    replies.handle(mail.imap, header(), config)
    assert row(mail)['status'] == 'unknown' and row(mail)['attempts'] == 1
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 1


def test_concurrent_scans_use_one_reply(mail):
    config = enable(mail)
    errors = []
    def handle():
        try: replies.handle(mail.imap, header(), config)
        except Exception as error: errors.append(error)
    threads = [threading.Thread(target=handle) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 1


def test_activation_only_new_mail_unless_current_explicitly_selected(mail):
    enable(mail, existing=False)
    replies.tick(mail.imap)
    assert not row(mail)
    mail.imap.headers.append(header('8'))
    replies.tick(mail.imap)
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 1


def test_current_and_new_mail_survive_reconfiguration(mail, monkeypatch):
    enable(mail, existing=False)
    other = header('8')
    other['sender']['email'] = 'second-customer@example.test'
    mail.imap.headers.append(other)
    monkeypatch.setattr('support_email_store.load_orders', lambda **kw:
                        [*orders(), {**orders()[0], 'customer_email': 'second-customer@example.test'}])
    replies.configure(ACTOR, True, existing=header())
    replies.tick(mail.imap)
    assert row(mail)['status'] == 'queued'
    replies.tick(mail.imap)
    mail.sql.execute('SELECT count(*) AS n FROM support_email_outbox')
    assert mail.sql.fetchone()['n'] == 2


def test_sent_reply_prevents_duplicate(mail):
    mail.imap.sent = [dict(sender={'email': MAILBOX}, in_reply_to=[header()['message_id']], references=[])]
    assert replies.preview_latest(ACTOR)['status'] == 'answered'
    with pytest.raises(ValueError, match='changed or already'):
        enable(mail)
    assert not row(mail)


@pytest.mark.parametrize('kind', ['draft', 'unknown'])
def test_existing_human_draft_or_unresolved_reply_preserved(mail, kind):
    if kind == 'draft':
        mail.sql.execute("""INSERT INTO support_email_drafts(mailbox,actor,draft_id,operation_id,payload)
          VALUES(%s,'human',%s,%s,%s::jsonb)""",
          (MAILBOX, str(uuid.uuid4()), str(uuid.uuid4()), json.dumps({'source_message': header()}, default=str)))
    else:
        mail.sql.execute("""INSERT INTO support_email_outbox(mailbox,operation_id,message_id,fingerprint,payload,status)
          VALUES(%s,%s,'<manual@example.test>','fixture',%s::jsonb,'unknown')""",
          (MAILBOX, str(uuid.uuid4()), json.dumps({'recipients': ['customer@example.test']})))
    assert replies.preview_latest(ACTOR)['status'] == 'review'
    assert not row(mail)


def test_disable_during_inspection_prevents_queue(mail, monkeypatch):
    config = enable(mail)
    original = replies.inspect
    def inspect(*args, **kwargs):
        result = original(*args, **kwargs)
        replies.configure(ACTOR, False)
        return result
    monkeypatch.setattr(replies, 'inspect', inspect)
    replies.handle(mail.imap, header(), config)
    assert not row(mail)


def test_reconnect_keeps_cursor_and_explicit_current_request(mail, monkeypatch):
    enable(mail)
    before = state.read(replies.SETTING)
    def interrupted(*args, **kwargs): raise ConnectionError('fixture')
    monkeypatch.setattr(mail.imap, 'read_message', interrupted)
    with pytest.raises(ConnectionError): replies.tick(mail.imap)
    assert state.read(replies.SETTING) == before and not row(mail)


def test_uidvalidity_rotation_never_replays_old_mail(mail):
    enable(mail)
    mail.imap.validity = '20'
    replies.tick(mail.imap)
    assert state.read(replies.SETTING)['cursor']['uidvalidity'] == '20'
    assert state.read(replies.SETTING)['initial_message'] is None and not row(mail)


def test_disabled_worker_no_mailbox_reads(mail):
    assert not replies.tick(mail.imap)
    assert not mail.imap.reads


def test_unavailable_certificate_and_unreadable_message_stay_manual(mail, monkeypatch):
    monkeypatch.setattr('support_email_store.load_orders', lambda **kw: [{**orders()[0], 'editions': []}])
    assert replies.preview_latest(ACTOR)['status'] == 'review'
    mail.imap.warnings = ['fixture incomplete body']
    assert replies.preview_latest(ACTOR)['status'] == 'review'
    mail.imap.headers[0]['automated'] = True
    assert replies.preview_latest(ACTOR)['status'] == 'ignored'
    assert not row(mail)


def test_inactive_and_non_admin_cannot_activate(mail):
    for changed in [dict(is_active=False), dict(role='worker')]:
        with pytest.raises(PermissionError): replies.configure({**ACTOR, **changed}, True)


def test_explicit_retry_after_review_rechecks_certificate_and_uses_same_intent(mail, monkeypatch):
    config = enable(mail)
    monkeypatch.setattr('support_email_store.load_orders', lambda **kw: [{**orders()[0], 'editions': []}])
    replies.handle(mail.imap, header(), config)
    assert not row(mail)
    monkeypatch.setattr('support_email_store.load_orders', lambda **kw: orders())
    replies.configure(ACTOR, True, existing=header())
    replies.tick(mail.imap)
    assert row(mail)['status'] == 'queued'


def test_missing_smtp_cannot_enable_automation(mail, monkeypatch):
    monkeypatch.setattr('support_email_smtp.load_smtp_configuration', lambda: SimpleNamespace(configured=False))
    with pytest.raises(ValueError, match='mailbox sender'):
        enable(mail)
    assert not state.read(replies.SETTING)


def test_different_sender_mailbox_cannot_enable_automation(mail, monkeypatch):
    monkeypatch.setattr('support_email_smtp.load_smtp_configuration',
                        lambda: SimpleNamespace(configured=True, address='different@example.test'))
    with pytest.raises(ValueError, match='same mailbox'):
        enable(mail)
    assert not state.read(replies.SETTING)


def test_server_lifecycle_starts_and_stops_reply_worker_once(monkeypatch):
    import asyncio
    from unittest.mock import Mock
    from support_email_idle import IdleLifecycle
    watcher, reads, outbox, certificates = [Mock() for _ in range(4)]
    monkeypatch.setattr('support_email_idle.MailboxWatcher', Mock(return_value=watcher))
    monkeypatch.setattr('support_email_idle.load_configuration', lambda: SimpleNamespace(configured=True))
    monkeypatch.setattr('support_email_reads.service', Mock(return_value=reads))
    monkeypatch.setattr('support_email_durable.OutboxWorker', Mock(return_value=outbox))
    monkeypatch.setattr('support_email_smtp.load_smtp_configuration', lambda: SimpleNamespace(configured=True))
    monkeypatch.setattr(replies, 'CertificateReplyWorker', Mock(return_value=certificates))
    async def app(scope, receive, send):
        await send({'type': 'lifespan.startup.complete'})
        await send({'type': 'lifespan.startup.complete'})
        await receive()
    async def receive(): return {'type': 'lifespan.shutdown'}
    async def send(message): pass
    asyncio.run(IdleLifecycle(app)({'type': 'lifespan'}, receive, send))
    for worker in [watcher, reads, outbox, certificates]:
        worker.start.assert_called_once()
        worker.close.assert_called_once()


def test_plain_human_reply_has_no_automatic_response_headers():
    from support_email_compose import new_draft, build_mime
    settings = default_settings()
    draft = new_draft(MAILBOX, mode='reply', header=header(), signature='nathan')
    msg = BytesParser(policy=email_policy.default).parsebytes(
        build_mime(draft, MAILBOX, settings['sender_name'], settings['signatures'])['bytes'])
    assert not msg['Auto-Submitted'] and not msg['X-Auto-Response-Suppress']


@pytest.mark.parametrize('action', ['current', 'toggle'])
def test_ui_activation_survives_reruns_without_stale_toggle_disabling_it(monkeypatch, action):
    from unittest.mock import MagicMock
    from streamlit.testing.v1 import AppTest
    config = {}
    calls = []
    def configure(actor, enabled, **kwargs):
        calls.append(enabled)
        config['enabled'] = enabled
    monkeypatch.setattr(state, 'read', lambda key: deepcopy(config))
    monkeypatch.setattr(replies, 'configure', configure)
    monkeypatch.setattr(replies, 'preview_latest', lambda actor:
                        dict(status='eligible', html='<p>Click the link and log in.</p>', header=header()))
    conn = MagicMock()
    conn.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = []
    monkeypatch.setattr(state.prep, 'connect', lambda: conn)
    app = AppTest.from_string("from inbox_companion_ui import certificate_controls\ncertificate_controls({'id':'fixture','role':'admin'})").run()
    if action == 'current':
        app.button(key='certificate-replies-preview').click().run()
        app.button(key='certificate-replies-current-send').click().run()
    else:
        app.toggle(key='certificate-replies-enabled').set_value(True).run()
    app.run()
    assert not app.exception and config['enabled'] is True and calls == [True]
    assert app.toggle(key='certificate-replies-enabled').value is True
    app.toggle(key='certificate-replies-enabled').set_value(False).run()
    assert config['enabled'] is False and calls == [True, False]


def test_interactive_preview_and_activation_use_foreground_capacity(mail, monkeypatch):
    lanes = []
    def provider(*args, **kwargs):
        lanes.append(kwargs['background'])
        return mail.imap
    monkeypatch.setattr('support_email_provider.ImapProvider', provider)
    assert replies.preview_latest(ACTOR)['status'] == 'eligible'
    enable(mail)
    assert lanes == [False, False]


def test_grouped_read_needs_one_remaining_background_slot_and_preserves_uid_fences():
    from support_email_provider import ImapProvider, Configuration, MailboxError
    from support_email_runtime import MailboxRuntime
    cfg = Configuration(password='synthetic-password')
    runtime = MailboxRuntime(clock=lambda: 100)
    for _ in range(5):
        with runtime.connection(cfg.scope, background=True):
            pass
    wires = []
    class Wire:
        def __init__(self): self.calls = []; self.folder = ''
        def login(self, *args): return 'OK', [b'authenticated']
        def select(self, folder, readonly=False):
            self.folder = folder; self.calls.append(('select', readonly))
            return 'OK', [b'1']
        def response(self, name): return name, [b'20' if 'Sent' in self.folder else b'10']
        def logout(self): self.calls.append(('logout',))
        def shutdown(self): self.calls.append(('shutdown',))
    def factory(*args, **kwargs):
        wire = Wire(); wires.append(wire); return wire
    adapter = ImapProvider(cfg, connection_factory=factory, runtime=runtime, background=True)
    with adapter.read_session():
        for _ in range(5):
            with adapter._connection('INBOX', '10') as (_, count, validity):
                assert count == 1 and validity == '10'
        with adapter.read_session():
            with adapter._connection('Sent', '20'):
                pass
        with pytest.raises(MailboxError, match='identifiers changed'):
            with adapter._connection('INBOX', '99'):
                pytest.fail('Changed mailbox must not be read')
        with pytest.raises(MailboxError, match='read-only'):
            with adapter._connection('INBOX', write=True):
                pytest.fail('Grouped session must not mutate mail')
    assert len(wires) == 1 and runtime.active == 0 and runtime.background_active == 0
    assert all(call[1] is True for call in wires[0].calls if call[0] == 'select')
    assert wires[0].calls.count(('logout',)) == 1
    assert adapter._read_session.get() is None
    with pytest.raises(MailboxError):
        with adapter._connection('INBOX'):
            pytest.fail('The existing six-connection background budget must still apply')


def test_group_failure_closes_socket_instead_of_retrying_the_failed_connection():
    from support_email_provider import ImapProvider, Configuration, MailboxError, _retry_read
    from unittest.mock import Mock
    wire = Mock(); wire.login.return_value = ('OK', [b'authenticated'])
    adapter = ImapProvider(Configuration(password='synthetic-password'), connection_factory=Mock(return_value=wire))
    attempts = []
    @_retry_read
    def broken(self):
        attempts.append(1)
        raise MailboxError('Synthetic interrupted read', retryable=True, code='connection')
    with pytest.raises(MailboxError):
        with adapter.read_session():
            broken(adapter)
    assert attempts == [1] and adapter._read_session.get() is None
    wire.logout.assert_called_once()
    wire.shutdown.assert_called_once()
