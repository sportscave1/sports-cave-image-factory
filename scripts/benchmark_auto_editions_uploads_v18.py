"""Deterministic provider simulator; measures request reduction, NOT live Dropbox."""
import argparse,importlib.util,json,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import auto_editions as ae
from auto_editions_cloud import DropboxAssets
from scripts.benchmark_auto_editions_v18 import fixture

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline-root',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    spec=importlib.util.spec_from_file_location('baseline_upload',Path(args.baseline_root)/'auto_editions_cloud.py');baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='v18-upload-simulator-') as tmp:
        root=Path(tmp);manifest,names=fixture(root,320,240)
        assets=[manifest['master'],*manifest['patches'].values()];digest=ae.fingerprint(manifest)
        for existing_count in (0,50,101):
            for cls in (baseline.DropboxAssets,DropboxAssets):
                for repeat in range(3):
                    class Integration:
                        def __init__(self):self.records={};self.calls=[];self.lock=threading.Lock()
                        def call(self,kind):
                            with self.lock:self.calls.append(kind)
                            time.sleep(.005)
                        def row(self,path,local):return dict(name=local.name,path_lower=path.lower(),id='id:'+local.stem,rev='a18',size=local.stat().st_size,content_hash=ae.file_hash(local,dropbox=True))
                        def ensure_folder_path(self,*a,**k):pass
                        def get_metadata_if_exists(self,token,path):self.call('metadata');return self.records.get(path)
                        def list_folder_page(self,token,path,limit):self.call('listing');return dict(entries=list(self.records.values()),has_more=False)
                        def upload_local_file(self,token,path,local,conflict):
                            assert conflict=='cancel' and path not in self.records
                            self.call('upload');r=self.row(path,local);self.records[path]=r;return r
                    integration=Integration()
                    for a in assets[:existing_count]:
                        path=DropboxAssets.path(digest,a['name']);integration.records[path]=integration.row(path,root/a['name'])
                    start=time.perf_counter();receipts=cls('synthetic-only',integration).publish_preparation(manifest,root)
                    assert len(receipts['assets'])==101
                    rows.append(dict(mode='baseline' if cls is baseline.DropboxAssets else 'v18',existing_assets=existing_count,
                                     duration_seconds=time.perf_counter()-start,metadata_calls=integration.calls.count('metadata'),
                                     listing_calls=integration.calls.count('listing'),upload_calls=integration.calls.count('upload')))
    Path(args.output).write_text(json.dumps(dict(simulated_latency_ms=5,production_calls=0,runs=rows),indent=2));print(json.dumps(rows))

if __name__=='__main__':main()
