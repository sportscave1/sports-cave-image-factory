"""One-time preparation in the existing companion. No order-time Photoshop."""
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request,build_opener
import zipfile

import edition_test_local as transfer

JOBS={}
LOCK=threading.Lock()
HOST_THREAD=None
HOST_STOP=threading.Event()
HOST_FILE=Path.home()/'Documents'/'SportsCaveAutoEditions'/'preparation-host.dpapi'


def configure_host(config):
    """Opt-in preparation-only capability; never a Dropbox or Shopify credential."""
    import re
    from device_trust import protect
    if (not isinstance(config,dict) or set(config)!={'base_url','token'}
            or config['base_url'] not in transfer.ALLOWED_ORIGINS
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}',str(config['token']))):
        raise ValueError('A scoped Sports Cave preparation host capability is required.')
    HOST_FILE.parent.mkdir(parents=True,exist_ok=True)
    temporary=HOST_FILE.with_suffix('.tmp')
    temporary.write_bytes(protect(json.dumps(config).encode()))
    os.replace(temporary,HOST_FILE)
    restore_host()
    return dict(status='Connected for background master preparation')


def restore_host():
    global HOST_THREAD
    with LOCK:
        if not HOST_FILE.exists() or HOST_THREAD and HOST_THREAD.is_alive():return
        HOST_STOP.clear()
        HOST_THREAD=threading.Thread(target=host_loop,name='auto-editions-preparation-host',daemon=True)
        HOST_THREAD.start()


def host_loop():
    from device_trust import protect
    import requests
    while not HOST_STOP.is_set():
        try:
            config=json.loads(protect(HOST_FILE.read_bytes(),decrypt=True))
            if config['base_url'] not in transfer.ALLOWED_ORIGINS:return
            if shutil.disk_usage(HOST_FILE.parent).free<8*1024**3:
                HOST_STOP.wait(30);continue
            # Other authorised Photoshop operations share this existing lease.
            if any(r['status']=='Working' for r in list(JOBS.values())) or (Path.home()/'Documents'/'SportsCavePrintJobs'/'processor.lock').exists():
                HOST_STOP.wait(30);continue
            retry_verified_cleanup()
            response=requests.post(config['base_url']+'/api/auto-editions/onboarding/claim',json={},
                headers={'X-Sports-Cave-Preparation-Host':config['token']},allow_redirects=False,timeout=90)
            if response.status_code==403:return
            response.raise_for_status();data=response.json()
            (HOST_FILE.parent/'host-status.json').write_text(json.dumps(dict(last_poll=time.time(),
                status='Preparing' if data.get('grant') else 'Waiting for eligible work')))
            if data.get('grant'):start(data['grant'])
        except Exception as error:
            # No credentials or private transport data in logs. Durable leases
            # make interrupted work recoverable on the next authorised session.
            try:(HOST_FILE.parent/'host-status.json').write_text(json.dumps(dict(last_poll=time.time(),status='Retrying',error_type=type(error).__name__)))
            except OSError:pass
        HOST_STOP.wait(30)


def context(grant):
    import re
    if (not isinstance(grant,dict) or set(grant)!={'base_url','ticket','secret'}
            or grant['base_url'] not in transfer.ALLOWED_ORIGINS
            or not re.fullmatch(r'[A-Za-z0-9_-]{32}',grant['ticket'])
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}',grant['secret'])):
        raise ValueError('A scoped administrator preparation grant is required.')
    return transfer.get(grant,'/api/auto-editions/context?'+urlencode({'ticket':grant['ticket']}))


