"""Companion-owned streaming transfers. Payload accounting, never wire capacity.

One process-wide upload slot and a small shared token bucket. No worker/queue
pause semantics, provider publication changes, or resumable protocol here.
"""
from contextlib import contextmanager,nullcontext
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

CAPABILITY = 3
DEFAULTS = dict(mode='Balanced', manual_mbps=None, sustainable_mbps=None,
                headroom_percent=25, background_percent=25, download_mbps=None,
                paused=False)
MODES = ('Balanced', 'Background', 'Maximum speed', 'Manual')


def settings(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULTS):
        raise ValueError('Choose bounded companion transfer settings.')
    out = {**DEFAULTS, **value}
    if out['mode'] not in MODES or type(out['paused']) is not bool:
        raise ValueError('Invalid transfer mode or pause state.')
    for key in ('manual_mbps', 'sustainable_mbps', 'download_mbps'):
        n = out[key]
        if n is not None and (type(n) not in (int, float) or not math.isfinite(n) or not .01 <= n <= 10000):
            raise ValueError('Upload/download rates must be 0.01–10000 Mbps.')
    for key in ('headroom_percent', 'background_percent'):
        if type(out[key]) not in (int, float) or not 5 <= out[key] <= 95:
            raise ValueError('Headroom/background percentages must be 5–95.')
    if out['mode'] == 'Manual' and out['manual_mbps'] is None:
        raise ValueError('Manual mode needs an upload cap in Mbps.')
    return out


def allowance(value):
    if value['mode'] == 'Maximum speed': return None
    if value['mode'] == 'Manual': return value['manual_mbps'] * 1_000_000 / 8
    rate = value['sustainable_mbps']
    if rate is None: return 0  # Fail closed: never advertise unprotected Balanced.
    rate *= 1 - value['headroom_percent'] / 100
    if value['mode'] == 'Background': rate *= value['background_percent'] / 100
    return rate * 1_000_000 / 8


def burst_allowance(rate):
    # A 16 KiB bucket discards credit when Windows wakes a short wait late.
    # Cover at most 32 ms at higher rates, capped at 256 KiB. Reader chunks
    # remain 16 KiB; low-rate behaviour retains its existing 1–16 KiB bound.
    # This is a burst allowance, not an increase in the aggregate rate.
    return min(262144, max(1024, min(16384, rate*.1), rate*.032))


