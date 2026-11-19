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


@pytest.mark.parametrize('refresh,old_mapping,lost_move_response',
    [(refresh, old, lost) for refresh, old in [(False, None), (True, None), (True, 'different'), (True, 'same')]
     for lost in [False, True, 'already_moved']] + [(True, fault, False) for fault in ['changed', 'busy', 'wrong_target']])
def test_publish_now_hands_off_exact_revision_and_queues_auto_editions(env, monkeypatch, lost_move_response, refresh, old_mapping):
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
        if refresh:
            row['mode'] = 'UPDATE'
            row['data'].update(smart_upload=True, metadata={
                'upload_intent': 'existing_product_refresh', 'shopify_product_id': PID,
                'design_origin': 'designs_to_refresh',
            })
    row = store.read(intake_id, ADMIN['id'])
    if old_mapping:
        sql.execute('ALTER TABLE auto_edition_onboarding ADD COLUMN IF NOT EXISTS replacement jsonb')
        old_id = original['id'] if old_mapping == 'same' else 'id:prior-master'
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual',%s)",
                    (PID, old_id, '/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/old-master.psd', ADMIN['id']))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,reason,attempts) VALUES(%s,%s,'Needs PSD Repair','Old plaque needs repair',3)", (PID, old_id))
    handoff = prepare(result, row, receipt, 'Exact saved scenes.', staff_job=str(job_id))
    prompt = handoff['prompt']
    saved = handoff['staff_mapping']
    if refresh:
        assert saved['mode'] == 'UPDATE' and saved['target'] == PID
        assert 'Update only the exact linked existing Shopify product' in prompt
        assert 'Use ACTIVE from the first Shopify create call' not in prompt
        assert 'A different moment, title or collector concept is a new product' not in prompt
        assert PID in prompt
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
    queue.tick(token, {'id': str(job_id), 'state': 'uncertain'})
    assert queue.list_jobs('staff-fixture')['jobs'][0]['stage'] == 4
    assert not provider.api.move_path.called

    listing['tags'].append(saved['ready_tag'])
    queue.tick(token, {'id': str(job_id), 'state': 'uncertain'})
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
    if old_mapping in ('changed', 'busy', 'wrong_target'):
        if old_mapping == 'changed':
            sql.execute("UPDATE product_psd_mappings SET updated_at=now()+interval '1 second' WHERE shopify_product_gid=%s", (PID,))
        elif old_mapping == 'busy':
            sql.execute("UPDATE auto_edition_onboarding SET status='Preparing' WHERE product_gid=%s", (PID,))
        else:
            with store.locked(intake_id, ADMIN['id']) as (row, cur):
                row['data']['staff_mapping']['target'] = 'gid://shopify/Product/111'
        queue.tick(token, {})
        assert queue.list_jobs('staff-fixture')['jobs'][0]['stage'] == (5 if old_mapping == 'busy' else 7)
        assert not provider.api.move_path.called
        assert service.mappings.read_one(PID)['dropbox_file_id'] == old_id
        assert count(sql, 'auto_edition_onboarding') == 1
        assert read_edition(store.connect, PID) == before
        if old_mapping == 'busy':
            sql.execute("UPDATE auto_edition_onboarding SET status='Needs PSD Repair' WHERE product_gid=%s", (PID,))
            queue.tick(token, {})
            assert queue.list_jobs('staff-fixture')['jobs'][0]['stage'] == 6
            assert provider.api.move_path.call_count == 1
        return
    if lost_move_response == 'already_moved':
        from product_upload_dropbox import ROOTS
        provider.api.move_path(provider.token, original['id'], ROOTS['live'] + '/' + original['name'],
                               root_path=provider.context['root_path'])
    if lost_move_response is True:
        original_move = provider.api.move_path.side_effect

        def lose_response(*args, **kwargs):
            original_move(*args, **kwargs)
            raise ConnectionError('Simulated loss after Dropbox moved the file.')

        provider.api.move_path.side_effect = lose_response
        queue.tick(token, {})
        done = queue.list_jobs('staff-fixture')['jobs'][0]
        assert done['stage'] == 5
        if not old_mapping:
            assert 'Moving PSD failed' in done['detail']
        assert count(sql, 'product_psd_mappings') == bool(old_mapping)
        assert count(sql, 'auto_edition_onboarding') == bool(old_mapping)
        provider.api.move_path.side_effect = original_move
    queue.tick(token, {})
    done = queue.list_jobs('staff-fixture')['jobs'][0]
    assert done['stage'] == 6 and done['percent'] == 100, (done, service.status(intake_id, ADMIN))
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
    assert service.map(intake_id, ADMIN, product_id=PID, confirm_product=True,
                       source_version=saved['version'], staff_job=str(job_id))['state'] == 'Mapped'
    if old_mapping:
        sql.execute("SELECT count(*) AS n FROM product_psd_mapping_audit WHERE action='replace'")
        assert sql.fetchone()['n'] == 1
    assert queue.tick(token, {}) == {}
    assert provider.api.move_path.call_count == 1


def test_refresh_mapping_rejects_any_other_shopify_listing():
    from unittest.mock import Mock
    from product_upload_staff_mapping import published_product
    row = {'id': str(uuid4())}
    saved = {'target': PID, 'ready_tag': 'ready-fixture', 'files': []}
    other = {'shopify_product_id': 'gid://shopify/Product/999999',
             'tags': [tag(row['id']), saved['ready_tag']]}
    shopify = Mock()
    shopify.fetch_catalog_page.return_value = {'products': [other], 'has_next_page': False}
    shopify.shopify_gid.side_effect = lambda kind, value: value
    with pytest.raises(ValueError, match='other than the saved refresh target'):
        published_product(row, saved, shopify)
