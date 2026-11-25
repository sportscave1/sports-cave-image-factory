"""100 uncached reads per mode: measured CPU + explicitly modeled IMAP delays."""
from pathlib import Path
import json
import sys
import time
from support_email_provider import ImapProvider
from tests.test_support_email import CONFIG, header
from tests.test_support_email_v2 import WireImap
from test_email_phase2_speed import ManualTimer


def summary(values):
    ordered = sorted(values)
    return dict(n=len(values),p50_ms=ordered[len(ordered)//2],
                p95_ms=ordered[min(len(ordered)-1,int(len(ordered)*.95))],
                max_ms=max(ordered))


def run(reuse):
    clock = [0.0]
    wires = []
    def charge(ms):clock[0] += ms/1000
    class Wire(WireImap):
        def login(self,*args):
            charge(230)
            return super().login(*args)
        def select(self,*args,**kwargs):
            charge(210)
            return super().select(*args,**kwargs)
        def uid(self,*args,**kwargs):
            charge(210)
            return super().uid(*args,**kwargs)
        def logout(self):
            charge(210)
            return super().logout()
    def factory(*args,**kwargs):
        charge(700)
        wire = Wire(); wires.append(wire)
        return wire
    p = ImapProvider(CONFIG,connection_factory=factory,reuse_reads=reuse)
    if reuse:
        p._read_slot.clock=lambda:clock[0]
        p._read_slot.timer_factory=ManualTimer
    cpu, modeled = [], []
    try:
        for _ in range(100):
            before_clock, before_cpu = clock[0], time.perf_counter()
            result=p.read_message(header())
            assert 'Hello' in result['text']
            cpu.append((time.perf_counter()-before_cpu)*1000)
            modeled.append((clock[0]-before_clock)*1000)
    finally:
        p.close_read_connections()
    return dict(cpu_ms=summary(cpu),modeled_network_ms=summary(modeled),
                connections=len(wires),readonly_selects=sum(sum(c[0]=='select' and c[-1] is True for c in w.calls) for w in wires))


if __name__=='__main__':
    result=dict(synthetic_only=True,network_model_ms=dict(connect=700,login=230,select=210,command=210,logout=210),
                before=run(False),after=run(True))
    print(json.dumps(result,indent=2))
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(result,indent=2))
