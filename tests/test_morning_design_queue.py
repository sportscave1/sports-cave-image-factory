import json
from pathlib import Path
from datetime import date

import pytest
import morning_design_queue as queue
import product_upload_staff_queue as uploads
from test_auto_editions_jobs import database

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(database, monkeypatch):
    db, cur = database
    for name in ('20261117110000_product_upload_staff_queue.sql', '20261117150000_morning_design_queue.sql'):
        cur.execute((ROOT / 'migrations' / name).read_text(encoding='utf8'))
    cur.execute('CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    cur.execute("UPDATE morning_design_control SET enabled=true,start_date='2026-11-17',activated_at='2026-11-17T00:00:00Z'")
    monkeypatch.setattr(queue, 'connect', db.connect)
    monkeypatch.setattr(uploads, 'connect', db.connect)
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {})
    return cur, uploads.pair({'id': 'desktop'})


def publish(cur, day='2026-11-17', count=5):
    from home_brief_calendar import HISTORY_PREFIX
    edition = dict(date=day, recommendations=[dict(title=f'Design {n}', recommendation='Create a collector design.') for n in range(count)])
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',
                (HISTORY_PREFIX + day, json.dumps(edition)))
    return edition


def test_one_slot_duplicate_publications_and_next_day(store, monkeypatch):
    cur, token = store
    publish(cur)
    first = queue.tick(token, [])['jobs']
    assert len(first) == 1
    assert {job['id'] for job in queue.tick(token, [])['jobs']} == {job['id'] for job in first}
    assert len(queue.list_jobs()) == 5
    for job in first:
        assert f'morning_design_job_id = "{job["id"]}"' in job['prompt']
    queue.tick(token, [dict(id=job['id'], state='submitted') for job in first])
    assert {j['stage'] for j in queue.list_jobs() if j['id'] in {r['id'] for r in first}} == {2}
    # A fresh morning is independent, but cannot exceed the occupied slots.
    publish(cur, '2026-11-18', count=2)
    assert len(queue.tick(token, [])['jobs']) == 1
    assert len(queue.list_jobs()) == 7
    completed = first[0]['id']
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {completed: dict(stage=4, message='',
        source=dict(id='id:final', rev='R1', path_display='/Review/Final.psd'))})
    next_jobs = queue.tick(token, [])['jobs']
    assert len(next_jobs) == 1
    assert completed not in {j['id'] for j in next_jobs}
    assert next(j for j in queue.list_jobs() if j['id'] == completed)['label'] == 'Ready for review'
    publish(cur)
    queue.tick(token, [])
    assert len(queue.list_jobs()) == 7


def test_auth_pause_and_uncertain_submission(store):
    cur, token = store
    publish(cur)
    with pytest.raises(PermissionError):
        queue.tick('wrong', [])
    assert queue.list_jobs() == []
    queue.settings(False)
    assert queue.tick(token, [])['jobs'] == []
    queue.settings(True)
    jobs = queue.tick(token, [])['jobs']
    key = jobs[0]['id']
    queue.tick(token, [dict(id=key, state='uncertain', reason='Inspect the chat.')])
    assert next(j for j in queue.list_jobs() if j['id'] == key)['stage'] == 5
    queue.tick(token, [dict(id=key, state='submitted')])
    assert next(j for j in queue.list_jobs() if j['id'] == key)['stage'] == 5
    # Failure automatically frees the slot, but the failed job is never replayed.
    following = queue.tick(token, [])['jobs']
    assert len(following) == 1 and following[0]['id'] != key
    assert next(j for j in queue.list_jobs() if j['id'] == key)['stage'] == 5


def test_old_editions_are_not_backfilled_on_first_enable(store):
    cur, token = store
    publish(cur)
    cur.execute("UPDATE app_settings SET updated_at='2026-11-16T00:00:00Z'")
    assert queue.tick(token, [])['jobs'] == []
    publish(cur, day='2026-11-18')
    assert len(queue.tick(token, [])['jobs']) == 1


def test_current_suggestion_can_be_queued_once_without_backfill(store):
    cur, token = store
    from home_sports_morning_brief import SETTING_KEY
    edition = publish(cur)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',
                (SETTING_KEY, json.dumps(edition)))
    cur.execute("UPDATE app_settings SET updated_at='2026-11-16T00:00:00Z'")
    suggestion = queue.current_suggestions()[0]
    queue.enqueue_selected(suggestion['id'])
    queue.enqueue_selected(suggestion['id'])
    assert len(queue.list_jobs()) == 1
    assert queue.tick(token, [])['jobs'][0]['id'] == suggestion['id']
    with pytest.raises(ValueError):
        queue.enqueue_selected('not-current')


def test_timeout_preserves_chat_and_late_verified_upload_can_finish(store, monkeypatch):
    cur, token = store
    publish(cur)
    job = queue.tick(token, [])['jobs'][0]
    chat = 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654-designs/c/00000000-0000-0000-0000-000000000001'
    queue.tick(token, [dict(id=job['id'], state='submitted', chat_url=chat)])
    cur.execute("UPDATE morning_design_jobs SET updated_at=now()-interval '4 hours' WHERE id=%s", (job['id'],))
    queue.tick(token, [])
    record = next(j for j in queue.list_jobs() if j['id'] == job['id'])
    assert record['stage'] == 5 and record['chat_url'] == chat
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {job['id']: dict(stage=4, message='',
        source=dict(id='id:late', rev='R1', path_display='/Review/Late.psd'))})
    queue.tick(token, [])
    assert next(j for j in queue.list_jobs() if j['id'] == job['id'])['stage'] == 4


