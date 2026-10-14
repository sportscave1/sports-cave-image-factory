from auto_editions_priority import priority,refresh
from tests.test_auto_editions_onboarding import setup_queue
from tests.test_auto_editions_jobs import database


def test_commercial_order_and_defer():
    empty=dict(active=True,sales=0,outstanding=0,recent=0,advertised=False)
    assert priority(empty)[0]==0
    assert priority(empty,2)[0]==2
    assert priority(empty,10)[0]==10
    assert priority({**empty,'advertised':True})[0]==4
    assert priority({**empty,'sales':1})[0]==5
    assert priority({**empty,'sales':2})[0]==6
    assert priority({**empty,'outstanding':1})[0]==8
    assert priority({**empty,'active':False},2)[0]==0


def test_first_synced_order_promotes_deferred_without_allocating(database):
    queue,sql=setup_queue(database)
    sql.execute("CREATE TABLE edition_products(shopify_product_gid text,shopify_product_id text,shopify_handle text,is_active boolean,active boolean)")
    sql.execute("INSERT INTO edition_products VALUES('p','p','art',true,true)")
    sql.execute("CREATE TABLE shopify_order_lines(shopify_order_id text,shopify_product_id text,quantity int)")
    sql.execute("CREATE TABLE shopify_orders(shopify_order_id text,fulfillment_status text,financial_status text,cancelled_at timestamptz,created_at timestamptz,raw_json jsonb)")
    sql.execute("CREATE TABLE ads_product_mapping(ad_id text,product_handle text)")
    sql.execute("CREATE TABLE meta_ads(ad_id text,effective_status text)")
    queue.enqueue('p','f','admin',newly_linked=False)
    refresh(queue,'host');assert queue.claim('host') is None
    sql.execute("INSERT INTO shopify_orders VALUES('order','unfulfilled','paid',NULL,now(),'{}')")
    sql.execute("INSERT INTO shopify_order_lines VALUES('order','p',1)")
    refresh(queue,'host');row=queue.claim('host');assert row['priority']==8
    assert row['product_gid']=='p'
    queue.checkpoint('p',row['lease_token'],'host','Cloud Ready')
    refresh(queue,'host');assert queue.claim('host') is None


def test_prepare_now_preserves_approved_assets(database):
    queue,sql=setup_queue(database)
    queue.enqueue('p','f','admin',newly_linked=False)
    queue.prepare_now('p','admin');assert queue.claim('host')['priority']==10
