"""Synthetic overlap admission, real SQL leases and fast authenticated reads."""
import sys
import hashlib
from pathlib import Path
import json
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest
import requests
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
import edition_pipeline as pipeline
from tests.test_auto_editions_jobs import database
from tests.test_companion_phase3 import env,http_receiver,create
from tests.test_auto_editions_onboarding import setup_queue


@pytest.fixture
def peer(tmp_path,monkeypatch):
    folder=tmp_path/'a';folder.mkdir();(folder/'prepared.zip').write_bytes(b'verified fixture')
    monkeypatch.setattr(pipeline.shutil,'disk_usage',lambda _:SimpleNamespace(free=20*pipeline.GIB))
    monkeypatch.setattr('psutil.virtual_memory',lambda:SimpleNamespace(available=8*pipeline.GIB))
    return dict(folder=folder,status='Working',phase='Uploading',native_released=True,
                upload_protocol=1,context=dict(automatic=True))


def test_one_upload_only_admits_one_native_peer(peer,tmp_path):
    assert pipeline.admission([peer],tmp_path) is peer
    assert pipeline.admission([peer,dict(peer,phase='Preparing')],tmp_path) is None
    assert pipeline.admission([peer],tmp_path,paused=True) is None
    assert pipeline.admission([peer],tmp_path,processor_locked=True) is None


@pytest.mark.parametrize('change',[
    dict(native_released=False),dict(upload_protocol=0),dict(cancel_requested=True),
    dict(checkpoint_pending=True),dict(phase='Preparing'),dict(context=dict(automatic=False))])
def test_unreleased_legacy_cancelled_or_interactive_job_cannot_overlap(peer,tmp_path,change):
    peer.update(change)
    assert pipeline.admission([peer],tmp_path) is None


def test_resource_gates_fail_closed_and_native_wait_falls_back_to_serial(peer,tmp_path,monkeypatch):
    monkeypatch.setattr('psutil.virtual_memory',lambda:SimpleNamespace(available=pipeline.MIN_FREE_RAM-1))
    assert pipeline.admission([peer],tmp_path) is None
    next_folder=tmp_path/'b';next_folder.mkdir()
    row=dict(folder=next_folder,status='Working',context=dict(metadata=dict(size=1024)))
    assert pipeline.native_budget([peer,row],row,tmp_path) is False
    peer['status']='Prepared'
    assert pipeline.native_budget([peer,row],row,tmp_path) is True


def test_large_source_reservation_and_unowned_paths_block_overlap(peer,tmp_path,monkeypatch):
    monkeypatch.setattr(pipeline,'footprint',lambda *a:7*pipeline.GIB)
    assert pipeline.admission([peer],tmp_path) is None
    monkeypatch.undo()
    peer['folder']=tmp_path.parent
    assert pipeline.admission([peer],tmp_path) is None


@pytest.fixture
def sql_pipeline(database,monkeypatch):
    for name in ('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED'):
        monkeypatch.delenv(name,raising=False)
    queue,sql=setup_queue(database)
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261020002955_companion_resumable_packages.sql').read_text())
    sql.execute((Path(__file__).parents[1]/'supabase/migrations/20261121233808_editions_pipeline_live_lease_lookup.sql').read_text())
    sql.execute("INSERT INTO product_psd_mappings VALUES('p2','f2'),('p3','f3')")
    for pid,fid in [('p','f'),('p2','f2'),('p3','f3')]:queue.enqueue(pid,fid,'admin')
    first=queue.claim('admin');pid=first['product_gid'];token=str(first['lease_token'])
    sql.execute("""INSERT INTO companion_package_uploads(id,owner_id,host_hash,shop_origin,context,descriptor,data)
        VALUES(%s,'admin',%s,'https://synthetic.invalid',%s::jsonb,'{}',%s::jsonb)""",
        ('a'*64,'b'*64,json.dumps(dict(product_gid=pid,lease_token=token)),json.dumps(dict(offset=8388608))))
    return SimpleNamespace(queue=queue,sql=sql,first=first,
        proof=dict(product_gid=pid,lease_token=token,host_hash='b'*64))


def test_sql_two_leases_one_durable_upload_and_no_third_claim(sql_pipeline):
    e=sql_pipeline
    assert e.queue.claim('admin') is None
    second=e.queue.claim('admin',e.proof)
    assert second and second['product_gid']!=e.first['product_gid']
    assert e.queue.claim('admin',e.proof) is None
    e.queue.heartbeat(e.first['product_gid'],e.proof['lease_token'],'admin','Uploading')
    e.queue.heartbeat(second['product_gid'],str(second['lease_token']),'admin','Preparing')
    with pytest.raises(PermissionError):
        e.queue.heartbeat(second['product_gid'],str(second['lease_token']),'other-admin','Preparing')


