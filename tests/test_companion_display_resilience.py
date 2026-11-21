from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import time
import pytest
from display_snapshot import Snapshots
from worker_health_cache import Snapshot, DisplayIndex, summary


def wait_for(check, timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=check()
        if result: return result
        time.sleep(.005)
    raise AssertionError('background refresh did not complete')


def value(n=100):
    return dict(jobs=[dict(id=f'gid://shopify/Product/{i+1}', category='Queued' if i%2 else 'Failed',
                          design='Synthetic fixture', stage='Waiting', versionless=i) for i in range(n)],
                cost={'queries':2}, counts={'queued':n//2}, updated_at='fixture', overall='Degraded')


def test_20_viewers_single_refresh_stale_failure_and_expiry():
    now=[0.]
    cache=Snapshot(clock=lambda:now[0])
    gate=Event(); calls=[]
    def loader():
        calls.append(1);gate.wait(2);return value(10000)
    def read():
        try:return cache.read_index(loader)
        except TimeoutError:return None
    with ThreadPoolExecutor(max_workers=20) as pool:
        start=time.monotonic();results=list(pool.map(lambda _:read(),range(20)))
    assert time.monotonic()-start<.5 and len(calls)==1
    gate.set();wait_for(lambda: not cache.loading)
    index,meta=read()
    assert len(index.select(limit=50))==50 and index.filters['All']==10000
    now[0]=6
    failed=Event()
    def failure():
        failed.set();raise RuntimeError('synthetic outage')
    before=time.monotonic();old,meta=cache.read_index(failure)
    assert time.monotonic()-before<.1 and old is index and meta['state']=='stale'
    failed.wait(1);wait_for(lambda:not cache.loading)
    assert cache.read_index(failure)[1]['state']=='stale'
    now[0]=130
    with pytest.raises(TimeoutError):cache.read_index(failure)


def test_index_filter_cursor_delta_and_full_counts():
    index=DisplayIndex(value(10000))
    rows=index.select('Queued',limit=50)
    assert len(rows)==50 and all(r['category']=='Queued' for r in rows)
    second=index.select('Queued',cursor=rows[-1]['id'],limit=50)
    assert not set(r['id'] for r in rows)&set(r['id'] for r in second)
    known={r['id']:r['version'] for r in rows}
    changed,removed=index.changes('Queued',known,rows[-1]['id'])
    assert changed==[] and removed==[]
    known[rows[0]['id']]='0'*20
    changed,removed=index.changes('Queued',known,rows[-1]['id'])
    assert [r['id'] for r in changed]==[rows[0]['id']]
    changed,removed=index.changes('Failed',known,'end')
    assert len(changed)<=50 and len(removed)==50
    assert summary(index,{'state':'ready'})['filters']['All']==10000
    assert len(json.dumps(rows))<50000


def test_invalidation_during_refresh_cannot_publish_obsolete_snapshot():
    cache=Snapshot();gate=Event()
    def loader():gate.wait(1);return value()
    with pytest.raises(TimeoutError):cache.read_index(loader)
    cache.invalidate();gate.set();wait_for(lambda:not cache.loading)
    assert cache.value is None
    wait_for(lambda: safe_read(cache,lambda:value(10)))
    assert cache.value.filters['All']==10


def safe_read(cache, loader):
    try:return cache.read_index(loader)
    except TimeoutError:return None


def test_queue_cache_isolated_bounded_and_returns_last_good():
    now=[1.];cache=Snapshots(workers=1,limit=2,ttl=1,max_age=10,byte_limit=10000,clock=lambda:now[0])
    try:
        cache.read(('a','upload'),lambda:{'jobs':['private-a']})
        result=wait_for(lambda:cache.read(('a','upload'),lambda:None)['value'])
        result['jobs'].append('changed')
        assert cache.read(('a','upload'),lambda:None)['value']['jobs']==['private-a']
        assert cache.read(('b','upload'),lambda:{'jobs':['private-b']})['value'] is None
        wait_for(lambda:cache.read(('b','upload'),lambda:None)['value'])
        now[0]=3
        def fail():raise RuntimeError('outage')
        assert cache.read(('a','upload'),fail)['value']['jobs']==['private-a']
    finally:cache.close()


def test_queue_cache_invalidation_discards_late_old_result():
    gate=Event();cache=Snapshots(workers=2,limit=2,ttl=10,byte_limit=10000)
    try:
        def old():gate.wait(1);return {'enabled':True}
        cache.read(('admin','control'),old)
        cache.invalidate(('admin','control'))
        cache.read(('admin','control'),lambda:{'enabled':False})
        wait_for(lambda:cache.read(('admin','control'),lambda:None)['value'])
        gate.set();time.sleep(.02)
        assert cache.read(('admin','control'),lambda:None)['value']=={'enabled':False}
    finally:gate.set();cache.close()


def test_cold_api_refresh_is_retryable_and_redacted(monkeypatch):
    import asyncio
    import worker_health_api as api
    from tests.test_auto_editions_api import ADMIN,request
    monkeypatch.setattr('files_upload_api._request_user',lambda *args,**kwargs:ADMIN)
    def fail():raise TimeoutError('private connection details')
    monkeypatch.setattr(api,'store',fail)
    response=asyncio.run(api.snapshot(request('GET')))
    assert response.status_code==503 and response.headers['Retry-After']=='2'
    assert b'private connection' not in response.body and b'loading' in response.body
