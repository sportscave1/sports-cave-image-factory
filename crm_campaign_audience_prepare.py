"""Session-owned, read-only eligibility preparation, independent of email content."""
from concurrent.futures import Future
from copy import copy, deepcopy
import hashlib
import json
import logging
import threading
import time

from crm_campaign_send import final_audience

LOG = logging.getLogger(__name__)
TTL_SECONDS = 60
_SLOTS = threading.BoundedSemaphore(2)


def measured_reads(shop,store):
    """Count logical Graph operations and database reads without logging inputs."""
    from crm_shopify import Shopify
    from crm_store import Store
    counts={'shopify_graphql_requests':0,'database_query_count':0,'provider_request_count':0}
    lock=threading.Lock()
    def instrument(target,method,key):
        target=copy(target)
        original=getattr(target,method)
        def read(*args,**kwargs):
            with lock:counts[key]+=1
            return original(*args,**kwargs)
        setattr(target,method,read)
        return target
    return (instrument(shop,'query','shopify_graphql_requests') if isinstance(shop,Shopify) else shop,
            instrument(store,'q','database_query_count') if isinstance(store,Store) else store,counts)


def fingerprint(shop, document, settings=None):
    inputs = {key: document.get(key) for key in ('market_audience', 'market', 'audience', 'smart_hours')}
    inputs['shop'] = str(getattr(shop, 'namespace', 'session'))
    from crm_resend_marketing import get_resend_marketing_config_status
    delivery=get_resend_marketing_config_status()
    inputs['sender'] = {key: (settings or {}).get(key,delivery.get(key)) for key in ('from', 'sender', 'reply_to','contact')}
    inputs['policy'] = 1
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()


class AudienceJob:
    def __init__(self, shop, store, document, settings=None, previous=None, debounce=0.4):
        self.identity = fingerprint(shop, document, settings)
        self.settings = deepcopy(settings)
        self.future = Future()
        self.completed_at = None
        self.previous = previous.display() if previous and previous.identity == self.identity else None
        doc = {key:deepcopy(document[key]) for key in ('market_audience','market','audience','smart_hours') if key in document}
        def work():
            if not self.future.set_running_or_notify_cancel(): return
            started = time.monotonic()
            if not _SLOTS.acquire(blocking=False):
                self.future.set_exception(ValueError('Audience preparation is busy. Retry shortly.'))
                return
            try:
                measured_shop,measured_store,reads=measured_reads(shop,store)
                state = final_audience(measured_shop, measured_store, doc)
                # Retain only frozen IDs/hashes/counts and scheduling evidence.
                # No customer mirror, full profiles, email lists or tokens.
                state['profiles'] = {identity: {'defaultAddress': {k:v for k,v in (c.get('defaultAddress') or {}).items()
                    if k in ('countryCodeV2','countryCode','country','provinceCode','province','zip','timeZone')},
                    'country': c.get('country'), 'timezone': c.get('timezone'), 'timeZone': c.get('timeZone')}
                    for identity, c in state['profiles'].items()}
                self.completed_at = time.monotonic()
                self.future.set_result(deepcopy(state))
                LOG.info('audience_prepare member_count=%d eligible_count=%d excluded_count=%d cache_hit=false total_ms=%.1f',
                    state['members'], state['eligible'], sum(state['excluded'].values()), (self.completed_at-started)*1000)
                LOG.info('audience_prepare shopify_graphql_requests=%d database_query_count=%d provider_request_count=%d',
                    reads['shopify_graphql_requests'],reads['database_query_count'],reads['provider_request_count'])
            except Exception as exc:
                LOG.warning('audience_prepare failed type=%s', type(exc).__name__)
                self.future.set_exception(exc)
            finally: _SLOTS.release()
        self.timer = threading.Timer(debounce, work)
        self.timer.daemon = True
        self.timer.start()

    def valid(self):
        return bool(self.future.done() and not self.future.cancelled() and self.future.exception() is None
            and self.completed_at is not None and time.monotonic()-self.completed_at < TTL_SECONDS)

    def display(self):
        if self.future.done() and not self.future.cancelled() and self.future.exception() is None:
            return deepcopy(self.future.result())
        return deepcopy(self.previous) if self.previous else None

    def result(self):
        state = self.future.result(timeout=90)
        if not self.valid(): raise ValueError('Audience verification expired. Review again.')
        LOG.info('audience_prepare cache_hit=true snapshot_age_ms=%.1f', (time.monotonic()-self.completed_at)*1000)
        return deepcopy(state)


def prepare(previous, shop, store, document, settings=None, *, debounce=0.4):
    token = fingerprint(shop, document, settings)
    if previous and previous.identity == token:
        if not previous.future.done() or previous.valid(): return previous
        # Errors remain visible and retryable; polling never creates a retry storm.
        if not previous.future.cancelled() and previous.future.exception() is not None: return previous
    if previous and not previous.future.running() and not previous.future.done():
        previous.timer.cancel(); previous.future.cancel()
    return AudienceJob(shop, store, document, settings, previous, debounce)


def prepare_session(session, shop, store, editor, key, settings=None):
    token = key+'audience_job'
    active=session.get('campaign_audience_active_key')
    previous=session.get(token)
    if active and active!=token:
        previous=session.pop(active,None)
    session['campaign_audience_active_key']=token
    session[token] = prepare(previous, shop, store, editor['document'], settings)
    return session[token]
