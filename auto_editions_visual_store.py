"""Bounded reconciliation using existing preparations/layouts and append-only audit.

No source, allocation, certificate, mapping or asset writes. No new worker/schema.
"""
import json,shutil
from pathlib import Path
import auto_editions as ae
import auto_editions_visual as visual

EVENT='automatic_visual_assessment'

def shopify_identity(spec):
    # Reuse the existing canonical authenticated read; no new GraphQL operation.
    from shopify_sync import fetch_product_by_shopify_id
    product=fetch_product_by_shopify_id(spec['product_gid'])
    matches=[i for i in product.get('images',[]) if i.get('id')==spec['media_id']]
    if len(matches)!=1:raise ValueError('Reviewed Shopify media is missing or ambiguous.')
    return dict(product_gid=product['shopify_product_id'],product_revision=product['remote_updated_at'],
                media_id=matches[0]['id'],url=matches[0]['url'])

class Providers:
    def __init__(self,assets):self.assets=assets
    def metadata(self,fid):return self.assets.integration.psd_open_metadata(self.assets.token,fid,include_preview=False)
    def reference(self,spec,destination):
        metadata,response=self.assets.integration.get_file_response(self.assets.token,spec['file_id'])
        try:
            size=metadata.get('size')
            if (metadata.get('id')!=spec['file_id'] or metadata.get('rev')!=spec['revision']
                    or type(size) is not int or not 0<size<=160*1024*1024):raise ValueError('Approved reference receipt changed.')
            length=0
            with Path(destination).open('xb') as out:
                for block in response.iter_content(chunk_size=1024*1024):
                    length+=len(block)
                    if length>size:raise ValueError('Approved reference transfer exceeds bounds.')
                    out.write(block)
            if length!=size or ae.file_hash(destination,dropbox=True)!=metadata.get('content_hash'):raise ValueError('Approved reference transfer changed.')
        finally:response.close()
    def shopify(self,spec,destination):
        from urllib.parse import urlsplit
        import requests
        identity=shopify_identity(spec);url=identity.pop('url');parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname!='cdn.shopify.com' or parsed.port not in (None,443) or parsed.username:
            raise ValueError('Reviewed Shopify image location is unsupported.')
        with requests.get(url,stream=True,timeout=(8,30),allow_redirects=False) as response:
            if response.status_code!=200:raise ValueError('Shopify image is unavailable.')
            length=0
            with Path(destination).open('xb') as out:
                for block in response.iter_content(chunk_size=256*1024):
                    length+=len(block)
                    if length>16*1024*1024:raise ValueError('Shopify image exceeds comparison bounds.')
                    out.write(block)
        return identity
    def shopify_fence(self,spec):
        live=shopify_identity(spec)
        return all(live[k]==spec[k] for k in ('product_gid','product_revision','media_id'))

