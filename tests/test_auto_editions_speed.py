"""Performance changes must preserve bytes, archive identity and permissions."""
from pathlib import Path
from unittest.mock import Mock,patch
import asyncio
import pytest
from functools import wraps

def async_test(f):
    @wraps(f)
    def run(*args,**kwargs):return asyncio.run(f(*args,**kwargs))
    return run
import auto_editions as ae
import auto_editions_api as api
from auto_editions_asset_cache import AssetCache
from test_auto_editions import package
from test_auto_editions_api import request,VA


def test_instrumented_encoder_keeps_exact_existing_bytes(tmp_path):
    manifest=package(tmp_path)
    with ae.compose(manifest,tmp_path,2) as image:
        image.save(tmp_path/'before.jpg',format='JPEG',quality=100,subsampling=0,
                   icc_profile=image.info.get('icc_profile',b''),dpi=(300,300))
    result=ae.render_jpg(manifest,tmp_path,2,tmp_path/'after.jpg')
    assert (tmp_path/'before.jpg').read_bytes()==(tmp_path/'after.jpg').read_bytes()
    assert set(result['render_timings'])=={'master_decode_copy_ms','number_patch_ms','jpg_encode_ms','jpg_integrity_ms'}


@pytest.mark.parametrize('retained',[False,True])
@async_test
async def test_validated_download_reuses_bytes_but_checks_archive(tmp_path,retained):
    source=tmp_path/'source.jpg';source.write_bytes(b'exact-validated-jpg')
    digest=ae.file_hash(source);cache=AssetCache(1024);cache.remember(digest,source)
    assets=Mock();jobs=Mock()
    output={'sha256':digest,'bytes':source.stat().st_size,'file_id':'id:archive','revision':'abc'}
    row={'status':'Ready','result':{'output':output,'filename':'002-of-100 - TEST.jpg','retained':retained}}
    with patch.object(api,'actor',return_value=VA),patch.object(api,'stored_current',return_value=({'id':'a'*64},assets,row)),\
         patch.object(api.runtime,'stores',return_value=(None,jobs)),patch('auto_editions_asset_cache.output_assets',cache):
        response=await api.download(request())
        assert response.status_code==200
        assert Path(response.path).read_bytes()==source.read_bytes()
        assets.verify_output.assert_called_once_with(output)
        assets.output_response.assert_not_called()
        assert jobs.retain.call_count==(0 if retained else 1)
        assert 'output_cache_hit;dur=1' in response.headers['server-timing']
        await response.background()
        assets.verify_output.side_effect=ValueError('Archived revision changed')
        denied=await api.download(request())
        assert denied.status_code==409
        assets.output_response.assert_not_called()


@async_test
async def test_progress_poll_checks_allocation_without_repeated_psd_fetch():
    identity={'allocation_id':42}
    row={'status':'Generating','payload':{'id':'a'*64,'identity':identity},'error_code':None}
    registry=Mock();registry.unit.return_value=({'id':42},None)
    jobs=Mock();jobs.read_bound.return_value=(row,{'id':42})
    with patch.object(api,'actor',return_value=VA),patch.object(api.runtime,'stores',return_value=(registry,jobs)),\
         patch.object(api,'same_allocation',return_value=True) as checked,patch.object(api.runtime,'job_for') as resolver,\
         patch.object(api.runtime,'start_worker'):
        response=await api.state(request(query='allocation_id=42&job_id='+'a'*64))
        assert response.status_code==200
        checked.assert_called_once_with({'id':42},identity)
        resolver.assert_not_called()
        checked.return_value=False
        assert (await api.state(request(query='allocation_id=42&job_id='+'a'*64))).status_code==403


def test_overlapped_identity_reads_still_reject_changed_source(tmp_path):
    import pytest
    import auto_editions_runtime as runtime
    from test_auto_editions_cloud import prepared
    unit,mapping,metadata,preparation=prepared(tmp_path)
    registry=Mock();registry.unit.return_value=(unit,mapping);registry.for_unit.return_value=preparation
    assets=Mock();assets.integration.psd_open_metadata.return_value=metadata
    with patch.object(runtime,'stores',return_value=(registry,None)),patch.object(runtime,'storage',return_value=assets):
        job,_=runtime.job_for(42)
        assert job['number']==2
        metadata['rev']='fff'
        with pytest.raises(ValueError,match='revision changed'):runtime.job_for(42)
        metadata['rev']='abc123';unit['cancelled_at']='now'
        with pytest.raises(ValueError,match='cancelled'):runtime.job_for(42)

@async_test
async def test_bound_snapshot_overlaps_reads_but_never_returns_before_authorization():
    import threading
    read_started=threading.Event()
    def read(*args):
        read_started.set()
        return ({'private':'row'}, {'id':42})
    async def deny(*args):
        assert await asyncio.to_thread(read_started.wait,2)
        raise PermissionError('revoked')
    jobs=Mock();jobs.read_bound.side_effect=read
    with patch.object(api,'actor',side_effect=deny),patch.object(api.runtime,'stores',return_value=(None,jobs)):
        with pytest.raises(PermissionError,match='revoked'):
            await api.bound_snapshot(request(query='allocation_id=42&job_id='+'a'*64))


@async_test
async def test_download_final_fence_rejects_revoked_permission_even_with_cached_bytes(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'validated')
    digest=ae.file_hash(source);cache=AssetCache(1024);cache.remember(digest,source)
    assets=Mock();row={'status':'Ready','result':{'retained':True,'filename':'x.jpg','output':{'sha256':digest}}}
    with patch.object(api,'actor',return_value=VA),patch.object(api,'stored_current',side_effect=[({'id':'a'*64},assets,row),PermissionError('revoked')]),patch.object(api.runtime,'stores',return_value=(None,Mock())),patch('auto_editions_asset_cache.output_assets',cache):
        response=await api.download(request())
        assert response.status_code==403
        assets.output_response.assert_not_called()
