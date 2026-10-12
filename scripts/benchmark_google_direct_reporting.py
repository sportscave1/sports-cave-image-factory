"""Offline cache-overhead benchmark. No credentials, network or database."""
from pathlib import Path
import sys
import json
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google_direct_reporting import MemoryReports


def main():
    cache = MemoryReports()
    rows = [{'query': f'query {i}', 'clicks': i, 'impressions': i * 10, 'position': 5.5} for i in range(5000)]
    fetched = [0]
    def fetch():
        fetched[0] += 1
        return rows
    start = time.perf_counter()
    cache.read('report', 28800, fetch)
    cold = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    for _ in range(20):
        cache.read('report', 28800, fetch)
    warm = (time.perf_counter() - start) * 1000 / 20
    print(json.dumps({'synthetic_rows': len(rows), 'cold_cache_insert_ms': round(cold, 3), 'mean_warm_copy_ms': round(warm, 3), 'fetch_calls_for_21_reads': fetched[0], 'retained_serialized_bytes': cache.size, 'live_google_latency_measured': False}))


if __name__ == '__main__':
    main()
