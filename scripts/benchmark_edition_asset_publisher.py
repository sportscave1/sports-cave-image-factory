"""Compare real publisher/SDK adapter paths using synthetic PNGs and RPC latency.

No credentials or network calls. This measures request overhead, not Dropbox
capacity, throughput or a prediction of production completion time.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import auto_editions as ae
import dropbox_integration as integration
from auto_editions_cloud import DropboxAssets
from scripts.benchmark_auto_editions_v18 import fixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('baseline_cloud',Path(args.baseline_root)/'auto_editions_cloud.py')
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    runs=[]
    with tempfile.TemporaryDirectory(prefix='edition-publisher-simulator-') as temporary:
        root=Path(temporary);manifest,_=fixture(root,320,240)
        assets=[manifest['master'],*manifest['patches'].values()]
        digest=ae.fingerprint(manifest)
        for existing in (0,50,101):
            for mode,cls in [('baseline',baseline.DropboxAssets),('phase3',DropboxAssets)]:
                for repeat in range(3):
                    records={};counts={};lock=threading.Lock();active=0;maximum=0
                    def rpc(kind):
                        nonlocal active,maximum
                        with lock:
                            counts[kind]=counts.get(kind,0)+1;active+=1;maximum=max(maximum,active)
                        time.sleep(.01)
                        with lock:active-=1
                    def row(path,data):
                        import hashlib
                        blocks=b''.join(hashlib.sha256(data[i:i+4*1024**2]).digest() for i in range(0,len(data),4*1024**2))
                        return dict(id='id:'+path,rev='synthetic',size=len(data),path_lower=path.lower(),
                                    name=Path(path).name,content_hash=hashlib.sha256(blocks).hexdigest())
                    for asset in assets[:existing]:
                        path=DropboxAssets.path(digest,asset['name']);records[path]=row(path,(root/asset['name']).read_bytes())
                    class Client:
                        def clone(self,**kwargs):return self
                        def files_upload(self,data,path,**kwargs):
                            rpc('upload');assert path not in records and not kwargs['autorename']
                            records[path]=row(path,data);return records[path]
                    def metadata(token,path):rpc('metadata');return records.get(path)
                    def listing(*args,**kwargs):rpc('listing');return dict(entries=list(records.values()),has_more=False)
                    with patch.object(integration,'team_space_client',return_value=Client()), \
                            patch.object(integration,'ensure_folder_path'), \
                            patch.object(integration,'get_metadata_if_exists',side_effect=metadata), \
                            patch.object(integration,'list_folder_page',side_effect=listing):
                        started=time.perf_counter()
                        receipts=cls('synthetic-only',integration).publish_preparation(manifest,root)
                        elapsed=time.perf_counter()-started
                    assert len(receipts['assets'])==len(records)==101 and maximum<=3
                    runs.append(dict(mode=mode,existing=existing,seconds=elapsed,calls=counts,max_concurrency=maximum))
    summaries=[]
    for existing in (0,50,101):
        medians={mode:statistics.median(r['seconds'] for r in runs if r['mode']==mode and r['existing']==existing)
                 for mode in ('baseline','phase3')}
        summaries.append(dict(existing=existing,median_seconds=medians,
                              reduction_percent=100*(1-medians['phase3']/medians['baseline'])))
    result=dict(simulated_rpc_ms=10,production_calls=0,runs=runs,summaries=summaries)
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result['summaries'],indent=2))


if __name__=='__main__':main()
