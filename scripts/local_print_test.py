"""Bounded owner-run Photoshop test; no network, pairing server or production writes."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import print_specifications
from scripts.verify_psd_number_pixels import compare,region


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(4*1024*1024),b''):sha.update(block)
    return sha.hexdigest()


def verified_unit(record, evidence):
    """Retained read-only proof only, never a substitute for fresh production authorisation."""
    unit=record.get('order_unit') or {}
    keys=('shopify_order_id','shopify_line_item_id','allocation_index','allocation_id','edition_number','edition_total')
    if unit.get('source')!='read_only_supabase' or any(unit.get(k) is None for k in keys):raise ValueError('Exact assigned Supabase unit evidence is required')
    selected=[u for u in evidence['target'] if u.get('shopify_product_gid')==record['product_gid'] and all(u.get(k)==unit[k] for k in keys)]
    if len(selected)!=1:raise ValueError('Exact order-line unit allocation evidence mismatch')
    target=selected[0]
    if any(target.get(k) is not True or unit.get(k) is not True for k in ('allocation_valid','identity_enforced')) or target.get('invalidated_at') or target.get('cancelled_at'):raise ValueError('Confirmed valid/enforced unit evidence is required')
    text=re.fullmatch(r'\s*(?:#|(?:LIMITED\s+)?EDITION\s*)?(\d+)\s*(?:/|of)\s*(\d+)\s*',record['after_text'],flags=re.I)
    if not text or [int(text[1]),int(text[2])]!=[unit['edition_number'],unit['edition_total']]:raise ValueError('Native number replacement does not match the assigned unit edition')
    for key in ('dropbox_file_id','dropbox_revision'):
        if unit.get(key)!=record.get(key):raise ValueError('Unit/source PSD identity mismatch')
    return target


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--proof',type=Path,required=True);p.add_argument('--product',required=True);p.add_argument('--size',choices=['L','XL'],default='XL');p.add_argument('--owner',required=True)
    p.add_argument('--supplier-master',action='store_true',help='One approved XL master per exact unit; no inferred specifications, crop or padding')
    p.add_argument('--retry-local',action='store_true',help='Explicitly retain and retry a failed local test, maximum three attempts')
    a=p.parse_args();proof=a.proof.resolve()
    if not proof.is_relative_to(ROOT/'output'):raise ValueError('Only retained local proof reports accepted')
    data=json.loads(proof.read_text(encoding='utf-8-sig'));rows=[r for r in data['documents'] if r['product_gid']==a.product and r.get('structural_verification') and r.get('lossless_pixels',{}).get('ok')]
    if len(rows)!=1:raise ValueError('Exactly one verified selected native proof required')
    record=rows[0];inputs={k:Path(record[k]).resolve() for k in ['psd','before_png','after_png']}
    variant_identity=None
    if record.get('order_unit'):
        evidence=json.loads((proof.parent/'supabase-read-only-evidence.json').read_text(encoding='utf-8'))
        selected=[u for u in evidence['target'] if u['shopify_line_item_id']==record['order_unit']['shopify_line_item_id'] and u['shopify_product_gid']==a.product]
        if a.supplier_master:selected=[verified_unit(record,evidence)]
        if len(selected)!=1 or selected[0]['edition_number']!=record['order_unit']['edition_number']:raise ValueError('Exact assigned variant evidence mismatch')
        match=re.match(r'^(Black|Oak|White|Unframed)\s*/\s*(XL|L|M|S)\b',selected[0]['variant_title'])
        if not match or (not a.supplier_master and match[2]!=a.size):raise ValueError('Requested print size differs from selected real order variant')
        variant_identity=selected[0]['shopify_variant_id']
        if a.supplier_master and (selected[0].get('allocation_valid') is not True or selected[0].get('identity_enforced') is not True or selected[0].get('invalidated_at')):raise ValueError('Confirmed valid/enforced unit evidence is required; never use a product next number')
    if any(not path.is_relative_to(ROOT/'output') or 'NON_PRODUCTION' not in path.name for path in inputs.values()):raise ValueError('Only retained disposable proof artifacts accepted')
    native_region=record['lossless_pixels']['allowed_region']
    if not compare(inputs['before_png'],inputs['after_png'],native_region)['ok']:raise ValueError('Native number-region comparison failed')
    plan=None
    if a.supplier_master:
        if not record.get('order_unit') or record['order_unit'].get('source')!='read_only_supabase':raise ValueError('Exact Supabase allocation proof is required for a supplier master')
        mapped=json.loads((ROOT/'output/psd_std/standardisation-index.json').read_text(encoding='utf-8'))['records'][a.product]
        if mapped.get('dropbox_file_id')!=record['dropbox_file_id'] or mapped.get('dropbox_revision')!=record['dropbox_revision'] or not mapped.get('content_hash'):raise ValueError('Exact verified mapped source revision/hash is required')
        if record['order_unit'].get('content_hash')!=mapped['content_hash']:raise ValueError('Assigned unit PSD content hash differs from the verified mapping')
        plan=print_specifications.master_plan(selected[0]['variant_title'],record.get('approved_layout'))
        if plan['status']!='Shared master':raise ValueError(plan['reason'])
        layout=record['approved_layout']
        if layout['dimensions']!=[record['width'],record['height']]:raise ValueError('Approved layout belongs to different source dimensions')
        b=layout['protected_bounds']
        for bounds in (record['number_bounds_before'],record['number_bounds_after']):
            if bounds[0]<b[0] or bounds[1]<b[1] or bounds[2]>b[2] or bounds[3]>b[3]:raise ValueError('The edition badge is outside the approved protected artwork bounds')
        a.size='XL';spec=plan['master']
    else:
        spec=print_specifications.registry()['storefront_references'][a.size]
    identity=hashlib.sha256(json.dumps({'product':a.product,'unit':record.get('order_unit'),'edition':record['after_text'],'revision':record['dropbox_revision'],'file':record['dropbox_file_id'],'size':a.size,'spec':spec,'processor':digest(ROOT/'scripts/photoshop/upscale_print_test.jsx'),'inputs':{k:digest(v) for k,v in inputs.items()}},sort_keys=True).encode()).hexdigest()
    if plan:
        identity=hashlib.sha256(json.dumps({'strategy':'largest_approved_size_first','proof_identity':identity,'variant':variant_identity,'content_hash':mapped['content_hash'],'layout':record['approved_layout']},sort_keys=True).encode()).hexdigest()
    cache=Path.home()/'Documents/SportsCavePrintJobs';cache.mkdir(parents=True,exist_ok=True)
    job=cache/identity;job.mkdir(exist_ok=True)
    lock=cache/'processor.lock';lease=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(lease)
    created=False
    release_lease=True
    try:
        manifest=job/'job.json'
        attempt=1
        if manifest.exists():
            prior=json.loads(manifest.read_text(encoding='utf-8'));attempt=prior.get('attempt',1)+1
            if not a.retry_local or prior.get('status')!='Blocked' or prior.get('owner')!=a.owner or attempt>3:raise ValueError('Duplicate/replay job blocked; explicit bounded failed-job retry required')
            (job/f'failed-attempt-{attempt-1}.json').write_bytes(manifest.read_bytes())
        manifest.write_text(json.dumps({'identity':identity,'owner':a.owner,'status':'Generating','print_ready':False,'attempt':attempt}),encoding='utf-8')
        created=True
        width,height=spec['pixel_dimensions'] if plan else spec['pixels_300ppi'];prefix=job/f'{a.size}-NON_PRODUCTION-{"SUPPLIER-MASTER" if plan else "STOREFRONT-TEST"}-ATTEMPT-{attempt}'
        if (proof.parent/'target-inspection.json').exists():
            candidates=json.loads((proof.parent/'target-inspection.json').read_text(encoding='utf-8-sig'))['documents'][0]['detection']['candidates']
        else:
            candidates=json.loads((ROOT/'output/psd_std/standardisation-index.json').read_text(encoding='utf-8'))['records'][a.product]['detection']['candidates']
        if len(candidates)!=1 or candidates[0].get('smart_object_chain'):raise ValueError('Exactly one proven root target identity required')
        layer=candidates[0]['layer_id']
        req={'local_test':True,'supplier_master':bool(plan),'inspection_script':str(ROOT/'scripts/photoshop/inspect_psd_editions.jsx'),'input_root':str(ROOT/'output'),'output_root':str(job),'report_path':str(job/'native-report.json'),'entries':[{'psd':str(inputs['psd']),'before_png':str(inputs['before_png']),'after_png':str(inputs['after_png']),'layer_id':layer,'expected_text':record['after_text'],'width':width,'height':height,'prefix':str(prefix)}]}
        (job/'request.json').write_text(json.dumps(req),encoding='utf-8');start=time.perf_counter()
        if plan:
            req['entries'][0]['colour_profile']=spec['colour']['profile']
            (job/'request.json').write_text(json.dumps(req),encoding='utf-8')
        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/photoshop_dispatch.py'),str(ROOT/'scripts/photoshop/upscale_print_test.jsx'),str(job/'request.json')],check=True,timeout=900)
        native=json.loads((job/'native-report.json').read_text(encoding='utf-8-sig'));after=native['documents'][1];scale=after['scale'];pad=after['padding'];before_bounds=record['number_bounds_before'];after_bounds=record['number_bounds_after'];transform=lambda bounds:[bounds[0]*scale+pad[0],bounds[1]*scale+pad[1],bounds[2]*scale+pad[0],bounds[3]*scale+pad[1]]
        roi=region(transform(before_bounds),transform(after_bounds),(width,height),padding=80)
        fidelity=compare(str(prefix)+'-BEFORE.png',str(prefix)+'-AFTER.png',roi)
        jpg=Path(str(prefix)+'-AFTER.jpg');result={'identity':identity,'owner':a.owner,'status':'Review' if fidelity['ok'] else 'Blocked','validated':fidelity['ok'],'print_ready':False,'quality_approved':False,'jpg':str(jpg),'jpg_sha256':digest(jpg),'bytes':jpg.stat().st_size,'dimensions':[width,height],'native':native,'number_region_fidelity':fidelity,'seconds':time.perf_counter()-start,'source_proof':str(proof),'edition':record['after_text'],'reason':'Provisional storefront test; supplier specifications and print quality unverified. Padding is explicit, not supplier-approved bleed.'}
        if plan:
            result.update(strategy='largest_approved_size_first',master_size='XL',shared_sizes=plan['shared_sizes'],compatibility=plan['sizes'],reason='Verified supplier XL geometry; quality approval and authenticated production transport still required. No crop/stretch/padding.')
        manifest.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    except (Exception, KeyboardInterrupt) as error:
        if isinstance(error,(KeyboardInterrupt,subprocess.TimeoutExpired)):
            release_lease=False # Photoshop may still be executing after a caller disconnect; never start a duplicate.
        if created and (job/'job.json').exists():
            prior=json.loads((job/'job.json').read_text());prior.update(status='Blocked',reason='Local processor or validation failed; no download authorised',requires_idle_confirmation=not release_lease);(job/'job.json').write_text(json.dumps(prior),encoding='utf-8')
        raise
    finally:
        if release_lease:lock.unlink()


if __name__=='__main__':main()
