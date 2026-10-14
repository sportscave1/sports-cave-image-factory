"""Additive setup records. Existing mappings and allocations are read-only."""
import json
import auto_editions as ae
from auto_editions_cloud import PreparationBlocked


class Preparations:
    def __init__(self,connect):self.connect=connect

    def unit(self,allocation_id):
        if type(allocation_id) is not int or allocation_id<=0:raise ValueError('Select an allocated order unit.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM public.edition_orders WHERE id=%s',(allocation_id,))
            row=cur.fetchone()
            if not row:raise PreparationBlocked('The allocation is unavailable.')
            unit=dict(row)
            cur.execute('SELECT * FROM public.product_psd_mappings WHERE shopify_product_gid=%s',(unit['shopify_product_gid'],))
            row=cur.fetchone()
            mapping={**dict(row), 'verified':True,'state':'Linked'} if row else None
        return unit,mapping

    def read(self,digest):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM public.auto_edition_preparations WHERE hash=%s',(digest,))
            row=cur.fetchone()
            return dict(row) if row else None

    def for_unit(self,unit):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''SELECT p.manifest,l.approval,l.variant_id FROM public.auto_edition_layouts l
                JOIN public.auto_edition_preparations p ON p.hash=l.preparation_hash
                WHERE l.product_gid=%s AND l.variant_id=%s''',
                (unit['shopify_product_gid'],str(unit.get('shopify_variant_id') or '')))
            row=cur.fetchone()
            if not row:raise PreparationBlocked('This variant needs Auto Editions setup.')
            return dict(manifest=row['manifest'],approval=row['approval'],variant_ids=[row['variant_id']])

    def save(self,manifest,proofs,receipts,actor):
        ae.validate_manifest(manifest)
        digest=ae.fingerprint(manifest)
        if not actor:raise PermissionError('Administrator identity required.')
        if (not proofs or any(p.get('preparation_hash')!=digest for p in proofs)
                or not any(p.get('outside_number_exact') is True for p in proofs)
                or not any(p.get('pixel_exact') is True for p in proofs)):
            raise PreparationBlocked('Original and Photoshop pixel proofs are required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('''INSERT INTO public.auto_edition_preparations(hash,manifest,proofs,receipts,created_by)
                VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,%s) ON CONFLICT(hash) DO NOTHING''',
                (digest,json.dumps(manifest),json.dumps(proofs),json.dumps(receipts),actor))
            cur.execute('''INSERT INTO public.auto_edition_setup_audit(actor_id,preparation_hash,event,detail)
                VALUES(%s,%s,'prepared','{}'::jsonb)''',(actor,digest))
        return digest

    def approve(self,digest,unit,actor,expected=''):
        row=self.read(digest)
        if not row or row['manifest']['source']['product_gid']!=unit['shopify_product_gid']:
            raise PreparationBlocked('Preparation does not belong to this product.')
        approval=dict(actor_id=actor,preparation_hash=digest,visual_approved=True,pixel_exact=True,test_only=True)
        if ae.status(row['manifest'],approval)!='TEST READY':raise PreparationBlocked('Preparation is invalid.')
        variant=str(unit.get('shopify_variant_id') or '')
        if not actor or not variant:raise PreparationBlocked('Exact variant and administrator are required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('LOCK TABLE public.auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT preparation_hash FROM public.auto_edition_layouts WHERE product_gid=%s AND variant_id=%s',
                        (unit['shopify_product_gid'],variant))
            current=cur.fetchone()
            if (current['preparation_hash'] if current else '')!=expected:
                raise PreparationBlocked('Layout changed. Refresh before approving a replacement.')
            cur.execute('''INSERT INTO public.auto_edition_layouts(product_gid,variant_id,preparation_hash,approval)
                VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT(product_gid,variant_id) DO UPDATE
                SET preparation_hash=excluded.preparation_hash,approval=excluded.approval,updated_at=now()''',
                (unit['shopify_product_gid'],variant,digest,json.dumps(approval)))
            cur.execute('''INSERT INTO public.auto_edition_setup_audit(actor_id,preparation_hash,event,detail)
                VALUES(%s,%s,'approved_test_layout',%s::jsonb)''',
                (actor,digest,json.dumps(dict(variant_id=variant,previous=expected))))
        return approval

    def index(self):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT product_gid,variant_id FROM public.auto_edition_layouts')
            return {(r['product_gid'],r['variant_id']) for r in cur.fetchall()}
