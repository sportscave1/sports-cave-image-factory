"""Explicit two-ad completion, preserving missing-route evidence and idempotency."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
import pytest

import design_publish_ad as ads
import ads_partial_delivery as partial
from meta_posting_service import MetaPostingService, PostingError, PostingValidationError, validate_posting_request, posting_ad_results
from meta_posting_jobs import confirmed_ads
from tests.test_meta_posting import FakePostingClient, FakePostingStore, request_for
from test_ads_companion_transfer import batch, send
from test_product_upload_staff_queue import database, store


def test_two_cover_pack_is_explicit_and_legacy_default_stays_three():
    request = request_for()
    two = replace(request, creatives=(request.creatives[0],request.creatives[2]))
    with pytest.raises(PostingValidationError):
        validate_posting_request(two)
    assert len(validate_posting_request(replace(two,partial_pack=True))['creatives']) == 2
    with pytest.raises(PostingValidationError):
        validate_posting_request(replace(two,creatives=two.creatives[:1],partial_pack=True))
    assert len(posting_ad_results([{'index':1},{'index':2}])) == 3
    marked = posting_ad_results([], expected_count=2)
    assert len(posting_ad_results(marked)) == 2


def test_real_posting_service_creates_only_two_paused_ads_and_reuses_receipt():
    request = request_for()
    request = replace(request, creatives=(request.creatives[0],request.creatives[2]),partial_pack=True)
    client, ledger = FakePostingClient(), FakePostingStore()
    service = MetaPostingService(client=client,store=ledger)
    first = service.create_paused_campaign(request)
    assert confirmed_ads(first) == (2, 2)
    assert len(client.copy_ads) == 2
    ids = [row['meta_ad_id'] for row in first['ad_results']]
    again = service.create_paused_campaign(request)
    assert [row['meta_ad_id'] for row in again['ad_results']] == ids
    assert len(client.copy_ads) == 2


@pytest.mark.parametrize('reason', ['moderation_blocked: architectural-wall.jpg missing',
                                  'architectural-wall.jpg missing after reserve technical failure'])
def test_partial_collection_freezes_only_original_successes_and_completes(batch, monkeypatch, reason):
    import ads_companion_controls
    import ads_attachment_repair
    import meta_posting_jobs
    monkeypatch.setattr(ads_companion_controls, 'stopped', lambda _:False)
    monkeypatch.setattr(ads_attachment_repair,'advance',lambda *_:pytest.fail('No generation or repair Send allowed'))
    value = batch.read()
    assert partial.begin(value, reason)
    ads.write(ads.PREFIX+batch.job,value)
    for name in ('ad_copy.csv','collector-hallway.jpg','man-cave.jpg'):
        send(batch,name)
    value = batch.read()
    assert partial.advance(value,{}) is None
    assert [name for _,name in partial.posting_routes(value)] == ['collector-hallway.jpg','man-cave.jpg']
    saved = deepcopy(value['artifacts'])
    request = SimpleNamespace(submission_id=ads._posting_id(batch.job))
    monkeypatch.setattr(ads,'_post_request', lambda _:request)
    posted = []
    monkeypatch.setattr(meta_posting_jobs,'JOBS',SimpleNamespace(submit=lambda r:posted.append(r.submission_id) or r.submission_id,
        snapshot=lambda _:dict(status='COMPLETE',ad_type='Instant Experience',ad_results=[
            {'index':i,'expected_ad_count':2,'meta_ad_id':str(i),'meta_ad_configured_status':'PAUSED'} for i in (1,2)])))
    ads._step(ads.PREFIX+batch.job,value,{}, {},0)
    assert value['stage'] == 'complete' and posted == [ads._posting_id(batch.job)]
    assert value['artifacts'] == saved
    kind = 'provider' if 'moderation' in reason else 'delivery'
    assert ads.public(value)['label'] == f'Needs {kind} review · 2/3 covers saved'
    assert 'Two Meta ads created paused' in ads.public(value)['detail']


def test_rejected_or_duplicate_routes_cannot_fill_the_pack():
    value = dict(partial_posting=True,partial_routes=list(ads.COVERS)[:2],
                 blocked_collection={'state':'saved','excluded':['architectural-wall.jpg']})
    with pytest.raises(ValueError):
        partial.posting_routes(value)
    value['partial_routes'] = [list(ads.COVERS)[0]]*2
    with pytest.raises(ValueError):
        partial.posting_routes(value)


def test_review_label_for_historical_failures_does_not_reactivate_them():
    value = dict(stage='failed',detail='moderation_blocked',artifacts={name:{} for name in list(ads.COVERS.values())[:2]})
    frozen = deepcopy(value)
    assert ads.public(value)['label'] == 'Needs provider review · 2/3 covers saved'
    assert value == frozen and not ads.public(value)['active']


def test_two_ad_retry_preserves_first_ad_and_campaign():
    request = request_for()
    request = replace(request, creatives=request.creatives[:2], partial_pack=True)
    client, ledger = FakePostingClient(fail_at='ad_2'), FakePostingStore()
    service = MetaPostingService(client=client,store=ledger)
    with pytest.raises(PostingError) as error:
        service.create_paused_campaign(request)
    first = error.value.result['ad_results'][0]['meta_ad_id']
    client.fail_at = ''
    completed = service.create_paused_campaign(request)
    assert confirmed_ads(completed) == (2,2)
    assert completed['ad_results'][0]['meta_ad_id'] == first
    assert client.calls.count('campaign') == client.calls.count('adset') == 1


def test_actual_post_request_uses_matching_copy_for_successful_original_routes(batch,monkeypatch):
    import ads_direct_post
    import ads_companion_targeting
    import ads_page
    import ads_posting_page
    value = batch.read()
    assert partial.begin(value, 'moderation_blocked: architectural-wall.jpg missing')
    ads.write(ads.PREFIX+batch.job,value)
    for name in ('ad_copy.csv','collector-hallway.jpg','man-cave.jpg'):
        send(batch,name)
    value = batch.read()
    assert partial.advance(value,{}) is None
    value['handle'] = 'synthetic-product'
    monkeypatch.setattr(ads,'_download',lambda dbx,meta,limit:batch.files[meta['path_display'].rsplit('/',1)[-1]])
    monkeypatch.setattr(ads_direct_post,'references',lambda *a,**kw:dict(catalog_resolution={'id':'25'},dataset_resolution={'id':'26'},page=True,instagram=True))
    monkeypatch.setattr(ads_companion_targeting,'select',lambda *a,**kw:dict(product_set_id='20',audience={'type':'broad'}))
    monkeypatch.setattr(ads_posting_page,'MetaPostingClient',lambda:object())
    request = ads._post_request(value)
    assert request.partial_pack and len(request.creatives) == 2
    copy = ads_page.parse_instant_experience_copy_csv(batch.files['ad_copy.csv'],value['result'])
    for creative,(route,name) in zip(request.creatives,partial.posting_routes(value)):
        assert creative.image_name == name and creative.image_bytes == batch.files[name]
        assert creative.headline == copy[route][0]['headline']
