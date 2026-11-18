from types import SimpleNamespace
import pytest
from ads_companion_targeting import select,contains_product


def fixture():
    result=dict(product_name='Joe Namath New York Jets Wall Art',category='NFL',country='USA',product_id='123',
                product_url='https://www.sportscaveshop.com/products/joe-namath')
    refs=dict(product_sets=[dict(id='1',name='Football Wall Art'),dict(id='2',name='NFL Wall Art')],
        saved_audiences=[dict(id='10',name='NFL Fans',targeting={'geo_locations':{'countries':['US']}}),
                        dict(id='11',name='New York Jets',targeting={'geo_locations':{'countries':['US']}}),
                        dict(id='12',name='Joe Namath New York Jets',targeting={'geo_locations':{'countries':['AU']}})])
    client=SimpleNamespace(product_set_health=lambda key:dict(products=[dict(retailer_id='shopify_US_123_456')]))
    return result,refs,client


def test_membership_and_closest_market_audience():
    result,refs,client=fixture()
    chosen=select(refs,result,client=client)
    assert chosen['product_set_id']=='2'
    assert chosen['audience']['id']=='11'
    assert not contains_product([dict(retailer_id='shopify_US_1234_456')],result)
    assert not contains_product([dict(url='https://evil.example/products/joe-namath')],result)
    client.product_set_health=lambda key:dict(products=[] if key=='2' else [dict(url=result['product_url'])])
    assert select(refs,result,client=client)['product_set_id']=='1'
    client.product_set_health=lambda key:dict(products=[])
    with pytest.raises(ValueError,match='contains this product'):select(refs,result,client=client)


def test_prefilled_broad_is_fallback_explicit_broad_is_preserved_and_saved_revalidated():
    result,refs,client=fixture()
    result['posting_settings']=dict(audience={'key':'broad'})
    assert select(refs,result,client=client)['audience']['id']=='11'
    result['posting_settings']['audience_explicit']=True
    selected=select(refs,result,client=client)
    assert selected['audience']['key']=='broad'
    selected['product_set_id']='missing'
    with pytest.raises(ValueError,match='no longer'):select(refs,result,client=client,saved=selected)
    result['posting_settings']=dict(audience={'key':'saved:12'},audience_explicit=True)
    with pytest.raises(ValueError,match='market'):select(refs,result,client=client)


def test_wrong_country_lookalike_does_not_displace_broad():
    result,refs,client=fixture()
    refs['saved_audiences']=[]
    refs['custom_audiences']=[dict(id='99',name='Joe Namath',lookalike_spec={'country':'AU'})]
    assert select(refs,result,client=client)['audience']['key']=='broad'


def test_specific_team_product_set_precedes_generic_league():
    result,refs,client=fixture()
    refs['product_sets'].append(dict(id='3',name='New York Jets Wall Art'))
    assert select(refs,result,client=client)['product_set_id']=='3'
