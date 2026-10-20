"""Bounded loopback check or analysis of <=32 existing control observations.

Never starts an internet speed test. For a future authorised WAN measurement,
record existing heartbeat request durations with idle/loaded labels and analyse
that file. It measures control-path responsiveness, not household browsing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def analyse(rows):
    import math
    if not isinstance(rows,list) or not 1<=len(rows)<=32:raise ValueError('Use 1–32 bounded observations.')
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'seconds','loaded'} or type(row['loaded']) is not bool
            or type(row['seconds']) not in (int,float) or not math.isfinite(row['seconds']) or not 0<row['seconds']<=20):
            raise ValueError('Only control duration and idle/loaded flag are accepted.')
    result={}
    for flag,label in ((False,'idle'),(True,'loaded')):
        values=sorted(r['seconds'] for r in rows if r['loaded']==flag)
        result[label]=dict(count=len(values),median_seconds=statistics.median(values) if values else None,
            max_seconds=max(values) if values else None)
    result['loaded_to_idle_ratio']=(result['loaded']['median_seconds']/result['idle']['median_seconds']
        if result['loaded']['count']>=3 and result['idle']['count']>=3 else None)
    result['interpretation']='Control path includes server work; cannot attribute congestion or prove household browsing performance.'
    return result


def fixture():
    from tests.test_companion_phase2_transfers import receiver
    from companion_transfer import Controller,post_file,burst_allowance
    import requests
    rows=[];c=Controller();c.configure(dict(mode='Balanced',sustainable_mbps=16/.75))
    # Explicit fixture latency, never a live household measurement.
    for _ in range(3):c.observe_control(.02,loaded=False)
    c.policy.last_change=time.monotonic()-31
    for _ in range(3):c.observe_control(.4,loaded=True)
    rate=c.rate()
    with tempfile.TemporaryDirectory(prefix='sc-phase5-') as temp,receiver() as (url,received,_),ThreadPoolExecutor(1) as pool:
        path=Path(temp)/'payload';path.write_bytes(b'x'*4*1024**2)
        def probe(loaded):
            started=time.monotonic();requests.post(url+'/heartbeat',json={'fixture':True},timeout=2).raise_for_status()
            rows.append(dict(seconds=time.monotonic()-started,loaded=loaded))
        for _ in range(3):probe(False)
        started=time.monotonic();future=pool.submit(post_file,c,url+'/bulk',path,{})
        for _ in range(10):
            if future.done():break
            time.sleep(.15);probe(True)
        response,trace=future.result(6);response.raise_for_status();elapsed=time.monotonic()-started
        bulk=next(r for r in received if r['path']=='/bulk');assert bulk['bytes']==path.stat().st_size
        assert bulk['bytes']<=rate*elapsed+burst_allowance(rate)
        result=dict(local_only=True,network_capacity_measured=False,simulated_latency_reduction=True,
            requested_balanced_mbps=16,effective_mbps=rate*8/1_000_000,application_bytes=bulk['bytes'],
            elapsed_seconds=elapsed,receiver_mbps=bulk['bytes']*8/elapsed/1_000_000,
            allowance_wait_seconds=trace['allowance_wait_seconds'],burst_bytes=burst_allowance(rate),
            responsiveness=analyse(rows),observations=rows)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True);choice.add_argument('--fixture',action='store_true');choice.add_argument('--observations',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'output') or output.exists():raise ValueError('Use a new task-local output file.')
    if args.observations and args.observations.stat().st_size>16384:raise ValueError('Bounded observation file required.')
    value=fixture() if args.fixture else analyse(json.loads(args.observations.read_text(encoding='utf-8')))
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps(value,indent=2))
