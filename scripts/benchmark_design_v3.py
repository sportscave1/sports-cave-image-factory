"""Deterministic local benchmark; no network, live records or credentials."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import design_studio_sales_intelligence as intel
from tests.test_design_studio_sales_intelligence import fixture_sources


def measure(action, count=10):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        action()
        samples.append(1000 * (time.perf_counter() - start))
    return {'median_ms': round(statistics.median(samples), 3), 'max_ms': round(max(samples), 3), 'samples': count}


if __name__ == '__main__':
    source = fixture_sources()
    line = source['lines'][0]
    source['lines'] = [{**deepcopy(line), 'order_id': str(i + 1000), 'line_id': str(i + 1000)} for i in range(20000)]
    start, end = intel.reporting_window(date(2026, 10, 10))
    result = {'fixture_lines': 20000, 'aggregation': measure(lambda: intel.aggregate_sources(source, start, end), 5)}
    calls = []
    def load(*_):
        calls.append(1)
        return source
    intel._CACHE.clear()
    snap = intel.get_snapshot('Baseball', today=date(2026, 10, 10), loader=load)
    result['cached_scoped_read'] = measure(lambda: intel.get_snapshot('Baseball', today=date(2026, 10, 10), loader=load), 50)
    result['loader_calls_for_51_reads'] = len(calls)
    result['context_characters'] = len(intel.intelligence_context(snap))
    print(json.dumps(result, indent=2))
