"""Stable disposable connection factory, matching production cache identity."""
import logging,time
from tests.crm_db_fixture import connect as sql_connect
CONTROLS={'latency_ms':0,'fail_identity':False,'fail_save':False,'fail_definition':False}
def configure(**values):CONTROLS.update(values)
def connect():
    controls=dict(CONTROLS)
    started=time.perf_counter();connection=sql_connect()
    logging.warning('V5_DB_CONNECTION duration_ms=%.3f',(time.perf_counter()-started)*1000)
    class TracedConnection:
        def __enter__(self):
            started=time.perf_counter();connection.__enter__()
            logging.warning('V5_DB_BEGIN duration_ms=%.3f',(time.perf_counter()-started)*1000)
            return self
        def __exit__(self,*args):return connection.__exit__(*args)
        def execute(self,sql,args=()):
            started=time.perf_counter()
            try:
                if controls['latency_ms']:time.sleep(controls['latency_ms']/1000)
                if controls['fail_identity'] and 'jsonb_array_length' in sql and 'JOIN' not in sql:raise TimeoutError('Synthetic identity timeout')
                if controls['fail_save'] and sql.startswith('UPDATE crm_automations'):raise OSError('Synthetic save failure')
                if controls['fail_definition'] and 'SELECT * FROM crm_automations' in sql:raise OSError('Synthetic definition failure')
                return connection.execute(sql,args)
            finally:
                category='identity' if 'jsonb_array_length' in sql and 'JOIN' not in sql else 'definition' if 'SELECT * FROM crm_automations' in sql else 'freshness' if 'SELECT updated_at FROM crm_automations' in sql else 'publication' if 'crm_template_versions' in sql else 'other'
                logging.warning('V5_DB_QUERY kind=%s duration_ms=%.3f',category,(time.perf_counter()-started)*1000)
    return TracedConnection()
