"""One bounded consumer of the existing durable ledger; no email transport."""
import logging
import threading
from time import perf_counter

admission=threading.BoundedSemaphore(4)
_stop=threading.Event()
_thread=None
LOG=logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    LOG.addHandler(logging.StreamHandler())
    LOG.propagate=False


def log(stage,**fields):
    LOG.info('resend_webhook stage=%s %s',stage,' '.join(k+'='+str(v) for k,v in fields.items()))


def run_once(store=None):
    from crm_store import Store
    from crm_workspace_store import WorkspaceRecords
    store=store or Store();processed=0
    # Row lock stays owned until reconciliation completes and DONE commits.
    # A crash/exception rolls it back; PENDING survives for the next cycle.
    for _ in range(50):
        if _stop.is_set():break
        started=perf_counter()
        row=None
        try:
            with store.db() as conn:
                row=conn.execute("SELECT * FROM crm_webhook_events WHERE provider='resend' AND status='PENDING' AND (lease_until IS NULL OR lease_until<=now()) ORDER BY received_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
                if not row:break
                # Reuse the SAME transaction for the unchanged reconciliation,
                # including stop-state, and DONE. No second pool connection.
                class Borrowed:
                    def __enter__(self):return self
                    def __exit__(self,*args):return False
                    def execute(self,*args,**kwargs):return conn.execute(*args,**kwargs)
                WorkspaceRecords(lambda:Borrowed()).reconcile_events(row['object_id'])
                conn.execute("UPDATE crm_webhook_events SET status='DONE',processed_at=now() WHERE provider='resend' AND event_id=%s",(row['event_id'],))
        except Exception as exc:
            log('processing_failed',event_id=(row or {}).get('event_id','unclaimed'),error_type=type(exc).__name__,duration_ms=round((perf_counter()-started)*1000,1))
            if row:
                store.q("UPDATE crm_webhook_events SET attempts=attempts+1,error_code='processing_unavailable',lease_until=now()+interval '5 seconds' WHERE provider='resend' AND event_id=%s AND status='PENDING'",(row['event_id'],))
            return processed
        processed+=1
        log('processed',event_id=row['event_id'],duration_ms=round((perf_counter()-started)*1000,1))
    return processed


def _loop():
    while not _stop.is_set():
        try:run_once()
        except Exception as exc:log('processing_failed',error_type=type(exc).__name__)
        _stop.wait(1)


def start():
    global _thread
    if _thread and _thread.is_alive():return
    _stop.clear();_thread=threading.Thread(target=_loop,name='crm-resend-events',daemon=True);_thread.start()


def stop():
    _stop.set()
    if _thread:_thread.join(timeout=10)
    if _thread and _thread.is_alive():LOG.warning('resend_webhook stage=shutdown_pending durable_work_retained=true')
