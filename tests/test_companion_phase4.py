"""Capped real receiver and processing-preservation regressions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time
import pytest
from companion_transfer import Controller,post_file,allowance,burst_allowance
from tests.test_companion_phase2_transfers import receiver


@pytest.mark.parametrize('mbps,burst',[(1,12500),(10,40000),(50,200000),(100,262144),(10000,262144)])
def test_pacing_budget_is_rate_based_and_bounded(mbps,burst):
    c=Controller();c.configure(dict(mode='Manual',manual_mbps=mbps))
    assert allowance(c.value)==mbps*1000000/8
    assert burst_allowance(allowance(c.value))==burst


def test_delayed_windows_wake_retains_bounded_credit_at_receiver(tmp_path):
    path=tmp_path/'data';path.write_bytes(bytes(range(256))*8192)
    c=Controller();c.configure(dict(mode='Manual',manual_mbps=100))
    wait=c.cv.wait
    # A real slow scheduler, not a mocked take/read/HTTP call. Receiver-side
    # observations must still satisfy the cap plus the documented burst.
    c.cv.wait=lambda seconds=None:wait(max(.015,seconds or 0))
    with receiver() as (url,rows,_):
        begin=time.monotonic();response,trace=post_file(c,url+'/bulk',path,{})
        elapsed=time.monotonic()-begin;response.raise_for_status()
    row=rows[0];rate=100*1000000/8
    assert row['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert trace['transport_bytes']==trace['server_received_bytes']==path.stat().st_size
    assert path.stat().st_size <= rate*elapsed+burst_allowance(rate)
    assert elapsed<.7  # Old 16 KiB bucket needs ~1.9s with these real waits.
    points=row['points']
    excess=max(b[1]-a[1]-rate*(b[0]-a[0]) for i,a in enumerate(points) for b in points[i+1:])
    assert excess<=burst_allowance(rate)+65536 # Receiver scheduling/socket allowance.
    assert trace['allowance_wait_seconds']>0


def test_high_rate_competitors_retries_and_pause_keep_one_budget(tmp_path):
    path=tmp_path/'data';path.write_bytes(bytes(range(256))*4096)
    c=Controller();c.configure(dict(mode='Manual',manual_mbps=50))
    with receiver(failures=1) as (url,rows,_),ThreadPoolExecutor(2) as pool:
        begin=time.monotonic()
        results=[pool.submit(post_file,c,url+'/bulk',path,{}) for _ in range(2)]
        values=[f.result(5) for f in results]
        # The failed body's bytes consumed the same allowance as its successor.
        assert sorted(r.status_code for r,t in values)==[200,503]
        assert sum(r['bytes'] for r in rows)<=allowance(c.value)*(time.monotonic()-begin)+burst_allowance(allowance(c.value))
        assert max(t['slot_wait_seconds'] for r,t in values)>.05
        c.configure({**c.value,'paused':True},'request_100')
        waiting=pool.submit(post_file,c,url+'/bulk',path,{})
        time.sleep(.08);assert not waiting.done()
        c.configure({**c.value,'paused':False,'manual_mbps':10},'request_101')
        resume=time.monotonic();waiting.result(5)[0].raise_for_status()
        # No accumulated high-rate credit is released after pause/rate change.
        assert time.monotonic()-resume >= (path.stat().st_size-burst_allowance(1250000))/1250000-.025
    assert len(rows)==3 and all(r['bytes']==path.stat().st_size for r in rows)


@pytest.mark.parametrize('which',['source','working'])
def test_native_preservation_hash_checks_staged_and_original(tmp_path,which):
    from auto_editions import file_hash
    from tests.test_product_upload_mockups import colour_psd,icc
    from scripts.render_product_upload_psd import render
    source=colour_psd(tmp_path/'source.psd',icc())
    identity=dict(template_id='test',file_id='id:fixture',revision='1',content_hash=file_hash(source,dropbox=True))
    output=tmp_path/'render'
    def dispatch(script):
        target=source if which=='source' else output/'working.psd'
        with target.open('ab') as stream:stream.write(b'changed during native dispatch')
        raise RuntimeError('Native failure')
    with pytest.raises(ValueError,match='preservation'):
        render(source,output,identity,dispatch=dispatch)


def test_comparison_allows_only_reviewed_metadata_and_valid_colour_hints():
    from scripts.benchmark_companion_phase4_native import stable_xmp
    profile=dict(name='sRGB IEC61966-2.1',description='sRGB IEC61966-2.1')
    def xmp(extra='',identity='one',subject='same'):
        return ('<r xmlns:mm="http://ns.adobe.com/xap/1.0/mm/" '
                'xmlns:ps="http://ns.adobe.com/photoshop/1.0/" '
                'xmlns:exif="http://ns.adobe.com/exif/1.0/" '
                f'mm:InstanceID="{identity}" subject="{subject}" {extra}/>')
    assert stable_xmp(xmp(),profile)==stable_xmp(xmp('ps:ICCProfile="sRGB IEC61966-2.1" exif:ColorSpace="1"','two'),profile)
    assert stable_xmp(xmp(),profile)!=stable_xmp(xmp(subject='changed rights or artwork metadata'),profile)
    with pytest.raises(ValueError,match='profile label'):
        stable_xmp(xmp('ps:ICCProfile="Adobe RGB (1998)"'),profile)
    with pytest.raises(ValueError,match='colour-space'):
        stable_xmp(xmp('exif:ColorSpace="1"'),dict(name='Adobe RGB (1998)',description='Adobe RGB (1998)'))


def test_empty_restart_cannot_interrupt_host_or_open_documents(monkeypatch):
    from unittest.mock import Mock
    import scripts.benchmark_companion_phase4_native as bench
    call=Mock();lease=Mock()
    monkeypatch.setattr(bench,'run',call);monkeypatch.setattr(bench,'processor_lease',lambda:lease)
    monkeypatch.setattr(bench,'preflight',lambda:dict(allowed=False))
    with pytest.raises(bench.BenchmarkBlocked):bench.close_empty_photoshop()
    call.assert_not_called();lease.unlink.assert_not_called()
    monkeypatch.setattr(bench,'preflight',lambda:dict(allowed=True,photoshop_pids=[123]))
    monkeypatch.setattr(bench,'inventory',lambda:dict(documents=[dict(id=42)]))
    with pytest.raises(bench.BenchmarkBlocked,match='open documents'):bench.close_empty_photoshop()
    call.assert_not_called();lease.unlink.assert_called_once()


def test_preparation_uses_released_strategy_when_memory_headroom_is_unproven(monkeypatch):
    from types import SimpleNamespace
    import psutil
    from scripts.prepare_auto_editions import select_export_strategy
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=4*1024**3-1))
    assert select_export_strategy()=='duplicate_merged'
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=4*1024**3))
    assert select_export_strategy()=='history_merged_crop'
    def unavailable():raise OSError('No memory counters')
    monkeypatch.setattr(psutil,'virtual_memory',unavailable)
    assert select_export_strategy()=='duplicate_merged'


@pytest.mark.parametrize('rle,colour',[(False,(12,53,201)),(True,(123,44,210,128))])
def test_private_fast_png_preserves_released_pixels_profile_and_alpha(tmp_path,rle,colour):
    import subprocess,types
    from unittest.mock import patch
    from pathlib import Path
    from PIL import Image,ImageCms
    from tests.test_product_upload_server_artwork import real_psd
    import product_upload_artwork as candidate
    source=real_psd(tmp_path/'source.psd',colour=colour,width=64,height=32,rle=rle)
    before=source.read_bytes();released=types.ModuleType('released_artwork');released.__file__=candidate.__file__
    root=Path(candidate.__file__).parent
    exec(compile(subprocess.check_output(['git','show','58569c66:product_upload_artwork.py'],cwd=root),released.__file__,'exec'),released.__dict__)
    profile=ImageCms.createProfile('sRGB')
    with patch('PIL.ImageCms.createProfile',return_value=profile):
        released.decode(source,tmp_path/'before.png',{},None)
        candidate.decode(source,tmp_path/'after.png',{},None)
    with Image.open(tmp_path/'before.png') as a,Image.open(tmp_path/'after.png') as b:
        assert a.size==b.size==(64,32) and a.mode==b.mode
        assert a.tobytes()==b.tobytes() and a.info['icc_profile']==b.info['icc_profile']
        if len(colour)==4:assert b.mode=='RGBA' and b.getpixel((30,20))[3]==128
    assert source.read_bytes()==before
