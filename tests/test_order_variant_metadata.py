import unittest
from pathlib import Path
from unittest.mock import patch

import order_variant_metadata as metadata
import shopify_sync
import supabase_backend as backend
import orders_page
import os_pages


class VariantMetadataTests(unittest.TestCase):
    attributes = [{'key': 'Frame', 'value': 'Unframed'}, {'key': 'Size', 'value': '30 × 45 cm'}]

    def test_medium_unframed_custom_options(self):
        self.assertEqual(metadata.variant_title('', self.attributes), metadata.MEDIUM_UNFRAMED)

    def test_conflicting_missing_unknown_options_fail_closed(self):
        for attrs in [[], self.attributes[:1], self.attributes + [{'key':'Size','value':'XL'}],
                      [{'key':'Frame','value':'Unframed'},{'key':'Size','value':'arbitrary'}]]:
            self.assertEqual(metadata.variant_title('', attrs), '')

    def test_existing_variant_is_unchanged(self):
        self.assertEqual(metadata.variant_title('Black / XL', self.attributes), 'Black / XL')

    def test_graphql_null_variant_uses_attributes_without_inventing_id(self):
        row = shopify_sync.normalize_order({'lineItems': {'nodes':[{'id':'line','quantity':1,'customAttributes':self.attributes}]}}, 'example.myshopify.com')
        self.assertEqual(row['line_items'][0]['variant_title'], metadata.MEDIUM_UNFRAMED)
        self.assertEqual(row['line_items'][0]['variant_id'], '')

    def test_rest_null_variant_uses_properties(self):
        props = [{'name':x['key'],'value':x['value']} for x in self.attributes]
        with patch.object(shopify_sync,'get_config',return_value={}):
            row = backend.normalize_rest_order({'id':1,'line_items':[{'id':2,'properties':props}]})
        self.assertEqual(row['line_items'][0]['variant_title'], metadata.MEDIUM_UNFRAMED)

    def test_display_shipping_and_mapping(self):
        self.assertNotEqual(orders_page._display_variant_label(metadata.MEDIUM_UNFRAMED), 'Missing variant')
        self.assertEqual(orders_page._display_shipping_label('Standard Shipping'), 'Standard')
        mapped = os_pages.prodigi_mapping_for_variant(metadata.MEDIUM_UNFRAMED)
        self.assertEqual(mapped['frame'], 'Unframed')
        self.assertTrue(mapped['size'].startswith('M'))
        self.assertEqual(mapped['prodigi_code'], 'GLOBAL-FAP-A3')

    def test_missing_variant_blocks_even_with_edition_and_manual_override(self):
        row = {'edition_number':1,'frame':'Unframed','size':'M','prodigi_code':'GLOBAL-FAP-A3'}
        self.assertTrue(any('Missing variant metadata' in b for b in os_pages.prodigi_submission_blockers(row)))
        with patch.object(backend,'upsert_prodigi_dispatch_row') as write:
            with self.assertRaisesRegex(ValueError,'Missing variant metadata'):
                os_pages.prodigi_save_dispatch_row(row,status='Complete',manual_override={'fulfilment_override':True})
            write.assert_not_called()
        self.assertEqual(row['edition_number'],1)

    def test_repair_contains_no_allocator_or_counter_updates(self):
        sql = Path('scripts/repair_sc3232_variant.sql').read_text(encoding='utf-8')
        self.assertNotIn('allocate_edition_line_units_atomic', sql)
        self.assertNotIn('UPDATE edition_products', sql)
        self.assertNotIn('INSERT INTO edition_orders', sql)


if __name__ == '__main__':
    unittest.main()
