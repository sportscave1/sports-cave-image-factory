"""Paid certificate units join Orders/Companion without allocating new editions.

The reserved JS-safe identifier namespace is backed by app_settings, not by the
edition ledger. Every read rechecks the paid request, line, owner and certificate.
"""
import hashlib
import io
import json
import logging
from pathlib import Path
import tempfile
from urllib.parse import urlparse

BASE = 2 ** 52
PREFIX = 'certificate_frame_unit:'
POLICY = 'issued-certificate-source-v1'
LOG = logging.getLogger(__name__)


def is_unit(value):
    try:
        return BASE <= int(value) < BASE + 2 ** 48
    except (ValueError, TypeError):
        return False


def allocation_id(order_id, line_id, ordinal):
    return BASE + int(hashlib.sha256(f'{order_id}|{line_id}|{ordinal}'.encode()).hexdigest()[:12], 16)


def ingest_paid(payload, connect):
    """Only validated owner-bound requests; retries never replace a pinned unit."""
    import collector_vault as vault
    from collector_collection_offers import FRAME_SKUS
    order_id = vault._canonical_gid('Order', payload.get('admin_graphql_api_id') or payload.get('id'))
    customer = vault._canonical_gid('Customer', (payload.get('customer') or {}).get('id'))
    created = 0
    if not order_id or not customer:
        return 0
    with connect() as c, c.cursor() as q:
        for line in payload.get('line_items') or []:
            reference = vault._line_item_properties(line).get('_sports_cave_frame_request', '')
            if not vault._UUID.fullmatch(reference):
                continue
            q.execute('SELECT * FROM collector_frame_requests WHERE request_reference=%s AND status=\'ordered\'', (reference,))
            request = q.fetchone()
            if not request or request['framed_shopify_order_id'] != order_id or request['shopify_customer_id'] not in vault.customer_id_candidates(customer):
                continue
            variant = vault._line_item_variant_id(line)
            color = FRAME_SKUS.get(line.get('sku'))
            if variant != request['frame_variant_id'] or not color:
                continue
            line_id = vault._canonical_gid('LineItem', line.get('id') or line.get('admin_graphql_api_id'))
            quantity = int(line.get('quantity') or 0)
            if not line_id or not 1 <= quantity <= 50:
                raise ValueError('Certificate line identity or quantity needs review.')
            for ordinal in range(1, quantity + 1):
                aid = allocation_id(order_id, line_id, ordinal)
                value = dict(id=aid, source_kind='framed_certificate', request_reference=reference,
                    shopify_order_id=order_id, shopify_order_name=str(payload.get('name') or ''),
                    shopify_line_item_id=line_id, shopify_product_gid=request['frame_product_id'],
                    shopify_product_id=request['frame_product_id'], shopify_variant_id=variant,
                    allocation_index=ordinal, unit_ordinal=ordinal, quantity=1,
                    edition_number=int(request['edition_number']), edition_total=int(request['edition_limit']),
                    certificate_row_id=request['certificate_row_id'], certificate_id=request.get('certificate_id'),
                    product_title='Framed Collector Certificate — ' + request['artwork_title'],
                    variant_title=f'{color} / S - 21 × 30 cm (8.3 × 11.8 in)', frame_color=color,
                    status='assigned', allocation_valid=True, identity_enforced=True)
                q.execute('SELECT id FROM edition_orders WHERE id=%s', (aid,))
                if q.fetchone():
                    raise ValueError('Certificate fulfilment identifier collides with an edition allocation.')
                q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO NOTHING',
                          (PREFIX + str(aid), json.dumps(value)))
                q.execute('SELECT value FROM app_settings WHERE key=%s', (PREFIX + str(aid),))
                if q.fetchone()['value'] != value:
                    raise ValueError('Certificate fulfilment identity changed; preserve the existing unit.')
                created += 1
    return created


