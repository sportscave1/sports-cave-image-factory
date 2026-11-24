"""One bounded import chunk per existing CRM worker tick; no email permissions."""
import logging
from reviews_store import ReviewsStore

def tick(store=None):
    store=store or ReviewsStore()
    from reviews_media import tick_media
    tick_media(store)
    from reviews_reward_delivery import tick as tick_reward
    try:tick_reward(store)
    except Exception:logging.getLogger(__name__).warning('review_reward_cycle_unavailable')
    # Claim under a short transaction; network work is outside the database lock.
    with store.db() as conn:
        row=conn.execute("""SELECT * FROM sc_review_imports WHERE status='PENDING' OR
          (status='RUNNING' AND lease_until<now()) ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if not row:return None
        claim=conn.execute("UPDATE sc_review_imports SET status='RUNNING',lease_until=now()+interval '60 seconds',attempts=attempts+1,updated_at=now() WHERE id=%s RETURNING attempts",(row['id'],)).fetchone()['attempts']
    try:
        invalid=0;skipped=0
        if row['source'] not in ('csv','judgeme'):
            store.q("UPDATE sc_review_imports SET status='FAILED',lease_until=NULL,error_code='provider_retired',updated_at=now() WHERE id=%s",(row['id'],))
            return row['id']
        items=row['payload'][row['cursor']:row['cursor']+100];done=row['cursor']+len(items)>=row['total'];raw=items
        products=store.match_products([item.get('product_hints',{}) for item in items])
        inserted=duplicate=unresolved=0
        with store.db() as conn:
            locked=conn.execute('SELECT * FROM sc_review_imports WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
            if locked['attempts']!=claim or locked['status']!='RUNNING':return None
            for item,product in zip(items,products):
                result=store.import_one(conn,item,product)
                inserted+=int(result);duplicate+=int(not result);unresolved+=int(result and not product and item.get('review_type','PRODUCT')=='PRODUCT')
            conn.execute("""UPDATE sc_review_imports SET cursor=cursor+%s,imported=imported+%s,duplicates=duplicates+%s,
              unresolved=unresolved+%s,invalid=invalid+%s,skipped=skipped+%s,total=total,
              provider_page=provider_page+1,status=%s,lease_until=NULL,error_code=NULL,updated_at=now() WHERE id=%s""",
              (len(raw),inserted,duplicate,unresolved,invalid,skipped,'COMPLETED' if done else 'PENDING',row['id']))
        logging.getLogger(__name__).info('review_import job_id=%s processed=%s imported=%s duplicates=%s unresolved=%s',row['id'],len(raw),inserted,duplicate,unresolved)
        return row['id']
    except Exception as exc:
        store.q("UPDATE sc_review_imports SET status=%s,lease_until=NULL,error_code='source_unavailable',updated_at=now() WHERE id=%s AND attempts=%s",('FAILED' if claim>=3 else 'PENDING',row['id'],claim))
        logging.getLogger(__name__).warning('review_import_failed job_id=%s exception_type=%s',row['id'],type(exc).__name__)
        return None