@pytest.mark.parametrize('fault',['zero','expired','wrong_host','wrong_actor','superseded'])
def test_sql_overlap_cannot_bypass_owned_acknowledged_live_lease(sql_pipeline,fault):
    e=sql_pipeline;actor='admin';proof=dict(e.proof)
    if fault=='zero':e.sql.execute("UPDATE companion_package_uploads SET data='{"+'"offset":0'+"}'::jsonb")
    if fault=='expired':e.sql.execute("UPDATE companion_package_uploads SET expires_at=now()-interval '1 minute'")
    if fault=='wrong_host':proof['host_hash']='c'*64
    if fault=='wrong_actor':actor='other-admin'
    if fault=='superseded':e.sql.execute('UPDATE auto_edition_onboarding SET lease_token=gen_random_uuid() WHERE product_gid=%s',(proof['product_gid'],))
    with pytest.raises(ValueError):e.queue.claim(actor,proof)


def test_sql_pause_prevents_pipeline_claim(sql_pipeline):
    from worker_health import set_pause
    e=sql_pipeline;set_pause(e.queue.connect,True,'admin')
    assert e.queue.claim('admin',e.proof) is None


def test_pending_status_does_not_enter_slow_source_or_provider_work(env,monkeypatch):
    import companion_package_api as api
    e=env;state=create(e)
    with http_receiver(e,monkeypatch) as (base,token,seen):
        e.sql.execute('UPDATE companion_package_uploads SET host_hash=%s,shop_origin=%s',
                      (hashlib.sha256(token.encode()).hexdigest(),base))
        fence=Mock(side_effect=AssertionError('Pending read reached expensive source fence'))
        monkeypatch.setattr(api,'current',fence)
        start=time.monotonic()
        result=requests.post(base+'/api/auto-editions/uploads/status?id='+state['id'],json={},
            headers={'X-Sports-Cave-Preparation-Host':token},timeout=3)
        assert result.status_code==200,result.text
        assert result.json()['state']=='Receiving' and not result.json().get('result')
        assert time.monotonic()-start<1
        fence.assert_not_called()


def test_complete_status_still_runs_fresh_source_fence(env,monkeypatch):
    import companion_package_api as api
    e=env;state=create(e)
    e.sql.execute("UPDATE companion_package_uploads SET state='Complete',result='{}'::jsonb")
    with http_receiver(e,monkeypatch) as (base,token,seen):
        e.sql.execute('UPDATE companion_package_uploads SET host_hash=%s,shop_origin=%s',
                      (hashlib.sha256(token.encode()).hexdigest(),base))
        fence=Mock(side_effect=ValueError('Source changed'))
        monkeypatch.setattr(api,'current',fence)
        response=requests.post(base+'/api/auto-editions/uploads/status?id='+state['id'],json={},
            headers={'X-Sports-Cave-Preparation-Host':token},timeout=3)
        assert response.status_code==409
        fence.assert_called_once()


