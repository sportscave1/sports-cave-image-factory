from pathlib import Path
import json
from uuid import uuid4

import pytest

import product_upload_staff_queue as queue
from test_auto_editions_jobs import database


@pytest.fixture
def store(database, monkeypatch):
    jobs, cursor = database
    sql = Path(__file__).resolve().parents[1] / 'migrations' / '20261117110000_product_upload_staff_queue.sql'
    cursor.execute(sql.read_text(encoding='utf8'))
    cursor.execute(sql.with_name('20261118070000_product_upload_manual_restart.sql').read_text(encoding='utf8'))
    cursor.execute('CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    monkeypatch.setattr(queue, 'connect', jobs.connect)
    monkeypatch.setattr('design_review_page.final_psd', lambda source: True)
    return jobs.connect


def submit(actor, revision='A'):
    return queue.enqueue({'id': actor}, {'id': 'id:original', 'rev': revision}, 'Design', 'NFL Wall Art')


def test_header_display_does_not_reconcile_or_write_stalled_jobs(store):
    key = submit('staff-one')
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_staff_jobs SET stage=4,updated_at=now()-interval '40 minutes' WHERE id=%s", (key,))
    queue.list_jobs('staff-one', display_only=True)
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT stage FROM product_upload_staff_jobs WHERE id=%s', (key,))
        assert cur.fetchone()['stage'] == 4


def test_upload_order_ignores_pending_ads_and_prefers_latest_completion(store):
    import design_publish_ad
    old=submit('staff','old');recent=submit('staff','recent');failed=submit('staff','failed')
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_staff_jobs SET stage=6,updated_at=now()-interval '1 day' WHERE id=%s",(old,))
        cur.execute("UPDATE product_upload_staff_jobs SET stage=6,updated_at=now()-interval '1 hour' WHERE id=%s",(recent,))
        cur.execute("UPDATE product_upload_staff_jobs SET stage=7 WHERE id=%s",(failed,))
        cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',
            (design_publish_ad.PREFIX+str(old),json.dumps(dict(upload=str(old),stage='generating'))))
    for actor in (None,'staff'):
        rows=queue.list_jobs(actor,display_only=True)['jobs']
        assert [r['id'] for r in rows]==[str(recent),str(old),str(failed)]
        assert rows[1]['ad']['active']
    current=submit('staff','current')
    with store() as conn, conn.cursor() as cur:
        cur.execute('UPDATE product_upload_staff_jobs SET stage=2 WHERE id=%s',(current,))
    assert queue.list_jobs(display_only=True)['jobs'][0]['id']==str(current)


def test_offline_requests_are_durable_private_and_claimed_once(store, monkeypatch):
    first = submit('staff-one')
    assert submit('staff-two') == first
    assert submit('staff-one') == first
    second = submit('staff-one', 'B')
    assert queue.list_jobs('unrelated')['jobs'] == []
    assert queue.list_jobs('staff-two')['jobs'][0]['stage'] == 0
    assert queue.list_jobs('staff-one')['online'] is False
    with pytest.raises(PermissionError):
        queue.desktop_tick('x' * 43)

    token = queue.pair({'id': 'desktop-admin'})
    with pytest.raises(ValueError):
        queue.pair({'id': 'different-admin'})
    assert str(queue.tick(token, {})['job']['id']) == str(first)
    assert str(queue.tick(token, {})['job']['id']) == str(first)
    assert queue.list_jobs('staff-one')['online']
    assert queue.worker_job(str(first), 'staff-one') is None

    queue.advance(first, 'desktop-admin', 1, intake=uuid4(), allowed=[1])
    queue.advance(first, 'desktop-admin', 3, allowed=[1, 2])
    queue.advance(first, 'desktop-admin', 2)
    assert queue.worker_job(str(first), 'desktop-admin')['stage'] == 3
    queue.advance(first, 'desktop-admin', 4)
    verify_calls = []
    monkeypatch.setattr(queue, 'verify', lambda job: verify_calls.append(job))
    queue.tick(token, {'id': str(first), 'state': 'submitted'})
    assert verify_calls
    assert queue.list_jobs('staff-two')['jobs'][0]['stage'] == 5
    queue.tick(token, {'id': str(first), 'state': 'blocked', 'reason': 'PSD mapping unavailable.'})
    stopped = queue.list_jobs('staff-two')['jobs'][0]
    assert stopped['stage'] == 7
    assert stopped['detail'] == 'PSD mapping unavailable.'
    assert queue.tick(token, {})['job']['id'] == str(second)


