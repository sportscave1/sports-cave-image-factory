"""Repeatable synthetic GraphQL/cache benchmark; never calls external systems."""
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_cache import DisplayCache
from crm_shopify import Shopify
from crm_logic import LiveFacts
from tests.crm_fixtures import ShopifyFixture


def main():
    wire=ShopifyFixture(1000);shop=Shopify(wire,DisplayCache())
    results={}
    def measure(label,call,n=1):
        times=[];before=len(wire.calls);value=None
        for _ in range(n):
            start=time.perf_counter();value=call();times.append((time.perf_counter()-start)*1000)
        results[label]={'mean_ms':round(statistics.mean(times),3),'requests_total':len(wire.calls)-before,'iterations':n}
        return value
    page=measure('first_customer_page_cold',shop.customers)
    measure('first_customer_page_cached',shop.customers,100)
    measure('next_page',lambda:shop.customers(page['pageInfo']['endCursor']))
    c=measure('customer_detail_cold',lambda:shop.customer(1))
    measure('purchase_facts_cold',lambda:LiveFacts(shop,c).purchases())
    measure('purchase_facts_cached',lambda:LiveFacts(shop,c).purchases(),100)
    measure('native_segment_members',lambda:shop.members('gid://shopify/Segment/1'))
    results['customer_page_json_bytes']=len(json.dumps(page).encode())
    results['cache_approx_bytes']=shop.cache.bytes
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
