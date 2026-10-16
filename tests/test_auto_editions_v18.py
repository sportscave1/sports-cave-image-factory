"""Synthetic/local contracts. No production credentials, uploads or Photoshop."""
import hashlib,json,sys,threading,time,zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import PngImagePlugin,Image
import auto_editions as ae
from auto_editions_transport import build_package,DESCRIPTOR
from auto_editions_package import unpack
from scripts.benchmark_auto_editions_v18 import fixture,legacy_pack
from auto_editions_local_cache import reuse_source,cached_inspection,inspection_receipt
from auto_editions_performance import file_hashes
from worker_health_cache import Snapshot

def packet(tmp_path):
    root=tmp_path/'source';root.mkdir();manifest,names=fixture(root,320,240)
    # Photoshop PNGs may have equal pixels/IDAT and different XMP metadata.
    with Image.open(root/'reference-1.png') as image:
        info=PngImagePlugin.PngInfo();info.add_itxt('fixture','Independent Photoshop reference export')
        image.save(root/'changed.png',pnginfo=info,icc_profile=image.info['icc_profile'],compress_level=1)
    (root/'changed.png').replace(root/'reference-1.png')
    archive=tmp_path/'compact.zip';result=build_package(root,names,archive,compact=True)
    assert result['references_shared']==1
    return root,manifest,names,archive,result

def test_compact_packet_reconstructs_every_byte_and_keeps_all_proofs(tmp_path):
    root,m,names,archive,result=packet(tmp_path)
    before={n:ae.file_hash(root/n) for n in names};legacy=tmp_path/'legacy.zip';legacy_pack(root,names,legacy)
    assert archive.stat().st_size<legacy.stat().st_size
    target=tmp_path/'unpacked';target.mkdir();actual,proofs=unpack(archive,target,m['source'],1,100)
    assert actual==m and all(p.get('pixel_exact',p.get('outside_number_exact')) for p in proofs)
    assert {n:ae.file_hash(target/n) for n in names}==before
    assert {n:ae.file_hash(root/n) for n in names}==before
    full=tmp_path/'old-server.zip';result=build_package(root,names,full,compact=False)
    assert result['transport_version']==0
    with zipfile.ZipFile(full) as z:assert DESCRIPTOR not in z.namelist()

@pytest.mark.parametrize('fault',['path','base','range','boolean','oversize','sha','base_sha','payload','extra','duplicate_target'])
def test_transport_cannot_bypass_paths_budgets_hashes_or_references(tmp_path,fault):
    root,m,names,archive,result=packet(tmp_path)
    with zipfile.ZipFile(archive) as z:files={n:z.read(n) for n in z.namelist()}
    d=json.loads(files[DESCRIPTOR]);name=next(iter(d['deltas']));delta=d['deltas'][name]
    if fault=='path':d['deltas']['../outside.png']=d['deltas'].pop(name)
    elif fault=='base':delta['base']='master.png'
    elif fault=='range':delta['prefix']=-1
    elif fault=='boolean':delta['prefix']=True
    elif fault=='oversize':delta['bytes']=300*1024**2
    elif fault=='sha':delta['sha256']='0'*64
    elif fault=='base_sha':delta['base_sha256']='0'*64
    elif fault=='payload':
        raw=files[delta['delta']];files[delta['delta']]=bytes([raw[0]^1])+raw[1:]
    elif fault=='extra':files['unreviewed.png']=b'arbitrary'
    elif fault=='duplicate_target':files[name]=(root/name).read_bytes()
    files[DESCRIPTOR]=json.dumps(d).encode();bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:
        for n,b in files.items():z.writestr(n,b)
    target=tmp_path/'rejected';target.mkdir()
    with pytest.raises(ValueError):unpack(bad,target,m['source'],1,100)
    assert not (tmp_path/'outside.png').exists()


def test_shared_reference_cannot_bypass_exact_icc_verification(tmp_path):
    root,m,names,archive,result=packet(tmp_path)
    with Image.open(root/'reference-1.png') as image:
        conflicting=bytearray(image.info['icc_profile']);conflicting[84:100]=b'1'*16
        image.save(root/'changed.png',icc_profile=bytes(conflicting),compress_level=1)
    (root/'changed.png').replace(root/'reference-1.png')
    altered=tmp_path/'conflict.zip';build_package(root,names,altered,compact=True)
    target=tmp_path/'conflict';target.mkdir()
    with pytest.raises(ValueError,match='ICC export mismatch'):unpack(altered,target,m['source'],1,100)

@pytest.mark.parametrize('size',[0,1024,4*1024*1024+37])
def test_combined_checksums_are_identical_to_existing_hashes(tmp_path,size):
    p=tmp_path/'bytes';p.write_bytes(b'x'*size);h=file_hashes(p)
    assert h==dict(sha256=ae.file_hash(p),dropbox=ae.file_hash(p,dropbox=True))

