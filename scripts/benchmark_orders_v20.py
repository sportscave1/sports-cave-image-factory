"""Read-only Orders profiler: aggregates/digests only, no customer data output.

May run in an isolated production-shell process. Never changes deployed files.
An optional local bundle replaces read functions in this process only.
"""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path.cwd()))


def main(samples=20, bundle=None):
    import psycopg
    import requests
    import supabase_backend as db
    import orders_page as orders
    import auto_editions_runtime as runtime
    import psd_directory
    import database_read_pool as pools
    import psutil

    original_execute = psycopg.Cursor.execute
    original_fetchall = psycopg.Cursor.fetchall
    queries, details = [], []
    recording = [False]
    counts = {'sql': 0, 'api': 0}
    def execute(cur, query, params=None, **kwargs):
        sql = str(query).strip()
        if sql and not sql.upper().startswith(('SELECT', 'WITH', 'SHOW', 'SET', 'BEGIN', 'COMMIT', 'ROLLBACK', 'EXPLAIN')):
            raise RuntimeError('Read-only profiler refused SQL')
        before = time.perf_counter()
        result = original_execute(cur, query, params, **kwargs)
        if sql.upper().startswith(('SELECT', 'WITH')):
            counts['sql'] += 1
            if recording[0]:
                queries.append((sql, params))
                details.append({'sql_hash': hashlib.sha256(sql.encode()).hexdigest()[:12],
                                'execute_ms': round((time.perf_counter()-before)*1000, 3)})
        return result
    def fetchall(cur):
        rows = original_fetchall(cur)
        if recording[0] and details:
            details[-1].update(rows=len(rows), decoded_bytes=len(json.dumps(rows, default=str)))
        return rows
    def no_http(*args, **kwargs):
        counts['api'] += 1
        raise RuntimeError('External HTTP forbidden during Orders display reads')
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
    def measure(fn):
        elapsed, sql, api, waits = [], [], [], []
        cold = time.perf_counter(); fn(); cold = (time.perf_counter()-cold)*1000
        for _ in range(samples):
            previous = dict(counts)
            before_wait = sum(p.get('requests_wait_ms', 0) for p in pools.stats())
            before = time.perf_counter(); fn(); elapsed.append((time.perf_counter()-before)*1000)
            sql.append(counts['sql']-previous['sql']); api.append(counts['api']-previous['api'])
            waits.append(sum(p.get('requests_wait_ms', 0) for p in pools.stats())-before_wait)
        return dict(n=samples, first_ms=round(cold,3), median_ms=round(statistics.median(elapsed),3),
                    p95_ms=round(sorted(elapsed)[math.ceil(.95*samples)-1],3),
                    min_ms=round(min(elapsed),3), max_ms=round(max(elapsed),3),
                    sql_per_call=sorted(set(sql)), api_per_call=sorted(set(api)), lease_wait_ms=waits)

    with patch.object(psycopg.Cursor, 'execute', execute), patch.object(psycopg.Cursor, 'fetchall', fetchall), \
            patch.object(requests.sessions.Session, 'request', no_http), contextlib.redirect_stdout(io.StringIO()):
        recording[0] = True
        initial = orders._read_orders_snapshot(limit=50)
        rows = orders._sort_rows(initial['rows'])
        runtime.download_links(rows)
        recording[0] = False
        plans = []
        with db.read_connection() as conn, conn.cursor() as cur:
            for sql, params in queries:
                cur.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql, params)
                plan = cur.fetchone()['QUERY PLAN'][0]
                plans.append({'execution_ms': plan['Execution Time'], 'planning_ms': plan['Planning Time'],
                              'node': plan['Plan']['Node Type'], 'rows': plan['Plan']['Actual Rows']})
        before_digest = digest(initial['rows'])
        before_links = digest(runtime.download_links(rows))
        parity_queries = ('SC3303', 'SC3145', 'Warne', 'no-order-v20-fixture')
        before_searches = {query: digest(orders._read_orders_snapshot(search=query, limit=50)['rows'])
                           for query in parity_queries}
        if bundle:
            import types
            for name, source in json.loads(Path(bundle).read_text()).items():
                module = sys.modules.get(name)
                if module is None:
                    module = types.ModuleType(name);sys.modules[name] = module
                exec(compile(source, '<read-only-benchmark-candidate>', 'exec'), module.__dict__)
        operations = {'latest_50': lambda: orders._read_orders_snapshot(limit=50),
                      'search': lambda: orders._read_orders_snapshot(search='SC3303', limit=50),
                      'badge': db.get_order_action_summary,
                      'psd': psd_directory.directory,
                      'jpg': lambda: orders._order_display_resources(rows)[1],
                      'render_preparation': lambda: orders._display_rows(rows, normalised=True)}
        results = {key: measure(fn) for key, fn in operations.items()}
        current = orders._read_orders_snapshot(limit=50)
        results.update(rows=len(rows), equal_initial_rows=before_digest==digest(current['rows']),
                       equal_jpg_links=before_links==digest(orders._order_display_resources(rows)[1]),
                       search_parity={query: before_searches[query]==digest(
                           orders._read_orders_snapshot(search=query, limit=50)['rows']) for query in parity_queries},
                       sql_profile=details, plans=plans, read_pools=pools.stats(),
                       rss_mb=round(psutil.Process().memory_info().rss/1024/1024,2))
    print('V20_BENCHMARK_JSON='+json.dumps(results, sort_keys=True), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv)>1 else 20, sys.argv[2] if len(sys.argv)>2 else None)
