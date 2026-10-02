"""One bounded import chunk per existing CRM worker tick; no email permissions."""
import json
import logging
from reviews_import import JudgeMe
from reviews_store import ReviewsStore

def tick(store=None,provider=None):
    store=store or ReviewsStore();provider=provider or JudgeMe()
    # Claim under a short transaction; network work is outside the database lock.
    with store.db() as conn:
        row=conn.execute("""SELECT * FROM sc_review_imports WHERE status='PENDING' OR
          (status='RUNNING' AND lease_until<now()) ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if not row:return None
        claim=conn.execute("UPDATE sc_review_imports SET status='RUNNING',lease_until=now()+interval '60 seconds',attempts=attempts+1,updated_at=now() WHERE id=%s RETURNING attempts",(row['id'],)).fetchone()['attempts']
    try:
        invalid=0
        if row['source']=='judgeme_api':
            raw=provider.page(row['provider_page']);items=[]
            for r in raw:
                try:items.append(provider.normalize(r))
                except (ValueError,TypeError):invalid+=1
            done=len(raw)<100
            if row['provider_page']>1000:raise ValueError('Provider pagination limit reached.')
        else:
            items=row['payload'][row['cursor']:row['cursor']+100];done=row['cursor']+len(items)>=row['total'];raw=items
        products=store.match_products([item.get('product_hints',{}) for item in items])
        inserted=duplicate=unresolved=0
        with store.db() as conn:
            locked=conn.execute('SELECT * FROM sc_review_imports WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
            if locked['attempts']!=claim or locked['status']!='RUNNING':return None
            for item,product in zip(items,products):
                result=store.import_one(conn,item,product)
                inserted+=int(result);duplicate+=int(not result);unresolved+=int(result and not product)
            conn.execute("""UPDATE sc_review_imports SET cursor=cursor+%s,imported=imported+%s,duplicates=duplicates+%s,
              unresolved=unresolved+%s,invalid=invalid+%s,total=CASE WHEN source='judgeme_api' THEN total+%s ELSE total END,
              provider_page=provider_page+1,status=%s,lease_until=NULL,error_code=NULL,updated_at=now() WHERE id=%s""",
              (len(raw),inserted,duplicate,unresolved,invalid,len(raw),'COMPLETED' if done else 'PENDING',row['id']))
            if row['source']=='judgeme_api':conn.execute("INSERT INTO sc_review_settings(key,value) VALUES('judgeme',%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",(json.dumps({'verified':True,'last_sync':__import__('crm_logic').now().isoformat()}),))
        logging.getLogger(__name__).info('review_import job_id=%s processed=%s imported=%s duplicates=%s unresolved=%s',row['id'],len(raw),inserted,duplicate,unresolved)
        return row['id']
    except Exception as exc:
        store.q("UPDATE sc_review_imports SET status=%s,lease_until=NULL,error_code='source_unavailable',updated_at=now() WHERE id=%s AND attempts=%s",('FAILED' if claim>=3 else 'PENDING',row['id'],claim))
        logging.getLogger(__name__).warning('review_import_failed job_id=%s exception_type=%s',row['id'],type(exc).__name__)
        return None
