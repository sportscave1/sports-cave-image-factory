import json
from types import SimpleNamespace
from test_auto_editions_jobs import database
import orders_auto_jpg as auto
import auto_editions_runtime as runtime


def tables(sql):
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    sql.execute('CREATE TABLE edition_products(shopify_product_gid text,product_title text)')
    sql.execute('CREATE TABLE auto_edition_onboarding(product_gid text,status text)')
    sql.execute('CREATE TABLE edition_orders(id bigint,shopify_product_gid text,shopify_order_name text,status text,allocation_valid bool,identity_enforced bool,invalidated_at timestamptz,assigned_at timestamptz)')
    sql.execute("INSERT INTO edition_products VALUES('p','Synthetic artwork')")
    sql.execute("INSERT INTO auto_edition_onboarding VALUES('p','Cloud Ready')")
    sql.execute("INSERT INTO edition_orders VALUES(1,'p','#TEST1','assigned',true,true,NULL,now()-interval '1 day')")


def test_only_new_valid_orders_are_automatically_admitted_in_small_batches(database,monkeypatch):
    jobs,sql=database;tables(sql);calls=[]
    mockjobs=SimpleNamespace(enqueue=lambda job,actor:(calls.append((job['id'],actor)) or {'status':'Queued'}))
    monkeypatch.setattr(runtime,'stores',lambda:(None,mockjobs))
    monkeypatch.setattr(runtime,'job_for',lambda allocation:({'id':'job-'+str(allocation)},None))
    assert auto.admit(jobs.connect)==0 # Historical orders are not silently regenerated.
    sql.execute("INSERT INTO edition_orders VALUES(2,'p','#TEST2','assigned',true,true,NULL,now()+interval '1 second'),(3,'p','#TEST3','assigned',false,true,NULL,now()+interval '1 second')")
    assert auto.admit(jobs.connect)==1
    assert calls==[('job-2','orders-auto-jpg')]
    assert auto.admit(jobs.connect)==0 # Thirty-second durable admission throttle.
    sql.execute("SELECT value FROM app_settings WHERE key='orders_auto_jpg:2'")
    assert sql.fetchone()['value']['status']=='Queued'


def test_blocked_preparation_uses_existing_repair_queue_and_never_sends_to_supplier(database,monkeypatch):
    jobs,sql=database;tables(sql)
    monkeypatch.setattr(runtime,'stores',lambda:(None,None))
    sql.execute('INSERT INTO app_settings(key,value) VALUES(%s,to_jsonb(%s::text))',(auto.SINCE,'2020-01-01T00:00:00Z'))
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked'")
    assert auto.admit(jobs.connect)==1
    sql.execute("SELECT value FROM app_settings WHERE key='orders_auto_jpg:1'")
    assert sql.fetchone()['value']['status']=='Repairing'


def test_orders_header_is_bounded_local_and_exposes_real_status(database,monkeypatch):
    import prodigi_preparation as prep
    from orders_companion_header import snapshot
    jobs,sql=database;tables(sql)
    sql.execute('CREATE TABLE product_upload_desktop(singleton bool,seen_at timestamptz)')
    sql.execute('INSERT INTO product_upload_desktop VALUES(true,now())')
    sql.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',('prodigi_prepare:1',json.dumps(dict(allocation_id=1,status='Checking dashboard QA',snapshot={'order_reference':'#TEST1','product':'Artwork'}))))
    monkeypatch.setattr(prep,'enabled',lambda:True)
    value=snapshot(jobs.connect)
    assert not value.get('unavailable') and value['online']
    assert value['jobs'][0]['state']=='running' and value['jobs'][0]['percent']==0
    assert value['jobs'][0]['title']=='#TEST1 · Artwork'
