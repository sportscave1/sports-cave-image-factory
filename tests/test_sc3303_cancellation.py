from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import MagicMock, patch

from scripts import repair_sc3303 as repair
from edition_cancellation import require_certificate_allocation
from tests.edition_db_fixture import connect


def shopify():
    return dict(id=repair.ORDER,name='#SC3303',currentSubtotalLineItemsQuantity=0,
      currentTotalPriceSet={'shopMoney':{'amount':'0.00'}},fulfillments=[],
      lineItems={'pageInfo':{'hasNextPage':False},'nodes':[dict(id=repair.LINE,currentQuantity=0,
        unfulfilledQuantity=0,product={'id':repair.PRODUCT})]},
      fulfillmentOrders={'pageInfo':{'hasNextPage':False},'nodes':[dict(status='CLOSED',requestStatus='UNSUBMITTED')]})


class EvidenceTests(unittest.TestCase):
    def test_live_evidence_is_required_and_fresh(self):
        now=datetime.now(timezone.utc)
        repair.validate_shopify(shopify(),now)
        with self.assertRaisesRegex(ValueError,'stale'):
            repair.validate_shopify(shopify(),now-timedelta(minutes=3))
        for key,value in [('id','other'),('currentSubtotalLineItemsQuantity',1),('fulfillments',[{'status':'SUCCESS'}])]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                repair.validate_shopify({**shopify(),key:value},now)
        for status,request in [('OPEN','UNSUBMITTED'),('CLOSED','ACCEPTED')]:
            data=shopify();data['fulfillmentOrders']['nodes'][0].update(status=status,requestStatus=request)
            with self.assertRaisesRegex(ValueError,'fulfilment work'):
                repair.validate_shopify(data,now)

    def test_generation_checks_database_not_stale_assignment(self):
        for order,unit in [(None,None),({'cancelled_at':'now'},None),({'cancelled':True},None),
                           ({'cancelled':False},{'allocation_valid':False,'status':'cancelled'})]:
            cur=MagicMock();cur.fetchone.side_effect=[order,unit]
            with self.subTest(order=order,unit=unit),self.assertRaises(ValueError):
                require_certificate_allocation(cur,{'id':678,'shopify_order_id':repair.ORDER,'status':'assigned'})


