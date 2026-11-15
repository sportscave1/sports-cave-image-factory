"""Native benchmark admission and strict proof contracts; never calls Photoshop."""
import json,shutil
from pathlib import Path
from unittest.mock import Mock
import pytest
from PIL import Image
import auto_editions as ae
from scripts.benchmark_auto_editions_native_v19 import preflight,require_admission,benchmark,exact_outputs,cleanup_proven,BenchmarkBlocked
from scripts.benchmark_auto_editions_v18 import fixture
from scripts.prepare_auto_editions import prepare
from tests.test_auto_editions_colour import psd,icc

def test_running_even_idle_companion_blocks_native_bench_before_lock_or_com(tmp_path,monkeypatch):
    import scripts.benchmark_auto_editions_native_v19 as bench
    check=preflight(home=tmp_path,processes=[dict(pid=42,name='pythonw.exe',cmdline=['pythonw','run_icc_companion.py','--worker'])])
    assert not check['allowed'] and check['companion_pids']==[42] and not check['photoshop_executed']
    monkeypatch.setattr(bench,'preflight',lambda:check);acquire=Mock(side_effect=AssertionError('No lock or COM while production runs'));monkeypatch.setattr(bench,'processor_lease',acquire)
    with pytest.raises(BenchmarkBlocked):benchmark(bench.ROOT/'output/v19/never-created')
    acquire.assert_not_called();assert not (bench.ROOT/'output/v19/never-created').exists()

def test_host_pid_and_uncertain_lock_fail_closed(tmp_path):
    status=tmp_path/'Documents/SportsCaveAutoEditions';status.mkdir(parents=True)
    (status/'host-status.json').write_text(json.dumps(dict(companion_pid=43,status='Idle')))
    report=preflight(home=tmp_path,processes=[dict(pid=43,name='pythonw.exe',cmdline=['unknown-launcher.py'])])
    assert not report['allowed'] and report['companion_pids']==[43]
    lock=tmp_path/'Documents/SportsCavePrintJobs';lock.mkdir();(lock/'processor.lock').write_text('uncertain')
    assert not preflight(home=tmp_path,processes=[])['allowed']
    assert not preflight(home=tmp_path/'empty',processes=[dict(pid=44,name='python.exe',cmdline=None)])['allowed']

def test_small_resource_budget_and_missing_cleanup_are_not_assumed_safe(tmp_path):
    with pytest.raises(BenchmarkBlocked):require_admission(dict(allowed=True,available_ram_bytes=1024,temporary_volume_free_bytes=1024))
    assert not cleanup_proven(tmp_path)
    (tmp_path/'native-status.json').write_text('{broken');assert not cleanup_proven(tmp_path)
    (tmp_path/'native-status.json').write_text('{"owned_document_closed":false}');assert not cleanup_proven(tmp_path)

@pytest.mark.parametrize('strategy',['unknown'])
def test_unrecognised_strategy_cannot_be_selected_by_normal_preparation(tmp_path,strategy):
    with pytest.raises(ValueError,match='Unsupported'):
        prepare(tmp_path/'not-read.psd',tmp_path/'not-created',{},number_layer='n',plaque_layer='p',total=100,reference_number=1,export_strategy=strategy)
    assert not (tmp_path/'not-created').exists()

def outputs(tmp_path):
    left=tmp_path/'legacy';right=tmp_path/'candidate';left.mkdir();m,names=fixture(left,320,240)
    # The benchmark's schema comparison needs no fake source/layer claims.
    ae.render_jpg(m,left,1,left/'edition-001-TEST-NOT-PRINT-READY.jpg')
    shutil.copytree(left,right);return left,right,m

def test_comparison_verifies_all_100_patches_and_originals(tmp_path):
    left,right,m=outputs(tmp_path);before={p.name:ae.file_hash(p) for p in left.iterdir()}
    result=exact_outputs(left,right);assert result['all_100_patches_pixel_exact'] and result['files_compared']>=104
    assert {p.name:ae.file_hash(p) for p in left.iterdir()}==before

