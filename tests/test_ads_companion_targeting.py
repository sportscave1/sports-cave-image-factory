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
    client=SimpleNamespace(product_set_members=lambda key, **kwargs:[dict(retailer_id='shopify_US_123_456')])
    return result,refs,client


def test_membership_and_closest_market_audience():
    result,refs,client=fixture()
    chosen=select(refs,result,client=client)
    assert chosen['product_set_id']=='2'
    assert chosen['audience']['id']=='11'
    assert not contains_product([dict(retailer_id='shopify_US_1234_456')],result)
    assert not contains_product([dict(url='https://evil.example/products/joe-namath')],result)
    client.product_set_members=lambda key, **kwargs:[] if key=='2' else [dict(url=result['product_url'])]
    with pytest.raises(ValueError,match='NFL Wall Art'):
        select(refs,result,client=client)
    client.product_set_members=lambda key, **kwargs:[]
    with pytest.raises(ValueError,match='confirmed this product'):select(refs,result,client=client)


def test_prefilled_broad_is_fallback_explicit_broad_is_preserved_and_saved_revalidated():
    result,refs,client=fixture()
    result['posting_settings']=dict(audience={'key':'broad'})
    assert select(refs,result,client=client)['audience']['id']=='11'
    result['posting_settings']['audience_explicit']=True
    selected=select(refs,result,client=client)
    assert selected['audience']['key']=='broad'
    selected['product_set_id']='missing'
    assert select(refs,result,client=client,saved=selected)['product_set_id']=='2'
    result['posting_settings']=dict(audience={'key':'saved:12'},audience_explicit=True)
    with pytest.raises(ValueError,match='market'):select(refs,result,client=client)


def test_wrong_country_lookalike_does_not_displace_broad():
    result,refs,client=fixture()
    refs['saved_audiences']=[]
    refs['custom_audiences']=[dict(id='99',name='Joe Namath',lookalike_spec={'country':'AU'})]
    assert select(refs,result,client=client)['audience']['key']=='broad'


def test_sport_wall_art_precedes_specific_team():
    result,refs,client=fixture()
    refs['product_sets'].append(dict(id='3',name='New York Jets Wall Art'))
    assert select(refs,result,client=client)['product_set_id']=='2'


def test_membership_uses_minimal_read_and_capability_denial_is_actionable(monkeypatch):
    import meta_ads_client as meta
    result,refs,client=fixture()
    calls=[]
    def read(path,**kwargs):
        calls.append((path,kwargs))
        return {'rows':[{'retailer_id':'123'}]}
    monkeypatch.setattr(meta,'_paged_get',read)
    actual=object.__new__(meta.MetaPostingClient)
    actual.config={'fixture':True}
    assert select(refs,result,client=actual)['product_set_id']=='2'
    assert calls[0][0]=='2/products'
    assert 'filter' in calls[0][1]['params']
    assert calls[0][1]['params']['fields']=='id,retailer_id,url'
    def denied(*args,**kwargs):
        raise meta.MetaAdsApiError('Capability denied',status_code=400,error_code=3)
    monkeypatch.setattr(meta,'_paged_get',denied)
    with pytest.raises(ValueError,match='All imported files are saved'):
        select(refs,result,client=actual)
    def transient(*args,**kwargs):
        raise meta.MetaAdsApiError('Try later',status_code=503,error_code=2,is_transient=True)
    monkeypatch.setattr(meta,'_paged_get',transient)
    with pytest.raises(meta.MetaAdsApiError):
        select(refs,result,client=actual)


@pytest.mark.parametrize('category,name', [('NBA','NBA Wall Art'),('Basketball','NBA Wall Art'),
    ('Soccer','Football Wall Art'),('NFL','NFL Wall Art'),('Formula 1','Formula One Wall Art'),
    ('NRL','Rugby League Wall Art'),('NHL','Ice Hockey Wall Art')])
def test_selected_sport_wins_over_title_and_stale_saved_set(category,name):
    result,refs,client=fixture()
    result.update(category=category,product_name='Legends Never Die Jordan vs Bryant')
    refs['product_sets']=[dict(id='wrong',name='Jordan vs Bryant Wall Art'),dict(id='sport',name=name)]
    result['posting_settings']={'product_set_id':'wrong'}
    assert select(refs,result,client=client)['product_set_id']=='sport'
    assert select(refs,result,client=client,saved={'product_set_id':'wrong'})['product_set_id']=='sport'


def test_missing_sport_collection_never_falls_back_to_other_sport():
    result,refs,client=fixture()
    result['category']='NBA'
    with pytest.raises(ValueError,match='NBA Wall Art'):
        select(refs,result,client=client)
