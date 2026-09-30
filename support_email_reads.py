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

    def request(self, key, loader, ttl=20):
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
                future = self.pool.submit(loader)
                job = (future, now + ttl)
                self.jobs[key] = job
            if not job[0].done():
                raise MailboxError('Loading mailbox…', code='pending', retry_after=1)
            return deepcopy(job[0].result())

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
        self.wake.set()

    def sync(self):
        started = self.clock()
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
            value = dict(old,snapshot=snap,synced_at=time.time())
            # Publish the useful list BEFORE optional folder discovery/database writes.
            with self.lock:
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
            try:self.store.save_index(self.config,value)
            except Exception as error:LOGGER.warning('email_snapshot_write category=DATABASE type=%s',type(error).__name__)
            with self.lock:self.value = value
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
        try:
            cached = self.store.read_index(self.config)
            with self.lock:self.value = cached
        except Exception as error:LOGGER.warning('email_snapshot_read category=DATABASE type=%s',type(error).__name__)
        while not self.stop.is_set():
            self.wake.clear()
            if self.clock() >= self.health['retry_at']:self.sync()
            delay = max(1,self.health['retry_at']-self.clock()) if self.health['retry_at'] else 60
            self.wake.wait(delay)

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
        yield

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
