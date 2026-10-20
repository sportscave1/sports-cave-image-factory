"""Only Phase 5 risks: conservative estimates, durable binding, control/UX gates."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock
import pytest
from companion_bandwidth import Policy,TTL
from companion_transfer import Controller,post_file
from companion_transfer_control import evidence
from tests.test_companion_phase2_transfers import receiver
from tests.test_auto_editions_jobs import database
from tests.test_companion_phase3 import env,http_receiver,verify


def sample(mbps=20,**extra):
    count=8*1024**2;seconds=count*8/(mbps*1_000_000)
    return dict(capacity_eligible=True,transport_bytes=count,server_received_bytes=count,
        body_first_handoff_seconds=.001,body_last_handoff_seconds=seconds+.001,
        server_body_receive_seconds=seconds,allowance_wait_seconds=0,disk_read_seconds=.001,**extra)


def test_calibration_smoothing_hysteresis_staleness_and_capped_rejection():
    p=Policy()
    for stamp in (1000,1010,1020):assert p.observe_transfer(sample(),now=stamp)
    v=Controller().value
    assert 19.9<p.rate(v,now=1020)<20.1
    before=p.saved()
    for key,val in [('capacity_eligible',False),('allowance_wait_seconds',1),('disk_read_seconds',2),('server_body_receive_seconds',.001),('server_received_bytes',0)]:
        assert not p.observe_transfer({**sample(),key:val},now=1030)
        assert p.saved()==before
    # One slow sample cannot collapse the estimate; sustained lower rates can.
    p.observe_transfer(sample(10),now=1030);assert p.estimate==before['estimate']
    p.observe_transfer(sample(10),now=1040);assert p.estimate==pytest.approx(before['estimate']*.8)
    for stamp in (1050,1060,1070):
        old=p.estimate;p.observe_transfer(sample(30),now=stamp);assert p.estimate<=old*1.05
    assert p.rate(v,now=1070+TTL) is None


def test_mode_limits_and_persisted_measurements_never_change_owner_choice(tmp_path):
    path=tmp_path/'settings.json';c=Controller(path);c.configure(dict(mode='Maximum speed'),'request_10')
    # Fixture rates, no internet measurement claimed.
    for _ in range(3):c.observe_transfer(sample())
    assert c.snapshot()['settings']['mode']=='Maximum speed' and c.rate() is None
    r=Controller(path);assert r.snapshot()['calibration']['sample_count']==3
    r.configure({**r.value,'mode':'Balanced'},'request_11');assert r.rate()==pytest.approx(r.policy.estimate*.75*1_000_000/8)
    r.configure({**r.value,'mode':'Background'},'request_12');assert r.rate()==pytest.approx(r.policy.estimate*.75*.25*1_000_000/8)
    r.configure({**r.value,'mode':'Manual','manual_mbps':4},'request_13');r.policy.factor=.25
    assert r.rate()==500000 and evidence(r.snapshot())['capability']==3
    r.configure({**r.value,'mode':'Maximum speed'},'request_12');assert r.value['mode']=='Manual'


def test_latency_requires_sustained_evidence_bounded_cut_and_gradual_recovery():
    p=Policy()
    for _ in range(3):p.observe_latency(.02,loaded=False)
    assert not p.observe_latency(.3,loaded=True,now=100)
    p.observe_latency(.02,loaded=True,now=101);assert p.factor==1
    for stamp in (102,103,104):p.observe_latency(.4,loaded=True,now=stamp)
    assert p.factor==.8
    for stamp in (105,106,107):p.observe_latency(.4,loaded=True,now=stamp)
    assert p.factor==.8 # No repeated rapid cuts.
    for stamp in range(170,175):p.observe_latency(.02,loaded=True,now=stamp)
    assert p.factor==pytest.approx(.84)
    for stamp in range(200,1000,31):p.observe_latency(.8,loaded=True,now=stamp)
    assert .25<=p.factor<=.84 and p.estimate is None


def test_real_receiver_reduced_budget_manual_authority_and_independent_control(tmp_path):
    path=tmp_path/'payload';path.write_bytes(b'x'*512*1024)
    c=Controller();c.configure(dict(mode='Balanced',sustainable_mbps=8))
    for _ in range(3):c.observe_control(.02,loaded=False)
    c.policy.last_change=time.monotonic()-31
    for _ in range(3):c.observe_control(.5,loaded=True)
    assert c.rate()==pytest.approx(600000)
    with receiver() as (url,rows,_),ThreadPoolExecutor(2) as pool:
        start=time.monotonic();future=pool.submit(post_file,c,url+'/bulk',path,{})
        import requests
        beats=[]
        while not future.done():
            tick=time.monotonic();requests.post(url+'/heartbeat',json={'lease':'fixture'},timeout=1).raise_for_status();beats.append(time.monotonic()-tick);time.sleep(.05)
        response,trace=future.result();elapsed=time.monotonic()-start;response.raise_for_status()
    assert trace['transport_bytes']==trace['server_received_bytes']==path.stat().st_size
    assert elapsed>=path.stat().st_size/600000-.06 and max(beats)<.3 and len(beats)>4
    assert c.policy.samples==[] # Capped receiver progress never calibrates.
    c.configure(dict(mode='Manual',manual_mbps=8));assert c.rate()==1_000_000


def test_partial_or_failed_stream_has_no_speed_eta_and_health_remains_bounded():
    c=Controller();c.configure(dict(mode='Manual',manual_mbps=4))
    with c.slot(1024*1024,resumable=True) as t:
        t.update(state='Uploaded, verifying',transport_bytes=1024*1024,transfer_seconds=2,verification_seconds=100)
        s=c.snapshot();assert s['transfer']['payload_bytes_per_second'] is None and s['transfer']['eta_seconds'] is None
        assert evidence(s)
    with pytest.raises(ValueError):evidence({**c.snapshot(),'calibration':{**c.snapshot()['calibration'],'token':'forbidden'}})


def test_acceptance_flag_is_separate_and_default_closed(monkeypatch):
    import companion_package_api as api
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','true');monkeypatch.setenv('SPORTS_CAVE_AUTO_EDITIONS_V6','true')
    monkeypatch.delenv('COMPANION_RESUMABLE_ACCEPTANCE',raising=False);assert api.capability()==0
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','true');assert api.capability()==0
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE','provider-postgres-retention-v1');assert api.capability()==0
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE_GENERATION',__import__('companion_package_identity').generation())
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE_EVIDENCE_SHA256','f'*64);assert api.capability()==1
    monkeypatch.setenv('COMPANION_RESUMABLE_ACCEPTANCE_GENERATION','0'*64);assert api.capability()==0
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','false');assert api.capability()==0


def test_summary_does_not_sum_overlap_invent_network_or_expose_secrets(tmp_path):
    from companion_job_summary import summary
    row=dict(folder=tmp_path,timings=dict(prepare_validate_seconds=10,photoshop_prepare_seconds=8,package_build_seconds=1,source_reused=True),
        server_timings=dict(handler_total_seconds=100,validation_seconds=20,token='secret'),
        transfer_attempts=[dict(correlation_id='a'*32,server_received_bytes=123,verification_seconds=90)],
        transfer_totals=dict(payload_bytes=123,body_stream_seconds=2))
    s=summary(row,dict(status='Uploading'));assert s['completion']=='Uploaded, verifying'
    assert s['queue']['wait_seconds'] is None and s['preparation']['prepare_validate_seconds']==10
    assert 'secret' not in json.dumps(s) and 'internet_seconds' not in json.dumps(s)
    assert len(json.dumps(s))<4096


def test_unverified_completion_retains_packet_without_cloud_receipt(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    cleanup=Mock();monkeypatch.setattr(local,'release_verified_temporary_files',cleanup);monkeypatch.setattr(local,'journal',lambda _:None)
    row=dict(folder=tmp_path,context=dict(automatic=True),timings=dict(package_bytes=10))
    local.finish_upload(row,dict(preparation_hash='a'*64,status='Uploading'),time.monotonic())
    cleanup.assert_not_called();assert json.loads((tmp_path/'job-summary.json').read_text())['completion']=='Uploaded, verifying'


def test_memory_next_step_preserves_phase4_default():
    from worker_diagnostics import explain
    from scripts.prepare_auto_editions import select_export_strategy
    assert explain('Photoshop not enough memory')['code']=='MEMORY_PRESSURE'
    assert select_export_strategy() in ('history_merged_crop','duplicate_merged')


def test_real_uncapped_stream_calibrates_only_with_receiver_timing(tmp_path,record_property):
    import hashlib,socket,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import requests
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            total=int(self.headers['Content-Length']);received=0;started=None
            while received<total:
                block=self.rfile.read(min(16384,total-received))
                if not block:return
                if started is None:started=time.monotonic()
                received+=len(block)
                time.sleep(len(block)/2_000_000) # Explicit local fixture capacity.
            duration=time.monotonic()-started
            self.send_response(200);self.send_header('Content-Length','2')
            self.send_header('X-SC-Transfer-ID',self.headers['X-SC-Transfer-ID'])
            self.send_header('X-SC-Received-Bytes',str(received))
            self.send_header('X-SC-Body-Receive-Seconds',str(round(duration,6)))
            self.end_headers();self.wfile.write(b'{}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    path=tmp_path/'payload';path.write_bytes(b'x'*8*1024**2)
    c=Controller(tmp_path/'settings.json');c.configure(dict(mode='Maximum speed'));c.session=requests.Session()
    # Bound the fixture's sender buffer so the real streaming calls expose
    # backpressure; no custom adapter and no production transport setting.
    adapter=c.session.get_adapter('http://127.0.0.1')
    from urllib3.connection import HTTPConnection
    adapter.poolmanager.connection_pool_kw['socket_options']=HTTPConnection.default_socket_options+[(socket.SOL_SOCKET,socket.SO_SNDBUF,32768)]
    try:
        for _ in range(3):post_file(c,f'http://127.0.0.1:{server.server_port}/bulk',path,{})[0].raise_for_status()
        s=c.snapshot();assert s['calibration']['sample_count']==3
        assert 8<s['calibration']['sustainable_mbps']<17
        assert s['settings']['mode']=='Maximum speed' and s['effective_mbps'] is None
        assert Controller(c.path).policy.samples==c.policy.samples
        record_property('calibration_receiver',json.dumps(dict(application_bytes=3*path.stat().st_size,
            samples_mbps=c.policy.samples,estimate_mbps=c.policy.estimate,mode=c.value['mode'],local_only=True)))
    finally:c.session.close();server.shutdown();server.server_close();thread.join(2)


def test_lost_finalize_ack_reuses_complete_server_session(env,monkeypatch,record_property):
    import requests
    from companion_package_client import upload
    from companion_package_store import Sessions
    from tests.test_companion_phase3 import DiskProvider
    e=env;c=Controller();c.configure(dict(mode='Maximum speed'));journal=e.root/'client.json'
    with http_receiver(e,monkeypatch) as (base,token,seen):
        grant=dict(base_url=base,ticket='fixture',secret='fixture');host=dict(base_url=base,token=token)
        original=e.store.finalize
        def lost(*args):
            original(*args);raise requests.ConnectionError('Lost finalisation acknowledgement')
        monkeypatch.setattr(e.store,'finalize',lost)
        with pytest.raises(requests.HTTPError):upload(c,e.path,grant,host,journal,correlation='e'*32)
        saved=json.loads(journal.read_text());assert saved['confirmed_bytes']==e.path.stat().st_size
        before=e.provider.sent;assert e.provider.finishes==1
        e.provider=DiskProvider(e.provider.root);e.store=Sessions(e.connect,e.provider)
        assert e.store.run_one(lambda row,path:verify(e,row,path))
        restarted=Controller();restarted.configure(dict(mode='Maximum speed'))
        assert upload(restarted,e.path,grant,host,journal,correlation='e'*32)['status']=='Cloud Ready'
        assert sum(r['bytes'] for r in seen if r['path'].endswith('/chunk'))==e.path.stat().st_size
        assert before==e.path.stat().st_size and e.provider.sent==0
        record_property('finalize_recovery',json.dumps(dict(payload_bytes=e.path.stat().st_size,resent_bytes=0,
            duplicate_publication=0,local_provider=True)))


@pytest.mark.parametrize('fault',['regressed','session','generation','incomplete','preparation'])
def test_client_refuses_inconsistent_confirmed_ack(env,monkeypatch,fault):
    import requests,auto_editions as ae
    import companion_package_client as client
    from tests.test_companion_phase3 import create
    e=env;state=create(e);journal=e.root/'client.json'
    saved=dict(protocol=1,descriptor=ae.fingerprint(e.descriptor),id=state['id'],confirmed_bytes=e.path.stat().st_size if fault=='regressed' else 0)
    journal.write_text(json.dumps(saved))
    if fault=='session':state['id']='b'*64
    if fault=='generation':state['generation']='0'*64
    if fault=='incomplete':state['state']='Complete'
    if fault=='preparation':state['result']=dict(preparation_hash='0'*64)
    response=requests.Response();response.status_code=200;response._content=json.dumps(state).encode()
    monkeypatch.setattr(client.requests,'post',lambda *a,**k:response)
    bulk=Mock();monkeypatch.setattr(client,'post_file',bulk)
    c=Controller();c.configure(dict(mode='Maximum speed'))
    with pytest.raises(ValueError):client.upload(c,e.path,dict(base_url='https://fixture',ticket='fixture',secret='fixture'),dict(base_url='https://fixture',token='fixture'),journal,correlation='f'*32)
    bulk.assert_not_called();assert json.loads(journal.read_text())==saved


def test_expiring_calibration_finishes_admitted_body_then_blocks_new_work():
    c=Controller()
    for _ in range(3):c.observe_transfer(sample())
    c.configure(dict(mode='Balanced'),'request_1')
    admitted=c.rate()
    with c.slot(8*1024**2) as trace:
        c.policy.measured_at=time.time()-TTL-1
        assert c.rate()==admitted and c.snapshot()['effective_mbps']>0
    assert c.rate()==0 and c.snapshot()['protection']=='Calibration needed'


def test_unaccepted_create_never_initializes_provider(monkeypatch):
    import asyncio
    import companion_package_api as api,auto_editions_onboarding_api as onboarding
    from starlette.requests import Request
    from unittest.mock import AsyncMock
    monkeypatch.setenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','true');monkeypatch.setenv('SPORTS_CAVE_AUTO_EDITIONS_V6','true')
    monkeypatch.delenv('COMPANION_RESUMABLE_ACCEPTANCE',raising=False)
    monkeypatch.setattr(onboarding,'preparation_actor',AsyncMock(return_value=dict(id='fixture-owner')))
    provider=Mock(side_effect=AssertionError('Unaccepted provider access'));monkeypatch.setattr(api,'service',provider)
    request=Request(dict(type='http',method='POST',path='/api/auto-editions/uploads/create',path_params=dict(upload_action='create'),headers=[(b'x-sports-cave-preparation-host',b'fixture')],query_string=b''))
    response=asyncio.run(api.host(request));assert response.status_code==409
    provider.assert_not_called()


def test_failed_settings_write_does_not_ack_or_change_effective_allowance(tmp_path,monkeypatch):
    c=Controller(tmp_path/'settings.json');c.configure(dict(mode='Balanced',sustainable_mbps=20),'request_1')
    c.policy.factor=.8;before=c.rate()
    def fail(*args,**kwargs):raise OSError('Disk full')
    monkeypatch.setattr(c,'_persist',fail)
    with pytest.raises(OSError):c.configure(dict(mode='Balanced',sustainable_mbps=50),'request_2')
    assert c.rate()==before and c.revision=='request_1' and c.value['sustainable_mbps']==20


def test_pause_reconciliation_refuses_server_progress_regression(env,monkeypatch):
    import hashlib
    import auto_editions as ae
    from companion_package_client import upload
    from tests.test_companion_phase3 import padded
    from companion_package_identity import CHUNK
    e=env;padded(e);c=Controller();c.configure(dict(mode='Maximum speed'));journal=e.root/'pause-client.json'
    with http_receiver(e,monkeypatch) as (base,token,seen):
        host_hash=hashlib.sha256(token.encode()).hexdigest()
        state=e.store.create('owner',host_hash,base,e.context,e.descriptor)
        with e.path.open('rb') as source:content=source.read(CHUNK)
        e.store.chunk(state['id'],'owner',host_hash,0,content,hashlib.sha256(content).hexdigest())
        journal.write_text(json.dumps(dict(protocol=1,descriptor=ae.fingerprint(e.descriptor),id=state['id'],confirmed_bytes=CHUNK)))
        def paused(*args):
            e.sql.execute("UPDATE companion_package_uploads SET data=jsonb_set(data,'{offset}','0'::jsonb)")
            return True
        monkeypatch.setattr(c,'chunk_boundary',paused)
        with pytest.raises(ValueError,match='after pause'):
            upload(c,e.path,dict(base_url=base,ticket='fixture',secret='fixture'),dict(base_url=base,token=token),journal,correlation='a'*32)
        assert not any(r['path'].endswith('/chunk') for r in seen)
        assert json.loads(journal.read_text())['confirmed_bytes']==CHUNK and e.provider.sent==CHUNK
