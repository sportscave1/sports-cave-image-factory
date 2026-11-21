"""Admit new allocated orders to the existing JPG worker in small durable batches."""
import json,os
from datetime import datetime,timezone

PREFIX='orders_auto_jpg:'
SINCE='orders_auto_jpg_since'


def admit(connect,limit=3):
    if os.getenv('SPORTS_CAVE_ORDERS_AUTO_JPG','true').lower()!='true':return 0
    import auto_editions_runtime as runtime
    with connect() as c,c.cursor() as q:
        q.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(%s,to_jsonb(now()::text),now()) ON CONFLICT(key) DO NOTHING",(SINCE,))
        q.execute('SELECT value FROM app_settings WHERE key=%s',(SINCE,));since=q.fetchone()['value']
        q.execute("""SELECT e.id,e.shopify_product_gid,e.shopify_order_name,p.product_title,
          o.status AS preparation_status,a.value AS journal,j.id AS job_id,j.status AS job_status
          FROM edition_orders e
          LEFT JOIN edition_products p ON p.shopify_product_gid=e.shopify_product_gid
          LEFT JOIN auto_edition_onboarding o ON o.product_gid=e.shopify_product_gid
          LEFT JOIN app_settings a ON a.key=%s||e.id::text
          LEFT JOIN LATERAL (SELECT id,status FROM auto_edition_jobs
            WHERE payload->'identity'->>'allocation_id'=e.id::text ORDER BY updated_at DESC LIMIT 1) j ON true
          WHERE e.status='assigned' AND e.allocation_valid=true AND e.identity_enforced=true
            AND e.invalidated_at IS NULL AND to_jsonb(e)->>'cancelled_at' IS NULL
            AND COALESCE(to_jsonb(e)->>'duplicate_allocation_warning','') IN ('','false')
            AND COALESCE(NULLIF(to_jsonb(e)->>'assigned_at','')::timestamptz,
                         NULLIF(to_jsonb(e)->>'created_at','')::timestamptz)>=%s::timestamptz
            AND COALESCE(a.value->>'status','')<>'Ready'
            AND (a.updated_at IS NULL OR a.updated_at<now()-interval '30 seconds')
          ORDER BY a.updated_at NULLS FIRST,e.id LIMIT %s""",(PREFIX,since,max(1,min(limit,10))))
        rows=q.fetchall()
    _,jobs=runtime.stores()
    for row in rows:
        status='Waiting';message='Waiting for prepared artwork';job_id=row.get('job_id')
        try:
            if row.get('job_status')=='Ready':status,message='Ready','JPG ready'
            elif row.get('job_status') in ('Queued','Generating'):status,message=row['job_status'],'Preparing numbered JPG'
            elif row.get('preparation_status')=='Cloud Ready':
                job,_=runtime.job_for(row['id']);result=jobs.enqueue(job,'orders-auto-jpg')
                status,job_id,message=result['status'],job['id'],'Preparing numbered JPG'
            elif row.get('preparation_status') in ('Blocked','Needs PSD Repair'):
                status,message='Repairing','Edition Companion repair queue'
        except ValueError:
            status,message='Repair','Artwork preparation needs repair; use the existing Repair action.'
        value=dict(allocation_id=row['id'],order_reference=row.get('shopify_order_name'),
            title=row.get('product_title') or 'Edition artwork',status=status,message=message,job_id=job_id,
            updated_at=datetime.now(timezone.utc).isoformat())
        with connect() as c,c.cursor() as q:
            q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()',
                      (PREFIX+str(row['id']),json.dumps(value)))
    return len(rows)
