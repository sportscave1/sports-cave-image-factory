"""Small transactional chat outbox, delivered through the existing Resend account.

Only event types and a private-chat link enter the email. One reusable record per
participant/conversation and an indexed due pointer keep storage and idle work low.
"""
import asyncio
from copy import deepcopy
from email.utils import formataddr
from html import escape
import logging
import os
import threading
import time
from uuid import uuid4

from marketplace import BASE_PATH, PUBLIC_ORIGIN, email, identifier
from marketplace_accounts import digest
from marketplace_mail import smtp_plan
from marketplace_store import MarketplaceStore, PREFIX, lock, put, read
from email_service import (EmailConfiguration, EmailMessage, EmailDeliveryError,
                           EmailConfigurationError, ResendEmailProvider)

LOG = logging.getLogger(__name__)
GRACE = 12
COOLDOWN = 15 * 60
HOURLY_LIMIT = 6
LEASE = 90
RETRY_AGE = 23 * 60 * 60  # Resend retains idempotency keys for 24 hours.
RETRY_DELAYS = (30, 120, 300, 900, 1800)
EVENTS = {'text': ('New message', 'You have a new message.'),
          'offer': ('New offer', 'You have a new offer.'),
          'invoice': ('New PayPal invoice', 'Your seller shared a PayPal invoice.'),
          'offer_response': ('Offer update', 'Your seller responded to your offer.')}
_WORKER = None
_WORKER_LOCK = threading.Lock()


def channel(thread_id, role):
    if role not in ('buyer', 'seller'):
        raise ValueError('Invalid notification recipient.')
    return 'notice:' + identifier(thread_id) + ':' + role


def _delete(conn, key):
    conn.execute('DELETE FROM crm_runtime_state WHERE key=%s', (PREFIX + key,))


def _schedule(conn, row, due=None):
    if row.get('due_key'):
        _delete(conn, row['due_key'])
    row.pop('due_key', None)
    row.pop('due_at', None)
    if due is not None:
        key = f'notice-due:{int(due * 1000):013d}:{row["thread_id"]}:{row["role"]}'
        row['due_key'] = key
        row['due_at'] = due
        put(conn, key, {'thread_id': row['thread_id'], 'role': row['role'], 'due_key': key})
    put(conn, channel(row['thread_id'], row['role']), row)


def _unread(row):
    return row.get('pending_seq', 0) > max(row.get('read_seq', 0), row.get('settled_seq', 0))


def enqueue(conn, thread, message, at=None):
    """Called within the message transaction. Never contacts an email provider."""
    at = time.time() if at is None else at
    role = 'seller' if message['sender'] == 'buyer' else 'buyer'
    key = channel(thread['id'], role)
    lock(conn, key)
    row = read(conn, key, {'thread_id': thread['id'], 'role': role})
    kinds = set(row.get('kinds', [])) if _unread(row) else set()
    kinds.add(message['kind'])
    row.update(pending_seq=message['seq'], kinds=sorted(kinds), latest_at=at)
    if row.get('attempt'):
        put(conn, key, row)  # Keep the immutable in-flight attempt and its lease.
    else:
        _schedule(conn, row, max(min(at + GRACE, row.get('due_at', at + GRACE)), row.get('cooldown_until', 0)))


def acknowledge(conn, thread, uid, seen, at=None):
    """A customer page/poll received these messages. OS support reads do not count."""
    at = time.time() if at is None else at
    role = 'buyer' if thread['buyer_id'] == uid else 'seller'
    key = channel(thread['id'], role)
    lock(conn, key)
    row = read(conn, key, {'thread_id': thread['id'], 'role': role})
    seen = min(seen, thread['seq'])
    if row.get('read_seq', -1) >= seen:
        return  # Visible polling with no new messages produces no extra writes.
    row['read_seq'] = max(row.get('read_seq', 0), seen)
    if _unread(row) or row.get('attempt'):
        put(conn, key, row)
    else:
        row['kinds'] = []
        _schedule(conn, row)


