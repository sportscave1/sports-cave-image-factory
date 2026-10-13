from copy import deepcopy
from unittest.mock import patch
import sys
from pathlib import Path
import pytest
import edition_test as case
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/studio'))
import edition_test_local as local


def context():
    return {'actor_id':'synthetic-user','unit':{'shopify_product_gid':case.PRODUCT,'shopify_order_id':case.ORDER,
            'shopify_line_item_id':case.LINE,'allocation_id':655,'allocation_index':1,'edition_number':2,'edition_total':100,
            'allocation_valid':True,'identity_enforced':True,'invalidated_at':None,'status':'assigned'},
            'metadata':{'id':case.FILE,'rev':case.REVISION,'content_hash':case.CONTENT_HASH}}


@pytest.mark.parametrize('key,value',[('shopify_product_gid','other'),('shopify_order_id','other'),('shopify_line_item_id','other'),('allocation_id',656),('allocation_index',2),('edition_number',3),('edition_total',99),('allocation_valid',False),('identity_enforced',False),('invalidated_at','now'),('status','cancelled')])
def test_other_units_and_allocations_blocked(key,value):
    data=context();data['unit'][key]=value
    with pytest.raises(ValueError):case.validate_context(data)


@pytest.mark.parametrize('key,value',[('id','id:other'),('rev','changed'),('content_hash','changed')])
def test_psd_revision_or_hash_changed(key,value):
    data=context();data['metadata'][key]=value
    with pytest.raises(ValueError):case.validate_context(data)


@pytest.mark.parametrize('grant',[{}, {'base_url':'https://evil.test','ticket':'t'*32,'secret':'s'*43},
    {'base_url':'https://sports-cave-image-factory.onrender.com/path','ticket':'t'*32,'secret':'s'*43},
    {'base_url':'https://sports-cave-image-factory.onrender.com','ticket':'t'*32,'secret':'s'*43,'path':'C:/arbitrary'}])
def test_no_forged_origins_or_paths(grant):
    with patch.object(local,'get') as get,pytest.raises(ValueError):local.start(grant)
    get.assert_not_called()


def test_no_arbitrary_scripts_or_numbers():
    with pytest.raises(ValueError):local.action({'action':'edition-test-start','grant':{},'script':'unsafe'})
    with pytest.raises(ValueError):local.action({'action':'run','edition':20})


def test_only_exact_verified_unit_gets_link():
    row={'shopify_product_gid':case.PRODUCT,'shopify_order_id':case.ORDER,'shopify_line_item_id':case.LINE,'allocation_index':1,'edition_number':2,'edition_total':100}
    mapping={'verified':True,'dropbox_file_id':case.FILE}
    assert case.eligible(row,mapping)
    for edit in ({'edition_number':3},{'allocation_index':2},{'shopify_product_gid':'gid://shopify/Product/1'}):assert not case.eligible({**row,**edit},mapping)
    assert not case.eligible(row,None)


def test_mobile_orders_keeps_psd_and_pilot_action_without_global_name_errors():
    import orders_page as orders
    from contextlib import nullcontext
    from types import SimpleNamespace
    row={'shopify_product_gid':case.PRODUCT,'shopify_order_id':case.ORDER,'shopify_line_item_id':case.LINE,'allocation_index':1,'edition_number':2,'edition_total':100}
    mapping={case.PRODUCT:{'verified':True,'dropbox_file_id':case.FILE,'state':'Linked'}}
    links=[]
    fake=SimpleNamespace(session_state={},container=lambda **_:nullcontext(),checkbox=lambda *a,**k:None,
                         markdown=lambda *a:None,caption=lambda *a:None,link_button=lambda *a:links.append(a))
    with patch.object(orders,'st',fake),patch.object(orders.psd_directory,'page_directory',return_value=mapping),patch.object(orders.psd_directory,'render_missing_link_guard'):
        orders._render_mobile_orders([row])
    assert any(label=='Open PSD' for label,url in links)
    assert ('Download JPG','/edition-jpg-download#Download JPG') in links
