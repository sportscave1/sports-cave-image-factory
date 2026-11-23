"""Offline verification of an existing sibling Save; never repeats supplier writes."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest


def functions():
    tree=ast.parse(Path('prodigi_browser.py').read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'business','verified_sibling_baseline'}]
    ns={'deepcopy':deepcopy};exec(compile(ast.Module(body=nodes,type_ignores=[]),'prodigi_browser.py','exec'),ns)
    return ns


class VerifiedSiblingTests(unittest.TestCase):
    def fixture(self):
        ns=functions()
        before={'id':'order','charges':[],'recipient':{'name':'Synthetic'},'items':[
            {'id':'target','sku':'A3','quantity':1},
            {'id':'sibling','sku':'A3','quantity':1,'assets':[],'sizing':'fillPrintArea'}]}
        order=deepcopy(before);order['items'][1].update(assets=[{'url':'verified-render','printArea':'default'}],sizing='fitPrintArea')
        value={'allocation_id':1,'browser':{'before':before}}
        sibling={'allocation_id':2,'order_id':'order','item_id':'sibling','browser':{'started':True,'verified':True,
            'original_sha256':'hash','original_asset_id':'asset','filename':'pinned.jpg'}}
        cursor=Mock();cursor.fetchall.return_value=[{'value':sibling}]
        ns['snapshot']=Mock(return_value={'output':{'sha256':'hash'},'dimensions':[100,100]})
        ns['prep']=SimpleNamespace(validate_order=Mock())
        ns['original_file']=Mock(return_value='verified-original');ns['verify_original']=Mock(return_value=('asset',True))
        return ns,cursor,value,order,sibling

    def test_only_independently_verified_artwork_and_fit_advance(self):
        ns,cur,value,order,_=self.fixture();original=deepcopy(value)
        before,ids=ns['verified_sibling_baseline'](cur,value,order,'target','provider','resolver')
        self.assertEqual(ids,['sibling']);self.assertEqual(value,original)
        self.assertEqual(ns['business'](before,'target',after_save=True),ns['business'](order,'target',after_save=True))
        ns['verify_original'].assert_called_once_with('provider','verified-original','pinned.jpg',{'sha256':'hash'},[100,100])

    def test_missing_ambiguous_unstarted_or_unverified_receipts_are_rejected(self):
        for change in ('missing','ambiguous','unstarted','unverified','same_allocation'):
            with self.subTest(change=change):
                ns,cur,value,order,sibling=self.fixture()
                if change=='missing':cur.fetchall.return_value=[]
                if change=='ambiguous':cur.fetchall.return_value=[{'value':sibling},{'value':sibling}]
                if change=='unstarted':sibling['browser']['started']=False
                if change=='unverified':sibling['browser']['verified']=False
                if change=='same_allocation':sibling['allocation_id']=1
                with self.assertRaises(ValueError):ns['verified_sibling_baseline'](cur,value,order,'target',None,None)
                ns['verify_original'].assert_not_called()

    def test_source_checksum_asset_and_geometry_failures_are_rejected(self):
        for change in ('checksum','asset','geometry','source'):
            with self.subTest(change=change):
                ns,cur,value,order,sibling=self.fixture()
                if change=='checksum':sibling['browser']['original_sha256']='other'
                if change=='asset':ns['verify_original'].return_value=('other',True)
                if change=='geometry':ns['original_file'].side_effect=ValueError('Changed fit')
                if change=='source':ns['snapshot'].side_effect=ValueError('Changed source')
                with self.assertRaises(ValueError):ns['verified_sibling_baseline'](cur,value,order,'target',None,None)

    def test_sibling_approval_does_not_accept_other_business_changes(self):
        for change in ('address','sku','quantity','charges'):
            with self.subTest(change=change):
                ns,cur,value,order,_=self.fixture()
                if change=='address':order['recipient']['name']='Changed'
                if change=='sku':order['items'][1]['sku']='different'
                if change=='quantity':order['items'][1]['quantity']=2
                if change=='charges':order['charges']=[{'id':'paid'}]
                before,_=ns['verified_sibling_baseline'](cur,value,order,'target',None,None)
                self.assertNotEqual(ns['business'](before,'target',after_save=True),ns['business'](order,'target',after_save=True))

    def test_unchanged_siblings_do_not_trigger_extra_provider_reads(self):
        ns,cur,value,order,_=self.fixture();order=deepcopy(value['browser']['before'])
        _,ids=ns['verified_sibling_baseline'](cur,value,order,'target',None,None)
        self.assertEqual(ids,[]);cur.execute.assert_not_called();ns['verify_original'].assert_not_called()


if __name__=='__main__':unittest.main()
