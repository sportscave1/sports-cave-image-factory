"""Saved creatives survive delayed catalogue sync without duplicate work."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
import design_publish_ad as ads
from ads_companion_targeting import CatalogPending


def setup(monkeypatch):
    import ads_companion_controls
    monkeypatch.setattr(ads_companion_controls, 'stopped', lambda _: False)
    clock = [1000.0]
    monkeypatch.setattr(ads.time, 'time', lambda: clock[0])
    writes = []
    monkeypatch.setattr(ads, 'write', lambda key, value: writes.append(dict(value)))
    value = dict(upload=str(uuid4()), stage='generating', folder='/saved', chat_url='saved-chat')
    calls = []
    def pending(value):
        calls.append(value['upload'])
        raise CatalogPending('not indexed yet')
    monkeypatch.setattr(ads, '_post_request', pending)
    return clock, writes, value, calls


def test_wait_backoff_and_no_duplicate_work(monkeypatch):
    clock, writes, value, calls = setup(monkeypatch)
    assert ads._step('key', value, {}, {}, 0) == {}
    assert value['stage'] == 'generating' and value['collect_only']
    assert value['catalog_retry']['next_at'] == 1060
    assert ads.public(value)['label'] == 'Waiting for Meta catalogue'
    assert ads._step('key', value, {}, {}, 99999) == {}
    assert len(calls) == 1 and len(writes) == 1
    clock[0] = 1060
    ads._step('key', value, {}, {}, 60)
    assert value['catalog_retry']['next_at'] == 1180
    clock[0] = 87400
    with pytest.raises(ValueError, match='24 hours'):
        ads._step('key', value, {}, {}, 0)
    assert value['chat_url'] == 'saved-chat'


def test_recovery_submits_same_durable_id_then_clears_wait(monkeypatch):
    import meta_posting_jobs
    clock, writes, value, calls = setup(monkeypatch)
    ads._step('key', value, {}, {}, 0)
    clock[0] = 1060
    request = SimpleNamespace(submission_id=ads._posting_id(value['upload']))
    monkeypatch.setattr(ads, '_post_request', lambda _: request)
    submissions=[]
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(
        submit=lambda req: submissions.append(req.submission_id) or req.submission_id,
        snapshot=lambda _: {'status':'CREATING'}))
    ads._step('key', value, {}, {}, 60)
    ads._step('key', value, {}, {}, 1)
    assert submissions == [request.submission_id]
    assert value['stage'] == 'posting' and 'catalog_retry' not in value


def test_pagination_exhaustion_is_not_missing_membership(monkeypatch):
    import meta_ads_client as meta
    monkeypatch.setattr(meta, '_paged_get', lambda *a, **kw: {'rows':[], 'has_more':True})
    client=object.__new__(meta.MetaPostingClient)
    client.config={}
    with pytest.raises(CatalogPending, match='incomplete'):
        client.product_set_members('set', product={'product_id':'123'})


def test_paged_get_reports_truncation(monkeypatch):
    import meta_ads_client as meta
    monkeypatch.setattr(meta, '_request', lambda *a, **kw: {'data':[{'id':'one'}], 'paging':{'next':'next'}})
    monkeypatch.setattr(meta, '_get_next_page', lambda _: {'data':[{'id':'two'}]})
    assert meta._paged_get('set', max_pages=1)['has_more'] is True
    result=meta._paged_get('set', max_pages=2)
    assert result['has_more'] is False and len(result['rows'])==2


def test_shopify_variant_feed_uses_exact_product_group(monkeypatch):
    import json
    import meta_ads_client as meta
    from ads_companion_targeting import contains_product
    product = dict(product_id='gid://shopify/Product/15492780228915',
        product_url='https://www.sportscaveshop.com/products/the-unseen-lane-nikita-kucherov-wall-art')
    variant = dict(retailer_id='68014763770163',
        url=product['product_url'] + '?variant=68014763770163&utm_source=facebook')
    calls = []
    def read(path, **kwargs):
        calls.append(path)
        # Current Shopify feed retailer IDs identify variants, not products.
        assert json.loads(kwargs['params']['filter']) == {
            'retailer_product_group_id': {'eq': '15492780228915'}}
        return {'rows': [variant], 'has_more': False}
    monkeypatch.setattr(meta, '_paged_get', read)
    client = object.__new__(meta.MetaPostingClient)
    client.config = {}
    assert contains_product(client.product_set_members('set', product=product), product)
    assert calls == ['set/products']
    assert not contains_product([dict(variant, url=product['product_url']+'-other')], product)
