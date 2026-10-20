"""Focused unattended recovery contracts; all files/SQL identities synthetic."""
from pathlib import Path
import json,sys,io,struct
from datetime import datetime,timezone,timedelta
from unittest.mock import patch,Mock
import pytest
from PIL import Image,ImageCms
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
import auto_editions_local as local
import auto_editions_status as status
from auto_editions_colour import restore_export_profiles
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID,rows
from tests.test_auto_editions_status import record


def exports(tmp_path):
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    name=ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(profile))).strip()
    Image.new('RGB',(20,10),'red').save(tmp_path/'original.png',icc_profile=profile)
    Image.new('RGB',(20,10),'red').save(tmp_path/'master.png')
    return profile,dict(source_inspection={'document':{'profile':name}},export_profiles={'original.png':name,'master.png':name})


def idat(path):
    data=path.read_bytes();pos=8;result=[]
    while pos<len(data):
        n=struct.unpack('>I',data[pos:pos+4])[0]
        if data[pos+4:pos+8]==b'IDAT':result.append(data[pos:pos+n+12])
        pos+=n+12
    return result


def test_omitted_profile_is_restored_without_touching_compressed_pixels(tmp_path):
    profile,report=exports(tmp_path);before=idat(tmp_path/'master.png')
    assert restore_export_profiles(tmp_path,report,['original.png','master.png'])==['master.png']
    assert idat(tmp_path/'master.png')==before
    with Image.open(tmp_path/'master.png') as image:assert image.info['icc_profile']==profile
    assert restore_export_profiles(tmp_path,report,['original.png','master.png'])==[]


@pytest.mark.parametrize('fault',['missing','altered','conflict'])
def test_colour_evidence_fails_closed_before_local_change(tmp_path,fault):
    _,report=exports(tmp_path);before=(tmp_path/'master.png').read_bytes()
    if fault=='missing':report['export_profiles'].pop('master.png')
    elif fault=='altered':report['export_profiles']['master.png']='Other profile'
    else:Image.new('RGB',(20,10)).save(tmp_path/'original.png',icc_profile=b'invalid-profile')
    with pytest.raises((ValueError,OSError)):restore_export_profiles(tmp_path,report,['original.png','master.png'])
    assert (tmp_path/'master.png').read_bytes()==before


def test_owned_processor_lock_never_stolen_or_removed_after_owner_change(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    lock=local.processor_lease();path=tmp_path/'Documents/SportsCavePrintJobs/processor.lock'
    assert json.loads(path.read_text())['pid']==local.os.getpid()
    with pytest.raises(FileExistsError):local.processor_lease()
    path.write_text(json.dumps({'owner':'another-owner'}))
    with pytest.raises(RuntimeError):lock.unlink()
    assert path.exists()


def test_recovery_journal_contains_no_transfer_secret_and_uses_same_owned_lease(tmp_path,monkeypatch):
    folder=tmp_path/('b'*48);folder.mkdir();ctx={'automatic':True,'product_gid':PID,'lease_token':'owned','source':{'revision':'a1'}}
    row=dict(folder=folder,context=ctx,status='Working',grant={'secret':'NEVER-PERSIST','ticket':'NEVER-PERSIST'})
    local.journal(row);assert 'NEVER-PERSIST' not in (folder/'job-state.json').read_text()
    monkeypatch.setattr(local,'HOST_FILE',tmp_path/'host.dpapi')
    with patch.object(local,'host_request',return_value={'grant':{'base_url':'scoped'}}) as request,patch.object(local,'start') as start:
        assert local.recover_retained({'base_url':'scoped'})
    assert request.call_args.args[2]=={'product_gid':PID,'lease_token':'owned'}
    start.assert_called_once_with({'base_url':'scoped'},resume_folder=folder,package_transport=0,upload_protocol=0)


def test_lost_response_receipt_recovers_without_photoshop_or_second_upload(tmp_path,monkeypatch):
    folder=tmp_path/('c'*48);folder.mkdir();ctx={'automatic':True,'product_gid':PID,'lease_token':'owned','source':{'revision':'a1'}}
    local.journal(dict(folder=folder,context=ctx,status='Working'))
    monkeypatch.setattr(local,'HOST_FILE',tmp_path/'host.dpapi')
    with patch.object(local,'host_request',return_value={'completed':{'source':ctx['source'],'preparation_hash':'a'*64}}),patch.object(local,'finish_upload') as finish,patch.object(local,'start') as start:
        assert local.recover_retained({});finish.assert_called_once();start.assert_not_called()


def test_heartbeat_renews_only_owned_unclaimed_lease_and_protects_allocations(store):
    d,sql=store;register(store);tick(store,[asset()]);lease=d.queue.claim('owner');token=str(lease['lease_token'])
    before=rows(sql,'edition_allocations')
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    with pytest.raises(PermissionError):d.queue.heartbeat(PID,token,'other','Uploading')
    d.queue.heartbeat(PID,token,'owner','Uploading')
    row=rows(sql,'auto_edition_onboarding')[0];assert row['reason']=='Uploading'
    sql.execute('SELECT lease_until>now() AS renewed FROM auto_edition_onboarding WHERE product_gid=%s',(PID,))
    assert sql.fetchone()['renewed'] is True
    assert rows(sql,'edition_allocations')==before
    sql.execute("UPDATE auto_edition_onboarding SET lease_token=NULL")
    with pytest.raises(ValueError):d.queue.heartbeat(PID,token,'owner','Preparing')


def test_stale_and_uploading_status_are_not_false_preparing():
    now=datetime.now(timezone.utc)
    stale={**record(),'status':'Preparing','updated_at':now-timedelta(minutes=3)}
    assert status.project(stale,now=now)['status']=='Recovering'
    assert status.project({**stale,'updated_at':now,'reason':'Uploading'},now=now)['status']=='Uploading'


def test_orders_failure_is_an_actionable_status_link_without_remote_calls():
    import auto_editions_runtime as runtime
    from auto_editions_store import LayoutIndex
    index=LayoutIndex();index.reasons[PID]='Failed'
    registry=Mock();registry.index.return_value=index
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)),patch.object(runtime,'storage') as storage:
        links=runtime.download_links([dict(id=679,shopify_product_gid=PID)])
    assert links['679'].startswith('/auto-editions/status?') and links['679'].endswith('#Failed')
    storage.assert_not_called()