def test_success_requires_live_product_and_exact_mapped_master(store, monkeypatch):
    import product_upload_intake
    import product_upload_mapping
    import product_upload_services
    import psd_directory
    import psd_mapping_store
    import shopify_sync
    from product_upload_identity import tag

    key = submit('staff')
    intake = uuid4()
    token = queue.pair({'id': 'desktop'})
    queue.tick(token, {})
    queue.advance(key, 'desktop', 1, intake=intake)
    queue.advance(key, 'desktop', 4)
    pid = 'gid://shopify/Product/100'
    path = psd_directory.ROOT + '/Master.psd'
    current = {'id': 'id:original', 'content_hash': 'exact', 'path_display': path}
    mapping = {'dropbox_file_id': 'id:original', 'verified': True, 'path': path}
    listing = {'shopify_product_id': pid, 'status': 'DRAFT', 'tags': [tag(intake)],
               'online_store_url': 'https://example.com/products/design'}

    with store() as conn, conn.cursor() as cur:
        cur.execute('CREATE TABLE product_psd_mappings (shopify_product_gid text, dropbox_file_id text)')
        cur.execute('INSERT INTO product_psd_mappings VALUES (%s,%s)', (pid, 'id:original'))

    monkeypatch.setattr(product_upload_intake.Intakes, 'read', lambda *args: {'data': {'source': {'content_hash': 'exact'}}})
    monkeypatch.setattr(product_upload_mapping, 'read_edition', lambda *args: {'id': 1})
    monkeypatch.setattr(psd_mapping_store.STORE, 'read_one', lambda *args: mapping)
    monkeypatch.setattr(shopify_sync, 'fetch_product_by_shopify_id', lambda *args: listing)
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: type('Dropbox', (), {'metadata_if_present': lambda *args: current})())

    queue.tick(token, {'id': str(key), 'state': 'submitted'})
    assert queue.list_jobs('staff')['jobs'][0]['stage'] == 5
    listing['status'] = 'ACTIVE'
    listing['tags'] = []
    queue.tick(token, {})
    assert queue.list_jobs('staff')['jobs'][0]['stage'] == 5
    listing['tags'] = [tag(intake)]
    current['content_hash'] = 'different'
    queue.tick(token, {})
    assert queue.list_jobs('staff')['jobs'][0]['stage'] == 5
    current['content_hash'] = 'exact'
    queue.tick(token, {})
    done = queue.list_jobs('staff')['jobs'][0]
    assert done['stage'] == 6
    assert done['storefront'] == listing['online_store_url']


def test_many_publish_requests_wait_and_advance_after_failure_or_verified_success(store, monkeypatch):
    import design_review_page
    monkeypatch.setattr(design_review_page, 'final_psd', lambda source: True)
    keys = [queue.enqueue({'id':'staff'}, {'id':f'id:art-{n}','rev':'R1'}, f'Artwork {n}', 'Basketball') for n in range(5)]
    token = queue.pair({'id':'desktop'})
    first = queue.tick(token, {})['job']['id']
    assert first == str(keys[0])
    assert len(queue.list_jobs('staff')['jobs']) == 5
    assert queue.tick(token, {})['job']['id'] == first
    queue.advance(keys[0], 'desktop', 7, 'Fixture failure', allowed=[1])
    second = queue.tick(token, {})['job']['id']
    assert second == str(keys[1])
    queue.advance(keys[1], 'desktop', 5, allowed=[1])
    monkeypatch.setattr(queue, 'verify', lambda job: queue.advance(job['id'], 'desktop', 6, allowed=[5]))
    queue.tick(token, {})
    assert queue.tick(token, {})['job']['id'] == str(keys[2])


