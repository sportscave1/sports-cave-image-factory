"""Fixed SC3284 job in the existing authenticated Studio companion. No script/path input."""
import base64,hashlib,io,json,re,secrets,shutil,subprocess,sys,threading,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import edition_test as case
ALLOWED_ORIGINS={'https://sports-cave-image-factory.onrender.com'}
LOCK=threading.RLock()
JOBS={}
ACTIVE=None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Redirected edition transfer rejected.')


def get(grant,path,limit=1024*1024):
    req=Request(grant['base_url']+path,headers={'X-Sports-Cave-Transfer-Secret':grant['secret']})
    with build_opener(NoRedirect()).open(req,timeout=30) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Edition response exceeds its bound.')
        return json.loads(data)


def digest(path,dropbox=False):
    result=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(4*1024*1024),b''):
            result.update(hashlib.sha256(block).digest() if dropbox else block)
    return result.hexdigest()


def start(grant):
    global ACTIVE
    if not isinstance(grant,dict) or set(grant)!={'base_url','ticket','secret'} or grant['base_url'] not in ALLOWED_ORIGINS or not re.fullmatch(r'[A-Za-z0-9_-]{32}',grant['ticket']) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',grant['secret']):raise ValueError('Only a scoped grant from the authorised Sports Cave OS origin is accepted.')
    context=case.validate_context(get(grant,'/api/edition-jpg-test/context?'+urlencode({'ticket':grant['ticket']})))
    with LOCK:
        for old,job in list(JOBS.items()):
            if job['status']!='Generating' and time.monotonic()-job['created']>900:JOBS.pop(old,None)
        if len(JOBS)>=64:raise ValueError('Too many pending test jobs. Wait before retrying.')
        if ACTIVE and JOBS[ACTIVE]['status']=='Generating':raise ValueError('Photoshop is already processing this test. Wait for it to finish.')
        key=secrets.token_hex(24);JOBS[key]={'status':'Generating','context':context,'grant':dict(grant),'created':time.monotonic()};ACTIVE=key
        thread=threading.Thread(target=worker,args=(key,dict(grant)),daemon=True);thread.start()
    return {'job_id':key,'status':'Generating','test_only':True}


def status(key):
    with LOCK:
        job=JOBS.get(str(key))
        if not job or time.monotonic()-job['created']>900:raise ValueError('Test job expired. Generate again to verify the current unit.')
        return {'status':job['status'],'error':job.get('error'),'test_only':True}


def result(key,download=False):
    from PIL import Image
    if status(key)['status']!='Ready':raise ValueError('A validated finished TEST JPG is required.')
    job=JOBS[key];data=job['result'];path=Path(data['jpg'])
    if job.get('grant'):case.validate_context(get(job['grant'],'/api/edition-jpg-test/context?'+urlencode({'ticket':job['grant']['ticket'],'verify':'1'})))
    if digest(path)!=data['jpg_sha256']:raise ValueError('TEST JPG changed after validation; download blocked.')
    if path.stat().st_size>32*1024*1024:raise ValueError('Pilot JPG exceeds the bounded download size.')
    with Image.open(path) as image:
        image.thumbnail((900,900));out=io.BytesIO();image.save(out,format='JPEG',quality=85,icc_profile=image.info.get('icc_profile',b''))
    output={'test_only':True,'print_ready':False,'validated':True,'edition':'002 / 100','dimensions':data['dimensions'],'job_id':key,
            'filename':'SC3284-DICK-JOHNSON-JOHN-FRENCH-UNIT-1-002-of-100-TEST-NOT-PRINT-READY.jpg',
            'preview':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode(),
            'jpg_sha256':data['jpg_sha256']}
    if download:output['jpg_base64']=base64.b64encode(path.read_bytes()).decode()
    return output


def worker(key,grant):
    try:process(key,grant)
    except Exception as error:JOBS[key].update(status='Blocked',error='Required local processor component is unavailable: '+type(error).__name__+'. Check the companion installation.')


