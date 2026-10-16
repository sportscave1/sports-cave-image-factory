"""Exclusive LOCAL Photoshop benchmark. No provider access or production jobs.

Refuses even idle production companions before any COM/lock/fixture operation.
Candidate is experimental; only real 100-patch comparisons can establish gains.
"""
import argparse,json,math,os,statistics,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if __name__=='__main__':
    # prepare() imports this guard by package name. Keep one exception/ownership
    # implementation when the runner itself was launched as a script.
    sys.modules.setdefault('scripts.benchmark_auto_editions_native_v19',sys.modules[__name__])
import auto_editions as ae

class BenchmarkBlocked(RuntimeError):pass

def preflight(*,home=None,processes=None):
    import psutil
    home=Path.home() if home is None else Path(home)
    processes=list(psutil.process_iter(['pid','name','cmdline'])) if processes is None else processes
    hosts=[];photoshop=[];unknown=[]
    for item in processes:
        try:
            info=item if isinstance(item,dict) else item.info
            name=(info.get('name') or '').lower();args=info.get('cmdline')
            if name=='photoshop.exe':photoshop.append(info['pid'])
            if name not in ('python.exe','pythonw.exe'):continue
            if args is None:unknown.append(info['pid']);continue
            command=' '.join(args).lower()
            if any(marker in command for marker in ('run_icc_companion.py','auto_editions_local.py','edition_test_local.py','local_print_test.py')):hosts.append(info['pid'])
        except psutil.Error:unknown.append(getattr(item,'pid',None))
    status_path=home/'Documents/SportsCaveAutoEditions/host-status.json';state=None
    try:
        status=json.loads(status_path.read_text(encoding='utf-8'));state=status.get('status')
        # A host launcher may have an unfamiliar filename. Its recorded live PID
        # is sufficient to block admission independently of command matching.
        pid=status.get('companion_pid')
        if any((p if isinstance(p,dict) else p.info).get('pid')==pid for p in processes) and pid not in hosts:hosts.append(pid)
    except (OSError,ValueError):pass
    lock=home/'Documents/SportsCavePrintJobs/processor.lock'
    reasons=[]
    if hosts:reasons.append('An Auto Editions/print companion process is running; production is not interrupted for benchmarking.')
    if unknown:reasons.append('Some Python process ownership is unreadable; exclusive Photoshop admission cannot be proven.')
    if lock.exists():reasons.append('The existing Photoshop processor lock is held or uncertain.')
    return dict(allowed=not reasons,reasons=reasons,companion_pids=hosts,unreadable_pids=unknown,photoshop_pids=photoshop,
                observed_host_state=state,processor_lock_present=lock.exists(),photoshop_executed=False,production_mutated=False,
                available_ram_bytes=psutil.virtual_memory().available,temporary_volume_free_bytes=__import__('shutil').disk_usage(ROOT).free,
                photoshop_scratch_available_bytes=None)

def require_admission(check=None):
    report=preflight() if check is None else check
    if not report['allowed']:raise BenchmarkBlocked(' '.join(report['reasons']))
    if report['available_ram_bytes']<4*1024**3 or report['temporary_volume_free_bytes']<8*1024**3:
        raise BenchmarkBlocked('Insufficient verified RAM or temporary storage for a native benchmark.')
    return report

def processor_lease():
    # Same lock and owner-checked release as the installed execution architecture;
    # import only, never start or change a companion.
    sys.path.insert(0,str(ROOT/'scripts/studio'))
    from auto_editions_local import processor_lease as acquire
    return acquire()

def require_native_owner(source,output):
    """A JSON request flag alone cannot bypass exclusive benchmark admission."""
    boundary=(ROOT/'output/v19').resolve()
    if not Path(source).resolve().is_relative_to(boundary) or not Path(output).resolve().is_relative_to(boundary):
        raise BenchmarkBlocked('Native benchmark sources and outputs must remain inside this task output/v19 directory.')
    check=preflight();check['reasons']=[r for r in check['reasons'] if not r.startswith('The existing Photoshop processor lock')]
    check['allowed']=not check['reasons'];require_admission(check)
    try:
        value=json.loads((Path.home()/'Documents/SportsCavePrintJobs/processor.lock').read_text())
        if value.get('pid')!=os.getpid() or not isinstance(value.get('owner'),str) or not value['owner']:
            raise ValueError('Not this benchmark owner')
    except (OSError,ValueError,AttributeError) as error:
        raise BenchmarkBlocked('This benchmark process does not own the existing Photoshop processor lease.') from error

def cleanup_proven(root,name='native-status.json'):
    try:return json.loads((Path(root)/name).read_text(encoding='utf-8-sig')).get('owned_document_closed') is True
    except (OSError,ValueError):return False

