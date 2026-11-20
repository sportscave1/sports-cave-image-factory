"""Real disposable SQL contracts for the single companion ad slot."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import ads_companion_controls as controls
import ads_companion_queue as queue
import design_publish_ad as ads
import product_upload_staff_queue as uploads
from test_ads_companion_queue import queued_store, store, database, brief, ROW, USER, no_provider_network


def enqueue_pair(monkeypatch):
    monkeypatch.setattr(uploads, 'can_control_queues', lambda _: True)
    monkeypatch.setattr(queue, 'prepare', lambda _: dict(stage='opening', prompt='fixture'))
    first = queue.enqueue(USER, brief(), {'row': ROW})['id']
    other = brief(); other['country'] = 'Canada'
    second = queue.enqueue(USER, other, {'row': ROW})['id']
    return uploads.pair(USER), first, second


def read(db, job):
    with db() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (ads.PREFIX+job,))
        return cur.fetchone()['value']


@pytest.mark.parametrize('release', ['complete', 'failed', 'cancel', 'delete'])
def test_catalogue_wait_keeps_slot_until_release(queued_store, monkeypatch, release):
    token, first, second = enqueue_pair(monkeypatch)
    assert ads.tick(token, {})['job']['id'] == first
    value = read(queued_store, first)
    value.update(stage='generating', catalog_retry={'next_at': time.time()+600})
    ads.write(ads.PREFIX+first, value)
    for _ in range(3):
        assert ads.tick(token, {}) == {'job': {}}
        assert read(queued_store, second)['stage'] == 'waiting'
    if release in ('cancel', 'delete'):
        controls.action(USER, first, release)
    else:
        value['stage'] = release; ads.write(ads.PREFIX+first, value)
    assert ads.tick(token, {})['job']['id'] == second


def test_resume_waits_and_preserves_checkpoint(queued_store, monkeypatch):
    token, first, second = enqueue_pair(monkeypatch)
    ads.tick(token, {})
    value = read(queued_store, second)
    value.update(stage='failed', folder='/saved', artifacts={'copy': 'kept'},
                 chat_url=ads.PROJECT.removesuffix('/project')+'/c/'+second)
    ads.write(ads.PREFIX+second, value)
    controls.action(USER, second, 'play')
    saved = read(queued_store, second)
    assert saved['stage'] == 'waiting' and saved['resume_stage'] == 'generating'
    assert saved['artifacts'] == value['artifacts'] and saved['chat_url'] == value['chat_url']
    assert ads.tick(token, {})['job']['id'] == first
    controls.action(USER, first, 'cancel')
    seen = []
    monkeypatch.setattr(ads, '_step', lambda key, value, *args: seen.append(value.copy()) or {})
    ads.tick(token, {})
    assert seen[0]['stage'] == 'generating' and seen[0]['collect_only']
    assert 'resume_stage' not in seen[0]


def test_legacy_overlaps_are_queued_without_rotating(queued_store, monkeypatch):
    token, first, second = enqueue_pair(monkeypatch)
    ads.tick(token, {})
    value = read(queued_store, second); value.update(stage='generating', folder='/kept')
    ads.write(ads.PREFIX+second, value)
    assert ads.tick(token, {})['job']['id'] == first
    assert read(queued_store, second)['resume_stage'] == 'generating'
    # Updating the current job must not rotate to the other saved checkpoint.
    ads.write(ads.PREFIX+first, read(queued_store, first))
    assert ads.tick(token, {'id': second}) == {'stop': {'id': second}}
    assert ads.tick(token, {})['job']['id'] == first
    assert read(queued_store, second)['stage'] == 'waiting'


def test_concurrent_ticks_only_run_one_step(queued_store, monkeypatch):
    token, first, second = enqueue_pair(monkeypatch)
    entered, finish = Event(), Event()
    calls = []
    def step(key, value, *args):
        calls.append(value['upload']); entered.set()
        assert finish.wait(10)
        return {'id': value['upload']}
    monkeypatch.setattr(ads, '_step', step)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(ads.tick, token, {})
        try:
            assert entered.wait(10)
            assert pool.submit(ads.tick, token, {}).result(10) == {'busy': True}
        finally:
            finish.set()
        assert running.result(10)['job']['id'] == first
    assert calls == [first]
    assert read(queued_store, second)['stage'] == 'waiting'
