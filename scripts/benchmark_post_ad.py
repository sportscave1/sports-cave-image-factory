"""Reproducible offline renderer timings, excluding network and process import."""
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest

path = Path(__file__).resolve().parents[1] / 'tests/fixtures/post_ad_compact_preview.py'
samples = []
for _ in range(7):
    app = AppTest.from_file(str(path), default_timeout=30)
    start = time.perf_counter()
    app.run()
    cold = (time.perf_counter() - start) * 1000
    assert not app.exception, str(app.exception)
    start = time.perf_counter()
    app.run()
    warm = (time.perf_counter() - start) * 1000
    samples.append((cold, warm))
report = {'first_process_render_ms': samples[0][0], 'samples_ms': samples[1:],
                  'median_initial_ms': statistics.median(x[0] for x in samples[1:]),
                  'median_rerender_ms': statistics.median(x[1] for x in samples[1:]),
                  'elements': len(list(app)), 'network': 'mocked'}

# Compare the exact legacy lookup with the indexed lookup on identical data.
import ads_posting_page as page
rows = tuple({'shopify_product_id': str(n), 'product_title': f'Product {n}',
              'product_handle': f'product-{n}'} for n in range(10000))
records, by_id = page._product_selector_state(rows, state={})
value = records[-1]['identity']
lookup = {}
for name, action in (
    ('legacy', lambda: page.ads_page.resolve_ads_product_selector_value(value, rows=rows, records=records)),
    ('indexed', lambda: page._resolve_selected_product(value, rows, records, by_id)),
):
    timings = []
    for _ in range(7):
        start = time.perf_counter()
        for _ in range(1000):
            action()
        timings.append((time.perf_counter() - start) * 1000 / 1000)
    lookup[name + '_median_ms'] = statistics.median(timings)
report['selected_product_lookup_10000_rows'] = lookup
print(json.dumps(report, indent=2))