class Controller:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.cv = threading.Condition()
        from companion_bandwidth import Policy
        self.policy = Policy()
        self.value = dict(DEFAULTS)
        self.revision = 'local'
        self.epoch = 0
        self.busy = False
        self.download_busy = False
        self.session = None
        self.active = None
        self.last = None
        self.tokens = 0.
        self.tick = time.monotonic()
        self.download_tokens = 0.
        self.download_tick = self.tick
        if self.path and self.path.exists():
            if self.path.stat().st_size>16384:raise ValueError('Bounded transfer settings required.')
            saved = json.loads(self.path.read_text())
            self.policy = Policy(saved.get('calibration'))
            self.value = settings(saved['settings']); self.revision = saved['revision']

    def configure(self, value, revision='local'):
        import re
        value = settings(value)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', str(revision)): raise ValueError('Invalid settings revision.')
        with self.cv:
            if self.revision.startswith('request_') and str(revision).startswith('request_'):
                try:
                    if int(revision[8:]) < int(self.revision[8:]):return
                except ValueError:raise ValueError('Invalid ordered settings revision.')
            if value == self.value and revision == self.revision: return
            reset=value['sustainable_mbps']!=self.value['sustainable_mbps']
            calibration=self.policy.saved()
            if reset:calibration={**calibration,'factor':1.}
            self._persist(value,revision,calibration)
            if reset:self.policy.factor=1.;self.policy.loaded=[]
            self.value = value; self.revision = revision; self.epoch += 1
            self.tokens = self.download_tokens = 0.
            self.tick = self.download_tick = time.monotonic()
            self.cv.notify_all()

    def _persist(self,value=None,revision=None,calibration=None):
        if not self.path:return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        from companion_atomic import atomic_json
        atomic_json(self.path,dict(settings=value or self.value,revision=revision or self.revision,
                                  calibration=self.policy.saved() if calibration is None else calibration))

    def rate(self):
        rate=self.policy.allowance(self.value)
        # Calibration expiry must block the next transfer, not deadlock an
        # already admitted finite body. An explicit settings change still wins.
        if rate==0 and self.active and self.active.get('_admitted_epoch')==self.epoch:
            return self.active.get('_admitted_rate',0)
        return rate

    def observe_transfer(self,trace):
        with self.cv:
            if self.policy.observe_transfer(trace):
                try:self._persist()
                except OSError:pass
                self.cv.notify_all()

    def observe_control(self,seconds,*,loaded=None):
        with self.cv:
            transferring=bool(self.active and self.active.get('state') in ('Uploading','Resuming') and self.active.get('transport_bytes',0)>0)
            if loaded is not None:transferring=loaded
            # Do not train an idle baseline during server verification/downloads.
            if not transferring and (self.active or self.download_busy):return
            if self.policy.observe_latency(seconds,loaded=transferring):
                self.tokens=0.;self.tick=time.monotonic()
                try:self._persist()
                except OSError:pass
                self.cv.notify_all()

    def snapshot(self):
        with self.cv:
            rate = self.rate()
            progress = dict(self.active or self.last or {})
            if self.active:
                elapsed = progress.get('transfer_seconds',0) if progress.get('resumable') else max(0,time.monotonic() - progress['started_monotonic']-progress.get('body_first_handoff_seconds',0))
                # Average payload handoff rate; deliberately includes throttle waits.
                speed = progress['transport_bytes'] / max(elapsed, .001)
                progress['payload_bytes_per_second'] = round(speed, 1) if elapsed >= 2 and progress.get('state') in ('Uploading','Resuming') else None
                eta_speed=min(speed,rate) if rate is not None else speed
                progress['eta_seconds'] = round((progress['total_bytes']-progress.get('progress_bytes',progress['transport_bytes']))/eta_speed, 1) if elapsed >= 3 and progress['transport_bytes'] >= 262144 and eta_speed > 0 and progress['state'] in ('Uploading','Resuming') else None
            progress.pop('started_monotonic', None)
            progress={k:v for k,v in progress.items() if not k.startswith('_') and k!='capacity_eligible'}
            pause='Running'
            if self.value['paused']:
                if self.active and self.active.get('resumable') and self.active.get('state') not in ('Uploaded, verifying','Cloud Ready'):
                    pause='Paused at chunk boundary' if self.active['state']=='Paused' else 'Pausing at chunk boundary'
                elif self.download_busy or self.active and not self.active.get('resumable'):pause='Pause after current transfer'
                else:pause='Transfers paused'
            return dict(capability=CAPABILITY, revision=self.revision, settings=dict(self.value),
                        active_upload=self.active is not None,active_download=self.download_busy,
                        calibration=self.policy.snapshot(self.value),
                        effective_mbps=None if rate is None else rate*8/1_000_000,
                        protection='Calibration needed' if rate == 0 else 'Maximum speed (uncapped)' if rate is None else 'Limited',
                        pause_state=pause,
                        transfer=progress)

    @contextmanager
    def slot(self, total, correlation=None, stopped=lambda: False, *, resumable=False, verification_only=False):
        waits=dict(slot_wait_seconds=0.,pause_wait_seconds=0.,calibration_wait_seconds=0.)
        with self.cv:
            if stopped():raise InterruptedError('Transfer stopped before dispatch.')
            while self.busy or not verification_only and (self.value['paused'] or self.rate() == 0):
                if stopped(): raise InterruptedError('Transfer stopped before dispatch.')
                waiting='slot_wait_seconds' if self.busy else 'pause_wait_seconds' if self.value['paused'] else 'calibration_wait_seconds'
                phase=time.monotonic();self.cv.wait(.1);waits[waiting]+=time.monotonic()-phase
            self.busy = True
            trace = dict(correlation_id=correlation or uuid.uuid4().hex, total_bytes=total,
                         disk_bytes=0, transport_bytes=0, server_received_bytes=None, disk_read_seconds=0.,
                         request_id=uuid.uuid4().hex, **waits, allowance_wait_seconds=0.,
                         resumable=resumable,state='Uploading', started_monotonic=time.monotonic(),
                         connection_seconds=None, connection_observability='Not exposed by requests/urllib3')
            trace['_admitted_rate']=self.rate();trace['_admitted_epoch']=self.epoch
            trace['capacity_eligible']=self.rate() is None
            trace['_capacity_epoch']=self.epoch
            self.active = trace
        try: yield trace
        finally:
            with self.cv:
                self.last = dict(trace); self.active = None; self.busy = False
                self.cv.notify_all()

    def chunk_boundary(self,trace,stopped=lambda:False):
        with self.cv:
            waiting=False
            while self.value['paused'] or self.rate()==0:
                trace['state']='Paused' if self.value['paused'] else 'Calibration needed';waiting=True
                if stopped():raise InterruptedError('Resumable transfer stopped at a confirmed boundary.')
                reason='pause_wait_seconds' if self.value['paused'] else 'calibration_wait_seconds'
                start=time.monotonic();self.cv.wait(.1);trace[reason]+=time.monotonic()-start
            if stopped():raise InterruptedError('Resumable transfer stopped at a confirmed boundary.')
            trace['state']='Resuming' if waiting else 'Uploading'
            return waiting

    def take(self, maximum, trace=None, *, download=False, stopped=lambda: False):
        waited = 0.
        with self.cv:
            while True:
                if stopped(): raise InterruptedError('Transfer stopped.')
                rate = self.value['download_mbps']*1_000_000/8 if download and self.value['download_mbps'] else None if download else self.rate()
                if rate is None: n = min(maximum, 16384); break
                now = time.monotonic()
                token_key, tick_key = ('download_tokens', 'download_tick') if download else ('tokens', 'tick')
                burst = burst_allowance(rate)
                tokens = min(burst, getattr(self, token_key) + (now-getattr(self, tick_key))*rate)
                setattr(self, token_key, tokens); setattr(self, tick_key, now)
                n = min(maximum, 16384, max(1024, int(rate*.05)))
                if rate and tokens >= n:
                    setattr(self, token_key, tokens-n); break
                start=time.monotonic()
                self.cv.wait(min(.1, max(.001, (n-tokens)/rate)) if rate else .1)
                waited+=time.monotonic()-start
            if trace is not None: trace['allowance_wait_seconds'] += waited
            return n

    @contextmanager
    def download_slot(self, stopped=lambda: False):
        # Reserve before opening the HTTP request, so pause prevents dispatch.
        with self.cv:
            if stopped():raise InterruptedError('Download stopped before dispatch.')
            while self.value['paused'] or self.download_busy:
                if stopped():raise InterruptedError('Download stopped before dispatch.')
                self.cv.wait(.1)
            self.download_busy=True
        try:yield
        finally:
            with self.cv:self.download_busy=False;self.cv.notify_all()

    def download(self, response, size=16384):
        # Allowance before read: never buffer a complete PSD to apply a cap.
        while True:
            block = response.read(self.take(size, download=True))
            if not block: return
            yield block


