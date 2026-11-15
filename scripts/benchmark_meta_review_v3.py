"""Repeatable offline CPU benchmark; deliberately makes no Meta/storage calls."""
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import meta_review_tables as tables
import meta_review_search as search
import meta_review_live as live

def measure(fn, n=30, prepare=None):
    values=[]
    for _ in range(n):
        if prepare: prepare()
        start=time.perf_counter(); fn(); values.append((time.perf_counter()-start)*1000)
    return {'p50_ms':round(statistics.median(values),3), 'p95_ms':round(sorted(values)[int(.95*(n-1))],3),'samples':n}

def run():
    result={}
    for size in (100,1000):
        rows=[{'campaign_id':str(i),'campaign_name':f'Motorsport Brock campaign {i}',
               'status':'ACTIVE','created_time':'2026-09-01','metrics':{'spend':i*1.23,'roas':2.5}} for i in range(size)]
        cache={}; key=('fixture','overview'); live.cached_read(cache,key,lambda:rows)
        # Warm imports separately from repeated work.
        tables.va_styled(tables.va_campaign_rows(rows),rows)._compute()
        result[str(size)]={
            'search':measure(lambda:search.search_campaigns(rows,'brock')),
            'sort':measure(lambda:tables.sort_campaigns(rows,'Spend')),
            'table_style':measure(lambda:tables.va_styled(tables.va_campaign_rows(rows),rows)._compute()),
            'warm_cache_copy':measure(lambda:live.cached_read(cache,key,lambda:rows))}
    print(json.dumps(result,indent=2))
if __name__=='__main__': run()
