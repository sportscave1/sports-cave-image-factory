"""Loopback-only Phase 2 evidence. Never claims internet capacity or Cloud Ready.

Reuses Phase 1's retained fixture inventory and resource sampler. No Photoshop,
provider calls, live capabilities, queue changes, or original-source writes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_companion_phase1 import Sample,checksums
from tests.test_companion_phase2_transfers import receiver,capped
from companion_transfer import Controller,post_file,allowance
from auto_editions_transport import build_package
import auto_editions as ae
import requests


def clean(trace):return {k:v for k,v in trace.items() if k!='started_monotonic'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--colour-policies',type=Path,required=True,help='Unchanged retained approval evidence, task-local copy')
    args=parser.parse_args();fixture=args.fixture.resolve();report=args.report.resolve()
    if not fixture.is_relative_to(ROOT/'output') or not report.is_relative_to(ROOT/'output') or report.exists():
        parser.error('Use retained task-local fixture and a new task-local report path.')
    report.parent.mkdir(parents=True,exist_ok=True)
    before=checksums(fixture);prepared=fixture/'prepared'
    manifest=ae.validate_manifest(json.loads((prepared/'manifest.json').read_text()))
    policy_file=args.colour_policies.resolve()
    if not policy_file.is_relative_to(ROOT/'output'):parser.error('Use a task-local policy evidence copy.')
    os.environ['AUTO_EDITIONS_COLOUR_POLICIES_FILE']=str(policy_file)
    os.environ['AUTO_EDITIONS_COLOUR_POLICY_BACKEND']='file'
    from auto_editions_colour_policy import resolve
    _,approved=resolve(manifest['source'])
    if approved!=manifest['colour_evidence']['policy']:raise ValueError('Retained exact-source colour approval differs.')
    names=sorted({'manifest.json','original.png','reference-1.png',f"reference-{manifest['edition_total']}.png",manifest['master']['name']}|{p['name'] for p in manifest['patches'].values()})
    result=dict(kind='Controlled loopback receiver evidence',internet_capacity_measured=False,
                browsing_measured=False,production_uploads=0,photoshop_runs=0,
                source=manifest['source'],preparation_hash=ae.fingerprint(manifest),runs=[])
    with tempfile.TemporaryDirectory(prefix='phase2-',dir=report.parent) as scratch:
        root=Path(scratch);package=root/'prepared.zip'
        with Sample() as sample:package_info=build_package(prepared,names,package,compact=True)
        result['package_build']={**package_info,**sample.result}
        digest=ae.file_hash(package);result['package_sha256']=digest
        # Equivalent full real package, alternating request order. Warm loopback;
        # connection reuse can reduce setup, but no artificial latency is added.
        c=Controller();c.configure(dict(mode='Maximum speed'))
        with receiver(response_delay=.1) as (url,rows,connections):
            for repeat in range(3):
                order=['before','after'] if repeat%2==0 else ['after','before']
                for method in order:
                    previous=len(connections)
                    with Sample() as sample:
                        if method=='before':
                            with package.open('rb',buffering=1024*1024) as body:response=requests.post(url+'/bulk',data=body,headers={'Content-Type':'application/zip'},timeout=30)
                            trace=None
                        else:response,trace=post_file(c,url+'/bulk',package,{'Content-Type':'application/zip'})
                        response.raise_for_status()
                    received=rows[-1]
                    assert received['sha256']==digest and received['bytes']==package.stat().st_size
                    result['runs'].append(dict(method=method,repeat=repeat,**sample.result,
                        receiver_bytes=received['bytes'],receiver_sha256=received['sha256'],
                        new_connections=len(connections)-previous,trace=clean(trace) if trace else None))
        c.session.close()
        result['comparison']={method:statistics.median(r['seconds'] for r in result['runs'] if r['method']==method) for method in ('before','after')}
        b,a=result['comparison']['before'],result['comparison']['after']
        result['comparison'].update(seconds_saved=b-a,percent_saved=(b-a)/b*100)
        # Fixed explicit rates, not inferred from any production request.
        small=root/'bounded.bin';small.write_bytes(bytes(range(256))*1024)
        c=capped(1.048576);beat_times=[];stop=threading.Event()
        with receiver(response_delay=.1) as (url,rows,connections):
            def heartbeat():
                while not stop.wait(.1):
                    start=time.monotonic();requests.post(url+'/heartbeat',json={'lease':'fixture'},timeout=2).raise_for_status();beat_times.append(time.monotonic()-start)
            beat=threading.Thread(target=heartbeat);beat.start()
            with Sample() as sample,ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(post_file,c,url+'/bulk',small,{}) for _ in range(2)]
                transfers=[future.result(10) for future in futures]
            stop.set();beat.join(3)
            bulk=[r for r in rows if r['path']=='/bulk'];points=sorted(p for r in bulk for p in [(t,r['points'][i][1]-(r['points'][i-1][1] if i else 0)) for i,(t,_) in enumerate(r['points'])])
            rate=allowance(c.value);worst=0
            # Fixed 100 ms receiver windows, with measured event timestamps.
            for i in range(0,len(points),16):
                end=points[i][0]+.1
                count=sum(n for t,n in points[i:] if t<=end)
                worst=max(worst,count)
            result['aggregate']=dict(**sample.result,configured_mbps=1.048576,allowance_bytes_per_second=rate,
                receiver_bytes=sum(r['bytes'] for r in bulk),attempts=2,retries=0,
                effective_payload_mbps=sum(r['bytes'] for r in bulk)*8/sample.wall/1e6,
                maximum_observed_100ms_bytes=worst,application_bucket_max_bytes=min(16384,max(1024,rate*.1)),
                control_requests=len(beat_times),max_control_request_seconds=max(beat_times),
                traces=[clean(t) for _,t in transfers])
        c.session.close()
        # Run the unchanged server validation and compare every reconstructed
        # member with the retained fixture, including all PNGs and ICC/proofs.
        from auto_editions_package import unpack
        expanded=root/'expanded';expanded.mkdir()
        with Sample() as sample:received_manifest,proofs=unpack(package,expanded,manifest['source'],manifest['edition_total'],manifest['edition_total'])
        for name in names:assert ae.file_hash(expanded/name)==ae.file_hash(prepared/name)
        assert received_manifest==manifest and ae.file_hash(package)==digest
        result['verification']=dict(**sample.result,exact_members=len(names),proofs=proofs,passed=True,cloud_ready=False)
    assert before==checksums(fixture)
    result['fixture_unchanged']=True
    report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(report=str(report),comparison=result['comparison'],aggregate={k:v for k,v in result['aggregate'].items() if k!='traces'},verification=result['verification']['passed'])))


if __name__=='__main__':main()
