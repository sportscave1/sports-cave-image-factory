from pathlib import Path
from uuid import uuid4

import pytest

import product_upload_staff_queue as queue
from test_auto_editions_jobs import database


@pytest.fixture
def store(database, monkeypatch):
    jobs, cursor = database
    sql = Path(__file__).resolve().parents[1] / 'migrations' / '20261117110000_product_upload_staff_queue.sql'
    cursor.execute(sql.read_text(encoding='utf8'))
    cursor.execute('CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    monkeypatch.setattr(queue, 'connect', jobs.connect)
    monkeypatch.setattr('design_review_page.final_psd', lambda source: True)
    return jobs.connect


def submit(actor, revision='A'):
    return queue.enqueue({'id': actor}, {'id': 'id:original', 'rev': revision}, 'Design', 'NFL Wall Art')


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