class Body:
    """Finite streaming body. Reject read-all adapters rather than bypass limits."""
    def __init__(self, source, total, controller, trace, stopped, progress=None, progress_offset=0):
        self.source=source; self.total=total; self.controller=controller; self.trace=trace; self.stopped=stopped
        self.read_count=0;self.progress=progress;self.progress_offset=progress_offset
        self.started=time.monotonic();self.prior_seconds=(progress or {}).get('transfer_seconds',0)
    def __len__(self): return self.total
    def __iter__(self): return self
    def __next__(self):
        value=self.read(16384)
        if not value: raise StopIteration
        return value
    def read(self, size=-1):
        t=self.trace
        remaining=self.total-self.read_count
        if remaining <= 0: return b''
        if size is None or size < 0: raise ValueError('Buffering upload adapters are unsupported.')
        if size == 0: return b''
        n=self.controller.take(min(size, remaining), t, stopped=self.stopped)
        disk_started=time.monotonic()
        block=self.source.read(n)
        t['disk_read_seconds']+=time.monotonic()-disk_started
        if not block: raise OSError('Upload source ended before its verified size.')
        now=time.monotonic()-t['started_monotonic']
        t.setdefault('body_first_handoff_seconds', now)
        self.read_count+=len(block)
        t['disk_bytes']+=len(block); t['transport_bytes']+=len(block)
        if self.progress is not None:
            self.progress['transport_bytes']+=len(block);self.progress['disk_bytes']+=len(block)
            self.progress['disk_read_seconds']+=time.monotonic()-disk_started
            self.progress['progress_bytes']=self.progress_offset+self.read_count
            self.progress['transfer_seconds']=self.prior_seconds+time.monotonic()-self.started
        t['body_last_handoff_seconds']=now
        if self.read_count==self.total:
            t['state']='Waiting for server verification'
            if self.progress is not None:self.progress['state']='Waiting for durable chunk acknowledgement'
        return block


