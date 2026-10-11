"""Private, bounded Inbox metadata only. No MIME, attachments or credentials."""
from datetime import datetime
from contextlib import contextmanager
import hashlib
import json
import threading
import uuid
from support_email_idle_store import SignalStore


def identity(config):
    return hashlib.sha256(repr(config.scope).encode()).hexdigest()


def encode(value):
    return json.dumps(value, default=lambda v: v.isoformat() if isinstance(v, datetime) else list(v))


def decode(value):
    for row in (value.get('snapshot') or {}).get('messages', []):
        for field in ('date', 'received_at'):
            if isinstance(row.get(field), str):
                row[field] = datetime.fromisoformat(row[field])
    snapshot = value.get('snapshot') or {}
    if isinstance(snapshot.get('refreshed_at'), str):
        snapshot['refreshed_at'] = datetime.fromisoformat(snapshot['refreshed_at'])
    return value


class SnapshotStore(SignalStore):
    @contextmanager
    def mutation_guard(self, config):
        """Serialize writes across OS workers, including delayed provider acknowledgements."""
        from support_email_provider import MailboxError
        mailbox, owner = 'mailbox-mutation:' + identity(config), str(uuid.uuid4())
        try:
            claimed = self.claim(mailbox, owner)
        except Exception:
            raise MailboxError('Mailbox write coordination is unavailable. Nothing was changed.', code='busy') from None
        if not claimed:
            raise MailboxError('Another mailbox action is still finishing. Try again shortly.', code='busy')
        stopped = threading.Event()
        lease = {'valid':True}
        def renew():
            while not stopped.wait(15):
                try:lease['valid'] = self.renew(mailbox, owner)
                except Exception:lease['valid'] = False
                if not lease['valid']:return
        worker = threading.Thread(target=renew, name='email-write-lease', daemon=True)
        worker.start()
        try:yield lease
        finally:
            stopped.set();worker.join(timeout=3)
            try:self.release(mailbox, owner)
            except Exception:pass  # A confirmed provider action must not be reported as rejected.

    def save_confirmed(self, config, project, fallback):
        """Merge an exact confirmed mutation atomically, preserving other workers' writes.

        No transaction is held across provider I/O. The observation timestamp fences
        index reads begun before this confirmation. No body data enters this table.
        """
        with self.transaction() as cur:
            cur.execute('SELECT snapshot FROM support_email_inbox_snapshot WHERE mailbox_key=%s FOR UPDATE', (identity(config),))
            row = cur.fetchone()
            value = project(decode(row['snapshot'])) if row else fallback
            if row:
                cur.execute('UPDATE support_email_inbox_snapshot SET snapshot=%s::jsonb,updated_at=now() WHERE mailbox_key=%s',
                            (encode(value), identity(config)))
        if not row:
            self.save_index(config, value)
        return value

    def read_index(self, config):
        with self.transaction() as cur:
            cur.execute('SELECT snapshot FROM support_email_inbox_snapshot WHERE mailbox_key=%s', (identity(config),))
            return decode((cur.fetchone() or {}).get('snapshot') or {})

    def save_index(self, config, value):
        # Explicitly retain only metadata produced by header reads.
        allowed = {'uid','uidvalidity','folder','message_id','references','in_reply_to','subject',
                   'sender','reply_to','to','cc','date','received_at','flags','unread','has_attachments'}
        snapshot = value['snapshot']
        data = {'snapshot': {k: snapshot[k] for k in ('total','matched','uidvalidity','live_uid','refreshed_at','has_more')},
                'mutation_revision': value.get('mutation_revision', ''),
                'folders': value.get('folders'), 'synced_at': value['synced_at'],
                'observed_at': value.get('observed_at', value['synced_at'])}
        data['snapshot']['messages'] = [{k:v for k,v in m.items() if k in allowed} for m in snapshot['messages'][-50:]]
        serialized = encode(data)
        if len(serialized.encode()) > 512*1024:
            raise ValueError('Mailbox metadata exceeds snapshot limit')
        with self.transaction() as cur:
            cur.execute('''INSERT INTO support_email_inbox_snapshot(mailbox_key,snapshot,updated_at)
                VALUES(%s,%s::jsonb,now()) ON CONFLICT(mailbox_key) DO UPDATE
                SET snapshot=EXCLUDED.snapshot,updated_at=now()
                WHERE COALESCE(support_email_inbox_snapshot.snapshot->>'observed_at',
                               support_email_inbox_snapshot.snapshot->>'synced_at')::numeric < %s
                  AND COALESCE(support_email_inbox_snapshot.snapshot->>'mutation_revision','') =
                      COALESCE(EXCLUDED.snapshot->>'mutation_revision','')''',
                (identity(config), serialized, data['observed_at']))