class Visual:
    def __init__(self,connect):self.connect=connect
    def run_one(self,assets,*,pid=None,providers=None,local_root=None):
        if not visual.enabled():return False
        records=visual.policies();catalogue_hash=ae.fingerprint(records);provider=providers or Providers(assets)
        from worker_health import control
        with self.connect() as conn,conn.cursor() as cur:
            if control(cur)['paused']:return False
            cur.execute('SELECT pg_try_advisory_xact_lock(1616002) AS locked')
            if not cur.fetchone()['locked']:return False
            cur.execute("""SELECT p.*,to_jsonb(q) AS checkpoint,to_jsonb(m) AS mapping,ep.edition_total AS current_total,
                EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=q.product_gid AND l.preparation_hash<>p.hash) AS conflicting
                FROM auto_edition_onboarding q JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
                JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                JOIN edition_products ep ON ep.shopify_product_gid=q.product_gid
                LEFT JOIN LATERAL(SELECT a.detail,a.created_at FROM auto_edition_setup_audit a
                    WHERE a.preparation_hash=p.hash AND a.event=%s ORDER BY a.id DESC LIMIT 1) v ON true
                WHERE q.status IN ('Blocked','Cloud Ready') AND (%s::text IS NULL OR q.product_gid=%s)
                AND COALESCE(to_jsonb(q)->'replacement'->>'stage','') NOT IN ('Discovering','Queued','Preparing')
                AND NOT EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=q.product_gid AND l.preparation_hash=p.hash
                    AND (l.approval->>'visual_approved'='true' OR l.approval->>'method'='product-upload-technical-v1'))
                AND (v.created_at IS NULL OR v.created_at<now()-interval '24 hours' OR v.detail->>'catalogue_hash'<>%s)
                ORDER BY v.created_at NULLS FIRST,q.priority DESC,q.updated_at LIMIT 1""",(EVENT,pid,pid,catalogue_hash))
            row=cur.fetchone()
            if not row:return False
            row=dict(row);checkpoint=dict(row['checkpoint'],current_total=row['current_total'],conflicting_approval=row['conflicting'])
            m=row['manifest'];policy=visual.policy_for(row,records)
            from auto_editions_quality import result
            if not policy:check=result('Needs Review','Visual policy awaiting approval: exact trusted reference evidence is insufficient.',m)
            else:
                try:
                    source=provider.metadata(m['source']['file_id'])
                    def fetch(digest,asset,destination):
                        if local_root is None:return assets.fetch(digest,asset,destination)
                        # Fresh cloud receipts are independently checked by the
                        # shared validator before trusting these imported bytes.
                        shutil.copyfile(ae.asset_path(local_root,asset),destination)
                    check=visual.assess(row,row['mapping'],checkpoint,source,provider.metadata,fetch,provider.reference,provider.shopify,records)
                    if check['status']=='Auto Approved' and (ae.source_identity(m['source']['product_gid'],provider.metadata(m['source']['file_id']))!=m['source'] or not provider.shopify_fence(policy['shopify'])):
                        check=result('Needs Review','Source or Shopify identity changed during visual validation.',m)
                except Exception:check=result('Failed','Visual source, reference or provider verification is unavailable.',m)
            # Same final lock order as V15/V16; no network calls under row locks.
            cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',(checkpoint['product_gid'],));product=cur.fetchone()
            cur.execute('SELECT to_jsonb(m) AS value FROM product_psd_mappings m WHERE shopify_product_gid=%s FOR SHARE',(checkpoint['product_gid'],));mapping=cur.fetchone()
            cur.execute('SELECT to_jsonb(q) AS value FROM auto_edition_onboarding q WHERE product_gid=%s FOR UPDATE',(checkpoint['product_gid'],));current=cur.fetchone()
            cur.execute('LOCK TABLE auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT preparation_hash,approval FROM auto_edition_layouts WHERE product_gid=%s',(checkpoint['product_gid'],));layouts=cur.fetchall()
            if (not current or not mapping or not product or product['edition_total']!=row['current_total']
                    or current['value']!=row['checkpoint'] or mapping['value']!=row['mapping']
                    or any(l['preparation_hash']!=row['hash'] for l in layouts)):
                check=result('Needs Review','Mapping, edition limit, approval or preparation changed during visual validation.',m)
            if not visual.enabled() or visual.policies()!=records:return False
            # Never replace a human review or a different preparation's history.
            writable=bool(current and current['value']==row['checkpoint'] and not any(l['preparation_hash']!=row['hash'] or l['approval'].get('visual_approved') is True for l in layouts))
            if check['status']=='Auto Approved' and not writable:
                check=result('Needs Review','Approval changed during visual validation; existing review retained.',m)
            if check['status']=='Auto Approved' and writable:
                approval=visual.approval(check,m,records)
                cur.execute("""INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval)
                    VALUES(%s,'*',%s,%s::jsonb) ON CONFLICT(product_gid,variant_id) DO UPDATE
                    SET approval=excluded.approval,updated_at=now() WHERE auto_edition_layouts.preparation_hash=excluded.preparation_hash
                    AND auto_edition_layouts.approval->>'method'=%s""",(checkpoint['product_gid'],row['hash'],json.dumps(approval),visual.POLICY))
                cur.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',reason=%s,updated_at=now() WHERE product_gid=%s",(check['reason'],checkpoint['product_gid']))
            elif writable and any(l['approval'].get('method')==visual.POLICY for l in layouts):
                # Keep the exact historical layout, revoke its current automated
                # eligibility after a failed recheck; append-only audit survives.
                cur.execute("UPDATE auto_edition_layouts SET approval=jsonb_set(approval,'{assessment}',%s::jsonb),updated_at=now() WHERE product_gid=%s AND preparation_hash=%s AND approval->>'method'=%s",(json.dumps(check),checkpoint['product_gid'],row['hash'],visual.POLICY))
                cur.execute("UPDATE auto_edition_onboarding SET status='Blocked',reason=%s,updated_at=now() WHERE product_gid=%s",(check['reason'],checkpoint['product_gid']))
            cur.execute("INSERT INTO auto_edition_setup_audit(actor_id,preparation_hash,event,detail) VALUES(%s,%s,%s,%s::jsonb)",
                        ('automatic:'+visual.POLICY,row['hash'],EVENT,json.dumps(dict(assessment=check,catalogue_hash=catalogue_hash))))
            from auto_editions_onboarding_store import Queue
            Queue.audit(cur,checkpoint['product_gid'],'automatic:'+visual.POLICY,'automatic_visual_assessment',dict(hash=row['hash'],status=check['status'],reason=check['reason'],stage='Review',policy_hash=check.get('policy_hash'),evidence_hash=ae.fingerprint(check)))
        return True