@pytest.mark.parametrize('outcome', ['completed', 'blocked'])
def test_pause_finishes_current_and_holds_next_until_play(store, monkeypatch, outcome):
    first = submit('staff', 'A')
    second = submit('staff', 'B')
    token = queue.pair({'id': 'desktop'})
    assert queue.settings() == {'enabled': True}
    assert queue.tick(token, {})['job']['id'] == str(first)
    assert queue.settings(False) == {'enabled': False}
    # Ongoing preparation is still returned to the companion while paused.
    assert queue.tick(token, {})['job'] == {'id': str(first), 'stage': 1}
    queue.advance(first, 'desktop', 4)
    verified = []
    def finish(job):
        verified.append(str(job['id']))
        if outcome == 'completed':
            queue.advance(job['id'], 'desktop', 6, storefront='https://example.test/product', allowed=[5])
    monkeypatch.setattr(queue, 'verify', finish)
    result = queue.tick(token, {'id': str(first), 'state': 'submitted'})
    assert verified == [str(first)]
    if outcome == 'blocked':
        assert result['job']['stage'] == 5
        queue.tick(token, {'id': str(first), 'state': 'blocked', 'reason': 'Review needed'})
    assert queue.tick(token, {}) == {}
    assert queue.tick(token, {}) == {}
    assert queue.settings() == {'enabled': False}
    rows = {j['id']: j for j in queue.list_jobs()['jobs']}
    assert rows[str(first)]['stage'] == (6 if outcome == 'completed' else 7)
    assert rows[str(second)]['stage'] == 0
    # Re-pairing/restarting the companion cannot clear the durable pause.
    token = queue.pair({'id': 'desktop'})
    assert queue.tick(token, {}) == {}
    queue.settings(True)
    assert queue.tick(token, {})['job']['id'] == str(second)
    assert queue.tick(token, {})['job']['id'] == str(second)


def test_pause_before_pairing_holds_first_upload(store):
    key = submit('staff')
    queue.settings(False)
    token = queue.pair({'id': 'desktop'})
    assert queue.tick(token, {}) == {}
    queue.settings(True)
    assert queue.tick(token, {})['job']['id'] == str(key)


def test_manual_reset_preserves_upload_and_rejects_old_events(store, monkeypatch):
    key = submit('staff')
    token = queue.pair({'id': 'desktop'})
    assert queue.tick(token, {})['job']['id'] == str(key)
    queue.advance(key, 'desktop', 7, 'Generation failed', allowed=[1])
    stopped = queue.list_jobs('staff')['jobs'][0]
    assert stopped['restartable']
    # Polling and re-enqueue do not reset a failed job.
    assert submit('staff') == key
    assert queue.tick(token, {}) == {}
    with pytest.raises(PermissionError):
        queue.restart(key, {'id': 'unrelated'}, stopped['updated_at'])
    queue.settings(False)
    restarted = queue.restart(key, {'id': 'staff'}, stopped['updated_at'])
    assert restarted['id'] == str(key) and restarted['stage'] == 0
    assert queue.tick(token, {}) == {}  # reset honours Pause
    with pytest.raises(ValueError):
        queue.restart(key, {'id': 'staff'}, stopped['updated_at'])
    queue.settings(True)
    new = queue.tick(token, {'id': str(key), 'state': 'blocked'})['job']
    assert new['id'] != str(key) and new['stage'] == 1
    assert queue.worker_job(str(key), 'desktop') is None
    assert queue.worker_job(new['id'], 'desktop')
    queue.advance(key, 'desktop', 7, 'Stale tab')
    assert queue.worker_job(new['id'], 'desktop')['stage'] == 1
    queue.advance(new['id'], 'desktop', 6, allowed=[1])
    done = queue.list_jobs('staff')['jobs'][0]
    assert not done['restartable']
    with pytest.raises(ValueError):
        queue.restart(key, {'id': 'staff'}, done['updated_at'])


