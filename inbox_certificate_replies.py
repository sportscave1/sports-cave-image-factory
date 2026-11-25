"""Server-owned certificate replies using the existing private, durable mail outbox."""
from copy import deepcopy
import logging
import threading
import uuid

import inbox_companion as state
import inbox_certificate_policy as policy

SETTING = 'inbox_certificate_reply_settings'
PREFIX = 'inbox_certificate_reply:'
LOG = logging.getLogger(__name__)
_gate = threading.Lock()


def identity(mailbox, header):
    return PREFIX + state.prep.digest([mailbox.casefold(), header['message_id']])


def operation(key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'sports-cave-certificate-reply:' + key))


def require_admin(actor):
    import os_accounts
    state.prep.require_user(actor)
    if not os_accounts.is_admin(actor) or not os_accounts.can_access_page(actor, 'Email'):
        raise PermissionError('Administrator and Email access required.')


def pointer(header):
    return {k: str(header[k]) for k in ('uidvalidity', 'uid', 'message_id')}


def pending_human_reply(mailbox, header, op):
    with state.prep.connect() as c, c.cursor() as q:
        q.execute("""SELECT 1 FROM support_email_drafts WHERE mailbox=%s AND state='active'
          AND payload->'source_message'->>'message_id'=%s LIMIT 1""", (mailbox.casefold(), header['message_id']))
        if q.fetchone():
            return True
        q.execute("""SELECT 1 FROM support_email_outbox WHERE mailbox=%s AND operation_id<>%s
          AND status IN ('queued','in_progress','unknown') AND payload->'recipients' ? %s
          AND created_at>=%s::timestamptz LIMIT 1""",
                  (mailbox.casefold(), op, header['sender']['email'].casefold(), header.get('received_at') or header.get('date')))
        return bool(q.fetchone())


def inspect(imap, header, actor_id, *, orders_loader=None, settings_loader=None):
    from support_email_store import load_orders, load_email_settings
    from support_email_provider import folder_roles
    mailbox = imap.configuration.address
    result = {'status': 'ignored', 'reason': 'No matching certificate request.'}
    if not policy.safe_sender(header, mailbox):
        return result
    orders = (orders_loader or load_orders)(emails=[header['sender']['email'].casefold()])
    if not orders:
        return result
    body = imap.read_message(header, load_inline_images=False)
    if body.get('warnings'):
        return {'status': 'review', 'reason': 'Message could not be read completely.'}
    if not policy.request(header.get('subject', ''), body.get('text', ''),
                          is_reply=bool(header.get('in_reply_to') or header.get('references'))):
        return result
    if not policy.ready_customer(header, body.get('text', ''), orders):
        return {'status': 'review', 'reason': 'A ready certificate could not be verified for this customer.'}
    key = identity(mailbox, header)
    if pending_human_reply(mailbox, header, operation(key)):
        return {'status': 'review', 'reason': 'A saved draft or unresolved reply already exists.'}
    settings, _ = (settings_loader or load_email_settings)(mailbox, actor_id)
    sent = folder_roles(imap.discover_folders(counts=False)['folders'], settings.get('folder_mapping')).get('sent')
    if not sent:
        return {'status': 'review', 'reason': 'The Sent folder could not be verified.'}
    replies = imap.related_headers(sent, [header['message_id']], limit=100)
    if len(replies) >= 100:
        return {'status': 'review', 'reason': 'Conversation is too large to verify automatically.'}
    for reply in replies:
        if (reply.get('sender', {}).get('email', '').casefold() == mailbox.casefold()
                and header['message_id'] in (*reply.get('in_reply_to', ()), *reply.get('references', ()))):
            return {'status': 'answered', 'reason': 'This request already has a reply in Sent.'}
    return {'status': 'eligible', 'reason': 'Missing-certificate request matched.', 'html': policy.reply_html(header),
            'settings': settings, 'sent_folder': sent, 'header': deepcopy(header), 'key': key}


def preview_latest(actor):
    from support_email_provider import ImapProvider, load_configuration
    require_admin(actor)
    imap = ImapProvider(load_configuration(), background=True)
    current = imap.notification_snapshot(None)
    header = imap.notification_target(current['uidvalidity'], str(current['last_uid']))
    if not header:
        return {'status': 'ignored', 'reason': 'No newest Inbox message is available.'}
    return inspect(imap, header, str(actor['id']))


