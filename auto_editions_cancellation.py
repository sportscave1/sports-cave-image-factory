"""Durable design-scoped cancellation before the unchanged normal Reset."""
import json
import uuid
from auto_editions_onboarding_store import Queue
from auto_editions_reset import Reset, locks
import psd_directory as psd
from psd_mapping_store import PostgresMappings

PENDING = ('Cancelling', 'Confirmed')


class Cancellation:
    def __init__(self, connect): self.connect = connect

    def clear(self, pid, request_id, actor):
        return self.request(pid,request_id,actor,clear_mapping=True)

    def request(self, pid, request_id, actor, *, clear_mapping=False):
        from auto_editions_discovery import enabled
        if not enabled(): raise ValueError('Automatic PSD discovery is disabled.')
        if not psd.product_id({'shopify_product_gid': pid}) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError('Exact product and reset request identities are required.')
        if not actor: raise PermissionError('An identified administrator is required.')
        with self.connect() as conn, conn.cursor() as cur:
            locks(cur)
            PostgresMappings.product(cur, pid)
            # Match claim's table lock before taking a row lock; no lock upgrade race.
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE', (pid,))
            row = cur.fetchone()
            if row:
                pending = row.get('reset_cancellation') or {}
                if pending.get('stage') in PENDING or pending.get('id') == request_id:
                    request_id = pending['id']
                    actor = pending['actor']
                else:
                    # Delayed retries must never cancel a later reset.
                    cur.execute("SELECT 1 FROM auto_edition_onboarding_audit WHERE product_gid=%s AND detail->>'request_id'=%s AND event LIKE 'reset_%%' LIMIT 1", (pid, request_id))
                    if cur.fetchone(): return 'Already requested'
                    replacement = row.get('replacement') or {}
                    active = row['status'] == 'Preparing' or replacement.get('stage') == 'Preparing'
                    pending = dict(id=request_id, actor=actor, stage='Cancelling' if active else 'Confirmed',
                                   lease=str(row['lease_token']) if active and row.get('lease_token') else None,clear_mapping=clear_mapping)
                    if replacement.get('stage') in ('Discovering', 'Queued', 'Preparing'):
                        replacement.update(stage='Failed', reason='Cancelled for Reset.')
                    # Fence callbacks, heartbeat, reconnect and checkpoint immediately.
                    cur.execute("""UPDATE auto_edition_onboarding SET reset_cancellation=%s::jsonb,
                        replacement=%s::jsonb,lease_token=NULL,lease_until=NULL,
                        status=CASE WHEN status IN ('Preparing','Awaiting preparation') THEN 'Blocked' ELSE status END
                        WHERE product_gid=%s""", (json.dumps(pending), json.dumps(replacement) if replacement else None, pid))
                    Queue.audit(cur, pid, actor, 'companion_cancellation_requested', dict(request_id=request_id, lease=pending['lease']))
                if pending['stage'] == 'Cancelling': return 'Cancelling'
                if pending['stage'] == 'Dispatched' and (row.get('replacement') or {}).get('id') == request_id:
                    return row['replacement']['stage']
        # Normal Reset remains the sole owner of mapping, discovery and review behavior.
        stage = (Reset(self.connect).clear if pending.get('clear_mapping',clear_mapping) else Reset(self.connect).request)(pid, request_id, actor)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_onboarding SET reset_cancellation=jsonb_set(reset_cancellation,'{stage}','"Dispatched"')
                WHERE product_gid=%s AND reset_cancellation->>'id'=%s AND reset_cancellation->>'stage'='Confirmed'""", (pid, request_id))
        return stage

    def poll(self, pid, token, actor, stopped=False):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM auto_edition_onboarding_audit WHERE product_gid=%s
                AND actor_id=%s AND event='claimed' AND detail->>'lease'=%s""", (pid, actor, token))
            if not cur.fetchone(): raise PermissionError('Preparation lease belongs to another operator.')
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT reset_cancellation FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE', (pid,))
            pending = (cur.fetchone() or {}).get('reset_cancellation') or {}
            cancelled = pending.get('lease') == token
            # Old cancellations remain terminal even after a newer Reset.
            if not cancelled:
                cur.execute("""SELECT 1 FROM auto_edition_onboarding_audit WHERE product_gid=%s
                    AND event='companion_cancellation_requested' AND detail->>'lease'=%s""", (pid, token))
                cancelled = bool(cur.fetchone())
            if cancelled and stopped and pending.get('lease') == token and pending.get('stage') == 'Cancelling':
                pending['stage'] = 'Confirmed'
                cur.execute('UPDATE auto_edition_onboarding SET reset_cancellation=%s::jsonb WHERE product_gid=%s', (json.dumps(pending), pid))
                Queue.audit(cur, pid, actor, 'companion_cancellation_confirmed', dict(request_id=pending['id'], lease=token))
        if cancelled and stopped: self.resume()
        return cancelled

    def resume(self):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT product_gid,reset_cancellation AS pending FROM auto_edition_onboarding
                WHERE reset_cancellation->>'stage'='Confirmed' ORDER BY created_at LIMIT 10""")
            rows = cur.fetchall()
        for row in rows:
            self.request(row['product_gid'], row['pending']['id'], row['pending']['actor'])
