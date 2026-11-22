"""One bounded local read, reused by the existing cached companion status feed."""
def snapshot(connect):
    from companion_read_connection import read_connection
    import prodigi_preparation as prep
    try:
        with read_connection(connect) as c,c.cursor() as q:
            q.execute("""WITH units AS (
              SELECT DISTINCT ON (value->>'allocation_id') value,updated_at
              FROM app_settings WHERE (key LIKE 'prodigi_prepare:%%' OR key LIKE 'orders_auto_jpg:%%' OR key LIKE 'prodigi_prepare_failure:%%') AND (key NOT LIKE 'prodigi_prepare_failure:%%' OR COALESCE((value->>'active')::boolean,false)) AND NOT COALESCE((value->>'hidden')::boolean,false)
              ORDER BY value->>'allocation_id',CASE WHEN key LIKE 'prodigi_prepare_failure:%%' THEN 0 WHEN key LIKE 'prodigi_prepare:%%' THEN 1 ELSE 2 END,updated_at DESC
            ), stats AS (SELECT count(*) FILTER(WHERE value->>'status' IN
              ('Queued','Waiting','Preparing JPG','Awaiting product selection','Awaiting browser upload','Awaiting dashboard QA','Ready for manual payment','Submitted')) AS waiting FROM units)
            SELECT value,updated_at,stats.waiting,
              EXISTS(SELECT 1 FROM app_settings WHERE key='orders_submit_after_qa' AND value->>'enabled'='true') AS automatic,
              EXISTS(SELECT 1 FROM product_upload_desktop WHERE singleton AND seen_at>now()-interval '95 seconds') AS online
            FROM stats LEFT JOIN LATERAL (SELECT * FROM units ORDER BY
              CASE WHEN value->>'status' IN ('Uploading','Selecting product','Browser uploading','Generating','Checking QA','Checking dashboard QA','Submitting','Certificate pending') THEN 0
                   WHEN value->>'status' IN ('Needs QA','Needs review','Repair','Submission uncertain') THEN 1
                   WHEN value->>'status' IN ('Queued','Waiting','Preparing JPG','Awaiting product selection','Awaiting browser upload','Awaiting dashboard QA','Ready for manual payment','Submitted') THEN 2 ELSE 3 END,updated_at DESC LIMIT 10) recent ON true""")
            rows=q.fetchall()
        jobs=[]
        for row in rows:
            v=row.get('value')
            if not v:continue
            status=v.get('status','Needs review')
            state=('complete' if status in ('Complete','Ready') else 'running' if status in
                ('Uploading','Selecting product','Browser uploading','Generating','Checking QA','Checking dashboard QA','Submitting','Certificate pending')
                else 'waiting' if status in ('Queued','Waiting','Preparing JPG','Awaiting product selection','Awaiting browser upload','Awaiting dashboard QA','Ready for manual payment','Submitted') else 'failed')
            snap=v.get('snapshot') or {}
            jobs.append(dict(id=str(v.get('allocation_id')),title=(snap.get('order_reference') or v.get('order_reference') or '')+' · '+(snap.get('product') or v.get('title') or 'Order'),
                state=state,can_restart=state=='failed',label='JPG ready' if status=='Ready' else status,updated_at=str(row['updated_at']),percent=100 if state=='complete' else 0,estimated=False))
        return dict(enabled=prep.enabled(),automation_enabled=bool(rows and rows[0]['automatic']),online=bool(rows and rows[0]['online']),waiting=rows[0]['waiting'] if rows else 0,jobs=jobs)
    except Exception:return dict(enabled=prep.enabled(),online=False,waiting=0,jobs=[],unavailable=True)