@unittest.skipUnless(os.getenv('SC3303_TEST_SQL')=='1','Disposable SC3303 SQL required')
class TransactionTests(unittest.TestCase):
    actor='11111111-1111-4111-8111-111111111111'

    def setUp(self):
        self.connection=connect();self.connection.__enter__();self.cur=self.connection.cursor()
        self.addCleanup(self.connection.__exit__,ValueError,ValueError('test rollback'),None)
        c=self.cur
        c.execute("INSERT INTO os_users VALUES(%s,'admin',true,'active')",(self.actor,))
        c.execute("INSERT INTO edition_products(id,shopify_product_id,shopify_product_gid,shopify_handle,active_edition_run_id) VALUES(727,%s,%s,%s,%s)",
                  (repair.PRODUCT,repair.PRODUCT,repair.HANDLE,repair.RUN))
        c.execute("INSERT INTO edition_runs(id,edition_product_id,shopify_product_id,shopify_handle,edition_name,edition_total,next_edition_number,status) VALUES(%s,727,%s,%s,'Original Edition',100,1,'active')",
                  (repair.RUN,repair.PRODUCT,repair.HANDLE))
        for number in range(1,20):
            order=repair.ORDER if number==19 else 'gid://shopify/Order/'+str(9000+number)
            line=repair.LINE if number==19 else 'gid://shopify/LineItem/'+str(8000+number)
            name={17:'#SC3301',18:'#SC3302',19:'#SC3303'}.get(number,'#SYNTHETIC'+str(number))
            c.execute('INSERT INTO shopify_orders(shopify_order_id,order_name) VALUES(%s,%s)',(order,name))
            c.execute('SELECT allocate_edition_line_units_atomic(%s,%s,%s,%s,1,%s,%s,%s)',
                      ('shopify',order,line,repair.PRODUCT,order,name,line))
        c.execute("SELECT set_config('sports_cave.edition_repair_key','synthetic-fixture',true)")
        c.execute('UPDATE edition_orders SET id=678 WHERE shopify_order_id=%s',(repair.ORDER,))
        c.execute('INSERT INTO shopify_order_lines(shopify_order_id,shopify_line_item_id,shopify_product_id,quantity,assignment_status) VALUES(%s,%s,%s,1,\'Assigned\')',
                  (repair.ORDER,repair.LINE,repair.PRODUCT))
        c.execute('INSERT INTO shopify_orders(shopify_order_id,order_name) VALUES(\'gid://shopify/Order/3304\',\'#SC3304\')')
        c.execute("INSERT INTO edition_products(id,shopify_handle,sold_count,remaining_count,next_edition_number) VALUES(999,'unrelated-art',9,91,10)")
        c.execute("SELECT set_config('sports_cave.edition_repair_key','',true)")

    def apply(self):
        return repair.apply(self.cur,shopify(),datetime.now(timezone.utc),self.actor)

    def test_cancelled_allocation_is_excluded_from_every_search_branch(self):
        import supabase_backend as backend
        self.cur.execute('ALTER TABLE edition_orders ADD COLUMN product_handle text')
        self.cur.execute("UPDATE edition_orders SET customer_name='Heath Morgan' WHERE id=678")
        self.apply()

        def ids(search, history=False):
            connection = MagicMock()
            capture = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
            with patch.object(backend, 'ensure_schema'), patch.object(backend, 'connect', return_value=connection):
                backend.list_edition_orders(search=search, include_cancelled=history)
            sql, params = capture.execute.call_args.args
            where = sql[sql.index('WHERE '):sql.index('ORDER BY COALESCE')]
            self.cur.execute('SELECT eo.id FROM edition_orders eo LEFT JOIN shopify_orders o '
                             'ON o.shopify_order_id=eo.shopify_order_id ' + where, params[:-1])
            return {row['id'] for row in self.cur.fetchall()}

        for search in ('', '#SC3303', 'SC3303', '19', '019', 'Heath Morgan', repair.HANDLE):
            with self.subTest(search=search):
                self.assertNotIn(678, ids(search))
        self.assertEqual(ids('#SC3303', history=True), {678})
        self.assertTrue(ids('#SC3302'))

    def test_exact_one_decrement_history_replay_and_next_customer(self):
        c=self.cur
        c.execute('SELECT * FROM edition_products WHERE id=999');other=c.fetchone()
        c.execute("SELECT * FROM shopify_orders WHERE order_name='#SC3304'");sc3304=c.fetchone()
        self.assertEqual(self.apply()['next'],19)
        c.execute('SELECT status,allocation_valid,edition_number FROM edition_orders WHERE id=678')
        self.assertEqual(c.fetchone(),dict(status='cancelled',allocation_valid=False,edition_number=19))
        c.execute('SELECT count(*) AS n FROM edition_repair_archive');self.assertEqual(c.fetchone()['n'],1)
        c.execute('SELECT * FROM edition_products WHERE id=999');self.assertEqual(c.fetchone(),other)
        c.execute("SELECT * FROM shopify_orders WHERE order_name='#SC3304'");self.assertEqual(c.fetchone(),sc3304)
        # Production commit clears these transaction-local repair/allocator flags.
        for setting in ('sports_cave.cursor_action','sports_cave.atomic_edition_allocation','sports_cave.edition_repair_key'):
            c.execute("SELECT set_config(%s,'',true)",(setting,))
        # Older Shopify payload cannot clear the local cancellation or revive lines.
        c.execute("UPDATE shopify_orders SET cancelled_at=NULL,fulfillment_status='UNFULFILLED',total_price='339.00',raw_json='{}' WHERE shopify_order_id=%s",(repair.ORDER,))
        c.execute('SELECT cancelled_at,fulfillment_status,total_price FROM shopify_orders WHERE shopify_order_id=%s',(repair.ORDER,))
        row=c.fetchone();self.assertTrue(row['cancelled_at']);self.assertEqual(row['fulfillment_status'],'CANCELLED');self.assertEqual(row['total_price'],'0.00')
        c.execute("UPDATE shopify_order_lines SET quantity=1,assignment_status='Assigned' WHERE shopify_order_id=%s",(repair.ORDER,))
        c.execute('SELECT quantity,assignment_status FROM shopify_order_lines WHERE shopify_order_id=%s',(repair.ORDER,))
        self.assertEqual(c.fetchone(),dict(quantity=0,assignment_status='Cancelled'))
        for sql,args in [
            ('SELECT allocate_edition_line_units_atomic(%s,%s,%s,%s,1,%s,%s,%s)',('shopify',repair.ORDER,repair.LINE,repair.PRODUCT,repair.ORDER,'#SC3303',repair.LINE)),
            ("INSERT INTO certificates(edition_order_id,shopify_order_id) VALUES('678',%s)",(repair.ORDER,)),
            ("INSERT INTO prodigi_dispatch_rows(row_id,shopify_order_id) VALUES('blocked',%s)",(repair.ORDER,)),
            ("UPDATE edition_orders SET status='assigned',allocation_valid=true WHERE id=678",()),
            ('UPDATE edition_products SET next_edition_number=20 WHERE id=727',()),
        ]:
            c.execute('SAVEPOINT rejected')
            with self.subTest(sql=sql),self.assertRaises(RuntimeError):c.execute(sql,args)
            c.execute('ROLLBACK TO SAVEPOINT rejected')
        with self.assertRaisesRegex(ValueError,'already recorded'):self.apply()
        c.execute("INSERT INTO shopify_orders(shopify_order_id) VALUES('gid://shopify/Order/999999')")
        c.execute('SELECT allocate_edition_line_units_atomic(%s,%s,%s,%s,1,%s,%s,%s) AS result',
                  ('shopify','gid://shopify/Order/999999','gid://shopify/LineItem/999999',repair.PRODUCT,
                   'gid://shopify/Order/999999','#NEXT','gid://shopify/LineItem/999999'))
        self.assertEqual(c.fetchone()['result']['allocation']['edition_number'],19)
        c.execute('SELECT sold_count,remaining_count,next_edition_number FROM edition_products WHERE id=727')
        self.assertEqual(c.fetchone(),dict(sold_count=19,remaining_count=81,next_edition_number=20))

    def test_conflicts_abort_before_mutation(self):
        c=self.cur
        conflicts=[("INSERT INTO certificates(edition_order_id,shopify_order_id) VALUES('678',%s)",(repair.ORDER,)),
                   ("INSERT INTO auto_edition_jobs VALUES('pending','{\"edition_order_id\":\"678\"}')",()),
                   ("INSERT INTO prodigi_dispatch_rows(row_id,shopify_order_id) VALUES('sent',%s)",(repair.ORDER,)),
                   ("UPDATE edition_products SET next_edition_number=21 WHERE id=727",())]
        for sql,args in conflicts:
            c.execute('SAVEPOINT conflict')
            c.execute(sql,args)
            with self.subTest(sql=sql),self.assertRaises(ValueError):self.apply()
            c.execute('SELECT allocation_valid,status FROM edition_orders WHERE id=678')
            self.assertEqual(c.fetchone(),dict(allocation_valid=True,status='assigned'))
            c.execute('SELECT count(*) AS n FROM edition_repair_audits');self.assertEqual(c.fetchone()['n'],0)
            c.execute('ROLLBACK TO SAVEPOINT conflict')

    def test_failure_in_override_rolls_back_every_change(self):
        c=self.cur
        c.execute('SAVEPOINT entire_repair')
        with self.assertRaisesRegex(RuntimeError,'administrator'):
            repair.apply(c,shopify(),datetime.now(timezone.utc),'22222222-2222-4222-8222-222222222222')
        c.execute('ROLLBACK TO SAVEPOINT entire_repair')
        c.execute('SELECT allocation_valid,status FROM edition_orders WHERE id=678')
        self.assertEqual(c.fetchone(),dict(allocation_valid=True,status='assigned'))
        c.execute('SELECT next_edition_number,sold_count,remaining_count FROM edition_products WHERE id=727')
        self.assertEqual(c.fetchone(),dict(next_edition_number=20,sold_count=19,remaining_count=81))
        for table in ('edition_repair_archive','edition_repair_audits','edition_allocation_tombstones','edition_order_sync_locks'):
            c.execute('SELECT count(*) AS n FROM '+table);self.assertEqual(c.fetchone()['n'],0)


if __name__=='__main__':unittest.main()
