"""Actual SQL against an explicitly configured loopback-only disposable database."""
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
import uuid

import psycopg
from psycopg.rows import dict_row
import design_studio_intelligence_store as store
from tests.test_design_studio_sales_intelligence import snapshot
import design_studio_sales_intelligence as intel
from datetime import date

URL = os.getenv('DESIGN_V3_TEST_DATABASE_URL', '')


@unittest.skipUnless(URL, 'Set DESIGN_V3_TEST_DATABASE_URL to a disposable loopback PostgreSQL database')
class LocalPostgresTests(unittest.TestCase):
    def test_real_projections_refunds_sources_and_read_only_transaction(self):
        self.assertIn(urlsplit(URL).hostname, ('127.0.0.1', 'localhost', '::1'))
        schema = 'design_v3_' + uuid.uuid4().hex
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA {schema}')
        def connect():
            return psycopg.connect(URL, row_factory=dict_row, options=f'-c search_path={schema}')
        try:
            with connect() as conn:
                conn.execute('''
                    CREATE TABLE shopify_products(shopify_product_id text,title text,handle text,product_type text,
                        status text,image_url text,synced_at timestamptz,raw_json jsonb);
                    CREATE TABLE shopify_orders(shopify_order_id text,created_at timestamptz,cancelled_at timestamptz,
                        financial_status text,currency text,synced_at timestamptz,raw_json jsonb);
                    CREATE TABLE shopify_order_lines(shopify_line_item_id text,shopify_product_id text,
                        shopify_order_id text,variant_title text,quantity integer,raw_json jsonb);
                    CREATE TABLE edition_products(id int,shopify_product_id text,shopify_handle text,
                        active boolean,sold_out boolean,edition_total int);
                    CREATE TABLE edition_design_tracking(edition_product_id int,date_created date,first_order text);
                    CREATE TABLE seo_google_connections(workspace_key text PRIMARY KEY,ga4_property_id text);
                ''')
                # Actual repository schemas for the optional signals.
                conn.execute(Path('migrations/20260626_ads_intelligence_v1.sql').read_text())
                ga4 = Path('migrations/20260813_google_seo_phase3_storage.sql').read_text()
                begin = ga4.index('CREATE TABLE IF NOT EXISTS seo_ga4_daily_landing_pages')
                finish = ga4.index('CREATE INDEX', begin)
                conn.execute(ga4[begin:finish])
                product = {'tags': ['MLB'], 'published_at': '2026-01-01'}
                payload = {'test': False, 'shipping_country': 'AU', 'raw_payload': {
                    'line_items': [{'id': 11, 'price': '100', 'total_discount': '10', 'discount_allocations': [{'amount': '10'}]}],
                    'refunds': [{'refund_line_items': [{'line_item_id': 11, 'quantity': 1, 'subtotal': '90'}]}]},
                    'customer_email': 'secret@example.com'}
                conn.execute("INSERT INTO shopify_products VALUES('gid://shopify/Product/1','Baseball','baseball','Framed Art','ACTIVE','https://cdn.shopify.com/test.jpg',now(),%s)", (json.dumps(product),))
                conn.execute("INSERT INTO shopify_orders VALUES('1','2026-06-01',NULL,'PARTIALLY_REFUNDED','AUD',now(),%s)", (json.dumps(payload),))
                conn.execute("INSERT INTO shopify_order_lines VALUES('gid://shopify/LineItem/11','gid://shopify/Product/1','1','Large',3,'{}')")
                conn.execute("INSERT INTO meta_ad_accounts(account_id,currency) VALUES('a','AUD'); INSERT INTO ads_product_mapping(ad_id,product_handle) VALUES('ad','baseball')")
                conn.execute("INSERT INTO meta_ad_insights_daily(date,ad_id,account_id,spend,purchases,purchase_value) VALUES('2026-06-01','ad','a',100,3,300)")
                conn.execute("INSERT INTO seo_google_connections VALUES('sports-cave','property1')")
                conn.execute("INSERT INTO seo_ga4_daily_landing_pages(workspace_key,ga4_property_id,date,dimension_key_hash,landing_page_path_query,sessions) VALUES('sports-cave','property1','2026-06-01','hash','/products/baseball',50)")
                conn.execute("INSERT INTO edition_products VALUES(1,'gid://shopify/Product/1','baseball',true,false,100)")
                conn.execute("INSERT INTO edition_design_tracking VALUES(1,'2026-01-01','manual text')")
            start, end = intel.reporting_window(date(2026, 10, 10))
            sources = store.load_sources(start, end, connect=connect)
            self.assertEqual(sources['limitations'], [])
            self.assertEqual(sources['lines'][0]['refunds'], [{'quantity': 1, 'subtotal': '90'}])
            self.assertNotIn('secret@example.com', repr(sources))
            snap = snapshot(sources=sources)
            row = snap['performers'][0]
            self.assertEqual((row['net_units'], row['net_revenue']), (2, 200))
            self.assertEqual(row['meta'][0]['spend'], '100')
            self.assertEqual(float(row['ga4'][0]['sessions']), 50)
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                with store.read_cursor(connect) as cur:
                    cur.execute('DELETE FROM shopify_orders')
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM shopify_orders').fetchone()['n'], 1)
        finally:
            with psycopg.connect(URL, autocommit=True) as conn:
                conn.execute(f'DROP SCHEMA {schema} CASCADE')


if __name__ == '__main__':
    unittest.main()
