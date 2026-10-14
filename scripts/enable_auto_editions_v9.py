"""Verify and opt in only the seven existing Kostecki/Hazelwood TEST allocations.

Run on the existing authenticated cloud service. Default is read-only. This does
not allocate, render, change Shopify/fulfilment, or modify any source asset.
"""
import argparse
import hashlib
import json
import auto_editions_runtime as runtime
from auto_editions_cloud import confirmed_job

PRODUCT='gid://shopify/Product/15411172376883'
MASTER='5329ce4506f019b94465abbe8bf2248235300f4b20cd15b6c6e24e635c195986'
TARGETS={
    652:('SC3283','18941363421491','50791938720051','67647501992243',1,1),
    653:('SC3283','18941363421491','50791938720051','67647501992243',2,2),
    654:('SC3284','18941430858035','50792075100467','67647502418227',1,3),
    658:('SC3285','18941534765363','50792271577395','67647502090547',1,4),
    659:('SC3287','18942713102643','50794527129907','67647502385459',1,5),
    660:('SC3288','18942968037683','50795013472563','67647501992243',1,6),
    661:('SC3289','18943122932019','50795281776947','67647501992243',1,7),
}

def matches(unit, expected):
    order,oid,line,variant,ordinal,number=expected
    return (unit['shopify_product_gid']==PRODUCT
        and unit['shopify_order_name'].lstrip('#')==order
        and unit['shopify_order_id']=='gid://shopify/Order/'+oid
        and str(unit['shopify_line_item_id'])==line
        and str(unit['shopify_variant_id'])=='gid://shopify/ProductVariant/'+variant
        and unit['unit_ordinal']==ordinal and unit['allocation_index']==ordinal
        and unit['edition_number']==number and unit['edition_total']==100)

def protected_digest(reg):
    with reg.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT * FROM public.product_psd_mappings ORDER BY shopify_product_gid')
        mappings=[dict(x) for x in cur.fetchall()]
        cur.execute('SELECT * FROM public.edition_orders ORDER BY id')
        allocations=[dict(x) for x in cur.fetchall()]
    return hashlib.sha256(json.dumps([mappings,allocations],sort_keys=True,default=str).encode()).hexdigest()

def run(apply=False,actor=''):
    reg,jobs=runtime.stores()
    before=protected_digest(reg)
    current,assets=runtime.job_for(659)
    if current['preparation_hash']!=MASTER:raise ValueError('SC3287 master changed; stop and review.')
    manifest=current['manifest']
    if manifest['dimensions']!=[11340,8016]:raise ValueError('The verified master dimensions changed.')
    # The approved manifest and its immutable assets are reused byte for byte.
    rows=[];groups={}
    for allocation,expected in TARGETS.items():
        unit,mapping=reg.unit(allocation)
        if not matches(unit,expected):raise ValueError(f'Allocation {allocation} does not match the verified rollout.')
        metadata=assets.integration.psd_open_metadata(assets.token,mapping['dropbox_file_id'],include_preview=False)
        preparation=dict(manifest=manifest,approval=reg.for_unit(reg.unit(659)[0])['approval'],variant_ids=[unit['shopify_variant_id']])
        job=confirmed_job(unit,mapping,metadata,preparation)
        rows.append(dict(allocation=allocation,order=unit['shopify_order_name'],line=unit['shopify_line_item_id'],
            unit=unit['unit_ordinal'],edition=unit['edition_number'],variant=unit['variant_title'],job_id=job['id']))
        groups.setdefault(unit['shopify_variant_id'],[]).append(unit)
    old=jobs.read(current['id'])
    if not old or old['status']!='Ready':raise ValueError('Verified SC3287 archive is not ready.')
    assets.verify_output(old['result']['output'])
    if apply:
        if not actor:raise ValueError('An explicit operator identity is required.')
        for variant,units in groups.items():
            if any(u['id']==659 for u in units):continue
            with reg.connect() as conn,conn.cursor() as cur:
                cur.execute('SELECT preparation_hash,approval FROM public.auto_edition_layouts WHERE product_gid=%s AND variant_id=%s',(PRODUCT,variant))
                prior=cur.fetchone()
            ids=sorted(u['id'] for u in units)
            if prior:
                if prior['preparation_hash']==MASTER and prior['approval'].get('allocation_ids')==ids:continue
                raise ValueError('A newer or differently scoped variant approval exists; stop and review.')
            reg.approve(MASTER,units[0],actor,allocation_ids=ids)
        for allocation in TARGETS:runtime.job_for(allocation)
    after=protected_digest(reg)
    if before!=after:raise ValueError('Protected records changed during verification; investigate before continuing.')
    return dict(applied=apply,master=MASTER,targets=rows,protected_digest=after,sc3287_output=old['result']['output'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--actor',default='')
    a=p.parse_args();print(json.dumps(run(a.apply,a.actor),indent=2,default=str))
