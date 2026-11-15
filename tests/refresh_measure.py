"""Reproducible offline baseline/after measurements; not production timings."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from streamlit.testing.v1 import AppTest
import ads_page as ads
from tests.test_ads_refresh_plan import fixture


def measure():
    result = {}
    for kind, count in [('Instant Experience',3),('Carousel',5),('Carousel',6)]:
        app = AppTest.from_file('tests/fixtures/refresh_ui.py')
        app.query_params.update({'format':kind,'count':str(count)})
        start=time.perf_counter();app.run(timeout=30);cold=(time.perf_counter()-start)*1000
        values=[]
        for _ in range(5):
            start=time.perf_counter();app.run(timeout=30);values.append((time.perf_counter()-start)*1000)
        result[f'{kind}-{count}']={'cold_ms':round(cold,2),'rerun_median_ms':round(statistics.median(values),2),
            'exceptions':[e.message for e in app.exception],
            'buttons':[b.label for b in app.button],
            'media_reads':app.session_state.filtered_state.get('fixture_media_reads',0)}
    hashes={}
    for category in ('Football','Motorsport','Cricket','Baseball','NBA'):
        for kind in ('Carousel','Instant Experience','Single Image / Video'):
            prompt=ads.build_ads_prompt('Verified Collector Artwork',category,'Australia',kind,
                product_url='https://sportscave.com.au/products/verified',variation_token='baseline')
            hashes[f'new/{category}/{kind}']=hashlib.sha256(prompt.encode()).hexdigest()
        for kind in ('Instant Experience','Single Image / Video'):
            value=fixture(kind)
            prompt=ads.build_ads_prompt(value['product_name'],category,'Australia',kind,
                product_url=value['product_url'],creative_refresh_context=value['creative_refresh_context'],variation_token='baseline')
            hashes[f'refresh/{category}/{kind}']=hashlib.sha256(prompt.encode()).hexdigest()
    result['unaffected_prompts']=hashes
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__': measure()