def _read(aid, connect):
    with connect() as c, c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s', (PREFIX + str(int(aid)),))
        saved = q.fetchone()
        if not saved:
            raise ValueError('Certificate fulfilment unit is unavailable.')
        unit = saved['value']
        q.execute('SELECT * FROM collector_frame_requests WHERE request_reference=%s', (unit['request_reference'],))
        request = q.fetchone()
        if not request or request['status'] != 'ordered' or request['framed_shopify_order_id'] != unit['shopify_order_id'] or request['frame_variant_id'] != unit['shopify_variant_id'] or request['certificate_row_id'] != unit['certificate_row_id']:
            raise ValueError('Paid certificate request no longer matches this unit.')
        q.execute('SELECT c.*, c.id AS certificate_row_id FROM certificates c WHERE c.id=%s', (unit['certificate_row_id'],))
        certificate = q.fetchone()
        q.execute("SELECT raw_json FROM shopify_orders WHERE regexp_replace(shopify_order_id,'^.*/','')=%s LIMIT 2", (unit['shopify_order_id'].rsplit('/', 1)[-1],))
        mirrors = q.fetchall()
    if not certificate or len(mirrors) != 1:
        raise ValueError('Certificate or paid order mirror is missing or ambiguous.')
    raw = mirrors[0]['raw_json'] or {}
    if raw.get('cancelled_at') or str(raw.get('financial_status') or '').lower() != 'paid' or raw.get('refunds') or raw.get('refund_pending') or (raw.get('_orders_refund') or {}).get('blocked'):
        raise ValueError('Cancelled, unpaid or refunded certificate order needs review.')
    lines = [line for line in raw.get('line_items', []) if str(line.get('id') or line.get('shopify_line_item_id') or '').rsplit('/', 1)[-1] == unit['shopify_line_item_id'].rsplit('/', 1)[-1]]
    import collector_vault as vault
    if len(lines) != 1 or vault._line_item_properties(lines[0]).get('_sports_cave_frame_request') != unit['request_reference'] or vault._line_item_variant_id(lines[0]) != unit['shopify_variant_id'] or int(lines[0].get('quantity') or 0) < unit['unit_ordinal']:
        raise ValueError('The paid certificate line changed.')
    if str(certificate.get('shopify_order_id') or '').rsplit('/', 1)[-1] != str(request['original_shopify_order_id']).rsplit('/', 1)[-1]:
        raise ValueError('The original issued certificate identity changed.')
    customer = vault._canonical_gid('Customer', (raw.get('customer') or {}).get('id') or raw.get('shopify_customer_id') or raw.get('customer_id'))
    if (request['shopify_customer_id'] not in vault.customer_id_candidates(customer)
            or certificate.get('shopify_customer_id') not in vault.customer_id_candidates(customer)):
        raise ValueError('The paid certificate owner changed.')
    if (str(certificate.get('certificate_id') or '') != str(request.get('certificate_id') or '')
            or int(certificate.get('edition_number') or 0) != unit['edition_number']
            or int(certificate.get('edition_limit') or certificate.get('edition_total') or 0) != unit['edition_total']):
        raise ValueError('The original certificate number or identity changed.')
    return unit, certificate, raw, request


def unit(aid, connect):
    current, _, _, _ = _read(aid, connect)
    return current, {'source_kind': 'framed_certificate', 'verified': True, 'state': 'Linked'}


def job_for(aid, connect):
    import auto_editions as ae
    import collector_vault as vault
    current, certificate, _, _ = _read(aid, connect)
    asset = vault._asset_reference(certificate, 'print') or vault._asset_reference(certificate, 'pdf')
    if not asset:
        raise ValueError('The original full-quality certificate file is unavailable.')
    source = dict(product_gid=current['shopify_product_gid'], certificate_row_id=current['certificate_row_id'],
                  request_reference=current['request_reference'], asset=asset,
                  revision=str(certificate.get('updated_at') or certificate.get('generated_at') or ''))
    preparation = ae.fingerprint(source)
    identity = dict(allocation_id=current['id'], order_id=current['shopify_order_id'],
        line_id=current['shopify_line_item_id'], ordinal=current['unit_ordinal'],
        variant_id=current['shopify_variant_id'], number=current['edition_number'],
        total=current['edition_total'], source=source, preparation=preparation)
    job = dict(id=ae.fingerprint(identity), source_kind='framed_certificate', identity=identity,
        source=source, preparation_hash=preparation, number=identity['number'], total=identity['total'],
        production={'evidence': {'certificate_source_verified': True}},
        archive_labels=dict(order_name=current['shopify_order_name'], product_title=current['product_title'], variant_title=current['variant_title']))
    return job


