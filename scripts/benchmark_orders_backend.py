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
    import database_read_pool
    import os_accounts

    counts = {'sql': 0, 'api': 0}
    original = psycopg.Cursor.execute

    def execute(cursor, query, *args, **kwargs):
        sql = str(query).strip().upper()
        if sql and not sql.startswith(('SELECT', 'WITH', 'SHOW', 'SET', 'BEGIN', 'COMMIT', 'ROLLBACK')):
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
        import top_bar_api
        top_bar_api.clear_order_summary_display_cache()
        top_bar_api._cached_order_action_summary(db)
        result['badge_cached'] = measure(lambda: top_bar_api._cached_order_action_summary(db))
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
        # Skip schema creation in this read-only profiler, never normal auth.
        account_id, _ = db._run_read_operation('benchmark.account_id', lambda cur: (
            cur.execute('SELECT id FROM os_users ORDER BY created_at LIMIT 1'), cur.fetchone())[1])
        if account_id:
            with patch.object(os_accounts.DEFAULT_STORE, 'ensure_schema'):
                result['account_validation'] = measure(lambda: os_accounts.DEFAULT_STORE.get_user(account_id['id']))
        result['read_pools'] = database_read_pool.stats()
    print('ORDERS_BENCHMARK_JSON=' + json.dumps(result, sort_keys=True))
    return result


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
