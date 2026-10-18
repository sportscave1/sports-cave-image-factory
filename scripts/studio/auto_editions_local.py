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
HOST_WAKE=threading.Event()
HOST_LAST_COMPLETED_AT=None
HOST_BUSY=threading.Event()
HOST_FILE=Path.home()/'Documents'/'SportsCaveAutoEditions'/'preparation-host.dpapi'
RECOVERY_CURSOR=0
HOST_RETRY_AT=0
HOST_FAILURES=0
HOST_LAST_DIAGNOSTIC=None


def health_payload():
    import hashlib
    active=next((r for r in list(JOBS.values()) if r.get('status')=='Working'),None)
    retained=next((r for r in list(JOBS.values()) if r.get('checkpoint_pending') or r.get('status')=='Recovering'),{})
    row=active or retained;stage=row.get('phase','Unknown')
    if stage not in ('Claimed','Photoshop','Preparing','Uploading','Verifying','Review'):stage='Recovery' if retained else 'Unknown'
    if row and row.get('_last_stage')!=stage:row['_last_stage']=stage;row['last_progress_at']=time.time()
    marker=transfer.ROOT/'AUTO_EDITIONS_INSTALLED_RELEASE.json'
    try:revision=json.loads(marker.read_text()).get('revision','local')
    except (OSError,ValueError):revision='local'
    locked=(Path.home()/'Documents/SportsCavePrintJobs/processor.lock').exists()
    result=dict(state='Recovering' if HOST_FAILURES or retained or locked and not active else 'Live' if active else 'Idle',
        stage=stage,revision=revision,protocol=1,code_hash=hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').replace('\r\n','\n').encode()).hexdigest(),
        product_gid=row.get('context',{}).get('product_gid'),last_progress_at=row.get('last_progress_at',row.get('started_at',0)),
        retry_at=max(HOST_RETRY_AT,row.get('retry_at',0)),recovery_failures=max(HOST_FAILURES,row.get('recovery_failures',0)),
        checkpoint_pending=bool(row.get('checkpoint_pending')),processor_lock=locked and not bool(active))
    if row.get('diagnostic') or HOST_LAST_DIAGNOSTIC:result['diagnostic']=row.get('diagnostic') or HOST_LAST_DIAGNOSTIC
    return result


class Cancelled(Exception):
    pass


def cancellation_check(row, *, stopped=False, config=None):
    """Check only this lease. Acknowledge only after its workers have unwound."""
    if not row.get('context',{}).get('automatic'):return False
    if config is None:
        if not HOST_FILE.exists():raise ConnectionError('Companion host connection is required to check cancellation.')
        from device_trust import protect
        config=json.loads(protect(HOST_FILE.read_bytes(),decrypt=True))
    ctx=row['context']
    result=host_request(config,'/api/auto-editions/onboarding/cancellation',
        dict(product_gid=ctx['product_gid'],lease_token=ctx['lease_token'],stopped=stopped))
    if result.get('cancelled') is True:
        row['cancel_requested']=True
        if stopped:
            row.update(status='Cancelled',checkpoint_pending=False,cancellation_confirmed=True,error='Cancelled for Reset; source and generated files retained.')
            journal(row)
        return True
    return False


def boundary(row):
    if row.get('cancel_requested') or cancellation_check(row):raise Cancelled()


def cancellable(operation):
    """Nested stages share a worker count; no acknowledgement during COM/upload."""
    from functools import wraps
    @wraps(operation)
    def guarded(key,*args,**kwargs):
        row=JOBS[key]
        with LOCK:row['workers']=row.get('workers',0)+1
        try:
            boundary(row)
            return operation(key,*args,**kwargs)
        except Cancelled:
            row['cancel_requested']=True
        except Exception:
            row.update(status='Recovering',error='Companion cancellation check needs reconnection.')
            journal(row)
        finally:
            with LOCK:
                row['workers']-=1
                stopped=row['workers']==0
            if stopped and row.get('cancel_requested'):
                row.update(status='Cancelled',checkpoint_pending=False)
                journal(row)
                try:cancellation_check(row,stopped=True)
                except Exception:pass # Durable pending request is retried by host recovery.
    return guarded


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


