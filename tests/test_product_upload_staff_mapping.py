"""Publish Now through the real mapping transaction with synthetic Shopify and Dropbox."""
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager

import pytest

import os_accounts
import product_upload_services
import product_upload_staff_queue as queue
import shopify_sync
from product_upload_chat_handoff import CORE, prepare
from product_upload_identity import tag
from product_upload_package import ORDER
from product_upload_staff_mapping import arm
from tests.test_product_upload_mapping import (
    ADMIN, PID, count, database, env, read_edition, restore_provider_boundaries, setup,
)


def test_reset_rearms_mapping_version_without_losing_moved_psd(monkeypatch):
    import product_upload_staff_mapping as mapping
    attempt = str(uuid4())
    source = {'id': 'id:original', 'rev': 'r1'}
    task = {'staff_job': attempt, 'state': 'Mapped', 'source_version': 'old', 'moved': source}
    row = {'data': {'source': source, 'staff_upload_attempt': attempt,
                    'upload_operation': {'sync_map': task}}, 'mode': 'LIVE'}
    @contextmanager
    def locked(*args):
        yield row, None
    monkeypatch.setattr(mapping.Intakes, 'locked', locked)
    monkeypatch.setattr(mapping, 'require_job', lambda *a, **kw: {'stage': 1})
    handoff = {'job': attempt, 'version': 'fresh', 'source': source, 'mode': 'LIVE'}
    assert mapping.arm(lambda: None, 'upload', 'actor', handoff)
    assert task['source_version'] == 'fresh'
    assert task['state'] == 'Mapped' and task['moved'] == source


