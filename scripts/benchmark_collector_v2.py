"""Logical API counts with in-memory responses; never a live latency benchmark."""
from pathlib import Path
import sys,json,time,types
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_crm_collector_personalisation import A,P,Q,AT,context,order,product
from crm_collector_templates import document
from crm_collector_images import settings,marker
from crm_collector_resolver import resolve,ORDER,DISCOVERY
from crm_shopify import Shopify,PRODUCTS as BASE_PRODUCTS
from crm_cache import DisplayCache

ROOT=Path(__file__).resolve().parents[1]
baseline=types.ModuleType('collector_v1_benchmark');baseline.__file__=str(ROOT/'crm_collector_resolver.py')
exec(compile((ROOT/'tmp/collector-v2-baseline/crm_collector_resolver.py').read_text(),baseline.__file__,'exec'),baseline.__dict__)
records=[]
for selection in ('explicit','automatic'):
    for version,resolver in [('V1',baseline.resolve),('V2',resolve)]:
        calls=[];store=Mock(connect=None);store.state.return_value={};store.q.return_value=[{'shopify_product_id':Q}]
        def transport(query,args):
            calls.append(query.split('{')[0].strip())
            if query==ORDER:return {'order':order()}
            if query==BASE_PRODUCTS:return {'nodes':[product(i) for i in args['ids']]}
            if query==DISCOVERY:return {'s0':{'nodes':[{'id':Q}]}}
            return {'nodes':[product(i) for i in args['ids']]}
        shop=Shopify(transport=transport,namespace='fixture-'+version+'-'+selection,cache=DisplayCache())
        doc=document('collector-reengagement')
        html=marker(settings('Actual Purchased Product',1))+marker(settings('Related Products',3,product_ids=[Q] if selection=='explicit' else []))
        doc['custom_html']=html;doc['middle_sections'][0]['html']=html
        for temperature in ('cold','warm'):
            calls.clear();started=time.perf_counter()
            result=resolver(shop,store,doc,context(),A,AT,allocation_reader=lambda *a:None)
            records.append({'version':version,'selection':selection,'cache':temperature,'api_stub_calls':len(calls),
                'resolver_with_stubs_ms':round((time.perf_counter()-started)*1000,3),
                'cards':sum(len(rows) for rows in result['blocks'].values()),'live_shopify_calls':0,'delivery_calls':0})
(ROOT/'docs/collector-email-v2/resolver-performance.json').write_text(json.dumps(records,indent=2))
print(json.dumps(records,indent=2))
