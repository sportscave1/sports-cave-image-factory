"""One bounded consumer of the existing durable ledger; no email transport."""
import logging
import threading
from time import perf_counter

admission=threading.BoundedSemaphore(4)
_stop=threading.Event()
_thread=None
BATCH_SIZE=100
MAX_RECONCILIATIONS=24
LOG=logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    LOG.addHandler(logging.StreamHandler())
    LOG.propagate=False


def log(stage,**fields):
    LOG.info('resend_webhook stage=%s %s',stage,' '.join(k+'='+str(v) for k,v in fields.items()))


def run_once(store=None):
    from crm_store import Store
    from crm_callback_store import Connection
    from crm_workspace_store import WorkspaceRecords
    store=store or Store(Connection);processed=0
    # Row lock stays owned until reconciliation completes and DONE commits.
    # A crash/exception rolls it back; PENDING survives for the next cycle.
    if _stop.is_set():return 0
    started=perf_counter();rows=[]
    try:
        with store.db() as conn:
            rows=conn.execute("SELECT * FROM crm_webhook_events WHERE provider='resend' AND status='PENDING' AND (lease_until IS NULL OR lease_until<=now()) ORDER BY received_at,event_id LIMIT %s FOR UPDATE SKIP LOCKED",(BATCH_SIZE,)).fetchall()
            if not rows:return 0
            class Borrowed:
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def execute(self,*args,**kwargs):return conn.execute(*args,**kwargs)
            records=WorkspaceRecords(lambda:Borrowed())
            calls=0
            def defer(group):
                conn.execute("UPDATE crm_webhook_events SET attempts=attempts+1,error_code='processing_unavailable',lease_until=now()+interval '5 seconds' WHERE provider='resend' AND event_id=ANY(%s) AND status='PENDING'",([r['event_id'] for r in group],))
            def apply(group):
                nonlocal calls,processed
                if _stop.is_set() or calls>=MAX_RECONCILIATIONS:
                    defer(group);return
                calls+=1
                # Savepoints isolate a poison event without dropping its retry or
                # rolling back healthy peers. Splitting itself is strictly bounded.
                conn.execute('SAVEPOINT callback_reconcile')
                try:
                    records.reconcile_events_many(sorted({r['object_id'] for r in group}))
                    conn.execute("UPDATE crm_webhook_events SET status='DONE',processed_at=clock_timestamp(),error_code='',lease_until=NULL WHERE provider='resend' AND event_id=ANY(%s)",([r['event_id'] for r in group],))
                    conn.execute('RELEASE SAVEPOINT callback_reconcile')
                    processed+=len(group)
                except Exception as exc:
                    conn.execute('ROLLBACK TO SAVEPOINT callback_reconcile')
                    conn.execute('RELEASE SAVEPOINT callback_reconcile')
                    if len(group)>1:
                        middle=len(group)//2;apply(group[:middle]);apply(group[middle:])
                    else:
                        defer(group)
                        log('processing_failed',event_id=group[0]['event_id'],error_type=type(exc).__name__)
            apply(rows)
    except Exception as exc:
        # A failed/unknown outer commit is not acknowledged or automatically
        # replayed in this call. Durable queue state decides the next claim.
        log('processing_failed',error_type=type(exc).__name__,duration_ms=round((perf_counter()-started)*1000,1))
        return 0
    log('batch_processed',event_count=processed,claimed_count=len(rows),provider_count=len({r['object_id'] for r in rows}),duration_ms=round((perf_counter()-started)*1000,1))
    return processed


def _loop():
    while not _stop.is_set():
        try:processed=run_once()
        except Exception as exc:
            processed=0;log('processing_failed',error_type=type(exc).__name__)
        _stop.wait(.05 if processed else 1)


def start():
    global _thread
    if _thread and _thread.is_alive():return
    _stop.clear();_thread=threading.Thread(target=_loop,name='crm-resend-events',daemon=True);_thread.start()


def stop():
    _stop.set()
    if _thread:_thread.join(timeout=10)
    if _thread and _thread.is_alive():LOG.warning('resend_webhook stage=shutdown_pending durable_work_retained=true')
