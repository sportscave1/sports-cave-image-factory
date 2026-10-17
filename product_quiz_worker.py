"""Opt-in reconciliation using existing mirror events plus periodic read-only reads."""
import logging
import os
import time

SELLING_QUERY='''query SportsCaveQuizSellingPolicy($ids:[ID!]!) {
  nodes(ids:$ids) { ... on Product { id
    variants(first:100) { pageInfo { hasNextPage } nodes {
      inventoryQuantity inventoryPolicy inventoryItem { tracked }
    } }
  } }
}'''


def selling_policy(product):
    connection=product.get('variants') or {}
    variants=connection.get('nodes') or []
    unknown=False
    for variant in variants:
        tracked=(variant.get('inventoryItem') or {}).get('tracked')
        policy=variant.get('inventoryPolicy')
        quantity=variant.get('inventoryQuantity')
        if tracked is False or policy=='CONTINUE' or tracked is True and policy=='DENY' and type(quantity) is int and quantity>0: return True
        if tracked is None or policy not in {'CONTINUE','DENY'} or type(quantity) is not int: unknown=True
    if unknown or connection.get('pageInfo',{}).get('hasNextPage'): return None
    return False


def enabled(*,role='worker'):
    return os.getenv('PRODUCT_QUIZ_ENABLED')=='true' and os.getenv('PRODUCT_QUIZ_RECONCILER_HOST','app')==role


_APP_THREAD=None


def start_app_reconciler():
    """Reuse the existing app's private storage access; never copy credentials."""
    global _APP_THREAD
    if not enabled(role='app'): return False
    if _APP_THREAD is not None and _APP_THREAD.is_alive(): return True
    import atexit
    import threading
    stop=threading.Event()
    _APP_THREAD=threading.Thread(target=run,args=(stop,'app'),name='product-quiz-catalogue',daemon=True)
    atexit.register(stop.set)
    _APP_THREAD.start()
    return True


def refresh_mirror(store):
    """Recover missed product events; never calls allocation or Shopify mutations."""
    from shopify_sync import iter_catalog_pages,graphql_request,get_config
    from supabase_backend import _upsert_shopify_product_display_row
    seen=set()
    config=dict(get_config())
    config['max_products']=100000
    last_page=None
    # An empty search includes archived/draft rows, unlike the active-only operational sync.
    for page in iter_catalog_pages(search='',page_size=5,config=config):
        last_page=page
        policies={}
        ids=[p['shopify_product_id'] for p in page['products']]
        for offset in range(0,len(ids),3):
            data,_=graphql_request(SELLING_QUERY,variables={'ids':ids[offset:offset+3]},config=config)
            policies.update({p['id']:selling_policy(p) for p in data.get('nodes') or [] if p})
        with store.db() as conn:
            with conn.cursor() as cur:
                for product in page['products']:
                    product['quiz_sellable']=policies.get(product['shopify_product_id'])
                    _upsert_shopify_product_display_row(cur,product)
                    seen.add(product['shopify_product_id'])
    if last_page and last_page.get('has_next_page'):
        raise ValueError('Catalogue listing did not reach its end; previous ID snapshot preserved')
    # Tombstone deleted products only after a successful complete listing.
    # Do not alter the shared mirror: private exclusions disappear if an ID reappears.
    store.put_state('present_product_ids',sorted(seen))


def cycle(store,assets,*,reconcile=False):
    from product_quiz_publish import sync,now
    try:
        if reconcile: refresh_mirror(store)
        rows=store.catalogue_rows()
        present=store.get_state('present_product_ids')
        if present is not None: rows=[r for r in rows if r['shopify_product_id'] in present]
        sync(store,assets,rows=rows)
        store.q("DELETE FROM crm_runtime_state WHERE left(key,19)='product_quiz/event/' AND updated_at<now()-interval '90 days'")
    except Exception:
        status=store.get_state('catalogue_status',{})
        store.put_state('catalogue_status',{**status,'error':'Catalogue sync failed. Last published catalogue preserved; retry reconciliation.','last_attempt':now()})
        raise


def run(stop,role='worker'):
    if not enabled(role=role): return
    from product_quiz_store import QuizStore
    from product_quiz_publish import Assets
    next_reconcile=0
    while not stop.is_set():
        try:
            cycle(QuizStore(),Assets(),reconcile=time.monotonic()>=next_reconcile)
            if time.monotonic()>=next_reconcile: next_reconcile=time.monotonic()+3600
        except Exception as exc: logging.getLogger(__name__).warning('product_quiz_sync_failed type=%s',type(exc).__name__)
        stop.wait(60)