def test_urgent_paid_product_precedes_old_backlog_without_changing_167_deferred(store):
    d,sql=store;register(store);tick(store,[asset()])
    sql.execute("UPDATE auto_edition_onboarding SET priority=8")
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority,created_at,updated_at) VALUES('older','f',8,now()-interval '1 year',now()-interval '1 day')")
    for n in range(167):sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) VALUES(%s,'f',0)",('deferred-'+str(n),))
    def protected():
        sql.execute("SELECT to_jsonb(q) AS data FROM auto_edition_onboarding q WHERE priority=0 ORDER BY product_gid")
        return [r['data'] for r in sql.fetchall()]
    before=protected();allocations=rows(sql,'edition_allocations')
    first=d.queue.claim('host');assert first['product_gid']==PID
    for attempt in range(3):
        d.queue.defer_owned(PID,str(first['lease_token']),'host')
        if attempt<2:first=d.queue.claim('host');assert first['product_gid']==PID
    sql.execute('SELECT status,attempts FROM auto_edition_onboarding WHERE product_gid=%s',(PID,))
    assert sql.fetchone()=={'status':'Blocked','attempts':3}
    assert protected()==before and len(before)==167 and rows(sql,'edition_allocations')==allocations


def test_expired_lease_cannot_renew_over_another_active_processor(store):
    d,sql=store;register(store);tick(store,[asset()]);lease=d.queue.claim('host')
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second'")
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,lease_until) VALUES('another','f','Preparing',now()+interval '1 minute')")
    with pytest.raises(ValueError):d.queue.heartbeat(PID,str(lease['lease_token']),'host','Preparing')


def test_busy_companion_heartbeats_without_claiming_or_opening_photoshop(tmp_path,monkeypatch):
    config={'base_url':'https://sports-cave-image-factory.onrender.com','token':'a'*43}
    host=tmp_path/'host.dpapi';host.write_text(json.dumps(config))
    event=local.threading.Event()
    row={'status':'Working','phase':'Uploading','context':{'product_gid':PID,'lease_token':'owned'},'started_at':local.time.time()}
    monkeypatch.setattr(local,'HOST_FILE',host);monkeypatch.setattr(local,'HOST_STOP',event);monkeypatch.setattr(local,'HOST_WAKE',event);monkeypatch.setattr(local,'JOBS',{'job':row})
    import device_trust
    with patch.object(device_trust,'protect',side_effect=lambda data,**kw:data),patch.object(local,'host_request',return_value={}) as request,patch.object(event,'wait',side_effect=lambda delay:event.set()):
        local.host_loop()
    assert request.call_count==1 and request.call_args.args[1].endswith('/heartbeat')
    assert request.call_args.args[2]['stage']=='Uploading'
    state=json.loads((tmp_path/'host-status.json').read_text());assert state['status']=='Uploading'


def test_supervisor_continues_after_five_crashes_with_bounded_backoff(tmp_path,monkeypatch):
    import companion
    from contextlib import nullcontext
    child=Mock(pid=123);attempts=[]
    def failed_child():
        attempts.append(1)
        if len(attempts)==7:(tmp_path/'stopped').touch()
        return 1
    child.wait.side_effect=failed_child
    with patch.object(companion,'config',return_value=(tmp_path,{})),patch.object(companion,'instance_lock',return_value=nullcontext()),patch.object(companion,'existing_worker',return_value=child),patch.object(companion,'recover_previews'),patch.object(companion.time,'sleep') as sleep:
        companion.supervise(tmp_path,'task','owner')
    assert len(attempts)==7 and all(call.args[0]<=300 for call in sleep.call_args_list)


