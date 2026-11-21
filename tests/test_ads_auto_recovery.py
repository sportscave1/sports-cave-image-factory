"""Offline automatic recovery, real disposable SQL and real posting reconciliation."""
from copy import deepcopy
from contextlib import contextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import ads_auto_recovery as recovery
import design_publish_ad as ads
import ads_companion_queue as queue
import product_upload_staff_queue as uploads
from test_ads_companion_queue import queued_store, USER, ROW, brief
from test_product_upload_staff_queue import database, store


def due(store, job):
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE app_settings SET value=jsonb_set(value,'{auto_recovery,next_at}','0') WHERE key=%s", (ads.PREFIX+job,))


def read(store, job):
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (ads.PREFIX+job,))
        return cur.fetchone()['value']


def test_transient_failure_recovers_and_completes_without_play(queued_store, monkeypatch):
    import meta_posting_jobs
    item = queue.enqueue(USER, brief(), {'row': ROW})
    job = item['id']; token = uploads.pair({'id': 'desktop'})
    calls = []
    def prepare(value):
        calls.append(value['upload'])
        if len(calls) == 1:
            raise TimeoutError('temporary provider outage')
        return dict(stage='opening', folder='/frozen', prompt='original brief')
    monkeypatch.setattr(queue, 'prepare', prepare)
    request = SimpleNamespace(submission_id=ads._posting_id(job))
    monkeypatch.setattr(ads, '_post_request', lambda _: request)
    posted = []
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(
        submit=lambda req: posted.append(req.submission_id) or req.submission_id,
        snapshot=lambda _: dict(status='COMPLETE')))
    monkeypatch.setattr(meta_posting_jobs, 'confirmed_ads', lambda _: (3, 3))
    ads.tick(token, {})
    saved = read(queued_store, job)
    assert saved['stage'] == 'waiting' and saved['auto_recovery']['attempts'] == 1
    assert ads.tick(token, {}) == {}  # not due: no hot loop
    due(queued_store, job)
    ads.settings(False)
    assert ads.tick(token, {}) == {}  # an automatic retry cannot unpause the queue
    ads.settings(True)
    assert ads.tick(token, {})['job']['id'] == job
    ads.tick(token, dict(id=job, state='submitted'))
    assert read(queued_store, job)['stage'] == 'complete'
    assert posted == [request.submission_id]
    assert calls == [job, job]


def test_posting_failure_automatically_finishes_all_routes_without_duplicates(monkeypatch):
    import meta_posting_jobs
    import ads_companion_controls
    from meta_posting_jobs import PostingJobs, confirmed_ads
    from meta_posting_service import MetaPostingService
    from tests.test_meta_posting import FakePostingClient, request_for
    from tests.test_meta_posting_jobs import Ledger
    monkeypatch.setattr(ads_companion_controls, 'stopped', lambda _: False)
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    request = request_for()
    client, ledger = FakePostingClient(fail_at='ad_2'), Ledger()
    jobs = PostingJobs(store_factory=lambda: ledger,
        service_factory=lambda **kw: MetaPostingService(client=client, **kw))
    try:
        identity = jobs.submit(request)
        jobs.jobs[identity]['future'].result(timeout=15)
        failed = jobs.snapshot(identity)
        assert failed['status'] == 'FAILED' and confirmed_ads(failed) == (1, 3)
        first = failed['ad_results'][0]['meta_ad_id']
        monkeypatch.setattr(meta_posting_jobs, 'JOBS', jobs)
        monkeypatch.setattr(ads, '_post_request', lambda _: request)
        value = dict(upload=str(uuid4()), stage='posting', posting_id=identity)
        client.fail_at = ''
        ads._step('key', value, {}, {}, 0)
        assert value['stage'] == 'waiting' and value['auto_recovery']['checkpoint'] == 'posting'
        jobs.jobs[identity]['future'].result(timeout=15)
        recovery.activate(value)
        ads._step('key', value, {}, {}, 0)
        assert value['stage'] == 'complete'
        complete = jobs.snapshot(identity)
        assert confirmed_ads(complete) == (3, 3)
        assert complete['ad_results'][0]['meta_ad_id'] == first
        assert complete['campaign_id'] == failed['campaign_id']
        assert complete['adset_id'] == failed['adset_id']
        assert client.calls.count('campaign') == client.calls.count('adset') == 1
        assert len(client.copy_ads) == 3
    finally:
        jobs.pool.shutdown(wait=True)


