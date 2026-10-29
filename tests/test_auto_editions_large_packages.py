"""Disk-bounded packets, negotiated limits and real durable HTTP recovery."""
import hashlib
import json
import os
from pathlib import Path
import threading
from unittest.mock import patch

import pytest
import requests
import auto_editions as ae
from auto_editions_package_limits import LEGACY_BYTES,RESUMABLE_BYTES,negotiated
from auto_editions_transport import build_package
from companion_package_identity import CHUNK,describe
from tests.test_auto_editions_jobs import database
from tests.test_companion_phase3 import env,http_receiver,DiskProvider


@pytest.mark.parametrize('message',[
    'Prepared package exceeds transfer limit.',
    'Prepared package is 292429952 bytes; negotiated transfer limit is 268435456 bytes.'
])
def test_package_failure_diagnostic_identifies_local_boundary(message):
    from worker_diagnostics import explain,accepted
    result=explain(message,'Preparing')
    assert result['code']=='PACKAGE_TRANSFER_LIMIT' and result['component']=='Companion'
    assert accepted({k:result[k] for k in ('code','component','stage')})['component']=='Companion'


@pytest.mark.parametrize('protocol,advertised,expected',[
    (0,RESUMABLE_BYTES,LEGACY_BYTES),(1,None,LEGACY_BYTES),
    (1,RESUMABLE_BYTES,RESUMABLE_BYTES),(1,2**40,LEGACY_BYTES)])
def test_large_budget_requires_explicit_compatible_negotiation(protocol,advertised,expected):
    assert negotiated(protocol,advertised)==expected


def test_large_advertisement_requires_new_production_acceptance(monkeypatch):
    import companion_package_api as api
    monkeypatch.setattr(api,'capability',lambda:1)
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','provider-postgres-retention-v1')
    assert api.upload_max_bytes()==LEGACY_BYTES
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','provider-postgres-retention-large-v2')
    assert api.upload_max_bytes()==RESUMABLE_BYTES
    monkeypatch.setattr(api,'capability',lambda:0)
    assert api.upload_max_bytes()==LEGACY_BYTES


def test_oversized_isolated_acceptance_fixture_preserves_proofs(tmp_path):
    from companion_acceptance_fixture import build,validate_fixture
    from auto_editions_package import unpack
    run='d'*32;path=build(tmp_path/'packet',run,large=True);descriptor=describe(path)
    assert LEGACY_BYTES<descriptor['bytes']<LEGACY_BYTES+16*1024**2
    root=tmp_path/'assets';root.mkdir()
    manifest,proofs=unpack(path,root,descriptor['manifest']['source'],100,100,resumable=True)
    validate_fixture(manifest,run)
    assert len(proofs)==3 and all(p.get('pixel_exact') or p.get('outside_number_exact') for p in proofs)


@pytest.mark.parametrize('difference',[-1,0,1])
def test_exact_wire_boundary_is_checked_before_writing(tmp_path,difference):
    # A scaled budget tests the same ZIP header arithmetic at each edge.
    root=tmp_path/'source';root.mkdir();(root/'a.png').write_bytes(b'x'*4096)
    wire_bytes=4096+22+76+2*len('a.png')
    limit=wire_bytes-difference;dest=tmp_path/'prepared.zip'
    with patch('auto_editions_package.MAX_PACKAGE_BYTES',limit):
        if difference>0:
            with pytest.raises(ValueError,match=f'{wire_bytes} bytes; negotiated transfer limit is {limit}'):
                build_package(root,['a.png'],dest)
            assert not dest.exists() and not dest.with_suffix('.zip.partial').exists()
        else:
            assert build_package(root,['a.png'],dest)['package_bytes']==wire_bytes


