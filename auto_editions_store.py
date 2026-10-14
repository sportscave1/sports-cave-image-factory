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

    def layouts(self,product=None):
        """One authoritative policy for the Orders listing and generation request.

        V11 Cloud Ready approves a reusable TEST product composition. Legacy
        rollout lists are not perpetual order allowlists once that same source
        and sole master are Cloud Ready. Multiple distinct masters never infer
        compatibility for an unapproved variant.
        """
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT m.shopify_product_gid AS product_gid,m.dropbox_file_id,
                l.variant_id,l.preparation_hash,l.approval,p.manifest,
                q.status AS preparation_status,q.source AS current_source,
                q.preparation_hash AS current_hash
                FROM product_psd_mappings m
                LEFT JOIN auto_edition_layouts l ON l.product_gid=m.shopify_product_gid
                LEFT JOIN auto_edition_preparations p ON p.hash=l.preparation_hash
                LEFT JOIN auto_edition_onboarding q ON q.product_gid=m.shopify_product_gid
                WHERE (%s::text IS NULL OR m.shopify_product_gid=%s)""",(product,product))
            rows=cur.fetchall()
        return resolve_layouts(rows)

    def for_unit(self,unit):
        index=self.layouts(unit['shopify_product_gid'])
        key=(unit['shopify_product_gid'],variant_id(unit.get('shopify_variant_id')))
        row=index.get(key) or index.get((key[0],'*'))
        if not row:
            raise PreparationBlocked(index.reasons.get(key[0],'This variant needs an approved compatible layout.'))
        allowed=row['approval'].get('allocation_ids')
        if allowed is not None and unit.get('id') not in allowed:
            raise PreparationBlocked('This unit is outside the approved TEST rollout; product review is required.')
        return dict(manifest=row['manifest'],approval=row['approval'],
                    variant_ids=[str(unit.get('shopify_variant_id') or '')])

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

    def approve(self,digest,unit,actor,expected='',allocation_ids=None):
        row=self.read(digest)
        if not row or row['manifest']['source']['product_gid']!=unit['shopify_product_gid']:
            raise PreparationBlocked('Preparation does not belong to this product.')
        approval=dict(actor_id=actor,preparation_hash=digest,visual_approved=True,pixel_exact=True,test_only=True)
        if allocation_ids is not None:
            if not allocation_ids or any(type(x) is not int or x<=0 for x in allocation_ids) or unit['id'] not in allocation_ids:
                raise PreparationBlocked('Exact verified allocation IDs are required.')
            approval['allocation_ids']=sorted(set(allocation_ids))
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
        layouts=self.layouts()
        result=LayoutIndex({key:row['approval'].get('allocation_ids') for key,row in layouts.items()})
        result.reasons=layouts.reasons
        result.hashes={key:row['preparation_hash'] for key,row in layouts.items()}
        return result


def variant_id(value):
    return str(value or '').removeprefix('gid://shopify/ProductVariant/')


class LayoutIndex(dict):
    def __init__(self,*args):
        super().__init__(*args)
        self.reasons={}
        self.hashes={}


def resolve_layouts(rows):
    """No writes, order IDs, edition ranges, title matching or cached mappings."""
    result=LayoutIndex();products={}
    for row in rows:products.setdefault(row['product_gid'],[]).append(row)
    for product,group in products.items():
        first=group[0]
        state=first.get('preparation_status')
        result.reasons[product]={
            'Preparing':'Preparing master', 'Awaiting preparation':'Awaiting preparation',
            'Needs PSD Repair':'Needs PSD Repair', 'Blocked':'Preparation review required',
            'Cloud Ready':'Needs compatible layout',
        }.get(state,'Mapped; preparation required')
        approved=[]
        for row in group:
            manifest=row.get('manifest')
            if not manifest or ae.status(manifest,row.get('approval'))!='TEST READY':continue
            source=manifest['source']
            if source['product_gid']!=product or source['file_id']!=row['dropbox_file_id']:continue
            if row.get('current_source') and row['current_source']!=source:continue
            approved.append(row)
        # Do not turn a distinct variant master into a product-wide fallback.
        hashes={row['preparation_hash'] for row in group if row.get('preparation_hash')}
        if state=='Cloud Ready' and first.get('current_hash') not in hashes:
            approved=[]
        common=next((row for row in approved if state=='Cloud Ready'
            and row['preparation_hash']==first.get('current_hash')
            and row['manifest']['source']==first.get('current_source')
            and row['approval'].get('test_only') is True
            and hashes=={row['preparation_hash']}),None)
        for row in approved:
            value=dict(row)
            if common:
                value['approval']={k:v for k,v in row['approval'].items() if k!='allocation_ids'}
            result[(product,variant_id(row['variant_id']))]=value
        if common:
            value=dict(common,approval={k:v for k,v in common['approval'].items() if k!='allocation_ids'})
            result[(product,'*')]=value
    return result
