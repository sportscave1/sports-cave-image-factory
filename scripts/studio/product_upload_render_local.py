"""Additional pre-product render on the existing host/processor ownership path."""
import json
import logging
import threading
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

HEARTBEAT_SECONDS = 30


def render_heartbeat(stop, config, host):
    # Native rendering can exceed the normal host poll interval. Telemetry must
    # remain current without renewing/claiming an unrelated preparation lease.
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            host.host_request(config, '/api/auto-editions/onboarding/heartbeat', {})
        except Exception as error:
            logging.getLogger(__name__).warning('product_render_heartbeat_pending error_type=%s', type(error).__name__)


def run_one(config, host):
    import requests
    try:
        job = host.host_request(config, '/api/product-uploads/render/claim', {})['job']
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404: return False
        raise
    if not job: return False
    root=host.HOST_FILE.parent/('product-upload-'+job['id']+'-attempt-'+str(job.get('attempt',1)));root.mkdir(exist_ok=True)
    checkpoint=root/'render-job.json'
    if checkpoint.exists():
        previous=json.loads(checkpoint.read_text())
        if previous['source']!=job['source'] or previous['token']!=job['token']:
            raise ValueError('Retained render lease differs; manual reconciliation required.')
    else:host.atomic_json(checkpoint,{k:v for k,v in job.items() if k!='grant'})
    source=root/'input.psd';output=root/'render-v1'
    receipt_file=output/'receipt.json'
    job_key='product-upload:'+job['id']
    host.JOBS[job_key]=dict(status='Working',phase='Photoshop',started_at=__import__('time').time(),context={},folder=root)
    stopped=threading.Event()
    heartbeat=threading.Thread(target=render_heartbeat,args=(stopped,config,host),name='product-render-heartbeat',daemon=True)
    heartbeat.start()
    try:
        if receipt_file.exists():
            receipt=json.loads(receipt_file.read_text());path=output/'render.png'
            from auto_editions_performance import file_hashes
            if receipt['source']!=job['source'] or file_hashes(source)['sha256']!=receipt['source_sha256']:
                raise ValueError('Retained rendered source changed.')
        else:
            if output.exists():raise ValueError('Interrupted native render retained. Review Photoshop ownership before retrying.')
            if not source.exists():
                grant=job['grant'];manifest=host.transfer.get(grant,'/api/files-native-transfer/manifest?'+urlencode({'ticket':grant['ticket']}))
                if len(manifest['items'])!=1:raise ValueError('One exact PSD is required.')
                item=manifest['items'][0]
                if any(item.get(k)!=job['metadata'][v] for k,v in [('dropbox_id','id'),('revision','rev'),('content_hash','content_hash')]):raise ValueError('Native transfer source changed.')
                req=Request(grant['base_url']+'/api/files-native-transfer/content?'+urlencode({'ticket':grant['ticket'],'item':item['token']}),headers={'X-Sports-Cave-Transfer-Secret':grant['secret']})
                count=0
                temporary=root/'input.partial'
                with build_opener(host.transfer.NoRedirect()).open(req,timeout=300) as response,temporary.open('wb') as destination:
                    while block:=response.read(4*1024*1024):
                        count+=len(block)
                        if count>job['metadata']['size']:raise ValueError('PSD exceeds its verified size.')
                        destination.write(block)
                if count!=job['metadata']['size']:raise ValueError('Incomplete PSD download; retry retained transfer.')
                temporary.replace(source)
            lease=host.processor_lease()
            try:
                from scripts.render_product_upload_psd import render
                path,receipt=render(source,output,job['source'])
            finally:
                # A COM/RPC interruption retains the same safety fence as other
                # native work. Release only proven cleanup or pre-dispatch work.
                dispatched=(output/'dispatch-intent.json').exists()
                status=output/'native-status.json'
                safe=not dispatched or status.exists() and json.loads(status.read_text(encoding='utf-8-sig')).get('owned_document_closed') is True
                if safe:lease.unlink(missing_ok=True)
        host.JOBS[job_key]['phase']='Uploading'
        with path.open('rb') as image:
            response=requests.post(config['base_url']+'/api/product-uploads/render/complete?'+urlencode({'id':job['id']}),data=image,
                headers={'X-Sports-Cave-Preparation-Host':config['token'],'X-Render-Token':job['token'],'X-Render-Receipt':json.dumps(receipt,separators=(',',':'))},allow_redirects=False,timeout=300)
        response.raise_for_status()
        host.atomic_json(root/'completed.json',dict(source=job['source'],verified=True))
    except ValueError as error:
        host.host_request(config,'/api/product-uploads/render/fail',dict(id=job['id'],token=job['token'],reason=str(error),retryable=not (Path.home()/'Documents/SportsCavePrintJobs/processor.lock').exists()))
    except Exception as error:
        # Transient delivery failures retain the verified local receipt and
        # reconnect the same lease. Native/RPC/storage failures are visible,
        # never repeatedly rerendered under an assumed-clean Photoshop state.
        response=getattr(error,'response',None)
        if isinstance(error,requests.RequestException) and (response is None or response.status_code not in (400,409)):
            raise
        host.atomic_json(root/'failure-detail.json',dict(type=type(error).__name__,message=str(error),source=job['source']))
        host.host_request(config,'/api/product-uploads/render/fail',dict(id=job['id'],token=job['token'],
            reason='Photoshop rendering or delivery verification failed. Original PSD and diagnostics are retained. Check Companion diagnostics and any retained processor lock before retrying.',
            retryable=not (Path.home()/'Documents/SportsCavePrintJobs/processor.lock').exists()))
    finally:
        stopped.set()
        heartbeat.join(timeout=21)  # Existing host_request has a 20-second timeout.
        host.JOBS.pop(job_key,None)
    return True
