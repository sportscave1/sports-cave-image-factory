"""Private coordination metadata in the existing app_sync_state table only.

Short transactions work with transaction poolers. Lease time is PostgreSQL time;
an expired owner cannot renew or publish. No mailbox content is accepted here.
"""
import hashlib
import json
from contextlib import contextmanager

LEASE_SECONDS = 60


def key(mailbox, kind):
    return 'email_idle_v1:' + kind + ':' + hashlib.sha256(mailbox.casefold().encode()).hexdigest()


class SignalStore:
    def __init__(self, connect=None):
        self.connect = connect

    @contextmanager
    def transaction(self):
        if self.connect is None:
            from supabase_backend import connect
        else:
            connect = self.connect
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='2000ms'")
                yield cur
            conn.commit()

    def claim(self, mailbox, owner):
        with self.transaction() as cur:
            cur.execute("""INSERT INTO app_sync_state(key,value,status,updated_at)
                VALUES (%s,jsonb_build_object('owner',%s::text,'until',extract(epoch from clock_timestamp())+60),'ready',now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()
                WHERE COALESCE((app_sync_state.value->>'until')::numeric,0)<extract(epoch from clock_timestamp())
                RETURNING key""", (key(mailbox, 'lease'), owner))
            return cur.fetchone() is not None

    def renew(self, mailbox, owner):
        with self.transaction() as cur:
            cur.execute("""UPDATE app_sync_state SET
                value=jsonb_build_object('owner',%s::text,'until',extract(epoch from clock_timestamp())+60),updated_at=now()
                WHERE key=%s AND value->>'owner'=%s
                AND (value->>'until')::numeric>extract(epoch from clock_timestamp()) RETURNING key""",
                (owner, key(mailbox, 'lease'), owner))
            return cur.fetchone() is not None

    def release(self, mailbox, owner):
        with self.transaction() as cur:
            cur.execute("""UPDATE app_sync_state SET value=jsonb_build_object('owner',%s::text,'until',0),updated_at=now()
                WHERE key=%s AND value->>'owner'=%s""", (owner, key(mailbox, 'lease'), owner))

    def publish(self, mailbox, owner, status, version):
        # Explicit primitive allowlist. Never persist a provider response dictionary.
        value = {k: int(status[k]) for k in ('uidvalidity', 'uidnext', 'unseen', 'messages')}
        value.update(mailbox=mailbox.casefold(), version=str(version))
        with self.transaction() as cur:
            # Lock/fence the lease until the signal write commits.
            cur.execute("""SELECT key FROM app_sync_state WHERE key=%s AND value->>'owner'=%s
                AND (value->>'until')::numeric>extract(epoch from clock_timestamp()) FOR UPDATE""",
                (key(mailbox, 'lease'), owner))
            if not cur.fetchone():
                raise RuntimeError('Mailbox watcher ownership expired')
            cur.execute("""INSERT INTO app_sync_state(key,value,status,updated_at)
                VALUES (%s,%s::jsonb || jsonb_build_object('checked_at',extract(epoch from clock_timestamp())),'ready',now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now() RETURNING value""",
                (key(mailbox, 'signal'), json.dumps(value)))
            return cur.fetchone()['value']

    def read(self, mailbox):
        with self.transaction() as cur:
            cur.execute("SELECT value FROM app_sync_state WHERE key=%s", (key(mailbox, 'signal'),))
            return (cur.fetchone() or {}).get('value') or {}