def test_expansion_disk_and_per_asset_bounds_remain_separate(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'a.png').write_bytes(b'x'*4096)
    with patch('auto_editions_package_limits.EXPANDED_BYTES',4095):
        with pytest.raises(ValueError,match='Expanded preparation'):build_package(root,['a.png'],tmp_path/'expanded.zip')
    with patch('auto_editions_package_limits.ASSET_BYTES',4095):
        with pytest.raises(ValueError,match='individual byte limit'):build_package(root,['a.png'],tmp_path/'asset.zip')
    with patch('auto_editions_transport.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
        with pytest.raises(ValueError,match='free temporary bytes'):build_package(root,['a.png'],tmp_path/'disk.zip')
    assert not list(tmp_path.glob('*.zip*'))


@pytest.mark.parametrize('changed',[None,'source','generation'])
def test_normal_retry_reuses_only_compatible_failed_exports(tmp_path,monkeypatch,changed):
    import shutil,sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    from companion_package_identity import generation
    from tests.test_auto_editions_package import archive
    fixture=tmp_path/'fixture';fixture.mkdir();_,_,manifest=archive(fixture)
    manifest['confirmed_roles']={'number':'Number','plaque':'Plaque'}
    host=tmp_path/'host';old=host/'old';old.mkdir(parents=True);new=host/'new';new.mkdir()
    shutil.copytree(fixture/'source',old/'prepared')
    (old/'prepared/manifest.json').write_text(json.dumps(manifest))
    ctx=dict(automatic=True,source=manifest['source'],number=2,total=2)
    state=dict(status='Blocked',context=ctx,generation=generation())
    if changed=='source':state['context']={**ctx,'source':{**ctx['source'],'revision':'changed'}}
    if changed=='generation':state['generation']='0'*64
    journal=json.dumps(state);(old/'job-state.json').write_text(journal)
    before={p.name:ae.file_hash(p) for p in (old/'prepared').iterdir()}
    monkeypatch.setattr(local,'HOST_FILE',host/'test.dpapi')
    monkeypatch.setattr('auto_editions_preparation_geometry.matches',lambda *a:True)
    row=dict(folder=new,generation=generation(),upload_protocol=1,upload_max_bytes=RESUMABLE_BYTES,package_transport=1)
    packet=local.package_finished(row,ctx)
    if changed:assert packet is None
    else:
        assert packet==new/'prepared.zip'
        assert json.loads((new/'package-identity.json').read_text())['sha256']==ae.file_hash(packet)
    assert (old/'job-state.json').read_text()==journal
    assert {p.name:ae.file_hash(p) for p in (old/'prepared').iterdir()}==before


@pytest.mark.parametrize('size',[LEGACY_BYTES-1,LEGACY_BYTES,LEGACY_BYTES+1])
def test_real_size_descriptor_boundary(tmp_path,env,size):
    # ZIP preamble is fault-test padding only. It makes real 256 MiB packets
    # with bounded writes; it is never used as a compression benchmark.
    e=env;zip_bytes=e.path.read_bytes();path=tmp_path/'boundary.zip'
    with path.open('wb') as output:
        output.seek(size-len(zip_bytes)-1);output.write(b'X');output.write(zip_bytes)
    descriptor=describe(path)
    from companion_package_identity import validate
    assert validate(descriptor,e.context)['bytes']==size
    assert len(descriptor['chunks'])==(size+CHUNK-1)//CHUNK
    from auto_editions_package import unpack
    dest=tmp_path/'unpack';dest.mkdir()
    if size>LEGACY_BYTES:
        with pytest.raises(ValueError,match='negotiated transfer limit'):unpack(path,dest,e.context['source'],2,2)
    manifest,proofs=unpack(path,dest,e.context['source'],2,2,resumable=True)
    assert manifest==e.manifest and len(proofs)==3


def test_real_oversized_http_restart_integrity_and_single_import(env,monkeypatch):
    """Optional actual affected archive; otherwise a synthetic 256 MiB+ packet."""
    from companion_package_client import upload
    from companion_package_store import Sessions
    from companion_transfer import Controller
    from auto_editions_package import unpack
    e=env;actual=os.environ.get('AUTO_EDITIONS_AFFECTED_PACKAGE')
    if actual:
        e.path=Path(actual);e.descriptor=describe(e.path);e.manifest=e.descriptor['manifest']
        e.context.update(source=e.manifest['source'],total=e.manifest['edition_total'],number=1,
                         product_gid=e.manifest['source']['product_gid'])
    else:
        data=e.path.read_bytes()
        with e.path.open('wb') as output:
            output.seek(LEGACY_BYTES);output.write(data)
        e.descriptor=describe(e.path)
    assert LEGACY_BYTES<e.descriptor['bytes']<=RESUMABLE_BYTES
    journal=e.root/'large-upload.json';counts=[];errors=[];verified_proofs=[]
    def process(row,path):
        dest=path.parent/'assets';dest.mkdir()
        manifest,proofs=unpack(path,dest,row['context']['source'],row['context']['number'],row['context']['total'],resumable=True)
        assert manifest==e.manifest
        assert all(p.get('pixel_exact') or p.get('outside_number_exact') for p in proofs)
        exports=os.environ.get('AUTO_EDITIONS_AFFECTED_EXPORTS') if actual else None
        if exports:
            names=['manifest.json',manifest['master']['name'],'original.png']
            names+=[p['name'] for p in manifest['patches'].values()]
            names+=[f'reference-{n}.png' for n in sorted({1,e.context['number'],e.context['total']})]
            for name in names:assert ae.file_hash(dest/name)==ae.file_hash(Path(exports)/name)
        verified_proofs.extend(proofs)
        counts.append(ae.fingerprint(manifest))
        return dict(preparation_hash=counts[-1],status='Verified locally; production readiness still required')
    c=Controller();c.configure({'mode':'Maximum speed'})
    with http_receiver(e,monkeypatch,lose_chunk_ack=True) as (base,token,seen):
        # Old acceptance cannot be used to force a larger packet into storage.
        response=requests.post(base+'/api/auto-editions/uploads/create?ticket=fixture',json=e.descriptor,
                               headers={'X-Sports-Cave-Preparation-Host':token},timeout=10)
        assert response.status_code==409
        e.sql.execute('SELECT count(*) AS n FROM companion_package_uploads');assert e.sql.fetchone()['n']==0
        monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','provider-postgres-retention-large-v2')
        grant=dict(base_url=base,ticket='fixture',secret='fixture-secret');host=dict(base_url=base,token=token)
        with pytest.raises(requests.HTTPError):upload(c,e.path,grant,host,journal,correlation='e'*32,poll_interval=.02)
        saved=json.loads(journal.read_text());port=int(base.rsplit(':',1)[1]);old_seen=list(seen)
        assert e.store.status(saved['id'],'owner',hashlib.sha256(token.encode()).hexdigest())['offset']==CHUNK
    # Fresh provider/store/controller, retaining only the normal client journal.
    prior_sent=e.provider.sent;e.provider=DiskProvider(e.provider.root);e.store=Sessions(e.connect,e.provider)
    with http_receiver(e,monkeypatch,port=port) as (base,token,seen):
        monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','provider-postgres-retention-large-v2')
        original=e.store.finalize;workers=[]
        def finalize(*args):
            state=original(*args)
            def work():
                try:e.store.run_one(process)
                except BaseException as error:errors.append(repr(error))
            worker=threading.Thread(target=work,daemon=True);workers.append(worker);worker.start()
            return state
        monkeypatch.setattr(e.store,'finalize',finalize)
        restarted=Controller();restarted.configure({'mode':'Maximum speed'})
        result=upload(restarted,e.path,grant,host,journal,correlation='e'*32,poll_interval=.02)
        for worker in workers:worker.join(10)
        assert result['preparation_hash']==ae.fingerprint(e.manifest) and len(counts)==1 and not errors
        assert restarted.last['resumed_bytes']==CHUNK
        chunks=[r['bytes'] for r in old_seen+seen if r['path'].endswith('/chunk')]
        assert max(chunks)<=CHUNK and sum(chunks)==e.path.stat().st_size
        assert prior_sent+e.provider.sent==e.path.stat().st_size
        assert upload(restarted,e.path,grant,host,journal,correlation='e'*32,poll_interval=.02)==result
        assert len(counts)==1 and not e.store.run_one(lambda *a:pytest.fail('duplicate import'))
        e.sql.execute('SELECT count(*) AS n FROM companion_package_uploads')
        assert e.sql.fetchone()['n']==1
        report=dict(package_bytes=e.path.stat().st_size,sha256=ae.file_hash(e.path),
                    chunk_count=len(chunks),largest_request_bytes=max(chunks),resumed_bytes=CHUNK,
                    imported_sessions=1,import_count=len(counts),proofs=verified_proofs,
                    result=result['status'],actual_design=bool(actual))
        if actual:
            import psutil
            report['python_peak_working_set_bytes']=psutil.Process().memory_info().peak_wset
        destination=os.environ.get('AUTO_EDITIONS_LARGE_REPORT')
        if destination:Path(destination).write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
