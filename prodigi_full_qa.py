"""One background QA pass, pinned to an archived numbered file and exact draft.

This approves this draft's print evidence; it never rewrites Auto Editions TEST
history, creates an order, pays, submits, or manufactures a human approval.
"""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,io,math,os,tempfile
import prodigi_preparation as prep

POLICY='prodigi-draft-print-qa-v1'


def enabled():return os.getenv('SPORTS_CAVE_PRODIGI_FULL_QA_ENABLED','true').lower()=='true'
def live_enabled():return enabled() and os.getenv('SPORTS_CAVE_PRODIGI_FULL_QA_ACCEPTED','').lower()=='true'


def print_area(catalogue,dimensions):
    areas=[a for a in catalogue.get('printAreas',[]) if a.get('name')=='default']
    if len(areas)!=1:raise ValueError('The supplier has no unique default print area.')
    area=areas[0];dims=catalogue.get('dimensions') or {}
    width=area.get('widthMm') or (dims.get('width') or {}).get('mm')
    height=area.get('heightMm') or (dims.get('height') or {}).get('mm')
    if not all(type(n) in (int,float) and math.isfinite(n) and n>0 for n in (width,height)):
        raise ValueError('Supplier physical print dimensions are missing.')
    physical=sorted([width,height],reverse=dimensions[0]>dimensions[1])
    return physical,max(300,area.get('recommendedDpi') or 300)


def validate_current_artwork(snapshot):
    """Send checks source identity only; print quality is evaluated after upload."""
    import auto_editions_runtime as runtime
    job,_=runtime.job_for(snapshot['allocation_id'])
    if job['id']!=snapshot['job_id']:raise prep.MissingJPG('Generate the current allocated edition from the updated master.')


def approve(snapshot,provider,asset_id):
    if snapshot.get('source_kind')=='framed_certificate':
        from certificate_frame_fulfilment import approve as approve_certificate
        return approve_certificate(snapshot,provider,asset_id)
    import auto_editions_runtime as runtime
    import auto_editions as ae
    from PIL import Image,ImageCms,JpegImagePlugin
    from prodigi_artwork import fetch
    job,_=runtime.job_for(snapshot['allocation_id'])
    if job['id']!=snapshot['job_id']:raise ValueError('The approved layout/source changed. Generate the current edition again.')
    registry,_=runtime.stores();preparation=registry.read(job['preparation_hash'])
    proofs=(preparation or {}).get('proofs') or []
    if (not any(p.get('outside_number_exact') is True for p in proofs) or
        not {1,snapshot['total']}<={p.get('number') for p in proofs if p.get('pixel_exact') is True}):
        raise ValueError('Independent original/numbered pixel proofs are incomplete.')
    manifest=job['manifest'];sku=snapshot['mapping']['prodigi_code'];catalogue=provider.catalogue(sku)
    if (catalogue.get('sku') or catalogue.get('id'))!=sku:raise ValueError('Supplier catalogue SKU differs.')
    physical,dpi=print_area(catalogue,snapshot['dimensions'])
    native=manifest['source_dimensions']
    ppi=[n*25.4/mm for n,mm in zip(native,physical)]
    blockers=[]
    if min(ppi)<dpi:blockers.append(f'Native source resolution is {min(ppi):.0f} PPI; supplier recommendation is {dpi} PPI. The enlarged export does not prove extra native detail.')
    if job['number']!=snapshot['number'] or job['total']!=snapshot['total']:
        raise ValueError('Allocated and rendered edition numbers differ.')
    with tempfile.TemporaryDirectory(prefix='sc-print-qa-') as folder:
        path=fetch(snapshot,folder)
        with Image.open(path) as image:
            # Generation already decoded and verified these checksum-pinned
            # bytes. Read encoded metadata without allocating the large canvas again.
            icc=image.info.get('icc_profile',b'')
            if (image.format!='JPEG' or image.mode!='RGB' or list(image.size)!=snapshot['dimensions'] or
                list(image.info.get('dpi',()))!=[300,300] or JpegImagePlugin.get_sampling(image)!=0 or
                not image.quantization or any(v!=1 for t in image.quantization.values() for v in t)):
                raise ValueError('JPEG encoding, colour mode, dimensions or quality differ from the generated print file.')
            icc_sha,colour_blocker=colour_evidence(icc)
            if colour_blocker:blockers.append(colour_blocker)
    validation=provider.validate_asset(asset_id,sku)
    if validation.get('valid') is not True or validation.get('status')!='valid' or validation.get('issues'):
        blockers.append('Supplier artwork validation reports a warning or error. Review the full print preview.')
    return dict(policy=POLICY,job_id=snapshot['job_id'],sha256=snapshot['output']['sha256'],sku=sku,
        dimensions=snapshot['dimensions'],number=snapshot['number'],total=snapshot['total'],
        source_ppi=ppi,required_ppi=dpi,physical_mm=physical,icc_sha256=icc_sha,
        layout_pixel_proofs_verified=True,number_verified=True,supplier_asset_validated=bool(validation.get('valid') is True and validation.get('status')=='valid' and not validation.get('issues')),
        print_ready=not blockers,blockers=blockers,checked_at=prep.now(),basis='Existing approved layout, original pixel proofs, exact archived encoding and supplier validation')


