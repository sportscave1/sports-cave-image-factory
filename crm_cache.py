"""Bounded transient Shopify display cache; no disk/database or import-time I/O."""
from collections import OrderedDict
from copy import deepcopy
import threading
import time


class DisplayCache:
    def __init__(self, limit=256, byte_limit=12*1024*1024, clock=time.monotonic):
        self.limit,self.byte_limit,self.clock=limit,byte_limit,clock
        self.rows=OrderedDict();self.bytes=0;self.lock=threading.RLock();self.version=None

    def invalidate(self, version=None):
        with self.lock:
            if version is not None and version==self.version:return
            self.rows.clear();self.bytes=0;self.version=version

    def get(self,key):
        with self.lock:
            row=self.rows.pop(key,None)
            if row is None:return None
            if row[0]<=self.clock():self.bytes-=row[2];return None
            self.rows[key]=row
            return deepcopy(row[1])

    def put(self,key,value,ttl):
        import json
        size=len(json.dumps(value,default=str).encode())
        with self.lock:
            old=self.rows.pop(key,None)
            if old:self.bytes-=old[2]
            if size>self.byte_limit:return value
            self.rows[key]=(self.clock()+ttl,deepcopy(value),size);self.bytes+=size
            while self.bytes>self.byte_limit or len(self.rows)>self.limit:
                _,old=self.rows.popitem(last=False);self.bytes-=old[2]
        return value


CACHE=DisplayCache()