def test_reset_retains_intake_product_files_and_records_prior_error(store):
    key = submit('staff')
    token = queue.pair({'id': 'desktop'})
    queue.tick(token, {})
    intake = uuid4()
    data = dict(source={'id': 'id:original', 'rev': 'A'}, product_gid='gid://shopify/Product/100',
                mockup_saves={'receipt': 'verified-files'}, staff_mapping={'job': str(key)},
                server_artwork={'state':'Ready'}, mockups_exported=True, copied=True,
                upload_operation={'output':{'folder':'/Old output'}, 'sync_map': {'staff_job': str(key), 'lease': 'old',
                                              'moved': {'id': 'id:original'}, 'completed': ['moved']}})
    with store() as conn, conn.cursor() as cur:
        cur.execute('CREATE TABLE product_upload_intakes(id uuid PRIMARY KEY,data jsonb,updated_at timestamptz DEFAULT now())')
        cur.execute('INSERT INTO product_upload_intakes(id,data) VALUES (%s,%s::jsonb)', (intake, json.dumps(data)))
    queue.advance(key, 'desktop', 1, intake=intake)
    queue.advance(key, 'desktop', 7, 'Image generation rejected', allowed=[1])
    stopped = queue.list_jobs('staff')['jobs'][0]
    queue.restart(key, {'id': 'staff'}, stopped['updated_at'])
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s', (intake,))
        saved = cur.fetchone()['data']
        cur.execute('SELECT * FROM product_upload_staff_jobs WHERE id=%s', (key,))
        job = cur.fetchone()
    assert str(job['intake_id']) == str(intake)
    assert saved['source'] == data['source']
    assert saved['product_gid'] == data['product_gid']
    assert 'mockup_saves' not in saved
    assert saved['staff_upload_restarts'][0]['retired_outputs']['mockup_saves'] == data['mockup_saves']
    assert saved['staff_upload_restarts'][0]['retired_outputs']['output'] == data['upload_operation']['output']
    assert 'server_artwork' not in saved and 'output' not in saved['upload_operation']
    assert not saved['mockups_exported'] and not saved['copied']
    assert saved['staff_full_restart'] == str(job['dispatch_id'])
    assert saved['design_review']['decision'] == 'approved'
    assert saved['staff_upload_attempt'] == str(job['dispatch_id'])
    assert saved['staff_upload_restarts'][0]['reason'] == 'Image generation rejected'
    assert 'staff_mapping' not in saved  # re-armed for the new delivery only
    task = saved['upload_operation']['sync_map']
    assert task['staff_job'] == str(job['dispatch_id'])
    assert task['moved'] == {'id': 'id:original'} and task['completed'] == ['moved']
    assert 'lease' not in task


def test_clicked_attempt_clears_only_old_errors_once():
    from product_upload_jobs import Jobs
    jobs = Jobs()
    try:
        failed = ('desktop', 'upload', 'prepare')
        ready = ('desktop', 'upload', 'generate')
        jobs.jobs[failed] = {'state': 'Failed'}
        jobs.jobs[ready] = {'state': 'Ready'}
        jobs.begin_staff_attempt('upload', 'desktop', 'clicked-attempt')
        assert failed not in jobs.jobs and ready in jobs.jobs
        jobs.jobs[failed] = {'state': 'Failed'}
        jobs.begin_staff_attempt('upload', 'desktop', 'clicked-attempt')
        assert failed in jobs.jobs  # rerun/poll cannot retry this new failure
    finally:
        jobs.pool.shutdown(wait=False)