def fetch_source(asset):
    import requests
    from services import r2_storage
    if asset['storage'] == 'r2':
        url = r2_storage.generate_presigned_download_url(asset['bucket'], asset['key'], expires_seconds=300)
    else:
        url = asset['url']
        if urlparse(url).hostname != 'cdn.shopify.com':
            raise ValueError('The issued certificate must be in verified certificate storage.')
    response = requests.get(url, stream=True, timeout=(8, 60), allow_redirects=False)
    data = bytearray()
    try:
        response.raise_for_status()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError('Certificate source exceeds the print transfer limit.')
    finally:
        response.close()
    return bytes(data)


def render(content, mime, destination):
    import auto_editions as ae
    from auto_editions_onboarding import preparation_scale
    from PIL import Image, ImageCms, ImageOps
    if mime == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(content) as pdf:
            if len(pdf) != 1:
                raise ValueError('The issued certificate must contain exactly one page.')
            page = pdf[0]
            width,height=page.get_size()
            if width <= 0 or height <= 0 or width*height*(300/72)**2 > ae.WORKER_MAX_PIXELS:
                page.close()
                raise ValueError('Certificate PDF exceeds the verified pixel budget.')
            bitmap = page.render(scale=300 / 72)
            try:
                image = bitmap.to_pil().convert('RGB')
            finally:
                bitmap.close(); page.close()
    else:
        with Image.open(io.BytesIO(content)) as opened:
            if opened.width * opened.height > ae.WORKER_MAX_PIXELS:
                raise ValueError('Certificate image exceeds the verified pixel budget.')
            image = ImageOps.exif_transpose(opened).convert('RGB')
    try:
        native = list(image.size)
        scale = preparation_scale(native)  # Same bounded integer enlargement as PSD preparation.
        dimensions = [n * scale for n in native]
        if scale != 1:
            enlarged = image.resize(dimensions, Image.Resampling.LANCZOS)
            image.close(); image = enlarged
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        image.save(destination, 'JPEG', quality=100, subsampling=0, dpi=(300, 300), icc_profile=profile)
    finally:
        image.close()
    return dict(source_dimensions=native, dimensions=dimensions, scale=scale,
                source_sha256=hashlib.sha256(content).hexdigest(), sha256=ae.file_hash(destination))


def execute(job, assets):
    import auto_editions as ae
    from auto_editions_asset_cache import output_assets
    with tempfile.TemporaryDirectory(prefix='sc-framed-certificate-') as folder:
        path = Path(folder) / 'certificate.jpg'
        content = fetch_source(job['source']['asset'])
        with ae._RENDER_LOCK:
            evidence = render(content, job['source']['asset']['mime_type'], path)
        output = assets.publish_output(job, path)
        if output.get('sha256') != evidence['sha256']:
            raise ValueError('Archived certificate JPG differs from the verified output.')
        output_assets.remember(evidence['sha256'], path)
    return dict(**evidence, output=output, status='Ready', retained=True, test_only=False,
        edition_number=job['number'], edition_total=job['total'],
        filename=Path(output['path']).name, timings={}, print_spec={'basis': 'Issued certificate; supplier QA required'})


