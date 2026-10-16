"""Read-only production profiling. Prints timings/counts, never customer records."""
import contextlib
import io
import json
import math
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(samples=20):
    import psycopg
    import requests
    import supabase_backend as db
    import orders_page as orders
    import order_allocator
    import psd_directory
    import auto_editions_runtime

    counts = {'sql': 0, 'api': 0}
    original = psycopg.Cursor.execute

    def execute(cursor, query, *args, **kwargs):
        sql = str(query).strip().upper()
        if not sql.startswith(('SELECT', 'WITH', 'SHOW', 'SET', 'BEGIN', 'COMMIT', 'ROLLBACK')):
            raise RuntimeError('Benchmark refuses non-read SQL')
        if sql.startswith(('SELECT', 'WITH')) and sql not in {'SELECT 1', 'SELECT 1;'}:
            counts['sql'] += 1
        return original(cursor, query, *args, **kwargs)

    def network(*args, **kwargs):
        counts['api'] += 1
        raise RuntimeError('Orders rendering must not call external APIs')

    def measure(fn):
        elapsed, queries, api = [], [], []
        for _ in range(samples):
            before = dict(counts)
            started = time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            elapsed.append(round((time.perf_counter() - started) * 1000, 3))
            queries.append(counts['sql'] - before['sql'])
            api.append(counts['api'] - before['api'])
        result = {'n': samples, 'first_ms': elapsed[0],
                'median_ms': round(statistics.median(elapsed), 3),
                'p95_ms': sorted(elapsed)[math.ceil(.95 * samples) - 1],
                'sql_per_call': sorted(set(queries)), 'api_per_call': sorted(set(api))}
        print('ORDERS_BENCHMARK_PHASE=' + json.dumps(result), flush=True)
        return result

    with patch.object(psycopg.Cursor, 'execute', execute), patch.object(requests.sessions.Session, 'request', network):
        result = {'badge': measure(db.get_order_action_summary)}
        result['latest_50'] = measure(lambda: orders._read_orders_snapshot(limit=50))
        result['search'] = measure(lambda: orders._read_orders_snapshot(search='SC3303', limit=50))
        result['visibility_marker'] = measure(lambda: db.orders_visibility_marker(ensure_schema_first=False))
        with contextlib.redirect_stdout(io.StringIO()):
            rows = orders._sort_rows(orders._read_orders_snapshot(limit=50)['rows'])
        result['rows'] = len(rows)
        result['psd_directory'] = measure(psd_directory.directory)
        result['jpg_status'] = measure(lambda: auto_editions_runtime.download_links(rows))
        result['render_preparation'] = measure(lambda: orders._display_rows(rows, normalised=True))
        result['snapshot_reuse'] = measure(lambda: orders._apply_latest_product_numbers(rows))
    print('ORDERS_BENCHMARK_JSON=' + json.dumps(result, sort_keys=True))
    return result


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
