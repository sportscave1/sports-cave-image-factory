"""Cheap stage measurements, kept outside immutable artwork manifests."""
import hashlib,os,shutil,time
from contextlib import contextmanager
from pathlib import Path

def file_hashes(path):
    full=hashlib.sha256();dropbox=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):
            full.update(block);dropbox.update(hashlib.sha256(block).digest())
    return dict(sha256=full.hexdigest(),dropbox=dropbox.hexdigest())

def resources(metrics,path):
    """Process lifetime peak where supported; never guesses Photoshop scratch."""
    try:
        import psutil
        process=psutil.Process()
        with process.oneshot():
            memory=process.memory_info();cpu=process.cpu_times()
        metrics['process_rss_bytes']=memory.rss
        metrics['process_peak_rss_bytes']=max(metrics.get('process_peak_rss_bytes',0),getattr(memory,'peak_wset',memory.rss))
        metrics['process_cpu_seconds']=round(cpu.user+cpu.system,3)
        metrics['system_available_ram_bytes']=psutil.virtual_memory().available
        metrics['temporary_volume_free_bytes']=shutil.disk_usage(Path(path).resolve()).free
        # Read-only process counters; no COM calls or changes to Photoshop.
        for candidate in psutil.process_iter(['name']):
            if (candidate.info.get('name') or '').lower()!='photoshop.exe':continue
            try:
                with candidate.oneshot():memory=candidate.memory_info();cpu=candidate.cpu_times()
                metrics.update(photoshop_pid=candidate.pid,photoshop_process_rss_bytes=memory.rss,
                               photoshop_process_peak_rss_bytes=getattr(memory,'peak_wset',memory.rss),
                               photoshop_process_cpu_seconds=round(cpu.user+cpu.system,3))
            except psutil.Error:pass
            break
    except (ImportError,OSError):pass # Telemetry must not block artwork preparation.

@contextmanager
def stage(metrics,name,*,path=None):
    prior={}
    if name=='photoshop_prepare' and path is not None:resources(prior,path)
    start=time.perf_counter();cpu=time.process_time()
    try:yield
    finally:
        metrics[name+'_seconds']=round(time.perf_counter()-start,6)
        metrics[name+'_cpu_seconds']=round(time.process_time()-cpu,6)
        if path is not None:resources(metrics,path)
        if prior.get('photoshop_pid') and prior['photoshop_pid']==metrics.get('photoshop_pid'):
            metrics['photoshop_prepare_process_cpu_seconds']=round(metrics['photoshop_process_cpu_seconds']-prior['photoshop_process_cpu_seconds'],3)

def throughput(metrics,bytes_key,seconds_key,prefix):
    seconds=metrics.get(seconds_key,0)
    if seconds>0:metrics[prefix+'_mib_s']=round(metrics.get(bytes_key,0)/1024**2/seconds,4)