class Sample:
    def __init__(self,root):self.root=Path(root);self.stop=threading.Event();self.peak_rss=0;self.peak_ps_rss=0;self.peak_disk=0;self.peak_cpu_cores=0;self.observations=0
    def __enter__(self):
        import psutil
        self.process=psutil.Process();self.cpu_start=sum(self.process.cpu_times()[:2]);self.started=time.perf_counter();self.ps_cpu={}
        def sample():
            previous={};previous_tick=time.perf_counter()
            while not self.stop.is_set():
                try:
                    rss=self.process.memory_info().rss;ps_rss=0;current={}
                    for p in psutil.process_iter(['name']):
                        if (p.info.get('name') or '').lower()!='photoshop.exe':continue
                        try:ps_rss+=p.memory_info().rss;current[p.pid]=sum(p.cpu_times()[:2])
                        except psutil.Error:pass
                    now=time.perf_counter();delta=sum(max(0,v-previous[k]) for k,v in current.items() if k in previous)
                    if now>previous_tick:self.peak_cpu_cores=max(self.peak_cpu_cores,delta/(now-previous_tick))
                    previous=current;previous_tick=now
                    for k,v in current.items():self.ps_cpu.setdefault(k,[v,v])[1]=v
                    self.peak_rss=max(self.peak_rss,rss);self.peak_ps_rss=max(self.peak_ps_rss,ps_rss)
                    self.observations+=1
                    if self.observations%10==1:self.peak_disk=max(self.peak_disk,sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))
                except (OSError,psutil.Error):pass
                self.stop.wait(0.1)
        self.thread=threading.Thread(target=sample,daemon=True);self.thread.start();return self
    def __exit__(self,*a):
        self.stop.set();self.thread.join()
        try:self.peak_disk=max(self.peak_disk,sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))
        except OSError:pass
    def result(self):
        return dict(wall_seconds=time.perf_counter()-self.started,companion_cpu_seconds=sum(self.process.cpu_times()[:2])-self.cpu_start,
                    photoshop_cpu_seconds=sum(v[1]-v[0] for v in self.ps_cpu.values()),sampled_peak_cpu_cores=self.peak_cpu_cores,
                    peak_companion_rss_bytes=self.peak_rss,peak_photoshop_rss_bytes=self.peak_ps_rss,peak_logical_temporary_disk_bytes=self.peak_disk,samples=self.observations)

def exact_outputs(left,right,total=100):
    """Decode every patch/master/reference; no similarity thresholds or ICC conversion."""
    from PIL import Image,ImageChops
    from auto_editions_colour_source import profile_info
    a=json.loads((Path(left)/'manifest.json').read_text());b=json.loads((Path(right)/'manifest.json').read_text())
    fields=('source','dimensions','source_dimensions','number_region','plaque_bounds','original_number_bounds','original_text','font','edition_total','resolution','source_modified','upscaled','preparation_geometry','number_layer_name','plaque_layer_name','print_ready')
    if any(a.get(k)!=b.get(k) for k in fields):raise ValueError('Native preparation identity or geometry differs.')
    if a['edition_total']!=total or b['edition_total']!=total:raise ValueError('Complete numbered range required.')
    for manifest,root in ((a,left),(b,right)):
        for asset in [manifest['master'],*manifest['patches'].values()]:ae.asset_path(root,asset)
    names=['original.png','master.png']+[f'number-{n}.png' for n in range(1,total+1)]
    names += sorted(p.name for p in Path(left).glob('reference-*.png'))
    for name in names:
        with Image.open(Path(left)/name) as original,Image.open(Path(right)/name) as candidate:
            original.load();candidate.load()
            if original.mode!='RGB' or candidate.mode!='RGB' or candidate.size!=original.size:raise ValueError('Native mode or geometry differs: '+name)
            if not original.info.get('icc_profile') or original.info.get('icc_profile')!=candidate.info.get('icc_profile'):raise ValueError('Native ICC bytes differ: '+name)
            profile_info(original.info['icc_profile'])
            # Conservatively require all exported PNG metadata. Native volatile
            # XMP differences must be reviewed, never silently discarded here.
            if original.info!=candidate.info:raise ValueError('Required native metadata differs: '+name)
            with ImageChops.difference(original,candidate) as difference:
                if difference.getbbox() is not None:raise ValueError('Native pixels differ: '+name)
    preview='edition-001-TEST-NOT-PRINT-READY.jpg'
    from PIL import JpegImagePlugin
    for root in (left,right):
        with Image.open(Path(root)/preview) as image:
            if (image.format!='JPEG' or image.mode!='RGB' or list(image.size)!=a['dimensions'] or image.info.get('dpi')!=(300,300)
                    or JpegImagePlugin.get_sampling(image)!=0 or any(v!=1 for table in image.quantization.values() for v in table)):
                raise ValueError('Native preview JPEG quality or geometry differs.')
    if ae.file_hash(Path(left)/preview)!=ae.file_hash(Path(right)/preview):raise ValueError('Native preview JPEG bytes differ.')
    return dict(files_compared=len(names)+1,all_100_patches_pixel_exact=total==100,icc_exact=True,required_metadata_exact=True,jpeg_bytes_exact=True)

def summary(values):
    values=sorted(values)
    return dict(samples=len(values),median=statistics.median(values),p95=values[max(0,math.ceil(len(values)*0.95)-1)])

