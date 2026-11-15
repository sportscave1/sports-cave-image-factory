"""Real loopback receivers; no credentials, provider, Photoshop or live jobs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

import pytest
import requests
from companion_transfer import Controller, Body, allowance, settings, post_file


@contextmanager
def receiver(*, delay=0, response_delay=0, failures=0, stall=False):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup()
            with lock: connections.append(time.monotonic())
        def log_message(self,*args): pass
        def do_GET(self):
            body=bytes(range(256))*256
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            if stall:
                time.sleep(.4);self.close_connection=True;return
            size=int(self.headers['Content-Length']); received=0; digest=hashlib.sha256(); points=[]
            while received<size:
                block=self.rfile.read(min(1024,size-received))
                if not block: break
                received+=len(block);digest.update(block)
                # Full retained packages must not allocate one point per KiB.
                if size<=1024**2 or not points or received-points[-1][1]>=size/512 or received==size:
                    points.append((time.monotonic(),received))
                if delay:time.sleep(delay)
            row=dict(path=self.path,bytes=received,sha256=digest.hexdigest(),points=points,
                     correlation=self.headers.get('X-SC-Transfer-ID'))
            with lock: records.append(row); number=len([r for r in records if r['path']=='/bulk'])
            if self.path=='/bulk':time.sleep(response_delay)
            data=json.dumps(dict(ok=True)).encode()
            try:
                self.send_response(503 if self.path=='/bulk' and number<=failures else 200)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('X-SC-Transfer-ID',row['correlation'] or '')
                self.send_header('X-SC-Received-Bytes',str(received))
                self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    lock=threading.Lock();records=[];connections=[]
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',records,connections
    finally:
        server.shutdown();server.server_close();thread.join(2)


def capped(rate=1.048576, path=None):
    c=Controller(path);c.configure(dict(mode='Manual',manual_mbps=rate));return c


def payload(tmp_path,size=131072):
    path=tmp_path/'package.zip';path.write_bytes(bytes(range(256))*(size//256));return path


def test_aggregate_receiver_rate_burst_bytes_hash_and_control_responsiveness(tmp_path):
    path=payload(tmp_path);c=capped();stopped=threading.Event();beats=[]
    with receiver(response_delay=.15) as (url,rows,_):
        def heartbeat():
            while not stopped.wait(.07):
                start=time.monotonic();requests.post(url+'/heartbeat',json={'lease':'synthetic'},timeout=1).raise_for_status()
                beats.append(time.monotonic()-start)
        thread=threading.Thread(target=heartbeat);thread.start()
        start=time.monotonic()
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(post_file,c,url+'/bulk',path,{}) for _ in range(2)]
            results=[f.result(10) for f in futures]
        elapsed=time.monotonic()-start;stopped.set();thread.join(2)
    bulk=[r for r in rows if r['path']=='/bulk'];rate=allowance(c.value)
    assert len(bulk)==2 and all(r['sha256']==hashlib.sha256(path.read_bytes()).hexdigest() for r in bulk)
    assert elapsed>=2*path.stat().st_size/rate-.15
    assert elapsed<3.5
    assert len(beats)>10 and max(beats)<.4
    assert max(t['slot_wait_seconds'] for _,t in results)>.8
    for row,(_,trace) in zip(bulk,sorted(results,key=lambda x:x[1]['slot_wait_seconds'])):
        assert trace['transport_bytes']==trace['disk_bytes']==trace['server_received_bytes']==path.stat().st_size
        assert trace['allowance_wait_seconds']>.5
        assert trace['response_after_last_handoff_seconds']>=.14
        assert row['points'][-1][0]-row['points'][0][0]>.65 # Not a buffered whole body.
        # Every observed sliding window must fit rate + small bounded burst +
        # loopback scheduling tolerance. No full-file opening burst permitted.
        points=row['points']
        for a,b in zip(points,points[16:]):
            assert b[1]-a[1] <= rate*(b[0]-a[0])+16384+8192


def test_pause_after_current_and_dynamic_rate_persist(tmp_path):
    c=capped(.524288,tmp_path/'settings.json');path=payload(tmp_path)
    with receiver() as (url,rows,_),ThreadPoolExecutor(2) as pool:
        first=pool.submit(post_file,c,url+'/bulk',path,{})
        while not c.active or c.active['transport_bytes']<32768:time.sleep(.01)
        c.configure({**c.value,'paused':True},'pause')
        second=pool.submit(post_file,c,url+'/bulk',path,{})
        assert c.snapshot()['pause_state']=='Pause after current transfer'
        c.configure({**c.value,'manual_mbps':2.097152},'faster')
        response,trace=first.result(4);response.raise_for_status()
        assert not second.done() and len(rows)==1
        assert trace['request_seconds']<1.6 # Initial 0.5 Mbps then 2 Mbps, not 2s old rate.
        assert c.snapshot()['pause_state']=='Transfers paused'
        time.sleep(.12);assert len(rows)==1
        c.configure({**c.value,'paused':False},'resumed')
        second.result(4)[0].raise_for_status()
    loaded=Controller(c.path)
    assert loaded.value==c.value and loaded.revision=='resumed'
    assert len(rows)==2 and rows[0]['sha256']==rows[1]['sha256']
    early=rows[0]['points'];start=early[0][0]
    # Receiver observations include the rate change, not just configure calls.
    assert early[-1][0]-start<1.4
    assert rows[1]['points'][-1][0]-rows[1]['points'][0][0]<.8


def test_retries_share_allowance_and_slow_receiver_timeout_classification(tmp_path):
    path=payload(tmp_path,65536);c=capped(1.048576)
    with receiver(failures=1) as (url,rows,_):
        start=time.monotonic();first,t1=post_file(c,url+'/bulk',path,{})
        assert first.status_code==503
        second,t2=post_file(c,url+'/bulk',path,{})
        assert second.status_code==200
        assert time.monotonic()-start>=.88
        assert t1['transport_bytes']==t2['transport_bytes']==65536
        assert len(rows)==2
    with receiver(delay=.002) as (url,rows,_):
        response,trace=post_file(c,url+'/bulk',path,{})
        assert response.status_code==200 and rows[0]['bytes']==65536
    with receiver(response_delay=.4) as (url,rows,_):
        with pytest.raises(requests.ReadTimeout):post_file(c,url+'/bulk',path,{},timeout=(1,.1))
        assert c.last['failure_class']=='Response inactivity or server wait'
        assert c.last['allowance_wait_seconds']>.2


def test_calibration_modes_mbps_and_buffering_detection(tmp_path):
    assert allowance(settings(dict(mode='Manual',manual_mbps=8)))==1_000_000
    assert allowance(settings(dict(sustainable_mbps=8)))==750000
    assert allowance(settings(dict(mode='Background',sustainable_mbps=8)))==187500
    c=Controller();assert c.snapshot()['protection']=='Calibration needed' and allowance(c.value)==0
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(lambda: next_slot(c))
        time.sleep(.1);assert not future.done()
        c.configure(dict(mode='Maximum speed'));future.result(2)
    with c.slot(65536) as trace, payload(tmp_path,65536).open('rb') as source:
        body=Body(source,65536,c,trace,lambda:False)
        with pytest.raises(ValueError,match='Buffering'):body.read()
        assert trace['disk_bytes']==0
    for value in (float('nan'),0,-1,10001):
        with pytest.raises(ValueError):settings(dict(mode='Manual',manual_mbps=value))
    c.configure(dict(mode='Manual',manual_mbps=1),'request_22')
    c.configure(dict(mode='Maximum speed'),'request_21')
    assert c.snapshot()['effective_mbps']==1 and c.revision=='request_22'


def next_slot(c):
    with c.slot(1):return True


def test_one_controller_across_host_and_job_threads(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
    import auto_editions_local as local
    monkeypatch.setattr(local,'HOST_FILE',tmp_path/'isolated-host.dpapi')
    monkeypatch.setattr(local,'TRANSFER_CONTROLLER',None)
    with ThreadPoolExecutor(8) as pool:controllers=list(pool.map(lambda _:local.transfer_controller(),range(24)))
    assert len({id(c) for c in controllers})==1
    row=dict(started_at=0);c=controllers[0]
    c.configure(dict(mode='Manual',manual_mbps=1,download_mbps=.1))
    local.preparation_watchdog(row,'Claimed',c,now=10800)
    # Three hours of intentionally capped source download must not make the
    # following native stage expire immediately. Stuck native work still fails.
    local.preparation_watchdog(row,'Photoshop',c,now=10801)
    with pytest.raises(RuntimeError,match='recovery window'):
        local.preparation_watchdog(row,'Photoshop',c,now=13501)


def test_download_cap_real_receiver_and_connection_reuse(tmp_path):
    # Download-compatible response path reads finite blocks, same semantics as
    # the native source endpoint (the local receiver supplies bytes here).
    path=payload(tmp_path,65536);c=capped()
    c.configure({**c.value,'download_mbps':.524288})
    from urllib.request import urlopen
    with receiver() as (url,_,_):
        start=time.monotonic()
        with c.download_slot(),urlopen(url+'/source',timeout=2) as response:data=b''.join(c.download(response))
        assert time.monotonic()-start>=.9 and data==path.read_bytes()
    # Unlike requests.post per file, thread-owned bulk Session reuses HTTP/1.1.
    c.configure(dict(mode='Maximum speed'))
    with receiver() as (url,rows,connections):
        for _ in range(3):post_file(c,url+'/bulk',path,{})[0].raise_for_status()
        assert len(connections)==1 and len(rows)==3
        for _ in range(3):
            with path.open('rb') as body:requests.post(url+'/bulk',data=body,timeout=2).raise_for_status()
        assert len(connections)==4


def test_stalled_body_and_pause_before_source_dispatch(tmp_path):
    path=payload(tmp_path,8*1024**2);c=Controller();c.configure(dict(mode='Maximum speed'))
    with receiver(stall=True) as (url,_,_):
        with pytest.raises((requests.ConnectionError,requests.ReadTimeout)):
            post_file(c,url+'/bulk',path,{},timeout=(.1,.1))
        assert c.last['failure_class'] in ('Connection/send inactivity','Response inactivity or server wait')
        assert c.last['allowance_wait_seconds']==0 and not c.busy
        assert c.last['request_seconds']<1
    c.configure(dict(mode='Maximum speed',paused=True));entered=threading.Event()
    def download():
        with c.download_slot():entered.set()
    with ThreadPoolExecutor(1) as pool:
        pending=pool.submit(download);assert not entered.wait(.1)
        c.configure(dict(mode='Maximum speed'));pending.result(1)
        assert entered.is_set()


def test_telemetry_rejects_secrets_and_scoped_grant_renewal(monkeypatch):
    from companion_transfer_control import evidence
    c=capped();evidence(c.snapshot())
    with pytest.raises(ValueError):evidence({**c.snapshot(),'token':'secret'})
    value=c.snapshot();value['transfer']={'signed_url':'https://secret'}
    with pytest.raises(ValueError):evidence(value)
    from types import SimpleNamespace
    import auto_editions_onboarding_api as api
    import files_upload_api as files
    request=SimpleNamespace(headers={'x-sports-cave-preparation-host':'synthetic'})
    context=dict(product_gid='fixture',lease_token='owned')
    record=SimpleNamespace(expires_at=time.monotonic()+1,v6_setup=dict(context=context,host_token_hash=hashlib.sha256(b'synthetic').hexdigest()))
    monkeypatch.setattr(files.NATIVE_TRANSFER_MANAGER,'_records',{'fixture':record})
    assert api.renew_transfer(request,context,'fixture') and record.expires_at-time.monotonic()>2600
    with pytest.raises(PermissionError):api.renew_transfer(request,{**context,'lease_token':'other'},'fixture')
    record.expires_at=0;assert api.renew_transfer(request,context,'fixture') is False


def test_handler_correlates_actual_body_and_separates_auth_from_receive(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import Mock
    from starlette.requests import Request
    import auto_editions_setup_api as api
    import auto_editions_technical,auto_editions_visual,product_upload_services,auto_editions_review_thumbnails
    def grant(_):
        time.sleep(.01)
        return dict(context=dict(source={'fixture':True},number=1,total=1),actor_id='fixture')
    monkeypatch.setattr(api,'grant_context',grant)
    monkeypatch.setattr(api,'unpack',lambda *a:({'fixture':True},[]))
    assets=SimpleNamespace(publish_preparation=lambda *a:[],timings={})
    registry=SimpleNamespace(save=lambda *a:'a'*64,connect=lambda:None)
    monkeypatch.setattr(api.runtime,'storage',lambda:assets)
    monkeypatch.setattr(api.runtime,'stores',lambda:(registry,None))
    monkeypatch.setattr(auto_editions_technical,'enabled',lambda:False)
    monkeypatch.setattr(auto_editions_visual,'enabled',lambda:False)
    monkeypatch.setattr(product_upload_services,'enabled',lambda:False)
    monkeypatch.setattr(auto_editions_review_thumbnails,'schedule_prepared',lambda *a:None)
    async def receive():
        await asyncio.sleep(.02)
        return dict(type='http.request',body=b'fixture-body',more_body=False)
    correlation='c'*32;request_id='d'*32
    request=Request(dict(type='http',method='POST',scheme='http',path='/api/auto-editions/package',query_string=b'',headers=[(b'x-sc-transfer-id',correlation.encode()),(b'x-sc-request-id',request_id.encode())]),receive)
    response=asyncio.run(api.package(request));assert response.status_code==200,response.body
    timings=json.loads(response.body)['timings']
    assert response.headers['X-SC-Transfer-ID']==correlation and response.headers['X-SC-Received-Bytes']=='12'
    assert timings['correlation_id']==correlation and timings['request_id']==request_id
    assert timings['authentication_context_seconds']>=.009 and timings['body_receive_seconds']>=.019
    assert timings['handler_total_seconds']>=timings['authentication_context_seconds']+timings['body_receive_seconds']
