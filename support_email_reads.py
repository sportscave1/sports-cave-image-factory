"""Bounded asynchronous read model. Workers never access Streamlit/session state.

Existing provider owns each socket; foreground actions/sending remain unchanged.
Only this allowlist can run asynchronously, and no mail mutation is replayed.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import logging
import threading
import time
import random
import uuid

from support_email_provider import ImapProvider, MailboxError
from support_email_snapshot import SnapshotStore
from support_email_db_guard import SNAPSHOT_DB
from support_email_runtime import operation

LOGGER = logging.getLogger(__name__)
READS = {'discover_folders','list_headers','read_message','related_headers_many','live_changes','search_folders'}
MUTATIONS = {'set_flag', 'move_message', 'copy_message', 'mark_folder_read', 'delete_trash_messages'}


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
        self.coordination_delay = 0
        self.mutation_lock = threading.Lock()

    def request(self, key, loader, ttl=20, *, wait=False):
        with self.lock:
            now = self.clock()
            if key[0] == 'read_message':
                # Optional history that has not started must yield to an explicit
                # selected body. Never interrupt an active socket or a mutation.
                for old, entry in list(self.jobs.items()):
                    if old[0] == 'related_headers_many' and entry[0].cancel():
                        self.jobs.pop(old, None)
            job = self.jobs.get(key)
            if job and job[0].done() and (now > job[1] or job[0].exception() is not None):
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
            if self.stop.is_set() or (self.thread and self.thread.is_alive()) or not self.config.configured:return
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

    def mutate(self, name, *args, **kwargs):
        """Fence in-flight reads and publish confirmed provider writes to all sessions.

        Never replay a write. Rejected/ambiguous writes invalidate reads but are not
        projected as successful. Exact folder/UIDVALIDITY/UID identities only.
        """
        with self.mutation_lock:
            guard = self.store.mutation_guard(self.config) if isinstance(self.store, SnapshotStore) else nullcontext({'valid':True})
            with guard as lease:
                with self.lock:
                    self.epoch += 1
                    self.jobs.clear()
                try:
                    result = getattr(self.provider, name)(*deepcopy(args), **deepcopy(kwargs))
                except Exception:
                    self.wake.set()
                    raise
                if not lease['valid']:
                    with self.lock:
                        self.epoch += 1;self.jobs.clear()
                        self.value['force_full'] = True
                        self.health['mutation_warning'] = True
                    self.wake.set()
                    return result
                def project(value):
                    snapshot = value.get('snapshot')
                    if not snapshot:return value
                    rows = snapshot['messages']
                    unread_before = sum(bool(m['unread']) for m in rows)
                    def same(row, message):
                        return all(str(row.get(k, '')) == str(message.get(k, ''))
                                   for k in ('folder','uidvalidity','uid','message_id'))
                    if name == 'set_flag':
                        message, flag, enabled = args
                        for row in rows:
                            if same(row, message):
                                flags = set(row['flags'])
                                flags.add(flag) if enabled else flags.discard(flag)
                                row.update(flags=tuple(sorted(flags)), unread='\\Seen' not in flags)
                    elif name == 'mark_folder_read':
                        for row in rows:
                            if (row['folder'] == args[0] and str(row['uidvalidity']) == str(result['uidvalidity'])
                                    and row['uid'] in result['uids']):
                                row.update(flags=tuple(sorted({*row['flags'], '\\Seen'})), unread=False)
                    elif name == 'move_message' and result.get('status') == 'moved':
                        snapshot['messages'] = [m for m in rows if not same(m, args[0])]
                    elif name == 'delete_trash_messages' and result.get('status') == 'deleted':
                        snapshot['messages'] = [m for m in rows if not any(same(m, target) for target in args[0])]
                    removed = len(rows) - len(snapshot['messages'])
                    for count in ('total','matched'):
                        snapshot[count] = max(0, snapshot.get(count, 0) - removed)
                    unread_delta = sum(bool(m['unread']) for m in snapshot['messages']) - unread_before
                    for folder in (value.get('folders') or {}).get('folders', []):
                        if folder['name'] == 'INBOX' and isinstance(folder.get('unread'), int):
                            folder['unread'] = max(0, folder['unread'] + unread_delta)
                    value.update(observed_at=time.time(), mutation_revision=str(uuid.uuid4()))
                    if name in {'move_message', 'copy_message'} and len(args) > 1 and args[1] == 'INBOX':
                        value['force_full'] = True  # Destination UIDs belong to the provider, never guessed.
                    return value
                with self.lock:
                    self.epoch += 1
                    confirmed_epoch = self.epoch
                    self.jobs.clear()
                    value = project(deepcopy(self.value))
                    if value:self.value = value
                if value and value.get('snapshot'):
                    try:
                        if isinstance(self.store, SnapshotStore):
                            published = self.store.save_confirmed(self.config, project, value)
                            with self.lock:
                                if self.epoch == confirmed_epoch:self.value = published
                        else:
                            self.store.save_index(self.config, value)
                        with self.lock:self.health.pop('mutation_warning', None)
                    except Exception as error:
                        SNAPSHOT_DB.failed(error, 'mutation_snapshot_write')
                        with self.lock:self.health.update(database_verified=False, mutation_warning=True)
                self.wake.set()
                return result

    def sync(self):
        # One index owner, including manual refresh and tests/admin callers.
        if not self.sync_lock.acquire(blocking=False):
            return
        try:
            owner=str(uuid.uuid4());leased=False
            if isinstance(self.store,SnapshotStore) and SNAPSHOT_DB.ready():
                try:
                    leased=self.store.claim('inbox-index:'+self.config.address,owner)
                    if not leased:
                        # A rolling replacement may narrowly lose to the draining
                        # owner's last sync. Do not then sleep a full poll cycle.
                        # Persistent followers back off to the normal cadence.
                        self.coordination_delay = min(60, max(5, self.coordination_delay * 2))
                        LOGGER.info('email_index_lease_busy retry_seconds=%d', self.coordination_delay)
                        self.restore()
                        return
                except Exception as error:
                    SNAPSHOT_DB.failed(error,'snapshot_lease')
            with self.lock:
                forced, self.manual_refresh = self.manual_refresh, False
                self.coordination_delay = 0
            with operation(background=True, force=forced):
                self._sync()
        finally:
            if locals().get('leased'):
                try:self.store.release('inbox-index:'+self.config.address,owner)
                except Exception as error:SNAPSHOT_DB.failed(error,'snapshot_release')
            self.sync_lock.release()

    def health_snapshot(self):
        with self.lock:health=dict(self.health)
        last=health.get('last_success_at')
        if health['state']=='CONNECTED' and (not last or time.time()-last>180):
            health.update(state='RECONNECTING',category='stale')
        health['retry_after']=max(0,round(health.get('retry_at',0)-self.clock(),1))
        stage,category=health.get('failure_stage',''),health.get('category','')
        health['diagnosis']=('Mailbox connection fails before authentication; check provider/network access.' if stage in {'dns','tcp'} else
            'Mailbox authentication requires the owner to verify credentials.' if category=='authentication' else
            'Secure mailbox connection failed; TLS verification needs attention.' if category=='tls' else
            'Waiting for the next bounded mailbox sync.' if health['state']!='CONNECTED' else '')
        health['database_healthy']=SNAPSHOT_DB.ready() and health.get('database_verified',False)
        health['authentication_valid']=bool(last and health['state']=='CONNECTED' and not category and time.time()-last<180)
        health['worker_running']=bool(self.thread and self.thread.is_alive())
        return health

    def _sync(self):
        started = self.clock()
        run_id=str(uuid.uuid4())
        observed_at = time.time()  # Fence by read start, never late completion.
        with self.lock:self.health['last_attempt_at']=observed_at
        with self.lock: epoch = self.epoch
        try:
            with self.lock:old = deepcopy(self.value)
            if old.get('snapshot') and not old.get('force_full'):
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
            # Same provider identity repeated in a response is still one message;
            # different UIDs remain distinct even with identical sender/subject.
            raw=snap['messages']
            unique={(m['folder'],str(m['uidvalidity']),str(m['uid'])):m for m in raw}
            snap=dict(snap,messages=list(unique.values()))
            value = dict(old,snapshot=snap,synced_at=time.time(),observed_at=observed_at)
            value.pop('force_full', None)
            # Publish the useful list BEFORE optional folder discovery/database writes.
            with self.lock:
                if epoch != self.epoch or self.stop.is_set():return
                self.value = value
                self.health.update(state='CONNECTED',category='',attempts=0,retry_at=0,
                    last_success_at=value['synced_at'],failure_stage='',last_failure_at=None,duration_ms=round((self.clock()-started)*1000,1),
                    conversations_processed=len(snap['messages']))
                self.health.update(sync_run_id=run_id,messages_examined=len(raw),
                    duplicates_skipped=len(raw)-len(unique))
            if not old.get('folders') or time.time()-old.get('folders_at',0)>300:
                try:
                    value['folders'] = self.provider.discover_folders(counts=False)
                    value['folders_at'] = time.time()
                except Exception:
                    pass  # Folder discovery cannot discard a valid Inbox snapshot.
            if SNAPSHOT_DB.ready():
                try:
                    self.store.save_index(self.config,value)
                    with self.lock:self.health['database_verified']=True
                except Exception as error:SNAPSHOT_DB.failed(error,'snapshot_write')
            with self.lock:
                if epoch == self.epoch:self.value = value
            LOGGER.info('email_index_sync sync_run_id=%s duration_ms=%.1f headers=%d', run_id,(self.clock()-started)*1000,len(snap['messages']))
        except Exception as error:
            code = getattr(error,'code','unknown')
            with self.lock:
                if code in {'busy','pending','deferred'}:
                    self.health['retry_at'] = self.clock()+max(5,float(getattr(error,'retry_after',0) or 0))
                    return
                failures = min(7,self.health['attempts']+1)
                delay = 900 if code in {'authentication','configuration','tls'} else min(300,15*2**(failures-1))
                delay=max(float(getattr(error,'retry_after',0) or 0),delay+random.uniform(0,min(5,delay*.1)))
                self.health.update(state='RECONNECTING',category=code,failure_stage=getattr(error,'stage','operation'),
                    last_failure_at=time.time(),attempts=failures,retry_at=self.clock()+delay)
            LOGGER.warning('email_index_sync sync_run_id=%s category=%s stage=%s retry_seconds=%d duration_ms=%.1f',run_id,code,getattr(error,'stage','operation'),delay,(self.clock()-started)*1000)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            if not self.value.get('snapshot'):self.restore()
            if self.clock() >= self.health['retry_at']:self.sync()
            if self.stop.is_set():break
            # Coordination contention cannot shorten a provider/auth backoff.
            delay = max(1,self.health['retry_at']-self.clock()) if self.health['retry_at'] else (self.coordination_delay or 60)
            self.wake.wait(delay)

    def restore(self):
        if not SNAPSHOT_DB.ready():return
        try:
            cached = self.store.read_index(self.config)
            with self.lock:
                self.health['database_verified']=True
                different_revision = cached.get('mutation_revision') != self.value.get('mutation_revision')
                # A local confirmed write may not yet be durable. Clock skew in
                # the older shared snapshot must not undo it during that outage.
                blocked_revision = different_revision and self.health.get('mutation_warning')
                if cached.get('snapshot') and not blocked_revision and (different_revision or cached.get('observed_at',0)>self.value.get('observed_at',-1)):
                    if cached.get('mutation_revision') != self.value.get('mutation_revision'):
                        self.epoch += 1
                        self.jobs.clear()
                    self.value = cached
                    self.health['last_success_at'] = cached.get('synced_at')
                    # A recent confirmed sync from the lease owner is healthy; a
                    # restored old snapshot is usable but cannot claim Connected.
                    if (time.time()-float(cached.get('synced_at') or 0)<180
                            and float(cached.get('synced_at') or 0)>=float(self.health.get('last_failure_at') or 0)):
                        self.health.update(state='CONNECTED',category='',failure_stage='',last_failure_at=None,attempts=0,retry_at=0)
        except Exception as error:SNAPSHOT_DB.failed(error,'snapshot_read')

    def index(self, *, check_shared=True):
        self.start()
        if check_shared and isinstance(self.store, SnapshotStore):
            self.restore()  # Observe confirmed writes from another OS worker/session.
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
    """Async reads and confirmed-write fences; the provider still owns all IMAP I/O."""
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
        key = self.body_key(message)
        return self.reads.request(key,lambda:self.provider.read_message(deepcopy(message)),wait=True)

    def body_key(self, message):
        # Mutable flags/snippets must not fork a read of the same immutable MIME.
        return ('read_message', tuple(str(message.get(k, '')) for k in
                ('folder', 'uidvalidity', 'uid', 'message_id')), self.reads.epoch)

    def read_revision(self):
        if isinstance(self.reads.store, SnapshotStore):self.reads.restore()
        self._revision_checked = True
        with self.reads.lock:return self.reads.value.get('mutation_revision', '')

    def __getattr__(self,name):
        method = getattr(self.provider,name)
        if name in MUTATIONS:
            return lambda *args, **kwargs: self.reads.mutate(name, *args, **kwargs)
        if name not in READS:return method
        def read(*args,**kwargs):
            if name == 'discover_folders':
                self.reads.start()
                with self.reads.lock:folders = deepcopy(self.reads.value.get('folders'))
                if folders:return folders
                # IMAP's reserved Inbox name is authoritative; other folders arrive lazily.
                return {'folders':[{'name':'INBOX','label':'Inbox','role':'inbox','flags':()}], 'capabilities':[]}
            if name == 'list_headers' and (len(args)<2 or args[1]=='INBOX') and (not args or args[0]==50) and not kwargs.get('query') and not kwargs.get('before_uid') and not kwargs.get('filters'):
                checked = getattr(self, '_revision_checked', False)
                self._revision_checked = False
                return self.reads.index(check_shared=not checked)
            if name in {'list_headers','live_changes'} and isinstance(self.reads.store, SnapshotStore):
                self.reads.restore()
            epoch = self.reads.epoch
            key = self.body_key(args[0]) if name == 'read_message' else (name,repr(args),repr(sorted(kwargs.items())),epoch)
            result = self.reads.request(key,lambda:method(*deepcopy(args),**deepcopy(kwargs)))
            if epoch != self.reads.epoch:
                raise MailboxError('Mailbox changed; refreshing…', code='pending', retry_after=1)
            return result
        return read
