import ast
import json
import socket
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import psd_directory as psd
import print_jpg


def product(n=1, title='Art: One'):
    return {'shopify_product_gid': f'gid://shopify/Product/{n}', 'product_title': title, 'handle': f'art-{n}'}


def file(n=1, name='Art_ One.psd', folder=psd.ROOT):
    return {'.tag': 'file', 'id': f'id:{n}', 'name': name, 'path_display': folder + '/' + name,
            'preview_url': f'https://www.dropbox.com/preview/art-{n}'}


class PsdDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('No network'))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def test_exact_sanitised_title_and_verified_identity(self):
        rows = [product(), {'product_title': 'No ID', 'handle': 'no-id'}, product(2, 'Different')]
        mapping = psd.reconcile(rows, [file(), file(2, 'Different enough.psd')])
        self.assertTrue(psd.link(rows[0], mapping))
        self.assertEqual(mapping[psd.product_id(rows[2])]['state'], 'Not linked')
        self.assertEqual(psd.product_id({'shopify_product_id': '1'}), psd.product_id(rows[0]))
        self.assertEqual(psd.product_id({'shopify_product_id': 'gid://shopify/Order/1'}), '')

    def test_review_folder_and_ambiguous_files(self):
        p = product()
        self.assertFalse(psd.link(p, psd.reconcile([p], [file(folder=psd.ROOT + '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE')])))
        m = psd.reconcile([p], [file(), file(2)])
        self.assertIn('ambiguous', m[psd.product_id(p)]['state'])
        m = psd.reconcile([p, product(2)], [file()])
        self.assertFalse(any(psd.link(p, m) for p in [p, product(2)]))

    def test_rename_preserves_id_and_missing_retains_verified_assignment(self):
        p = product()
        old = psd.reconcile([p], [file()])
        new = psd.reconcile([p], [file(name='Completely renamed.psd')], old)
        self.assertEqual(new[psd.product_id(p)]['dropbox_file_id'], 'id:1')
        missing = psd.reconcile([p], [file(2)], new)
        self.assertEqual(missing[psd.product_id(p)]['dropbox_file_id'], 'id:1')
        self.assertFalse(psd.link(p, missing))
        moved = psd.reconcile([p], [file(folder=psd.ROOT + '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE')], old)
        self.assertFalse(psd.link(p, moved))
        reuse = psd.reconcile([product(2)], [file()], old)
        self.assertFalse(psd.link(product(2), reuse))

    def test_secure_links(self):
        for bad in ['javascript:alert(1)', 'https://www.dropbox.com.evil/preview/a',
                    'https://www.dropbox.com/s/a', 'https://www.dropbox.com/scl/fi/a',
                    'https://user@www.dropbox.com/preview/a', 'https://www.dropbox.com:443/preview/a',
                    'http://www.dropbox.com/preview/a']:
            self.assertEqual(psd.protected_url(bad), '')
        p = product()
        m = psd.reconcile([p], [{**file(), 'preview_url': 'https://www.dropbox.com/s/a'}])
        self.assertTrue(psd.link(p, m).startswith('/api/files-psd-open?'))
        self.assertNotIn('https://www.dropbox.com/s/a', psd.display_link(p, m))

    def test_export_sanitisation_collisions(self):
        p = product(1, 'A: B')
        mapping = psd.reconcile([p], [file(1, 'A - B.psd')])
        self.assertTrue(psd.link(p, mapping))
        self.assertFalse(psd.link(p, psd.reconcile([p, product(2, 'A - B')], [file(1, 'A - B.psd')])))
        self.assertTrue(psd.link(product(1, '50/50'), psd.reconcile([product(1, '50/50')], [file(1, '50 - 50.psd')])))

    def test_statuses(self):
        live = {'edition_enabled': True, 'edition_total':100, 'edition_next_number':1, 'sync_status':'Synced to Shopify'}
        self.assertEqual(psd.status(live),'Live')
        self.assertEqual(psd.status({**live,'online_store_url':'','status':'DRAFT'}),'Live')
        self.assertEqual(psd.status({**live,'edition_enabled':False}),'Offline')
        self.assertEqual(psd.status({**live,'sync_error':'failed'}),'Offline')
        self.assertEqual(psd.status({**live,'edition_next_number':101}),'Expired')
        self.assertEqual(psd.status({**live,'edition_sold_count':100}),'Expired')
        self.assertEqual(psd.status({**live,'run_status':'EXPIRED'}),'Expired')
        self.assertEqual(psd.status({**live,'run_status':'active','historical_run_status':'expired','edition_sold_count':200,'current_run_sold_count':0}),'Live')
        self.assertEqual(psd.status({}),'Offline')

    def test_persistence_cache_and_multi_line_orders(self):
        products = [product(1), product(2, 'Art Two')]
        mapping = psd.reconcile(products, [file(1), file(2, 'Art Two.psd')])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'directory.json'
            psd.save(mapping, path)
            with patch.object(Path, 'read_text', wraps=path.read_text) as read:
                loaded = psd.directory(path)
                for _ in range(100):
                    self.assertIs(psd.directory(path), loaded)
                self.assertEqual(read.call_count, 1)
        # Execute the real table projection without importing application/server modules.
        tree = ast.parse(Path('orders_page.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_display_rows')
        namespace = {'psd_directory': psd, 'print_jpg': print_jpg, 'VISIBLE_COLUMNS': ['order', 'product', 'file'], 'COPY_ORDER_ICON': 'copy', 'st': None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'orders_page.py', 'exec'), namespace)
        lines = [{'order': '#SC1', 'product': p['product_title'], 'shopify_product_id': p['shopify_product_gid']} for p in products]
        lines.append({'order': '#SC1', 'product': 'Missing', 'shopify_product_id': '3'})
        with patch.object(psd, 'directory', return_value=mapping) as lookup, patch('auto_editions_runtime.download_links',return_value={}):
            rows = namespace['_display_rows'](lines, normalised=True)
        self.assertEqual(lookup.call_count, 1)
        self.assertNotEqual(rows[0]['file'], rows[1]['file'])
        self.assertTrue(rows[0]['file'].endswith('#Open PSD'))
        self.assertEqual(rows[2]['file'], 'Not linked')

    def test_282_products_plus_40_excluded_and_performance(self):
        products = [product(i, f'Artwork {i}') for i in range(1, 283)]
        entries = [file(i, f'Artwork {i}.psd') for i in range(1, 283)]
        entries += [file(i+400, f'Artwork {i}.psd', psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE') for i in range(1, 41)]
        start = time.perf_counter()
        mapping = psd.reconcile(products, entries)
        for _ in range(10):
            links = [psd.display_link(p, mapping) for p in products]
        elapsed = time.perf_counter()-start
        self.assertEqual(sum(bool(psd.link(p, mapping)) for p in products), 282)
        self.assertLess(elapsed, 1.0)
        print(f'PSD synthetic benchmark: 282 matches + 2820 projections in {elapsed:.4f}s, no network')

    def test_explicit_refresh_batches_pages_and_fails_closed(self):
        p = product()
        api = SimpleNamespace(list_folder_page=lambda *a, **k: None)
        with tempfile.TemporaryDirectory() as d, patch.dict('sys.modules', {'dropbox_integration': api}):
            path = Path(d) / 'mapping.json'
            with patch.object(api, 'list_folder_page', side_effect=[
                {'entries': [file()], 'has_more': True, 'cursor': 'next'},
                {'entries': [], 'has_more': False},
            ]) as listing:
                mapping = psd.refresh_from_dropbox('test-only-token', [p], path)
                self.assertTrue(psd.link(p, mapping))
                self.assertEqual(listing.call_count, 2)
                self.assertEqual(listing.call_args.kwargs['cursor'], 'next')
            before = path.read_bytes()
            with patch.object(api, 'list_folder_page', return_value={'entries': [], 'has_more': True}):
                with self.assertRaises(ValueError):
                    psd.refresh_from_dropbox('test-only-token', [p], path)
            self.assertEqual(path.read_bytes(), before)

    def test_snapshot_identity_crosschecks(self):
        namespace = 'ns:123//02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/A - B.psd'
        product = {'edition_ops_title': 'A: B', 'shopify_handle': 'a-b', 'shopify_product_gid': 'gid://shopify/Product/1',
                   'approved_dropbox_file_id': 'id:one', 'approved_psd_filename': 'A - B.psd', 'approved_dropbox_namespace_path': namespace}
        approved = {'edition_ops_title': 'A: B', 'shopify_handle': 'a-b', 'shopify_product_gid': 'gid://shopify/Product/1',
                    'dropbox_file_id': 'id:one', 'dropbox_filename': 'A - B.psd', 'dropbox_namespace_path': namespace}
        catalogue, mapping = psd.snapshot_mapping([product], [approved], [])
        self.assertTrue(psd.link(catalogue[0], mapping))
        self.assertEqual(mapping['gid://shopify/Product/1']['namespace_path'], namespace)
        for changed in [{**approved, 'shopify_handle': 'wrong'}, {**approved, 'shopify_product_gid': 'gid://shopify/Product/2'},
                        {**approved, 'dropbox_namespace_path': namespace.replace('/A - B.psd', '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/A - B.psd')}]:
            with self.assertRaises(ValueError):
                psd.snapshot_mapping([product], [changed], [])
        with self.assertRaises(ValueError):
            psd.snapshot_mapping([product], [approved], [{'Current Dropbox path': psd.ROOT + '/A - B.psd'}])

    def test_page_contracts(self):
        source = Path('edition_ops.py').read_text(encoding='utf-8')
        self.assertIn('"display_status", "psd_file"', source)
        self.assertNotIn('TextColumn("Shopify Sync"', source)
        self.assertNotIn('LinkColumn("Open Admin"', source)
        self.assertIn('Save & Sync Shopify', source)
        for name in ('edition_ops.py', 'orders_page.py', 'dropbox_integration.py', 'psd_directory.py'):
            ast.parse(Path(name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
