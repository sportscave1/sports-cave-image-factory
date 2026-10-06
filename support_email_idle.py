"""Lifecycle-owned, leased INBOX watcher. No work or connections at import.

Only the lease holder opens IMAP. Other processes relay the tiny shared signal;
neither sessions nor HTTP subscribers can start a watcher. No body/header fetch.
"""
import asyncio
import logging
import ssl
import threading
import time
import uuid

from support_email_idle_store import SignalStore
from support_email_provider import load_configuration, _ManagedSSL, _failure
from support_email_runtime import RUNTIME, Deferred

LOGGER = logging.getLogger(__name__)
RENEW_IDLE_SECONDS = 20 * 60
RENEW_LEASE_SECONDS = 15
LOCAL_LEASE_SECONDS = 35  # Close before the 60s DB expiry, allowing bounded cleanup.


def client_factory(cfg):
    from imapclient import IMAPClient
    # The library's protocol debug logging can include authentication exchanges.
    logging.getLogger('imapclient').setLevel(logging.WARNING)

    class ManagedClient(IMAPClient):
        def _create_IMAP4(self):
            return _ManagedSSL(self.host, self.port, ssl_context=self.ssl_context, timeout=cfg.timeout)

        def __init__(self):
            try:
                super().__init__(cfg.host, port=cfg.port, ssl=True,
                                 ssl_context=ssl.create_default_context(), timeout=cfg.timeout)
            except BaseException:
                if getattr(self, '_imap', None):
                    self.shutdown()
                raise
    return ManagedClient()


def idle_supported(client):
    return b'IDLE' in {c.upper() if isinstance(c, bytes) else c.upper().encode() for c in client.capabilities()}


def mailbox_status(client):
    raw = client.folder_status('INBOX', ['UIDVALIDITY', 'UIDNEXT', 'UNSEEN', 'MESSAGES'])
    result = {k.lower(): int(raw[k.encode()]) for k in ('UIDVALIDITY', 'UIDNEXT', 'UNSEEN', 'MESSAGES')}
    if result['uidvalidity'] < 1 or result['uidnext'] < 1 or min(result.values()) < 0:
        raise ValueError('Invalid mailbox status')
    return result


class SignalHub:
    def __init__(self, on_change=None):
        self.lock = threading.Lock()
        self.value = {}
        self.on_change = on_change

    def accept(self, value):
        if not value or not value.get('version'):
            return
        with self.lock:
            if self.value.get('version') == value['version']:
                return
            self.value = dict(value)
        if self.on_change:
            self.on_change(value)

    def snapshot(self):
        with self.lock:
            return dict(self.value)


def invalidate_display(value):
    from support_email_runtime import RUNTIME
    from support_email_notifications import invalidate
    cfg = load_configuration()
    if cfg.address.casefold() == value.get('mailbox') and time.time() - value.get('checked_at', 0) < 120:
        RUNTIME.invalidate(cfg.scope)
        # Seed a real STATUS snapshot; notification and browsing share it.
        RUNTIME.put(cfg.scope, ('status', 'INBOX'), {k: value[k] for k in
                    ('uidvalidity', 'uidnext', 'unseen', 'messages')}, RUNTIME.generation(cfg.scope))
        from support_email_reads import wake_index
        wake_index(cfg)
        invalidate()


HUB = SignalHub(invalidate_display)


