"""Synthetic durable upload queue acknowledgement/read timing on real PostgreSQL."""
import json
from pathlib import Path
from time import perf_counter
import psycopg
import product_upload_staff_queue as queue
from product_upload_dropbox import REVIEW
from tests.status_phase1_postgres import disposable_database


def run():
    result = dict(synthetic=True, samples=[], provider_work_measured=False)
    with disposable_database() as (jobs, cursor):
        root = Path(__file__).resolve().parents[1]
        for file in ('20261117110000_product_upload_staff_queue.sql',
                     '20261118070000_product_upload_manual_restart.sql'):
            cursor.execute((root / 'migrations' / file).read_text())
        cursor.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
        statements = []
        class CountedCursor(psycopg.Cursor):
            def execute(self, query, params=None, **kwargs):
                statements.append(str(query))
                return super().execute(query, params, **kwargs)
        original = queue.connect
        def connect():
            conn = jobs.connect()
            conn.cursor_factory = CountedCursor
            return conn
        queue.connect = connect
        try:
            for trial in range(3):
                source = dict(id='id:synthetic-original', rev=str(trial), name='Synthetic.psd',
                              path_display=REVIEW + '/Synthetic.psd', **{'.tag':'file'})
                statements.clear(); started = perf_counter()
                identity = queue.enqueue({'id':'synthetic-staff'}, source, 'Synthetic design', 'NFL Wall Art')
                result['samples'].append(dict(workflow='durable_enqueue_acknowledgement', trial=trial,
                    ms=(perf_counter()-started)*1000, statements=len(statements)))
                assert queue.enqueue({'id':'synthetic-staff'}, source, 'Synthetic design', 'NFL Wall Art') == identity
                statements.clear(); started = perf_counter()
                value = queue.list_jobs('synthetic-staff', display_only=True)
                result['samples'].append(dict(workflow='scoped_queue_display_read', trial=trial,
                    ms=(perf_counter()-started)*1000, statements=len(statements),
                    json_bytes=len(json.dumps(value, default=str).encode())))
                assert len(value['jobs']) == trial+1
                assert queue.list_jobs('other-synthetic-staff', display_only=True)['jobs'] == []
            return result
        finally:
            queue.connect = original


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
