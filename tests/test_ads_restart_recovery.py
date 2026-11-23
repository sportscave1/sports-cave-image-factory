"""A process exit between routes reuses saved Meta IDs on the next poll."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import ads_auto_recovery as recovery
import design_publish_ad as ads
import meta_posting_jobs
from meta_posting_service import MetaPostingService
from tests.test_meta_posting import FakePostingClient, request_for
from tests.test_meta_posting_jobs import Ledger


def test_restart_after_two_routes_completes_without_thirty_minute_delay(monkeypatch):
    client, ledger, request = FakePostingClient(), Ledger(), request_for()
    ledger.reserve(request)

    def interrupted(message):
        if str(message).startswith('Creating Ad 3 of'):
            raise SystemExit('Simulated server process exit')

    with pytest.raises(SystemExit):
        MetaPostingService(client=client, store=ledger, progress_callback=interrupted).create_paused_campaign(request)
    before = deepcopy(ledger.record)
    assert meta_posting_jobs.confirmed_ads(before) == (2, 3)
    assert before['status'] == 'AD_CREATED'
    service = MetaPostingService(client=client, store=ledger)
    requests = []

    def resume(original):
        requests.append(original)
        service.create_paused_campaign(original)

    monkeypatch.setattr('ads_companion_controls.stopped', lambda _: False)
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    monkeypatch.setattr(ads, '_post_request', lambda _: request)
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(
        snapshot=lambda _: {**deepcopy(ledger.record), 'running_here':False, 'lease_active':False}, resume=resume))
    value = dict(upload=str(uuid4()),stage='posting',posting_id=str(request.submission_id))
    ads._step('key', value, {}, {}, 0)
    assert requests == [request]
    recovery.activate(value)
    ads._step('key', value, {}, {}, 0)
    assert value['stage'] == 'complete'
    assert meta_posting_jobs.confirmed_ads(ledger.record) == (3, 3)
    assert [a['meta_ad_id'] for a in ledger.record['ad_results'][:2]] == [a['meta_ad_id'] for a in before['ad_results'][:2]]
    assert client.calls.count('campaign') == client.calls.count('adset') == 1
    assert len(client.copy_ads) == 3


@pytest.mark.parametrize('flags', [{'running_here':True}, {'lease_active':True}])
def test_live_worker_is_not_resumed_even_with_old_stage_clock(monkeypatch, flags):
    monkeypatch.setattr('ads_companion_controls.stopped', lambda _: False)
    row = dict(status='AD_CREATED',running_here=False,lease_active=False,**{})
    row.update(flags)
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(snapshot=lambda _: row))
    monkeypatch.setattr(ads, '_post_request', lambda _: pytest.fail('A live worker must retain ownership'))
    value = dict(upload=str(uuid4()),stage='posting',posting_id=str(uuid4()),timed_stage='posting',stage_started_at=1)
    assert ads._step('key', value, {}, {}, 0) == {}
    assert value['stage'] == 'posting'