def email_message(thread_id, kinds):
    """Constant copy only: no names, message text, amounts or payment URLs."""
    kinds = set(kinds) & set(EVENTS)
    heading, intro = EVENTS[next(iter(kinds))] if len(kinds) == 1 else (
        'New chat activity', 'You have new activity in your conversation.')
    link = PUBLIC_ORIGIN + BASE_PATH + '/inbox/' + identifier(thread_id)
    settings = PUBLIC_ORIGIN + BASE_PATH + '/account'
    text = f'{intro}\n\nView conversation: {link}\n\nPlease reply in your chat.\nEmail preferences: {settings}\nSports Cave Marketplace'
    html = f'''<div style="background:#f5f3ed;padding:24px 16px;font-family:Arial,Helvetica,sans-serif;color:#1b1c19"><div style="max-width:480px;margin:auto;background:#fff;border-top:3px solid #b18a42;padding:28px"><p style="font-size:11px;font-weight:bold;letter-spacing:2px">SPORTS CAVE MARKETPLACE</p><h1 style="font-size:25px;letter-spacing:-.7px">{escape(heading)}</h1><p style="font-size:15px;line-height:1.6">{escape(intro)}</p><p style="margin:25px 0"><a href="{link}" style="display:inline-block;background:#1b1c19;color:#fff;padding:14px 22px;text-decoration:none;font-weight:bold;font-size:14px">View conversation</a></p><p style="font-size:12px;color:#68655c">Please reply in your chat.</p><p style="border-top:1px solid #e6e2d8;padding-top:17px;font-size:11px"><a href="{settings}" style="color:#68655c">Email preferences</a></p></div></div>'''
    return EmailMessage(heading + ' | Sports Cave Marketplace', html, text)