@pytest.mark.parametrize('fault',['patch_57','master','original','icc','geometry','metadata','source','missing_patch','jpeg_quality'])
def test_candidate_cannot_claim_success_for_changed_unsampled_pixels_or_metadata(tmp_path,fault):
    left,right,m=outputs(tmp_path)
    if fault=='source':
        d=json.loads((right/'manifest.json').read_text());d['source']['revision']='changed';(right/'manifest.json').write_text(json.dumps(d))
    elif fault=='missing_patch':(right/'number-57.png').unlink()
    elif fault=='jpeg_quality':
        path=right/'edition-001-TEST-NOT-PRINT-READY.jpg'
        with Image.open(path) as image:profile=image.info['icc_profile'];decoded=image.copy()
        decoded.save(path,quality=90,icc_profile=profile,dpi=(300,300));decoded.close()
    else:
        name={'master':'master.png','original':'original.png'}.get(fault,'number-57.png')
        with Image.open(right/name) as current:
            profile=current.info['icc_profile'];image=current.copy()
        if fault in ('patch_57','master','original'):image.putpixel((0,0),(255,0,1))
        if fault=='icc':profile=b'invalid-profile'
        if fault=='geometry':image=image.resize((2,2))
        image.save(right/name,icc_profile=profile,**({'dpi':(72,72)} if fault=='metadata' else {}));image.close()
    with pytest.raises((ValueError,OSError)):exact_outputs(left,right)

def test_native_failure_still_checks_original_source_and_never_builds_manifest(tmp_path,monkeypatch):
    import scripts.photoshop_dispatch as dispatch
    source=psd(tmp_path/'source.psd',icc());before=source.read_bytes()
    identity=dict(product_gid='gid://shopify/Product/190000001',file_id='id:synthetic',revision='a1',content_hash=ae.file_hash(source,dropbox=True))
    def fail(script):raise RuntimeError('Synthetic native failure')
    monkeypatch.setattr(dispatch,'run',fail)
    with pytest.raises(RuntimeError,match='Synthetic native failure'):
        prepare(source,tmp_path/'partial',identity,number_layer='number',plaque_layer='plaque',total=100,reference_number=1)
    assert source.read_bytes()==before and not (tmp_path/'partial/manifest.json').exists()
    def mutation(script):
        source.write_bytes(b'changed');raise RuntimeError('Synthetic failure after mutation')
    monkeypatch.setattr(dispatch,'run',mutation)
    with pytest.raises(ValueError,match='Source preservation'):
        prepare(source,tmp_path/'rejected',identity,number_layer='number',plaque_layer='plaque',total=100,reference_number=1)

def test_existing_partial_or_completed_package_is_never_overwritten(tmp_path):
    target=tmp_path/'existing';target.mkdir();(target/'keep').write_bytes(b'verified-package')
    with pytest.raises(ValueError,match='never overwritten'):
        prepare(tmp_path/'source.psd',target,{},number_layer='n',plaque_layer='p',total=100,reference_number=1)
    assert (target/'keep').read_bytes()==b'verified-package'

def test_resource_footprint_excludes_prior_trials_and_includes_final_jpeg(tmp_path,monkeypatch):
    import psutil
    from scripts.benchmark_auto_editions_native_v19 import Sample
    monkeypatch.setattr(psutil,'process_iter',lambda *a:[])
    previous=tmp_path/'previous';previous.mkdir();(previous/'old').write_bytes(b'x'*1000)
    current=tmp_path/'current';current.mkdir()
    with Sample(current) as sample:(current/'final-preview.jpg').write_bytes(b'x'*100)
    report=sample.result();assert report['peak_logical_temporary_disk_bytes']==100

