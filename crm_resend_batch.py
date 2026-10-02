"""Documented Resend batch API, bounded account-header pacing, safe receipts."""
import threading
import time
import uuid
import math
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from crm_resend import ProviderUnavailable

BATCH_SIZE=100


def seconds(value):
    try:
        number=float(value)
        return max(0,number) if math.isfinite(number) else 0
    except (TypeError,ValueError):
        try:return max(0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (TypeError,ValueError,OverflowError):return 0


class BatchError(ProviderUnavailable):
    def __init__(self,status=0,retry_after=0,category='submission_uncertain'):
        self.status=status;self.retry_after=retry_after;self.category=category
        super().__init__(category)


class Gate:
    """One request/sec until headers establish capacity; at most two in flight."""
    def __init__(self):
        self.lock=threading.Lock();self.next=0.;self.interval=1.;self.concurrency=1
    def wait(self):
        with self.lock:
            delay=max(0,self.next-time.monotonic())
            if delay>15:raise BatchError(429,delay)
            if delay:time.sleep(delay)
            self.next=time.monotonic()+self.interval
    def observe(self,headers,status):
        with self.lock:
            try:
                limit=float(headers['ratelimit-limit']);remaining=float(headers['ratelimit-remaining'])
                reset=seconds(headers.get('ratelimit-reset'))
                if math.isfinite(limit) and math.isfinite(remaining) and limit>0:
                    self.interval=max(.1,(reset or 1)/limit)
                    self.concurrency=2 if limit>=2 and remaining>=2 else 1
                if remaining<=0:self.next=max(self.next,time.monotonic()+reset)
            except (KeyError,TypeError,ValueError):pass
            retry=seconds(headers.get('retry-after'))
            if status==429:self.next=max(self.next,time.monotonic()+max(retry,1))
            return retry


class BatchTransport:
    def __init__(self,provider):
        self.provider=provider;self.gate=Gate();self.api_calls=0
    @property
    def concurrency(self):return self.gate.concurrency
    def request(self,method,path,**kwargs):
        self.gate.wait()
        with self.gate.lock:self.api_calls+=1
        try:
            response=self.provider.session.request(method,'https://api.resend.com'+path,
                headers={'Authorization':'Bearer '+self.provider.config.api_key,**kwargs.pop('headers',{})},
                timeout=15,allow_redirects=False,**kwargs)
        except Exception:raise BatchError() from None
        retry=self.gate.observe(response.headers,response.status_code)
        if not 200<=response.status_code<300:
            raise BatchError(response.status_code,retry,'provider_rejected' if response.status_code in (400,401,403,404,405,422) else 'submission_uncertain')
        try:
            remaining=response.headers.get('ratelimit-remaining')
            try:remaining=max(0,int(remaining))
            except (TypeError,ValueError):remaining=None
            return response.json(),response.status_code,retry,remaining
        except Exception:raise BatchError() from None
    def suppressed_hashes(self):
        """Complete provider stop-state once per dispatch, not two calls per email.

        No stale cache for consent. Pagination is bounded and fails closed.
        Only hashes survive this read; provider customer profiles are discarded.
        """
        from crm_logic import recipient_hash
        blocked=set()
        for path in ('/suppressions','/contacts'):
            after=None;seen=set()
            for _ in range(100):
                params={'limit':100}
                if after:params['after']=after
                data,*_=self.request('GET',path,params=params)
                if not isinstance(data,dict) or type(data.get('has_more')) is not bool or not isinstance(data.get('data'),list):raise BatchError(category='provider_stop_state_unavailable')
                rows=data['data']
                for row in rows:
                    if not isinstance(row,dict) or not row.get('email') or (path=='/contacts' and type(row.get('unsubscribed')) is not bool):raise BatchError(category='provider_stop_state_unavailable')
                    if path=='/suppressions' or row['unsubscribed']:blocked.add(recipient_hash(row['email']))
                if not data['has_more']:break
                cursor=rows[-1].get('id') if rows else None
                if not cursor or cursor in seen:raise BatchError(category='provider_stop_state_unavailable')
                seen.add(cursor);after=cursor
            else:raise BatchError(category='provider_stop_state_unavailable')
        return blocked
    def send(self,payloads,key):
        self.provider.config.require_send(False)
        if not 1<=len(payloads)<=BATCH_SIZE:raise ValueError('Invalid batch size.')
        data,status,retry,remaining=self.request('POST','/emails/batch',json=payloads,
            headers={'Idempotency-Key':key,'x-batch-validation':'strict'})
        # Strict mode gives ordered receipts for the complete request. Never
        # guess a partial index mapping or retry a subset after unknown acceptance.
        try:
            if data.get('errors') or len(data['data'])!=len(payloads):raise ValueError()
            ids=[str(uuid.UUID(row['id'])) for row in data['data']]
            if len(set(ids))!=len(ids):raise ValueError()
        except Exception:raise BatchError() from None
        return {'ids':ids,'status':status,'retry_after':retry,'remaining':remaining}