class NotificationStore(MarketplaceStore):
    def __init__(self, connect=None, *, clock=time.time):
        super().__init__(connect)
        self.clock = clock

    def due(self, limit=10):
        upper = PREFIX + f'notice-due:{int(self.clock() * 1000):013d}:z'
        with self.db() as conn:
            return [r['value'] for r in conn.execute('''SELECT value FROM crm_runtime_state
                WHERE key > %s AND key < %s AND key LIKE %s ORDER BY key LIMIT %s''',
                (PREFIX + 'notice-due:', upper, PREFIX + 'notice-due:%', min(10, max(1, limit)))).fetchall()]

    @staticmethod
    def _recipient(conn, thread, role):
        if thread.get('blocked_by'):
            return None
        profiles = {}
        for participant in ('buyer', 'seller'):
            uid = thread.get(participant + '_id')
            if uid:
                profile = read(conn, 'account:' + identifier(uid))
                if not profile or profile['status'] != 'active':
                    return None
                profiles[participant] = profile
        profile = profiles.get(role)
        if profile:
            return email(profile['email']) if profile.get('email_notifications', True) else None
        # Published guest sellers supplied this contact address for their listing.
        # The email includes no conversation content; viewing it still requires
        # signup and verified ownership of that original submission email.
        if role != 'seller':
            return None
        listing = read(conn, 'listing:' + thread['listing_id'])
        if not listing or listing['status'] != 'published':
            return None
        address = email(listing['seller_email'])
        if digest(address) != thread['seller_email_hash']:
            return None
        owner = read(conn, 'account-email:' + digest(address))
        if owner:
            profile = read(conn, 'account:' + owner['id'])
            if (not profile or profile['status'] != 'active' or profile['email'] != address
                    or not profile.get('email_notifications', True)):
                return None
        return address

    def claim(self, candidate, sender):
        at = self.clock()
        tid, role = identifier(candidate['thread_id']), candidate['role']
        key = channel(tid, role)
        with self.db() as conn:
            lock(conn, 'thread:' + tid)
            lock(conn, key)
            row, thread = read(conn, key), read(conn, 'thread:' + tid)
            if not row or row.get('due_key') != candidate['due_key']:
                return None
            attempt = row.get('attempt')
            address = self._recipient(conn, thread, role) if thread else None
            if not address or not _unread(row) or row.get('latest_at', 0) < at - 86400:
                row.update(settled_seq=row.get('pending_seq', 0), kinds=[])
                row.pop('attempt', None)
                _schedule(conn, row)
                return None
            if attempt and (attempt['recipient'] != address or at - attempt['started_at'] >= RETRY_AGE):
                # An address change must not reroute an old private notification;
                # an expired provider idempotency window must never resend it.
                row.update(settled_seq=attempt['seq'], last_outcome='uncertain', cooldown_until=at + COOLDOWN)
                row.pop('attempt', None)
                _schedule(conn, row, at + COOLDOWN if _unread(row) else None)
                return None
            if attempt and attempt['seq'] <= row.get('read_seq', 0):
                row.update(settled_seq=attempt['seq'])
                row.pop('attempt', None)
                _schedule(conn, row, max(at + GRACE, row.get('cooldown_until', 0)) if _unread(row) else None)
                return None
            if not attempt:
                budget_key = 'notice-budget:' + digest(address)
                lock(conn, budget_key)
                window = int(at // 3600)
                budget = read(conn, budget_key, {})
                count = budget.get('count', 0) if budget.get('window') == window else 0
                if count >= HOURLY_LIMIT:
                    _schedule(conn, row, (window + 1) * 3600 + GRACE)
                    return None
                put(conn, budget_key, {'window': window, 'count': count + 1})
                message = email_message(tid, row['kinds'])
                # Freeze the small email payload, never the private chat body.
                # Retries must send byte-for-byte identical fields under one key.
                attempt = {'id': str(uuid4()), 'seq': row['pending_seq'], 'started_at': at, 'tries': 0,
                    'recipient': address, 'sender': sender, 'subject': message.subject,
                    'html': message.html, 'text': message.text}
                row.update(attempt=attempt, kinds=[], cooldown_until=at + COOLDOWN)
            attempt['tries'] += 1
            attempt['token'] = str(uuid4())
            row['last_outcome'] = 'sending'
            _schedule(conn, row, at + LEASE)
            return {'thread_id': tid, 'role': role, 'attempt': deepcopy(attempt)}

    def complete(self, job, *, receipt=None, error=None):
        at = self.clock()
        key = channel(job['thread_id'], job['role'])
        with self.db() as conn:
            lock(conn, key)
            row = read(conn, key)
            attempt = (row or {}).get('attempt', {})
            if attempt.get('token') != job['attempt']['token']:
                return False
            code = getattr(error, 'status_code', None)
            ambiguous = error is not None and (code is None or 200 <= code < 300)
            retry = error is not None and (ambiguous or getattr(error, 'retryable', False))
            if retry and attempt['tries'] <= len(RETRY_DELAYS) and at - attempt['started_at'] < RETRY_AGE:
                row['last_outcome'] = 'retry'
                attempt.pop('token', None)
                _schedule(conn, row, at + RETRY_DELAYS[attempt['tries'] - 1])
                return True
            row['settled_seq'] = max(row.get('settled_seq', 0), attempt['seq'])
            row['last_outcome'] = 'accepted' if error is None else 'uncertain' if ambiguous else 'failed'
            if error is None:
                row.update(last_accepted_at=at, provider_id=str(receipt or '')[:250],
                           cooldown_until=max(row.get('cooldown_until', 0), at + COOLDOWN))
            row.pop('attempt', None)
            _schedule(conn, row, max(at + GRACE, row.get('cooldown_until', 0)) if _unread(row) else None)
            return True


class _NoRedirectSession:
    def post(self, *args, **kwargs):
        import requests
        return requests.post(*args, **kwargs, allow_redirects=False)


def deliver(job, environ=None, *, provider_factory=ResendEmailProvider):
    env = os.environ if environ is None else environ
    plan = smtp_plan(env)
    attempt = job['attempt']
    if not plan['configured'] or formataddr((plan['sender_name'], plan['sender_email'])) != attempt['sender']:
        raise EmailConfigurationError('The existing Resend sender is not available for this alert.')
    config = EmailConfiguration(api_key=env[plan['key_variable']], sender=attempt['sender'],
                                recipient=attempt['recipient'], reply_to=plan['sender_email'])
    provider = provider_factory(config, session=_NoRedirectSession(), timeout_seconds=8, max_attempts=1)
    message = EmailMessage(attempt['subject'], attempt['html'], attempt['text'])
    return provider.send(message, idempotency_key='marketplace-alert/' + attempt['id']).provider_message_id


class NotificationWorker:
    def __init__(self, store=None, *, environ=None, delivery=deliver):
        self.store = store or NotificationStore()
        self.env = os.environ if environ is None else environ
        self.delivery = delivery
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def run_once(self):
        plan = smtp_plan(self.env)
        if not plan['configured']:
            return 0
        sender = formataddr((plan['sender_name'], plan['sender_email']))
        count = 0
        for candidate in self.store.due():
            if self.stop.is_set():
                break
            job = self.store.claim(candidate, sender)
            if not job:
                continue
            try:
                receipt = self.delivery(job, self.env)
            except Exception as exc:
                # Transport exceptions and provider bodies must not leak customer
                # addresses, invoice details, message text or credentials to logs.
                LOG.warning('marketplace_notification_attempt_failed type=%s', type(exc).__name__)
                self.store.complete(job, error=exc)
            else:
                self.store.complete(job, receipt=receipt)
            count += 1
            if self.stop.wait(.6):
                break
        return count

    def start(self):
        def loop():
            while not self.stop.is_set():
                try:
                    self.run_once()
                except Exception as exc:
                    LOG.warning('marketplace_notification_queue_unavailable type=%s', type(exc).__name__)
                self.wake.wait(15)
                self.wake.clear()
        self.thread = threading.Thread(target=loop, name='marketplace-email-alerts', daemon=True)
        self.thread.start()
        LOG.info('marketplace_notifications_started provider=resend')
        return self

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)


