"""Namespaced persistence on the OS's existing private runtime-state table."""
from contextlib import contextmanager
from collections import Counter
from copy import deepcopy
from datetime import datetime
import json
from product_quiz import PREFIX, DEFAULT, validate
from crm_store import Store


class QuizStore(Store):
    def get_state(self, name, fallback=None):
        row=self.q('SELECT value FROM crm_runtime_state WHERE key=%s',(PREFIX+name,),True)
        return row['value'] if row is not None else deepcopy(fallback)

    def put_state(self, name, value):
        self.set_state(PREFIX+name,value)

    @contextmanager
    def lock(self):
        # Dedicated connection holds the session lock across independent state transactions.
        with self.db() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('product-quiz-publisher',0))")
            yield

    def draft(self):
        return self.get_state('draft',{'revision':0,'config':DEFAULT})

    def save(self, config, revision):
        config=validate(config)
        with self.lock():
            current=self.draft()
            if current['revision'] != revision: raise ValueError('Another editor saved changes. Reload before saving.')
            result={'revision':revision+1,'config':config}
            self.put_state('draft',result)
            return result

    def catalogue_rows(self):
        from supabase_backend import list_edition_products_read_only

        def product_id(row):
            number=str(row.get('shopify_product_gid') or row.get('shopify_product_id') or '').rsplit('/',1)[-1]
            return 'gid://shopify/Product/'+number if number.isascii() and number.isdigit() else ''

        ledger=[]
        while True:
            page=list_edition_products_read_only(limit=1000,offset=len(ledger))
            ledger.extend(page)
            if len(page)<1000:
                break
        identities=Counter(pid for row in ledger if (pid:=product_id(row)))
        if not identities:
            return []
        mirror_ids=[*identities,*(pid.rsplit('/',1)[-1] for pid in identities)]
        mirror={}
        for row in self.q('''SELECT shopify_product_id,shopify_product_gid,title,handle,status,
                            image_url,online_store_url,COALESCE(raw_json,raw) AS raw_json,synced_at
                            FROM shopify_products
                            WHERE shopify_product_id=ANY(%s) OR shopify_product_gid=ANY(%s)
                            ORDER BY synced_at NULLS FIRST''',(mirror_ids,mirror_ids)):
            mirror[product_id(row)]=row
        snapshot=self.get_state('present_product_ids')
        cutoff=datetime.fromisoformat(snapshot['started_at']) if isinstance(snapshot,dict) else None
        present=set(snapshot['ids']) if cutoff else set()
        rows=[]
        for entry in ledger:
            pid=product_id(entry)
            if not pid:
                continue
            product=mirror.get(pid,{})
            next_number=entry['next_edition_number']
            total=entry['edition_total']
            synced_at=product.get('synced_at')
            rows.append({
                **product, 'shopify_product_id':pid,
                'title':entry.get('product_title') or product.get('title'),
                'edition_identity_count':identities[pid],
                'edition':{
                    'closed':not entry['active'],
                    'exhausted':entry['sold_out'] or entry['remaining_count']==0 or next_number>total,
                    'blocked':entry.get('allocation_blocked',False),
                    'deleted':bool(cutoff and pid not in present and (not synced_at or synced_at<cutoff)),
                    'next_number':next_number, 'total':total,
                },
            })
        return rows

    def event(self, event):
        return bool(self.q('''INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
          ON CONFLICT(key) DO NOTHING RETURNING key''',(PREFIX+'event/'+event['event_id'],json.dumps(event)),True))

    def report(self):
        return self.q('''SELECT value->>'type' AS event,value->>'step' AS question,
          value->>'source' AS source,value->>'version' AS version,count(*) AS count,
          count(DISTINCT value->>'session_id') AS sessions
          FROM crm_runtime_state WHERE left(key,19)='product_quiz/event/'
          AND updated_at>now()-interval '30 days' GROUP BY 1,2,3,4 ORDER BY 1,2''')