def benchmark(root,*,repeats=3,width=2835,height=2004):
    root=Path(root).resolve()
    if not root.is_relative_to(ROOT/'output/v19') or root.exists():raise ValueError('Use a new task-local output/v19 benchmark directory.')
    require_admission();lease=processor_lease();uncertain=False;result=dict(real_photoshop=True,comparable_measurement_complete=False,native_speedup_established=False,recommended_for_release=False,runs=[],comparisons=[],failures=[])
    try:
        # Recheck after acquiring the same non-stealable Photoshop lock. Our own
        # lock is expected; a newly started companion still blocks before COM.
        admitted=preflight();admitted['reasons']=[r for r in admitted['reasons'] if not r.startswith('The existing Photoshop processor lock')]
        admitted['allowed']=not admitted['reasons'];require_admission(admitted)
        root.mkdir(parents=True);source=root/'synthetic-100.psd'
        from scripts.photoshop_dispatch import run
        script=(ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
        script+='\nvar SC_V19_FIXTURE_REQUEST='+json.dumps(dict(root=str(root),path=str(source),width=width,height=height))+';\n'
        script+=(ROOT/'scripts/photoshop/benchmark_auto_editions_fixture.jsx').read_text(encoding='utf-8-sig')
        uncertain=True
        try:
            if run(script)!='V19_SYNTHETIC_FIXTURE_CREATED':raise ValueError('Synthetic Photoshop fixture was not confirmed.')
        finally:uncertain=not cleanup_proven(root,'fixture-status.json')
        if uncertain:raise BenchmarkBlocked('Synthetic fixture cleanup is unproven; processor lock retained.')
        source_sha=ae.file_hash(source);identity=dict(product_gid='gid://shopify/Product/190000001',file_id='id:local-v19-synthetic',revision='190001',content_hash=ae.file_hash(source,dropbox=True))
        from scripts.prepare_auto_editions import prepare,native_cleanup_uncertain
        for repetition in range(repeats):
            paths={}
            order=('duplicate_merged','history_merged_crop') if repetition%2==0 else ('history_merged_crop','duplicate_merged')
            for strategy in order:
                # Never proceed if a host appeared between independent trials.
                admission=preflight();admission['reasons']=[r for r in admission['reasons'] if not r.startswith('The existing Photoshop processor lock')];admission['allowed']=not admission['reasons'];require_admission(admission)
                output=root/(str(repetition)+'-'+strategy);uncertain=True;started=time.perf_counter()
                try:
                    with Sample(output) as sample:
                        prepare(source,output,identity,number_layer='SC_EDITION_NUMBER',plaque_layer='SC_EDITION_PLAQUE',total=100,reference_number=1,scale=1,export_strategy=strategy,native_benchmark=True)
                except BenchmarkBlocked:
                    # These admission errors are raised before any export COM
                    # call. They do not require an invented cleanup receipt.
                    uncertain=False;raise
                finally:
                    uncertain=native_cleanup_uncertain(output)
                if uncertain:raise BenchmarkBlocked('Native export cleanup is unproven; processor lock retained.')
                if ae.file_hash(source)!=source_sha:raise ValueError('Synthetic source PSD changed during the benchmark.')
                timings=json.loads((output/'timings.json').read_text());paths[strategy]=output
                resources=sample.result();resources['source_fixture_bytes']=source.stat().st_size
                resources['peak_logical_total_bytes']=resources['peak_logical_temporary_disk_bytes']+source.stat().st_size
                result['runs'].append(dict(repetition=repetition,strategy=strategy,elapsed_seconds=time.perf_counter()-started,timings=timings,resources=resources))
            result['comparisons'].append(exact_outputs(paths['duplicate_merged'],paths['history_merged_crop']))
        result['summary']={strategy:{'local_prepare_seconds':summary([r['elapsed_seconds'] for r in result['runs'] if r['strategy']==strategy]),
            'photoshop_seconds':summary([r['timings']['photoshop_prepare_seconds'] for r in result['runs'] if r['strategy']==strategy]),
            'number_exports_seconds':summary([r['timings']['numbering_assets_ms']/1000 for r in result['runs'] if r['strategy']==strategy])} for strategy in ('duplicate_merged','history_merged_crop')}
        for value in result['summary'].values():value['local_designs_per_hour']=3600/value['local_prepare_seconds']['median']
        result['comparable_measurement_complete']=True
        result['native_speedup_established']=result['summary']['history_merged_crop']['local_prepare_seconds']['median']<result['summary']['duplicate_merged']['local_prepare_seconds']['median']
        return result
    except Exception as error:
        result['failures'].append(dict(type=type(error).__name__,message=str(error)));raise
    finally:
        try:
            if root.exists():(root/'native-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:
            if not uncertain:lease.unlink()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preflight',action='store_true');parser.add_argument('--output-root');parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.preflight:print(json.dumps(preflight(),indent=2));return
    if not args.output_root or args.repeats<3:parser.error('A new task-local output root and at least three repeated native trials are required.')
    try:print(json.dumps(benchmark(args.output_root,repeats=args.repeats),indent=2))
    except BenchmarkBlocked as error:print(json.dumps(dict(blocked=True,reason=str(error),photoshop_speedup_claimed=False)));raise SystemExit(2)
if __name__=='__main__':main()
