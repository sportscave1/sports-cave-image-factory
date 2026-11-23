"""Offline state-machine tests; no application imports, credentials or provider IO."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest


def load_functions():
    tree=ast.parse(Path('prodigi_product_browser.py').read_text(encoding='utf-8'))
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in
              {'business','after_selection_business','changed_fields','complete'}]
    for node in selected:node.decorator_list=[]
    def pinned(order,target):
        result=deepcopy(order)
        for item in result['items']:
            if item['id']==target:
                item.pop('assets',None);item.pop('sizing',None)
        return result
    namespace={'deepcopy':deepcopy,'browser':SimpleNamespace(business=pinned,WAITING='Awaiting browser upload',
        context=lambda _: (None,None,None,None),save=lambda *args:None),
        'prep':SimpleNamespace(now=lambda:'verified-now',validate_order=lambda *args,**kwargs:None,
            record_failure=lambda *args:None)}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'prodigi_product_browser.py','exec'),namespace)
    return namespace


class SelectionResetTests(unittest.TestCase):
    def fixture(self):
        ns=load_functions()
        before={'id':'order','recipient':{'name':'Synthetic'},'items':[
            {'id':'item','quantity':1,'assets':[],'sku':None,'attributes':{}},
            {'id':'sibling','sku':'GLOBAL-CFP-A3','quantity':1,'assets':[]}]}
        order=deepcopy(before);order['items'][0].update(sku='GLOBAL-CFP-A3',attributes={'color':'black'})
        value={'order_id':'order','item_id':'item','reset_generation':'generation','checks':{},
            'reset_authorisation':{'generation':'generation','order_id':'order','item_id':'item','assets':[],
                'before':ns['browser'].business(before,'item')},
            'product_browser':{'started':True,'before':ns['business'](before,'item')}}
        ns['checked']=lambda *args: ({},order,order['items'][0])
        return ns,value,order

    def test_verified_selection_updates_exact_upload_fence_once(self):
        ns,value,order=self.fixture()
        result=ns['complete'](None,'key',value,'product-readback')
        self.assertEqual(result['status'],'Awaiting browser upload')
        self.assertTrue(value['product_browser']['verified'])
        self.assertEqual(value['reset_authorisation']['before'],ns['browser'].business(order,'item'))
        previous=deepcopy(value);ns['complete'](None,'key',value,'product-readback')
        self.assertEqual(value,previous)

    def test_unrelated_business_changes_keep_upload_blocked(self):
        for change in ('recipient','sibling','assets','unpermitted'):
            with self.subTest(change=change):
                ns,value,order=self.fixture();proof=deepcopy(value['reset_authorisation'])
                if change=='recipient':order['recipient']['name']='Changed'
                if change=='sibling':order['items'][1]['quantity']=2
                if change=='assets':order['items'][0]['assets']=[{'url':'unexpected'}]
                if change=='unpermitted':value['product_browser']['started']=False
                self.assertEqual(ns['complete'](None,'key',value,'product-readback')['status'],'Needs review')
                self.assertFalse(value['product_browser'].get('verified'))
                self.assertEqual(value['reset_authorisation'],proof)

    def test_stale_used_or_misbound_reset_cannot_gain_a_fresh_fence(self):
        for field,data in [('generation','stale'),('used_at','already-used'),('order_id','other'),
                           ('item_id','other'),('assets',[{'url':'old'}])]:
            with self.subTest(field=field):
                ns,value,order=self.fixture();value['reset_authorisation'][field]=data
                proof=deepcopy(value['reset_authorisation'])
                self.assertEqual(ns['complete'](None,'key',value,'product-readback')['status'],'Needs review')
                self.assertEqual(value['reset_authorisation'],proof)

    def test_ordinary_selection_does_not_create_reset_authority(self):
        ns,value,_=self.fixture();value.pop('reset_authorisation')
        self.assertEqual(ns['complete'](None,'key',value,'product-readback')['status'],'Awaiting browser upload')
        self.assertNotIn('reset_authorisation',value)


if __name__=='__main__':unittest.main()
