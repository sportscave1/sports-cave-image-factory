"""Matched capped loopback measurements; no providers or Photoshop calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_companion_phase2_transfers import receiver
from scripts.benchmark_companion_phase1 import Sample
import companion_transfer as candidate


def benchmark(output, rates=(1,10,50,100), repeats=3):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'output') or output.exists():
        raise ValueError('Use a new task-local report directory.')
    output.mkdir(parents=True)
    baseline=output/'released_transfer.py'
    baseline.write_bytes(subprocess.check_output(['git','show','58569c66:companion_transfer.py'],cwd=ROOT))
    spec=importlib.util.spec_from_file_location('released_transfer',baseline)
    released=importlib.util.module_from_spec(spec);spec.loader.exec_module(released)
    result=dict(baseline='58569c66',local_only=True,wire_bytes_measured=False,runs=[])
    try:
        for rate in rates:
            # At least 1.5s at the cap, bounded to 20 MiB. No full-file buffering.
            size=max(256*1024,min(20*1024**2,int(rate*1e6/8*1.5)))
            path=output/'payload.bin';path.write_bytes(bytes(range(256))*(size//256));size=path.stat().st_size
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            for pair in range(repeats):
                for name in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
                    module=released if name=='baseline' else candidate
                    controller=module.Controller();controller.configure(dict(mode='Manual',manual_mbps=rate))
                    waits=dict(count=0,requested=0.,elapsed=0.,max_overshoot=0.)
                    original=controller.cv.wait
                    def wait(seconds=None):
                        start=time.monotonic();value=original(seconds);elapsed=time.monotonic()-start
                        waits['count']+=1;waits['requested']+=seconds or 0;waits['elapsed']+=elapsed
                        waits['max_overshoot']=max(waits['max_overshoot'],elapsed-(seconds or 0));return value
                    controller.cv.wait=wait
                    stop=threading.Event();beats=[]
                    with receiver() as (url,rows,_):
                        import requests
                        def control():
                            while not stop.wait(.05):
                                begin=time.monotonic()
                                requests.post(url+'/heartbeat',data=b'x',timeout=2).raise_for_status()
                                beats.append(time.monotonic()-begin)
                        thread=threading.Thread(target=control);thread.start()
                        try:
                            with Sample() as sample:
                                response,trace=module.post_file(controller,url+'/bulk',path,{})
                                response.raise_for_status()
                        finally:stop.set();thread.join(3)
                    row=next(row for row in rows if row['path']=='/bulk')
                    assert row['bytes']==size and row['sha256']==digest
                    points=row['points'];bps=rate*1e6/8
                    # Worst receiver excess above the configured slope, across
                    # observed intervals. Includes socket buffering/scheduling.
                    excess=max((b[1]-a[1]-bps*(b[0]-a[0]) for i,a in enumerate(points) for b in points[i+1:]),default=0)
                    trace={k:v for k,v in trace.items() if k!='started_monotonic'}
                    result['runs'].append(dict(pair=pair,variant=name,cap_mbps=rate,bytes=size,
                        observed_mbps=size*8/sample.result['seconds']/1e6,resources=sample.result,
                        trace=trace,waits=waits,receiver_excess_bytes=max(0,excess),
                        receiver_span_seconds=points[-1][0]-points[0][0],
                        control_requests=len(beats),max_control_seconds=max(beats,default=None)))
                    print(json.dumps({k:result['runs'][-1][k] for k in ('pair','variant','cap_mbps','observed_mbps')}),flush=True)
        return result
    finally:
        (output/'measurements.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--rates',nargs='+',type=float,default=[1,10,50,100])
    args=parser.parse_args();benchmark(args.output,args.rates)