@pytest.mark.parametrize('lost_move_response', [False, True])
def test_publish_now_hands_off_exact_revision_and_queues_auto_editions(env, monkeypatch, lost_move_response):
    service, intake_id, original, listing = setup(env, arrived=False)
    store, sql, provider = env
    sql.execute((Path(__file__).resolve().parents[1] /
                 'migrations/20261117110000_product_upload_staff_queue.sql').read_text(encoding='utf-8'))
    sql.execute((Path(__file__).resolve().parents[1] /
                 'migrations/20261118070000_product_upload_manual_restart.sql').read_text(encoding='utf-8'))
    monkeypatch.setattr(queue, 'connect', store.connect)
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: provider)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda key: ADMIN if key == ADMIN['id'] else None)
    monkeypatch.setattr(shopify_sync, 'get_config', lambda: {'store_domain': 'fixture.myshopify.com'})
    monkeypatch.setattr('prompt_store.get_prompt', lambda key, default, **kwargs: default)
    job_id = queue.enqueue({'id': 'staff-fixture'}, original, 'Approved fixture', 'Baseball')
    token = queue.pair(ADMIN)
    assert queue.tick(token, {})['job']['id'] == str(job_id)
    queue.advance(job_id, ADMIN['id'], 1, intake=intake_id)

    folder = '/Fixture/Baseball/Approved fixture'
    manifest = [dict(slot_id=role, sort_position=position, output_filename=role + '.webp')
                for position, role in enumerate(ORDER, 1)]
    completed = []
    for item in manifest:
        name = item['output_filename']
        path = f'{folder}/WEBP/{name}'
        info = dict(id='id:' + name, rev='webp-revision', content_hash='c' * 64,
                    size=45, path_display=path, name=name)
        if item['slot_id'] in CORE:
            provider.files[path] = info
            completed.append(dict(relative_path='WEBP/' + name, metadata=info))
    receipt = dict(destination=folder, successes=completed, export_fingerprint='fixture',
                   generation_receipt='generation')
    result = dict(product_image_manifest=manifest, product_name='Approved fixture', sport_category='Baseball')
    with store.locked(intake_id, ADMIN['id']) as (row, cur):
        # ChatGPT saves the three lifestyle files outside the regular Save All UI.
        row['data']['mockups_exported'] = False
    row = store.read(intake_id, ADMIN['id'])
    handoff = prepare(result, row, receipt, 'Exact saved scenes.', staff_job=str(job_id))
    prompt = handoff['prompt']
    saved = handoff['staff_mapping']
    assert saved['ready_tag'] in prompt
    assert 'Original PSD identity:' not in prompt and 'Use Add / Attach PSD' not in prompt
    assert 'Upload Companion owns this step' in prompt
    assert 'never during create' in prompt
    assert 'Original PSD identity:' in prepare(result, row, receipt, 'Exact saved scenes.')['prompt']
    with pytest.raises(ValueError, match='no longer owns'):
        arm(store.connect, intake_id, ADMIN['id'], dict(saved, job=str(uuid4())))
    assert arm(store.connect, intake_id, ADMIN['id'], saved)
    queue.advance(job_id, ADMIN['id'], 4)
    assert arm(store.connect, intake_id, ADMIN['id'], saved)

    listing['images'] = [dict(id='gid://shopify/MediaImage/' + str(i), url=f'https://fixture/{i}.webp')
                         for i in range(8)]
    assert tag(intake_id) in listing['tags']
    monkeypatch.setattr(shopify_sync, 'fetch_catalog_page', lambda **kw: {'products': [listing]})
    queue.tick(token, {'id': str(job_id), 'state': 'submitted'})
    assert queue.list_jobs('staff-fixture')['jobs'][0]['stage'] == 5
    assert not provider.api.move_path.called

    listing['tags'].append(saved['ready_tag'])
    queue.tick(token, {})
    progress = queue.list_jobs('staff-fixture')['jobs'][0]
    assert progress['stage'] == 5 and progress['percent'] == 96
    assert 'waiting for Edition Ops' in progress['detail']
    assert not provider.api.move_path.called
    service.register(listing, 200)  # Simulated normal webhook registration.
    before = read_edition(store.connect, PID)
    queue.tick(token, {})
    assert 'waiting for the complete Dropbox' in queue.list_jobs('staff-fixture')['jobs'][0]['detail']
    assert not provider.api.move_path.called

    for item in manifest:
        name = item['output_filename']
        path = f'{folder}/WEBP/{name}'
        provider.files.setdefault(path, dict(id='id:' + name, rev='new', content_hash='a' * 64,
                                             size=90, path_display=path, name=name))
    if lost_move_response:
        original_move = provider.api.move_path.side_effect

        def lose_response(*args, **kwargs):
            original_move(*args, **kwargs)
            raise ConnectionError('Simulated loss after Dropbox moved the file.')

        provider.api.move_path.side_effect = lose_response
        queue.tick(token, {})
        done = queue.list_jobs('staff-fixture')['jobs'][0]
        assert done['stage'] == 5 and 'Moving PSD failed' in done['detail']
        assert count(sql, 'product_psd_mappings') == 0
        assert count(sql, 'auto_edition_onboarding') == 0
        provider.api.move_path.side_effect = original_move
    queue.tick(token, {})
    done = queue.list_jobs('staff-fixture')['jobs'][0]
    assert done['stage'] == 6 and done['percent'] == 100
    assert done['storefront'] == listing['online_store_url'] and 'Auto Editions' in done['detail']
    assert provider.api.move_path.call_count == 1
    mapping = service.mappings.read_one(PID)
    assert mapping['verified'] and mapping['dropbox_file_id'] == original['id']
    assert mapping['file_path'].endswith('/03_DESIGNS-LIVE-ONLINE-UPLOADED/' + original['name'])
    sql.execute('SELECT product_gid, file_id, status, source FROM auto_edition_onboarding')
    job = sql.fetchone()
    assert (job['product_gid'], job['file_id'], job['status']) == (PID, original['id'], 'Awaiting preparation')
    assert job['source']['content_hash'] == original['content_hash']
    assert count(sql, 'auto_edition_onboarding') == 1
    assert read_edition(store.connect, PID) == before
    assert service.status(intake_id, ADMIN)['state'] == 'Mapped'
    assert queue.tick(token, {}) == {}
    assert provider.api.move_path.call_count == 1
