"""Private, bounded Inbox metadata only. No MIME, attachments or credentials."""
from datetime import datetime
import hashlib
import json
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
    def read_index(self, config):
        with self.transaction() as cur:
            cur.execute('SELECT snapshot FROM support_email_inbox_snapshot WHERE mailbox_key=%s', (identity(config),))
            return decode((cur.fetchone() or {}).get('snapshot') or {})

    def save_index(self, config, value):
        # Explicitly retain only metadata produced by header reads.
        allowed = {'uid','uidvalidity','folder','message_id','references','in_reply_to','subject',
                   'sender','reply_to','to','cc','date','received_at','flags','unread','snippet','has_attachments'}
        snapshot = value['snapshot']
        data = {'snapshot': {k: snapshot[k] for k in ('total','matched','uidvalidity','live_uid','refreshed_at','has_more')},
                'folders': value.get('folders'), 'synced_at': value['synced_at']}
        data['snapshot']['messages'] = [{k:v for k,v in m.items() if k in allowed} for m in snapshot['messages'][-50:]]
        serialized = encode(data)
        if len(serialized.encode()) > 512*1024:
            raise ValueError('Mailbox metadata exceeds snapshot limit')
        with self.transaction() as cur:
            cur.execute('''INSERT INTO support_email_inbox_snapshot(mailbox_key,snapshot,updated_at)
                VALUES(%s,%s::jsonb,now()) ON CONFLICT(mailbox_key) DO UPDATE
                SET snapshot=EXCLUDED.snapshot,updated_at=now()
                WHERE (support_email_inbox_snapshot.snapshot->>'synced_at')::numeric <= %s''',
                (identity(config), serialized, value['synced_at']))
