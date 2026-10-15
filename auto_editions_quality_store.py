"""Additive, bounded quality reconciliation in the existing discovery worker."""
import json
import logging

import auto_editions as ae
import auto_editions_quality as quality

LOG = logging.getLogger(__name__)


class Quality:
    def __init__(self, connect):
        self.connect = connect

    def recheck(self, pid, actor):
        if not quality.enabled() or not actor:
            raise PermissionError('An enabled production policy and administrator are required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_quality_checks c SET next_check_at=now()
                FROM auto_edition_onboarding q WHERE q.product_gid=%s
                  AND c.product_gid=q.product_gid AND c.preparation_hash=q.preparation_hash
                RETURNING c.preparation_hash""",(pid,))
            row=cur.fetchone()
            if not row:
                raise ValueError('No current quality checkpoint is available to recheck.')
            cur.execute("""INSERT INTO auto_edition_quality_audit(preparation_hash,event,detail)
                VALUES(%s,'recheck_requested',%s::jsonb)""",(row['preparation_hash'],json.dumps({'actor_id':actor})))

    def run_one(self, assets, records=None):
        if not quality.enabled():
            return False
        # Admission happens before provider I/O. An already admitted validation
        # finishes its existing transaction; a pause prevents the next one.
        from worker_health import control
        with self.connect() as conn,conn.cursor() as cur:
            if control(cur)['paused']:return False
        records = quality.standards() if records is None else records
        policy_hash = ae.fingerprint(records)
        with self.connect() as conn, conn.cursor() as cur:
            # Session advisory lock serialises only this quality worker. A crash
            # releases it; no preparation/mapping/approval row is leased or reset.
            cur.execute('SELECT pg_try_advisory_xact_lock(1616001) AS locked')
            if not cur.fetchone()['locked']:
                return False
            cur.execute("""SELECT p.*,to_jsonb(q) AS checkpoint,to_jsonb(m) AS mapping,ep.edition_total AS current_total,
                EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=q.product_gid
                       AND l.preparation_hash<>p.hash) AS conflicting
                FROM auto_edition_onboarding q
                JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
                JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                JOIN edition_products ep ON ep.shopify_product_gid=q.product_gid
                LEFT JOIN auto_edition_quality_checks c ON c.preparation_hash=p.hash
                WHERE q.status IN ('Blocked','Cloud Ready') AND
                  (c.preparation_hash IS NULL OR c.next_check_at<=now() OR c.policy_hash<>%s)
                ORDER BY c.next_check_at NULLS FIRST,q.updated_at LIMIT 1""", (policy_hash,))
            row = cur.fetchone()
            if not row:
                return False
            row = dict(row)
            checkpoint = dict(row['checkpoint'], conflicting_approval=row['conflicting'],current_total=row['current_total'])
            def metadata(fid):
                return assets.integration.psd_open_metadata(assets.token, fid, include_preview=False)
            # Avoid fetching historical PNGs without an eligible approved standard.
            try:
                source = metadata(row['mapping']['dropbox_file_id'])
                check = quality.assess(row, row['mapping'], checkpoint, source,
                                       metadata, assets.fetch, records)
                # Fence source changes during the expensive validation interval.
                if (check['status']=='Production Ready' and
                        ae.source_identity(row['manifest']['source']['product_gid'],
                                           metadata(row['mapping']['dropbox_file_id'])) != row['manifest']['source']):
                    check = quality.result('Needs Review', 'Source changed during validation.', row['manifest'])
            except Exception:
                check = quality.result('Failed', 'Quality verification is temporarily unavailable.', row['manifest'])
            # Final read-only mapping/checkpoint/approval fence before certification.
            # Same product -> mapping -> onboarding -> layouts order as V15.
            cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',
                        (checkpoint['product_gid'],))
            product=cur.fetchone()
            cur.execute('SELECT to_jsonb(m) AS value FROM product_psd_mappings m WHERE shopify_product_gid=%s FOR SHARE',
                        (checkpoint['product_gid'],))
            mapping = cur.fetchone()
            cur.execute('SELECT to_jsonb(q) AS value FROM auto_edition_onboarding q WHERE product_gid=%s FOR SHARE',
                        (checkpoint['product_gid'],))
            current = cur.fetchone()
            cur.execute('LOCK TABLE auto_edition_layouts IN SHARE MODE')
            cur.execute('SELECT 1 FROM auto_edition_layouts WHERE product_gid=%s AND preparation_hash<>%s LIMIT 1',
                        (checkpoint['product_gid'], row['hash']))
            if (not current or not mapping or not product or product['edition_total']!=row['current_total'] or current['value'] != row['checkpoint']
                    or mapping['value'] != row['mapping'] or cur.fetchone()):
                check = quality.result('Needs Review', 'Source, approval or checkpoint changed during validation.', row['manifest'])
            if not quality.enabled() or quality.standards() != records:
                return False
            cur.execute("""INSERT INTO auto_edition_quality_checks
                (preparation_hash,product_gid,source,status,assessment,policy_hash,next_check_at)
                VALUES(%s,%s,%s::jsonb,%s,%s::jsonb,%s,now()+interval '24 hours')
                ON CONFLICT(preparation_hash) DO UPDATE SET source=excluded.source,
                  status=excluded.status,assessment=excluded.assessment,policy_hash=excluded.policy_hash,
                  checked_at=now(),next_check_at=excluded.next_check_at""",
                (row['hash'],checkpoint['product_gid'],json.dumps(check['source']),check['status'],json.dumps(check),policy_hash))
            cur.execute("""INSERT INTO auto_edition_quality_audit(preparation_hash,event,detail)
                VALUES(%s,%s,%s::jsonb)""", (row['hash'],check['status'],json.dumps(dict(
                    policy=quality.POLICY,standard_id=check['standard_id'],reason=check['reason']))))
        return True

    def for_unit(self, unit):
        if not quality.enabled():
            return None
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT c.assessment,p.manifest,c.next_check_at>now() AS fresh,
                q.source,q.preparation_hash,q.edition_total,ep.edition_total AS current_total,m.dropbox_file_id,
                EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=q.product_gid
                    AND l.preparation_hash<>p.hash) AS conflicting
                FROM auto_edition_quality_checks c
                JOIN auto_edition_onboarding q ON q.product_gid=c.product_gid AND q.preparation_hash=c.preparation_hash
                JOIN auto_edition_preparations p ON p.hash=c.preparation_hash
                JOIN product_psd_mappings m ON m.shopify_product_gid=c.product_gid
                JOIN edition_products ep ON ep.shopify_product_gid=c.product_gid
                WHERE c.product_gid=%s AND q.status IN ('Blocked','Cloud Ready')""",(unit['shopify_product_gid'],))
            rows=cur.fetchall()
        if len(rows)!=1:
            return None
        row=rows[0];check=row['assessment'];m=row['manifest']
        variants={str(v).removeprefix('gid://shopify/ProductVariant/') for v in check.get('evidence',{}).get('scope',[])}
        if (not row['fresh'] or row['conflicting'] or row['source']!=m['source']
                or row['dropbox_file_id']!=m['source']['file_id'] or row['edition_total']!=m['edition_total']
                or row['current_total']!=m['edition_total']
                or str(unit.get('shopify_variant_id') or '').removeprefix('gid://shopify/ProductVariant/') not in variants
                or not quality.current_certificate(check,m,quality.standards())):
            return None
        return dict(manifest=m,approval=dict(actor_id='quality-policy:'+quality.POLICY,
                    preparation_hash=row['preparation_hash'],visual_approved=True,pixel_exact=True),
                    production=check,variant_ids=[str(unit['shopify_variant_id'])])

    def index(self):
        if not quality.enabled():
            return {}
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT c.assessment,p.manifest,c.product_gid
                FROM auto_edition_quality_checks c
                JOIN auto_edition_preparations p ON p.hash=c.preparation_hash
                JOIN auto_edition_onboarding q ON q.product_gid=c.product_gid AND q.preparation_hash=c.preparation_hash
                JOIN product_psd_mappings m ON m.shopify_product_gid=c.product_gid
                JOIN edition_products ep ON ep.shopify_product_gid=c.product_gid
                WHERE c.status='Production Ready' AND c.next_check_at>now()
                AND q.status IN ('Blocked','Cloud Ready') AND q.source=p.manifest->'source'
                AND m.dropbox_file_id=p.manifest->'source'->>'file_id'
                AND ep.edition_total=(p.manifest->>'edition_total')::int
                AND NOT EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=c.product_gid
                    AND l.preparation_hash<>p.hash)""")
            rows=cur.fetchall()
        records=quality.standards();result={}
        for row in rows:
            if quality.current_certificate(row['assessment'],row['manifest'],records):
                for variant in row['assessment']['evidence']['scope']:
                    result[(row['product_gid'],str(variant).removeprefix('gid://shopify/ProductVariant/'))]=row['assessment']['preparation_hash']
        return result
