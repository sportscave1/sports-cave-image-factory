"""Actual business-fence function isolated from application startup and providers."""
import ast
from copy import deepcopy
from pathlib import Path
import unittest


def business():
    tree=ast.parse(Path('prodigi_browser.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='business')
    ns={'deepcopy':deepcopy};exec(compile(ast.Module(body=[fn],type_ignores=[]),'prodigi_browser.py','exec'),ns)
    return ns['business']


class FirstPriceTests(unittest.TestCase):
    def fixture(self):
        before={'id':'order','charges':[],'recipient':{'name':'Synthetic'},'items':[
            {'id':'target','sku':'A3','quantity':1,'assets':[]},
            {'id':'sibling','sku':'A3','quantity':1,'assets':[]}]}
        after=deepcopy(before)
        after['items'][0]['assets']=[{'url':'saved'}]
        after['items'][1].update(unitPrice={'amount':'37.40','currency':'USD'},lineTotal={'amount':'37.40','currency':'USD'})
        return before,after

    def test_first_price_population_after_save_preserves_the_fence(self):
        before,after=self.fixture();fn=business()
        self.assertEqual(fn(before,'target',after_save=True),fn(after,'target',after_save=True,before=before))
        self.assertNotEqual(fn(before,'target'),fn(after,'target')) # Pre-Save remains strict.
        self.assertIn('amount',after['items'][1]['unitPrice']) # No provider data mutation.

    def test_existing_currency_changes_are_still_rejected(self):
        before,after=self.fixture();fn=business()
        before['items'][1]['unitPrice']={'amount':'40','currency':'AUD'}
        self.assertNotEqual(fn(before,'target',after_save=True),fn(after,'target',after_save=True,before=before))

    def test_unrelated_mutations_are_still_rejected(self):
        for change in ('address','quantity','sku','artwork','charges'):
            with self.subTest(change=change):
                before,after=self.fixture();fn=business()
                if change=='address':after['recipient']['name']='Changed'
                if change=='quantity':after['items'][1]['quantity']=2
                if change=='sku':after['items'][1]['sku']='different'
                if change=='artwork':after['items'][1]['assets']=[{'url':'changed'}]
                if change=='charges':after['charges']=[{'id':'paid'}]
                self.assertNotEqual(fn(before,'target',after_save=True),fn(after,'target',after_save=True,before=before))

    def test_invalid_new_money_or_extra_metadata_is_not_ignored(self):
        for money in ({'amount':'NaN','currency':'USD'},{'amount':'Infinity','currency':'USD'},
                      {'amount':'-1','currency':'USD'},{'amount':'37','currency':'usd'},
                      {'amount':'37','currency':'USD','unexpected':True}, {'currency':'USD'}):
            with self.subTest(money=money):
                before,after=self.fixture();fn=business();after['items'][1]['unitPrice']=money
                self.assertNotEqual(fn(before,'target',after_save=True),fn(after,'target',after_save=True,before=before))

    def test_existing_amount_repricing_is_allowed_only_after_save(self):
        before,after=self.fixture();fn=business()
        before['items'][1].update(unitPrice={'amount':'50','currency':'USD'},lineTotal={'amount':'50','currency':'USD'})
        self.assertEqual(fn(before,'target',after_save=True),fn(after,'target',after_save=True,before=before))
        self.assertNotEqual(fn(before,'target'),fn(after,'target'))


if __name__=='__main__':unittest.main()