def process(key,grant):
    from PIL import Image
    from scripts.verify_psd_number_pixels import compare,region
    context=JOBS[key]['context'];unit=context['unit'];meta=context['metadata']
    cache=Path.home()/'Documents/SportsCavePrintJobs';cache.mkdir(exist_ok=True,parents=True)
    lease=cache/'processor.lock';lease_owned=False;keep_lease=False
    try:
        fd=__import__('os').open(lease,__import__('os').O_CREAT|__import__('os').O_EXCL|__import__('os').O_WRONLY);__import__('os').close(fd);lease_owned=True
        identity=hashlib.sha256(json.dumps({'unit':unit,'source':{k:meta[k] for k in ('id','rev','content_hash')},'processor':digest(ROOT/'scripts/photoshop/prove_psd_number_export.jsx'),'actor':context['actor_id']},sort_keys=True).encode()).hexdigest()
        folder=cache/('native-test-'+identity);folder.mkdir(exist_ok=True)
        if not folder.resolve().is_relative_to(cache.resolve()):raise ValueError('Unsafe local output directory.')
        manifest=folder/'job.json'
        if manifest.exists():
            data=json.loads(manifest.read_text())
            cached=Path(data['jpg']).resolve()
            if not cached.is_relative_to(folder.resolve()) or cached.name!='SC3284-UNIT-1-002-NON_PRODUCTION-AFTER.jpg':raise ValueError('Unsafe cached JPG path.')
            if data.get('validated') and digest(cached)==data['jpg_sha256']:
                JOBS[key].update(status='Ready',result=data);return
        source=folder/'SC3284-NON_PRODUCTION-INPUT.psd'
        seed=Path('C:/Dev/SportsCaveWorktrees/sports-cave-integrations-read-only-psd-edition-number-inspection-v1-20261013-a2c10f66/output/sc3284_psd_test/staging/SC3284-DICK-JOHNSON-JOHN-FRENCH-NON_PRODUCTION-INPUT.psd')
        if not source.exists() or digest(source,True)!=case.CONTENT_HASH:
            if seed.is_file() and digest(seed,True)==case.CONTENT_HASH:shutil.copy2(seed,source)
            else:
                transfer=get(grant,'/api/files-native-transfer/manifest?'+urlencode({'ticket':grant['ticket']}))
                items=transfer['items']
                if len(items)!=1 or any(items[0].get(k)!=v for k,v in {'dropbox_id':case.FILE,'revision':case.REVISION,'content_hash':case.CONTENT_HASH}.items()):raise ValueError('Transferred PSD identity changed.')
                partial=source.with_suffix('.part');req=Request(grant['base_url']+'/api/files-native-transfer/content?'+urlencode({'ticket':grant['ticket'],'item':items[0]['token']}),headers={'X-Sports-Cave-Transfer-Secret':grant['secret']})
                count=0
                with build_opener(NoRedirect()).open(req,timeout=60) as response,partial.open('wb') as out:
                    for block in iter(lambda:response.read(4*1024*1024),b''):
                        count+=len(block)
                        if count>meta['size']:raise ValueError('PSD transfer size exceeded its verified metadata.')
                        out.write(block)
                if count!=meta['size'] or digest(partial,True)!=case.CONTENT_HASH:raise ValueError('PSD transfer content hash failed.')
                partial.replace(source)
        before_hash=digest(source)
        prefix=str(folder/'SC3284-UNIT-1-002-NON_PRODUCTION')
        target={'layer_id':34,'name':'100 / 100','text':'100 / 100','visible':True,'locked':False,'editable':True,'smart_object_chain':[],
                'pattern':{'number':100,'total':100,'number_width':3,'valid':True,'possible_date':False}}
        request={'non_production':True,'confirmed_order_unit':unit,'expected_display':'#002/100','inspection_script':str(ROOT/'scripts/photoshop/inspect_psd_editions.jsx'),
                 'stage_root':str(folder),'output_root':str(folder),'report_path':str(folder/'proof.json'),
                 'entries':[{'product_gid':case.PRODUCT,'product_title':'Dick Johnson & John French — The Comeback','shopify_order_id':case.ORDER,'shopify_line_item_id':case.LINE,
                             'dropbox_file_id':case.FILE,'dropbox_revision':case.REVISION,'content_hash':case.CONTENT_HASH,'work_path':str(source),'target':target,'output_prefix':prefix}]}
        (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
        started=time.monotonic()
        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/photoshop_dispatch.py'),str(ROOT/'scripts/photoshop/prove_psd_number_export.jsx'),str(folder/'request.json')],check=True,capture_output=True,timeout=180)
        proof=json.loads((folder/'proof.json').read_text(encoding='utf-8-sig'))['documents'][0]
        if not proof.get('structural_verification') or proof.get('actual_text')!='002 / 100' or digest(source)!=before_hash:raise ValueError('Artwork/text/master preservation verification failed.')
        size=[round(proof['width']),round(proof['height'])];roi=region(proof['number_bounds_before'],proof['number_bounds_after'],size)
        pixels=compare(proof['before_png'],proof['after_png'],roi)
        jpeg=compare(proof['before_jpg'],proof['after_jpg'],region(proof['number_bounds_before'],proof['number_bounds_after'],size,padding=32,block=16))
        if not pixels['ok'] or not jpeg['ok']:raise ValueError('Pixels outside the verified edition-number region changed.')
        jpg=Path(proof['after_jpg'])
        with Image.open(jpg) as image:
            if list(image.size)!=size or not image.info.get('icc_profile') or any(abs(d-proof['resolution'])>.001 for d in image.info.get('dpi',())):raise ValueError('JPG metadata validation failed.')
        data={'jpg':str(jpg),'jpg_sha256':digest(jpg),'dimensions':size,'validated':True,'test_only':True,'print_ready':False,'edition':'002 / 100','identity':identity,
              'pixels':pixels,'jpeg_pixels':jpeg,'seconds':time.monotonic()-started,'source_sha256':before_hash}
        manifest.write_text(json.dumps(data,indent=2));JOBS[key].update(status='Ready',result=data)
    except Exception as error:
        keep_lease=isinstance(error,subprocess.TimeoutExpired)
        message='Photoshop did not finish. Check for a Photoshop dialog; the processing lease is retained to prevent duplicate work.' if keep_lease else 'TEST JPG blocked: '+(str(error) if isinstance(error,ValueError) else type(error).__name__+'. Check Photoshop availability and the companion diagnostic.')
        JOBS[key].update(status='Blocked',error=message)
    finally:
        if lease_owned and not keep_lease:lease.unlink(missing_ok=True)


def action(data):
    kind=data.get('action')
    if kind=='edition-test-start' and set(data)=={'action','grant'}:return start(data['grant'])
    if kind in ('edition-test-status','edition-test-result','edition-test-download') and set(data)=={'action','job_id'}:
        return status(data['job_id']) if kind.endswith('status') else result(data['job_id'],download=kind.endswith('download'))
    raise ValueError('Unsupported edition test action. Arbitrary scripts, paths and product numbers are not accepted.')
