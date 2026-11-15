"""Local SQL benchmark; explicit fixture opt-in, no production connections."""
import ast
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.getenv('CRM_TEST_POSTGRES')!='1':raise SystemExit('Start the disposable CRM fixture and set CRM_TEST_POSTGRES=1.')
from tests.crm_db_fixture import Connection
from crm_store import Store
from crm_logic import now,date
from crm_checkout_analytics import details

# HEAD is the untouched pre-repair implementation, not a second checkout.
source=subprocess.check_output(['git','show','HEAD:crm_checkout_analytics.py'],text=True,encoding='utf-8')
tree=ast.parse(source);function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='details')
scope={'json':json,'date':date}
exec(compile(ast.Module(body=[function],type_ignores=[]),'<baseline-details>','exec'),scope)
baseline=scope['details']

class Measured(Connection):
    statements=0
    def execute(self,sql,args=()):
        type(self).statements+=1
        # Controlled 20ms transport cost per statement, not a production claim.
        time.sleep(.02)
        return super().execute(sql,args)

store=Store(Measured);os.environ['SHOPIFY_STORE_DOMAIN']='fixture.myshopify.com'
rows=[{'id':'gid://shopify/AbandonedCheckout/benchmark'+str(i),
       'createdAt':'2026-10-01T00:00:00Z','updatedAt':'2026-10-01T00:00:00Z',
       'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/benchmark-token-'+str(i)+'/recover',
       'customer':{'id':'gid://shopify/Customer/benchmark'+str(i),'firstName':'Fixture','email':'fixture'+str(i)+'@example.test'}} for i in range(12)]
for row in rows:details(store,row)
results={}
for name,fn in [('before',baseline),('after',details)]:
    samples=[];counts=[]
    for _ in range(3):
        Measured.statements=0;start=time.perf_counter()
        for row in rows:assert fn(store,row)=='Unchanged'
        samples.append(round((time.perf_counter()-start)*1000,2));counts.append(Measured.statements)
    results[name]={'samples_ms':samples,'median_ms':statistics.median(samples),'statements_per_page':counts}
print(json.dumps({'fixture':'12 unchanged checkouts; 20ms injected per SQL statement including BEGIN/COMMIT; 3 runs; PGlite loopback','results':results},indent=2))