@pytest.mark.parametrize('cancel_second',[False,True])
def test_real_start_and_native_lease_overlap_without_source_crossover(tmp_path,monkeypatch,cancel_second):
    import threading
    import auto_editions_local as local
    from tests.test_auto_editions import package
    root=tmp_path/'Documents/SportsCaveAutoEditions';root.mkdir(parents=True)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    monkeypatch.setattr(local,'HOST_FILE',root/'host.dpapi')
    monkeypatch.setattr(local,'JOBS',{})
    monkeypatch.setattr(local,'cancellation_check',lambda *a,**k:False)
    monkeypatch.setattr(local,'context',lambda grant:grant['synthetic_context'])
    monkeypatch.setattr(pipeline,'native_budget',lambda *a:True)
    upload_entered=threading.Event();second_native=threading.Event();release=threading.Event();release_native=threading.Event()
    uploaded=[];threads=[];native=[]
    def build(source,output,identity,**kwargs):
        assert (tmp_path/'Documents/SportsCavePrintJobs/processor.lock').exists()
        native.append(identity['file_id'])
        if len(native)==2:
            assert upload_entered.is_set() and not release.is_set()
            second_native.set()
            assert release_native.wait(5)
        output.mkdir();manifest=package(output);manifest['source']=identity
        (output/'manifest.json').write_text(json.dumps(manifest))
        (output/'original.png').write_bytes((output/'master.png').read_bytes())
        import auto_editions as ae
        for number in (1,2):ae.compose(manifest,output,number).save(output/f'reference-{number}.png')
    def upload(key,path):
        row=local.JOBS[key];row['phase']='Uploading'
        assert row['native_released'] and not (tmp_path/'Documents/SportsCavePrintJobs/processor.lock').exists()
        if not upload_entered.is_set():
            upload_entered.set();assert release.wait(5)
        uploaded.append((row['context']['source']['file_id'],path.parent.name))
        row['status']='Prepared'
    def inspect(key):
        threads.append(threading.current_thread())
        (local.JOBS[key]['folder']/'input.psd').write_bytes(b'synthetic original')
        local.prepare_worker(key,dict(number='Number',plaque='Plaque'))
    monkeypatch.setattr(local,'inspect',inspect)
    monkeypatch.setattr(local,'upload_prepared',upload)
    monkeypatch.setattr('scripts.prepare_auto_editions.prepare',build)
    monkeypatch.setattr(local,'find_reusable_package',lambda *a,**k:None)
    monkeypatch.setattr(local,'package_finished',lambda *a,**k:None)
    def context(number):
        return dict(automatic=True,source=dict(product_gid=f'gid://shopify/Product/{number}',
            file_id=f'id:synthetic-{number}',revision='a1',content_hash='a'*64),number=1,total=2,
            metadata=dict(size=18),product_gid=f'gid://shopify/Product/{number}',lease_token=str(number))
    first=context(1);second=context(2)
    a=local.start(dict(synthetic_context=first),initial_context=first,upload_protocol=1)
    try:
        assert upload_entered.wait(5),[(r['status'],r.get('error')) for r in local.JOBS.values()]
        b=local.start(dict(synthetic_context=second),initial_context=second,upload_protocol=1,pipeline=True)
        assert second_native.wait(5)
        if cancel_second:local.JOBS[b['job_id']]['cancel_requested']=True
        with pytest.raises(ValueError,match='already running'):
            local.start(dict(synthetic_context=context(3)),initial_context=context(3),upload_protocol=1,pipeline=True)
    finally:
        release.set()
        release_native.set()
        for thread in threads:thread.join(5)
    assert native==['id:synthetic-1','id:synthetic-2']
    assert sorted(uploaded)==sorted([('id:synthetic-1',a['job_id'])]+([] if cancel_second else [('id:synthetic-2',b['job_id'])]))
    assert local.JOBS[a['job_id']]['status']=='Prepared'
    assert local.JOBS[b['job_id']]['status']==('Cancelled' if cancel_second else 'Prepared')
    assert (local.JOBS[b['job_id']]['folder']/'input.psd').read_bytes()==b'synthetic original'
    assert not (tmp_path/'Documents/SportsCavePrintJobs/processor.lock').exists()


def test_accepted_packets_run_before_optional_provider_diagnosis(monkeypatch):
    import auto_editions_runtime as runtime
    import companion_package_api as api
    jobs=Mock();monkeypatch.setattr(runtime,'stores',lambda:(None,jobs))
    monkeypatch.setattr(runtime,'enabled',Mock(side_effect=[True,False]))
    process=Mock(return_value=True);monkeypatch.setattr(api,'run_one',process)
    runtime._loop()
    process.assert_called_once()
    jobs.expired.assert_not_called()


def test_pending_http_reads_stay_responsive_during_slow_write_fence(env,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import companion_package_api as api
    e=env;state=create(e);entered=threading.Event()
    with http_receiver(e,monkeypatch) as (base,token,seen),ThreadPoolExecutor(1) as pool:
        e.sql.execute('UPDATE companion_package_uploads SET host_hash=%s,shop_origin=%s',
                      (hashlib.sha256(token.encode()).hexdigest(),base))
        def slow(row):entered.set();time.sleep(.4)
        monkeypatch.setattr(api,'current',slow)
        headers={'X-Sports-Cave-Preparation-Host':token}
        write=pool.submit(requests.post,base+'/api/auto-editions/uploads/chunk?id='+state['id'],
                          json={},headers=headers,timeout=3)
        assert entered.wait(1)
        samples=[]
        for _ in range(10):
            start=time.monotonic()
            response=requests.post(base+'/api/auto-editions/uploads/status?id='+state['id'],json={},headers=headers,timeout=3)
            samples.append(time.monotonic()-start)
            assert response.status_code==200 and response.json()['state']=='Receiving'
        assert sorted(samples)[-1]<.2
        assert write.result().status_code==409
        print('synthetic_loaded_status_http_p95_ms='+str(round(sorted(samples)[-1]*1000,3)))