def journal(row):
    if not row.get('context',{}).get('automatic'):return
    atomic_json(row['folder']/'job-state.json',dict(schema=1,context=row['context'],
        package_transport=row.get('package_transport',0),
        phase=row.get('phase','Preparing'),status=row['status'],error=row.get('error',''),
        cancellation_confirmed=bool(row.get('cancellation_confirmed')),
        repair=bool(row.get('repair')),checkpoint_pending=bool(row.get('checkpoint_pending')),
        started_at=row.setdefault('started_at',time.time()),retry_at=row.get('retry_at',0),recovery_failures=row.get('recovery_failures',0),diagnostic=row.get('diagnostic')))


def host_request(config,path,body):
    import requests
    if path.rsplit('/',1)[-1] in ('claim','heartbeat','reconnect'):body={**body,'health':health_payload()}
    response=requests.post(config['base_url']+path,json=body,
        headers={'X-Sports-Cave-Preparation-Host':config['token']},allow_redirects=False,timeout=20)
    response.raise_for_status();return response.json()


def sync_colour_configuration(config):
    # Only the authenticated app supplies approvals. Atomic local snapshots are
    # shared by inspection and preparation; an active job never refreshes them.
    value=host_request(config,'/api/auto-editions/onboarding/colour-configuration',{})
    from auto_editions_colour_policy import validate
    if set(value)!={'policies','memberships','default_group'} or len(value['policies'])>200 or len(value['memberships'])>1000:
        raise ValueError('Invalid colour configuration.')
    for policy in value['policies']:validate(policy)
    root=HOST_FILE.parent/'colour-configuration';root.mkdir(exist_ok=True)
    for key,name in (('policies','AUTO_EDITIONS_COLOUR_POLICIES_FILE'),('memberships','AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE')):
        path=root/(key+'.json');atomic_json(path,value[key]);os.environ[name]=str(path)
    os.environ['AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT']=value['default_group']