def test_retry_budget_never_turns_a_transient_failure_terminal(monkeypatch):
    monkeypatch.setattr(recovery.time, 'time', lambda: 10000)
    value = dict(stage='generating', upload=str(uuid4()), artifacts={'saved': {'hash': 'same'}})
    for attempt in range(1, 60):
        recovery.schedule(value, 'temporary outage')
        assert value['auto_recovery']['attempts'] == attempt
        assert 60 <= value['auto_recovery']['next_at']-10000 <= 900
        assert value['stage'] == 'waiting'
        recovery.activate(value)
    assert value['artifacts'] == {'saved': {'hash': 'same'}}


def test_legacy_retry_and_policy_refusal_are_distinct():
    blocked = dict(stage='failed', detail='Image provider moderation_blocked. Missing cover.')
    assert not recovery.legacy(blocked)
    assert blocked['stage'] == 'failed'
    transient = dict(stage='failed', detail='A dependency did not respond. Review the saved ad job.')
    assert recovery.legacy(transient)
    assert transient['resume_stage'] == 'preparing'


def test_pending_meta_write_is_observed_without_replaying(monkeypatch):
    import meta_posting_jobs
    import ads_companion_controls
    monkeypatch.setattr(ads_companion_controls, 'stopped', lambda _: False)
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    row = dict(status='AMBIGUOUS', ad_results=[{'posting_operations_v1': {'intent': {'state': 'pending'}}}])
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(snapshot=lambda _: row,
        resume=lambda _: pytest.fail('Must not replay an unknown write')))
    monkeypatch.setattr(ads, '_post_request', lambda _: pytest.fail('No inputs needed for read-only reconciliation'))
    value = dict(stage='posting', upload=str(uuid4()), posting_id='saved')
    ads._step('key', value, {}, {}, 0)
    assert value['auto_recovery']['code'] == 'reconciliation'
    assert value['posting_id'] == 'saved' and value['stage'] == 'waiting'


def test_completion_repair_keeps_collected_files_and_one_send_permit(monkeypatch):
    import ads_attachment_repair
    value = dict(stage='generating', upload=str(uuid4()), folder='/saved',
        chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+str(uuid4()),
        artifacts={'ad_copy.csv': {'hash': 'original'}}, response_ids={'ad_copy.csv': 'original'})
    recovery.schedule(value, 'generation interrupted', code='generation', mode='complete_missing')
    recovery.activate(value)
    assert value.pop('completion_needed')
    ads_attachment_repair.advance(value, {'transfer_failed': True, 'complete_missing': True})
    repair = value['attachment_repair']
    assert repair['mode'] == 'complete_missing' and 'ad_copy.csv' not in repair['names']
    assert ads_attachment_repair.advance(value, {'repair_claim': repair['id']})
    recovery.schedule(value, 'missing send acknowledgement')
    recovery.activate(value)
    assert value['attachment_repair']['id'] == repair['id']
    assert not ads_attachment_repair.advance(value, {'repair_claim': repair['id']})
    assert value['response_ids'] == {'ad_copy.csv': 'original'}


