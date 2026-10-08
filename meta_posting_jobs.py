"""Browser-independent execution of the existing posting service and ledger.

No Meta operation is retried here. The service owns resource reconciliation and
idempotency. A lost process with a nonterminal ledger requires review, not replay.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
from meta_posting_service import (
    MetaPostingService, SupabasePostingStore, PostingError, PostingBusyError,
    posting_ad_results, carousel_ad_result, CAROUSEL_AD_TYPE,
)
from meta_ads_client import sanitize_meta_error

TERMINAL = {'COMPLETE', 'FAILED', 'AMBIGUOUS', 'ABANDONED_EXTERNALLY'}

class PostingJobs:
    def __init__(self, store_factory=SupabasePostingStore, service_factory=MetaPostingService):
        self.store_factory = store_factory
        self.service_factory = service_factory
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='meta-posting')
        self.lock = RLock()
        self.jobs = {}

    def submit(self, request, *, retry=False):
        identity = str(request.submission_id)
        with self.lock:
            job = self.jobs.get(identity)
            if job and not job['future'].done():
                return identity
            # Bound retained image buffers; running jobs must never be evicted.
            for key in list(self.jobs):
                if len(self.jobs) < 8:
                    break
                if self.jobs[key]['future'].done():
                    del self.jobs[key]
            if len(self.jobs) >= 8:
                raise PostingBusyError('Posting is busy. Retry shortly; no new job was submitted.')
            store = self.store_factory()
            if not store.reserve(request, retry=retry):
                return identity
            job = {'request': deepcopy(request), 'message': 'Validating campaign and creatives…'}
            self.jobs[identity] = job
            try:
                job['future'] = self.pool.submit(self._run, identity, job['request'])
            except Exception:
                job['future'] = Future()
                job['future'].set_result(None)
                store.update_stage(identity, 'FAILED', safe_error=(
                    'Posting could not start. No Meta request was made. Retry this job.'
                ))
                raise
        return identity

    def _run(self, identity, request):
        store = self.store_factory()
        def progress(message):
            with self.lock:
                self.jobs[identity]['message'] = message
        try:
            self.service_factory(store=store, progress_callback=progress).create_paused_campaign(request)
        except PostingBusyError:
            pass # Another valid lease is authoritative; never overwrite it.
        except PostingError as exc:
            row = store.get(identity)
            if row.get('status') not in TERMINAL:
                # Validation before ledger claim is safely retryable; after claim
                # a missing response must be reconciled before any new writes.
                status = 'FAILED' if row.get('request_fingerprint') == 'pending' else 'AMBIGUOUS'
                store.update_stage(identity, status, safe_error=sanitize_meta_error(exc))
        except Exception:
            try:
                store.update_stage(identity, 'AMBIGUOUS', safe_error=(
                    'Posting stopped unexpectedly. Review the saved Meta IDs before '
                    'retrying; no automatic replay was attempted.'
                ))
            except Exception:
                pass  # Keep last durable checkpoint; UI never calls it success.

    def snapshot(self, identity):
        row = self.store_factory().get(identity)
        with self.lock:
            job = self.jobs.get(str(identity))
            running = bool(job and not job['future'].done())
            return {
                **row, 'running_here': running,
                'operation': job['message'] if running else '',
                'can_retry': bool(job and not running and row.get('status') == 'FAILED'),
            }

    def retry(self, identity):
        with self.lock:
            request = self.jobs[str(identity)]['request']
        return self.submit(request, retry=True)

JOBS = PostingJobs()

def confirmed_ads(row):
    ads = (
        [carousel_ad_result(row.get('ad_results'))]
        if row.get('ad_type') == CAROUSEL_AD_TYPE
        else posting_ad_results(row.get('ad_results'))
    )
    count = sum(
        bool(ad.get('meta_ad_id')) and ad.get('meta_ad_configured_status') == 'PAUSED'
        for ad in ads
    )
    return count, len(ads)
