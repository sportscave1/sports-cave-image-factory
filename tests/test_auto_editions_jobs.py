"""Real disposable PostgreSQL execution via PGlite; never production data."""
import json
import os
from pathlib import Path
import subprocess
import threading
import urllib.request
import urllib.error

import pytest
import auto_editions as ae
from auto_editions_jobs import Jobs


@pytest.fixture
def database():
    module=os.environ.get('AUTO_EDITIONS_TEST_PGLITE')
    if not module or not Path(module).is_file():
        pytest.skip('Set AUTO_EDITIONS_TEST_PGLITE to the installed PGlite dist/index.js')
    child=subprocess.Popen(['node',str(Path(__file__).with_name('auto_editions_postgres_server.mjs'))],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        port=child.stdout.readline().strip()
        assert port.isdigit(), child.stderr.read()
        lock=threading.RLock()
        class Cursor:
            rows=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,args=()):
                parts=sql.split('%s')
                sql=parts[0]+''.join('$'+str(i)+p for i,p in enumerate(parts[1:],1))
                request=urllib.request.Request('http://127.0.0.1:'+port,
                    data=json.dumps(dict(sql=sql,args=args)).encode(),headers={'Content-Type':'application/json'})
                try:
                    with urllib.request.urlopen(request,timeout=10) as response:self.rows=json.load(response)['rows']
                except urllib.error.HTTPError as error:
                    with error:raise RuntimeError(json.load(error)['error']) from None
            def fetchone(self):return self.rows[0] if self.rows else None
            def fetchall(self):return self.rows
        class Connection:
            def __enter__(self):lock.acquire();Cursor().execute('BEGIN');return self
            def __exit__(self,typ,*args):
                try:Cursor().execute('ROLLBACK' if typ else 'COMMIT')
                finally:lock.release()
            def cursor(self):return Cursor()
        yield Jobs(Connection),Cursor()
    finally:
        child.terminate();child.communicate(timeout=10)


def job():
    identity=dict(allocation=42,number=5)
    return dict(id=ae.fingerprint(identity),identity=identity)


def test_idempotent_queue_reclaims_expired_lease_and_rejects_old_worker(database):
    jobs,sql=database;j=job()
    jobs.enqueue(j,'admin');jobs.enqueue(j,'va')
    sql.execute('SELECT count(*) AS n FROM auto_edition_jobs')
    assert sql.fetchone()['n']==1
    first=jobs.claim();assert first['attempts']==1 and jobs.claim() is None
    sql.execute("UPDATE auto_edition_jobs SET lease_until=now()-interval '1 second'")
    second=jobs.claim();assert second['attempts']==2
    with pytest.raises(ValueError,match='lease'):jobs.finish(j['id'],first['lease_token'],result={'ok':True})
    jobs.finish(j['id'],second['lease_token'],result={'ok':True})
    assert jobs.read(j['id'])['status']=='Ready' and jobs.claim() is None


def test_last_crashed_attempt_does_not_leave_permanent_spinner(database):
    jobs,sql=database;j=job();jobs.enqueue(j,'admin')
    for n in (1,2,3):
        assert jobs.claim()['attempts']==n
        sql.execute("UPDATE auto_edition_jobs SET lease_until=now()-interval '1 second'")
    assert jobs.claim() is None
    assert jobs.read(j['id'])['status']=='Blocked'
    with pytest.raises(ValueError,match='cannot be retried'):jobs.retry(j['id'],'admin')
    sql.execute("SELECT count(*) AS n FROM auto_edition_job_audit WHERE event='attempts_exhausted'")
    assert sql.fetchone()['n']==1


def test_retry_is_bounded_and_browser_roles_cannot_read_jobs(database):
    jobs,sql=database;j=job();jobs.enqueue(j,'admin')
    first=jobs.claim();jobs.finish(j['id'],first['lease_token'],error_code='worker_unavailable')
    jobs.retry(j['id'],'va');assert jobs.claim()['attempts']==2
    for role in ('anon','authenticated'):
        sql.execute('SET ROLE '+role)
        try:
            with pytest.raises(RuntimeError,match='permission denied'):
                sql.execute('SELECT * FROM auto_edition_jobs')
        finally:sql.execute('RESET ROLE')


def test_expired_output_is_not_downloadable_and_regenerates_only_on_request(database):
    jobs,sql=database;j=job();jobs.enqueue(j,'admin');claim=jobs.claim()
    jobs.finish(j['id'],claim['lease_token'],result={'output':{'file_id':'id:generated'}})
    sql.execute("UPDATE auto_edition_jobs SET updated_at=now()-interval '25 hours'")
    assert len(jobs.expired())==1
    assert jobs.read(j['id'])['status']=='Blocked' and jobs.claim() is None
    assert jobs.enqueue(j,'va')['status']=='Blocked' # Must finish remote cleanup first.
    jobs.forget_expired_output(j['id'])
    assert jobs.enqueue(j,'va')['status']=='Queued'
    assert jobs.claim()['attempts']==1


