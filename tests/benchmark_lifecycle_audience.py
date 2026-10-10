"""Bounded local SQL benchmark; synthetic rows, never a production connection."""
import sys,json,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_crm_lifecycle_expansion import DatabaseTests,AT
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG
from crm_automation_store import AutomationStore
from crm_lifecycle_audience import listing
from unittest.mock import patch

DatabaseTests.setUpClass();store=AutomationStore(connect)
store.q('''INSERT INTO crm_lifecycle_customers(customer_id,email,recipient_hash,name,subscribed_at,source_updated_at,verified_at,consent)
 SELECT 'gid://shopify/Customer/benchmark-'||i,'benchmark'||i||'@example.test',md5(i::text),'Benchmark Collector '||i,
 %s::timestamptz-i*interval '1 hour',%s,%s,'SUBSCRIBED' FROM generate_series(1,10000) i ON CONFLICT DO NOTHING''',(AT,AT,AT))
store.q('''INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,order_name,financial_status,fulfillment_status,created_at,total_price,currency)
 SELECT 'gid://shopify/Order/benchmark-'||i,'gid://shopify/Customer/benchmark-'||i,'#Benchmark'||i,'PAID','FULFILLED',
 %s::timestamptz-interval '100 days'-i*interval '1 hour','100','AUD' FROM generate_series(1,10000) i ON CONFLICT DO NOTHING''',(AT,))
store.q('ANALYZE shopify_orders');store.q('ANALYZE crm_lifecycle_customers')
results=[]
with patch.object(store,'render_settings',return_value=CFG):
    for kind in ('welcome','post_purchase','win_back'):
        row=store.create(ADMIN,kind,lifecycle=True)
        for label,kwargs in [('first_page',{}),('search',dict(search='benchmark9999@example.test'))]:
            samples=[]
            for _ in range(6):
                start=time.perf_counter();records=listing(store,row,at=AT,**kwargs)
                samples.append(round((time.perf_counter()-start)*1000,2))
            results.append(dict(flow=kind,query=label,synthetic_customers=10000,synthetic_orders=10000,queries_per_call=1,
                                shopify_calls=0,rows=len(records),warm_samples_ms=samples[1:],median_ms=statistics.median(samples[1:])))
Path('docs/lifecycle-expansion-evidence/sql-benchmark.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
