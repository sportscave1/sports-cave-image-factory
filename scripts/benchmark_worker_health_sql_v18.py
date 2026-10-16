"""Disposable PGlite Worker Health benchmark; no production connection or data."""
import argparse,json,math,os,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.getenv('AUTO_EDITIONS_BENCH_CODE_ROOT'):sys.path.insert(0,os.environ['AUTO_EDITIONS_BENCH_CODE_ROOT'])
import pytest
from tests.test_auto_editions_jobs import database
from tests.test_auto_editions_discovery import store
from tests.test_auto_editions_v17 import continuous,mapping
from tests.test_worker_health import telemetry
import worker_health

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--cached',action='store_true');args=parser.parse_args();results=[]
    for count in (285,334):
        patch=pytest.MonkeyPatch();generator=database.__wrapped__();db=next(generator)
        try:
            fixture=telemetry.__wrapped__(continuous.__wrapped__(store.__wrapped__(db,patch),patch),patch);d,sql=fixture
            for n in range(1000,1000+count):
                pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'synthetic-owner')
            cls=type(sql);original=cls.execute;calls=[]
            def execute(self,query,params=()):
                tick=time.perf_counter()
                try:return original(self,query,params)
                finally:calls.append((time.perf_counter()-tick)*1000)
            cls.execute=execute
            runs=[]
            for _ in range(7):
                calls.clear();tick=time.perf_counter()
                if args.cached:
                    from worker_health_cache import snapshot as cached
                    snapshot=cached(worker_health.Health(d.connect))
                else:snapshot=worker_health.Health(d.connect).snapshot()
                elapsed=(time.perf_counter()-tick)*1000
                assert len(snapshot['jobs'])==count
                page={**snapshot,'jobs':snapshot['jobs'][:25]}
                runs.append(dict(duration_ms=elapsed,sql_count=len(calls),sql_duration_ms=sum(calls),page_bytes=len(json.dumps(page).encode()),full_internal_bytes=len(json.dumps(snapshot).encode())))
            sql.execute("""INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event,detail)
                SELECT 'gid://shopify/Product/'||(1000+(n %% %s))::text,'synthetic-owner','diagnostic',
                '{"code":"ICC_MISMATCH","stage":"Preparing"}'::jsonb FROM generate_series(1,1000)n""".replace('%%','%'),(count,))
            diagnostics=[]
            for _ in range(7):
                calls.clear();tick=time.perf_counter();logs=worker_health.Health(d.connect).logs(component='Photoshop',search='ICC')
                diagnostics.append(dict(duration_ms=(time.perf_counter()-tick)*1000,sql_count=len(calls),visible_rows=len(logs['rows'])))
                assert len(logs['rows'])==50 and logs['next_cursor']
            cls.execute=original
            results.append(dict(products=count,runs=runs,median_ms=statistics.median(r['duration_ms'] for r in runs),p95_ms=sorted(r['duration_ms'] for r in runs)[-1],diagnostics=diagnostics))
        finally:
            patch.undo()
            try:next(generator)
            except StopIteration:pass
    Path(args.output).write_text(json.dumps(results,indent=2));print(json.dumps(results))

if __name__=='__main__':main()