def start(grant):
    verified=context(grant)
    with LOCK:
        for key,row in list(JOBS.items()):
            if time.monotonic()-row['created']>1800 and row['status']!='Working':JOBS.pop(key,None)
        # Durable server checkpoints retain completed automatic jobs. They must
        # not exhaust the eight interactive-session slots during a fast batch.
        for key,row in list(JOBS.items()):
            if row['context'].get('automatic') and row['status'] in ('Prepared','Blocked'):
                JOBS.pop(key,None)
        if any(row['status']=='Working' for row in JOBS.values()):raise ValueError('A preparation is already running.')
        if len(JOBS)>=8:raise ValueError('Too many preparation sessions. Retry later.')
        key=secrets.token_hex(24)
        folder=Path.home()/'Documents'/'SportsCaveAutoEditions'/key
        folder.mkdir(parents=True,exist_ok=False)
        JOBS[key]=dict(grant=grant,context=verified,folder=folder,created=time.monotonic(),status='Working')
        package=find_reusable_package(verified)
        if package:
            JOBS[key]['reused_package']=str(package)
            journal=package.parent/'preparation-timing.json'
            if journal.exists() and not journal.is_symlink():
                try:
                    saved=json.loads(journal.read_text())
                    if saved.get('source')==verified['source']:
                        JOBS[key]['timings']=saved.get('timings',{})
                except (OSError,ValueError):pass
            threading.Thread(target=upload_prepared,args=(key,package),daemon=True).start()
        else:threading.Thread(target=inspect,args=(key,),daemon=True).start()
        return dict(job_id=key,status='Working')


def find_reusable_package(ctx):
    """Only reuse exact source/edition identities. The server revalidates pixels."""
    if not ctx.get('automatic'):return None
    root=HOST_FILE.parent.resolve()
    for package in sorted(root.glob('*/prepared.zip'),key=lambda p:p.stat().st_mtime,reverse=True):
        if package.is_symlink() or package.parent.is_symlink():continue
        try:
            with zipfile.ZipFile(package) as archive:
                if archive.getinfo('manifest.json').file_size>4*1024*1024:continue
                manifest=json.loads(archive.read('manifest.json'))
            if ctx.get('reset_id') and manifest.get('reset_request_id')!=ctx['reset_id']:continue
            from auto_editions_onboarding import preparation_scale
            expected=preparation_scale(manifest.get('source_dimensions',manifest.get('dimensions',[])))
            if (manifest.get('source')==ctx['source'] and manifest.get('edition_total')==ctx['total']
                    and manifest.get('preparation_geometry',{}).get('scale',1)==expected):
                return package
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    return None


def reconnect(row):
    from device_trust import protect
    import requests
    config=json.loads(protect(HOST_FILE.read_bytes(),decrypt=True))
    if config['base_url']!=row['grant']['base_url']:raise ValueError('Preparation origin changed.')
    ctx=row['context']
    response=requests.post(config['base_url']+'/api/auto-editions/onboarding/reconnect',
        json={k:ctx[k] for k in ('product_gid','lease_token')},
        headers={'X-Sports-Cave-Preparation-Host':config['token']},allow_redirects=False,timeout=90)
    response.raise_for_status();data=response.json()
    if data.get('completed'):
        if data['completed'].get('source')!=ctx['source']:raise ValueError('Completed source changed.')
        return data['completed']
    row['grant']=data['grant']
    if context(row['grant'])!=ctx:raise ValueError('Preparation identity changed.')


def upload_prepared(key,archive):
    """Retry transfer after deploy without repeating Photoshop or source download."""
    import requests
    row=JOBS[key];started=time.monotonic()
    try:
        for attempt in range(3):
            try:
                grant=row['grant']
                with archive.open('rb') as content:
                    response=requests.post(grant['base_url']+'/api/auto-editions/package?'+urlencode({'ticket':grant['ticket']}),
                        data=content,headers={'X-Sports-Cave-Transfer-Secret':grant['secret'],'Content-Type':'application/zip'},
                        allow_redirects=False,timeout=600)
                response.raise_for_status();result=response.json()
                if not result.get('preparation_hash'):raise ValueError('Cloud preparation was not confirmed.')
                finish_upload(row,result,started)
                return
            except requests.RequestException:
                if attempt==2 or not row['context'].get('automatic'):raise
                completed=reconnect(row)
                if isinstance(completed,dict) and completed.get('preparation_hash'):
                    finish_upload(row,completed,started)
                    return
    except Exception as error:
        row.update(status='Blocked',error='Prepared package retained; upload/checkpoint failed: '+type(error).__name__)
        report_failure(row)