def configure(actor, enabled, *, existing=None):
    from support_email_provider import ImapProvider, load_configuration
    require_admin(actor)
    old = state.read(SETTING)
    config = {**old, 'enabled': bool(enabled), 'actor': str(actor['id']), 'changed_at': state.prep.now()}
    if enabled:
        from support_email_smtp import load_smtp_configuration
        smtp = load_smtp_configuration()
        if not smtp.configured:
            raise ValueError('Configure the mailbox sender before enabling automatic replies.')
        imap = ImapProvider(load_configuration(), background=True)
        if smtp.address.casefold() != imap.configuration.address.casefold():
            raise ValueError('The Inbox and sender must use the same mailbox.')
        current = imap.notification_snapshot(None)
        config.update(mailbox=imap.configuration.address.casefold(),
                      cursor=(old['cursor'] if old.get('enabled') and old.get('mailbox') == imap.configuration.address.casefold()
                              and old.get('cursor') else {k: current[k] for k in ('uidvalidity', 'last_uid')}),
                      initial_message=None)
        if existing:
            expected = pointer(existing)
            header = imap.notification_target(**expected)
            if (not header or pointer(header) != expected or str(current['uidvalidity']) != expected['uidvalidity']
                    or inspect(imap, header, str(actor['id']))['status'] != 'eligible'):
                raise ValueError('This request changed or already has a reply. Check it again before enabling.')
            config['initial_message'] = expected
    with state.prep.connect() as c, c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (SETTING,))
        q.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (SETTING,))
        row = q.fetchone()
        if (row['value'] if row else {}) != old:
            raise ValueError('Certificate reply settings changed. Refresh before continuing.')
        state.save(q, SETTING, config)


def handle(imap, header, config):
    key = identity(imap.configuration.address, header) if header.get('message_id') else ''
    previous = state.read(key) if key else {}
    if previous and (previous.get('operation_id') or config.get('initial_message') != pointer(header)):
        return
    result = inspect(imap, header, config['actor'])
    if result['status'] == 'ignored':
        return
    from support_email_compose import new_draft, build_mime
    from support_email_durable import REGISTRY
    with state.prep.connect() as c, c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s FOR SHARE', (SETTING,))
        fresh = q.fetchone()
        if not fresh or not fresh['value'].get('enabled') or fresh['value'].get('changed_at') != config['changed_at']:
            return
        previous = state.read(key, q)
        if previous and (previous.get('operation_id') or config.get('initial_message') != pointer(header)):
            return
        record = {'message_id': header['message_id'], 'sender_email': header['sender']['email'],
                  'status': result['status'], 'reason': result['reason'], 'created_at': state.prep.now()}
        if result['status'] == 'eligible':
            op = operation(key)
            draft = new_draft(imap.configuration.address, mode='reply', header=header, signature='nathan')
            draft.update(id=op, operation_id=op, html=result['html'], include_quote=False, auto_submitted='auto-replied')
            settings = result['settings']
            mime = build_mime(draft, imap.configuration.address, settings['sender_name'], settings['signatures'])
            queued = REGISTRY.store.prepare(imap.configuration.address, op, mime, actor=config['actor'],
                                            folder=result['sent_folder'], policy='append')
            record.update(operation_id=op, status=queued['status'], reason='Certificate access reply queued.')
        state.save(q, key, record)


def tick(imap):
    from support_email_store import load_assignees
    config = state.read(SETTING)
    if not config.get('enabled') or config.get('mailbox') != imap.configuration.address.casefold():
        return False
    actors = [a for a in load_assignees() if str(a['id']) == config.get('actor')]
    if len(actors) != 1:
        return False
    require_admin(actors[0])
    if not _gate.acquire(blocking=False):
        return False
    try:
        current = imap.notification_snapshot(config.get('cursor'))
        cursor = {k: current[k] for k in ('uidvalidity', 'last_uid')}
        same_mailbox = str((config.get('cursor') or {}).get('uidvalidity')) == str(current['uidvalidity'])
        initial = config.get('initial_message')
        if same_mailbox:
            if initial and initial['uidvalidity'] == str(current['uidvalidity']):
                header = imap.notification_target(**initial)
                if header and pointer(header) == initial:
                    handle(imap, header, config)
            messages = sorted(current['messages'], key=lambda h: int(h['uid']))
            for short in messages[:5]:
                header = imap.notification_target(short['uidvalidity'], short['uid'], short.get('message_id', ''))
                if header and pointer(header) == pointer(short):
                    handle(imap, header, config)
            if len(messages) > 5:
                cursor['last_uid'] = int(messages[4]['uid'])
        with state.prep.connect() as c, c.cursor() as q:
            q.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (SETTING,))
            row = q.fetchone()
            fresh = row['value'] if row else {}
            if (fresh.get('enabled') and fresh.get('changed_at') == config.get('changed_at')
                    and fresh.get('cursor') == config.get('cursor')):
                state.save(q, SETTING, {**fresh, 'cursor': cursor, 'initial_message': None,
                                      'checked_at': state.prep.now()})
        return True
    finally:
        _gate.release()


class CertificateReplyWorker:
    def __init__(self, configuration):
        self.configuration = configuration
        self.stop = threading.Event()
        self.thread = None

    def run(self):
        from support_email_provider import ImapProvider
        failures = 0
        while not self.stop.is_set():
            delay = 30
            try:
                tick(ImapProvider(self.configuration, background=True))
                failures = 0
            except Exception as error:
                failures = min(failures + 1, 4)
                delay = min(300, 15 * 2 ** failures)
                LOG.warning('certificate_reply_worker category=%s retry_seconds=%d', type(error).__name__, delay)
            self.stop.wait(delay)

    def start(self):
        if self.configuration.configured and not self.thread and not self.stop.is_set():
            self.thread = threading.Thread(target=self.run, name='certificate-replies', daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
