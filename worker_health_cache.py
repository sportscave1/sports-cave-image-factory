"""Two-second, bounded, single-flight read cache. Never authorises a mutation."""
from collections import OrderedDict
from copy import deepcopy
from threading import Condition,Lock
import time

class Snapshot:
    def __init__(self,ttl=2,clock=time.monotonic):
        self.ttl=ttl;self.clock=clock;self.condition=Condition();self.value=None
        self.expires=0;self.loading=False;self.generation=0

    def invalidate(self):
        with self.condition:
            self.generation+=1;self.value=None;self.expires=0;self.condition.notify_all()

    def read(self,loader):
        with self.condition:
            while self.loading:self.condition.wait()
            if self.value is not None and self.clock()<self.expires:
                result=deepcopy(self.value)
                result['cost']={**result['cost'],'snapshot_queries':result['cost']['queries'],'queries':0,'cached':True}
                return result
            self.loading=True;generation=self.generation
        try:
            value=loader()
            with self.condition:
                if generation==self.generation:
                    self.value=deepcopy(value);self.expires=self.clock()+self.ttl
            return value
        finally:
            with self.condition:self.loading=False;self.condition.notify_all()

_lock=Lock();_slots=OrderedDict()
def slot(connect):
    with _lock:
        if connect not in _slots:
            if len(_slots)>=8:_slots.popitem(last=False)
            _slots[connect]=Snapshot()
        _slots.move_to_end(connect)
        return _slots[connect]

def snapshot(service):return slot(service.connect).read(service.snapshot)
def invalidate(connect):slot(connect).invalidate()