def test_manual_cancel_is_private_durable_and_releases_next_job(store):
    first, second = submit('staff', 'A'), submit('staff', 'B')
    token = queue.pair({'id': 'desktop'})
    queue.tick(token, {})
    before = next(j for j in queue.list_jobs('staff')['jobs'] if j['id'] == str(first))
    with pytest.raises(PermissionError):
        queue.cancel(first, {'id': 'unrelated'}, before['updated_at'])
    with pytest.raises(ValueError):
        queue.cancel(first, {'id': 'staff'}, '2000-01-01T00:00:00+00:00')
    stopped = queue.cancel(first, {'id': 'staff'}, before['updated_at'])
    assert stopped['cancelled'] and not stopped['cancellable'] and stopped['label'] == 'Cancelled'
    assert queue.cancel(first, {'id': 'staff'}, before['updated_at'])['cancelled']
    assert queue.worker_job(str(first), 'desktop') is None
    queue.advance(first, 'desktop', 5, 'Late old report')
    result = queue.tick(token, {'id': str(first), 'state': 'submitted'})
    assert result['stop'] == {'id': str(first)}
    assert result['job']['id'] == str(second)
    queue.advance(second, 'desktop', 6)
    done = next(j for j in queue.list_jobs('staff')['jobs'] if j['id'] == str(second))
    with pytest.raises(ValueError):
        queue.cancel(second, {'id':'staff'}, done['updated_at'])


def test_cancel_blocks_persisted_intake_writes_and_explicit_restart_clears_it(store):
    from product_upload_intake import Intakes
    key = submit('staff')
    token = queue.pair({'id':'desktop'})
    queue.tick(token, {})
    intake = uuid4()
    with store() as conn, conn.cursor() as cur:
        cur.execute('''CREATE TABLE product_upload_intakes(id uuid PRIMARY KEY,actor_id text,
            mode text DEFAULT 'NEW',data jsonb,updated_at timestamptz DEFAULT now())''')
        cur.execute('INSERT INTO product_upload_intakes(id,actor_id,data) VALUES(%s,%s,%s::jsonb)',
                    (intake, 'desktop', json.dumps({'source':{'id':'id:original','rev':'A'}})))
    queue.advance(key, 'desktop', 1, intake=intake)
    before = queue.list_jobs('staff')['jobs'][0]
    stopped = queue.cancel(key, {'id':'staff'}, before['updated_at'])
    with pytest.raises(ValueError, match='cancelled'):
        with Intakes(store).locked(str(intake), 'desktop'):
            pytest.fail('Cancelled work must not acquire a writable intake')
    queue.restart(key, {'id':'staff'}, stopped['updated_at'])
    with Intakes(store).locked(str(intake), 'desktop') as (row, _):
        assert not row['data'].get('staff_upload_cancelled')


def test_slow_submitted_upload_remains_pending_without_false_failure(store, monkeypatch):
    key = submit('staff')
    token = queue.pair({'id':'desktop'})
    queue.tick(token, {})
    monkeypatch.setattr(queue, 'verify', lambda job: None)
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_staff_jobs SET stage=5,updated_at=now()-interval '11 minutes' WHERE id=%s", (key,))
    warning = queue.list_jobs('staff')['jobs'][0]
    assert warning['stalled'] and warning['cancellable'] and warning['stage'] == 5
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_staff_jobs SET updated_at=now()-interval '31 minutes' WHERE id=%s", (key,))
    expired = queue.list_jobs('staff')['jobs'][0]
    assert expired['stage'] == 5 and expired['stalled']
    assert 'Waiting for verified progress' in expired['label']
    assert not expired['restartable']
    result = queue.tick(token, {'id': str(key), 'state': 'submitted'})
    assert result['job']['stage'] == 5


def test_verification_failure_is_visible_and_does_not_extend_timeout(store, monkeypatch):
    key = submit('staff')
    token = queue.pair({'id':'desktop'})
    queue.tick(token, {})
    queue.advance(key, 'desktop', 5)
    before = queue.list_jobs('staff')['jobs'][0]['updated_at']
    def unavailable(job):
        raise RuntimeError('synthetic provider failure')
    monkeypatch.setattr(queue, 'verify', unavailable)
    queue.tick(token, {})
    after = queue.list_jobs('staff')['jobs'][0]
    assert 'Could not verify' in after['detail'] and after['updated_at'] == before
    monkeypatch.setattr(queue, 'verify', lambda job: queue.advance(job['id'], 'desktop', 6))
    assert queue.tick(token, {'id':str(key), 'state':'blocked', 'reason':'late error'}) == {}
    assert queue.list_jobs('staff')['jobs'][0]['stage'] == 6