def test_preparations_are_additive_and_approval_checks_expected_layout(database,tmp_path):
    from auto_editions_store import Preparations
    from test_auto_editions import package
    jobs,sql=database;registry=Preparations(jobs.connect)
    manifest=package(tmp_path);digest=ae.fingerprint(manifest)
    unit=dict(shopify_product_gid=manifest['source']['product_gid'],shopify_variant_id='v1')
    proofs=[dict(preparation_hash=digest,pixel_exact=True),dict(preparation_hash=digest,outside_number_exact=True)]
    registry.save(manifest,proofs,{},'admin')
    registry.approve(digest,unit,'admin')
    assert registry.for_unit(unit)['manifest']==manifest
    with pytest.raises(ValueError,match='changed'):registry.approve(digest,unit,'admin',expected='wrong')
    assert registry.index()=={(unit['shopify_product_gid'],'v1'):None}


def test_scoped_layout_does_not_enable_other_allocations(database,tmp_path):
    from auto_editions_store import Preparations
    from test_auto_editions import package
    jobs,sql=database;registry=Preparations(jobs.connect)
    manifest=package(tmp_path);digest=ae.fingerprint(manifest)
    unit=dict(id=42,shopify_product_gid=manifest['source']['product_gid'],shopify_variant_id='v1')
    registry.save(manifest,[dict(preparation_hash=digest,pixel_exact=True,outside_number_exact=True)],{},'admin')
    registry.approve(digest,unit,'admin',allocation_ids=[42,43])
    assert registry.for_unit(unit)['manifest']==manifest
    assert registry.index()[(unit['shopify_product_gid'],'v1')]==[42,43]
    with pytest.raises(ValueError,match='outside'):registry.for_unit({**unit,'id':44})



def test_download_retention_prevents_expiry_and_keeps_exact_output(database):
    jobs,sql=database;j=job();jobs.enqueue(j,'admin');claim=jobs.claim()
    result={'output':{'file_id':'id:exact','sha256':'a'*64}}
    jobs.finish(j['id'],claim['lease_token'],result=result)
    jobs.retain(j['id'],'va')
    sql.execute("UPDATE auto_edition_jobs SET updated_at=now()-interval '100 days'")
    assert jobs.expired()==[]
    assert jobs.read(j['id'])['result']['output']==result['output']
    assert jobs.read(j['id'])['result']['retained'] is True


def test_new_master_does_not_advertise_previous_output(database):
    jobs,sql=database;j=job()
    j['identity'].update(allocation_id=42,source={'product_gid':'gid://shopify/Product/123'},variant_id='v1')
    j['preparation_hash']='a'*64;j['id']=ae.fingerprint(j['identity'])
    jobs.enqueue(j,'admin');claimed=jobs.claim()
    jobs.finish(j['id'],claimed['lease_token'],result={'output':{'file_id':'id:old'},'retained':True})
    assert jobs.summaries(['42'])['42']['id']==j['id']
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES (%s,'{}','[]','{}','admin')",('b'*64,))
    sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES (%s,'v1',%s,'{}')",('gid://shopify/Product/123','b'*64))
    assert jobs.summaries(['42'])=={}
    assert jobs.read(j['id'])['result']['output']['file_id']=='id:old'


def test_product_test_layout_preserves_variant_override_and_history(database,tmp_path):
    from auto_editions_store import Preparations
    from test_auto_editions import package
    jobs,sql=database;registry=Preparations(jobs.connect)
    manifest=package(tmp_path);digest=ae.fingerprint(manifest)
    unit=dict(id=42,shopify_product_gid=manifest['source']['product_gid'],shopify_variant_id='v1')
    registry.save(manifest,[dict(preparation_hash=digest,pixel_exact=True,outside_number_exact=True)],{},'admin')
    registry.approve(digest,{**unit,'shopify_variant_id':'*'},'admin')
    assert registry.for_unit(unit)['variant_ids']==['v1']
    registry.approve(digest,unit,'admin',allocation_ids=[42])
    with pytest.raises(ValueError,match='outside'):registry.for_unit({**unit,'id':43})
    assert registry.for_unit({**unit,'id':43,'shopify_variant_id':'v2'})['manifest']==manifest
    j=job();j['identity'].update(allocation_id=43,source=manifest['source'],variant_id='v2');j['preparation_hash']=digest;j['id']=ae.fingerprint(j['identity'])
    jobs.enqueue(j,'admin');claimed=jobs.claim();jobs.finish(j['id'],claimed['lease_token'],result={'output':{'file_id':'original'}})
    assert jobs.summaries(['43'])['43']['id']==j['id']
    sql.execute("INSERT INTO auto_edition_preparations(hash,manifest,proofs,receipts,created_by) VALUES (%s,'{}','[]','{}','admin')",('b'*64,))
    sql.execute("UPDATE auto_edition_layouts SET preparation_hash=%s WHERE variant_id='*'",('b'*64,))
    assert jobs.summaries(['43'])=={}
    assert jobs.read(j['id'])['result']['output']['file_id']=='original'
