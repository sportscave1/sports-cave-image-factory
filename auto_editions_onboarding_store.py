"""Durable product preparation checkpoints; never writes mappings or allocations."""
import json
import uuid


class Queue:
    def __init__(self, connect):
        self.connect = connect

    @staticmethod
    def audit(cur, pid, actor, event, detail=None):
        if not actor:
            raise PermissionError('An identified operator is required.')
        cur.execute('''INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event,detail)
                    VALUES(%s,%s,%s,%s::jsonb)''', (pid,actor,event,json.dumps(detail or {})))

    def enqueue(self, pid, file_id, actor, *, newly_linked=True):
        with self.connect() as conn, conn.cursor() as cur:
            self.enqueue_cursor(cur,pid,file_id,actor,newly_linked=newly_linked)

    def enqueue_cursor(self, cur, pid, file_id, actor, *, newly_linked=True, expected_source=None):
        """Reuse checkpoint decisions inside a mapping/registration transaction."""
        cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s', (pid,))
        mapping = cur.fetchone()
        if not mapping or mapping['dropbox_file_id'] != file_id:
            raise ValueError('The verified PSD mapping changed.')
        cur.execute('''SELECT p.hash,p.manifest FROM auto_edition_layouts l
            JOIN auto_edition_preparations p ON p.hash=l.preparation_hash
            WHERE l.product_gid=%s AND p.manifest->'source'->>'file_id'=%s LIMIT 1''',(pid,file_id))
        approved=cur.fetchone()
        if approved and (expected_source is None or approved['manifest']['source']==expected_source):
            cur.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,status,source,preparation_hash)
                VALUES(%s,%s,'Cloud Ready',%s::jsonb,%s) ON CONFLICT DO NOTHING""",
                (pid,file_id,json.dumps(approved['manifest']['source']),approved['hash']))
            return
        cur.execute("""SELECT hash,manifest FROM auto_edition_preparations
            WHERE manifest->'source'->>'product_gid'=%s AND manifest->'source'->>'file_id'=%s
            ORDER BY created_at DESC LIMIT 1""",(pid,file_id))
        prepared=cur.fetchone()
        if prepared:
            cur.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,status,reason,source,preparation_hash)
                VALUES(%s,%s,'Blocked','Prepared assets retained; review current source and visual quality.',%s::jsonb,%s)
                ON CONFLICT DO NOTHING""",(pid,file_id,json.dumps(prepared['manifest']['source']),prepared['hash']))
            return
        cur.execute('''INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) VALUES(%s,%s,%s)
            ON CONFLICT(product_gid) DO UPDATE SET file_id=excluded.file_id,source=NULL,
            preparation_hash=NULL,status='Awaiting preparation',reason='',attempts=0,priority=excluded.priority,
            lease_token=NULL,lease_until=NULL,updated_at=now()
            WHERE auto_edition_onboarding.file_id<>excluded.file_id RETURNING product_gid''',(pid,file_id,2 if newly_linked else 0))
        if cur.fetchone():
            self.audit(cur,pid,actor,'queued')

    def seed(self, actor):
        """Resume existing mappings; completed products are not reset or rescanned."""
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''SELECT m.shopify_product_gid,m.dropbox_file_id FROM product_psd_mappings m
                 LEFT JOIN edition_orders o ON o.shopify_product_gid=m.shopify_product_gid
                 GROUP BY m.shopify_product_gid,m.dropbox_file_id
                 ORDER BY max(o.id) DESC NULLS LAST,count(o.id) DESC''')
            rows = cur.fetchall()
        for row in rows:
            self.enqueue(row['shopify_product_gid'],row['dropbox_file_id'],actor,newly_linked=False)
        return len(rows)

    def claim(self, actor):
        token = str(uuid.uuid4())
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            cur.execute("SELECT product_gid FROM auto_edition_onboarding WHERE status='Preparing' AND lease_until>now() LIMIT 1")
            if cur.fetchone():return None
            # Bounded retries; failed/stale workers cannot publish under a new lease.
            cur.execute("""UPDATE auto_edition_onboarding SET status='Blocked',
                reason='Preparation worker interrupted three times. Retry after checking Photoshop.',
                lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE status='Preparing' AND lease_until<now() AND attempts>=3""")
            cur.execute("""SELECT * FROM auto_edition_onboarding WHERE attempts<3 AND
                ((status='Awaiting preparation' AND priority>0) OR (status='Preparing' AND lease_until<now()))
                ORDER BY priority DESC,created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            row=cur.fetchone()
            if not row:return None
            cur.execute("""UPDATE auto_edition_onboarding SET status='Preparing',reason='',
                lease_token=%s,lease_until=now()+interval '45 minutes',attempts=attempts+1,
                updated_at=now() WHERE product_gid=%s RETURNING *""",(token,row['product_gid']))
            result=dict(cur.fetchone());self.audit(cur,row['product_gid'],actor,'claimed',{'lease':token})
            return result

    def checkpoint(self, pid, token, actor, status, reason='', source=None, total=None, digest=None, metrics=None):
        if status not in ('Preparing','Needs PSD Repair','Blocked','Cloud Ready'):
            raise ValueError('Unsupported preparation status.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_onboarding SET status=%s,reason=%s,
                source=COALESCE(%s::jsonb,source),edition_total=COALESCE(%s,edition_total),
                preparation_hash=COALESCE(%s,preparation_hash),updated_at=now()
                WHERE product_gid=%s AND lease_token=%s AND lease_until>now()
                AND status='Preparing' RETURNING product_gid""",
                (status,reason,json.dumps(source) if source else None,total,digest,pid,token))
            if not cur.fetchone():raise ValueError('Preparation lease expired or was superseded.')
            self.audit(cur,pid,actor,status,{'reason':reason,'preparation_hash':digest})
            if metrics is not None:
                self.audit(cur,pid,actor,'preparation_metrics',dict(metrics,preparation_hash=digest))

    def completed_receipt(self,pid,token,actor):
        """Recover an acknowledged import only for its original owner and lease."""
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT q.preparation_hash,p.manifest->'source' AS source,
                COALESCE((SELECT detail FROM auto_edition_onboarding_audit a
                    WHERE a.product_gid=q.product_gid AND a.event='preparation_metrics'
                    AND a.detail->>'preparation_hash'=q.preparation_hash
                    ORDER BY a.created_at DESC LIMIT 1),'{}'::jsonb) AS timings
                FROM auto_edition_onboarding q
                JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
                JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                WHERE q.product_gid=%s AND q.lease_token=%s
                AND q.status IN ('Blocked','Cloud Ready')
                AND m.dropbox_file_id=p.manifest->'source'->>'file_id'
                AND EXISTS (SELECT 1 FROM auto_edition_onboarding_audit a
                    WHERE a.product_gid=q.product_gid AND a.actor_id=%s
                    AND a.event='claimed' AND a.detail->>'lease'=%s)""",(pid,token,actor,token))
            row=cur.fetchone()
            return dict(row) if row else None

    def retry(self,pid,actor):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_onboarding SET status='Awaiting preparation',reason='',
                attempts=0,priority=10,lease_token=NULL,lease_until=NULL,source=NULL,preparation_hash=NULL,updated_at=now()
                WHERE product_gid=%s AND status IN ('Blocked','Needs PSD Repair') AND preparation_hash IS NULL
                RETURNING product_gid""",(pid,))
            if not cur.fetchone():raise ValueError('Only a failed preparation can be retried.')
            self.audit(cur,pid,actor,'retry')

    def rows(self):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''SELECT q.*,p.product_title FROM auto_edition_onboarding q
                JOIN edition_products p ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=q.product_gid
                ORDER BY q.created_at''')
            return [dict(r) for r in cur.fetchall()]

    def prepare_now(self,pid,actor):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_onboarding SET priority=10,reason='Administrator Prepare Now',updated_at=now()
                WHERE product_gid=%s AND status='Awaiting preparation' RETURNING product_gid""",(pid,))
            if not cur.fetchone():raise ValueError('Only an awaiting or deferred product can be prioritised. Review failed or prepared artwork separately.')
            self.audit(cur,pid,actor,'prepare_now')
