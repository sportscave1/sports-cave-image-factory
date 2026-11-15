"""Picker service boundaries, 75 ms synthetic provider latency, no external I/O."""
import json
import os
from pathlib import Path
from time import perf_counter,sleep
from unittest.mock import Mock,patch
from tests.test_crm_discounts import DiscountShop
from tests.test_crm_modular_catalogue import node,edition
from crm_discount_api import search,fresh
from crm_catalogue import Catalogue,PICKER_COLLECTIONS,PICKER_PRODUCTS,FACTS_QUERY

def main():
    rows=[]
    with patch('requests.sessions.Session.request',side_effect=AssertionError('External request forbidden')):
        for i in range(12):
            row={};calls=[]
            def measure(key,fn):
                start=perf_counter();value=fn();row[key]=(perf_counter()-start)*1000;return value
            discount=DiscountShop();original=discount.query
            def query(*a,**k):sleep(.075);return original(*a,**k)
            discount.query=query
            result=measure('discount_search_cold_service_ms',lambda:search(discount,'FIXTURE5'))
            count=len(discount.calls)
            measure('discount_search_cached_service_ms',lambda:search(discount,'FIXTURE5'))
            assert len(discount.calls)==count
            measure('discount_apply_fresh_service_ms',lambda:fresh(discount,result['rows'][0]))
            row['discount_cold_provider_calls']=count
            shop=Mock(namespace='v6-picker-'+str(i)+'-'+str(perf_counter()))
            def product_query(query,variables,*a,**k):
                calls.append(query);sleep(.075)
                if query==PICKER_COLLECTIONS:return {'collections':{'nodes':[{'id':'gid://shopify/Collection/1','title':'Editions'}],'pageInfo':{'hasNextPage':False}}}
                if query==PICKER_PRODUCTS:return {'products':{'nodes':[node()],'pageInfo':{'hasNextPage':False}}}
                if query==FACTS_QUERY:return {'nodes':[node()]}
                raise AssertionError('Unexpected provider request')
            shop.query=product_query
            catalogue=Catalogue(shop,edition_reader=lambda **kw:[edition()])
            measure('product_collections_cold_service_ms',catalogue.collections)
            measure('product_search_cold_service_ms',lambda:catalogue.search('art',collection='gid://shopify/Collection/1'))
            count=len(calls)
            measure('product_search_cached_service_ms',lambda:catalogue.search('art',collection='gid://shopify/Collection/1'))
            assert len(calls)==count
            selected=measure('product_insert_fresh_service_ms',lambda:catalogue.resolve([node()['id']],fresh=True))
            assert selected[0]['id']==node()['id'];rows.append(row)
    Path('tmp/email-v6-'+os.getenv('EMAIL_V6_LABEL','after')+'-pickers.json').write_text(json.dumps(rows,indent=2),encoding='utf8')

if __name__=='__main__':main()
