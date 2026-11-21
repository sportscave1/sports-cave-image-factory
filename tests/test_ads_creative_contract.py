"""Offline regression: an old export must never become today's new campaign."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import ads_creative_contract as contract
import ads_companion_queue as queue
import design_publish_ad as ads
import product_upload_staff_queue as uploads
from test_ads_companion_queue import queued_store, USER, ROW, brief
from test_product_upload_staff_queue import database, store
from test_ads_auto_recovery import read


def old_brief():
    result = brief()
    result['master_prompt'] = 'SPORTS CAVE TWO-LINE COLLECTOR FOOTER V5\nOriginal badge banner'
    result['generated_ad_output'] = result['master_prompt']
    result['prompt_contract_version'] = 'old footer'
    return result


def ledger(monkeypatch, row=None):
    import meta_posting_jobs
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(snapshot=lambda _: row or {}))


def test_old_recovery_creates_one_current_revision_and_completes(queued_store, monkeypatch):
    import meta_posting_jobs
    ledger(monkeypatch)
    parent = queue.enqueue(USER, old_brief(), {'row': ROW})['id']
    value = read(queued_store, parent)
    value.update(stage='generating', chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+parent,
                 folder='/old', artifacts={'man-cave.jpg': {'hash': 'old-badge'}},
                 targeting={'audience':'saved-selection'})
    value['result']['posting_settings'] = {'audience':'saved-selection'}
    ads.write(ads.PREFIX+parent, value)
    original = deepcopy(value)
    # Even a stale ready/submitted event cannot post or collect the old exports.
    monkeypatch.setattr(ads, '_post_request', lambda _: pytest.fail('old files reached Posting'))
    assert ads._step(ads.PREFIX+parent, value, {}, {'state': 'submitted'}, 0) == {}
    saved = read(queued_store, parent)
    assert saved['stage'] == 'cancelled'
    assert saved['result'] == original['result'] and saved['artifacts'] == original['artifacts']
    child = saved['superseded_by']
    new = read(queued_store, child)
    assert child != parent and new['creative_revision_of'] == parent
    assert not contract.obsolete(new['result'])
    assert new['targeting'] == original['targeting']
    assert new['result']['posting_settings'] == original['result']['posting_settings']
    assert 'No added footer badge or PNG overlay' in new['result']['master_prompt']
    assert not any(k in new for k in ('artifacts','chat_url','posting_id','attachment_repair'))
    # A lost response/replayed old checkpoint resolves to the same child.
    assert contract.replace_unposted(original)
    assert original['superseded_by'] == child
    with queued_store() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM app_settings WHERE key LIKE 'design_publish_ad:%' AND value ? 'upload'")
        assert cur.fetchone()['n'] == 2
    token = uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(queue, 'prepare', lambda _: dict(stage='opening', folder='/new', prompt='current brief'))
    assert ads.tick(token, {})['job']['id'] == child
    request = SimpleNamespace(submission_id=ads._posting_id(child))
    submitted = []
    monkeypatch.setattr(ads, '_post_request', lambda _: request)
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(
        submit=lambda r: submitted.append(r.submission_id) or r.submission_id,
        snapshot=lambda _: {'status':'COMPLETE'}))
    monkeypatch.setattr(meta_posting_jobs, 'confirmed_ads', lambda _: (3, 3))
    ads.tick(token, {'id':child, 'state':'submitted'})
    assert read(queued_store, child)['stage'] == 'complete'
    assert submitted == [ads._posting_id(child)]


def test_existing_current_product_market_job_is_reused(queued_store, monkeypatch):
    ledger(monkeypatch)
    current = queue.enqueue(USER, brief(), {'row': ROW})['id']
    parent = queue.enqueue(USER, old_brief(), {'row': ROW})['id']
    value = read(queued_store, parent)
    value['stage'] = 'preparing'
    assert contract.replace_unposted(value)
    assert value['superseded_by'] == current
    assert not contract.obsolete(read(queued_store, current)['result'])


def test_lost_posting_acknowledgement_reconciles_original_identity(queued_store, monkeypatch):
    ledger(monkeypatch, {'status':'AMBIGUOUS'})
    parent = queue.enqueue(USER, old_brief(), {'row': ROW})['id']
    value = read(queued_store, parent)
    value['stage'] = 'generating'
    assert contract.replace_unposted(value)
    assert value['stage'] == 'posting' and value['posting_id'] == ads._posting_id(parent)
    assert 'superseded_by' not in value


@pytest.mark.parametrize('updates', [dict(stage='complete'), dict(stage='cancelled'),
                                   dict(stage='failed'), dict(posting_id='already-reserved')])
def test_submitted_or_stopped_jobs_remain_immutable(updates):
    value = dict(stage='generating', result=old_brief(), **{'upload':'unused'})
    value.update(updates)
    frozen = deepcopy(value)
    assert not contract.replace_unposted(value)
    assert value == frozen


def test_current_hockey_contract_and_other_formats_untouched():
    for result in (brief(), {**old_brief(), 'campaign_type':'Carousel'},
                   {**old_brief(), 'workflow_mode':'creative_refresh'},
                   {**old_brief(), 'platform':'google'}):
        assert not contract.obsolete(result)


def test_posting_boundary_rejects_unmigrated_old_creative():
    with pytest.raises(ValueError, match='obsolete creative'):
        ads._post_request({'result':old_brief()})
