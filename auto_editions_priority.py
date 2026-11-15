"""Read synced commerce records; prioritise preparation without changing commerce."""
SQL = """
SELECT m.shopify_product_gid AS product_gid,
       COALESCE(p.is_active,p.active,false) AS active,
       COALESCE(s.sales,0) AS sales,COALESCE(s.outstanding,0) AS outstanding,
       COALESCE(s.recent,0) AS recent,
       EXISTS(SELECT 1 FROM ads_product_mapping am JOIN meta_ads a USING(ad_id)
         WHERE am.product_handle=p.shopify_handle AND p.shopify_handle<>''
           AND a.effective_status='ACTIVE') AS advertised
FROM product_psd_mappings m
JOIN edition_products p ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=m.shopify_product_gid
LEFT JOIN LATERAL (
 SELECT count(DISTINCT o.shopify_order_id) AS sales,
 count(DISTINCT o.shopify_order_id) FILTER(WHERE
   COALESCE(o.fulfillment_status,'') NOT IN ('fulfilled','FULFILLED')
   AND lower(COALESCE(o.financial_status,'')) IN ('paid','partially_paid')
   AND COALESCE(l.quantity,0)>0) AS outstanding,
 count(DISTINCT o.shopify_order_id) FILTER(WHERE o.created_at>=now()-interval '90 days') AS recent
 FROM shopify_order_lines l JOIN shopify_orders o USING(shopify_order_id)
 WHERE regexp_replace(l.shopify_product_id,'^gid://shopify/Product/','')=
       regexp_replace(m.shopify_product_gid,'^gid://shopify/Product/','')
 AND o.cancelled_at IS NULL AND COALESCE(o.financial_status,'') NOT IN ('voided','refunded','VOIDED','REFUNDED')
 AND COALESCE(o.raw_json->>'test','false')<>'true' AND COALESCE(l.quantity,0)>0
) s ON true
"""


def priority(row, current=0):
    from auto_editions_v17 import enabled
    if __import__('auto_editions_technical').enabled():
        if current==0:return 0,'Deliberately deferred/excluded'
    if enabled() and row['outstanding']:return 8, 'Outstanding customer orders'
    if current == 10:return 10, 'Administrator Prepare Now'
    if row['outstanding']:return 8, 'Outstanding customer orders'
    if enabled() and row['advertised']:return 7, 'Urgent advertised product'
    if row['recent'] or row['sales'] > 1:return 6, 'Recent or repeat sales'
    if row['sales']:return 5, 'Historical sale'
    if row['advertised']:return 4, 'Active mapped advertisement'
    if current == 2 and (row['active'] or __import__('auto_editions_technical').enabled()):return 2, 'Newly linked active product'
    if enabled():return 1, 'Continuous mapped catalogue'
    return 0, 'Deferred until an order, active advertisement or Prepare Now'


def refresh(queue, actor, *, limit=None):
    """Worker batches rotate durably; explicit legacy Resume retains a full refresh."""
    with queue.connect() as conn, conn.cursor() as cur:
        if limit is not None:
            cur.execute("""SELECT product_gid FROM auto_edition_onboarding
                WHERE status='Awaiting preparation' ORDER BY priority_checked_at NULLS FIRST,product_gid
                LIMIT %s FOR UPDATE SKIP LOCKED""",(max(1,min(int(limit),100)),))
            ids=[r['product_gid'] for r in cur.fetchall()]
            if not ids:return []
            cur.execute(SQL+' WHERE m.shopify_product_gid=ANY(%s)',(ids,))
            signals=[dict(r) for r in cur.fetchall()]
            cur.execute('SELECT product_gid,priority,status FROM auto_edition_onboarding WHERE product_gid=ANY(%s)',(ids,))
        else:
            cur.execute(SQL);signals=[dict(r) for r in cur.fetchall()]
            cur.execute('SELECT product_gid,priority,status FROM auto_edition_onboarding')
        existing={r['product_gid']:dict(r) for r in cur.fetchall()}
        for row in signals:
            old=existing.get(row['product_gid'])
            if not old or old['status']!='Awaiting preparation':continue
            score,reason=priority(row,old['priority'])
            cur.execute("""UPDATE auto_edition_onboarding SET priority=%s,reason=%s,updated_at=now()
                WHERE product_gid=%s AND status='Awaiting preparation'
                AND (priority<>%s OR reason<>%s) RETURNING product_gid""",
                (score,reason,row['product_gid'],score,reason))
            if cur.fetchone():queue.audit(cur,row['product_gid'],actor,'priority',{'priority':score,'reason':reason})
        if limit is not None:
            cur.execute('UPDATE auto_edition_onboarding SET priority_checked_at=now() WHERE product_gid=ANY(%s)',(ids,))
    return signals