def test_json_benchmark_flag_cannot_bypass_owner_or_live_host_check(tmp_path,monkeypatch):
    import scripts.benchmark_auto_editions_native_v19 as bench
    import scripts.photoshop_dispatch as dispatch
    called=Mock();monkeypatch.setattr(dispatch,'run',called)
    with pytest.raises(BenchmarkBlocked,match='inside this task'):
        prepare(tmp_path/'source.psd',tmp_path/'output',{},number_layer='n',plaque_layer='p',total=100,reference_number=1,native_benchmark=True,export_strategy='history_merged_crop')
    called.assert_not_called()
    monkeypatch.setattr(bench,'preflight',lambda:dict(allowed=False,reasons=['Active production host'],available_ram_bytes=8*1024**3,temporary_volume_free_bytes=20*1024**3))
    with pytest.raises(BenchmarkBlocked,match='Active production host'):
        bench.require_native_owner(bench.ROOT/'output/v19/source.psd',bench.ROOT/'output/v19/output')

def test_native_owner_check_rejects_foreign_lease_without_mutation(tmp_path,monkeypatch):
    import scripts.benchmark_auto_editions_native_v19 as bench
    monkeypatch.setattr(bench.Path,'home',lambda:tmp_path)
    monkeypatch.setattr(bench,'preflight',lambda:dict(allowed=True,reasons=[],available_ram_bytes=8*1024**3,temporary_volume_free_bytes=20*1024**3))
    folder=tmp_path/'Documents/SportsCavePrintJobs';folder.mkdir(parents=True);lock=folder/'processor.lock'
    lock.write_text('{"pid":-1,"owner":"another-owner"}')
    with pytest.raises(BenchmarkBlocked,match='does not own'):bench.require_native_owner(bench.ROOT/'output/v19/source.psd',bench.ROOT/'output/v19/output')
    assert json.loads(lock.read_text())['owner']=='another-owner'

def test_started_rpc_without_proven_cleanup_retains_ownership_evidence(tmp_path):
    from scripts.prepare_auto_editions import native_cleanup_uncertain
    assert not native_cleanup_uncertain(tmp_path) # pre-COM failure
    (tmp_path/'photoshop-dispatch.json').write_text('{"started":true}')
    assert native_cleanup_uncertain(tmp_path)
    (tmp_path/'native-status.json').write_text('{"owned_document_closed":false}')
    assert native_cleanup_uncertain(tmp_path)
    (tmp_path/'native-status.json').write_text('{"completed":false,"owned_document_closed":true}')
    assert not native_cleanup_uncertain(tmp_path) # failed export, safely closed

@pytest.mark.parametrize('state',['pre_com','closed','uncertain'])
def test_local_controller_releases_only_proven_safe_native_failures(tmp_path,monkeypatch,state):
    import sys
    from types import SimpleNamespace
    import scripts.prepare_auto_editions as prep
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    ctx=dict(product_gid='gid://shopify/Product/190000001',source={},number=1,total=100)
    row=dict(folder=tmp_path,grant={},context=ctx,status='Working',timings={})
    lease=SimpleNamespace(unlink=Mock());reported=Mock()
    def fail(source,output,*a,**kw):
        output.mkdir()
        if state!='pre_com':(output/'photoshop-dispatch.json').write_text('{"started":true}')
        if state=='closed':(output/'native-status.json').write_text('{"owned_document_closed":true,"completed":false}')
        raise RuntimeError('Synthetic native failure')
    monkeypatch.setattr(local,'JOBS',{'synthetic':row});monkeypatch.setattr(local,'context',lambda grant:ctx)
    monkeypatch.setattr(local,'processor_lease',lambda:lease);monkeypatch.setattr(local,'journal',lambda row:None)
    monkeypatch.setattr(local,'report_failure',reported);monkeypatch.setattr(local,'failure_detail',lambda *a:'Synthetic failure')
    monkeypatch.setattr(local,'safe_diagnostic',lambda *a:dict(code='PROCESSOR_LOCK_HELD'))
    monkeypatch.setattr(prep,'prepare',fail)
    local.prepare_worker('synthetic',dict(number='number',plaque='plaque'))
    assert row['status']=='Blocked';reported.assert_called_once_with(row)
    assert lease.unlink.call_count==(0 if state=='uncertain' else 1)
    if state=='uncertain':assert 'processor lock retained' in row['error'] and row['diagnostic']['code']=='PROCESSOR_LOCK_HELD'