class MailboxWatcher:
    def __init__(self, cfg, *, store=None, hub=None, factory=client_factory, clock=time.monotonic, runtime=None):
        self.cfg, self.store, self.hub = cfg, store or SignalStore(), hub or HUB
        self.factory, self.clock = factory, clock
        self.runtime = runtime or RUNTIME
        self.stop = threading.Event()
        self.owner = str(uuid.uuid4())
        self.thread = None
        self.start_lock = threading.Lock()
        self.deadline = 0
        self.renew_at = 0
        self.failures = 0
        self.stage = "lease"

    def start(self):
        with self.start_lock:
            if self.thread is not None or not self.cfg.configured:
                return
            self.thread = threading.Thread(target=self.run, name='email-idle-coordinator', daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=25)

    def lease(self, *, initial=False):
        started = self.clock()
        if not initial and started >= self.deadline:
            raise RuntimeError('Mailbox lease deadline passed')
        ok = (self.store.claim if initial else self.store.renew)(self.cfg.address, self.owner)
        if not ok:
            return False
        # Count time spent obtaining the lease too; never extend from a late response.
        self.deadline, self.renew_at = started + LOCAL_LEASE_SECONDS, started + RENEW_LEASE_SECONDS
        return self.clock() < self.deadline

    def check_lease(self):
        previous_stage, self.stage = self.stage, "lease"
        if self.clock() >= self.deadline:
            raise RuntimeError('Mailbox lease deadline passed')
        if self.clock() >= self.renew_at and not self.lease():
            raise RuntimeError('Mailbox watcher ownership lost')
        self.stage = previous_stage

    def watch(self):
        client = None
        try:
            self.check_lease()
            # Admission covers establishment only; a healthy long-lived IDLE
            # socket must not hold the foreground read slot for twenty minutes.
            with self.runtime.connection(self.cfg.scope, background=True):
                try:
                    self.stage = "connect"
                    client = self.factory(self.cfg)
                    self.check_lease()
                    self.stage = "authentication"
                    client.login(self.cfg.address, self.cfg.password)
                except Exception as error:
                    raise _failure(error, self.stage) from None
            self.check_lease()
            self.stage = "capability"
            if not idle_supported(client):
                LOGGER.info('email_idle_unsupported polling_fallback=true')
                return False
            self.stage = "select"
            client.select_folder('INBOX', readonly=True)
            self.check_lease()
            self.publish(client)  # STATUS baseline only; notification cursor is untouched.
            LOGGER.info('email_idle_connected supported=true')
            RUNTIME.watcher(self.cfg.scope, "healthy")
            healthy_since = self.clock()
            while not self.stop.is_set():
                self.check_lease()
                self.stage = "idle"
                client.idle()
                until = self.clock() + RENEW_IDLE_SECONDS
                changed = False
                while not self.stop.is_set() and self.clock() < until:
                    self.check_lease()
                    events = client.idle_check(timeout=1)
                    if self.clock() - healthy_since >= 60:
                        self.failures = 0
                    if any(b'BYE' in event for event in events):
                        raise ConnectionError('Mailbox closed IDLE')
                    if any(any(token in event for token in (b'EXISTS', b'EXPUNGE', b'FETCH', b'RECENT')) for event in events):
                        changed = True
                        break
                self.stage = "idle_done"
                client.idle_done()
                if self.stop.is_set():
                    break
                self.check_lease()
                if not changed:
                    self.stage = "noop"
                    client.noop()
                self.publish(client)  # Flag changes also change the version when counts do not.
            return True
        finally:
            RUNTIME.watcher(self.cfg.scope, "unavailable")
            if client is not None:
                # On error/lease loss close the transport directly: do not spend the
                # takeover safety margin waiting for DONE or LOGOUT on a broken socket.
                try:
                    client.shutdown()
                except Exception:
                    pass

    def publish(self, client):
        self.check_lease()
        self.stage = "status"
        status = mailbox_status(client)
        self.check_lease()
        self.stage = "signal"
        value = self.store.publish(self.cfg.address, self.owner, status, str(uuid.uuid4()))
        self.hub.accept(value)

    def run(self):
        while not self.stop.is_set():
            held = False
            wait = 15
            try:
                self.stage = "lease"
                held = self.lease(initial=True)
                if held:
                    supported = self.watch()
                    self.failures = 0
                    wait = 3600 if not supported else 15
                else:
                    # A follower relays one DB signal read/sec per process, not per tab.
                    until = self.clock() + 15
                    while not self.stop.is_set() and self.clock() < until:
                        self.hub.accept(self.store.read(self.cfg.address))
                        self.stop.wait(1)
                    wait = 0
            except Deferred:
                wait = max(5, self.runtime.recovery(self.cfg.scope)['retry_after'])
            except Exception as error:
                RUNTIME.watcher(self.cfg.scope, "reconnecting")
                self.failures = min(4, self.failures + 1)
                wait = min(120, 15 * 2 ** (self.failures - 1))
                failure = _failure(error, self.stage)
                if failure.code in {'configuration', 'authentication', 'tls'}:wait = 900
                LOGGER.warning('email_idle_reconnect stage=%s code=%s type=%s errno=%s delay=%d',
                               failure.stage, failure.code, type(error).__name__,
                               getattr(error, 'errno', None) if isinstance(getattr(error, 'errno', None), int) else None, wait)
            finally:
                if held:
                    try:
                        self.store.release(self.cfg.address, self.owner)
                    except Exception:
                        pass  # Expiring lease provides crash recovery.
            self.stop.wait(wait)


class IdleLifecycle:
    """Explicit ASGI lifecycle, independent of Streamlit imports and session reruns."""
    def __init__(self, app, factory=None):
        self.app, self.factory, self.watcher = app, factory, None
        self.inbox_reads = None
        self.outbox = None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'lifespan':
            return await self.app(scope, receive, send)

        async def lifecycle_receive():
            message = await receive()
            if message['type'] == 'lifespan.shutdown' and self.watcher:
                await asyncio.to_thread(self.watcher.close)
            if message['type'] == 'lifespan.shutdown' and self.inbox_reads:
                await asyncio.to_thread(self.inbox_reads.close)
            if message['type'] == 'lifespan.shutdown' and self.outbox:
                await asyncio.to_thread(self.outbox.close)
            return message

        async def lifecycle_send(message):
            if message['type'] == 'lifespan.startup.complete' and self.watcher is None:
                try:
                    self.watcher = self.factory() if self.factory else MailboxWatcher(load_configuration())
                    self.watcher.start()
                    if self.factory is None:
                        from support_email_reads import service
                        self.inbox_reads = service(load_configuration())
                        self.inbox_reads.start()
                        from support_email_durable import OutboxWorker
                        from support_email_smtp import load_smtp_configuration
                        self.outbox=OutboxWorker(load_configuration(),load_smtp_configuration())
                        self.outbox.start()
                except Exception as error:
                    # IDLE is optional; resource/thread initialization cannot prevent
                    # an otherwise healthy web server from serving polling/manual mail.
                    LOGGER.warning('email_idle_start_failure type=%s polling_fallback=true', type(error).__name__)
            await send(message)
        await self.app(scope, lifecycle_receive, lifecycle_send)
