"""Bounded transient WebP delivery cache; Dropbox remains the durable source."""
from collections import OrderedDict
import hashlib
import threading
import time


class ImageCache:
    def __init__(self,byte_limit=8*1024*1024,limit=64,clock=time.monotonic):
        self.byte_limit,self.limit,self.clock=byte_limit,limit,clock
        self.rows=OrderedDict();self.bytes=0;self.lock=threading.Lock()
    def get(self,key):
        with self.lock:
            row=self.rows.pop(key,None)
            if row is None:return None
            if row[0]<=self.clock():self.bytes-=len(row[1]);return None
            self.rows[key]=row;return row[1]
    def put(self,key,data):
        if len(data)>self.byte_limit:return data
        with self.lock:
            previous=self.rows.pop(key,None)
            if previous:self.bytes-=len(previous[1])
            self.rows[key]=(self.clock()+900,data);self.bytes+=len(data)
            while self.bytes>self.byte_limit or len(self.rows)>self.limit:
                _,row=self.rows.popitem(last=False);self.bytes-=len(row[1])
        return data


CACHE=ImageCache()


def display_bytes(ref,storage):
    if not 0<ref['size']<=1024*1024:raise ValueError('Invalid display size.')
    key=(ref['id'],ref['rev'],ref['sha256'])
    cached=CACHE.get(key)
    if cached is not None:return cached
    stream=storage.open(ref,0,ref['size']-1)
    try:
        data=bytearray()
        for chunk in stream.iter_chunks():
            data.extend(chunk)
            if len(data)>ref['size']:raise ValueError('Display media exceeded its recorded size.')
    finally:stream.close()
    data=bytes(data)
    if len(data)!=ref['size'] or hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('Display media bytes changed.')
    return CACHE.put(key,data)
