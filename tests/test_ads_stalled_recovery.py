"""Offline regressions for idle collection and polling-independent deadlines."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import design_publish_ad as ads


@pytest.fixture
def checkpoint(monkeypatch):
    import ads_companion_controls
    clock = [10000.0]
    monkeypatch.setattr(ads.time, 'time', lambda: clock[0])
    monkeypatch.setattr(ads_companion_controls, 'stopped', lambda _: False)
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    monkeypatch.setattr(ads, '_post_request', lambda _: None)
    value = dict(upload=str(uuid4()), stage='generating', folder='/saved',
                 chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+str(uuid4()),
                 last_chat_activity_at=9000, chat_generating=False,
                 artifacts={'ad_copy.csv': {'hash': 'preserved'},
                            'collector-hallway.jpg': {'hash': 'cover1'},
                            'architectural-wall.jpg': {'hash': 'cover2'}})
    return value, clock


def test_stalled_partial_delivery_repairs_only_missing_original_once(checkpoint):
    value, clock = checkpoint
    saved = deepcopy(value['artifacts'])
    event = dict(chat_url=value['chat_url'], generating=False, finished=True, activity='same')
    value['chat_activity'] = 'same'
    ads._step('key', value, {}, event, 0)
    clock[0] += 301
    delivery = ads._step('key', value, {}, event, 0)
    assert delivery['repair']['names'] == ['man-cave.jpg']
    rid = delivery['repair']['id']
    assert ads._step('key', value, {}, dict(repair_claim=rid), 0)['repair_send']
    assert not ads._step('key', value, {}, dict(repair_claim=rid), 0)['repair_send']
    assert value['artifacts'] == saved
    assert ads.public(value)['label'] == 'Restoring missing ad attachments'


def test_continual_generating_reports_cannot_extend_overall_deadline(checkpoint):
    value, clock = checkpoint
    value['artifacts'] = {}
    value['chat_generating'] = True
    ads._step('key', value, {}, dict(chat_url=value['chat_url'], generating=True), 0)
    clock[0] += 21601
    with pytest.raises(ValueError, match='six hours'):
        ads._step('key', value, {}, dict(chat_url=value['chat_url'], generating=True), 0)


def test_posting_deadline_survives_polling_and_restart(checkpoint, monkeypatch):
    import meta_posting_jobs
    value, clock = checkpoint
    value.update(stage='posting', posting_id='existing')
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(snapshot=lambda _: dict(status='CREATING')))
    ads._step('key', value, {}, {}, 0)
    value = deepcopy(value)
    clock[0] += 1801
    with pytest.raises(ValueError, match='Restoring original posting inputs'):
        ads._step('key', value, {}, {}, 0)


def test_slow_generation_gets_fresh_posting_deadline(checkpoint, monkeypatch):
    import meta_posting_jobs
    value, clock = checkpoint
    value.update(timed_stage='generating', stage_started_at=5000)
    monkeypatch.setattr(ads, '_post_request', lambda _: 'verified request')
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(submit=lambda _: 'same-posting',
        snapshot=lambda _: dict(status='CREATING')))
    # Complete receipts mean recovery is unnecessary.
    value['artifacts']['man-cave.jpg'] = {'hash': 'cover3'}
    ads._step('key', value, {}, {}, 0)
    assert value['stage'] == 'posting'
    assert value['stage_started_at'] == clock[0]
