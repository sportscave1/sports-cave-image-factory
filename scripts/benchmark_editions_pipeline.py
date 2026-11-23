"""Synthetic scheduler replay. No Photoshop/provider/production access."""
from pathlib import Path
import json
import sys
import tempfile
import statistics
import threading
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/studio'))
import auto_editions_local as local
from companion_transfer import Controller
from edition_pipeline import released_upload


def replay(overlap, jobs=12):
    native_max=upload_max=native_count=upload_count=0
    guard=threading.Lock();wire=threading.Lock();threads=[];receipts=[]
    with tempfile.TemporaryDirectory(prefix='editions-pipeline-') as temporary:
        root=Path(temporary);host=root/'Documents/SportsCaveAutoEditions';host.mkdir(parents=True)
        def inspect(key):
            nonlocal native_count,native_max,upload_count,upload_max
            threads.append(threading.current_thread());row=local.JOBS[key]
            lease=local.processor_lease()
            with guard:native_count+=1;native_max=max(native_max,native_count)
            time.sleep(.04)
            with guard:native_count-=1
            lease.unlink();row['native_released']=True;row['phase']='Uploading'
            with wire:
                with guard:upload_count+=1;upload_max=max(upload_max,upload_count)
                time.sleep(.08)
                receipts.append((row['context']['source'],key))
                with guard:upload_count-=1
            row['status']='Prepared'
        controller=Controller()
        with patch.object(Path,'home',return_value=root),patch.object(local,'HOST_FILE',host/'host.dpapi'), \
                patch.object(local,'JOBS',{}),patch.object(local,'inspect',side_effect=inspect), \
                patch.object(local,'find_reusable_package',return_value=None), \
                patch.object(local,'package_finished',return_value=None), \
                patch.object(local,'transfer_controller',return_value=controller):
            started=time.monotonic();number=0
            while number<jobs or any(r['status']=='Working' for r in local.JOBS.values()):
                active=[r for r in local.JOBS.values() if r['status']=='Working']
                if number<jobs and (not active or overlap and len(active)==1 and released_upload(active[0])):
                    context=dict(automatic=True,source=f'synthetic:{number}')
                    local.start({},initial_context=context,upload_protocol=1,pipeline=bool(active))
                    number+=1
                time.sleep(.001)
            elapsed=time.monotonic()-started
            for thread in threads:thread.join(2)
        assert len(receipts)==jobs and len(set(source for source,key in receipts))==jobs
        assert len(set(key for source,key in receipts))==jobs and native_max==upload_max==1
        return dict(seconds=elapsed,jobs=jobs,simulated_jobs_per_hour=jobs/elapsed*3600,
                    native_max=native_max,upload_max=upload_max)


if __name__=='__main__':
    replay(False,2) # Warm imports before comparing either mode.
    samples=[dict(serial=replay(False),overlap=replay(True)) for _ in range(3)]
    result=dict(samples=samples,production_calls=0)
    result['median_seconds']={mode:statistics.median(row[mode]['seconds'] for row in samples) for mode in ('serial','overlap')}
    result['elapsed_reduction_percent']=100*(1-result['median_seconds']['overlap']/result['median_seconds']['serial'])
    print(json.dumps(result,indent=2))
