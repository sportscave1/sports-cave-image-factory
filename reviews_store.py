"""Server-only canonical Reviews store; indexed pages and transactional aggregates."""
from datetime import timedelta
import json
import re
import uuid
from urllib.parse import urlsplit
from crm_store import Store
from crm_logic import now
from crm_tracking import public_https
from reviews_model import product_gid,display_settings,plain,STATUSES

def require(user):
    import os_accounts
    if not os_accounts.account_is_active(user) or not os_accounts.can_access_page(user,'reviews'):
        raise PermissionError('Your account does not have access to Reviews.')

def actor(user):return str(user.get('id') or user.get('email') or 'staff')[:200]

class ReviewsStore(Store):
    def settings(self):
        row=self.q("SELECT value FROM sc_review_settings WHERE key='display'",one=True)
        return display_settings(row['value'] if row else {})
    def save_settings(self,user,value):
        require(user);value=display_settings(value)
        self.q("INSERT INTO sc_review_settings(key,value) VALUES('display',%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",(json.dumps(value),))
        from reviews_public_cache import CACHE
        CACHE.invalidate()
    def summary(self):
        r=self.q("SELECT * FROM sc_review_totals WHERE scope='all'",one=True) or {}
        # Exact rolling UTC 30 days: complete UTC days plus one indexed boundary slice.
        start=now()-timedelta(days=30)
        count=self.q("""SELECT COALESCE((SELECT sum(total) FROM sc_review_days WHERE day>(%s AT TIME ZONE 'UTC')::date),0)+
          (SELECT count(*) FROM sc_reviews WHERE status IN ('PENDING','PUBLISHED') AND source_metadata->>'date_known' IS DISTINCT FROM 'false' AND created_at>=%s AND created_at<((%s AT TIME ZONE 'UTC')::date+1)::timestamp AT TIME ZONE 'UTC') AS n""",(start,start,start),True)['n']
        total=int(r.get('total',0));return {'total':total,'average':float(r.get('rating_total',0))/total if total else None,
          'recent':int(count),'five_rate':100*int(r.get('fives',0))/total if total else None,'attention':int(r.get('attention',0))}
    def aggregate(self,product=None):
        row=self.q('SELECT published,published_rating FROM sc_review_totals WHERE scope=%s',(product or 'all',),True) or {}
        n=int(row.get('published',0));return {'count':n,'average':float(row.get('published_rating',0))/n if n else None}
    def rows(self,*,status='all',search='',product='',rating=0,source='',since=None,offset=0,limit=25,sort='newest',public=False):
        limit=max(1,min(50,int(limit)));offset=max(0,min(50000,int(offset)));clauses=[];args=[]
        if public:clauses.extend(["status='PUBLISHED'","product_id IS NOT NULL"])
        elif status=='all':clauses.append("status<>'SPAM'")
        elif status=='reply':clauses.append("status IN ('PENDING','PUBLISHED') AND merchant_reply='' AND rating<=2")
        elif status=='attention':clauses.append("status IN ('PENDING','PUBLISHED') AND (status='PENDING' OR product_id IS NULL OR (rating<=2 AND merchant_reply=''))")
        elif status in STATUSES:clauses.append('status=%s');args.append(status)
        else:raise ValueError('Invalid status filter.')
        if search:clauses.append("search_document @@ plainto_tsquery('simple',%s)");args.append(str(search)[:150])
        if product:clauses.append('product_id=%s');args.append(product_gid(product))
        if rating:clauses.append('rating=%s');args.append(int(rating))
        if source:clauses.append('source=%s');args.append(source)
        if since:clauses.append('created_at>=%s');args.append(since)
        order={'newest':'created_at DESC,id DESC','highest':'rating DESC,created_at DESC,id DESC','lowest':'rating ASC,created_at DESC,id DESC'}
        if sort not in order:raise ValueError('Invalid review sort.')
        fields="id,product_id,product_title,product_image,product_url,reviewer_name,rating,title,body,created_at,verified_purchase,merchant_reply,status,(source_metadata->>'date_known' IS DISTINCT FROM 'false') AS date_known" if public else '*'
        return self.q('SELECT '+fields+' FROM sc_reviews WHERE '+' AND '.join(clauses)+' ORDER BY '+order[sort]+' LIMIT %s OFFSET %s',(*args,limit+1,offset))
    def get_review(self,identity):return self.q('SELECT * FROM sc_reviews WHERE id=%s',(str(uuid.UUID(str(identity))),),True)
    def products(self,search=''):
        return self.q("SELECT shopify_product_id,title,handle,image_url,online_store_url FROM shopify_products WHERE position(lower(%s) in lower(COALESCE(title,'')||' '||COALESCE(handle,'')))>0 ORDER BY title LIMIT 25",(str(search)[:150],))
    def match_product(self,hints):
        """Exact priority; an ambiguous higher-priority result never falls through."""
        checks=[];identity=product_gid(hints.get('product_id'))
        if identity:checks.append(('shopify_product_id IN (%s,%s)',(identity,identity.rsplit('/',1)[-1])))
        handle=str(hints.get('product_handle') or '').strip()
        if handle:checks.append(('handle=%s',(handle,)))
        url=str(hints.get('product_url') or '').strip()
        if url:
            # Canonical index equality only; a foreign URL is never reduced to a handle.
            checks.append(('online_store_url=%s',(url,)))
        sku=str(hints.get('product_sku') or '').strip()
        if sku:checks.append(('shopify_product_id IN (SELECT shopify_product_id FROM shopify_variants WHERE sku=%s)',(sku,)))
        title=plain(hints.get('product_title'),500)
        if title:checks.append(("lower(trim(title))=lower(trim(%s))",(title,)))
        for clause,args in checks:
            rows=self.q('SELECT shopify_product_id,title,handle,image_url,online_store_url FROM shopify_products WHERE '+clause+' LIMIT 2',args)
            if len(rows)>1:return None
            if rows:return rows[0]
        return None
    def match_products(self,hints_list):
        """Batch exact import mapping: at most five index reads per 200 hints."""
        if len(hints_list)>200:raise ValueError('Resolve at most 200 product hints per batch.')
        fields='shopify_product_id,title,handle,image_url,online_store_url'
        ids=set();handles=set();urls=set();skus=set();titles=set()
        for hints in hints_list:
            identity=product_gid(hints.get('product_id'))
            if identity:ids.update((identity,identity.rsplit('/',1)[-1]))
            if hints.get('product_handle'):handles.add(hints['product_handle'])
            if hints.get('product_url'):urls.add(hints['product_url'])
            if hints.get('product_sku'):skus.add(hints['product_sku'])
            if hints.get('product_title'):titles.add(hints['product_title'].strip().lower())
        groups={k:{} for k in ('id','handle','url','sku','title')}
        for group,values,column in (('id',ids,'shopify_product_id'),('handle',handles,'handle'),('url',urls,'online_store_url'),('title',titles,'lower(trim(title))')):
            if not values:continue
            rows=self.q('SELECT '+fields+',match_key FROM (SELECT '+fields+','+column+' AS match_key,row_number() OVER(PARTITION BY '+column+' ORDER BY shopify_product_id) AS rn FROM shopify_products WHERE '+column+'=ANY(%s::text[])) candidates WHERE rn<=2',(list(values),))
            for row in rows:groups[group].setdefault(row['match_key'],[]).append(row)
        if skus:
            rows=self.q('''SELECT shopify_product_id,title,handle,image_url,online_store_url,match_key FROM
              (SELECT matches.*,row_number() OVER(PARTITION BY match_key ORDER BY shopify_product_id) AS rn FROM
                (SELECT DISTINCT p.shopify_product_id,p.title,p.handle,p.image_url,p.online_store_url,v.sku AS match_key
                 FROM shopify_variants v JOIN shopify_products p ON p.shopify_product_id=v.shopify_product_id WHERE v.sku=ANY(%s::text[])) matches) ranked WHERE rn<=2''',(list(skus),))
            for row in rows:groups['sku'].setdefault(row['match_key'],[]).append(row)
        result=[]
        for hints in hints_list:
            identity=product_gid(hints.get('product_id'));choices=[]
            if identity:
                candidates=groups['id'].get(identity,[])+groups['id'].get(identity.rsplit('/',1)[-1],[])
                choices.append(candidates)
            for group,key in (('handle','product_handle'),('url','product_url'),('sku','product_sku'),('title','product_title')):
                value=hints.get(key) or '';value=value.strip().lower() if group=='title' else value
                if value:choices.append(groups[group].get(value,[]))
            matched=None
            for candidates in choices:
                if candidates:
                    if len(candidates)==1:matched=candidates[0]
                    break
            result.append(matched)
        return result
    def import_one(self,conn,item,product):
        metadata={'product_hints':item.get('product_hints',{}),'imported_reply':bool(item.get('merchant_reply')),'date_known':bool(item.get('created_at'))}
        pid=product_gid(product['shopify_product_id']) if product else None
        value=(item['source'],item.get('source_review_id'),item.get('source_store_id',''),pid,
          product.get('title','') if product else item.get('product_hints',{}).get('product_title',''),
          product.get('handle','') if product else '',product.get('image_url','') if product else '',product.get('online_store_url','') if product else '',
          item['reviewer_name'],item.get('reviewer_email_hash'),item['rating'],item['title'],item['body'],item.get('created_at') or now(),
          item['status'],item.get('source_verified',False),item.get('merchant_reply',''),json.dumps(metadata),item['dedupe_key'])
        row=conn.execute('''INSERT INTO sc_reviews(source,source_review_id,source_store_id,product_id,product_title,product_handle,product_image,product_url,
         reviewer_name,reviewer_email_hash,rating,title,body,created_at,status,source_verified,merchant_reply,source_metadata,dedupe_key)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING RETURNING id''',value).fetchone()
        if not row and item.get('source_review_id'):
            # Source refresh can update its own content, but local moderation,
            # mapping, reply and verification remain authoritative.
            conn.execute('''UPDATE sc_reviews SET rating=%s,title=%s,body=%s,source_verified=%s,updated_at=now(),
              status=CASE WHEN moderated_at IS NULL THEN %s ELSE status END
              WHERE source=%s AND source_store_id=%s AND source_review_id=%s''',
              (item['rating'],item['title'],item['body'],item.get('source_verified',False),item['status'],item['source'],item.get('source_store_id',''),item['source_review_id']))
        return bool(row)
    def moderate(self,user,identity,status=None,reply=None,product=None):
        require(user);identity=str(uuid.UUID(str(identity)))
        if status is not None and status not in STATUSES:raise ValueError('Invalid review status.')
        reply=plain(reply,3000) if reply is not None else None
        mapped=self.match_product({'product_id':product}) if product else None
        if product and not mapped:raise ValueError('Choose an exact indexed Shopify product.')
        with self.db() as conn:
            row=conn.execute('SELECT * FROM sc_reviews WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row:raise ValueError('Review not found.')
            if status:conn.execute('UPDATE sc_reviews SET status=%s,moderated_at=now(),updated_at=now() WHERE id=%s',(status,identity))
            if reply is not None:conn.execute('UPDATE sc_reviews SET merchant_reply=%s,merchant_reply_at=now(),reply_actor=%s,updated_at=now() WHERE id=%s',(reply,actor(user),identity))
            if mapped:
                conn.execute('''UPDATE sc_reviews SET product_id=%s,product_title=%s,product_handle=%s,product_image=%s,product_url=%s,
                  verified_purchase=false,customer_id=NULL,order_id=NULL,mapping_resolved_at=now(),updated_at=now() WHERE id=%s''',
                  (product_gid(mapped['shopify_product_id']),mapped['title'],mapped['handle'],mapped.get('image_url') or '',mapped.get('online_store_url') or '',identity))
            conn.execute('INSERT INTO sc_review_audit(review_id,actor,action) VALUES(%s,%s,%s)',(identity,actor(user),'mapping' if mapped else 'reply' if reply is not None else status))
        from reviews_public_cache import CACHE
        CACHE.invalidate()
    def enqueue_import(self,user,source,label,items,invalid=0):
        require(user)
        if source not in ('csv','judgeme') or len(items)>10000:raise ValueError('Import at most 10,000 reviews per file.')
        return self.q('''INSERT INTO sc_review_imports(source,label,payload,total,invalid,actor) VALUES(%s,%s,%s::jsonb,%s,%s,%s) RETURNING *''',
          (source,plain(label,200),json.dumps(items),len(items),invalid,actor(user)),True)
    def enqueue_sync(self,user):
        require(user)
        with self.db() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72634193)')
            row=conn.execute("SELECT id FROM sc_review_imports WHERE source='judgeme_api' AND status IN ('PENDING','RUNNING') ORDER BY created_at LIMIT 1").fetchone()
            return row or conn.execute("INSERT INTO sc_review_imports(source,label,actor) VALUES('judgeme_api','Judge.me',%s) RETURNING id",(actor(user),)).fetchone()
    def imports(self):return self.q('SELECT id,label,status,total,cursor,imported,duplicates,invalid,unresolved,error_code,created_at FROM sc_review_imports ORDER BY created_at DESC LIMIT 10')