def test_uncertain_handoff_releases_slot_without_republishing_or_losing_source(store):
    first = submit('staff', 'blocked')
    second = submit('staff', 'next')
    token = queue.pair({'id': 'desktop'})
    assert queue.tick(token, {})['job']['id'] == str(first)
    queue.advance(first, 'desktop', 4)
    event = dict(id=str(first), state='uncertain')
    queue.tick(token, event)
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_staff_jobs SET updated_at=now()-interval '31 minutes' WHERE id=%s", (first,))
    assert queue.tick(token, event) == {'stop': {'id': str(first)}}
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM product_upload_staff_jobs WHERE id=%s', (first,))
        row = cur.fetchone()
        assert row['stage'] == 7
        assert 'Queue slot released' in row['message']
        assert row['source_id'] == 'id:original' and row['source_rev'] == 'blocked'
    assert queue.tick(token, {})['job']['id'] == str(second)
    assert queue.tick(token, event)['job']['id'] == str(second)  # Late old events cannot stop next job.


def test_completed_blocker_after_uncertain_send_releases_upload_slot(store):
    first = submit('staff', 'blocked')
    second = submit('staff', 'next')
    token = queue.pair({'id': 'desktop'})
    queue.tick(token, {})
    queue.advance(first, 'desktop', 4)
    result = queue.tick(token, dict(id=str(first), state='blocked',
                                  reason='ChatGPT reported an upload failure: MODERATION'))
    assert result == {'stop': {'id': str(first)}}
    assert queue.tick(token, {})['job']['id'] == str(second)


def test_uncertain_receipt_recovers_only_from_verified_published_package(store, monkeypatch):
    import product_upload_staff_mapping as mapping
    first = submit('staff')
    token = queue.pair({'id': 'desktop'})
    queue.tick(token, {})
    queue.advance(first, 'desktop', 4)
    ready = []
    monkeypatch.setattr(mapping, 'publication_ready', lambda connect, job: bool(ready))
    verified = []
    monkeypatch.setattr(queue, 'verify', lambda job: verified.append(job['id']))
    event = dict(id=str(first), state='uncertain')
    assert queue.tick(token, event)['job']['stage'] == 4
    assert not verified
    ready.append(True)
    assert queue.tick(token, event)['job']['stage'] == 5
    assert verified == [first]
    monkeypatch.setattr(queue, 'verify', lambda job: queue.advance(job['id'], 'desktop', 6, allowed=[5]))
    assert queue.tick(token, event) == {}
    assert queue.list_jobs('staff')['jobs'][0]['stage'] == 6


def test_full_reset_clears_ready_mockups_once_without_automatic_retries():
    from product_upload_jobs import Jobs
    jobs=Jobs()
    try:
        ready=('desktop','upload','generate')
        jobs.jobs[ready]={'state':'Ready'}
        jobs.begin_staff_attempt('upload','desktop','full-click',full=True)
        assert ready not in jobs.jobs
        jobs.jobs[ready]={'state':'Failed'}
        jobs.begin_staff_attempt('upload','desktop','full-click',full=True)
        assert ready in jobs.jobs
    finally:
        jobs.pool.shutdown(wait=False)


def test_lightweight_desktop_heartbeat(store):
    assert queue.desktop_online() is False
    token = queue.pair({'id': 'desktop'})
    assert queue.desktop_online() is False
    queue.desktop_tick(token)
    assert queue.desktop_online() is True
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE product_upload_desktop SET seen_at=now()-interval '96 seconds'")
    assert queue.desktop_online() is False