def recover_retained(config):
    # No grants/secrets in journals. Reissue only the same host-owned lease.
    # Rotate the bounded read window: retained completed history must never hide
    # an older interrupted package once the continuous catalogue grows past 20.
    global RECOVERY_CURSOR
    files=sorted(HOST_FILE.parent.glob('*/job-state.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    cursor_start=RECOVERY_CURSOR%len(files) if files else 0
    window=(files[cursor_start:]+files[:cursor_start])[:20]
    RECOVERY_CURSOR=(cursor_start+len(window))%len(files) if files else 0
    for file in window:
        if file.is_symlink() or file.parent.is_symlink():continue
        try:
            if file.stat().st_size>4*1024*1024:continue
            data=json.loads(file.read_text());ctx=data['context']
            if not isinstance(ctx,dict) or data.get('status') not in ('Working','Recovering','Prepared','Blocked','Cancelled'):continue
            if not ctx.get('automatic') or not all(k in ctx for k in ('source','product_gid','lease_token')):continue
        except (OSError,ValueError,KeyError,TypeError):continue
        if data['status'] in ('Prepared','Blocked') and not data.get('checkpoint_pending'):continue
        if data['status']=='Cancelled' and data.get('cancellation_confirmed'):continue
        retained=dict(context=ctx,folder=file.parent,status=data['status'])
        if any(r.get('context',{}).get('lease_token')==ctx['lease_token'] and r.get('workers',0)>0 for r in list(JOBS.values())):continue
        if cancellation_check(retained,config=config):
            if (Path.home()/'Documents'/'SportsCavePrintJobs'/'processor.lock').exists():return True
            cancellation_check(retained,stopped=True,config=config);continue
        if data['status']=='Cancelled':continue
        if time.time()<data.get('retry_at',0)<=time.time()+300:return True
        heartbeat={k:ctx[k] for k in ('product_gid','lease_token')}
        try:
            try:result=host_request(config,'/api/auto-editions/onboarding/reconnect',heartbeat)
            except Exception as error:
                response=getattr(error,'response',None)
                if response is None or response.status_code not in (400,409):raise
                host_request(config,'/api/auto-editions/onboarding/heartbeat',dict(heartbeat,stage='Recovering'))
                result=host_request(config,'/api/auto-editions/onboarding/reconnect',heartbeat)
        except Exception as error:
            # Superseded/finished leases cannot be resurrected. Source/approval conflicts remain terminal.
            response=getattr(error,'response',None)
            if response is not None and response.status_code in (400,403,409):
                data.update(status='Blocked',checkpoint_pending=False,error='Lease or source changed; package retained for review.')
                atomic_json(file,data);continue
            raise
        if result.get('completed'):
            if result['completed']['source']!=ctx['source']:raise ValueError('Completed source changed.')
            row=dict(context=ctx,folder=file.parent,status='Prepared',created=time.monotonic())
            finish_upload(row,result['completed'],time.monotonic());journal(row);return True
        if data.get('checkpoint_pending'):
            row=dict(data,grant=result['grant'],folder=file.parent)
            report_failure(row);return True
        start(result['grant'],resume_folder=file.parent,package_transport=result.get('package_transport',0))
        return True
    return False


def host_loop():
    global HOST_FAILURES,HOST_RETRY_AT,HOST_LAST_DIAGNOSTIC
    from device_trust import protect
    failures=0
    while not HOST_STOP.is_set():
        HOST_WAKE.clear()
        with LOCK:
            if HOST_STOP.is_set():return
            HOST_BUSY.set()
        delay=30
        try:
            config=json.loads(protect(HOST_FILE.read_bytes(),decrypt=True))
            if config['base_url'] not in transfer.ALLOWED_ORIGINS:return
            active=[r for r in list(JOBS.values()) if r['status']=='Working']
            state='Companion Connected'
            if active:
                row=active[0];stage=row.get('phase','Preparing')
                if cancellation_check(row,config=config):
                    state='Cancelling'
                    if not row.get('workers',0) and not (Path.home()/'Documents'/'SportsCavePrintJobs'/'processor.lock').exists():
                        cancellation_check(row,stopped=True,config=config)
                    HOST_BUSY.clear();HOST_STOP.wait(delay);continue
                # A stuck COM call keeps its processor lock. Never steal it or renew forever.
                if time.time()-row.get('started_at',time.time())>2700:
                    state='Failed';raise RuntimeError('Preparation exceeded the recovery window; inspect Photoshop. Lock retained.')
                state=stage
                host_request(config,'/api/auto-editions/onboarding/heartbeat',
                    dict(product_gid=row['context']['product_gid'],lease_token=row['context']['lease_token'],stage=stage))
            elif (Path.home()/'Documents'/'SportsCavePrintJobs'/'processor.lock').exists():
                state='Recovering'
                host_request(config,'/api/auto-editions/onboarding/heartbeat',{})
            elif shutil.disk_usage(HOST_FILE.parent).free<8*1024**3:
                raise RuntimeError('Preparation storage is low.')
            elif recover_retained(config):state='Recovering'
            else:
                retry_verified_cleanup()
                sync_colour_configuration(config)
                claim_started=time.monotonic()
                data=host_request(config,'/api/auto-editions/onboarding/claim',{})
                if data.get('grant'):
                    started=start(data['grant'],initial_context=data.get('context'),package_transport=data.get('package_transport',0))
                    timings=JOBS[started['job_id']].setdefault('timings',{})
                    timings['claim_seconds']=round(time.monotonic()-claim_started,6)
                    if HOST_LAST_COMPLETED_AT is not None:timings['completed_to_claim_request_seconds']=round(claim_started-HOST_LAST_COMPLETED_AT,6)
                    state='Preparing'
                elif data.get('product_mockup_renders') is True:
                    import sys
                    from product_upload_render_local import run_one
                    if run_one(config,sys.modules[__name__]):state='Rendering product mockups'
            failures=0
            HOST_FAILURES=0;HOST_RETRY_AT=0;HOST_LAST_DIAGNOSTIC=None
            atomic_json(HOST_FILE.parent/'host-status.json',dict(last_poll=time.time(),status=state,
                companion_pid=os.getpid(),version='unattended-recovery-v1'))
        except Exception as error:
            failures=min(failures+1,5);delay=min(30*2**(failures-1),300)
            HOST_FAILURES=failures;HOST_RETRY_AT=time.time()+delay
            HOST_LAST_DIAGNOSTIC=safe_diagnostic(str(error) if isinstance(error,ValueError) else type(error).__name__,'Recovery')
            try:atomic_json(HOST_FILE.parent/'host-status.json',dict(last_poll=time.time(),status='Recovering',
                error_type=type(error).__name__,retry_seconds=delay,companion_pid=os.getpid()))
            except OSError:pass
        HOST_BUSY.clear()
        HOST_WAKE.wait(delay)


def prepare_stop():
    """Existing Close must not kill a daemon upload or an in-flight host claim."""
    with LOCK:
        if HOST_BUSY.is_set() or any(r.get('status')=='Working' or r.get('checkpoint_pending') for r in JOBS.values()):
            raise ValueError('Preparation is active or checkpointing. Wait for it to finish before stopping this companion.')
        HOST_STOP.set()
        HOST_WAKE.set()


def context(grant):
    import re
    if (not isinstance(grant,dict) or set(grant)!={'base_url','ticket','secret'}
            or grant['base_url'] not in transfer.ALLOWED_ORIGINS
            or not re.fullmatch(r'[A-Za-z0-9_-]{32}',grant['ticket'])
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}',grant['secret'])):
        raise ValueError('A scoped administrator preparation grant is required.')
    return transfer.get(grant,'/api/auto-editions/context?'+urlencode({'ticket':grant['ticket']}))


def start(grant,resume_folder=None,initial_context=None,package_transport=0):
    verified=initial_context or context(grant)
    with LOCK:
        for key,row in list(JOBS.items()):
            if time.monotonic()-row['created']>1800 and row['status']!='Working':JOBS.pop(key,None)
        # Durable server checkpoints retain completed automatic jobs. They must
        # not exhaust the eight interactive-session slots during a fast batch.
        for key,row in list(JOBS.items()):
            if row['context'].get('automatic') and row['status'] in ('Prepared','Blocked','Cancelled'):
                JOBS.pop(key,None)
        if any(row['status']=='Working' for row in JOBS.values()):raise ValueError('A preparation is already running.')
        if len(JOBS)>=8:raise ValueError('Too many preparation sessions. Retry later.')
        key=resume_folder.name if resume_folder else secrets.token_hex(24)
        folder=Path.home()/'Documents'/'SportsCaveAutoEditions'/key
        if resume_folder:
            if folder.resolve()!=resume_folder.resolve() or json.loads((folder/'job-state.json').read_text())['context']!=verified:
                raise ValueError('Retained preparation identity changed.')
        else:folder.mkdir(parents=True,exist_ok=False)
        JOBS[key]=dict(grant=grant,context=verified,folder=folder,created=time.monotonic(),status='Working',
                       package_transport=1 if type(package_transport) is int and package_transport==1 else 0)
        if resume_folder:JOBS[key]['recovery_failures']=json.loads((folder/'job-state.json').read_text()).get('recovery_failures',0)
        journal(JOBS[key])
        package=find_reusable_package(verified)
        if not package and resume_folder:package=package_finished(row=JOBS[key],ctx=verified)
        if package:
            JOBS[key]['reused_package']=str(package)
            timing_file=package.parent/'preparation-timing.json'
            if timing_file.exists() and not timing_file.is_symlink():
                try:
                    saved=json.loads(timing_file.read_text())
                    if saved.get('source')==verified['source']:
                        JOBS[key]['timings']=saved.get('timings',{})
                except (OSError,ValueError):pass
            threading.Thread(target=upload_prepared,args=(key,package),daemon=True).start()
        else:threading.Thread(target=inspect,args=(key,),daemon=True).start()
        return dict(job_id=key,status='Working')


def package_finished(row,ctx):
    """A crash after Photoshop/validation must not rerender a verified finished set."""
    import auto_editions as ae
    from auto_editions_onboarding import preparation_scale
    from auto_editions_package import MAX_PACKAGE_BYTES
    for folder in row['folder'].glob('prepared*'):
        if not folder.is_dir() or folder.is_symlink():continue
        try:
            manifest=json.loads((folder/'manifest.json').read_text())
            if (manifest['source']!=ctx['source'] or manifest['edition_total']!=ctx['total']
                or not manifest.get('confirmed_roles') or
                manifest.get('preparation_geometry',{}).get('scale',1)!=preparation_scale(manifest.get('source_dimensions',manifest['dimensions']))
                or (ctx.get('reset_id') and manifest.get('reset_request_id')!=ctx['reset_id'])):continue
            ae.validate_manifest(manifest)
            from auto_editions_artwork_recovery import verify_package
            verify_package(folder,manifest)
            refs=sorted({1,ctx['number'],ctx['total']})
            for n in refs:ae.compare_reference(manifest,folder,n,folder/f'reference-{n}.png')
            ae.compare_original_outside_number(manifest,folder,ctx['number'],folder/'original.png')
            names=['manifest.json','master.png','original.png']+[p['name'] for p in manifest['patches'].values()]+[f'reference-{n}.png' for n in refs]
            if (manifest.get('artwork_recovery') or {}).get('hidden_number'):names.append('uncorrected.png')
            archive=row['folder']/'prepared.zip'
            if archive.exists():return None
            from auto_editions_transport import build_package
            build_package(folder,names,archive,compact=row.get('package_transport')==1)
            return archive
        except (OSError,ValueError,KeyError):continue
    return None


def find_reusable_package(ctx):
    """Only reuse exact source/edition identities. The server revalidates pixels."""
    if not ctx.get('automatic'):return None
    from auto_editions_package import MAX_PACKAGE_BYTES
    root=HOST_FILE.parent.resolve()
    for package in sorted(root.glob('*/prepared.zip'),key=lambda p:p.stat().st_mtime,reverse=True):
        if package.is_symlink() or package.parent.is_symlink():continue
        try:
            if package.stat().st_size>MAX_PACKAGE_BYTES:continue
            with zipfile.ZipFile(package) as archive:
                if archive.getinfo('manifest.json').file_size>4*1024*1024:continue
                if sum(info.file_size for info in archive.infolist())>MAX_PACKAGE_BYTES:continue
                manifest=json.loads(archive.read('manifest.json'))
            colour=manifest.get('colour_evidence') or {}
            import re
            if not re.fullmatch('[a-f0-9]{64}',str(colour.get('icc_sha256',''))) or colour.get('pixels_converted') is not False:continue
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
        json={**{k:ctx[k] for k in ('product_gid','lease_token')},'health':health_payload()},
        headers={'X-Sports-Cave-Preparation-Host':config['token']},allow_redirects=False,timeout=90)
    response.raise_for_status();data=response.json()
    if data.get('completed'):
        if data['completed'].get('source')!=ctx['source']:raise ValueError('Completed source changed.')
        return data['completed']
    row['grant']=data['grant']
    if context(row['grant'])!=ctx:raise ValueError('Preparation identity changed.')


@cancellable
def upload_prepared(key,archive):
    """Retry transfer after deploy without repeating Photoshop or source download."""
    import requests
    row=JOBS[key];started=time.monotonic()
    row.setdefault('folder',archive.parent)
    row['phase']='Uploading';journal(row)
    row.setdefault('timings',{}).update(package_bytes=archive.stat().st_size,upload_attempts=0)
    try:
        for attempt in range(3):
            try:
                boundary(row)
                grant=row['grant']
                row['timings']['upload_attempts']+=1
                with archive.open('rb',buffering=1024*1024) as content:
                    response=requests.post(grant['base_url']+'/api/auto-editions/package?'+urlencode({'ticket':grant['ticket']}),
                        data=content,headers={'X-Sports-Cave-Transfer-Secret':grant['secret'],'Content-Type':'application/zip'},
                        allow_redirects=False,timeout=600)
                boundary(row)
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
    except Cancelled:raise
    except Exception as error:
        response=getattr(error,'response',None)
        transient=isinstance(error,requests.RequestException) and (response is None or response.status_code>=500)
        row.update(status='Recovering' if transient else 'Blocked',error='Prepared package retained; upload/checkpoint failed: '+type(error).__name__)
        if transient:
            row['recovery_failures']=row.get('recovery_failures',0)+1
            if row['recovery_failures']>=3:
                transient=False;row.update(status='Blocked',error='Upload recovery exhausted after three cycles; verified package retained.')
            row['retry_at']=time.time()+min(30*2**min(row['recovery_failures']-1,4),300)
        journal(row)
        if not transient:report_failure(row)


def finish_upload(row,result,started):
    global HOST_LAST_COMPLETED_AT
    row.update(status='Prepared',preparation_hash=result['preparation_hash'])
    row.setdefault('timings',{})['upload_validate_seconds']=round(time.monotonic()-started,3)
    from auto_editions_performance import throughput,resources
    throughput(row['timings'],'package_bytes','upload_validate_seconds','upload_end_to_end')
    resources(row['timings'],row['folder'])
    row['server_timings']=result.get('timings',{})
    row['checkpoint_pending']=False; journal(row)
    if row['context'].get('automatic'):
        try:release_verified_temporary_files(row)
        except (OSError,ValueError):row['cleanup_pending']=True
    HOST_LAST_COMPLETED_AT=time.monotonic()
    HOST_WAKE.set()


class OwnedProcessorLease:
    def __init__(self,path,owner):self.path,self.owner=path,owner
    def unlink(self,missing_ok=False):
        try:
            if json.loads(self.path.read_text()).get('owner')!=self.owner:
                raise RuntimeError('Processor lock ownership changed; lock retained.')
            self.path.unlink()
        except FileNotFoundError:
            if not missing_ok:raise


def processor_lease():
    folder=Path.home()/'Documents'/'SportsCavePrintJobs';folder.mkdir(parents=True,exist_ok=True)
    lease=folder/'processor.lock';owner=secrets.token_hex(16)
    handle=os.open(lease,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    with os.fdopen(handle,'w') as output:
        json.dump(dict(owner=owner,pid=os.getpid(),created_at=time.time()),output);output.flush();os.fsync(output.fileno())
    return OwnedProcessorLease(lease,owner)


def report_failure(row):
    if row.get('cancel_requested') or row.get('status')=='Cancelled':return
    if not row['context'].get('automatic') or row.get('status')!='Blocked' or row.get('checkpoint_reported'):return
    row['checkpoint_pending']=True; journal(row)
    try:
        import requests
        reconnect(row)
        grant=row['grant']
        response=requests.post(grant['base_url']+'/api/auto-editions/onboarding/fail?'+urlencode({'ticket':grant['ticket']}),
            json=dict(reason=row['error'][:500],repair=bool(row.get('repair')),diagnostic=row.get('diagnostic') or safe_diagnostic(row['error'],row.get('phase','Unknown'))),
            headers={'X-Sports-Cave-Transfer-Secret':grant['secret']},allow_redirects=False,timeout=30)
        response.raise_for_status()
        row['checkpoint_pending']=False; row['checkpoint_reported']=True; journal(row)
        HOST_WAKE.set()
    except Exception:
        row['recovery_failures']=row.get('recovery_failures',0)+1
        row['retry_at']=time.time()+min(30*2**min(row['recovery_failures']-1,4),300)
        journal(row)
        # The durable lease expires into an explicit retryable state; never
        # invent completion when a checkpoint cannot reach the service.
        row['error']+=' The server checkpoint needs reconnection.'


@cancellable
def inspect(key):
    lease=None
    automatic=False
    phase='PSD transfer'
    try:
        from scripts.photoshop_dispatch import run
        row=JOBS[key];grant=row['grant'];meta=row['context']['metadata'];folder=row['folder']
        row['phase']='Claimed'
        source=folder/'input.psd'
        manifest=transfer.get(grant,'/api/files-native-transfer/manifest?'+urlencode({'ticket':grant['ticket']}))
        if len(manifest['items'])!=1:raise ValueError('Expected the one linked PSD.')
        item=manifest['items'][0]
        if any(item.get(k)!=meta[v] for k,v in [('dropbox_id','id'),('revision','rev'),('content_hash','content_hash')]):
            raise ValueError('The linked source changed.')
        from auto_editions_source_limits import check_source
        check_source(meta['size'],folder)
        req=Request(grant['base_url']+'/api/files-native-transfer/content?'+urlencode({'ticket':grant['ticket'],'item':item['token']}),
                    headers={'X-Sports-Cave-Transfer-Secret':grant['secret']})
        from auto_editions_local_cache import reuse_source,cached_inspection,inspection_receipt
        from auto_editions_performance import file_hashes
        cached=reuse_source(HOST_FILE.parent,source,row['context']['source'],meta['size'])
        complete=bool(cached)
        if source.exists() and not complete:source.rename(source.with_name('input.incomplete-'+secrets.token_hex(6)+'.psd'))
        count=meta['size'] if complete else 0
        if not complete:
            with build_opener(transfer.NoRedirect()).open(req,timeout=300) as response,source.open('xb') as output:
                while block:=response.read(4*1024*1024):
                    count+=len(block)
                    if count>meta['size']:raise ValueError('Source exceeded its verified size.')
                    output.write(block)
        hashes=cached or file_hashes(source)
        if count!=meta['size'] or hashes['dropbox']!=meta['content_hash']:raise ValueError('Source checksum failed.')
        row.setdefault('timings',{})['psd_retrieval_seconds']=round(time.monotonic()-row['created'],3)
        row['timings'].update(source_bytes=meta['size'],source_transfer_bytes=0 if complete else count,source_reused=complete)
        boundary(row)
        phase='Photoshop inspection'
        row['phase']='Photoshop';journal(row)
        from auto_editions_colour_source import inspect_psd,ColourReview
        colour=inspect_psd(source)
        request=dict(stage_root=str(folder),output_root=str(folder),report_path=str(folder/'inspection.json'),
                     entries=[dict(work_path=str(source),product_gid=row['context']['source']['product_gid'],
                                   dropbox_file_id=meta['id'],dropbox_revision=meta['rev'])],
                     smart_object_depth=0,smart_object_limit=0)
        inspector=(transfer.ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
        inspector_hash=__import__('hashlib').sha256(inspector.replace('\r\n','\n').encode()).hexdigest()
        inspection=cached_inspection(folder,row['context']['source'],hashes['sha256'],inspector_hash)
        row['timings']['inspection_reused']=inspection is not None
        boundary(row)
        if inspection is None:
            lease=processor_lease()
            script='var SC_PSD_INSPECT_REQUEST = '+json.dumps(request)+';\n'+inspector
            boundary(row)
            run(script)
            boundary(row)
            inspection=json.loads((folder/'inspection.json').read_text(encoding='utf-8-sig'))
            if not inspection['documents'][0].get('error'):
                atomic_json(folder/'inspection-cache.json',inspection_receipt(folder,row['context']['source'],hashes['sha256'],inspector_hash))
        result=inspection['documents'][0]
        row['timings']['inspection_seconds']=round(time.monotonic()-row['created']-row['timings']['psd_retrieval_seconds'],3)
        if 'error' in result:raise ColourReview('Inspector failure: Photoshop could not inspect the linked source.')
        document=result['inspection']['document']
        if colour['state']=='untagged':
            document['observed_profile']=document.get('profile')
            document['observed_profile_state']=document.get('profile_state')
            document.update(profile=None,profile_state='untagged')
        elif document.get('profile_state')!='tagged':
            raise ColourReview('Inspector failure: embedded PSD profile was not retained by Photoshop.')
        elif document.get('profile') not in (colour['profile']['name'],colour['profile']['description']):
            raise ColourReview('ICC export mismatch: Photoshop did not retain the embedded source profile.')
        automatic=bool(row['context'].get('automatic'))
        row.update(status='Working' if automatic else 'Inspected',inspection=result['inspection'])
    except Cancelled:raise
    except Exception as error:
        from urllib.error import URLError
        transient=phase=='PSD transfer' and isinstance(error,(URLError,TimeoutError,ConnectionError))
        detail=failure_detail(JOBS[key],phase,error)
        JOBS[key].update(status='Recovering' if transient else 'Blocked',error=phase+' failed: '+detail)
        journal(JOBS[key])
    finally:
        if lease:lease.unlink(missing_ok=True)
    if automatic:
        try:
            from auto_editions_onboarding import detect,preparation_scale
            from auto_editions_colour_policy import resolve
            policy=None
            if row['inspection']['document'].get('profile_state')=='untagged':
                _,policy=resolve(row['context']['source'])
            roles=detect(row['inspection'],row['context']['total'],colour_policy=policy,source=row['context']['source'])
            prepare_worker(key,dict(number=roles['number_layer'],plaque=roles['plaque_layer']),
                           preparation_scale(roles['source_dimensions']))
        except Exception as error:
            from auto_editions_onboarding import NeedsRepair
            row.update(status='Blocked',error=failure_detail(row,'Photoshop',error),repair=isinstance(error,NeedsRepair))
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


def failure_detail(row,stage,error):
    """Retain Photoshop's cause locally; never put paths/capabilities in status."""
    import re
    message=str(error)[:4000]
    row['diagnostic']=safe_diagnostic(message,'Preparing')
    for value in [*row.get('grant',{}).values(),row.get('context',{}).get('lease_token')]:
        if isinstance(value,str) and len(value)>8:message=message.replace(value,'[redacted]')
    message=re.sub(r'https?://[^\s]+','[redacted URL]',message)
    try:
        atomic_json(row['folder']/'failure-detail.json',dict(stage=stage,error_type=type(error).__name__,
            message=message,product_gid=row.get('context',{}).get('product_gid'),recorded_at=time.time()))
    except OSError:pass
    if isinstance(error,RuntimeError):
        if 'source_profile_requires_review' in message or 'colour_conversion_requires_approval' in message:
            row['repair']=False
            return 'Colour policy awaiting approval: original PSD colour settings require owner review.'
        if 'profile_inspector_failure' in message:return 'Inspector failure: Photoshop colour metadata could not be read.'
        if 'export_profile_changed' in message:return 'ICC export mismatch: Photoshop changed the document profile.'
        if 'scratch' in message.lower():return 'Photoshop scratch disk failure; inspect free scratch storage.'
        return 'Photoshop preparation failed; inspect the retained local failure-detail.json.'
    return str(error)[:350] if isinstance(error,ValueError) else type(error).__name__


def safe_diagnostic(message,stage):
    from worker_diagnostics import explain
    value=explain(message,stage)
    result={k:value[k] for k in ('code','stage','component')}
    marker=transfer.ROOT/'AUTO_EDITIONS_INSTALLED_RELEASE.json'
    try:result['revision']=json.loads(marker.read_text()).get('revision','local')
    except (OSError,ValueError):result['revision']='local'
    return result


@cancellable
def prepare_worker(key,roles,scale=1):
    lease=None;output=None
    try:
        from scripts.prepare_auto_editions import prepare as build
        from auto_editions_package import MAX_PACKAGE_BYTES
        row=JOBS[key];ctx=context(row['grant'])
        row['phase']='Preparing';journal(row)
        if ctx!=row['context']:raise ValueError('Preparation identity changed.')
        lease=processor_lease()
        output=row['folder']/'prepared'
        if output.exists():output=row['folder']/('prepared-recovery-'+secrets.token_hex(6))
        boundary(row)
        build_started=time.monotonic()
        build(row['folder']/'input.psd',output,ctx['source'],number_layer=roles['number'],
              plaque_layer=roles['plaque'],total=ctx['total'],reference_number=ctx['number'],scale=scale)
        row.setdefault('timings',{})['prepare_validate_seconds']=round(time.monotonic()-build_started,3)
        boundary(row)
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
        if (manifest.get('artwork_recovery') or {}).get('hidden_number'):names.append('uncorrected.png')
        archive=row['folder']/'prepared.zip'
        from auto_editions_transport import build_package,digest
        from auto_editions_performance import stage as measured
        with measured(row['timings'],'package_build',path=output):
            packet=build_package(output,names,archive,compact=row.get('package_transport')==1)
        row['timings'].update(packet)
        with measured(row['timings'],'package_checksum'):
            packet_hash=digest(archive)
        atomic_json(row['folder']/'preparation-timing.json',dict(source=ctx['source'],
            timings=row.get('timings',{}),package_sha256=packet_hash,prepared_at=time.time()))
        # Photoshop is finished; independent uploads must not occupy its lease.
        lease.unlink(missing_ok=True);lease=None
        upload_prepared(key,archive)
    except Cancelled:raise
    except Exception as error:
        detail=failure_detail(JOBS[key],'Preparation',error)
        JOBS[key].update(status='Blocked',error='Preparation failed: '+detail+'. Existing PSD and mapping are preserved.')
    finally:
        if lease:
            from scripts.prepare_auto_editions import native_cleanup_uncertain
            if output is not None and native_cleanup_uncertain(output):
                JOBS[key]['error']+=' Photoshop cleanup is unproven; processor lock retained for owner review.'
                JOBS[key]['diagnostic']=safe_diagnostic('processor lock ownership is uncertain','Recovery')
                journal(JOBS[key])
            else:lease.unlink(missing_ok=True)
    report_failure(JOBS[key])


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
