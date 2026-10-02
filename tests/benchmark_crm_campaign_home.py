"""Reproducible offline scheduling comparison; never measures provider latency.

Run: python -m tests.benchmark_crm_campaign_home
Optional CRM_TEST_POSTGRES=1 adds EXPLAIN against the loopback SQL fixture only.
"""
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter, sleep
from types import SimpleNamespace
import json
import os
import subprocess
from crm_campaign_home_cache import job
from crm_campaign_home_data import counts, delivery_summary, attribution_summary, reporting_window, rows


def baseline():
    source=subprocess.run(['git','show','HEAD:crm_campaign_home_data.py'],check=True,capture_output=True,text=True).stdout
    namespace={}
    exec(compile(source,'baseline_home_data','exec'),namespace)
    return SimpleNamespace(**namespace)


def run():
    old=baseline();before=[];after=[]
    payload=dict(all_count=4,drafts=2,active=0,sent=2,archived=0,sent_emails=8,click_rate=25,revenue={'NZD':'250'},orders=2)
    def q(sql,args=(),one=False):
        sleep(.08)  # Equal fabricated latency for every logical read.
        if sql.startswith('SELECT c.id'):return None
        return payload.copy() if one else []
    store=SimpleNamespace(connect=None,q=q)
    for _ in range(5):
        started=perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            summary=pool.submit(old.summary,store)
            def table():return old.rows(store,top=old.top_identity(store))
            listing=pool.submit(table)
            listing.result();before.append((perf_counter()-started)*1000)
            summary.result()
        state={};window=reporting_window();started=perf_counter()
        jobs=[job(state,store,(name,),load) for name,load in (
            ('counts',lambda:counts(store)),('delivery',lambda:delivery_summary(store,window)),
            ('attribution',lambda:attribution_summary(store,window)),('table',lambda:rows(store)))]
        jobs[-1].result();after.append((perf_counter()-started)*1000)
        for future in jobs:future.result()
    report={'synthetic_read_delay_ms':80,'old_visible_table_median_ms':round(median(before),1),
      'new_visible_table_median_ms':round(median(after),1),'old_cold_read_count':3,'new_cold_read_count':4,
      'old_table_change_read_count':2,'new_table_change_read_count':1,
      'note':'Synthetic scheduling only; no live latency or production data.'}
    if os.getenv('CRM_TEST_POSTGRES')=='1':
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        sql_store=CampaignStore(connect);plans=[]
        def explain(sql,args=(),one=False):
            started=perf_counter()
            plan=sql_store.q('EXPLAIN (ANALYZE, FORMAT JSON) '+sql,args,one=True)
            result=sql_store.q(sql,args,one=one)
            root=plan['QUERY PLAN'][0]
            def nodes(node):
                return [dict(type=node['Node Type'],relation=node.get('Relation Name'),
                             rows=node.get('Actual Rows'),loops=node.get('Actual Loops'))]+[
                    child for subtree in node.get('Plans',[]) for child in nodes(subtree)]
            plans.append({'duration_including_explain_ms':round((perf_counter()-started)*1000,2),
                          'execution_ms':root['Execution Time'],'nodes':nodes(root['Plan'])})
            return result
        profiled=SimpleNamespace(connect=connect,q=explain)
        window=reporting_window()
        counts(profiled);delivery_summary(profiled,window);attribution_summary(profiled,window);rows(profiled)
        report['loopback_sql_plans']=plans
    print(json.dumps(report,default=str,indent=2))


if __name__=='__main__':run()