def finish_upload(row,result,started):
    row.update(status='Prepared',preparation_hash=result['preparation_hash'])
    row.setdefault('timings',{})['upload_validate_seconds']=round(time.monotonic()-started,3)
    row['server_timings']=result.get('timings',{})
    if row['context'].get('automatic'):
        try:release_verified_temporary_files(row)
        except (OSError,ValueError):row['cleanup_pending']=True


def processor_lease():
    folder=Path.home()/'Documents'/'SportsCavePrintJobs';folder.mkdir(parents=True,exist_ok=True)
    lease=folder/'processor.lock'
    handle=os.open(lease,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(handle)
    return lease


def report_failure(row):
    if not row['context'].get('automatic') or row.get('status')!='Blocked':return
    try:
        import requests
        grant=row['grant']
        response=requests.post(grant['base_url']+'/api/auto-editions/onboarding/fail?'+urlencode({'ticket':grant['ticket']}),
            json=dict(reason=row['error'][:500],repair=bool(row.get('repair'))),
            headers={'X-Sports-Cave-Transfer-Secret':grant['secret']},allow_redirects=False,timeout=30)
        response.raise_for_status()
    except Exception:
        # The durable lease expires into an explicit retryable state; never
        # invent completion when a checkpoint cannot reach the service.
        row['error']+=' The server checkpoint needs reconnection.'


def inspect(key):
    lease=None
    automatic=False
    phase='PSD transfer'
    try:
        from scripts.photoshop_dispatch import run
        row=JOBS[key];grant=row['grant'];meta=row['context']['metadata'];folder=row['folder']
        source=folder/'input.psd'
        manifest=transfer.get(grant,'/api/files-native-transfer/manifest?'+urlencode({'ticket':grant['ticket']}))
        if len(manifest['items'])!=1:raise ValueError('Expected the one linked PSD.')
        item=manifest['items'][0]
        if any(item.get(k)!=meta[v] for k,v in [('dropbox_id','id'),('revision','rev'),('content_hash','content_hash')]):
            raise ValueError('The linked source changed.')
        if not 0<meta['size']<=1024*1024*1024:raise ValueError('Source exceeds the preparation transfer limit.')
        req=Request(grant['base_url']+'/api/files-native-transfer/content?'+urlencode({'ticket':grant['ticket'],'item':item['token']}),
                    headers={'X-Sports-Cave-Transfer-Secret':grant['secret']})
        count=0
        with build_opener(transfer.NoRedirect()).open(req,timeout=300) as response,source.open('xb') as output:
            while block:=response.read(4*1024*1024):
                count+=len(block)
                if count>meta['size']:raise ValueError('Source exceeded its verified size.')
                output.write(block)
        if count!=meta['size'] or transfer.digest(source,True)!=meta['content_hash']:raise ValueError('Source checksum failed.')
        row.setdefault('timings',{})['psd_retrieval_seconds']=round(time.monotonic()-row['created'],3)
        phase='Photoshop inspection'
        lease=processor_lease()
        request=dict(stage_root=str(folder),output_root=str(folder),report_path=str(folder/'inspection.json'),
                     entries=[dict(work_path=str(source),product_gid=row['context']['source']['product_gid'],
                                   dropbox_file_id=meta['id'],dropbox_revision=meta['rev'])],
                     smart_object_depth=0,smart_object_limit=0)
        script='var SC_PSD_INSPECT_REQUEST = '+json.dumps(request)+';\n'
        script+=(transfer.ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
        run(script)
        result=json.loads((folder/'inspection.json').read_text(encoding='utf-8-sig'))['documents'][0]
        row['timings']['inspection_seconds']=round(time.monotonic()-row['created']-row['timings']['psd_retrieval_seconds'],3)
        if 'error' in result:raise ValueError('Photoshop could not inspect the linked source.')
        automatic=bool(row['context'].get('automatic'))
        row.update(status='Working' if automatic else 'Inspected',inspection=result['inspection'])
    except Exception as error:
        JOBS[key].update(status='Blocked',error=phase+' failed: '+type(error).__name__+'. Retry after checking '+('the connection' if phase=='PSD transfer' else 'Photoshop')+'.')
    finally:
        if lease:lease.unlink(missing_ok=True)
    if automatic:
        try:
            from auto_editions_onboarding import detect,preparation_scale
            roles=detect(row['inspection'],row['context']['total'])
            prepare_worker(key,dict(number=roles['number_layer'],plaque=roles['plaque_layer']),
                           preparation_scale(roles['source_dimensions']))
        except Exception as error:
            row.update(status='Blocked',error=str(error),repair=True)
    report_failure(JOBS[key])


def prepare(key,roles,scale=1):
    if type(scale) is not int or scale not in (1,2,3,4):raise ValueError("Unsupported TEST enlargement.")
    with LOCK:
        row=JOBS.get(key)
        if not row or row['status']!='Inspected':raise ValueError('Inspect this design before preparation.')
        if set(roles)!={'number','plaque','matting'} or len(set(roles.values()))!=3:raise ValueError('Confirm three distinct layer roles.')
        selected={}
        for role,name in roles.items():
            matches=[r for r in row['inspection']['layers'] if len(r['path'])==1 and r['path'][0]['name']==name]
            if len(matches)!=1 or matches[0].get('visible') is not True:raise ValueError('Each role must be one visible top-level layer.')
            selected[role]=matches[0]
        if selected['number'].get('kind')!='text' or selected['number'].get('editable') is not True:
            raise ValueError('Select editable edition text.')
        row['status']='Working'
        threading.Thread(target=prepare_worker,args=(key,roles,scale),daemon=True).start()
    return dict(job_id=key,status='Working')


def prepare_worker(key,roles,scale=1):
    lease=None
    try:
        from scripts.prepare_auto_editions import prepare as build
        from auto_editions_package import MAX_PACKAGE_BYTES
        row=JOBS[key];ctx=context(row['grant'])
        if ctx!=row['context']:raise ValueError('Preparation identity changed.')
        lease=processor_lease()
        output=row['folder']/'prepared'
        build_started=time.monotonic()
        build(row['folder']/'input.psd',output,ctx['source'],number_layer=roles['number'],
              plaque_layer=roles['plaque'],total=ctx['total'],reference_number=ctx['number'],scale=scale)
        row.setdefault('timings',{})['prepare_validate_seconds']=round(time.monotonic()-build_started,3)
        if (output/'timings.json').exists():row['timings'].update(json.loads((output/'timings.json').read_text()))
        manifest=json.loads((output/'manifest.json').read_text())
        manifest['confirmed_roles']=roles
        if ctx.get('reset_id'):manifest['reset_request_id']=ctx['reset_id']
        # Adding reviewed role metadata changes the package identity. Server
        # recomputes its own pixel proofs; local proof JSON is never trusted.
        (output/'manifest.json').write_text(json.dumps(manifest))
        names=['manifest.json','master.png','original.png']
        names += [p['name'] for p in manifest['patches'].values()]
        names += [f'reference-{n}.png' for n in sorted({1,ctx['number'],ctx['total']})]
        archive=row['folder']/'prepared.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as package:
            for name in names:package.write(output/name,name)
        if archive.stat().st_size>MAX_PACKAGE_BYTES:raise ValueError('Prepared package exceeds the cloud transfer limit.')
        atomic_json(row['folder']/'preparation-timing.json',dict(source=ctx['source'],
            timings=row.get('timings',{}),prepared_at=time.time()))
        # Photoshop is finished; independent uploads must not occupy its lease.
        lease.unlink(missing_ok=True);lease=None
        upload_prepared(key,archive)
    except Exception as error:
        JOBS[key].update(status='Blocked',error='Preparation failed: '+(str(error)[:350] if isinstance(error,ValueError) else type(error).__name__)+'. Existing PSD and mapping are preserved.')
    finally:
        if lease:lease.unlink(missing_ok=True)


def atomic_json(path,data):
    """Commit the receipt before any destructive cleanup; never truncate the old one."""
    temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as output:
            json.dump(data,output);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def retry_verified_cleanup():
    """Only new durable confirmation receipts authorize cleanup, never a package alone."""
    for receipt in HOST_FILE.parent.glob('*/receipt.json'):
        if receipt.is_symlink() or receipt.parent.is_symlink():continue
        try:
            data=json.loads(receipt.read_text())
            if not isinstance(data,dict):continue
            if data.get('schema')!=2 or data.get('cleanup_complete') is True:continue
            if data.get('status')!='Cloud assets independently verified':continue
            release_verified_temporary_files(dict(folder=receipt.parent,
                preparation_hash=data['preparation_hash'],context={'source':data['source']},
                timings=data.get('timings',{}),server_timings=data.get('server_timings',{}),
                confirmed_at=data['confirmed_at']))
        except (OSError,ValueError,KeyError):continue


def release_verified_temporary_files(row):
    """After cloud confirmation keep the receipt, release this job's staged copies."""
    import re
    folder=row['folder'].resolve()
    owned=(Path.home()/'Documents'/'SportsCaveAutoEditions').resolve()
    if folder.parent!=owned or not re.fullmatch(r'[a-f0-9]{48}',folder.name):
        raise ValueError('Temporary preparation directory is outside its owned root.')
    if not re.fullmatch(r'[a-f0-9]{64}',str(row.get('preparation_hash',''))):
        raise ValueError('Validated preparation identity required before cleanup.')
    receipt=dict(schema=2,preparation_hash=row['preparation_hash'],
        source=row['context']['source'],status='Cloud assets independently verified',
        confirmed_at=row.get('confirmed_at',time.time()),cleanup_complete=False,
        timings=row.get('timings',{}),server_timings=row.get('server_timings',{}))
    atomic_json(folder/'receipt.json',receipt)
    prepared=folder/'prepared'
    if prepared.exists():
        if prepared.is_symlink() or any(p.is_symlink() or not p.resolve().is_relative_to(folder) for p in prepared.rglob('*')):
            raise ValueError('Temporary preparation contains an unexpected link.')
        shutil.rmtree(prepared)
    source=folder/'input.psd'
    if source.exists():
        if source.is_symlink() or source.resolve().parent!=folder:raise ValueError('Unexpected staged source path.')
        source.unlink()
    archive=folder/'prepared.zip'
    if archive.exists():
        if archive.is_symlink() or archive.resolve().parent!=folder:raise ValueError('Unexpected package path.')
        archive.unlink()
    receipt['cleanup_complete']=True
    atomic_json(folder/'receipt.json',receipt)


def action(data):
    kind=data.get('action')
    if kind=='edition-prepare-host' and set(data)=={'action','config'}:return configure_host(data['config'])
    if kind=='edition-prepare-inspect' and set(data)=={'action','grant'}:return start(data['grant'])
    if kind=='edition-prepare-build' and set(data) in ({'action','job_id','roles'},{'action','job_id','roles','scale'}):return prepare(data['job_id'],data['roles'],data.get('scale',1))
    if kind=='edition-prepare-status' and set(data)=={'action','job_id'}:
        row=JOBS.get(data['job_id'])
        if not row or time.monotonic()-row['created']>1800:raise ValueError('Preparation session expired.')
        return dict(job_id=data['job_id'],**{k:row[k] for k in ('status','error','inspection','preparation_hash','repair') if k in row})
    raise ValueError('Unsupported preparation action.')
