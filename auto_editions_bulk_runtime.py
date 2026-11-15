"""Web-owned durable review consumer. No companion/preparation/unrelated worker changes.

Threads execute work, but PostgreSQL owns every selection, lease and result.
Startup always resumes committed pending/expired work independently of HTTP.
"""
import logging
import threading
from auto_editions_bulk_jobs import ReviewJobs

LOG=logging.getLogger(__name__)
wake=threading.Event()
_lock=threading.Lock()
_pool=None
_threads=[]
_stop=threading.Event()


def connection():
    global _pool
    import supabase_backend as db
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    with _lock:
        if _pool is None:
            _pool=ConnectionPool(db._database_url_with_ssl(),min_size=0,max_size=4,timeout=4,max_waiting=8,
                max_idle=60,max_lifetime=300,check=ConnectionPool.check_connection,
                kwargs=dict(row_factory=dict_row,connect_timeout=4,prepare_threshold=None,
                    options='-c statement_timeout=6000 -c lock_timeout=1500 -c idle_in_transaction_session_timeout=20000'))
        return _pool.connection()


def authorized(actor_id):
    import os_accounts as accounts
    with connection() as conn,conn.cursor() as cur:
        cur.execute('SELECT id,role,is_active,account_status,removed_at FROM os_users WHERE id=%s',(actor_id,));user=cur.fetchone()
    if not accounts.is_admin(user) or not accounts.can_access_page(user,'Edition Ops'):
        raise PermissionError('Approval owner is no longer an active Edition Ops administrator.')


def run_one(jobs,approve=None,authorize=authorized):
    from auto_editions_bulk import approve_one
    job=jobs.claim()
    if not job:return False
    done=threading.Event()
    def heartbeat():
        while not done.wait(20):
            try:
                if not jobs.renew(job):return
            except Exception:LOG.warning('Review lease renewal deferred job=%s',job['id'])
    pulse=threading.Thread(target=heartbeat,name='edition-review-lease',daemon=True);pulse.start()
    try:
        authorize(job['actor_id'])
        if job['attempts']>3:
            jobs.finish(job,'Failed','Processing was interrupted three times. Review the current evidence before resubmitting.')
            return True
        result=(approve or approve_one)(jobs.connect,dict(product_gid=job['product_gid'],hash=job['preparation_hash']),job['actor_id'],job=job)
        # Approved was committed atomically with its result. This handles early non-write returns only.
        if result!='Approved':jobs.finish(job,result,'Preparation changed or existing approval retained.' if result=='Skipped' else 'Current source or review evidence requires Review / Repair.')
    except (ValueError,KeyError,PermissionError) as error:
        reason=str(error)[:240] if isinstance(error,(ValueError,PermissionError)) else 'Required preparation evidence is incomplete.'
        jobs.finish(job,'Needs Attention',reason+' Use Review / Repair.')
        LOG.info('Review requires attention job=%s',job['id'])
    except Exception:
        # Conditional token update cannot overwrite a committed success after ambiguous COMMIT acknowledgement.
        jobs.transient(job)
        LOG.exception('Review provider/database operation deferred job=%s',job['id'])
    finally:done.set();pulse.join(timeout=1)
    return True


def start():
    import auto_editions_runtime as runtime
    if not runtime.enabled():return
    with _lock:
        if any(t.is_alive() for t in _threads):return
        _stop.clear()
        def loop():
            jobs=ReviewJobs(connection)
            while not _stop.is_set():
                try:
                    if run_one(jobs):continue
                except Exception:LOG.exception('Durable review consumer unavailable; retrying')
                wake.wait(15);wake.clear()
        for n in range(2):
            thread=threading.Thread(target=loop,name=f'edition-review-{n}',daemon=True);_threads.append(thread);thread.start()


class ReviewLifecycle:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':
            async def recv():
                message=await receive()
                if message['type']=='lifespan.startup':start()
                if message['type']=='lifespan.shutdown':_stop.set();wake.set()
                return message
            return await self.app(scope,recv,send)
        return await self.app(scope,receive,send)
