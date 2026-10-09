"""Read-only exact-product facts. No schema initialization, allocation or caching."""


def read(sql,args):
    from supabase_backend import connect
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("SET LOCAL statement_timeout='2000ms'")
            cur.execute(sql,args)
            return list(cur.fetchall())


def metadata(pid):
    rows=read("""SELECT product_type,raw_json FROM shopify_products
      WHERE regexp_replace(shopify_product_id,'^gid://shopify/Product/','')=%s LIMIT 2""",(str(pid).split('/')[-1],))
    if len(rows)!=1:return {}
    row=rows[0];raw=row.get('raw_json') or {};tags=raw.get('tags') or []
    if isinstance(tags,str):tags=tags.split(',')
    collections=raw.get('collections') or []
    if isinstance(collections,dict):collections=collections.get('nodes',[])
    return {'classifications':[row.get('product_type'),*tags,*[c.get('title','') for c in collections if isinstance(c,dict)]]}


def allocation(order_id,customer_id,pid,line_id):
    if not order_id or not customer_id or not line_id:return None
    rows=read("""SELECT edition_number,edition_total FROM edition_orders
      WHERE regexp_replace(shopify_order_id,'^gid://shopify/Order/','')=%s
      AND regexp_replace(shopify_customer_id,'^gid://shopify/Customer/','')=%s
      AND regexp_replace(COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id),'^gid://shopify/Product/','')=%s
      AND regexp_replace(shopify_line_item_id,'^gid://shopify/LineItem/','')=%s
      AND allocation_valid AND identity_enforced
      AND COALESCE(status,'') NOT IN ('voided','refunded','cancelled','superseded') LIMIT 2""",
      (str(order_id).split('/')[-1],str(customer_id).split('/')[-1],str(pid).split('/')[-1],str(line_id).split('/')[-1]))
    if len(rows)!=1:return None
    number,total=rows[0]['edition_number'],rows[0]['edition_total']
    if type(number) is int and type(total) is int and 1<=number<=total:return f'#{number:03d}/{total}'