def resolve(aid, connect):
    import prodigi_preparation as prep
    import os_pages
    from auto_editions_jobs import Jobs
    current, _, raw, _ = _read(aid, connect)
    job = job_for(aid, connect)
    record = Jobs(connect).read(job['id'])
    if not record or record['status'] != 'Ready':
        raise prep.MissingJPG('Preparing the exact issued certificate JPG.')
    mapping = os_pages.prodigi_mapping_for_frame_size(current['frame_color'], 'S')
    if not mapping.get('prodigi_code') or mapping.get('frame') != current['frame_color']:
        raise ValueError('The Small certificate frame mapping needs review.')
    result = record['result']
    return dict(source_kind='framed_certificate', allocation_id=aid, identity=job['identity'],
        job_id=job['id'], output=result['output'], mapping=mapping, order_reference=current['shopify_order_name'],
        product=current['product_title'], shipping=raw.get('shipping_method') or ((raw.get('shipping_lines') or [{}])[0].get('title', '')), number=job['number'], total=job['total'],
        recipient=prep.shopify_recipient(raw, current['shopify_order_id']), dimensions=result['dimensions'],
        rendered_number=result['edition_number'], rendered_total=result['edition_total'],
        certificate_evidence={k: result[k] for k in ('source_dimensions', 'source_sha256', 'sha256')},
        production_evidence={'certificate_source_verified': True}, draft_preparation=True)


def admit(actor, connect, limit=3):
    import auto_editions_runtime as runtime
    import prodigi_preparation as prep
    from auto_editions_jobs import Jobs
    with connect() as c, c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY updated_at DESC LIMIT 75', (PREFIX + '%',))
        units = [r['value'] for r in q.fetchall()]
    jobs = Jobs(connect)
    count = 0
    for current in units:
        if count >= limit:
            break
        try:
            if prep.read(current['id']):
                continue
            job = job_for(current['id'], connect)
            saved = jobs.read(job['id'])
            if not saved:
                jobs.enqueue(job, str(actor['id'])); runtime.start_worker()
            elif saved['status'] == 'Ready':
                prep.request(actor, current['id'])
            else:
                continue
            count += 1
        except (ValueError, PermissionError):
            LOG.warning('Certificate fulfilment admission needs source/order review')
    return count


def merge_rows(rows, connect, search=''):
    """Read-only Orders overlay. Artwork rows retain their original data and IDs."""
    import collector_vault as vault
    with connect() as c, c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY updated_at DESC LIMIT 75', (PREFIX + '%',))
        units = [r['value'] for r in q.fetchall()]
    additions = []
    for saved in units:
        if search and search.lower() not in json.dumps(saved).lower():
            continue
        try:
            current, certificate, raw, request = _read(saved['id'], connect)
        except (ValueError, PermissionError):
            continue
        certificate.update(certificate_row_id=current['certificate_row_id'], order_customer_id=request['shopify_customer_id'])
        try:
            assets = vault._certificate_public_row(certificate)
        except vault.CollectorVaultError:
            assets = {}
        preview = assets.get('preview_url') or ''
        additions.append(dict(current, edition_order_id=current['id'],
            edition_display=f"#{current['edition_number']:03d}/{current['edition_total']}",
            order=current['shopify_order_name'], order_name=current['shopify_order_name'],
            product=current['product_title'], variant=current['variant_title'],
            customer=raw.get('customer_name') or (raw.get('shipping_address') or {}).get('name', ''),
            date=raw.get('created_at') or '', has_saved_allocation=True, assignment_status='assigned',
            certificate_status='Uploaded',
            customer_name=(raw.get('shipping_address') or {}).get('name', ''),
            purchase_date=raw.get('created_at') or '', product_image_url='https://sports-cave-image-factory.onrender.com' + preview if preview else '',
            certificate_pdf_url='https://sports-cave-image-factory.onrender.com' + assets['pdf_url'] if assets.get('pdf_url') else '',
            shipping_method=raw.get('shipping_method') or (raw.get('shipping_lines') or [{}])[0].get('title', ''),
            prodigi='Pending', source='framed_certificate'))
    keys={(r['shopify_order_id'].rsplit('/',1)[-1],r['shopify_line_item_id'].rsplit('/',1)[-1]) for r in additions}
    return [r for r in rows if (str(r.get('shopify_order_id') or '').rsplit('/',1)[-1],str(r.get('shopify_line_item_id') or '').rsplit('/',1)[-1]) not in keys] + additions


