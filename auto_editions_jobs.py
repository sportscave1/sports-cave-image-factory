"""Durable, idempotent queue contract. No schema creation or work at import time."""
import json
import uuid

import auto_editions as ae


class Jobs:
    def __init__(self, connect):
        self.connect=connect

    @staticmethod
    def audit(cur, job_id, actor, event):
        cur.execute('INSERT INTO public.auto_edition_job_audit(job_id,actor_id,event) VALUES (%s,%s,%s)',
                    (job_id,actor,event))

    def enqueue(self, job, actor):
        if not actor or job['id'] != ae.fingerprint(job['identity']):
            raise ValueError('Authenticated actor and valid job identity required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''INSERT INTO public.auto_edition_jobs(id,payload,actor_id)
                           VALUES (%s,%s::jsonb,%s) ON CONFLICT(id) DO NOTHING''',
                        (job['id'],json.dumps(job),actor))
            cur.execute('''UPDATE public.auto_edition_jobs SET status='Queued',attempts=0,error_code=NULL,updated_at=now()
                WHERE id=%s AND status='Blocked' AND error_code='cache_expired' AND result IS NULL''',(job['id'],))
            self.audit(cur,job['id'],actor,'requested')
            cur.execute('SELECT id,status,attempts,error_code,result FROM public.auto_edition_jobs WHERE id=%s',(job['id'],))
            return dict(cur.fetchone())

    def claim(self):
        lease=str(uuid.uuid4())
        with self.connect() as conn,conn.cursor() as cur:
            # A worker can die on its last permitted attempt. Expire that lease
            # explicitly so the UI cannot remain in Generating indefinitely.
            cur.execute('''UPDATE public.auto_edition_jobs SET status='Blocked',
                error_code='worker_unavailable',lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE status='Generating' AND attempts >= 3 AND lease_until < now()
                RETURNING id''')
            for expired in cur.fetchall():
                self.audit(cur,expired['id'],'cloud-worker','attempts_exhausted')
            cur.execute('''WITH next AS (
                SELECT id FROM public.auto_edition_jobs
                WHERE attempts < 3 AND (status='Queued' OR (status='Generating' AND lease_until < now()))
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE public.auto_edition_jobs j SET status='Generating',attempts=attempts+1,
                  lease_token=%s,lease_until=now()+interval '10 minutes',updated_at=now()
                FROM next WHERE j.id=next.id RETURNING j.*''',(lease,))
            row=cur.fetchone()
            if row:self.audit(cur,row['id'],'cloud-worker','claimed')
            return dict(row) if row else None

    def finish(self, job_id, lease, result=None, error_code=None):
        # Caller supplies an allowlisted code, never provider exception messages.
        if error_code not in (None,'source_changed','asset_invalid','worker_unavailable'):
            raise ValueError('Unsupported worker error code.')
        if bool(result) == bool(error_code):
            raise ValueError('Exactly one result or error is required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''UPDATE public.auto_edition_jobs
                SET status=%s,result=%s::jsonb,error_code=%s,lease_token=NULL,
                    lease_until=NULL,updated_at=now()
                WHERE id=%s AND status='Generating' AND lease_token=%s AND lease_until > now()
                RETURNING id''',('Ready' if result else 'Blocked',json.dumps(result) if result else None,
                                error_code,job_id,lease))
            if not cur.fetchone():raise ValueError('Worker lease expired or was replaced; result rejected.')
            self.audit(cur,job_id,'cloud-worker','ready' if result else error_code)

    def retry(self, job_id, actor):
        if not actor:raise PermissionError('Authenticated actor required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''UPDATE public.auto_edition_jobs SET status='Queued',error_code=NULL,updated_at=now()
                WHERE id=%s AND status='Blocked' AND attempts < 3 AND error_code='worker_unavailable'
                RETURNING id''',(job_id,))
            if not cur.fetchone():raise ValueError('This job cannot be retried automatically.')
            self.audit(cur,job_id,actor,'retry')

    def read(self, job_id):
        # HTTP callers must revalidate current user, allocation and source first.
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM public.auto_edition_jobs WHERE id=%s',(job_id,))
            row=cur.fetchone()
            return dict(row) if row else None

    def expired(self):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''UPDATE public.auto_edition_jobs SET status='Blocked',error_code='cache_expired'
                WHERE id IN (SELECT id FROM public.auto_edition_jobs WHERE
                    (status='Ready' OR (status='Blocked' AND error_code='cache_expired'))
                    AND result IS NOT NULL AND updated_at<now()-interval '24 hours'
                    ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 10) RETURNING id,result''')
            return [dict(row) for row in cur.fetchall()]

    def forget_expired_output(self,job_id):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''UPDATE public.auto_edition_jobs SET result=NULL,updated_at=now()
                WHERE id=%s AND status='Blocked' AND error_code='cache_expired' RETURNING id''',(job_id,))
            if cur.fetchone():self.audit(cur,job_id,'cloud-worker','cache_expired')
