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
            cur.execute("SELECT to_jsonb(q)->'replacement' AS replacement FROM auto_edition_onboarding q WHERE product_gid=%s",(pid,))
            pending=(cur.fetchone() or {}).get('replacement') or {}
            if pending.get('stage') in ('Discovering','Queued','Preparing'):
                from auto_editions_reset import save
                pending.update(stage='Failed',reason='A newer authorised mapping superseded this reset.')
                save(cur,pid,pending)
                self.audit(cur,pid,actor,'reset_failed',{'request_id':pending['id'],'reason':pending['reason']})
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
            cur.execute("""SELECT product_gid FROM auto_edition_onboarding q WHERE lease_until>now()
                AND (status='Preparing' OR to_jsonb(q)->'replacement'->>'stage'='Preparing') LIMIT 1""")
            if cur.fetchone():return None
            cur.execute("""SELECT * FROM auto_edition_onboarding q WHERE lease_until<now()
                AND to_jsonb(q)->'replacement'->>'stage'='Preparing'
                AND (to_jsonb(q)->'replacement'->>'attempts')::int>=3 FOR UPDATE""")
            for interrupted in cur.fetchall():
                from auto_editions_reset import save
                pending=interrupted['replacement'];pending.update(stage='Failed',reason='Preparation interrupted three times. The working design is retained.')
                save(cur,interrupted['product_gid'],pending)
                self.audit(cur,interrupted['product_gid'],actor,'reset_failed',{'request_id':pending['id'],'reason':pending['reason']})
            # Bounded retries; failed/stale workers cannot publish under a new lease.
            cur.execute("""UPDATE auto_edition_onboarding SET status='Blocked',
                reason='Preparation worker interrupted three times. Retry after checking Photoshop.',
                lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE status='Preparing' AND lease_until<now() AND attempts>=3""")
            cur.execute("""SELECT * FROM auto_edition_onboarding q WHERE
                (((to_jsonb(q)->'replacement'->>'stage'='Queued' OR
                  (to_jsonb(q)->'replacement'->>'stage'='Preparing' AND lease_until<now()))
                   AND COALESCE((to_jsonb(q)->'replacement'->>'attempts')::int,0)<3)
                OR (COALESCE(to_jsonb(q)->'replacement'->>'stage','') IN ('','Complete','Failed') AND attempts<3 AND
                  ((status='Awaiting preparation' AND priority>0) OR (status='Preparing' AND lease_until<now()))))
                ORDER BY GREATEST(priority,CASE WHEN to_jsonb(q)->'replacement'->>'stage' IN ('Queued','Preparing') THEN 2 ELSE 0 END) DESC,
                created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            row=cur.fetchone()
            if not row:return None
            pending=row.get('replacement') or {}
            if pending.get('stage') in ('Queued','Preparing'):
                from auto_editions_reset import save
                pending.update(stage='Preparing',attempts=pending.get('attempts',0)+1)
                save(cur,row['product_gid'],pending)
                cur.execute("""UPDATE auto_edition_onboarding SET lease_token=%s,
                    lease_until=now()+interval '45 minutes' WHERE product_gid=%s RETURNING *""",(token,row['product_gid']))
                result=dict(cur.fetchone());result.update(file_id=pending['file_id'],source=pending['source'],status='Preparing')
                self.audit(cur,row['product_gid'],actor,'claimed',{'lease':token,'reset_id':pending['id']})
                return result
            if pending.get('stage')=='Failed':
                cur.execute('UPDATE auto_edition_onboarding SET replacement=NULL WHERE product_gid=%s',(row['product_gid'],))
            cur.execute("""UPDATE auto_edition_onboarding SET status='Preparing',reason='',
                lease_token=%s,lease_until=now()+interval '45 minutes',attempts=attempts+1,
                updated_at=now() WHERE product_gid=%s RETURNING *""",(token,row['product_gid']))
            result=dict(cur.fetchone());self.audit(cur,row['product_gid'],actor,'claimed',{'lease':token})
            return result

    def checkpoint(self, pid, token, actor, status, reason='', source=None, total=None, digest=None, metrics=None):
        if status not in ('Preparing','Needs PSD Repair','Blocked','Cloud Ready'):
            raise ValueError('Unsupported preparation status.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT to_jsonb(q)->'replacement' AS replacement FROM auto_edition_onboarding q WHERE product_gid=%s",(pid,))
            initial=cur.fetchone()
            if initial and (initial['replacement'] or {}).get('stage')=='Preparing':
                from auto_editions_reset import locks,save,finish
                locks(cur)
                cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s AND lease_token=%s AND lease_until>now() FOR UPDATE',(pid,token))
                row=cur.fetchone()
                if not row or (row.get('replacement') or {}).get('stage')!='Preparing':raise ValueError('Replacement lease expired or superseded.')
                pending=row['replacement']
                if source is not None and source!=pending['source']:raise ValueError('Replacement source changed.')
                if digest:
                    finish(cur,row,digest,actor,reason,metrics)
                elif status!='Preparing':
                    pending.update(stage='Failed',reason=reason,failure_status='Needs Repair' if status=='Needs PSD Repair' else 'Failed')
                    save(cur,pid,pending)
                    self.audit(cur,pid,actor,'reset_failed',{'request_id':pending['id'],'reason':reason})
                return
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
                AND COALESCE(to_jsonb(q)->'replacement'->>'stage','')<>'Preparing'
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
