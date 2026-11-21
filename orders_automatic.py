"""Bounded admission from the existing local Orders mirror, without page visits."""
import time,threading
_last=0
_gate=threading.Lock()


def owner(authorisation=None):
    import prodigi_preparation as prep,os_accounts
    from prodigi_submission import setting
    config=authorisation if authorisation is not None else setting()
    actor=config.get('actor')
    if not actor:
        with prep.connect() as c,c.cursor() as q:
            q.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton')
            paired=q.fetchone()
        actor=paired.get('actor_id') if paired else None
    if not actor:return None
    user=os_accounts.DEFAULT_STORE.get_user(actor);prep.require_user(user)
    return user


def kick():
    if not _gate.acquire(blocking=False):return
    def work():
        try:admit()
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Orders admission unavailable; existing jobs continue')
        finally:_gate.release()
    threading.Thread(target=work,daemon=True,name='orders-admit').start()


def admit(limit=3):
    global _last
    if time.monotonic()-_last<60:return 0
    _last=time.monotonic()
    import prodigi_preparation as prep
    from prodigi_submission import setting
    authorisation=setting()
    if not prep.enabled():return 0
    import order_allocator,order_refunds
    actor=owner(authorisation)
    if not actor:return 0
    payload=order_allocator.load_hybrid_orders_snapshot(limit=75,search='') or {}
    candidates=[r for r in payload.get('rows',[]) if str(r.get('edition_order_id') or '').isdigit()
        and r.get('allocation_valid') is not False and r.get('identity_enforced') is not False
        and str(r.get('prodigi_status') or '').strip().lower() not in ('complete','submitted')
        and not r.get('invalidated_at') and not r.get('cancelled_at') and not order_refunds.blocked(r)]
    keys=[prefix+str(r['edition_order_id']) for r in candidates for prefix in (prep.PREFIX,prep.FAILURE_PREFIX)]
    if not keys:return 0
    with prep.connect() as c,c.cursor() as q:
        q.execute("""SELECT id FROM edition_orders e WHERE id=ANY(%s) AND status='assigned'
            AND allocation_valid=true AND identity_enforced=true AND invalidated_at IS NULL
            AND to_jsonb(e)->>'cancelled_at' IS NULL
            AND COALESCE(to_jsonb(e)->>'duplicate_allocation_warning','') IN ('','false')""",
            ([int(r['edition_order_id']) for r in candidates],))
        valid={str(r['id']) for r in q.fetchall()}
        q.execute('SELECT key,value FROM app_settings WHERE key=ANY(%s)',(keys,))
        stopped={r['key'].split(':')[-1] for r in q.fetchall() if r['key'].startswith(prep.PREFIX) or r['value'].get('active')}
    count=0
    for row in candidates:
        aid=str(row['edition_order_id'])
        if aid in stopped or aid not in valid:continue
        try:prep.request(actor,int(aid))
        except (ValueError,PermissionError):pass # request records the exact failure; no automatic reset.
        count+=1
        if count>=limit:break
    return count
