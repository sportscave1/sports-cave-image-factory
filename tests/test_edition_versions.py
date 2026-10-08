import json
import os
import unittest
import uuid
from unittest.mock import patch

import edition_versions as versions
import supabase_backend as backend
from tests.edition_db_fixture import connect


@unittest.skipUnless(os.getenv('EDITION_TEST_POSTGRES')=='1','Disposable edition SQL required')
class EditionVersionTests(unittest.TestCase):
    def q(self,sql,args=()):
        with connect() as conn,conn.cursor() as cur:
            cur.execute(sql,args);return cur.fetchall()

    def setUp(self):
        self.patch=patch.object(backend,'connect',connect);self.patch.start();self.addCleanup(self.patch.stop)
        self.kick=patch.object(versions,'kick');self.kick.start();self.addCleanup(self.kick.stop)
        self.actor=str(uuid.uuid4());self.old=str(uuid.uuid4());self.request=str(uuid.uuid4())
        self.handle='test-'+uuid.uuid4().hex;self.gid='gid://shopify/Product/'+str(uuid.uuid4().int)[:15]
        self.q("INSERT INTO os_users VALUES(%s,'admin',true,'active')",(self.actor,))
        self.product=self.q("INSERT INTO edition_products(shopify_product_gid,shopify_product_id,shopify_handle,product_title,active_edition_run_id,edition_name) VALUES(%s,%s,%s,'Revised artwork',%s,'Original') RETURNING id",(self.gid,self.gid,self.handle,self.old))[0]['id']
        self.q("INSERT INTO edition_runs(id,edition_product_id,shopify_product_id,shopify_handle,edition_name,edition_total,next_edition_number,status) VALUES(%s,%s,%s,%s,'Original',100,1,'active')",(self.old,self.product,self.gid,self.handle))

    def create(self,**changes):
        args=dict(expected_run=self.old,request_id=self.request,name='Updated design',start=5,total=100,reason='Artwork revised',actor_id=self.actor)
        args.update(changes)
        return versions.create(self.handle,**args)

    def allocate(self,order=None,quantity=1,created='now()'):
        order=order or str(uuid.uuid4().int)[:15]
        gid='gid://shopify/Order/'+order;line='gid://shopify/LineItem/'+order
        if created not in ('now()',"now()-interval '1 day'"):raise AssertionError('test timestamp only')
        self.q(f'INSERT INTO shopify_orders(shopify_order_id,created_at) VALUES(%s,{created}) ON CONFLICT DO NOTHING',(gid,))
        return [r['result'] for r in self.q('SELECT allocate_edition_line_units_atomic(%s,%s,%s,%s,%s,%s,%s,%s) AS result',('shopify',gid,line,self.gid,quantity,gid,'#TEST',line))]

    def activate(self,version):
        with connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT set_config('sports_cave.edition_version_action','activate',true)")
            cur.execute("UPDATE edition_runs SET status='active',activated_at=now() WHERE id=%s",(version['id'],))
            cur.execute('UPDATE edition_products SET active=true,is_active=true WHERE id=%s',(self.product,))

    def test_transition_preserves_allocations_certificates_and_zero_sales_at_five(self):
        allocation=self.allocate()[0]['allocation']
        self.q("INSERT INTO certificates(edition_order_id,certificate_file_url) VALUES(%s,'unchanged.pdf')",(str(allocation['id']),))
        before=self.q('SELECT * FROM edition_orders WHERE edition_run_id=%s',(self.old,))
        new=self.create()
        self.assertNotEqual(new['id'],self.old);self.assertEqual(new['status'],'pending_sync')
        self.assertEqual((new['starting_number'],new['next_edition_number'],new['sold_count']),(5,5,0))
        old=self.q('SELECT * FROM edition_runs WHERE id=%s',(self.old,))[0]
        self.assertEqual((old['status'],old['sold_count'],old['last_allocated_number']),('expired',1,1))
        self.assertEqual(before,self.q('SELECT * FROM edition_orders WHERE edition_run_id=%s',(self.old,)))
        self.assertEqual(self.q('SELECT certificate_file_url FROM certificates WHERE edition_order_id=%s',(str(allocation['id']),))[0]['certificate_file_url'],'unchanged.pdf')
        with self.assertRaisesRegex(RuntimeError,'disabled|not active'):self.allocate()
        self.activate(new)
        first=self.allocate()[0]['allocation']
        self.assertEqual(first['edition_number'],5);self.assertEqual(first['edition_run_id'],new['id'])
        self.assertIn(new['id'],first['edition_release_label'])
        self.assertEqual(self.q('SELECT sold_count FROM edition_products WHERE id=%s',(self.product,))[0]['sold_count'],1)

    def test_idempotency_stale_submission_permissions_and_replay(self):
        first=self.allocate('100000'+str(self.product))[0]
        new=self.create();self.assertEqual(self.create()['id'],new['id'])
        with self.assertRaisesRegex(RuntimeError,'different values'):self.create(start=6)
        with self.assertRaisesRegex(RuntimeError,'changed'):self.create(request_id=str(uuid.uuid4()))
        with self.assertRaisesRegex(RuntimeError,'administrator'):self.create(actor_id=str(uuid.uuid4()))
        replay=self.allocate('100000'+str(self.product))[0]
        self.assertFalse(replay['was_created']);self.assertEqual(first['allocation']['id'],replay['allocation']['id'])
        self.assertEqual(len(self.q('SELECT id FROM edition_runs WHERE edition_product_id=%s',(self.product,))),2)

    def test_expired_immutable_activation_guard_and_old_event_guard(self):
        new=self.create()
        with self.assertRaisesRegex(RuntimeError,'read-only'):self.q('UPDATE edition_runs SET next_edition_number=1 WHERE id=%s',(self.old,))
        with self.assertRaisesRegex(RuntimeError,'confirmation'):self.q("UPDATE edition_runs SET status='active' WHERE id=%s",(new['id'],))
        with self.assertRaisesRegex(RuntimeError,'pending Shopify'):self.q('UPDATE edition_products SET next_edition_number=6 WHERE id=%s',(self.product,))
        self.activate(new)
        with self.assertRaisesRegex(RuntimeError,'predates'):self.allocate(created="now()-interval '1 day'")
        allocated=self.allocate()[0]['allocation']
        with self.assertRaisesRegex(RuntimeError,'identity is immutable'):self.q('UPDATE edition_orders SET edition_run_id=%s WHERE id=%s',(self.old,allocated['id']))

    def test_pending_failure_and_verified_retry_use_same_version(self):
        new=self.create()
        with patch.object(versions,'ensure_disclosure'),patch.object(versions.shopify_sync,'sync_complete_product_edition_metafields',side_effect=RuntimeError('Rate limited')):
            with self.assertRaisesRegex(RuntimeError,'Rate limited'):backend.sync_product_edition_metafields(self.handle,ensure_schema_first=False)
        state=self.q('SELECT status,sync_error FROM edition_runs WHERE id=%s',(new['id'],))[0]
        self.assertEqual(state,{'status':'pending_sync','sync_error':'Rate limited'})
        with patch.object(versions,'ensure_disclosure'),patch.object(versions.shopify_sync,'sync_complete_product_edition_metafields',return_value={'metafields':[]}) as mirror:
            backend.sync_product_edition_metafields(self.handle,ensure_schema_first=False)
        self.assertTrue(mirror.call_args.kwargs['verify']);self.assertTrue(mirror.call_args.kwargs['compare'])
        self.assertEqual(mirror.call_args.args[0]['edition_sold_count'],0)
        self.assertEqual(mirror.call_args.args[0]['edition_remaining'],96)
        self.assertEqual(self.q('SELECT status FROM edition_runs WHERE id=%s',(new['id'],))[0]['status'],'active')
        self.assertEqual(len(self.q('SELECT id FROM edition_runs WHERE edition_product_id=%s',(self.product,))),2)

    def test_read_projection_does_not_block_new_number_on_old_allocations(self):
        self.allocate(quantity=8);new=self.create();self.activate(new)
        row=backend.list_edition_products_read_only(handles=[self.handle],limit=1)[0]
        self.assertFalse(row['allocation_blocked']);self.assertEqual(row['sold_count'],0)
        self.assertEqual(row['next_edition_number'],5)
        self.assertEqual(len(versions.archive(self.handle)),1)

    def test_null_revision_inputs_and_failed_transaction_leave_original_active(self):
        for changes in ({'reason':None},{'name':None},{'start':None},{'total':None},{'start':101}):
            with self.subTest(changes=changes),self.assertRaisesRegex(RuntimeError,'required'):
                self.create(**changes)
        self.assertEqual(self.q('SELECT status FROM edition_runs WHERE id=%s',(self.old,))[0]['status'],'active')
        self.assertEqual(len(self.q('SELECT id FROM edition_runs WHERE edition_product_id=%s',(self.product,))),1)

    def test_same_number_distinct_release_and_history_cannot_be_deleted(self):
        self.allocate(quantity=5);new=self.create();self.activate(new)
        self.allocate()
        rows=self.q('SELECT edition_run_id FROM edition_orders WHERE shopify_product_gid=%s AND edition_number=5',(self.gid,))
        self.assertEqual({r['edition_run_id'] for r in rows},{self.old,new['id']})
        with self.assertRaisesRegex(RuntimeError,'cannot be deleted'):
            self.q('DELETE FROM edition_runs WHERE id=%s',(self.old,))
        with self.assertRaisesRegex(RuntimeError,'immutable'):
            self.q("UPDATE edition_version_audit SET reason='erased' WHERE run_id=%s",(new['id'],))

    def test_reconcile_derived_baseline_does_not_invent_sales(self):
        self.allocate(quantity=2)
        self.q('UPDATE edition_runs SET allocation_baseline_sold_count=7 WHERE id=%s',(self.old,))
        next_number=versions.reconcile(self.handle,self.old,self.actor,'Correct derived baseline')
        self.assertEqual(next_number,3)
        state=self.q('SELECT sold_count,allocation_baseline_sold_count FROM edition_runs WHERE id=%s',(self.old,))[0]
        self.assertEqual(state,{'sold_count':2,'allocation_baseline_sold_count':0})

    def test_revised_release_rejects_unsafe_rewind_and_stale_editor(self):
        new=self.create();self.activate(new);self.allocate()
        with connect() as conn,conn.cursor() as cur:
            with self.assertRaisesRegex(ValueError,'conflict'):
                backend._update_edition_product_with_cursor(cur,self.handle,next_edition_number=5,
                    manual_next_number_override=True,expected_next_edition_number=6,expected_edition_run_id=new['id'])
        with connect() as conn,conn.cursor() as cur:
            with self.assertRaisesRegex(ValueError,'changed'):
                backend._update_edition_product_with_cursor(cur,self.handle,next_edition_number=7,
                    manual_next_number_override=True,expected_next_edition_number=6,expected_edition_run_id=self.old)
        with connect() as conn,conn.cursor() as cur:
            backend._update_edition_product_with_cursor(cur,self.handle,next_edition_number=7,
                manual_next_number_override=True,expected_next_edition_number=6,expected_edition_run_id=new['id'])
        self.assertEqual(self.q('SELECT next_edition_number,sold_count FROM edition_products WHERE id=%s',(self.product,))[0],
                         {'next_edition_number':7,'sold_count':1})

    def test_worker_recovery_and_backoff_survive_new_dispatcher(self):
        new=self.create()
        self.assertIn(self.handle,versions.pending())
        with patch.object(versions,'ensure_disclosure',side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError,'offline'):
                backend.sync_product_edition_metafields(self.handle,ensure_schema_first=False)
        self.assertNotIn(self.handle,versions.pending())
        self.q('UPDATE edition_runs SET sync_retry_at=now() WHERE id=%s',(new['id'],))
        with patch.object(versions,'ensure_disclosure'),patch.object(versions.shopify_sync,'sync_complete_product_edition_metafields',return_value={}):
            versions.resume_pending()
        self.assertEqual(self.q('SELECT status FROM edition_runs WHERE id=%s',(new['id'],))[0]['status'],'active')


if __name__=='__main__':unittest.main()
