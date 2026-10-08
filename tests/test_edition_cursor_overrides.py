import uuid
from unittest.mock import patch
from tests.test_edition_versions import EditionVersionTests
import edition_cursor_overrides as overrides
import supabase_backend as backend


class CursorOverrideTests(EditionVersionTests):
    def test_competing_edits_only_one_expected_cursor_wins(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(n):
            try:return self.override(n,expected=1)['next_number']
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[5,6]))
        self.assertEqual(sum(isinstance(r,int) for r in results),1)
        self.assertTrue(any('changed' in str(r) for r in results))

    def override(self,number,expected=None,ack=False,request=None,actor=None):
        if expected is None:
            expected=self.q('SELECT next_edition_number FROM edition_products WHERE id=%s',(self.product,))[0]['next_edition_number']
        return overrides.save(self.handle,run_id=self.old,expected_next=expected,next_number=number,
            request_id=request or str(uuid.uuid4()),actor_id=actor or self.actor,acknowledged=ack)

    def test_reuse_preserves_sales_certificates_and_order_identity(self):
        first=self.allocate('800'+str(self.product),quantity=5)
        self.q("INSERT INTO certificates(edition_order_id,certificate_file_url) VALUES(%s,'original.pdf')",(str(first[4]['allocation']['id']),))
        self.q('UPDATE edition_products SET sold_count=94,remaining_count=6,last_assigned_edition=94,next_edition_number=95 WHERE id=%s',(self.product,))
        self.q('UPDATE edition_runs SET next_edition_number=95,allocation_baseline_sold_count=89 WHERE id=%s',(self.old,))
        before=self.q('SELECT * FROM edition_orders WHERE edition_run_id=%s ORDER BY id',(self.old,))
        with self.assertRaisesRegex(RuntimeError,'DUPLICATE_ACK_REQUIRED'):self.override(5)
        result=self.override(5,ack=True)
        p=self.q('SELECT * FROM edition_products WHERE id=%s',(self.product,))[0]
        self.assertEqual((p['next_edition_number'],p['sold_count'],p['remaining_count']),(5,94,6))
        projection=backend.list_edition_products_read_only(handles=[self.handle],limit=1)[0]
        self.assertFalse(projection['allocation_blocked'])
        self.assertEqual(before,self.q('SELECT * FROM edition_orders WHERE edition_run_id=%s ORDER BY id',(self.old,)))
        new=self.allocate('900'+str(self.product))[0]['allocation']
        self.assertEqual((new['edition_number'],new['manual_override_id']),(5,result['id']))
        again=self.allocate('900'+str(self.product))[0]
        self.assertFalse(again['was_created']);self.assertEqual(new['id'],again['allocation']['id'])
        projection=backend.list_edition_products_read_only(handles=[self.handle],limit=1)[0]
        self.assertFalse(projection['allocation_blocked'])
        self.allocate(quantity=5)
        with self.assertRaisesRegex(RuntimeError,'limit|sold out|not active|disabled'):self.allocate()
        self.assertEqual(self.q('SELECT certificate_file_url FROM certificates WHERE edition_order_id=%s',(str(first[4]['allocation']['id']),))[0]['certificate_file_url'],'original.pdf')

    def test_override_idempotence_stale_editor_and_permissions(self):
        request=str(uuid.uuid4())
        a=self.override(5,expected=1,request=request)
        self.assertEqual(a,self.override(5,expected=1,request=request))
        with self.assertRaisesRegex(RuntimeError,'different values'):self.override(6,expected=1,request=request)
        with self.assertRaisesRegex(RuntimeError,'changed'):self.override(6,expected=1)
        with self.assertRaisesRegex(RuntimeError,'administrator'):self.override(6,actor=str(uuid.uuid4()))
        self.allocate()
        with self.assertRaisesRegex(RuntimeError,'changed'):self.override(7,expected=5)

    def test_reconciliation_cannot_change_override_and_new_release_clears_it(self):
        self.override(5)
        for table,identifier in [('edition_products',self.product),('edition_runs',self.old)]:
            with self.assertRaisesRegex(RuntimeError,'cannot be overwritten'):
                self.q(f'UPDATE {table} SET next_edition_number=95 WHERE id=%s',(identifier,))
        fresh=self.create()
        self.assertIsNone(fresh['manual_override_id'])
        self.assertIsNone(self.q('SELECT manual_override_id FROM edition_products WHERE id=%s',(self.product,))[0]['manual_override_id'])

    def test_payload_allows_authorised_cursor_but_keeps_sales_validation(self):
        self.override(5)
        row=dict(next_edition_number=5,edition_total=100,sold_count=94,remaining_count=6,last_assigned_edition=94,manual_override_id='authorised')
        self.assertFalse(backend.calculate_product_edition_metafield_values(row)['allocation_blocked'])
        self.assertTrue(backend.calculate_product_edition_metafield_values({**row,'remaining_count':96})['allocation_blocked'])
        self.assertTrue(backend.calculate_product_edition_metafield_values({**row,'manual_override_id':None})['allocation_blocked'])

    def test_enable_toggle_after_reuse_keeps_cursor_and_sales(self):
        from tests.edition_db_fixture import connect
        self.allocate(quantity=5);self.override(5,ack=True);self.allocate()
        for enabled in (False,True):
            with connect() as conn,conn.cursor() as cur:
                backend._update_edition_product_with_cursor(cur,self.handle,next_edition_number=6,
                    active=enabled,expected_next_edition_number=6,expected_edition_run_id=self.old)
            row=self.q('SELECT next_edition_number,sold_count,active FROM edition_products WHERE id=%s',(self.product,))[0]
            self.assertEqual(row,{'next_edition_number':6,'sold_count':6,'active':enabled})

    def test_actual_mirror_payload_pending_failure_and_verified_retry(self):
        import edition_versions as versions
        self.allocate(quantity=5)
        self.override(5,ack=True)
        with patch.object(versions.shopify_sync,'sync_complete_product_edition_metafields',side_effect=RuntimeError('Shopify offline')):
            with self.assertRaisesRegex(RuntimeError,'offline'):
                backend.sync_product_edition_metafields(self.handle,ensure_schema_first=False)
        row=self.q('SELECT next_edition_number,metafields_sync_status FROM edition_products WHERE id=%s',(self.product,))[0]
        self.assertEqual(row,{'next_edition_number':5,'metafields_sync_status':'Failed'})
        self.q('UPDATE edition_runs SET sync_retry_at=now() WHERE id=%s',(self.old,))
        self.assertIn(self.handle,versions.pending(50))
        with patch.object(versions.shopify_sync,'sync_complete_product_edition_metafields',return_value={}) as mirror:
            backend.sync_product_edition_metafields(self.handle,ensure_schema_first=False)
        payload=mirror.call_args.args[0]
        self.assertEqual((payload['edition_next_number'],payload['edition_sold_count'],payload['edition_remaining']),(5,5,95))
        self.assertEqual(mirror.call_args.kwargs,{'config':None,'request_post':None,'verify':True,'compare':True})
        self.assertEqual(self.q('SELECT metafields_sync_status FROM edition_products WHERE id=%s',(self.product,))[0]['metafields_sync_status'],'Synced')
