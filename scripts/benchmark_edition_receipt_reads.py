"""Offline PostgreSQL benchmark; synthetic receipts, no application credentials."""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_auto_editions_jobs import database
from tests.test_edition_receipt_read_performance import legacy_sql, package
from auto_editions_v17 import receipt_sql


def main():
    fixture = database.__wrapped__()
    _, cursor = next(fixture)
    results = []
    try:
        cursor.execute('CREATE TEMP TABLE receipt_benchmark(hash text, manifest jsonb, receipts jsonb)')
        for total in (100, 500, 1000):
            manifest, receipts = package(total)
            cursor.execute('TRUNCATE receipt_benchmark')
            cursor.execute('INSERT INTO receipt_benchmark SELECT %s,%s::jsonb,%s::jsonb FROM generate_series(1,8)',
                           ('b' * 64, json.dumps(manifest), json.dumps(receipts)))
            result = {'editions_per_preparation': total, 'preparations': 8, 'samples': 3}
            for name, expression in [('before', legacy_sql()), ('after', receipt_sql('p'))]:
                cursor.execute('SELECT ' + expression + ' AS valid FROM receipt_benchmark p')
                assert all(row['valid'] for row in cursor.fetchall())
                times = []
                for _ in range(3):
                    cursor.execute('EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) SELECT ' + expression + ' FROM receipt_benchmark p')
                    plan = cursor.fetchone()['QUERY PLAN'][0]
                    times.append(plan['Execution Time'])
                result[name + '_median_server_ms'] = round(statistics.median(times), 3)
            result['speedup'] = round(result['before_median_server_ms'] / result['after_median_server_ms'], 2)
            results.append(result)
        print(json.dumps({'platform': 'Disposable PGlite PostgreSQL; synthetic data', 'results': results}, indent=2))
    finally:
        fixture.close()


if __name__ == '__main__':
    main()
