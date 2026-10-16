"""Read retained verified archives; rebuild only disposable local copies.

No Photoshop, Dropbox or production database calls. Retained inputs are hashed
before and after. Baseline/V18 alternate against the same extracted bytes.
"""
import argparse,json,shutil,statistics,sys,tempfile,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psutil
import auto_editions as ae
from auto_editions_package import unpack
from auto_editions_transport import build_package

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--index',required=True);p.add_argument('--output',required=True);p.add_argument('--repeats',type=int,default=3);args=p.parse_args()
    process=psutil.Process()
    if sys.platform=='win32':process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    rows=sorted(json.loads(Path(args.index).read_text()),key=lambda r:Path(r['package_path']).stat().st_size)
    selected=[rows[0],rows[len(rows)//2],rows[-1]];result=[]
    for row in selected:
        archive=Path(row['package_path']);before=ae.file_hash(archive);assert before==row['package_sha256']
        if psutil.virtual_memory().available<4*1024**3:raise RuntimeError('Insufficient idle RAM for retained-package benchmark.')
        with tempfile.TemporaryDirectory(prefix='sc-v18-retained-') as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();manifest,proofs=unpack(archive,source,row['source'],1,100)
            names=['manifest.json','master.png','original.png']+[a['name'] for a in manifest['patches'].values()]+['reference-1.png','reference-100.png']
            expected={n:ae.file_hash(source/n) for n in names};runs=[]
            for repeat in range(args.repeats):
                for compact in ([False,True] if repeat%2==0 else [True,False]):
                    output=root/f'{repeat}-{compact}.zip';tick=time.perf_counter();packet=build_package(source,names,output,compact=compact)
                    build=time.perf_counter()-tick;tick=time.perf_counter()
                    with tempfile.TemporaryDirectory(dir=root) as expanded:
                        actual,proofs=unpack(output,expanded,row['source'],1,100)
                        assert ae.fingerprint(actual)==row['preparation_hash']
                        assert all(ae.file_hash(Path(expanded)/n)==h for n,h in expected.items())
                    validate=time.perf_counter()-tick
                    runs.append(dict(compact=compact,package_seconds=build,validation_seconds=validate,package_bytes=output.stat().st_size,
                                     shared_bytes=packet['shared_bytes'],references_shared=packet['references_shared']))
                    output.unlink()
            result.append(dict(original_package_bytes=archive.stat().st_size,dimensions=manifest['dimensions'],
                               runs=runs,all_reconstructed_bytes_exact=True,all_pixel_icc_checks_passed=True,original_archive_unchanged=ae.file_hash(archive)==before,
                               peak_process_rss_bytes=getattr(process.memory_info(),'peak_wset',process.memory_info().rss)))
        Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result[-1]),flush=True)

if __name__=='__main__':main()