def test_edited_or_reordered_suggestion_keeps_identity_and_badges_escape():
    from home_morning_brief_actions import article_html
    item = dict(title='  A   Champion ', recommendation='Original', links=[])
    key = queue.identity('2026-11-17', 'legends', item)
    assert queue.identity('2026-11-17', 'legends', dict(title='a champion', recommendation='Updated')) == key
    assert queue.identity('2026-11-18', 'legends', item) != key
    assert '&lt;unsafe&gt;' in article_html(item, design_status='<unsafe>')


def test_real_file_verification_rejects_wrong_revision_and_missing_metadata(monkeypatch):
    import product_upload_services
    import design_review_page
    import design_review_metadata
    from psd_directory import REVIEW_METADATA_FOLDER, REVIEW_FOLDER
    key = queue.identity('2026-11-17', 'legends', {'title': 'A'})
    source = dict(id='id:final', rev='R1', path_display=REVIEW_FOLDER+'/Final.psd', size=100, name='Final.psd')
    sidecar = dict(name='Final.upload.json', path_display=REVIEW_METADATA_FOLDER+'/Final.upload.json')
    value = dict(morning_design_job_id=key, dropbox_file_id=source['id'], dropbox_revision='R1',
                 dropbox_path=source['path_display'], upload_intent='new_product', design_title='Final',
                 intended_collections=['basketball'], sport='Basketball', review_status='ready_for_review')
    provider = type('Provider', (), {'metadata_if_present': lambda self, identifier: source})()
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: provider)
    monkeypatch.setattr(design_review_page, '_folder_entries', lambda *args: [sidecar])
    monkeypatch.setattr(design_review_page, 'final_psd', lambda source: True)
    monkeypatch.setattr(design_review_metadata, '_read_sidecar', lambda *args: (value, sidecar))
    assert queue.verify_outputs([{'id': key}])[key]['stage'] == 4
    value['review_status'] = 'needs_attention'
    assert queue.verify_outputs([{'id': key}])[key]['stage'] == 5
    value['review_status'] = 'ready_for_review'
    value['dropbox_revision'] = 'stale'
    assert queue.verify_outputs([{'id': key}]) == {}
    value['dropbox_revision'] = 'R1'
    value['intended_collections'] = []
    assert queue.verify_outputs([{'id': key}])[key]['stage'] == 3
    value['morning_design_job_id'] = 'some-other-job'
    assert queue.verify_outputs([{'id': key}]) == {}


def test_saved_artwork_with_review_concerns_releases_slot(store, monkeypatch):
    cur, token = store
    publish(cur)
    first = queue.tick(token, [])['jobs'][0]
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {first['id']: dict(stage=5,
        message='Face softness needs review.', source=dict(id='id:saved', rev='R1', path_display='/Review/Final.psd'))})
    following = queue.tick(token, [])['jobs']
    assert len(following) == 1 and following[0]['id'] != first['id']
    saved = next(j for j in queue.list_jobs() if j['id'] == first['id'])
    assert saved['label'] == 'Uploaded · needs review'
    assert saved['file_path'] == '/Review/Final.psd'

def test_pause_keeps_current_chat_and_holds_next_until_play(store, monkeypatch):
    cur, token = store
    publish(cur, count=2)
    first = queue.tick(token, [])['jobs'][0]
    queue.settings(False)
    running = queue.tick(token, [dict(id=first['id'], state='submitted')])
    assert running['enabled'] is False
    assert [(j['id'], j['stage']) for j in running['jobs']] == [(first['id'], 2)]
    assert sum(j['stage'] == 0 for j in queue.list_jobs()) == 1
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {first['id']: dict(stage=4, message='',
        source=dict(id='id:paused-final', rev='R1', path_display='/Review/Final.psd'))})
    assert queue.tick(token, [])['jobs'] == []
    assert queue.tick(token, [])['jobs'] == []
    assert next(j for j in queue.list_jobs() if j['id'] == first['id'])['stage'] == 4
    assert sum(j['stage'] == 0 for j in queue.list_jobs()) == 1
    queue.settings(True)
    resumed = queue.tick(token, [])['jobs']
    assert len(resumed) == 1 and resumed[0]['id'] != first['id']


@pytest.mark.parametrize('status,icon,tone', [
    ('Completed · uploaded', '✓', 'complete'), ('Ready for review', '✓', 'complete'),
    ('Uploaded · needs review', '!', 'attention'), ('Needs attention', '!', 'attention'),
    ('Generating', '◌', 'running'), ('Pending', '○', 'pending'),
])
def test_home_status_icons_preserve_honest_labels(status, icon, tone):
    from home_morning_brief_actions import article_html
    html = article_html(dict(title='A Champion', recommendation='Fixture', links=[]), design_status=status)
    assert f'sc-brief-status {tone}' in html
    assert f'aria-hidden="true">{icon}</i>' in html
    assert status in html