def colour_evidence(icc):
    from PIL import ImageCms
    if not icc:return None,'The JPG has no embedded colour profile; a verified colour policy is required.'
    try:ImageCms.ImageCmsProfile(io.BytesIO(icc))
    except Exception:return None,'The JPG colour profile is invalid; a verified colour policy is required.'
    return hashlib.sha256(icc).hexdigest(),None


def approval_matches(approval,snapshot):
    return evidence_matches(approval,snapshot) and approval.get('print_ready') is True


def evidence_matches(approval,snapshot):
    if snapshot.get('source_kind')=='framed_certificate':
        from certificate_frame_fulfilment import evidence_matches as certificate_matches
        return certificate_matches(approval,snapshot)
    return bool(approval and approval.get('policy')==POLICY and
        approval.get('job_id')==snapshot['job_id'] and approval.get('sha256')==snapshot['output']['sha256'] and
        approval.get('sku')==snapshot['mapping']['prodigi_code'] and approval.get('dimensions')==snapshot['dimensions'] and
        approval.get('number')==snapshot['number'] and approval.get('total')==snapshot['total'] and
        all(approval.get(k) is True for k in ('layout_pixel_proofs_verified','number_verified','supplier_asset_validated')))


def same_order(before,after):
    """Document attachment can only alter packingSlip and calculated quotes."""
    from prodigi_browser import business
    def pinned(o):
        v=business(o,'',after_save=True);v.pop('packingSlip',None)
        for item in v['items']:
            item.pop('unitPrice',None);item.pop('lineTotal',None)
            for asset in item.get('assets',[]):asset.pop('status',None)
        return v
    return pinned(before)==pinned(after)


def run(value,provider,resolver,persist):
    from prodigi_documents import create
    from prodigi_qa import evaluate
    from prodigi_browser import checked
    sandbox=value.get('environment')=='sandbox'
    if not enabled() or (not sandbox and not live_enabled()):raise ValueError('Automatic QA is paused; no supplier document was changed.')
    if not sandbox:
        from prodigi_dashboard_qa import enqueue
        return enqueue(value,provider,resolver,persist)
    snap,order,item=checked(value,provider,resolver,sandbox)
    receipt=value.get('browser') or {}
    if not receipt.get('verified') or not receipt.get('full_image_fit_verified'):
        raise ValueError('Verify the saved image before completing QA.')
    if len(order.get('items',[]))!=1 or item.get('quantity')!=1:
        raise ValueError('Automatic certificate packing slips currently require one numbered item per supplier order.')
    assets=item.get('assets') or []
    if len(assets)!=1 or prep.digest(assets[0].get('url'))!=value.get('url_hash'):
        raise ValueError('Saved supplier artwork changed; no document was attached.')
    approval=value.get('print_approval')
    if not evidence_matches(approval,snap):
        approval=approve(snap,provider,receipt['original_asset_id'])
        value['print_approval']=approval;persist(value)
    document=value.get('document') or create(value,snap)
    value['document']=document
    slip=order.get('packingSlip') or {};certificate=value.get('document_browser') or {}
    if not certificate.get('verified'):
        if slip.get('url') or certificate or value.get('document_write_intent'):
            raise ValueError('Packing-slip attachment requires review. Preserve the existing draft; no automatic retry.')
        value.update(document_before=deepcopy(order),status='Awaiting certificate browser',
            message='Waiting for Companion 1.7.19 to attach the exact certificate. Payment and Submit stay manual.')
        persist(value);return value
    if certificate.get('sha256')!=document['output']['sha256'] or slip.get('url')!=certificate.get('supplier_url'):
        raise ValueError('Verified supplier certificate changed; review this draft.')
    _,latest,current=checked(value,provider,resolver,sandbox)
    if not same_order(value.get('document_before') or order,latest):
        raise ValueError('Supplier order changed while attaching the certificate. Review this exact draft.')
    evidence=deepcopy(snap);evidence['certificate_url']=certificate['supplier_url'];evidence['draft_print_approval']=approval
    evidence['draft_certificate_verified']=True
    evidence['draft_full_fit_verified']=receipt['full_image_fit_verified']
    qa=evaluate(evidence,latest,current,value['url_hash'])
    qa['blockers']=[*approval.get('blockers',[]),*qa['blockers']]
    qa.update(checked_at=prep.now(),companion_source_sha256_verified=True,supplier_asset_identity_verified=True,supplier_full_image_fit_verified=True,
        supplier_original_bytes_verified=receipt.get('supplier_original_bytes_verified',False),production_approval_basis=approval['basis'])
    pending=(latest.get('packingSlip') or {}).get('url')==certificate['supplier_url'] and (latest.get('packingSlip') or {}).get('status')=='pending'
    if pending and value.get('document_attempted_at'):
        pending=(datetime.now(timezone.utc)-datetime.fromisoformat(value['document_attempted_at'])).total_seconds()<600
    value.update(qa=qa,checks=qa['checks'],status='Checking QA' if pending else ('Ready for manual payment' if all(qa['checks'].values()) else 'Needs QA'),
        message='Certificate and packing slip processing; waiting for supplier confirmation.' if pending else
        ('All QA checks passed. Open this exact draft to review, pay and Submit manually.' if all(qa['checks'].values()) else ' '.join(qa['blockers'])))
    persist(value)
    return value
