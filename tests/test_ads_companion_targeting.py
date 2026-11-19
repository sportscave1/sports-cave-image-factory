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


def test_missing_featured_membership_does_not_block_sport_set_and_audience():
    result,refs,client=fixture()
    chosen=select(refs,result,client=client)
    assert chosen['product_set_id']=='2'
    assert chosen['audience']['id']=='11'
    assert not contains_product([dict(retailer_id='shopify_US_1234_456')],result)
    assert not contains_product([dict(url='https://evil.example/products/joe-namath')],result)
    client.product_set_members=lambda key, **kwargs:[] if key=='2' else [dict(url=result['product_url'])]
    assert select(refs,result,client=client)['product_set_id']=='2'
    client.product_set_members=lambda key, **kwargs:[]
    assert select(refs,result,client=client)['product_set_id']=='2'


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


def test_optional_membership_api_is_not_a_posting_gate(monkeypatch):
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
    assert calls == []
    def denied(*args,**kwargs):
        raise meta.MetaAdsApiError('Capability denied',status_code=400,error_code=3)
    monkeypatch.setattr(meta,'_paged_get',denied)
    assert select(refs,result,client=actual)['product_set_id']=='2'
    def transient(*args,**kwargs):
        raise meta.MetaAdsApiError('Try later',status_code=503,error_code=2,is_transient=True)
    monkeypatch.setattr(meta,'_paged_get',transient)
    assert select(refs,result,client=actual)['product_set_id']=='2'


@pytest.mark.parametrize('category,name', [('NBA','NBA Wall Art'),('Basketball','NBA Wall Art'),
    ('Soccer','Football Wall Art'),('NFL','NFL Wall Art'),('Formula 1','FORMULA 1 WALL ART POPULAR'),
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


@pytest.mark.parametrize('category', ['Formula One', 'Formula 1', 'F1', 'formula-one-wall-art'])
def test_formula_one_always_uses_popular_even_with_saved_old_selection(category):
    result,refs,client=fixture()
    result['category']=category
    refs['product_sets']=[
        dict(id='1',name='Formula One Wall Art'),
        dict(id='2',name='Motor Racing Wall Art'),
        dict(id='3',name='Formula 1 Wall Art Popular USA'),
        dict(id='4',name='  Formula 1  Wall Art Popular  '),
    ]
    def membership(*args, **kwargs):
        pytest.fail('Featured-product membership must not block a curated set')
    client.product_set_members=membership
    assert select(refs,result,client=client,saved={'product_set_id':'1'})['product_set_id']=='4'
    refs['product_sets'].pop()
    with pytest.raises(ValueError,match='FORMULA 1 WALL ART POPULAR'):
        select(refs,result,client=client)


@pytest.mark.parametrize('category,name', [
    ('NBA','NBA Wall Art'), ('NFL','NFL Wall Art'), ('Soccer','Football Wall Art'),
    ('AFL','AFL Wall Art'), ('NRL','Rugby League Wall Art'), ('NHL','Ice Hockey Wall Art'),
    ('Cricket','Cricket Wall Art'), ('Tennis','Tennis Wall Art'), ('Golf','Golf Wall Art'),
    ('Formula One','FORMULA 1 WALL ART POPULAR'),
])
def test_sport_sets_work_without_featured_product_membership(category,name):
    result,refs,client=fixture()
    result['category']=category
    refs['product_sets']=[dict(id='selected',name=name)]
    def membership(*args, **kwargs):
        pytest.fail('No per-product membership dependency for any sport')
    client.product_set_members=membership
    assert select(refs,result,client=client)['product_set_id']=='selected'
