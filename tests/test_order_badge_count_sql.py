"""Execute the production badge aggregate on disposable PostgreSQL fixtures."""
import json
from unittest.mock import patch

import supabase_backend as db
from tests.test_auto_editions_jobs import database


def test_badge_counts_distinct_unfinished_orders_with_aliases_and_closed_history(database):
    _, sql = database
    sql.execute('''CREATE TEMP TABLE shopify_orders(shopify_order_id text,order_name text,
        financial_status text,cancelled_at timestamptz,fulfillment_status text,raw_json jsonb);
        CREATE TEMP TABLE shopify_order_lines(shopify_order_id text,shopify_line_item_id text,quantity int);
        CREATE TEMP TABLE prodigi_dispatch_rows(shopify_line_item_id text,prodigi_status text,
        updated_at timestamptz,submitted_at timestamptz)''')
    for order in ('first','second','refunded','cancelled','removed','fulfilled'):
        payload = {'_orders_refund': {'blocked': True}} if order == 'refunded' else (
            {'_orders_refund': {'line_current_quantities': {'removed':0}}} if order == 'removed' else {})
        sql.execute('INSERT INTO shopify_orders VALUES (%s,%s,%s,%s,%s,%s::jsonb)',
            (order,order,'PAID','2026-11-21T00:00:00Z' if order=='cancelled' else None,
             'FULFILLED' if order=='fulfilled' else 'UNFULFILLED',json.dumps(payload)))
        sql.execute('INSERT INTO shopify_order_lines VALUES (%s,%s,1)', (order,order))
    # Numeric/GID representations and multi-unit rows must not inflate orders.
    sql.execute("INSERT INTO shopify_order_lines VALUES ('first','gid://shopify/LineItem/first',1),('second','second-done',3)")
    sql.execute("INSERT INTO prodigi_dispatch_rows VALUES ('gid://shopify/LineItem/second-done','Complete',now(),now())")
    sql.execute("""INSERT INTO shopify_orders SELECT 'closed-'||n,'closed','PAID',NULL,'UNFULFILLED','{}'::jsonb
        FROM generate_series(1,1000) n""")
    sql.execute("INSERT INTO shopify_order_lines SELECT shopify_order_id,shopify_order_id,1 FROM shopify_orders WHERE order_name='closed'")
    sql.execute("INSERT INTO prodigi_dispatch_rows SELECT shopify_order_id,'Complete',now(),now() FROM shopify_orders WHERE order_name='closed'")
    def summary():
        with patch.object(db, '_run_read_operation', side_effect=lambda operation, read: (read(sql), {})):
            return db.get_order_action_summary()
    assert summary() == {'action_required_count':2, 'badge_label':'2'}
    sql.execute("INSERT INTO prodigi_dispatch_rows VALUES ('first','Complete',now(),now())")
    assert summary() == {'action_required_count':1, 'badge_label':'1'}
    sql.execute("INSERT INTO prodigi_dispatch_rows VALUES ('second','Complete',now(),now())")
    assert summary() == {'action_required_count':0, 'badge_label':''}