def enabled(environ=None):
    env = os.environ if environ is None else environ
    return str(env.get('RENDER', '')).lower() in ('true', '1') and env.get('MARKETPLACE_NOTIFICATIONS_ENABLED', 'true').lower() == 'true'


def start_worker():
    global _WORKER
    if not enabled() or not smtp_plan()['configured']:
        return None
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.thread or not _WORKER.thread.is_alive():
            _WORKER = NotificationWorker().start()
        return _WORKER


def wake_dispatcher():
    if _WORKER:
        _WORKER.wake.set()


def status():
    return {'enabled': enabled(), 'configured': smtp_plan()['configured'],
            'running': bool(_WORKER and _WORKER.thread and _WORKER.thread.is_alive())}


class NotificationLifecycle:
    """Starts only on the real server's ASGI lifespan, never on module import."""
    def __init__(self, app, factory=start_worker):
        self.app, self.factory, self.worker = app, factory, None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'lifespan':
            return await self.app(scope, receive, send)
        async def lifecycle_receive():
            message = await receive()
            if message['type'] == 'lifespan.shutdown' and self.worker:
                await asyncio.to_thread(self.worker.close)
            return message
        async def lifecycle_send(message):
            if message['type'] == 'lifespan.startup.complete' and self.worker is None:
                try:
                    self.worker = self.factory()
                except Exception as exc:
                    LOG.warning('marketplace_notifications_start_failed type=%s', type(exc).__name__)
            await send(message)
        await self.app(scope, lifecycle_receive, lifecycle_send)
