"""Local deterministic timings; simulated API latency, never production."""
from copy import deepcopy
import json
from time import perf_counter,sleep
from timeit import repeat
from tests.test_crm_discounts import DiscountShop,doc
from tests.test_crm_abandoned_checkout import native_document,checkout
from tests.test_crm_send_flow import CFG
from crm_abandoned_checkout import hydrate,context
from crm_discount_api import search
from crm_recovery_discount import substitute,apply_links
from crm_campaign_content import render_campaign


def main():
    shop=DiscountShop();query=shop.query
    def transport(*args,**kwargs):sleep(.02);return query(*args,**kwargs)
    shop.query=transport
    at=perf_counter();search(shop,'FIXTURE5');cold=(perf_counter()-at)*1000;calls=len(shop.calls)
    at=perf_counter();search(shop,'FIXTURE5');warm=(perf_counter()-at)*1000
    original=hydrate(native_document(),context(checkout(9001)))
    selected=deepcopy(original);selected['recovery_discount']=doc(shop)['recovery_discount']
    selected['content'].update(subject='Offer {{discount_code}}',preheader='{{discount_value}}')
    target={**selected['recovery_discount'],'original_url':checkout(9001)['abandonedCheckoutUrl']}
    before=lambda:render_campaign(original,CFG)
    after=lambda:apply_links(render_campaign(substitute(selected),CFG),target)
    before();after()
    print(json.dumps({'cold_search_ms':round(cold,3),'cached_search_ms':round(warm,3),
        'cold_fixture_api_calls':calls,'cached_extra_api_calls':len(shop.calls)-calls,
        'existing_render_ms':round(min(repeat(before,number=100,repeat=3))*10,3),
        'render_with_discount_ms':round(min(repeat(after,number=100,repeat=3))*10,3)}))


if __name__=='__main__':main()