def post_file(controller, url, path, headers, *, correlation=None, stopped=lambda: False, timeout=(20, 600), on_trace=lambda trace: None, offset=0, length=None, _parent=None):
    import requests
    path=Path(path)
    total=path.stat().st_size-offset if length is None else length
    if type(offset) is not int or type(total) is not int or offset<0 or total<=0 or offset+total>path.stat().st_size:
        raise ValueError('Invalid finite upload slice.')
    if _parent is not None and controller.active is not _parent:raise ValueError('Chunk requires the aggregate slot owner.')
    child=dict(total_bytes=total,disk_bytes=0,transport_bytes=0,server_received_bytes=None,disk_read_seconds=0.,
        allowance_wait_seconds=0.,correlation_id=correlation or uuid.uuid4().hex,request_id=uuid.uuid4().hex,started_monotonic=time.monotonic())
    scope=nullcontext(child) if _parent is not None else controller.slot(total,correlation,stopped)
    with scope as trace:
        with controller.cv:
            trace.setdefault('capacity_eligible',controller.rate() is None)
            trace.setdefault('_capacity_epoch',controller.epoch)
        # Only the single slot owner touches this Session, including when a
        # later job runs on another thread. Control requests use another client.
        if controller.session is None:controller.session=requests.Session()
        session=controller.session
        if type(session.get_adapter(url)) is not requests.adapters.HTTPAdapter:
            raise ValueError('Unverified buffering upload adapter.')
        started=time.monotonic()
        try:
            # Retain the previous bounded disk read-ahead. Transport reads are
            # still <=16 KiB; the full request is never buffered.
            with path.open('rb', buffering=1024*1024) as source:
                source.seek(offset)
                body=Body(source,trace['total_bytes'],controller,trace,stopped,_parent,offset)
                request=session.prepare_request(requests.Request('POST', url, data=body,
                    headers={**headers, 'Content-Length':str(trace['total_bytes']), 'X-SC-Transfer-ID':trace['correlation_id'], 'X-SC-Request-ID':trace['request_id']}))
                if request.body is not body or request.headers.get('Transfer-Encoding'):
                    raise ValueError('Upload body was buffered or transformed.')
                trace['request_preparation_seconds']=time.monotonic()-started
                environment=session.merge_environment_settings(url, {}, False, None, None)
                response=session.send(request, allow_redirects=False, timeout=timeout, **environment)
            trace['request_seconds']=time.monotonic()-started
            trace['response_after_last_handoff_seconds']=max(0, trace['request_seconds']-trace.get('body_last_handoff_seconds',trace['request_seconds']))
            # A server echo is proof of receipt, not an assumption based on reads.
            if response.headers.get('X-SC-Transfer-ID') == trace['correlation_id']:
                count=response.headers.get('X-SC-Received-Bytes','')
                if count.isdigit() and int(count)<=trace['total_bytes']: trace['server_received_bytes']=int(count)
            trace['state']='Response received'
            trace['capacity_eligible'] &= type(response.status_code) is int and 200<=response.status_code<300 and trace['_capacity_epoch']==controller.epoch
            for header,field in (('X-SC-Handler-Seconds','server_handler_seconds'),('X-SC-Body-Receive-Seconds','server_body_receive_seconds'),('X-SC-Body-Wait-Seconds','server_body_wait_seconds'),('X-SC-Durable-Seconds','server_durable_seconds')):
                value=response.headers.get(header,'')
                if isinstance(value,str) and __import__('re').fullmatch(r'[0-9]{1,6}(\.[0-9]{1,6})?',value):trace[field]=float(value)
            return response, trace
        except Exception as error:
            trace['request_seconds']=time.monotonic()-started
            trace['failure_class']='Response inactivity or server wait' if isinstance(error,requests.ReadTimeout) else 'Connection/send inactivity' if isinstance(error,(requests.ConnectionError,requests.ConnectTimeout)) else type(error).__name__
            trace['state']='Transfer failed'
            trace['capacity_eligible']=False
            raise
        finally:
            trace['unattributed_transport_response_seconds']=max(0,trace.get('request_seconds',0)-trace.get('request_preparation_seconds',0)-trace['allowance_wait_seconds']-trace['disk_read_seconds'])
            if _parent is not None:_parent['allowance_wait_seconds']+=trace['allowance_wait_seconds']
            controller.observe_transfer(trace)
            trace.pop('capacity_eligible',None);trace.pop('_capacity_epoch',None)
            # Diagnostics cannot turn a verified upload into a failed job.
            try:on_trace(trace)
            except OSError:pass
