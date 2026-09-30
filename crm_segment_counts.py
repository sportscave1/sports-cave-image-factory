"""Bounded, server-process aggregate display cache. Never used to authorize sends."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import logging
import threading
import time
from crm_campaign_segments import count_snapshot

TTL=60
REVISION_INTERVAL=10
FAILURE_BACKOFF=60

class SegmentCounts:
    def __init__(self,clock=time.monotonic,executor=None,loader=count_snapshot):
        self.clock=clock;self.executor=executor or ThreadPoolExecutor(max_workers=2,thread_name_prefix='crm-counts')
        self.loader=loader;self.lock=threading.Lock();self.rows={}

    def display(self,shop,store,hours=16):
        # Same store + server-side connection factory. No recipient/customer data
        # survives the background job; only aggregate numbers are cached.
        key=(shop.namespace,store.connect)
        with self.lock:
            if key not in self.rows:
                if len(self.rows)>=32:
                    free=[k for k,v in self.rows.items() if not v['pending']]
                    if not free:return {'counts':{},'pending':False,'error':True}
                    del self.rows[min(free,key=lambda k:self.rows[k]['touched'])]
                self.rows[key]={'counts':{},'snapshot':{},'at':None,'revision':None,'next_check':0,'pending':False,'error':False}
            row=self.rows[key];row['touched']=self.clock()
            if not row['pending'] and self.clock()>=row['next_check']:
                row['pending']=True
                try:self.executor.submit(self._refresh,key,shop,store,hours)
                except Exception:
                    row.update(pending=False,error=True,next_check=self.clock()+FAILURE_BACKOFF)
            return deepcopy({k:row[k] for k in ('counts','snapshot','revision','pending','error')})

    def refresh(self,shop,store):
        store.invalidate()
        with self.lock:
            row=self.rows.get((shop.namespace,store.connect))
            if row:row.update(at=None,next_check=0)

    def _refresh(self,key,shop,store,hours):
        try:
            revision=store.state('cache_version')
            with self.lock:
                row=self.rows[key]
                needed=row['at'] is None or self.clock()-row['at']>=TTL or row['revision']!=revision
            if needed:
                result=self.loader(shop,store,hours)
                counts={m:r['subscribed'] for m,r in result.items()}
                # An opt-out during calculation must not make stale counts fresh.
                if store.state('cache_version')!=revision:
                    with self.lock:self.rows[key].update(next_check=self.clock())
                    return # Ordinary update race: retry next fragment, no outage backoff.
                with self.lock:self.rows[key].update(counts=counts,snapshot=result,at=self.clock(),revision=revision)
            with self.lock:self.rows[key].update(error=False,next_check=self.clock()+REVISION_INTERVAL)
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_segment_count_refresh_failed type=%s',type(exc).__name__)
            with self.lock:self.rows[key].update(error=True,next_check=self.clock()+FAILURE_BACKOFF)
        finally:
            with self.lock:self.rows[key]['pending']=False

COUNTS=SegmentCounts()
