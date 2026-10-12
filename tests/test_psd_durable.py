"""Actual isolated PostgreSQL tests; refuse any non-local URL or database."""
import csv
import io
import os
import json
import socket
import time
import statistics
import unittest
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
import psd_directory as psd
from psd_mapping_store import PostgresMappings, MappingConflict, preview

ADMIN={'id':'local-admin','role':'admin','is_active':True}
ROOT=Path(__file__).resolve().parents[1]
PORT=os.getenv('PSD_LOCAL_TEST_PORT')


@unittest.skipUnless(PORT,'Set PSD_LOCAL_TEST_PORT to the isolated postgres test container port.')
class DurablePsdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PORT.isdigit():raise ValueError('Local test port must be numeric')
        cls.connect=staticmethod(lambda:psycopg.connect(host='127.0.0.1',port=int(PORT),dbname='psd_test',user='postgres',password='local-psd-test-only',row_factory=dict_row))
        with zipfile.ZipFile(os.getenv('PSD_LOCAL_SNAPSHOT',r'C:\Users\hello\Downloads\Sports_Cave_Codex_PSD_Snapshot_2026-10-12.zip')) as archive:
            data=[list(csv.DictReader(io.StringIO(archive.read(n).decode('utf-8-sig')))) for n in ('edition_ops_products_333.csv','approved_dropbox_psds_282.csv','excluded_review_psds_40.csv')]
        cls.products,cls.candidates=psd.snapshot_mapping(*data)
        cls.approved=[{'id':r['dropbox_file_id'],'.tag':'file','name':r['path'].rsplit('/',1)[-1],'path_display':r['path']} for r in cls.candidates.values() if r.get('verified')]
        cls.excluded=data[2]
        with cls.connect() as conn,conn.cursor() as cur:
            for role in ('anon','authenticated','service_role'):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,))
                if not cur.fetchone():cur.execute('CREATE ROLE '+role+' NOLOGIN')
            cur.execute('CREATE TABLE IF NOT EXISTS edition_products(shopify_product_gid text PRIMARY KEY, shopify_product_id text,shopify_handle text,product_title text,metafields_sync_status text,active boolean,edition_total integer,next_edition_number integer)')
            cur.execute((ROOT/'scripts/sql/product_psd_mapping.sql').read_text())
            for row in cls.products:
                cur.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,'Synced',true,100,1) ON CONFLICT DO NOTHING",(psd.product_id(row),psd.product_id(row),row['handle'],row['product_title']))

    def setUp(self):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('TRUNCATE product_psd_mappings,product_psd_mapping_audit RESTART IDENTITY')
        self.store=PostgresMappings(self.connect)
        self.other=PostgresMappings(self.connect)
        self.pid=psd.product_id(self.products[0])
        self.second=psd.product_id(self.products[1])
        self.meta={'.tag':'file','id':'id:local-manual','name':'Different artwork.psd','path_display':psd.ROOT+'/Different artwork.psd'}

    def test_real_282_backfill_40_exclusions_51_missing_and_idempotence(self):
        report=self.store.backfill(self.candidates)
        self.assertEqual(len(report['insert']),282)
        self.assertEqual(len(report['conflicts']),0)
        self.assertEqual(self.store.read(),{})
        self.store.backfill(self.candidates,execute=True,approval='local fixture owner approval',preview_hash=report['preview_hash'])
        mapping=self.other.read()
        self.assertEqual(len(mapping),282)
        self.assertEqual(sum(not psd.link(p,mapping) for p in self.products),51)
        self.assertFalse(any('99_PSD_NEEDS_REVIEW' in r['path'] for r in mapping.values()))
        rerun=self.store.backfill(self.candidates)
        self.assertEqual(len(rerun['preserved']),282)
        self.assertEqual(len(rerun['insert']),0)
        self.store.backfill(self.candidates,execute=True,approval='local idempotence test',preview_hash=rerun['preview_hash'])
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT count(*) AS count FROM product_psd_mapping_audit')
            self.assertEqual(cur.fetchone()['count'],282)
            cur.execute("SELECT count(*) AS count FROM edition_products WHERE metafields_sync_status='Synced' AND active AND edition_total=100 AND next_edition_number=1")
            self.assertEqual(cur.fetchone()['count'],333)

    def test_manual_priority_and_replacement_audit(self):
        self.store.attach(self.pid,self.meta,ADMIN,confirm_mismatch=True)
        report=self.store.backfill(self.candidates)
        self.assertTrue(any(r['product_gid']==self.pid for r in report['conflicts']))
        self.store.backfill(self.candidates,execute=True,approval='local approval',preview_hash=report['preview_hash'])
        self.assertEqual(self.other.read()[self.pid]['source'],'manual')
        newer={**self.meta,'id':'id:replacement'}
        with self.assertRaises(MappingConflict):self.store.attach(self.pid,newer,ADMIN,expected_file_id=self.meta['id'],confirm_mismatch=True)
        self.store.attach(self.pid,newer,ADMIN,expected_file_id=self.meta['id'],confirm_mismatch=True,confirm_replace=True)
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT * FROM product_psd_mapping_audit WHERE action='replace'")
            row=cur.fetchone();self.assertEqual(row['before_state']['dropbox_file_id'],'id:local-manual');self.assertEqual(row['after_state']['dropbox_file_id'],'id:replacement')

    def test_reload_and_multiple_app_instances_immediately_see_manual_attach(self):
        self.assertEqual(self.other.read(),{})
        self.store.attach(self.pid,self.meta,ADMIN,confirm_mismatch=True)
        self.assertEqual(self.other.read()[self.pid]['dropbox_file_id'],self.meta['id'])
        self.assertEqual(PostgresMappings(self.connect).read()[self.pid]['source'],'manual')
        import orders_page
        with patch.object(psd,'directory',side_effect=self.other.read):
            rows=orders_page._display_rows([{'order':'#LOCAL','shopify_product_id':self.pid},{'order':'#LOCAL','shopify_product_id':self.second}],normalised=True)
        self.assertTrue(rows[0]['file'].endswith('#Open PSD'));self.assertEqual(rows[1]['file'],'Not linked')

    def test_invalid_review_duplicate_and_concurrent_assignments(self):
        with self.assertRaises(ValueError):self.store.attach(self.pid,{**self.meta,'path_display':psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Different artwork.psd'},ADMIN,confirm_mismatch=True)
        with self.assertRaises(PermissionError):self.store.attach(self.pid,self.meta,{**ADMIN,'role':'worker'},confirm_mismatch=True)
        with self.assertRaises(ValueError):self.store.attach(self.pid,self.meta,ADMIN)
        def attach(pid):
            try:self.store.attach(pid,self.meta,ADMIN,confirm_mismatch=True);return 'saved'
            except MappingConflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(attach,[self.pid,self.second]))
        self.assertEqual(sorted(result),['conflict','saved'])
        self.assertEqual(len(self.store.read()),1)

    def test_stale_preview_and_cancelled_picker_never_write(self):
        report=self.store.backfill(self.candidates)
        with self.assertRaises(PermissionError):self.store.backfill(self.candidates,execute=True,preview_hash=report['preview_hash'])
        self.store.attach(self.pid,self.meta,ADMIN,confirm_mismatch=True)
        with self.assertRaises(MappingConflict):self.store.backfill(self.candidates,execute=True,approval='local approval',preview_hash=report['preview_hash'])
        self.assertEqual(len(self.store.read()),1)
        with self.assertRaises(MappingConflict):self.store.attach(self.pid,{**self.meta,'id':'id:new'},ADMIN,confirm_mismatch=True,confirm_replace=True)
        self.assertEqual(self.store.read()[self.pid]['dropbox_file_id'],self.meta['id'])

    def test_rls_client_denied_and_unique_database_constraints(self):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SET LOCAL ROLE anon')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):cur.execute('SELECT * FROM product_psd_mappings')
            conn.rollback()
        self.store.attach(self.pid,self.meta,ADMIN,confirm_mismatch=True)
        with self.connect() as conn,conn.cursor() as cur:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                cur.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','test')",(self.second,self.meta['id'],self.meta['path_display']))
            conn.rollback()

    def test_status_all_333_synced_fixture_records_unchanged(self):
        import edition_ops
        for product in self.products:
            source={**product,'metafields_sync_status':'Synced','active':True,'edition_total':100,'next_edition_number':1,'status':'active','online_store_url':''}
            row=edition_ops._row_from_supabase_product(source)
            before=dict(row)
            self.assertEqual(psd.status(row),'Live')
            self.assertEqual(row,before)
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM edition_products WHERE metafields_sync_status='Synced'")
            self.assertEqual(cur.fetchone()['n'],333)

    def test_schema_is_additive_idempotent_and_unavailability_is_not_missing(self):
        self.store.attach(self.pid,self.meta,ADMIN,confirm_mismatch=True)
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute((ROOT/'scripts/sql/product_psd_mapping.sql').read_text())
        self.assertEqual(self.other.read()[self.pid]['source'],'manual')
        with patch.object(psd,'directory',side_effect=__import__('psd_mapping_store').MappingUnavailable('unavailable')):
            directory=psd.page_directory()
        self.assertEqual(psd.display_link({'shopify_product_gid':self.pid},directory),'Unavailable')

    def test_performance_cached_reads_and_real_table_projection(self):
        report=self.store.backfill(self.candidates)
        self.store.backfill(self.candidates,execute=True,approval='local perf approval',preview_hash=report['preview_hash'])
        import edition_ops,orders_page
        mapping=self.store.read()
        rows=[{**p,'edition_enabled':True,'edition_total':100,'sync_status':'Synced to Shopify'} for p in self.products]
        orders=[{'order':'#LOCAL','shopify_product_id':psd.product_id(p)} for p in self.products]
        results={}
        for name,fn in [('revision_cached_read',self.store.read),('edition_projection',lambda:[edition_ops._editor_payload(r,mapping) for r in rows]),('orders_projection',lambda:orders_page._display_rows(orders,normalised=True))]:
            values=[]
            with patch.object(psd,'directory',return_value=mapping):
                for _ in range(20):
                    start=time.perf_counter();fn();values.append((time.perf_counter()-start)*1000)
            results[name+'_median_ms']=round(statistics.median(values),3)
        results['rows']=333;results['dropbox_requests']=0
        (ROOT/'output/psd_durable_performance.json').write_text(json.dumps(results,indent=2))
        print('Durable PSD performance:',json.dumps(results))


if __name__=='__main__':unittest.main()