def download_links(rows, jobs):
    ids = [str(r.get('edition_order_id')) for r in rows if r.get('source_kind') == 'framed_certificate']
    result = {}
    for aid, saved in jobs.summaries(ids).items() if ids else []:
        result[aid] = ('/api/auto-editions/file?allocation_id=' + aid + '&job_id=' + saved['id'] + '&inline=1#Open JPG'
                       if saved['status'] == 'Ready' else '/auto-editions/download?allocation_id=' + aid + '#Generating')
    return result


def identity_proof(snapshot):
    import auto_editions_runtime as runtime
    job,_=runtime.job_for(snapshot['allocation_id'])
    return bool(job.get('source_kind')=='framed_certificate' and job['id']==snapshot['job_id']
        and job['number']==snapshot['number']==snapshot.get('rendered_number')
        and job['total']==snapshot['total']==snapshot.get('rendered_total')
        and snapshot.get('certificate_evidence',{}).get('sha256')==snapshot.get('output',{}).get('sha256'))


def approve(snapshot,provider,asset_id):
    import prodigi_full_qa as qa
    from prodigi_artwork import fetch
    from PIL import Image,JpegImagePlugin
    if not identity_proof(snapshot):raise ValueError('The exact issued certificate source changed.')
    sku=snapshot['mapping']['prodigi_code']; catalogue=provider.catalogue(sku)
    if (catalogue.get('sku') or catalogue.get('id'))!=sku:raise ValueError('Supplier catalogue SKU differs.')
    physical,dpi=qa.print_area(catalogue,snapshot['dimensions'])
    native=snapshot['certificate_evidence']['source_dimensions']
    ppi=[n*25.4/mm for n,mm in zip(native,physical)]
    blockers=[]
    if min(ppi)+0.5<dpi:blockers.append('The original certificate resolution is below the supplier recommendation; review required.')
    with tempfile.TemporaryDirectory(prefix='sc-certificate-qa-') as folder:
        path=fetch(snapshot,folder)
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=snapshot['output']['sha256']:
            raise ValueError('The archived certificate checksum changed.')
        with Image.open(path) as image:
            if (image.format!='JPEG' or image.mode!='RGB' or list(image.size)!=snapshot['dimensions']
                or list(image.info.get('dpi',()))!=[300,300] or JpegImagePlugin.get_sampling(image)!=0
                or not image.quantization or any(v!=1 for t in image.quantization.values() for v in t)):
                raise ValueError('The certificate print encoding changed.')
            icc_sha,colour_blocker=qa.colour_evidence(image.info.get('icc_profile',b''))
            if colour_blocker:blockers.append(colour_blocker)
    validation=provider.validate_asset(asset_id,sku)
    valid=validation.get('valid') is True and validation.get('status')=='valid' and not validation.get('issues')
    if not valid:blockers.append('Supplier artwork validation requires review.')
    import prodigi_preparation as prep
    return dict(policy=POLICY,job_id=snapshot['job_id'],sha256=snapshot['output']['sha256'],sku=sku,
        dimensions=snapshot['dimensions'],number=snapshot['number'],total=snapshot['total'],
        source_sha256=snapshot['certificate_evidence']['source_sha256'],source_ppi=ppi,required_ppi=dpi,
        physical_mm=physical,icc_sha256=icc_sha,certificate_source_verified=True,number_verified=True,
        supplier_asset_validated=valid,print_ready=not blockers,blockers=blockers,checked_at=prep.now(),
        basis='Exact issued certificate, original edition identity, archived print encoding and supplier validation')


def evidence_matches(approval,snapshot):
    return bool(approval and approval.get('policy')==POLICY
        and approval.get('job_id')==snapshot['job_id'] and approval.get('sha256')==snapshot['output']['sha256']
        and approval.get('sku')==snapshot['mapping']['prodigi_code'] and approval.get('dimensions')==snapshot['dimensions']
        and approval.get('number')==snapshot['number'] and approval.get('total')==snapshot['total']
        and approval.get('source_sha256')==snapshot.get('certificate_evidence',{}).get('source_sha256')
        and all(approval.get(k) is True for k in ('certificate_source_verified','number_verified','supplier_asset_validated')))
