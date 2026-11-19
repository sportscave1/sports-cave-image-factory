import json
from pathlib import Path
from datetime import date

import pytest
import morning_design_queue as queue
import product_upload_staff_queue as uploads
from test_auto_editions_jobs import database

ROOT = Path(__file__).resolve().parents[1]
VERIFY_OUTPUTS = queue.verify_outputs


@pytest.fixture
def store(database, monkeypatch):
    import product_upload_services
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: type('Provider', (), {
        'metadata_if_present': lambda self, path: {'id': path}})())
    db, cur = database
    for name in ('20261117110000_product_upload_staff_queue.sql', '20261117150000_morning_design_queue.sql', '20261118070000_product_upload_manual_restart.sql'):
        cur.execute((ROOT / 'migrations' / name).read_text(encoding='utf8'))
    cur.execute('CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    cur.execute('''CREATE TABLE IF NOT EXISTS shopify_products (
        shopify_product_id text PRIMARY KEY,status text,online_store_url text);
        CREATE TABLE IF NOT EXISTS product_psd_mappings (
        shopify_product_gid text PRIMARY KEY,dropbox_file_id text UNIQUE,file_path text);
        CREATE TABLE IF NOT EXISTS product_upload_mapping_holds (
        operation_id uuid,product_gid text PRIMARY KEY,file_id text);
        CREATE OR REPLACE FUNCTION public.product_upload_mapping_complete(uuid,text,text)
        RETURNS boolean LANGUAGE sql AS $$ SELECT false $$;''')
    cur.execute("UPDATE morning_design_control SET enabled=true,start_date='2026-11-17',activated_at='2026-11-17T00:00:00Z'")
    monkeypatch.setattr(queue, 'connect', db.connect)
    monkeypatch.setattr(uploads, 'connect', db.connect)
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {})
    monkeypatch.setattr(queue, 'poll_outputs', lambda jobs: queue.verify_outputs(jobs))
    return cur, uploads.pair({'id': 'desktop'})


def publish(cur, day='2026-11-17', count=5):
    from home_brief_calendar import HISTORY_PREFIX
    edition = dict(date=day, recommendations=[dict(title=f'Design {n}', recommendation='Create a collector design.') for n in range(count)])
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',
                (HISTORY_PREFIX + day, json.dumps(edition)))
    return edition


@pytest.mark.parametrize('finished,minutes',[(True,6),(False,31)])
def test_stalled_design_releases_slot_without_resending_and_accepts_late_receipt(store,monkeypatch,finished,minutes):
    cur,token=store;publish(cur,count=2)
    first=queue.tick(token,[])['jobs'][0]
    queue.tick(token,[dict(id=first['id'],state='submitted')])
    cur.execute("UPDATE morning_design_jobs SET updated_at=now()-(%s * interval '1 minute') WHERE id=%s",(minutes,first['id']))
    event=dict(id=first['id'],state='submitted',activity='unchanged',finished=finished,generating=not finished)
    next_job=queue.tick(token,[event])['jobs'][0]
    assert next_job['id']!=first['id']
    cur.execute('SELECT stage,message FROM morning_design_jobs WHERE id=%s',(first['id'],))
    stopped=cur.fetchone();assert stopped['stage']==5 and 'Queue continues' in stopped['message']
    assert queue.tick(token,[event])['jobs'][0]['id']==next_job['id']
    # Late delivery with review warnings is still reconciled, including edit jobs
    # that already store their original source ID before dispatch.
    cur.execute("UPDATE morning_design_jobs SET file_id='id:original' WHERE id=%s",(first['id'],))
    monkeypatch.setattr(queue,'verify_outputs',lambda _: {first['id']:dict(stage=5,message='Delivered; review needed',source=dict(id='id:original',rev='new',path_display='/Review/Final.psd'))})
    queue.tick(token,[])
    cur.execute('SELECT file_rev,file_path FROM morning_design_jobs WHERE id=%s',(first['id'],))
    assert cur.fetchone()['file_rev']=='new'


def test_fresh_activity_keeps_slot_and_finished_response_has_grace(store):
    cur,token=store;publish(cur,count=2)
    first=queue.tick(token,[])['jobs'][0]
    queue.tick(token,[dict(id=first['id'],state='submitted')])
    assert queue.tick(token,[dict(id=first['id'],state='submitted',activity='one',finished=False,generating=True)])['jobs'][0]['id']==first['id']
    cur.execute("UPDATE app_settings SET value=jsonb_set(value,'{changed_at}',to_jsonb(extract(epoch from now())-1900)) WHERE key=%s",('design_queue_progress:'+first['id'],))
    assert queue.tick(token,[dict(id=first['id'],state='submitted',activity='two',finished=True,generating=False)])['jobs'][0]['id']==first['id']


def test_review_edit_apply_is_idempotent_and_keeps_prompt_unchanged(store,monkeypatch):
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api
    import design_review_metadata as metadata
    from home_morning_brief_actions import _prompt
    cur,token=store
    record=dict(id='id:edit',rev='original',name='Selected.psd',path_display='/Review/Selected.psd')
    monkeypatch.setattr(api,'_gallery_review_user',AsyncMock(return_value={'id':'reviewer'}))
    monkeypatch.setattr(api,'Dropbox',lambda:SimpleNamespace())
    monkeypatch.setattr(api,'_review_metadata',lambda *args:record)
    monkeypatch.setattr(metadata,'read_handoff',lambda *args:dict(design_name='Selected',product_context='Original story'))
    app=Starlette(routes=[Route('/api/design-review/edit-queue',api.review_edit_enqueue,methods=['POST'])])
    with TestClient(app) as client:
        kwargs=dict(params=dict(id=record['id'],rev=record['rev']),json=dict(comments='Fix the spacing'),headers={'Origin':'http://testserver'})
        first=client.post('/api/design-review/edit-queue',**kwargs)
        assert first.status_code==200,first.text
        assert client.post('/api/design-review/edit-queue',**kwargs).json()==first.json()
        kwargs['json']=dict(comments='Conflicting request')
        assert client.post('/api/design-review/edit-queue',**kwargs).status_code>=400
    result=queue.tick(token,[])['jobs'][0]
    assert result['kind']=='edit'
    expected='**USER-REQUESTED DESIGN CHANGES**\nFix the spacing\n\n'+_prompt('Selected','Original story',edit=dict(source=record,metadata=dict(design_name='Selected',product_context='Original story')))
    assert result['prompt']==expected
    cur.execute("SELECT count(*) AS n FROM morning_design_jobs WHERE section='edit'")
    assert cur.fetchone()['n']==1


def test_edit_completion_requires_changed_canonical_revision_and_matching_sidecar(monkeypatch):
    from uuid import uuid4
    import product_upload_services,design_review_page,design_review_metadata
    from psd_directory import REVIEW_FOLDER,REVIEW_METADATA_FOLDER
    jid=str(uuid4())
    job=dict(id=jid,section='edit',file_id='id:canonical',file_rev='old',prompt='unchanged')
    source=dict(id='id:canonical',rev='old',name='Selected.psd',path_display=REVIEW_FOLDER+'/Selected.psd',size=100,**{'.tag':'file'})
    sidecar=dict(id='id:json',rev='j1',name='Selected.upload.json',path_display=REVIEW_METADATA_FOLDER+'/Selected.upload.json')
    value=dict(dropbox_file_id=source['id'],dropbox_revision='old',dropbox_path=source['path_display'])
    provider=type('Provider',(),{'metadata_if_present':lambda self,key:source})()
    monkeypatch.setattr(product_upload_services,'Dropbox',lambda:provider)
    monkeypatch.setattr(design_review_page,'_folder_entries',lambda *args:[sidecar])
    monkeypatch.setattr(design_review_metadata,'_read_sidecar',lambda *args:(value,sidecar))
    monkeypatch.setattr(design_review_metadata,'_handoff_details',lambda *args:dict(review_status='ready_for_review'))
    assert VERIFY_OUTPUTS([job])=={}
    value['dropbox_revision']='new'
    assert VERIFY_OUTPUTS([job])=={}  # JSON alone cannot complete the edit.
    source['rev']='new'
    assert VERIFY_OUTPUTS([job])[jid]['stage']==4


def test_header_counts_waiting_jobs_and_reads_both_control_states(store, monkeypatch):
    import design_publish_ad
    monkeypatch.setattr(design_publish_ad, 'connect', uploads.connect)
    cur, token = store
    publish(cur)
    queue.tick(token, [])
    cur.execute("""INSERT INTO product_upload_staff_jobs(id,source_id,source_rev,title,sport)
        VALUES ('fa74cb28-f3c1-4b34-8ba5-0c39b3e8d31e', 'source', 'rev', 'Waiting upload', 'Sport')""")
    status = uploads.header_queue_status()
    assert status['ads']['waiting'] == 0 and status['ads']['jobs'] == []
    assert status['design']['jobs'][0]['state'] == 'running'
    assert {key:{field:status[key][field] for field in ('waiting','enabled')} for key in ('design','upload')} == {
        'design': {'waiting': 4, 'enabled': True},
        'upload': {'waiting': 1, 'enabled': True},
    }
    queue.settings(False)
    uploads.settings(False)
    status = uploads.header_queue_status()
    assert {key:{field:status[key][field] for field in ('waiting','enabled')} for key in ('design','upload')} == {
        'design': {'waiting': 4, 'enabled': False},
        'upload': {'waiting': 1, 'enabled': False},
    }


def test_home_publication_badges_use_current_mapping_and_verified_upload(store):
    from psd_directory import REVIEW_FOLDER, ROOT
    cur, _ = store
    publish(cur, count=2)
    queue.discover(cur)
    cur.execute('SELECT id FROM morning_design_jobs ORDER BY title')
    original, replacement = [row['id'] for row in cur.fetchall()]
    same_psd = 'Forever a Brewer - Ken Sanders Wall Art.psd'
    original_psd = 'The Heart of Oil Country - Connor McDavid Wall Art.psd'
    alternate_psd = 'The Heart of Oil Country – Connor McDavid Wall Art.psd'
    cur.execute('UPDATE morning_design_jobs SET stage=5,file_id=%s,file_path=%s WHERE id=%s',
                ('id:brewer', REVIEW_FOLDER + '/' + same_psd, original))
    cur.execute('UPDATE morning_design_jobs SET stage=5,file_id=%s,file_path=%s WHERE id=%s',
                ('id:review', REVIEW_FOLDER + '/' + original_psd, replacement))
    products = ['gid://shopify/Product/101', 'gid://shopify/Product/102']
    for number, (gid, file_id, asset) in enumerate(zip(products, ['id:brewer', 'id:alternate'], [same_psd, alternate_psd])):
        cur.execute('INSERT INTO shopify_products (shopify_product_id,status,online_store_url) VALUES (%s,%s,%s)',
                    (gid, 'ACTIVE', f'https://example.test/products/art-{number}'))
        cur.execute('INSERT INTO product_psd_mappings (shopify_product_gid,dropbox_file_id,file_path) VALUES (%s,%s,%s)',
                    (gid, file_id, ROOT + '/' + asset))

    def badges():
        return [job['label'] for job in sorted(queue.list_jobs('2026-11-17'), key=lambda job: job['title'])]

    assert badges() == ['Completed · uploaded', 'Uploaded · needs review']
    cur.execute('''INSERT INTO product_upload_staff_jobs (id,source_id,source_rev,title,stage,storefront,created_at)
        VALUES ('7da624bc-0dab-4580-942f-8343406fada9','id:alternate','R2','Artwork',6,
                'https://example.test/products/art-1',now()-interval '1 day')''')
    assert badges() == ['Completed · uploaded', 'Uploaded · needs review']
    cur.execute("UPDATE product_upload_staff_jobs SET created_at=now() WHERE source_id='id:alternate'")
    assert badges() == ['Completed · uploaded', 'Completed · uploaded']

    cur.execute('INSERT INTO product_upload_mapping_holds VALUES (%s,%s,%s)',
                ('7da624bc-0dab-4580-942f-8343406fada9', products[1], 'id:alternate'))
    cur.execute("UPDATE shopify_products SET status='ARCHIVED' WHERE shopify_product_id=%s", (products[0],))
    assert badges() == ['Uploaded · needs review', 'Uploaded · needs review']
    cur.execute('DELETE FROM product_upload_mapping_holds')
    cur.execute('INSERT INTO product_psd_mappings (shopify_product_gid,dropbox_file_id,file_path) VALUES (%s,%s,%s)',
                ('gid://shopify/Product/103', 'id:ambiguous', ROOT + '/' + original_psd))
    assert badges() == ['Uploaded · needs review', 'Uploaded · needs review']


def test_claim_upgrades_waiting_legacy_prompt_without_replacing_active_prompt(store):
    cur, token = store
    edition = publish(cur, count=2)
    queue.discover(cur)
    first, waiting = [queue.identity(edition['date'], 'recommendations', item)
                      for item in edition['recommendations']]
    cur.execute("UPDATE morning_design_jobs SET stage=2,prompt=%s WHERE id=%s", ('a chat already submitted this', first))
    old = ('Old workflow. Report PSD and JSON delivery separately from successful visual checks.\n\n'
           'Use the original selected story.\n\n**CHOOSE THE COLLECTOR TITLE AND DESIGN DIRECTION**\n\nOld rules')
    cur.execute("UPDATE morning_design_jobs SET prompt=%s WHERE id=%s", (old, waiting))
    assert queue.tick(token, [])['jobs'][0]['prompt'] == 'a chat already submitted this'
    cur.execute("UPDATE morning_design_jobs SET stage=4 WHERE id=%s", (first,))
    claim = queue.tick(token, [])['jobs'][0]
    assert claim['id'] == waiting
    assert 'Use the original selected story.' in claim['prompt']
    assert f'morning_design_job_id = "{waiting}"' in claim['prompt']
    assert 'Generate the collector treatment once' in claim['prompt']
    assert 'Old rules' not in claim['prompt']


def test_waiting_creative_upgrade_preserves_original_story_and_retry_receipt():
    from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
    from design_new_composition import PURPOSEFUL_ABSTRACT
    story = 'A verified club transition.\n\nSuggested title: New Chapter.\nKeep the original sporting context.'
    key = queue.identity('2026-11-18', 'recommendations', {'title': 'A Champion'})
    prompt = queue._job_prompt(key, 'A Champion', story)
    old = prompt.replace(NEW_DESIGN_TITLE_GUIDANCE, 'Previous title selection rules.\n\n')
    old = old.replace(PURPOSEFUL_ABSTRACT, 'Previous abstract treatment.')
    old += '\nQueue retry receipt: 00000000-0000-0000-0000-000000000001\n'
    job = dict(id=key, title='A Champion', prompt=old)
    receipt = queue._receipt(job)
    upgraded = queue._waiting_prompt(job)
    assert story in upgraded and NEW_DESIGN_TITLE_GUIDANCE in upgraded and PURPOSEFUL_ABSTRACT in upgraded
    assert f'morning_design_job_id = "{key}"' in upgraded
    assert queue._receipt(dict(job, prompt=upgraded)) == receipt
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_waiting_filename_upgrade_keeps_job_story_and_receipt():
    from home_morning_brief_actions import REVIEW_SAVE_NAMING
    key = queue.identity('2026-11-18', 'legends', {'title':'Panda'})
    story = 'A verified Pablo Sandoval tribute. Preserve the chosen Forever Panda headline.'
    prompt = queue._job_prompt(key, 'Panda', story)
    saved = prompt.replace(REVIEW_SAVE_NAMING, '')
    job = dict(id=key, title='Panda', prompt=saved)
    upgraded = queue._waiting_prompt(job)
    assert REVIEW_SAVE_NAMING in upgraded and story in upgraded
    assert queue._receipt(dict(job, prompt=upgraded)) == queue._receipt(job)


def test_one_slot_duplicate_publications_and_next_day(store, monkeypatch):
    cur, token = store
    publish(cur)
    first = queue.tick(token, [])['jobs']
    assert len(first) == 1
    assert {job['id'] for job in queue.tick(token, [])['jobs']} == {job['id'] for job in first}
    assert len(queue.list_jobs()) == 5
    for job in first:
        assert f'morning_design_job_id = "{job["id"]}"' in job['prompt']
        assert 'Use the original photos as the authority' in job['prompt']
        assert 'Generate the collector treatment once' in job['prompt']
        assert 'Omit the marker for visual concerns alone.' in job['prompt']
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
    assert queue.enqueue_selected(suggestion['id']) is True
    assert queue.enqueue_selected(suggestion['id']) is False
    assert len(queue.list_jobs()) == 1
    assert queue.tick(token, [])['jobs'][0]['id'] == suggestion['id']
    with pytest.raises(ValueError):
        queue.enqueue_selected('not-current')


def test_explicit_retry_for_all_finished_jobs(store):
    from home_sports_morning_brief import SETTING_KEY
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    assert queue.enqueue_selected(first['id']) is False
    queue.tick(token, [dict(id=first['id'], state='failed')])
    assert queue.enqueue_selected(first['id']) is True
    assert queue.enqueue_selected(first['id']) is False
    retry = queue.tick(token, [])['jobs'][0]
    assert retry['id'] == first['id'] and retry['receipt'] != first['receipt']
    assert queue.tick(token, [])['jobs'][0]['receipt'] == retry['receipt']
    for stage, file_id, path in ((5, 'id:made', '/Review/Made.psd'), (5, 'id:made', ''),
                                 (3, '', ''), (4, '', ''), (2, '', ''), (0, '', '')):
        cur.execute('UPDATE morning_design_jobs SET stage=%s,file_id=%s,file_path=%s WHERE id=%s',
                    (stage, file_id, path, first['id']))
        assert queue.enqueue_selected(first['id']) is (stage in (3, 4, 5))


def test_late_verified_artwork_does_not_block_explicit_retry(store, monkeypatch):
    from home_sports_morning_brief import SETTING_KEY
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    queue.tick(token, [dict(id=first['id'], state='failed')])
    monkeypatch.setattr(queue, 'verify_outputs', lambda jobs: {first['id']: {'stage': 4}})
    assert queue.enqueue_selected(first['id']) is True
    assert queue.list_jobs()[0]['stage'] == 0


@pytest.mark.parametrize('status', [None, 'Pending', 'Generating', 'Opening ChatGPT',
    'Ready for review', 'Completed · uploaded', 'Uploaded · needs review', 'Uploaded · checking review metadata'])
def test_home_queue_button_enabled_regardless_of_status(status):
    from home_morning_brief_actions import article_html
    item = dict(title='Champion', recommendation='Brief', links=[])
    markup = article_html(item, design_key='fixture', design_status=status)
    assert ' disabled>Add to Queue</button>' not in markup
    assert 'data-prompt=' not in markup
    enabled = article_html(item, design_key='fixture', design_status='Needs attention')
    assert ' disabled' not in enabled and 'Add to Queue</button>' in enabled


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
    output = '00000000-0000-0000-0000-000000000099'
    repeated = {'id': key, 'prompt': f'\nQueue output receipt: {output}\n'}
    assert queue.verify_outputs([repeated]) == {}
    value['morning_design_job_id'] = output
    assert queue.verify_outputs([repeated])[key]['stage'] == 4
    value['morning_design_job_id'] = key

    value['review_status'] = 'needs_attention'
    assert queue.verify_outputs([{'id': key}])[key]['stage'] == 5
    value['review_status'] = 'ready_for_review'
    value['dropbox_revision'] = 'stale'
    assert queue.verify_outputs([{'id': key}]) == {}
    value['dropbox_revision'] = 'R1'
    value['intended_collections'] = []
    result = queue.verify_outputs([{'id': key}])[key]
    assert result['stage'] == 5 and 'Generation is complete' in result['message']
    value['upload_intent'] = 'invalid'
    assert queue.verify_outputs([{'id': key}])[key]['stage'] == 5
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


def test_legacy_delivered_job_releases_slot_even_if_desktop_verification_is_offline(store, monkeypatch):
    cur, token = store
    publish(cur, count=2)
    first = queue.tick(token, [])['jobs'][0]
    cur.execute('''UPDATE morning_design_jobs SET stage=3,file_id='id:delivered',file_rev='R1',
        file_path='/Review/Completed.psd',message='Collections missing' WHERE id=%s''', (first['id'],))
    def offline(jobs):
        raise OSError('Synthetic offline provider')
    monkeypatch.setattr(queue, 'verify_outputs', offline)
    # Merely opening the queue fixes the obsolete active state without a desktop.
    saved = next(job for job in queue.list_jobs() if job['id'] == first['id'])
    assert saved['stage'] == 5 and 'generation is complete' in saved['detail']
    assert saved['file_path'] == '/Review/Completed.psd'
    following = queue.tick(token, [])['jobs']
    assert len(following) == 1 and following[0]['id'] != first['id']
    queue.tick(token, [dict(id=first['id'], state='submitted')])
    assert next(job for job in queue.list_jobs() if job['id'] == first['id'])['stage'] == 5


def test_tick_repairs_delivered_legacy_job_but_respects_pause(store):
    cur, token = store
    publish(cur, count=2)
    first = queue.tick(token, [])['jobs'][0]
    cur.execute('''UPDATE morning_design_jobs SET stage=3,file_id='id:saved',file_rev='R1',
        file_path='/Review/Completed.psd' WHERE id=%s''', (first['id'],))
    queue.settings(False)
    assert queue.tick(token, [])['jobs'] == []
    assert next(job for job in queue.list_jobs() if job['id'] == first['id'])['stage'] == 5
    assert sum(job['stage'] == 0 for job in queue.list_jobs()) == 1


@pytest.mark.parametrize('metadata', [
    {'intended_collections': []},
    {'upload_intent': 'incomplete'},
])
def test_verified_review_delivery_advances_next_job_even_with_incomplete_metadata(store, monkeypatch, metadata):
    import product_upload_services
    import design_review_page
    import design_review_metadata
    from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER
    cur, token = store
    publish(cur, count=2)
    first = queue.tick(token, [])['jobs'][0]
    source = dict(id='id:delivered', rev='R1', path_display=REVIEW_FOLDER+'/Final.psd',
                  size=100, name='Final.psd', **{'.tag':'file'})
    sidecar = dict(id='id:receipt', rev='J1', name='Final.upload.json',
                   path_display=REVIEW_FOLDER+'/Final.upload.json')
    value = dict(morning_design_job_id=first['id'], dropbox_file_id=source['id'], dropbox_revision='R1',
                 dropbox_path=source['path_display'], upload_intent='new_product', design_title='Final',
                 sport='NBA', intended_collections=['nba'], review_status='ready_for_review')
    value.update(metadata)
    provider = type('Provider', (), {'metadata_if_present': lambda self, key: source})()
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: provider)
    def entries(provider, path):
        if path == REVIEW_METADATA_FOLDER:
            raise OSError('Synthetic central folder outage')
        return [sidecar]
    monkeypatch.setattr(design_review_page, '_folder_entries', entries)
    monkeypatch.setattr(design_review_metadata, '_read_sidecar', lambda *args: (value, sidecar))
    monkeypatch.setattr(queue, 'verify_outputs', VERIFY_OUTPUTS)
    following = queue.tick(token, [])['jobs']
    assert len(following) == 1 and following[0]['id'] != first['id']
    completed = next(job for job in queue.list_jobs() if job['id'] == first['id'])
    assert completed['stage'] == 5 and completed['file_path'] == source['path_display']
    assert 'PSD delivered to Design Studio Review' in completed['detail']

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

@pytest.mark.parametrize('stage', [4, 5])
def test_deleted_unposted_design_can_be_explicitly_requeued(store, monkeypatch, stage):
    import product_upload_services
    from home_sports_morning_brief import SETTING_KEY
    from home_morning_brief_actions import article_html
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    cur.execute("UPDATE morning_design_jobs SET stage=%s,file_id='id:deleted',file_rev='R1',file_path='/Review/Final.psd' WHERE id=%s", (stage, first['id']))
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: type('Provider', (), {
        'metadata_if_present': lambda self, path: None})())
    record = queue.list_jobs()[0]
    assert record['label'] == 'Deleted · ready to redo'
    markup = article_html(dict(title='A', recommendation='Brief', links=[]), design_key=first['id'], design_status=record['label'])
    assert ' disabled' not in markup
    assert queue.enqueue_selected(first['id']) is True
    assert queue.enqueue_selected(first['id']) is False
    record = queue.list_jobs()[0]
    assert record['stage'] == 0 and record['file_path'] == ''
    retry = queue.tick(token, [])['jobs'][0]
    assert retry['receipt'] != first['receipt']


@pytest.mark.parametrize('signal', ['moved', 'replacement', 'offline', 'published', 'receipt'])
def test_deleted_design_redo_blocks_existing_unverified_or_posted_artwork(store, monkeypatch, signal):
    import product_upload_services
    from home_sports_morning_brief import SETTING_KEY
    from psd_directory import ROOT
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    cur.execute("UPDATE morning_design_jobs SET stage=5,file_id='id:saved',file_rev='R1',file_path='/Review/Final.psd' WHERE id=%s", (first['id'],))
    def metadata(self, path):
        if signal == 'offline':
            raise OSError('Synthetic outage')
        if signal == 'moved' and path == 'id:saved':
            return {'id': 'id:saved', 'path_display': '/Elsewhere/Renamed.psd'}
        if signal == 'replacement' and path == ROOT + '/Final.psd':
            return {'id': 'id:replacement'}
        return None
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: type('Provider', (), {'metadata_if_present': metadata})())
    if signal == 'published':
        cur.execute("INSERT INTO shopify_products VALUES ('product','ACTIVE','https://example.test/product')")
        cur.execute('INSERT INTO product_psd_mappings VALUES (%s,%s,%s)', ('product', 'id:saved', ROOT + '/Final.psd'))
    if signal == 'receipt':
        cur.execute("INSERT INTO product_upload_staff_jobs(id,source_id,source_rev,title,sport,stage) VALUES ('00000000-0000-0000-0000-000000000001','id:saved','R1','Final','NBA',6)")
    assert queue.list_jobs()[0]['label'] != 'Deleted · ready to redo'
    assert queue.enqueue_selected(first['id']) is True


def test_restored_design_is_rechecked_when_redo_is_clicked(store, monkeypatch):
    import product_upload_services
    from home_sports_morning_brief import SETTING_KEY
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    cur.execute("UPDATE morning_design_jobs SET stage=5,file_id='id:saved',file_path='/Review/Final.psd' WHERE id=%s", (first['id'],))
    present = []
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: type('Provider', (), {
        'metadata_if_present': lambda self, path: {'id': path} if present else None})())
    assert queue.list_jobs()[0]['label'] == 'Deleted · ready to redo'
    present.append(True)
    assert queue.enqueue_selected(first['id']) is True


def test_display_only_uses_cached_deletions_without_provider_reads(store, monkeypatch):
    import design_deletion_status
    cur, token = store
    publish(cur, count=1)
    job=queue.tick(token, [])['jobs'][0]
    cur.execute("UPDATE morning_design_jobs SET stage=5,file_id='id:deleted',file_rev='R1',file_path='/Review/Final.psd' WHERE id=%s", (job['id'],))
    monkeypatch.setattr(design_deletion_status,'deleted',lambda jobs,posted:{r['id'] for r in jobs})
    monkeypatch.setattr(queue,'_deleted_designs',lambda *args: (_ for _ in ()).throw(AssertionError('foreground Dropbox call')))
    assert queue.list_jobs(display_only=True)[0]['label']=='Deleted · ready to redo'


def test_requeue_during_output_lookup_ignores_previous_attempt(store, monkeypatch):
    from home_sports_morning_brief import SETTING_KEY
    cur, token = store
    edition = publish(cur, count=1)
    cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)', (SETTING_KEY, json.dumps(edition)))
    first = queue.tick(token, [])['jobs'][0]
    queue.tick(token, [dict(id=first['id'], state='failed')])

    def late_output(jobs):
        assert queue.enqueue_selected(first['id']) is True
        return {first['id']: dict(stage=4, message='', source=dict(
            id='id:old', rev='R1', path_display='/Review/Old.psd'))}

    monkeypatch.setattr(queue, 'verify_outputs', late_output)
    restarted = queue.tick(token, [])['jobs'][0]
    assert restarted['id'] == first['id']
    assert restarted['receipt'] != first['receipt']
    record = queue.list_jobs()[0]
    assert record['stage'] == 1 and record['file_path'] == ''


def test_waiting_refresh_upgrades_old_two_pass_snapshot_and_keeps_receipts():
    job_id = '00000000-0000-0000-0000-000000000123'
    old = ('SPORTS CAVE EXISTING DESIGN REFRESH\nOld two-pass refresh workflow.\n'
           'Product: Collector\nShopify product ID: 123\n'
           'Product page: https://example.test/products/collector\n'
           'Research hypothesis from the Home recommendation: Improve the title.\n'
           'Decision context: Selected by owner.\n1. Old workflow rules.\n'
           f'Include morning_design_job_id = "{job_id}" in the final .upload.json handoff. '
           'Save to Design Studio Review only; do not publish or alter the live product.\n'
           'Queue retry receipt: 00000000-0000-0000-0000-000000000001\n')
    job = dict(id=job_id, title='Collector', prompt=old)
    upgraded = queue._waiting_prompt(job)
    assert 'one creative image-generation call' in upgraded
    assert 'Old two-pass' not in upgraded and 'Old workflow rules' not in upgraded
    assert 'Improve the title.' in upgraded and 'Selected by owner.' in upgraded
    assert f'morning_design_job_id = "{job_id}"' in upgraded
    assert 'gid://shopify/Product/123' in upgraded
    assert 'design_origin (designs_to_refresh)' in upgraded
    assert queue._receipt(dict(job, prompt=upgraded)) == queue._receipt(job)
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_waiting_refresh_rebuilds_old_shared_brief_with_edition_lock():
    from home_design_refresh import _refresh_prompt
    job_id = '00000000-0000-0000-0000-000000000123'
    prompt = _refresh_prompt(dict(title='Collector', product_id='123', suggestion='Try a newer achievement.',
                                 evidence='Selected by owner.'), 'https://example.test/products/collector')
    prompt = prompt.replace('Existing edition/product title (preserve):',
                            'Current title (suggestion, not an approved title lock):')
    prompt = prompt.replace('Preserve the existing edition name, exact headline',
                            'Reconsider the title, photographs, composition and treatment freely. Preserve exact headline')
    tail = (f'\nInclude morning_design_job_id = "{job_id}" in the final .upload.json handoff.\n'
            'Queue retry receipt: 00000000-0000-0000-0000-000000000001\n'
            'Queue output receipt: 00000000-0000-0000-0000-000000000002\n')
    job = dict(id=job_id, title='Collector', prompt='SPORTS CAVE EXISTING DESIGN REFRESH\n'+prompt+tail)
    upgraded = queue._waiting_prompt(job)
    assert 'Reconsider the title, photographs, composition and treatment freely' not in upgraded
    assert 'Current title (suggestion' not in upgraded
    assert 'Existing edition/product title (preserve): Collector' in upgraded
    assert 'Try a newer achievement.' in upgraded and 'Selected by owner.' in upgraded
    assert 'any older suggestion to rename the edition or change its story is superseded' in upgraded
    assert upgraded.endswith(tail)
    assert queue._receipt(dict(job, prompt=upgraded)) == queue._receipt(job)
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded
