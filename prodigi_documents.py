"""Immutable certificate-as-packing-slip files with revocable scoped links."""
from datetime import datetime,timedelta,timezone
import hashlib,json,re,secrets,tempfile
from pathlib import Path
from starlette.background import BackgroundTask
from starlette.responses import Response,FileResponse
from starlette.concurrency import run_in_threadpool
import prodigi_preparation as prep
from prodigi_artwork import HEADERS,fetch

PREFIX='prodigi_document:'
URL='https://sports-cave-image-factory.onrender.com/api/prodigi-document/'


def render_certificate(snapshot,path):
    """Fit the existing certificate on one A4 landscape sheet, with safe margins."""
    from PIL import Image
    from certificate_service import render_template_certificate_image
    with Image.new('RGB',(3508,2480),'white') as page:
        certificate=render_template_certificate_image(product_title=snapshot['product'],edition_number=snapshot['number'],
            edition_total=snapshot['total'],target_size=(3300,2200))
        try:page.paste(certificate,(104,140))
        finally:certificate.close()
        page.save(path,'PDF',resolution=300.0)


def subject_key(value):
    return ('prodigi_sandbox_test:'+value['id']) if value.get('environment')=='sandbox' else prep.PREFIX+str(value['allocation_id'])


def create(value,snapshot):
    key=PREFIX+subject_key(value)
    identity=prep.digest(dict(format='a4-landscape-certificate-v1',**{k:snapshot[k] for k in ('allocation_id','job_id','output','product','number','total')}))
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s',(key,));found=q.fetchone()
    if found:
        doc=found['value']
        if doc['identity']!=identity:raise ValueError('Certificate identity changed; review the existing packing slip.')
        import auto_editions_runtime as rt
        rt.storage().verify_output(doc['output'])
        return doc
    import auto_editions_runtime as rt
    import auto_editions as ae
    with tempfile.TemporaryDirectory(prefix='sc-prodigi-certificate-') as folder:
        path=Path(folder)/'certificate.pdf';render_certificate(snapshot,path)
        if not 0<path.stat().st_size<=16*1024*1024:raise ValueError('Certificate PDF exceeds the supported limit.')
        sha=hashlib.sha256(path.read_bytes()).hexdigest();storage=rt.storage()
        destination=storage.GENERATED_ROOT+'/Fulfilment Documents/'+str(snapshot['allocation_id'])+'/'+sha+'.pdf'
        storage.integration.ensure_folder_path(storage.token,destination.rsplit('/',1)[0],root_path='/Sportscave Team Folder')
        meta=storage.integration.get_metadata_if_exists(storage.token,destination)
        if not meta:meta=storage.integration.upload_local_file(storage.token,destination,path,conflict='cancel')
        if meta.get('size')!=path.stat().st_size or meta.get('content_hash')!=ae.file_hash(path,dropbox=True):
            raise ValueError('Archived certificate differs from the generated PDF.')
        output=dict(file_id=meta['id'],revision=meta['rev'],path=meta.get('path_display') or destination,
                    bytes=meta['size'],sha256=sha,dropbox_content_hash=meta['content_hash'])
    token=secrets.token_urlsafe(32)
    doc=dict(identity=identity,subject=subject_key(value),allocation_id=snapshot['allocation_id'],job_id=snapshot['job_id'],
        source_output=snapshot['output'],output=output,url=URL+token,number=snapshot['number'],total=snapshot['total'],
        expires_at=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat())
    with prep.connect() as c,c.cursor() as q:
        q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO NOTHING',(key,json.dumps(doc)))
        q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())',
            (PREFIX+hashlib.sha256(token.encode()).hexdigest(),json.dumps(doc)))
    return doc


def bound(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):raise ValueError('Unavailable')
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s',(PREFIX+hashlib.sha256(token.encode()).hexdigest(),));r=q.fetchone()
        if not r:raise ValueError('Unavailable')
        doc=r['value'];q.execute('SELECT value FROM app_settings WHERE key=%s',(doc['subject'],));r=q.fetchone()
    if not r or r['value'].get('hidden') or datetime.fromisoformat(doc['expires_at'])<=datetime.now(timezone.utc):raise ValueError('Unavailable')
    value=r['value'];snapshot=value.get('source_snapshot') or value['snapshot']
    if snapshot['job_id']!=doc['job_id'] or snapshot['output']!=doc['source_output']:raise ValueError('Unavailable')
    from auto_editions_jobs import Jobs
    from auto_editions_api import same_allocation
    record,unit=Jobs(prep.connect).read_bound(doc['job_id'],doc['allocation_id'])
    if not record or record['status']!='Ready' or not same_allocation(unit,record['payload']['identity']) or record['result']['output']!=doc['source_output']:
        raise ValueError('Unavailable')
    return doc


async def serve(request):
    folder=None
    try:
        doc=await run_in_threadpool(bound,request.path_params['token'])
        if request.method=='HEAD':return Response(headers={**HEADERS,'Content-Type':'application/pdf','Content-Length':str(doc['output']['bytes'])})
        folder=tempfile.TemporaryDirectory(prefix='sc-prodigi-document-')
        path=await run_in_threadpool(fetch,doc,folder.name)
        await run_in_threadpool(bound,request.path_params['token'])
        return FileResponse(path,media_type='application/pdf',filename='certificate.pdf',content_disposition_type='inline',
            headers=HEADERS,background=BackgroundTask(folder.cleanup))
    except Exception:
        if folder:folder.cleanup()
        return Response(status_code=404,headers=HEADERS)
