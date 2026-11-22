"""Bounded GET-only supplier tracking, independent of submission/PDF uploads.

One read per existing supplier order, shared by its numbered units. Durable
leases coordinate web/desktop processes; no countdown or supplier writes.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import threading
import prodigi_preparation as prep
import prodigi_submission as submission

LOCK = 19721130
_gate = threading.Lock()
_start_gate = threading.Lock()
_thread = None
LABELS = {'submitted':'Submitted','paused':'Submitted','on_hold':'On hold',
          'in_production':'In production','partially_shipped':'Partially shipped',
          'shipped':'Shipped','completed':'Completed','cancelled':'Cancelled','failed':'Failed'}
TERMINAL = {'completed','cancelled','failed'}


def after(seconds):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()


def refresh(value, order, persist):
    """Observe only the pinned supplier identity; never repeat submission/PDF."""
    before=(value.get('dashboard_qa') or {}).get('before') or {}
    if (str(order.get('id')) != str(value.get('order_id')) or
            str(order.get('merchantReference')) != str(before.get('merchantReference'))):
        raise ValueError('Supplier tracking identity mismatch.')
    state=order.get('status')
    if state not in LABELS:
        raise ValueError('Supplier tracking status is not recognised.')
    receipt=value['submission']
    receipt.update(supplier_status=state,checked_at=prep.now())
    value['supplier_sync']={'checked_at':prep.now(),'status':state,
        'next_at':after(86400 if state in TERMINAL else 60 if state in submission.FINALISED else 15)}
    if value['status']=='Submitted' and state in {'cancelled','failed'}:
        value.update(status='Needs review',message='Prodigi reports '+state+'. Open the existing order for review.')
        persist(value)
    elif value['status']=='Submitted':
        class Readback:
            def order(self, order_id):
                if str(order_id)!=str(order['id']):raise ValueError('Wrong supplier order.')
                return order
        # Retain the full artwork/product/manifest checks before certificates.
        submission.run(value,Readback(),prep.resolve,persist,certificate=None)
    else:
        persist(value)


def tick(limit=20):
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(LOCK,))
        if not q.fetchone()['acquired']:return
        q.execute("""SELECT key,value FROM app_settings
          WHERE key LIKE 'prodigi_prepare:%%' AND value ? 'submission'
          AND NOT COALESCE((value->>'hidden')::boolean,false)
          AND value->>'status' IN ('Submitted','Complete')
          AND COALESCE(value->'supplier_sync'->>'status','') NOT IN ('completed','cancelled','failed')
          AND COALESCE((value->'supplier_sync'->>'next_at')::timestamptz,'epoch')<now()
          AND COALESCE((value->'submission'->>'lease_until')::timestamptz,'epoch')<now()
          ORDER BY COALESCE(value->'supplier_sync'->>'checked_at',''),updated_at
          LIMIT 200 FOR UPDATE SKIP LOCKED""")
        groups={}
        for row in q.fetchall():
            v=row['value'];oid=v.get('order_id')
            if not oid or (oid not in groups and len(groups)>=limit):continue
            groups.setdefault(oid,[]).append(v)
            v.setdefault('supplier_sync',{})['next_at']=after(120)
            # Submission reconciliation cannot race this production readback.
            v['submission']['lease_until']=after(300)
            prep.save(q,v)
    def read(oid):
        try:return prep.Client().order(oid)
        except Exception:return None
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix='prodigi-read') as pool:
        for (oid,values),order in zip(groups.items(),pool.map(read,groups)):
            for value in values:
                try:
                    if order is None:raise ValueError('Supplier status temporarily unavailable.')
                    refresh(value,order,lambda _:None)
                except Exception:
                    # Preserve last good supplier state and certificate. Back off
                    # instead of treating a network failure as a production failure.
                    value.setdefault('supplier_sync',{}).update(next_at=after(60),delayed=True)
                finally:
                    value['submission']['lease_until']=prep.now()
                    submission._save(value)
    submission.kick()


def kick():
    if not prep.enabled() or not _gate.acquire(blocking=False):return
    def work():
        try:tick()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Supplier status sync delayed')
        finally:_gate.release()
    threading.Thread(target=work,daemon=True,name='orders-status').start()


def start_worker():
    """Keep tracking alive while the artwork worker is busy or Edge is closed."""
    global _thread
    if not prep.enabled():return
    with _start_gate:
        if _thread and _thread.is_alive():return
        def loop():
            wake=threading.Event()
            while True:
                kick()
                wake.wait(15)
        _thread=threading.Thread(target=loop,daemon=True,name='orders-status-clock')
        _thread.start()