@pytest.mark.parametrize('status,lease,age,pending,expected', [
    ('FAILED', False, 0, False, True),
    ('FAILED', False, 0, True, False),
    ('AD_CREATED', False, 31, False, True),
    ('AD_CREATED', False, 1, False, False),
    ('AD_CREATED', True, 31, False, False),
    ('AD_CREATED', 'expired', 31, False, True),
    ('AD_CREATED', False, 31, True, False),
    ('COMPLETE', False, 31, False, False),
    ('AMBIGUOUS', False, 31, False, False),
    ('ABANDONED_EXTERNALLY', False, 31, False, False),
])
def test_real_sql_retry_fences_active_pending_and_terminal_jobs(store, monkeypatch, status, lease, age, pending, expected):
    from meta_posting_service import SupabasePostingStore
    from tests.test_meta_posting import request_for
    with store() as conn, conn.cursor() as cur:
        cur.execute("CREATE TABLE meta_posting_submissions(submission_id uuid PRIMARY KEY, request_fingerprint text, status text, ad_name text, destination_url text, image_checksum text, product_title text, ad_type text, safe_error text, lease_token uuid, lease_expires_at timestamptz, updated_at timestamptz DEFAULT now(), ad_results jsonb DEFAULT '[]')")
    @contextmanager
    def connect():
        with store() as conn:
            yield SimpleNamespace(cursor=conn.cursor, commit=lambda: None)
    backend = SimpleNamespace(connect=connect, ensure_ads_schema=lambda: None)
    monkeypatch.setattr(SupabasePostingStore, '_backend', lambda _: backend)
    posting = SupabasePostingStore(); request = request_for(submission_id=str(uuid4()))
    assert posting.reserve(request)
    journal = [{'posting_operations_v1': {'original-intent': {'state': 'pending' if pending else 'complete', 'result': 'saved-ad'}}}]
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE meta_posting_submissions SET status=%s, request_fingerprint='frozen', updated_at=now()-(%s * interval '1 minute'), lease_token=%s, lease_expires_at=now()+(%s * interval '1 minute'), ad_results=%s::jsonb WHERE submission_id=%s::uuid", (status, age, str(uuid4()) if lease else None, -1 if lease == 'expired' else 1, json.dumps(journal), request.submission_id))
    assert posting.reserve(request, retry=True) is expected
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid', (request.submission_id,))
        saved = cur.fetchone()
    assert saved['request_fingerprint'] == 'frozen'
    assert saved['ad_results'] == journal
    if expected:
        assert saved['status'] == 'VALIDATING' and saved['lease_token'] is None
        assert not posting.reserve(request, retry=True)


def test_cancelled_and_deleted_jobs_never_auto_resume(queued_store, monkeypatch):
    import ads_companion_controls
    for operation in ('cancel', 'delete'):
        result = {**brief(), 'country': 'Canada' if operation == 'delete' else 'USA'}
        job = queue.enqueue(USER, result, {'row': ROW})['id']
        value = read(queued_store, job)
        value.update(stage='failed', detail='A dependency did not respond.')
        ads.write(ads.PREFIX+job, value)
        ads_companion_controls.action(USER, job, operation)
    token = uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(queue, 'prepare', lambda _: pytest.fail('Stopped job must not resume'))
    assert ads.tick(token, {}) == {}


def test_recovery_cycle_reopens_only_after_confirmed_finished_response(monkeypatch):
    monkeypatch.setattr(recovery.time, 'time', lambda: 10000)
    value = dict(stage='generating', upload=str(uuid4()),
        attachment_repair=dict(id='original-permit',state='submitted',attempt=2,submitted_at=8000,start_activity='before'),
        last_finished_activity='after', last_finished_at=9000)
    recovery.schedule(value, 'files still unavailable', code='attachments')
    assert value['auto_recovery']['next_at'] == 10900
    recovery.activate(value)
    assert 'attachment_repair' not in value
    assert value['attachment_repair_history'][0]['id'] == 'original-permit'
    value['attachment_repair'] = dict(id='uncertain-permit',state='sending',created_at=8000,attempt=1)
    recovery.schedule(value, 'acknowledgement unavailable')
    recovery.activate(value)
    assert value['attachment_repair']['id'] == 'uncertain-permit'
    assert value['attachment_repair']['state'] == 'sending'


def test_existing_failed_job_is_recovered_by_scheduler_without_operator_action(queued_store, monkeypatch):
    job = queue.enqueue(USER, brief(), {'row': ROW})['id']
    value = read(queued_store, job)
    value.update(stage='failed', detail='A dependency did not respond. Review the saved ad job.')
    ads.write(ads.PREFIX+job, value)
    token = uploads.pair({'id': 'desktop'})
    monkeypatch.setattr(queue, 'prepare', lambda _: dict(stage='opening', prompt='saved brief'))
    assert ads.tick(token, {})['job']['id'] == job
    saved = read(queued_store, job)
    assert saved['stage'] == 'opening' and saved['auto_recovery']['attempts'] == 1
    assert saved['requester'] == value['requester']