def test_source_cache_reuses_only_exact_pinned_bytes_and_preserves_original(tmp_path):
    root=tmp_path/'owned';root.mkdir();a=root/('a'*48);b=root/('b'*48);a.mkdir();b.mkdir()
    source=a/'input.psd';source.write_bytes(b'synthetic-original-psd'*100)
    identity=ae.source_identity('gid://shopify/Product/1800',dict(id='id:source',rev='a18',content_hash=ae.file_hash(source,dropbox=True)))
    (a/'job-state.json').write_text(json.dumps(dict(context=dict(source=identity))))
    before=source.read_bytes();result=reuse_source(root,b/'input.psd',identity,len(before))
    assert result['sha256']==ae.file_hash(source) and source.read_bytes()==before and (b/'input.psd').read_bytes()==before
    assert reuse_source(root,b/'input.psd',{**identity,'revision':'changed','content_hash':'0'*64},len(before)) is None
    assert source.read_bytes()==before
    with pytest.raises(ValueError):reuse_source(root,tmp_path/'outside.psd',identity,len(before))

def test_inspection_checkpoint_invalidates_source_code_and_report_changes(tmp_path):
    report=tmp_path/'inspection.json';report.write_text(json.dumps(dict(documents=[dict(inspection='synthetic')])));
    identity={'file_id':'id:source','revision':'a18'};receipt=inspection_receipt(tmp_path,identity,'a'*64,'b'*64)
    (tmp_path/'inspection-cache.json').write_text(json.dumps(receipt))
    assert cached_inspection(tmp_path,identity,'a'*64,'b'*64)
    assert cached_inspection(tmp_path,identity,'a'*64,'c'*64) is None
    assert cached_inspection(tmp_path,{**identity,'revision':'new'},'a'*64,'b'*64) is None
    report.write_text('changed');assert cached_inspection(tmp_path,identity,'a'*64,'b'*64) is None

def test_snapshot_cache_single_flight_copy_isolation_expiry_and_fail_closed():
    from concurrent.futures import ThreadPoolExecutor
    now=[0];cache=Snapshot(clock=lambda:now[0]);calls=[];entered=threading.Event();release=threading.Event()
    def loader():calls.append(1);entered.set();release.wait(2);return dict(jobs=[{'id':1}],cost={'queries':2})
    with ThreadPoolExecutor(max_workers=4) as pool:
        first=pool.submit(cache.read,loader);assert entered.wait(1)
        rest=[pool.submit(cache.read,loader) for _ in range(3)];release.set();values=[first.result()]+[f.result() for f in rest]
    assert len(calls)==1
    values[0]['jobs'].clear();assert cache.read(loader)['jobs']==[{'id':1}]
    assert cache.read(loader)['cost']['queries']==0
    now[0]=3
    def failure():raise RuntimeError('Database unavailable')
    with pytest.raises(RuntimeError):cache.read(failure)
    cache.invalidate();assert cache.read(loader)['cost']['queries']==2

def test_pause_invalidation_during_snapshot_does_not_publish_stale_cache():
    cache=Snapshot();entered=threading.Event();release=threading.Event()
    def old():entered.set();release.wait(2);return dict(jobs=['before pause'],cost={'queries':2})
    thread=threading.Thread(target=lambda:cache.read(old));thread.start();assert entered.wait(1)
    cache.invalidate();release.set();thread.join()
    assert cache.read(lambda:dict(jobs=['after pause'],cost={'queries':2}))['jobs']==['after pause']

def test_terminal_verified_checkpoint_wakes_host_without_polling_delay(tmp_path,monkeypatch):
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    event=threading.Event();monkeypatch.setattr(local,'HOST_WAKE',event)
    row=dict(status='Working',folder=tmp_path,context={},timings={'package_bytes':1024})
    started=time.monotonic();local.finish_upload(row,dict(preparation_hash='a'*64),started)
    assert event.wait(.1) and row['status']=='Prepared' and time.monotonic()-started<1

def test_fresh_complete_folder_listing_reuses_receipts_without_individual_reads(tmp_path):
    from tests.test_auto_editions import package
    from auto_editions_cloud import DropboxAssets
    m=package(tmp_path);records={};reads=[];writes=[];listing=[False]
    class Integration:
        def ensure_folder_path(self,*a,**k):pass
        def list_folder_page(self,token,path,limit):
            assert limit==4;reads.append('listing');return dict(entries=list(records.values()),has_more=listing[0])
        def get_metadata_if_exists(self,token,path):reads.append('metadata');return records.get(path)
        def upload_local_file(self,token,path,local,conflict):
            assert conflict=='cancel';writes.append(path)
            row=dict(name=local.name,path_lower=path.lower(),id='id:'+local.stem,rev='a18',size=local.stat().st_size,content_hash=ae.file_hash(local,dropbox=True))
            records[path]=row;return row
    storage=DropboxAssets('synthetic-token',Integration());first=storage.publish_preparation(m,tmp_path)
    assert reads==['listing'] and len(writes)==3
    reads.clear();second=storage.publish_preparation(m,tmp_path)
    assert second==first and reads==['listing'] and len(writes)==3
    assert storage.timings['prepared_reused_assets']==3 and storage.timings['prepared_upload_requests']==0
    # Partial listings cannot turn an absent entry into permission to overwrite.
    listing[0]=True;storage.integration.list_folder_page=lambda *a,**k:dict(entries=[],has_more=True)
    reads.clear();assert storage.publish_preparation(m,tmp_path)==first and reads==['metadata']*3 and len(writes)==3
    records[next(iter(records))]['content_hash']='0'*64
    with pytest.raises(ValueError,match='not overwritten'):storage.publish_preparation(m,tmp_path)
    assert len(writes)==3
