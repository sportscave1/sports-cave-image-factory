"""Real multi-connection PostgreSQL lock contention on an explicitly local DB."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg.rows import dict_row
import pytest
from auto_editions_jobs import Jobs
from tests.test_product_upload_intake import env as env_fixture
from tests.test_product_upload_manual_takeover import inactive, save
from tests.test_product_upload_mapping import ADMIN,PID,count
from psd_mapping_store import MappingConflict


@pytest.fixture
def local_env(tmp_path,monkeypatch):
    port=os.getenv('MANUAL_TAKEOVER_LOCAL_PORT','')
    if not port.isdigit():pytest.skip('Set MANUAL_TAKEOVER_LOCAL_PORT to the disposable localhost PostgreSQL test container')
    def connect():
        return psycopg.connect(host='127.0.0.1',port=int(port),dbname='manual_takeover_test',
                              user='postgres',password=os.environ['MANUAL_TAKEOVER_LOCAL_PASSWORD'],row_factory=dict_row)
    with connect() as conn,conn.cursor() as cur:
        cur.execute('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS')
        cur.execute((Path(__file__).resolve().parents[1]/'migrations/20261014004209_auto_editions_v6.sql').read_text())
    with connect() as conn:
        conn.autocommit=True
        with conn.cursor() as cur:
            yield env_fixture.__wrapped__((Jobs(connect),cur),tmp_path,monkeypatch)


def test_expired_lease_with_inflight_row_lock_refuses_takeover_then_recovers(local_env):
    service,key,source,current=inactive(local_env,moved=True)
    before=local_env[0].read(key,ADMIN['id'])
    with service.connect() as worker,worker.cursor() as cur:
        cur.execute('SELECT id FROM product_upload_intakes WHERE id=%s FOR UPDATE',(key,))
        # A separate connection must fail promptly, without waiting for the worker,
        # even though its persisted lease is absent/expired.
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(save,service,key,current)
            with pytest.raises(MappingConflict,match='worker is active'):future.result(timeout=5)
        assert count(local_env[1],'product_psd_mappings')==0
    assert local_env[0].read(key,ADMIN['id'])==before
    assert save(service,key,current)['verified']
    assert service.mappings.read_one(PID)['file_path']==current['path_display']