def test_publish_now_resumes_paused_uploads_and_claims_exact_request_once(store, monkeypatch):
    monkeypatch.setattr(queue, 'can_control_queues', lambda user: user['id'] == 'admin')
    token = queue.pair({'id': 'desktop'})
    queue.settings(False)
    key = queue.enqueue({'id':'admin'}, {'id':'id:publish','rev':'R1'}, 'Publish now', 'NBA', start=True)
    assert queue.settings() == {'enabled': True}
    assert queue.tick(token, {})['job']['id'] == str(key)
    assert queue.enqueue({'id':'admin'}, {'id':'id:publish','rev':'R1'}, 'Publish now', 'NBA', start=True) == key
    assert queue.tick(token, {})['job']['id'] == str(key)
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM product_upload_staff_jobs')
        assert cur.fetchone()['n'] == 1


def test_bulk_queue_and_nonadministrator_publish_preserve_admin_pause(store, monkeypatch):
    monkeypatch.setattr(queue, 'can_control_queues', lambda user: user['id'] == 'admin')
    token = queue.pair({'id':'desktop'})
    queue.settings(False)
    queue.enqueue({'id':'admin'}, {'id':'id:bulk','rev':'R1'}, 'Bulk request', 'NBA')
    key = queue.enqueue({'id':'staff'}, {'id':'id:staff','rev':'R1'}, 'Staff request', 'NBA', start=True)
    assert queue.settings() == {'enabled': False}
    assert queue.tick(token, {}) == {}
    assert queue.requested_status({'id':'staff'}, str(key))['job']['stage'] == 0


def test_publish_queue_resume_rolls_back_with_failed_request(store, monkeypatch):
    import design_publish_ad as ad
    monkeypatch.setattr(queue, 'can_control_queues', lambda user: True)
    monkeypatch.setattr(ad, 'check_request', lambda *args: ('NBA', 'AUS'))
    def unavailable(*args):
        raise RuntimeError('Synthetic request save failure')
    monkeypatch.setattr(ad, 'enqueue', unavailable)
    queue.settings(False)
    with pytest.raises(RuntimeError, match='Synthetic'):
        queue.enqueue({'id':'admin'}, {'id':'id:atomic','rev':'R1'}, 'Atomic request', 'NBA', ad_country='AUS', start=True)
    assert queue.settings() == {'enabled': False}
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM product_upload_staff_jobs')
        assert cur.fetchone()['n'] == 0


def test_requested_upload_status_is_private_and_survives_header_history_limit(store, monkeypatch):
    monkeypatch.setattr(queue, 'can_control_queues', lambda user: user['id'] == 'admin')
    key = submit('owner')
    for n in range(21):
        submit('owner', str(n))
    assert str(key) not in {job['id'] for job in queue.list_jobs('owner',display_only=True)['jobs']}
    assert queue.requested_status({'id':'owner'}, key)['job']['id'] == str(key)
    assert queue.requested_status({'id':'admin'}, key)['job']['id'] == str(key)
    with pytest.raises(PermissionError):
        queue.requested_status({'id':'other'}, key)


def test_requested_status_route_bypasses_warming_history_without_leaking_requests(store, monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import files_upload_api
    monkeypatch.setattr(queue, 'can_control_queues', lambda user: False)
    key = submit('owner')
    active = {'id':'owner'}
    monkeypatch.setattr(files_upload_api, '_request_user', lambda *args, **kwargs: dict(active))
    monkeypatch.setattr(queue, '_header_display', lambda _: dict(display_state='loading', jobs=[]))
    app = Starlette(routes=[Route('/api/staff-product-uploads/status',queue.status_route)])
    with TestClient(app) as client:
        query = dict(display='1',job_id=str(key))
        response = client.get('/api/staff-product-uploads/status',params=query)
        assert response.status_code == 200, response.text
        assert response.json()['display_state'] == 'ready'
        assert response.json()['jobs'][0]['id'] == str(key)
        assert response.json()['queues']['upload']['waiting'] is None
        active['id'] = 'other'
        assert client.get('/api/staff-product-uploads/status',params=query).status_code == 403
    with store() as conn, conn.cursor() as cur:
        cur.execute('SELECT stage FROM product_upload_staff_jobs WHERE id=%s',(key,))
        assert cur.fetchone()['stage'] == 0  # Status reads never start or publish work.
