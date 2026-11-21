"""Partial originals are saved without retrying rejected generation or posting."""
from copy import deepcopy
from uuid import uuid4

import pytest
import ads_partial_delivery as partial
import design_publish_ad as ads
import ads_companion_transfer as transfer
from test_ads_companion_transfer import batch, send
from test_product_upload_staff_queue import database, store
from test_ads_companion_queue import queued_store, USER, ROW, brief


def blocked_value():
    return dict(upload=str(uuid4()), stage='generating', folder='/saved',
        chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+str(uuid4()),
        attachment_repair={'id':'uncertain-send', 'state':'sending'})


def test_blocked_step_collects_successes_then_stops_without_send_or_post(monkeypatch):
    import ads_attachment_repair
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    monkeypatch.setattr(ads, '_post_request', lambda _: pytest.fail('Rejected package reached Posting'))
    monkeypatch.setattr(ads_attachment_repair, 'advance', lambda *_: pytest.fail('Rejected package sent a repair'))
    value = blocked_value()
    reason = 'Image provider moderation_blocked. Ad 3 man-cave.jpg missing.'
    event = dict(state='blocked', reason=reason)
    payload = ads._step('key', value, {}, event, 0)
    assert payload['missing'] == ['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg']
    assert payload['repair'] is None and payload['recover'] is True
    assert value['attachment_repair']['id'] == 'uncertain-send'
    assert ads.public(value)['label'] == 'Saving completed ad files'
    started = value['blocked_collection']['started_at']
    value = deepcopy(value)  # restart, durable original deadline and permits
    value['artifacts'] = {name:{'hash':'saved-'+name} for name in payload['missing']}
    saved = deepcopy(value['artifacts'])
    assert ads._step('key', value, {}, event, 0) == {}
    assert value['stage'] == 'failed' and value['artifacts'] == saved
    assert value['blocked_collection']['state'] == 'saved'
    assert value['blocked_collection']['started_at'] == started
    assert value['recovery_checked_version'] == 1


@pytest.mark.parametrize('event,elapsed', [({'transfer_failed':True}, 0), ({},601)])
def test_collection_failure_is_bounded_and_preserves_outputs(monkeypatch, event, elapsed):
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    value = blocked_value()
    assert partial.begin(value, 'moderation_blocked: man-cave.jpg missing')
    value['artifacts'] = {'ad_copy.csv': {'hash':'saved'}}
    monkeypatch.setattr(partial.time, 'time', lambda: value['blocked_collection']['started_at']+elapsed)
    assert partial.advance(value, event) == {}
    assert value['stage'] == 'failed' and value['artifacts']['ad_copy.csv']['hash'] == 'saved'
    assert value['blocked_collection']['state'] == 'needs_download_review'


def test_unknown_slot_or_existing_posting_cannot_start_partial_collection():
    value = blocked_value()
    assert not partial.begin(value, 'moderation_blocked: no specific slot supplied')
    value['posting_id'] = 'existing'
    assert not partial.begin(value, 'moderation_blocked: man-cave.jpg missing')


def test_posting_guard_rejects_partial_package():
    with pytest.raises(ValueError, match='rejected image slots'):
        ads._post_request({'blocked_collection': {'excluded':['man-cave.jpg']}})


def test_real_receipts_for_available_exports_rejected_slot_never_accepted(batch):
    value = batch.read()
    assert partial.begin(value, 'moderation_blocked: man-cave.jpg missing')
    ads.write(ads.PREFIX+batch.job, value)
    assert send(batch, 'ad_copy.csv')['received'] == 'ad_copy.csv'
    assert not send(batch, 'collector-hallway.jpg')['ready']
    assert not send(batch, 'architectural-wall.jpg')['ready']
    # Validation rejects this slot before downloading, image inspection or upload.
    with pytest.raises(ValueError, match='slot was rejected'):
        send(batch, 'man-cave.jpg')
    assert len(batch.calls) == 3
    assert batch.read()['artifacts']['ad_copy.csv']['id']
    assert transfer.delivery(batch.read())['missing'] == []


def test_rejection_collection_never_becomes_a_new_creative_revision():
    from ads_creative_contract import replace_unposted
    value = blocked_value()
    value['result'] = dict(campaign_type='Instant Experience', master_prompt='legacy old release')
    assert partial.begin(value, 'moderation_blocked: man-cave.jpg missing')
    assert not replace_unposted(value)
    assert 'superseded_by' not in value


def test_resume_of_rejected_job_only_collects_existing_exports(batch):
    value = batch.read()
    value.update(stage='failed', detail='moderation_blocked: man-cave.jpg missing')
    value['blocked_collection'] = dict(reason=value['detail'], excluded=['man-cave.jpg'], started_at=1)
    ads.write(ads.PREFIX+batch.job, value)
    transfer.resume(batch.job, {'id':'admin'})
    resumed = batch.read()
    assert resumed['stage'] == 'generating' and resumed['collect_only']
    assert resumed['blocked_collection']['excluded'] == ['man-cave.jpg']
    assert resumed['blocked_collection']['started_at'] > 1
    assert 'man-cave.jpg' not in transfer.delivery(resumed)['missing']


def test_new_prompt_has_one_footer_and_independent_partial_delivery():
    import ads_page
    from ads_ie_two_line import FOOTER_RULES
    result = ads_page.build_ads_result_record('Synthetic Edition','NBA','Australia','Instant Experience')
    prompt = result['master_prompt']
    assert prompt.count(FOOTER_RULES) == 1
    assert 'Complete this independent step even if an image remains missing' in prompt
    assert 'do not regenerate a safety-blocked or unexplained rejected slot' in prompt
    assert 'still attach every completed image' in ads.delivery_prompt(result,'synthetic reference','/fixture','fixture-job')


def test_queued_collection_precedes_new_generation_and_deadline_starts_on_claim(queued_store, monkeypatch):
    import ads_companion_queue as queue
    import product_upload_staff_queue as uploads
    queue.enqueue(USER, brief(), {'row':ROW})
    item = queue.enqueue(USER, {**brief(), 'variation_token':'partial-distinct'}, {'row':ROW})
    value = dict(blocked_value(), upload=item['id'], requester=USER['id'], source='new_ads',
        sport='Baseball',country='USA',result=brief(),stage='waiting',resume_stage='generating',collect_only=True,
        blocked_collection={'reason':'moderation_blocked: man-cave.jpg missing','excluded':['man-cave.jpg']})
    ads.write(ads.PREFIX+item['id'],value)
    monkeypatch.setattr(queue, 'prepare', lambda _: pytest.fail('New generation ran before existing export collection'))
    token = uploads.pair({'id':'desktop'})
    payload = ads.tick(token, {})['job']
    assert payload['id'] == item['id'] and payload['repair'] is None
    with queued_store() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(ads.PREFIX+item['id'],))
        assert cur.fetchone()['value']['blocked_collection']['started_at'] > 0
