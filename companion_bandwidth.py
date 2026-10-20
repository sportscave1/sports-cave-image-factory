"""Conservative payload calibration and latency headroom. No network probes.

Capped observations never establish capacity. Control latency can reduce a
calibrated allowance, but cannot prove a new capacity or attribute WAN congestion.
"""
import math
import statistics
import time

TTL=86400


class Policy:
    def __init__(self,saved=None):
        self.samples=[];self.estimate=None;self.measured_at=0.;self.factor=1.
        self.idle=[];self.loaded=[];self.last_change=0.;self.reason='Calibration needed'
        if isinstance(saved,dict):
            samples=saved.get('samples',[])
            if (isinstance(samples,list) and len(samples)<=7 and
                all(type(x) in (int,float) and math.isfinite(x) and .01<=x<=10000 for x in samples)):
                rate=saved.get('estimate');stamp=saved.get('measured_at',0)
                if type(rate) in (int,float) and math.isfinite(rate) and .01<=rate<=10000 and type(stamp) in (int,float) and math.isfinite(stamp):
                    self.samples=samples;self.estimate=rate;self.measured_at=stamp
            factor=saved.get('factor',1)
            if type(factor) in (int,float) and math.isfinite(factor) and .25<=factor<=1:self.factor=factor

    def saved(self):
        return dict(samples=self.samples,estimate=self.estimate,measured_at=self.measured_at,factor=self.factor)

    def rate(self,value,now=None):
        if value['sustainable_mbps'] is not None:return value['sustainable_mbps']
        now=time.time() if now is None else now
        return self.estimate if self.estimate and len(self.samples)>=3 and 0<=now-self.measured_at<TTL else None

    def allowance(self,value):
        if value['mode']=='Maximum speed':return None
        if value['mode']=='Manual':return value['manual_mbps']*1_000_000/8
        rate=self.rate(value)
        if rate is None:return 0
        rate*=1-value['headroom_percent']/100
        if value['mode']=='Background':rate*=value['background_percent']/100
        return rate*self.factor*1_000_000/8

    def observe_transfer(self,t,now=None):
        # Both local streaming/backpressure and server body reception must span
        # real time. An ingress-buffered body, small request, capped transfer,
        # retry/failure, disk delay or changed settings cannot calibrate capacity.
        elapsed=t.get('body_last_handoff_seconds',0)-t.get('body_first_handoff_seconds',0)
        server=t.get('server_body_receive_seconds',0);count=t.get('transport_bytes',0)
        if (t.get('capacity_eligible') is not True or t.get('server_received_bytes')!=count
            or count<2*1024**2 or elapsed<2 or server<2 or not .5<=server/elapsed<=2
            or t.get('allowance_wait_seconds',0)>.01 or t.get('disk_read_seconds',0)>.02*elapsed):return False
        rate=min((count-16384)/elapsed,count/server)*8/1_000_000
        if not .01<=rate<=10000:return False
        now=time.time() if now is None else now
        if not 0<=now-self.measured_at<TTL:self.samples=[];self.estimate=None
        self.samples=(self.samples+[rate])[-7:]
        self.measured_at=now
        if len(self.samples)>=3:
            target=statistics.median(self.samples[-3:])
            if self.estimate is None:self.estimate=target
            elif target<self.estimate*.9:self.estimate=max(target,self.estimate*.8)
            elif target>self.estimate*1.1:self.estimate=min(target,self.estimate*1.05)
            self.reason='Transfer calibration'
        return True

    def observe_latency(self,seconds,*,loaded,now=None):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=20:return False
        now=time.monotonic() if now is None else now
        if not loaded:
            self.idle=(self.idle+[seconds])[-7:];self.loaded=[];return False
        if len(self.idle)<3:return False
        self.loaded=(self.loaded+[seconds])[-5:]
        baseline=statistics.median(self.idle)
        bad=len(self.loaded)>=3 and all(x>max(baseline*2.5,baseline+.1) for x in self.loaded[-3:])
        good=len(self.loaded)>=5 and all(x<=max(baseline*1.5,baseline+.04) for x in self.loaded)
        if bad and now-self.last_change>=30 and self.factor>.25:
            self.factor=max(.25,self.factor*.8);self.last_change=now;self.loaded=[]
            self.reason='Sustained control latency';return True
        if good and now-self.last_change>=60 and self.factor<1:
            self.factor=min(1,self.factor*1.05);self.last_change=now;self.loaded=[]
            self.reason='Gradual headroom recovery';return True
        return False

    def snapshot(self,value):
        rate=self.rate(value)
        return dict(state='Calibrated' if rate else 'Calibration needed',
            source='Operator supplied' if value['sustainable_mbps'] is not None else 'Transfer observations' if rate else 'Unmeasured',
            sustainable_mbps=rate,sample_count=len(self.samples),adaptive_percent=round(self.factor*100,2),
            idle_rtt_ms=round(statistics.median(self.idle)*1000,1) if len(self.idle)>=3 else None,
            loaded_rtt_ms=round(statistics.median(self.loaded)*1000,1) if self.loaded else None,
            reason=self.reason)
