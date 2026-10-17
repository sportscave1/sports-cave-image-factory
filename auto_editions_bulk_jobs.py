"""Durable, isolated TEST review operations. Never processes preparation/order jobs."""
import json
import uuid
import auto_editions as ae
STATES=('Pending','Processing','Approved','Skipped','Needs Attention','Failed')
ACTIVE=('Pending','Processing')
MAX_ATTEMPTS=3


def request_identity(value):
    try:return str(uuid.UUID(value))
    except (ValueError,TypeError,AttributeError):raise ValueError('Stable approval request UUID required.')


class ReviewJobs:

    def __init__(self,connect):self.connect=connect

    def submit(self,actor,key,items,validate=None):
        from auto_editions_status import identity
        key=request_identity(key)
        if not actor or not isinstance(items,list) or not 1<=len(items)<=1000:raise ValueError('Bounded confirmed selection required.')
        selected={}
        import re
        for item in items:
            if not isinstance(item,dict) or set(item)!={'product_gid','hash'}:raise ValueError('Exact review identities required.')
            pid=identity(item['product_gid']);digest=item['hash']
            if not re.fullmatch('[a-f0-9]{64}',str(digest)):raise ValueError('Exact preparation hashes required.')
            if pid in selected and selected[pid]!=digest:raise ValueError('Conflicting preparation identities.')
            selected[pid]=digest
        fingerprint=ae.fingerprint(sorted(selected.items()))
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='800ms'; SET LOCAL statement_timeout='4000ms'")
            cur.execute('INSERT INTO auto_edition_review_batches(id,actor_id,payload_hash) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(key,actor,fingerprint))
            cur.execute('SELECT * FROM auto_edition_review_batches WHERE id=%s FOR UPDATE',(key,));batch=cur.fetchone()
            if batch['actor_id']!=actor:raise PermissionError('This review request belongs to another administrator.')
            if batch['payload_hash']!=fingerprint:raise ValueError('Review request identity already used for a different selection.')
            cur.execute('SELECT count(*) AS n FROM auto_edition_review_items WHERE batch_id=%s',(key,))
            if cur.fetchone()['n']:return key
            rejected=validate(conn,selected) if validate else {}
            payload=json.dumps([dict(id=str(uuid.uuid4()),product_gid=pid,preparation_hash=digest,
                state='Needs Attention' if pid in rejected else 'Pending',reason=rejected.get(pid,'')) for pid,digest in sorted(selected.items())])
            cur.execute("""INSERT INTO auto_edition_review_jobs(id,product_gid,preparation_hash,actor_id,state,reason)
                SELECT x.id,x.product_gid,x.preparation_hash,%s,x.state,x.reason FROM jsonb_to_recordset(%s::jsonb)
                AS x(id text,product_gid text,preparation_hash text,state text,reason text)
                WHERE x.state<>'Pending' OR NOT EXISTS(SELECT 1 FROM auto_edition_review_jobs done
                    JOIN auto_edition_layouts l ON l.product_gid=done.product_gid AND l.preparation_hash=done.preparation_hash AND l.variant_id='*'
                    JOIN auto_edition_onboarding q ON q.product_gid=done.product_gid AND q.preparation_hash=done.preparation_hash
                    WHERE done.product_gid=x.product_gid AND done.preparation_hash=x.preparation_hash AND done.state='Approved'
                    AND l.approval->>'test_only'='true' AND l.approval->>'visual_approved'='true')
                ORDER BY x.product_gid
                ON CONFLICT (product_gid) WHERE state IN ('Pending','Processing') DO NOTHING""",(actor,payload))
            cur.execute("""INSERT INTO auto_edition_review_items(batch_id,product_gid,job_id)
                SELECT %s,x.product_gid,j.id FROM jsonb_to_recordset(%s::jsonb)
                    AS x(id text,product_gid text,preparation_hash text)
                JOIN LATERAL (SELECT candidate.id FROM auto_edition_review_jobs candidate
                    WHERE candidate.product_gid=x.product_gid AND (candidate.id=x.id OR (candidate.state IN ('Pending','Processing') AND candidate.preparation_hash=x.preparation_hash) OR
                        (candidate.state='Approved' AND candidate.preparation_hash=x.preparation_hash AND EXISTS(
                            SELECT 1 FROM auto_edition_layouts l JOIN auto_edition_onboarding q ON q.product_gid=l.product_gid
                            WHERE l.product_gid=x.product_gid AND l.preparation_hash=x.preparation_hash AND q.preparation_hash=x.preparation_hash
                            AND l.variant_id='*' AND l.approval->>'test_only'='true' AND l.approval->>'visual_approved'='true')))
                    ORDER BY (candidate.state IN ('Pending','Processing')) DESC,(candidate.id=x.id) DESC,candidate.created_at DESC,candidate.id DESC LIMIT 1) j ON true
                RETURNING product_gid""",(key,payload))
            if len(cur.fetchall())!=len(selected):raise RuntimeError('Concurrent review completed during submission. Reconcile this request before retrying.')
        return key

    def progress(self,actor,*,batch_id=None,product_gids=None,active_review_only=False,watch=None):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='3000ms'; SET LOCAL lock_timeout='500ms'")
            if batch_id:
                batch_id=request_identity(batch_id)
                cur.execute('SELECT id FROM auto_edition_review_batches WHERE id=%s AND actor_id=%s',(batch_id,actor))
                if not cur.fetchone():return dict(batch_id=batch_id,found=False,rows=[],counts={s:0 for s in STATES},active=False)
                cur.execute("""SELECT j.*,i.batch_id,(j.created_at<b.confirmed_at) AS reused FROM auto_edition_review_items i JOIN auto_edition_review_jobs j ON j.id=i.job_id
                    JOIN auto_edition_review_batches b ON b.id=i.batch_id
                    WHERE i.batch_id=%s ORDER BY j.created_at,j.id""",(batch_id,))
            else:
                # Bounded catalogue recovery includes terminal results; no browser storage is required for accepted work.
                from auto_editions_status import identity
                ids=list(dict.fromkeys(identity(p) for p in product_gids or []))
                if len(ids)>1000:raise ValueError('Bounded recovery selection required.')
                watch=list(dict.fromkeys(identity(p) for p in watch or []))
                if len(watch)>1000 or not set(watch)<=set(ids):raise ValueError('Watched products must belong to this catalogue selection.')
                cur.execute("""SELECT * FROM (SELECT DISTINCT ON(j.product_gid) j.* FROM auto_edition_review_jobs j
                    WHERE j.product_gid=ANY(%s) ORDER BY j.product_gid,j.created_at DESC,j.id DESC) latest"""+
                    (" WHERE state IN ('Pending','Processing','Failed','Needs Attention') OR product_gid=ANY(%s)" if active_review_only else ''),(ids,watch) if active_review_only else (ids,))
            rows=cur.fetchall()
        public=[dict(job_id=r['id'],product_gid=r['product_gid'],hash=r['preparation_hash'],state=r['state'],reason=r['reason'],
            acceptance=('already_processing' if r.get('reused') else 'accepted') if r['state'] in ACTIVE else 'already_approved' if r['state']=='Approved' else 'failed') for r in rows]
        counts={s:sum(r['state']==s for r in public) for s in STATES}
        return dict(batch_id=batch_id,found=True,rows=public,counts=counts,active=any(r['state'] in ACTIVE for r in public),print_ready=False)

    def claim(self):
        token=str(uuid.uuid4())
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='3000ms'")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('edition-review-claims-v1'))")
            cur.execute("SELECT count(*) AS n FROM auto_edition_review_jobs WHERE state='Processing' AND lease_until>now()")
            if cur.fetchone()['n']>=2:return None
            cur.execute("""SELECT * FROM auto_edition_review_jobs
                WHERE (state='Pending' AND next_attempt_at<=now()) OR (state='Processing' AND lease_until<now())
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1""");row=cur.fetchone()
            if not row:return None
            # Recovery of an expired lease must inspect the atomic result before applying an attempt limit.
            cur.execute("""UPDATE auto_edition_review_jobs SET state='Processing',attempts=attempts+1,
                lease_token=%s,lease_until=now()+interval '90 seconds',updated_at=now() WHERE id=%s RETURNING *""",(token,row['id']))
            return dict(cur.fetchone())

    def renew(self,job):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_review_jobs SET lease_until=now()+interval '90 seconds'
                WHERE id=%s AND lease_token=%s AND state='Processing' AND lease_until>now() RETURNING id""",(job['id'],job['lease_token']))
            return bool(cur.fetchone())

    @staticmethod
    def fence(cur,job):
        cur.execute("SELECT id FROM auto_edition_review_jobs WHERE id=%s AND lease_token=%s AND state='Processing' AND lease_until>now() FOR UPDATE",(job['id'],job['lease_token']))
        if not cur.fetchone():raise ValueError('Approval lease changed; current owner will reconcile.')

    @staticmethod
    def terminal(cur,job,state,reason=''):
        if state not in STATES or state in ACTIVE:raise ValueError('Terminal approval result required.')
        cur.execute("""UPDATE auto_edition_review_jobs SET state=%s,reason=%s,lease_token=NULL,lease_until=NULL,updated_at=now()
            WHERE id=%s AND lease_token=%s AND state='Processing'""",(state,reason,job['id'],job['lease_token']))

    def finish(self,job,state,reason=''):
        with self.connect() as conn,conn.cursor() as cur:self.terminal(cur,job,state,reason)

    def transient(self,job):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_review_jobs SET state=%s,reason=%s,lease_token=NULL,lease_until=NULL,
                next_attempt_at=now()+interval '15 seconds',updated_at=now()
                WHERE id=%s AND lease_token=%s AND state='Processing'""",
                ('Pending' if job['attempts']<MAX_ATTEMPTS else 'Failed',
                 'Provider or database temporarily unavailable; retry scheduled.' if job['attempts']<MAX_ATTEMPTS else 'Provider or database unavailable after three attempts. Use Review / Repair, then submit again.',job['id'],job['lease_token']))


class PreviewStore:

    def __init__(self,connect):self.connect=connect

    def get(self,key):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT encode(jpeg,'hex') AS jpeg FROM auto_edition_review_previews WHERE identity=%s",(key,));row=cur.fetchone()
            return bytes.fromhex(row['jpeg']) if row else None

    def get_many(self,keys):
        if len(keys)>8:raise ValueError('Bounded preview cache read required.')
        if not keys:return {}
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT identity,encode(jpeg,'hex') AS jpeg FROM auto_edition_review_previews WHERE identity=ANY(%s)",(keys,))
            return {row['identity']:bytes.fromhex(row['jpeg']) for row in cur.fetchall()}

    def put(self,key,data):
        if len(data)>524288:return
        with self.connect() as conn,conn.cursor() as cur:
            # Decode hex server-side for both psycopg and disposable PostgreSQL transport.
            cur.execute("INSERT INTO auto_edition_review_previews(identity,jpeg) VALUES(%s,decode(%s,'hex')) ON CONFLICT(identity) DO UPDATE SET jpeg=EXCLUDED.jpeg WHERE auto_edition_review_previews.jpeg<>EXCLUDED.jpeg",(key,data.hex()))
