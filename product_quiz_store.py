"""Namespaced persistence on the OS's existing private runtime-state table."""
from contextlib import contextmanager
from copy import deepcopy
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
        # Identity join uses stable IDs, never a filename/title match. No PSD scan.
        rows=self.q('''SELECT sp.shopify_product_id,sp.title,sp.handle,sp.status,sp.image_url,
          sp.online_store_url,sp.raw_json,
          ep.edition_total,ep.next_edition_number,ep.active,ep.is_active,ep.edition_status,
          ep.sold_out,ep.is_sold_out,ep.remaining_count,
          count(ep.id) OVER (PARTITION BY sp.shopify_product_id) AS edition_identity_count
          FROM shopify_products sp LEFT JOIN edition_products ep
          ON REPLACE(COALESCE(NULLIF(ep.shopify_product_gid,''),ep.shopify_product_id),'gid://shopify/Product/','')
             =REPLACE(sp.shopify_product_id,'gid://shopify/Product/','')
          ORDER BY sp.shopify_product_id''')
        for r in rows:
            r['edition']={'closed':r.get('active') is False or r.get('is_active') is False or any(s in str(r.get('edition_status') or '').casefold() for s in ('archiv','expir','inactive','disabled','complet','sold','ended','closed')),
                          'exhausted':bool(r.get('sold_out') or r.get('is_sold_out') or r.get('remaining_count') == 0 or (r.get('edition_total') and r.get('next_edition_number') and int(r['next_edition_number'])>int(r['edition_total'])))}
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
