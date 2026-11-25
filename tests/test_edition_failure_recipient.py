"""Offline regression of the actual mapper without application startup."""
import ast
from pathlib import Path
import unittest
from copy import deepcopy
from prodigi_qa import address_matches

source = ast.parse(Path(__file__).resolve().parents[1].joinpath('prodigi_preparation.py').read_text())
function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'shopify_recipient')
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'prodigi_preparation.py', 'exec'), namespace)
map_recipient = namespace['shopify_recipient']

class RecipientRegression(unittest.TestCase):
    def payload(self):
        return {'shipping_address': {'name':'Synthetic Customer', 'address1':'10 Example Road',
            'address2':'', 'company':'Example Farm', 'city':'Example City', 'province':'Iowa',
            'province_code':'IA', 'zip':'50000-1234', 'country_code':'US'}}

    def test_company_is_preserved_as_supplier_second_line(self):
        expected = map_recipient(self.payload(), '123')
        actual = deepcopy(expected)
        actual['address']['stateOrCounty'] = 'IA'
        actual.pop('state_aliases')
        self.assertEqual(expected['address']['line2'], 'Example Farm')
        self.assertTrue(address_matches(expected, actual))
        actual['address']['line2'] = 'Other Farm'
        self.assertFalse(address_matches(expected, actual))

    def test_apartment_is_never_replaced_by_company(self):
        raw = self.payload(); raw['shipping_address']['address2'] = 'Unit 7'
        self.assertEqual(map_recipient(raw, '123')['address']['line2'], 'Unit 7')

    def test_no_company_does_not_invent_address(self):
        raw = self.payload(); raw['shipping_address'].pop('company')
        expected = map_recipient(raw, '123')
        self.assertFalse(expected['address']['line2'])
        self.assertTrue(address_matches(expected, deepcopy(expected)))

    def test_graphql_and_order_identity_guard(self):
        raw = self.payload(); raw['shippingAddress'] = raw.pop('shipping_address')
        self.assertEqual(map_recipient(raw, '123')['address']['line2'], 'Example Farm')
        with self.assertRaisesRegex(ValueError, 'different or unidentified'):
            map_recipient({'raw_payload':dict(raw, id='456')}, '123')

    def test_different_street_zip_country_and_recipient_still_fail(self):
        expected = map_recipient(self.payload(), '123')
        for field in ('line1','line2','townOrCity','postalOrZipCode','countryCode','stateOrCounty'):
            actual = deepcopy(expected); actual['address'][field] = 'different'
            self.assertFalse(address_matches(expected, actual), field)
        actual = deepcopy(expected); actual['name'] = 'Different Customer'
        self.assertFalse(address_matches(expected, actual))

if __name__ == '__main__': unittest.main()
