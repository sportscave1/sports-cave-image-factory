"""Actual projection on disposable PostgreSQL, never live credentials."""
import json, time
from pathlib import Path
import pytest
from tests.test_worker_health_queue import operations, seed
from tests.test_worker_health import telemetry,continuous,store,database,pglite_database
from worker_health import Health
from worker_health_cache import DisplayIndex

@pytest.mark.parametrize('count',[100,1000,10000])
def test_full_backlog_projection_and_index(count,operations):
    d,sql=operations;seed(sql,count)
    start=time.perf_counter();value=Health(d.connect).snapshot()
    projected=(time.perf_counter()-start)*1000
    assert len(value['jobs'])==count
    index=DisplayIndex(value)
    assert sum(index.filters[k] for k in index.filters if k!='All')==count
    assert index.filters['All']==count
    cursor='';seen=[]
    while True:
        rows=index.select(cursor=cursor)
        if not rows:break
        seen.extend(r['id'] for r in rows);cursor=rows[-1]['id']
    assert len(seen)==len(set(seen))==count
    report=dict(jobs=count,projection_ms=round(projected,2),queries=value['cost']['queries'],index_bytes=index.bytes)
    out=Path('output/companion-phases');out.mkdir(parents=True,exist_ok=True)
    (out/f'database-{count}.json').write_text(json.dumps(report,indent=2))
    print(report)
