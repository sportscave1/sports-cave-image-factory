"""Deterministic, bounded identity reads; no executor or provider dependency."""
from time import monotonic
from crm_automation_read_cache import lifecycle


class BoundedStore:
    def __init__(self,store):self.store=store
    def q(self,sql,args=(),one=False):
        with self.store.db() as connection:
            connection.execute("SET LOCAL statement_timeout = '1500ms'")
            connection.execute("SET LOCAL lock_timeout = '500ms'")
            cursor=connection.execute(sql,args)
            return cursor.fetchone() if one else cursor.fetchall()


def identity_read(state,store,key,load):
    cache=state.setdefault('automation_identity_cache',{})
    identity=(store.connect,key)
    previous=cache.get(identity)
    if previous and monotonic()-previous['at']<30:
        return previous['rows'],previous['state']
    started=monotonic()
    lifecycle('READ_START',key)
    try:
        records=load(BoundedStore(store))
        rows=[{**r,'id':str(r['id']),'updated_at':str(r.get('updated_at') or ''),
               'publication':r.get('publication') or {}} for r in records]
        phase='READY'
        lifecycle('READ_COMPLETE',key,elapsed_ms=round((monotonic()-started)*1000),rows=len(rows))
        lifecycle('RESULT_CONSUMED',key,rows=len(rows))
    except Exception as exc:
        phase='TIMED_OUT' if isinstance(exc,TimeoutError) or getattr(exc,'sqlstate',None) in ('57014','55P03') else 'ERROR'
        rows=previous['rows'] if previous else []
        lifecycle('READ_TIMEOUT' if phase=='TIMED_OUT' else 'READ_ERROR',key,exception=type(exc).__name__)
    cache[identity]={'rows':rows,'state':phase,'at':monotonic()}
    while len(cache)>8:cache.pop(next(iter(cache)))
    return rows,phase
