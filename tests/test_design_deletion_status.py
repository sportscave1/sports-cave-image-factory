from threading import Event
from time import perf_counter, sleep
from uuid import uuid4
import design_deletion_status as status
from display_snapshot import Snapshots


def test_nonblocking_shared_check_and_invalidation(monkeypatch):
    import morning_design_queue
    cache=Snapshots(workers=1,limit=8,ttl=30,max_age=60)
    monkeypatch.setattr(status,'CACHE',cache)
    job=dict(id=uuid4(),stage=5,file_id='saved',file_rev='r1',file_path='/Review/Final.psd')
    release=Event(); entered=Event(); calls=[]
    def check(jobs, posted):
        calls.append(jobs); entered.set(); release.wait(3)
        return {job['id']}
    monkeypatch.setattr(morning_design_queue,'_deleted_designs',check)
    try:
        assert status.deleted([job],set())==set()
        assert entered.wait(1)
        start=perf_counter()
        for _ in range(100):assert status.deleted([job],set())==set()
        assert perf_counter()-start < .2 and len(calls)==1
        release.set()
        end=perf_counter()+2
        while any(r['loading'] for r in cache.rows.values()) and perf_counter()<end:sleep(.005)
        assert status.deleted([job],set())=={job['id']}
        assert status.deleted([job],{job['id']})==set()
        # A replacement revision must never inherit an old missing-file observation.
        assert status.deleted([{**job,'file_rev':'r2'}],set())==set()
    finally:
        release.set();cache.close()
