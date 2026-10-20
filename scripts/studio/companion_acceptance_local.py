"""Explicit idle-only acceptance inside the installed singleton and upload budget."""
import json,re,threading,time
from pathlib import Path

LOCK=threading.Lock()
THREAD=None
STATE={}

def active():return THREAD is not None and THREAD.is_alive()

def location(host,run):return host.HOST_FILE.parent/'acceptance'/run

def status():
    with LOCK:return dict(STATE)

def start(host,run,*,restored=False):
    global THREAD
    if not re.fullmatch('[a-f0-9]{32}',str(run)):raise ValueError('Exact acceptance run required.')
    with host.LOCK,LOCK:
        if active() or host.HOST_BUSY.is_set() or any(r.get('status')=='Working' or r.get('checkpoint_pending') for r in host.JOBS.values()) or (Path.home()/'Documents/SportsCavePrintJobs/processor.lock').exists():
            raise ValueError('Companion must be idle before acceptance.')
        folder=location(host,run);file=folder/'state.json'
        if restored and (not file.exists() or json.loads(file.read_text()).get('state')!='Awaiting companion restart'):return
        STATE.clear();STATE.update(run=run,state='Starting',restored=restored)
        THREAD=threading.Thread(target=work,args=(host,run,restored),name='isolated-companion-acceptance',daemon=True);THREAD.start()
        host.HOST_WAKE.set()
    return dict(started=True,run=run)

def restore(host):
    # Only an explicitly requested interrupted diagnostic may restart itself.
    for file in (host.HOST_FILE.parent/'acceptance').glob('*/state.json'):
        try:
            data=json.loads(file.read_text())
            if data.get('state')=='Awaiting companion restart':
                def deferred(run=data['run']):
                    for _ in range(60):
                        if host.HOST_STOP.wait(.5):return
                        try:start(host,run,restored=True);return
                        except ValueError:continue
                threading.Thread(target=deferred,name='acceptance-restart',daemon=True).start();return
        except (OSError,ValueError,KeyError):continue

def work(host,run,restored):
    from device_trust import protect
    from companion_package_client import upload
    from companion_acceptance_fixture import build
    import requests
    folder=location(host,run);folder.mkdir(parents=True,exist_ok=True)
    config=json.loads(protect(host.HOST_FILE.read_bytes(),decrypt=True))
    controller=host.transfer_controller();original=dict(controller.value);revision=controller.revision
    traces=[];controls=[];started=time.monotonic()
    def save(state,**kwargs):
        with LOCK:
            STATE.update(state=state,**kwargs)
            host.atomic_json(folder/'state.json',dict(STATE))
    def ping(loaded=False,progress=None):
        before=time.monotonic();value=host.host_request(config,'/api/auto-editions/acceptance/ping',{})
        controls.append(dict(loaded=loaded,application_progress_at_start=progress,milliseconds=round((time.monotonic()-before)*1000,3)));return value
    def trace(value):
        # Payload telemetry only; never persist host/grant/provider capabilities.
        traces.append({k:v for k,v in value.items() if isinstance(v,(int,float,bool)) or k in ('state','failure_class')})
        traces[:]=traces[-6:]
    try:
        for _ in range(3):ping()
        archive=folder/'packet'/'package.zip'
        if not archive.exists():archive=build(folder/'packet',run)
        grant=dict(base_url=config['base_url'],ticket='isolated-acceptance',secret='isolated-no-grant',upload_path='/api/auto-editions/acceptance/')
        if restored:
            # Exercise the real safe-boundary pause without changing mode.
            controller.configure({**original,'paused':True},revision)
            def resume():
                controller.configure(original,revision)
            threading.Timer(.5,resume).start()
        save('Uploading',package_bytes=archive.stat().st_size)
        monitor_stop=threading.Event()
        def loaded_controls():
            from companion_package_identity import CHUNK
            # At most three independent controls during an actual body handoff.
            # Never start another transfer or infer raw connection capacity.
            for _ in range(100):
                if monitor_stop.wait(.1):return
                with controller.cv:
                    current=controller.active or {};progress=current.get('progress_bytes',0)
                    transferring=current.get('state')=='Uploading' and 0<progress<CHUNK
                if transferring:
                    try:ping(True,progress)
                    except Exception:return
                    if sum(c['loaded'] for c in controls)>=3:return
        monitor=threading.Thread(target=loaded_controls,name='acceptance-controls',daemon=True);monitor.start()
        try:
            result=upload(controller,archive,grant,config,folder/'upload-session.json',correlation=run,
                stopped=host.HOST_STOP.is_set,on_trace=trace,poll_interval=3,verification_timeout=600)
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code!=503:raise
            if not restored:
                save('Awaiting companion restart',elapsed_seconds=time.monotonic()-started,traces=traces,controls=controls)
                host.atomic_json(folder/'attempt-1.json',status())
                return
            # Lost finalisation acknowledgement: resume the same durable journal.
            ping(True)
            result=upload(controller,archive,grant,config,folder/'upload-session.json',correlation=run,
                stopped=host.HOST_STOP.is_set,on_trace=trace,poll_interval=3,verification_timeout=600)
        if result.get('status')!='Cloud Ready' or result.get('verified_assets')!=101:raise ValueError('Isolated cloud verification is incomplete.')
        journal=json.loads((folder/'upload-session.json').read_text())
        response=requests.post(config['base_url']+'/api/auto-editions/acceptance/evidence',params={'id':journal['id']},json={},
            headers={'X-Sports-Cave-Preparation-Host':config['token']},timeout=(20,180),allow_redirects=False)
        response.raise_for_status();evidence=response.json()
        for _ in range(2):ping()
        save('Cloud Ready',elapsed_seconds=time.monotonic()-started,result=result,evidence=evidence,traces=traces,controls=controls)
    except Exception as error:
        save('Failed',error_type=type(error).__name__,traces=traces,controls=controls)
    finally:
        if 'monitor_stop' in locals():monitor_stop.set();monitor.join(timeout=21)
        if controller.value!=original:controller.configure(original,revision)
