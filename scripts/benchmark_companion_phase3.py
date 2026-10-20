"""Offline/loopback Phase 3 evidence. No real hosts, credentials or provider writes."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import threading
import zipfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from scripts.benchmark_companion_phase1 import Sample,checksums
from auto_editions_transport import build_package,spans
from companion_package_identity import describe
from companion_package_client import upload
from companion_package_store import Sessions
from companion_transfer import Controller,post_file
from tests.test_companion_phase2_transfers import receiver
from tests.test_companion_phase3 import DiskProvider,http_receiver,MIGRATION,padded,verify,small_archive
from tests.test_auto_editions_jobs import database
import pytest
import auto_editions as ae
import requests
import time
from concurrent.futures import ThreadPoolExecutor


def recovery(report):
    generator=database.__wrapped__();jobs,sql=next(generator);mp=pytest.MonkeyPatch()
    try:
        sql.execute(MIGRATION.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(prefix='fault-',dir=report.parent) as scratch:
            root=Path(scratch);folder=root/'fixture';folder.mkdir();path,_,manifest=small_archive(folder)
            provider=DiskProvider(root/'provider');e=SimpleNamespace(root=root,path=path,manifest=manifest,provider=provider,
                store=Sessions(jobs.connect,provider),context=dict(automatic=True,source=manifest['source'],total=2,number=2,product_gid=manifest['source']['product_gid'],lease_token='fault'))
            padded(e);c=Controller();c.configure(dict(mode='Manual',manual_mbps=32))
            journal=root/'session.json';result=dict(kind='Fault-only ZIP preamble fixture; not package-size evidence',wire_bytes_measured=False,browsing_measured=False,configured_mbps=32,package_bytes=path.stat().st_size)
            with http_receiver(e,mp,lose_chunk_ack=True) as (base,token,seen):
                grant=dict(base_url=base,ticket='fixture',secret='fixture');host=dict(base_url=base,token=token)
                with Sample() as sample:
                    try:upload(c,path,grant,host,journal,correlation='a'*32,poll_interval=.02)
                    except requests.HTTPError:pass
                    else:raise AssertionError('Expected lost acknowledgement')
                result['interrupted_attempt']=sample.result
                saved=json.loads(journal.read_text());state=e.store.status(saved['id'],'owner',hashlib.sha256(token.encode()).hexdigest())
                result.update(server_confirmed_after_loss=state['offset'],client_journal_after_loss=saved['confirmed_bytes'])
                first_seen=list(seen);port=int(base.rsplit(':',1)[1]);first_sent=provider.sent
            # Fresh receiver, adapter and companion controller; same durable SQL/provider data.
            e.provider=DiskProvider(provider.root);e.store=Sessions(jobs.connect,e.provider)
            original=e.store.finalize
            def finalise(*a):
                state=original(*a);threading.Thread(target=lambda:e.store.run_one(lambda row,archive:verify(e,row,archive)),daemon=True).start();return state
            mp.setattr(e.store,'finalize',finalise);beats=[];stop=threading.Event()
            with http_receiver(e,mp,port=port) as (base,token,seen):
                def beat():
                    while not stop.wait(.1):
                        started=time.monotonic()
                        requests.post(base+'/api/auto-editions/uploads/status?id='+saved['id'],json={},headers={'X-Sports-Cave-Preparation-Host':token},timeout=3).raise_for_status()
                        beats.append(time.monotonic()-started)
                thread=threading.Thread(target=beat,daemon=True);thread.start()
                restarted=Controller();restarted.configure(dict(mode='Manual',manual_mbps=32))
                with Sample() as sample:
                    outcome=upload(restarted,path,grant,host,journal,correlation='a'*32,poll_interval=.02)
                stop.set();thread.join(4)
                result['resumed_attempt']={**sample.result,**{k:restarted.last[k] for k in ('transport_bytes','resumed_bytes','transfer_seconds','allowance_wait_seconds','verification_seconds')}}
                result.update(receiver_package_bytes=sum(r['bytes'] for r in first_seen+seen if r['path'].endswith('/chunk')),
                    provider_appended_bytes=first_sent+e.provider.sent,control_requests=len(beats),max_control_seconds=max(beats),synthetic_verified=outcome['synthetic_provider_verification'])
                assert result['receiver_package_bytes']==result['provider_appended_bytes']==path.stat().st_size
                assert restarted.last['resumed_bytes']==8*1024*1024
                c.session.close();restarted.session.close()
            report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:mp.undo();generator.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--recovery-only',action='store_true')
    args=parser.parse_args();report=args.report.resolve()
    if not report.is_relative_to(ROOT/'output') or report.exists():parser.error('New task-local report required.')
    report.parent.mkdir(parents=True,exist_ok=True)
    if args.recovery_only:return recovery(report)
    fixture=ROOT/'output/companion-phase1/fixture';prepared=fixture/'prepared'
    before=checksums(fixture);manifest=ae.validate_manifest(json.loads((prepared/'manifest.json').read_text()))
    names=sorted({'manifest.json','original.png','reference-1.png','reference-100.png',manifest['master']['name']}|{p['name'] for p in manifest['patches'].values()})
    result=dict(kind='Offline and controlled loopback; synthetic auth/provider only',production_writes=0,photoshop_runs=0,
                internet_capacity_measured=False,browsing_measured=False,wire_bytes_measured=False,
                cold_cache_measured=False,source=manifest['source'],preparation_hash=ae.fingerprint(manifest))
    groups=defaultdict(list)
    for name in names:groups[ae.file_hash(prepared/name)].append(name)
    result['audit']=dict(final_assets=dict(count=101,bytes=sum((prepared/n).stat().st_size for n in names if n not in ('manifest.json','original.png','reference-1.png','reference-100.png'))),
        independent_proofs=dict(count=3,bytes=sum((prepared/n).stat().st_size for n in ('original.png','reference-1.png','reference-100.png'))),
        metadata=dict(count=1,bytes=(prepared/'manifest.json').stat().st_size),
        exact_duplicate_groups=[n for n in groups.values() if len(n)>1],
        compact_candidates={n:dict(zip(('prefix','suffix'),spans(prepared/'original.png',prepared/n))) for n in ('reference-1.png','reference-100.png')})
    with tempfile.TemporaryDirectory(prefix='phase3-',dir=report.parent) as scratch:
        root=Path(scratch);package=root/'prepared.zip'
        with Sample() as sample:info=build_package(prepared,names,package,compact=True)
        result['package_build']={**info,**sample.result};digest=ae.file_hash(package)
        result['package_sha256']=digest;result['compression']=[]
        for level in (1,6):
            compressed=root/f'deflate-{level}.zip'
            with Sample() as sample:
                with zipfile.ZipFile(compressed,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=level) as z:
                    for name in names:z.write(prepared/name,name)
            with zipfile.ZipFile(compressed) as z:
                for name in names:
                    with z.open(name) as member:assert hashlib.file_digest(member,'sha256').hexdigest()==ae.file_hash(prepared/name)
            result['compression'].append(dict(level=level,bytes=compressed.stat().st_size,saved_bytes=package.stat().st_size-compressed.stat().st_size,**sample.result))
            compressed.unlink()
        # The existing complete independent validator, using unchanged retained approval.
        os.environ['AUTO_EDITIONS_COLOUR_POLICY_BACKEND']='file'
        os.environ['AUTO_EDITIONS_COLOUR_POLICIES_FILE']=str(ROOT/'output/companion-phase2/colour-policies.json')
        from auto_editions_package import unpack
        expanded=root/'expanded';expanded.mkdir()
        with Sample() as sample:actual,proofs=unpack(package,expanded,manifest['source'],1,100)
        assert actual==manifest
        assert all(ae.file_hash(expanded/n)==ae.file_hash(prepared/n) for n in names)
        result['independent_validation']=dict(**sample.result,exact_members=len(names),proofs=proofs)
        # Durable local provider + disposable SQL. Distinct synthetic leases per trial.
        generator=database.__wrapped__();jobs,sql=next(generator)
        try:
            sql.execute(MIGRATION.read_text(encoding='utf-8'))
            provider=DiskProvider(root/'provider');store=Sessions(jobs.connect,provider)
            e=SimpleNamespace(store=store,provider=provider,context=dict(automatic=True,source=manifest['source'],total=100,number=1,product_gid=manifest['source']['product_gid'],lease_token='fixture'),path=package)
            result['runs']=[];mp=pytest.MonkeyPatch()
            original=store.finalize
            def finalize(*a):
                state=original(*a)
                def process(row,path):
                    assert ae.file_hash(path)==digest
                    return dict(preparation_hash=ae.fingerprint(manifest),status='Cloud Ready',synthetic_provider_verification=True)
                threading.Thread(target=lambda:store.run_one(process),daemon=True).start()
                return state
            mp.setattr(store,'finalize',finalize)
            try:
                with receiver() as (legacy,rows,_),http_receiver(e,mp) as (base,token,seen):
                    c=Controller();c.configure(dict(mode='Maximum speed'))
                    for repeat in range(3):
                        for method in (('legacy','resumable') if repeat%2==0 else ('resumable','legacy')):
                            e.context={**e.context,'lease_token':f'fixture-{repeat}'}
                            seen_start=len(seen);row_start=len(rows)
                            with Sample() as sample:
                                if method=='legacy':
                                    response,trace=post_file(c,legacy+'/bulk',package,{})
                                    response.raise_for_status();assert rows[-1]['sha256']==digest
                                else:
                                    value=upload(c,package,dict(base_url=base,ticket='fixture',secret='fixture'),dict(base_url=base,token=token),root/f'session-{repeat}.json',correlation='e'*32,poll_interval=.02)
                                    assert value['synthetic_provider_verification'];trace=dict(c.last)
                            count=sum(r['bytes'] for r in (rows[row_start:] if method=='legacy' else seen[seen_start:]) if method=='legacy' or r['path'].endswith('/chunk'))
                            result['runs'].append(dict(method=method,repeat=repeat,receiver_payload_bytes=count,**sample.result,
                                transfer_seconds=trace.get('transfer_seconds'),verification_seconds=trace.get('verification_seconds')))
                    # Lost client state can recover the same completed session from its binding.
                    start=len(seen)
                    with Sample() as sample:
                        value=upload(c,package,dict(base_url=base,ticket='fixture',secret='fixture'),dict(base_url=base,token=token),root/'recovered.json',correlation='f'*32,poll_interval=.02)
                    result['completed_reuse']=dict(**sample.result,receiver_payload_bytes=sum(r['bytes'] for r in seen[start:] if r['path'].endswith('/chunk')))
                    c.session.close()
                result['provider']=dict(received_payload_bytes=provider.sent,committed_packages=provider.finishes,verification_downloads=provider.downloads,
                    peak_retained_staging_bytes=sum(p.stat().st_size for p in provider.root.iterdir()))
            finally:mp.undo()
        finally:generator.close()
        from companion_source_cache import remember,reuse
        source=fixture/'input.psd'
        # Match the short private LocalAppData layout; the task's very long
        # worktree name exceeds Win32 MAX_PATH with a nested hash directory.
        with tempfile.TemporaryDirectory(prefix='sc-cache-') as cache_folder:
            cache=Path(cache_folder)
            with Sample() as sample:assert remember(source,manifest['source'],source.stat().st_size,cache=cache)
            result['cache_store']=sample.result
            with Sample() as sample:assert reuse(root/'reused.psd',manifest['source'],source.stat().st_size,cache=cache)
            result['cache_reuse']=dict(**sample.result,conditional_download_bytes_avoided=source.stat().st_size)
    result['fixture_unchanged']=checksums(fixture)==before;assert result['fixture_unchanged']
    result['normal_medians']={m:statistics.median(r['seconds'] for r in result['runs'] if r['method']==m) for m in ('legacy','resumable')}
    report.write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps(dict(report=str(report),medians=result['normal_medians'],compression=result['compression'],fixture_unchanged=True),indent=2))


if __name__=='__main__':main()
