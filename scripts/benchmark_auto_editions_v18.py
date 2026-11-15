"""Offline synthetic pipeline benchmark. No Photoshop, credentials or providers.

python scripts/benchmark_auto_editions_v18.py --mode legacy --output output/v18/baseline.json
Repeat with --mode v18 against the same deterministic fixtures and process budget.
Loopback pacing is a local experiment, never a measurement of Dropbox throughput.
"""
import argparse,base64,hashlib,http.client,json,math,os,random,shutil,statistics,sys,tempfile,threading,time,zipfile
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.getenv('AUTO_EDITIONS_BENCH_CODE_ROOT'):sys.path.insert(0,os.environ['AUTO_EDITIONS_BENCH_CODE_ROOT'])
from PIL import Image,ImageCms
import psutil
import auto_editions as ae
from auto_editions_package import unpack

def summary(values):
    values=sorted(values)
    return dict(median=statistics.median(values),p95=values[max(0,math.ceil(.95*len(values))-1)])

def fixture(root,width,height):
    policies=json.loads((Path(__file__).resolve().parents[1]/'config/auto_editions/icc-policies-20261016.json').read_text())
    icc=base64.b64decode(policies[0]['icc_base64']) # Fixed public ICC bytes, identical in both runs.
    region=[20,20,120,40]
    with Image.frombytes('RGB',(width,height),random.Random(18).randbytes(width*height*3)) as master:
        master.save(root/'master.png',icc_profile=icc,compress_level=1)
        for n in range(1,101):
            with Image.new('RGB',(100,20),(n,255-n,n)) as patch:
                patch.save(root/f'number-{n}.png',icc_profile=icc)
        for n in (1,100):
            with master.copy() as ref,Image.open(root/f'number-{n}.png') as patch:
                ref.paste(patch,(20,20));ref.save(root/f'reference-{n}.png',icc_profile=icc,compress_level=1)
    shutil.copyfile(root/'reference-1.png',root/'original.png')
    asset=lambda n:dict(name=n,sha256=ae.file_hash(root/n))
    manifest=dict(schema_version=1,strategy='photoshop_number_patches',source=ae.source_identity('gid://shopify/Product/1800',dict(id='id:synthetic',rev='a18',content_hash='a'*64)),
                  dimensions=[width,height],source_dimensions=[width,height],upscaled=False,number_region=region,edition_total=100,
                  master=asset('master.png'),patches={str(n):asset(f'number-{n}.png') for n in range(1,101)},
                  colour_evidence=dict(icc_sha256=hashlib.sha256(icc).hexdigest(),pixels_converted=False))
    (root/'manifest.json').write_text(json.dumps(manifest))
    return manifest,['manifest.json','master.png','original.png']+[f'number-{n}.png' for n in range(1,101)]+['reference-1.png','reference-100.png']

def legacy_pack(root,names,destination):
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_STORED) as z:
        for name in names:z.write(root/name,name)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['legacy','v18'],required=True)
    p.add_argument('--output',required=True);p.add_argument('--repeats',type=int,default=3);p.add_argument('--mib-per-second',type=float,default=16)
    args=p.parse_args();assert 1<=args.repeats<=10 and args.mib_per_second>0
    result=dict(mode=args.mode,fixture_seed=18,repeats=args.repeats,loopback_pacing_mib_s=args.mib_per_second,production_requests=0,photoshop_opened=False,cases=[])
    process=psutil.Process();cpu0=sum(process.cpu_times()[:2]);wall=time.perf_counter();peak=[process.memory_info().rss];stop=threading.Event()
    if sys.platform=='win32':process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    def sample():
        while not stop.wait(.1):peak[0]=max(peak[0],process.memory_info().rss)
    sampler=threading.Thread(target=sample,daemon=True);sampler.start()
    try:
        with tempfile.TemporaryDirectory(prefix='sc-v18-bench-') as temp:
            base=Path(temp)
            for label,size in [('small',(640,480)),('medium',(1600,1200)),('large',(2835,2004))]:
                root=base/label;root.mkdir();manifest,names=fixture(root,*size)
                original_hashes={n:ae.file_hash(root/n) for n in names};runs=[]
                for iteration in range(args.repeats):
                    archive=base/f'{label}-{iteration}.zip';received=base/'received.zip'
                    tick=time.perf_counter()
                    if args.mode=='legacy':legacy_pack(root,names,archive)
                    else:
                        from auto_editions_transport import build_package
                        build_package(root,names,archive,compact=True)
                    packaging=time.perf_counter()-tick
                    class Handler(BaseHTTPRequestHandler):
                        def log_message(self,*a):pass
                        def do_POST(self):
                            remaining=int(self.headers['Content-Length'])
                            with received.open('wb') as output:
                                while remaining:
                                    chunk=self.rfile.read(min(256*1024,remaining));assert chunk
                                    output.write(chunk);remaining-=len(chunk)
                                    time.sleep(len(chunk)/(args.mib_per_second*1024**2))
                            self.send_response(200);self.end_headers()
                    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.handle_request);thread.start()
                    tick=time.perf_counter();connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=60)
                    try:
                        with archive.open('rb') as body:connection.request('POST','/',body,headers={'Content-Length':str(archive.stat().st_size)})
                        response=connection.getresponse();assert response.status==200;response.read()
                    finally:connection.close();thread.join();server.server_close()
                    transfer=time.perf_counter()-tick;tick=time.perf_counter()
                    with tempfile.TemporaryDirectory(dir=base) as assets:
                        actual,proofs=unpack(received,assets,manifest['source'],1,100)
                        assert ae.fingerprint(actual)==ae.fingerprint(manifest)
                        assert all(x.get('pixel_exact',x.get('outside_number_exact',False)) for x in proofs)
                        assert all(ae.file_hash(Path(assets)/n)==h for n,h in original_hashes.items())
                        # Count the full logical file footprint while both ZIPs
                        # and every reconstructed server asset are present.
                        footprint=sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
                        result['peak_temporary_disk_bytes']=max(result.get('peak_temporary_disk_bytes',0),footprint)
                    validation=time.perf_counter()-tick
                    runs.append(dict(package_seconds=packaging,transfer_seconds=transfer,validation_seconds=validation,
                                     total_seconds=packaging+transfer+validation,package_bytes=archive.stat().st_size,
                                     transfer_mib_s=archive.stat().st_size/1024**2/transfer))
                    archive.unlink();received.unlink()
                assert all(ae.file_hash(root/n)==h for n,h in original_hashes.items())
                case=dict(size=label,dimensions=size,fixture_fingerprint=ae.fingerprint(manifest),runs=runs,summary={k:summary([r[k] for r in runs]) for k in runs[0]},
                          all_imported_bytes_identical=True,all_icc_and_pixel_proofs_passed=True,original_files_unchanged=True)
                result['cases'].append(case);print(json.dumps(case['summary']),flush=True)
            result['temporary_disk_bytes']=sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
    finally:stop.set();sampler.join()
    result.update(peak_process_rss_bytes=peak[0],cpu_seconds=sum(process.cpu_times()[:2])-cpu0,wall_seconds=time.perf_counter()-wall,
                  free_disk_bytes=shutil.disk_usage('.').free,photoshop_scratch_available_bytes=None)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2))

if __name__=='__main__':main()