def test_heartbeat_endpoint_requires_host_and_rejects_arbitrary_stage():
    import asyncio
    from unittest.mock import AsyncMock
    import auto_editions_onboarding_api as api
    from tests.test_auto_editions_api import request,ADMIN
    assert asyncio.run(api.heartbeat(request('POST',body={}))).status_code==403
    req=request('POST',body={'product_gid':PID,'lease_token':'owned','stage':'Cloud Ready'})
    req.scope['headers'].append((b'x-sports-cave-preparation-host',b'a'*43))
    queue=Mock();queue.heartbeat.side_effect=ValueError('Unsupported preparation stage.')
    with patch.object(api,'preparation_actor',new=AsyncMock(return_value=ADMIN)),patch.object(api,'queue',return_value=queue):
        assert asyncio.run(api.heartbeat(req)).status_code==409


def test_only_exact_existing_product_approval_can_skip_repeated_review(tmp_path):
    from auto_editions_onboarding_store import Queue
    from tests.test_auto_editions import package
    import auto_editions as ae
    manifest=package(tmp_path);digest=ae.fingerprint(manifest)
    approval=dict(preparation_hash=digest,actor_id='original-owner',visual_approved=True,pixel_exact=True,test_only=True)
    # MagicMock supplies context managers; every query remains a read.
    from unittest.mock import MagicMock
    connection=MagicMock();cur=connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value={'manifest':manifest,'approval':approval}
    queue=Queue(connection)
    assert queue.imported_state(PID,digest,manifest['source'])=='Cloud Ready'
    assert queue.imported_state(PID,digest,{**manifest['source'],'revision':'changed'})=='Blocked'
    cur.fetchone.return_value={'manifest':manifest,'approval':{**approval,'visual_approved':False}}
    assert queue.imported_state(PID,digest,manifest['source'])=='Blocked'
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cur.execute.call_args_list)


def test_idle_stop_cannot_interrupt_work_or_an_inflight_claim(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    busy=local.threading.Event();stop=local.threading.Event()
    monkeypatch.setattr(local,'HOST_BUSY',busy);monkeypatch.setattr(local,'HOST_STOP',stop)
    monkeypatch.setattr(local,'JOBS',{'job':{'status':'Working'}})
    with pytest.raises(ValueError):local.prepare_stop()
    assert not stop.is_set()
    local.JOBS.clear();busy.set()
    with pytest.raises(ValueError):local.prepare_stop()
    assert not stop.is_set()
    busy.clear();local.prepare_stop();assert stop.is_set()


def test_backoff_retains_recovery_without_repeated_network_calls(tmp_path,monkeypatch):
    folder=tmp_path/('d'*48);folder.mkdir()
    row=dict(folder=folder,context={'automatic':True,'product_gid':PID,'lease_token':'owned','source':{}},status='Recovering',retry_at=local.time.time()+300)
    local.journal(row);monkeypatch.setattr(local,'HOST_FILE',tmp_path/'host.dpapi')
    with patch.object(local,'host_request') as request:
        assert local.recover_retained({});request.assert_called_once()
    assert request.call_args.args[1].endswith('/cancellation')


def test_finished_pixels_can_resume_packaging_without_reopening_photoshop(tmp_path):
    from tests.test_auto_editions import package
    import auto_editions as ae
    folder=tmp_path/'job';folder.mkdir();prepared=folder/'prepared';prepared.mkdir()
    manifest=package(prepared);manifest['confirmed_roles']={'number':'number','plaque':'plaque'}
    for n in (1,2):
        with ae.compose(manifest,prepared,n) as image:image.save(prepared/f'reference-{n}.png')
    import shutil
    shutil.copyfile(prepared/'master.png',prepared/'original.png')
    (prepared/'manifest.json').write_text(json.dumps(manifest))
    ctx=dict(source=manifest['source'],total=2,number=1)
    with patch('auto_editions_onboarding.preparation_scale',return_value=1):
        archive=local.package_finished({'folder':folder},ctx)
    assert archive and archive.exists()
    import zipfile
    with zipfile.ZipFile(archive) as z:assert {'master.png','number-1.png','number-2.png'}<=set(z.namelist())


def test_current_release_334_row_batch_cost(store,tmp_path):
    import subprocess,types,statistics,time,tracemalloc
    d,sql=store;register(store);tick(store,[asset()]);ids=[PID]+['gid://shopify/Product/'+str(n) for n in range(1000,1333)]
    baseline=types.ModuleType('approved_status_baseline')
    exec(compile(subprocess.check_output(['git','show','f3651669:auto_editions_status.py']).decode('utf-8'),'approved_status_baseline','exec'),baseline.__dict__)
    results={}
    for name,module in [('approved_f3651669',baseline),('local_reliability',status)]:
        times=[];tracemalloc.start()
        for _ in range(7):
            value=module.batch(d.connect,ids);times.append(value['duration_ms'])
            assert value['query_count']==1 and len(value['rows'])==334
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        results[name]={'median_ms':statistics.median(times),'peak_bytes':peak,'response_bytes':len(json.dumps(value).encode()),'queries':1,'dropbox_calls':0}
        assert results[name]['median_ms']<500
    output=Path(__file__).parents[1]/'output/reliability/current-baseline-performance.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(results,indent=2))
