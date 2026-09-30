"""Bounded asynchronous read model. Workers never access Streamlit/session state.

Existing provider owns each socket; foreground actions/sending remain unchanged.
Only this allowlist can run asynchronously, and no mail mutation is replayed.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import logging
import threading
import time

from support_email_provider import ImapProvider, MailboxError
from support_email_snapshot import SnapshotStore
from support_email_db_guard import SNAPSHOT_DB
from support_email_runtime import operation

LOGGER = logging.getLogger(__name__)
READS = {'discover_folders','list_headers','read_message','related_headers_many','live_changes'}


class ReadService:
    def __init__(self, provider, store=None, clock=time.monotonic):
        self.provider, self.config = provider, provider.configuration
        self.store = store or SnapshotStore()
        self.clock = clock
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='email-read')
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.value = {}
        self.health = {'state':'SYNCING','category':'','attempts':0,'retry_at':0}
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.epoch = 0
        self.sync_lock = threading.Lock()
        self.manual_refresh = False

    def request(self, key, loader, ttl=20, *, wait=False):
        with self.lock:
            now = self.clock()
            job = self.jobs.get(key)
            if job and job[0].done() and now > job[1]:
                self.jobs.pop(key); job = None
            if job is None:
                # Keep queued work bounded even during rapid thread switching.
                for old, entry in list(self.jobs.items()):
                    if entry[0].done() and (now > entry[1] or len(self.jobs) >= 24):
                        self.jobs.pop(old)
                if len(self.jobs) >= 24:
                    raise MailboxError('Loading selected message…', code='pending', retry_after=1)
                def timed():
                    started = self.clock()
                    try:return loader()
                    finally:LOGGER.info('email_read stage=%s duration_ms=%.1f',key[0],(self.clock()-started)*1000)
                future = self.pool.submit(timed)
                job = (future, now + ttl)
                self.jobs[key] = job
            if not job[0].done() and not wait:
                raise MailboxError('Loading mailbox…', code='pending', retry_after=1)
        try:return deepcopy(job[0].result(timeout=25 if wait else 0))
        except TimeoutError:
            raise MailboxError('Message loading timed out.',code='timeout',retryable=True) from None

    def start(self):
        with self.lock:
            if self.thread or not self.config.configured:return
            self.thread = threading.Thread(target=self.run, name='email-inbox-index', daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set(); self.wake.set()
        if self.thread:self.thread.join(timeout=2)
        self.pool.shutdown(wait=False, cancel_futures=True)

    def refresh(self):
        with self.lock:
            self.epoch += 1
            # Do not cancel or duplicate an active read/connection.
            self.jobs = OrderedDict((k,v) for k,v in self.jobs.items() if not v[0].done())
            self.health['retry_at'] = 0
            self.health['state'] = 'SYNCING'
            self.manual_refresh = True
        self.wake.set()

    def sync(self):
        # One index owner, including manual refresh and tests/admin callers.
        if not self.sync_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                forced, self.manual_refresh = self.manual_refresh, False
            with operation(background=True, force=forced):
                self._sync()
        finally:
            self.sync_lock.release()

    def _sync(self):
        started = self.clock()
        observed_at = time.time()  # Fence by read start, never late completion.
        with self.lock: epoch = self.epoch
        try:
            with self.lock:old = deepcopy(self.value)
            if old.get('snapshot'):
                # Existing IMAP UID/UIDVALIDITY + loaded flag delta, never full history.
                snap = old['snapshot']
                delta = self.provider.live_changes('INBOX', snap, limit=50)
                rows = [] if delta['reset'] else [dict(m, flags=delta['flags'][m['uid']],
                    unread='\\Seen' not in delta['flags'][m['uid']]) for m in snap['messages'] if m['uid'] in delta['flags']]
                unique = {m['uid']:m for m in [*rows,*delta['added']]}
                rows = sorted(unique.values(),key=lambda m:int(m['uid']))[-50:]
                snap = dict(snap, messages=rows,uidvalidity=delta['uidvalidity'],live_uid=delta['live_uid'],
                    total=delta['total'],matched=delta['total'],has_more=delta['total']>len(rows),
                    refreshed_at=datetime.fromtimestamp(delta['checked_at'],timezone.utc))
            else:
                snap = self.provider.list_headers(50,'INBOX',previews=False)
            value = dict(old,snapshot=snap,synced_at=time.time(),observed_at=observed_at)
            # Publish the useful list BEFORE optional folder discovery/database writes.
            with self.lock:
                if epoch != self.epoch or self.stop.is_set():return
                self.value = value
                self.health.update(state='CONNECTED',category='',attempts=0,retry_at=0,
                    last_success_at=value['synced_at'],duration_ms=round((self.clock()-started)*1000,1),
                    conversations_processed=len(snap['messages']))
            if not old.get('folders') or time.time()-old.get('folders_at',0)>300:
                try:
                    value['folders'] = self.provider.discover_folders(counts=False)
                    value['folders_at'] = time.time()
                except Exception:
                    pass  # Folder discovery cannot discard a valid Inbox snapshot.
            if SNAPSHOT_DB.ready():
                try:self.store.save_index(self.config,value)
                except Exception as error:SNAPSHOT_DB.failed(error,'snapshot_write')
            with self.lock:
                if epoch == self.epoch:self.value = value
            LOGGER.info('email_index_sync duration_ms=%.1f headers=%d', (self.clock()-started)*1000,len(snap['messages']))
        except Exception as error:
            code = getattr(error,'code','unknown')
            with self.lock:
                if code in {'busy','pending'}:
                    self.health['retry_at'] = self.clock()+5
                    return
                failures = min(7,self.health['attempts']+1)
                delay = 900 if code in {'authentication','configuration','tls'} else min(300,15*2**(failures-1))
                self.health.update(state='RECONNECTING',category=code,attempts=failures,retry_at=self.clock()+delay)
            LOGGER.warning('email_index_sync category=%s retry_seconds=%d duration_ms=%.1f',code,delay,(self.clock()-started)*1000)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            if not self.value.get('snapshot'):self.restore()
            if self.clock() >= self.health['retry_at']:self.sync()
            if self.stop.is_set():break
            delay = max(1,self.health['retry_at']-self.clock()) if self.health['retry_at'] else 60
            self.wake.wait(delay)

    def restore(self):
        if not SNAPSHOT_DB.ready():return
        try:
            cached = self.store.read_index(self.config)
            with self.lock:
                if not self.value.get('snapshot') and cached.get('snapshot'):
                    self.value = cached
                    self.health['last_success_at'] = cached.get('synced_at')
        except Exception as error:SNAPSHOT_DB.failed(error,'snapshot_read')

    def index(self):
        self.start()
        with self.lock:
            if self.value.get('snapshot'):return deepcopy(self.value['snapshot'])
            if self.health['category']:
                code = self.health['category']
                raise MailboxError('Reconnecting mailbox…', code=code, retry_after=max(1,self.health['retry_at']-self.clock()))
        raise MailboxError('Loading conversations…',code='pending',retry_after=1)


_SERVICES = {}
_LOCK = threading.Lock()


def wake_index(config):
    """A validated IDLE signal wakes the existing owner without bypassing backoff."""
    with _LOCK:
        reads = _SERVICES.get(config.scope)
        if reads:reads.wake.set()


def service(config):
    with _LOCK:
        if config.scope not in _SERVICES:
            for key, old in list(_SERVICES.items()):
                old.close();_SERVICES.pop(key)  # Credential rotation cannot retain old mail.
            _SERVICES[config.scope] = ReadService(ImapProvider(config))
        return _SERVICES[config.scope]


class AsyncInbox:
    """Read-only facade; actual SMTP/mutations still use existing provider methods."""
    def __init__(self,config,reads=None):
        self.reads = reads or service(config)
        self.provider = self.reads.provider

    @contextmanager
    def interactive_refresh(self):
        self.reads.refresh()
        with self.provider.interactive_refresh():yield

    def read_body_for_action(self, message):
        # Compose/download keep their existing bounded synchronous semantics and
        # reuse an in-flight read instead of opening a second socket.
        key = ('read_message',repr((message,)),repr([]))
        return self.reads.request(key,lambda:self.provider.read_message(deepcopy(message)),wait=True)

    def __getattr__(self,name):
        method = getattr(self.provider,name)
        if name not in READS:return method
        def read(*args,**kwargs):
            if name == 'discover_folders':
                self.reads.start()
                with self.reads.lock:folders = deepcopy(self.reads.value.get('folders'))
                if folders:return folders
                # IMAP's reserved Inbox name is authoritative; other folders arrive lazily.
                return {'folders':[{'name':'INBOX','label':'Inbox','role':'inbox','flags':()}], 'capabilities':[]}
            if name == 'list_headers' and (len(args)<2 or args[1]=='INBOX') and (not args or args[0]==50) and not kwargs.get('query'):
                return self.reads.index()
            key = (name,repr(args),repr(sorted(kwargs.items())))
            return self.reads.request(key,lambda:method(*deepcopy(args),**deepcopy(kwargs)))
        return read
