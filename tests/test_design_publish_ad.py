"""Exercise Publish + ad without sending a prompt or using live services."""
import hashlib
import io
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

import ads_page
import design_publish_ad as ads
import product_upload_staff_queue as uploads
from test_product_upload_staff_queue import database, store
from tests.test_ads_posting_handoff import completed_ad


def test_combined_job_preserves_upload_and_posts_once_after_four_files(store, monkeypatch):
    import meta_posting_jobs
    import os_accounts

    monkeypatch.setattr(ads, 'connect', store)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda user, page: True)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda key, **kwargs: {'id': key})
    actor = {'id': 'staff'}
    source = {'id': 'id:fixture-psd', 'rev': 'original'}
    upload = uploads.enqueue(actor, source, 'A Collector Design', 'Baseball', ad_country='USA')
    assert uploads.enqueue(actor, source, 'A Collector Design', 'Baseball') == upload
    with pytest.raises(ValueError, match='different targeting'):
        uploads.enqueue(actor, source, 'A Collector Design', 'Baseball', ad_country='UK')
    key = str(upload)
    token = uploads.pair({'id': 'desktop'})
    with pytest.raises(PermissionError):
        ads.tick('x' * 43, {})
    assert ads.tick(token, {}) == {}
    assert uploads.list_jobs('staff')['jobs'][0]['ad']['active']
    # An upload dependency failure must not fail or consume the waiting ad.
    with store() as conn, conn.cursor() as cur:
        cur.execute('UPDATE product_upload_staff_jobs SET stage=7 WHERE id=%s', (upload,))
    assert ads.tick(token, {}) == {}
    assert uploads.list_jobs('staff')['jobs'][0]['ad']['active']
    with store() as conn, conn.cursor() as cur:
        cur.execute('UPDATE product_upload_staff_jobs SET stage=0 WHERE id=%s', (upload,))
    assert not uploads.list_jobs('stranger')['jobs']

    uploads.desktop_tick(token)
    uploads.advance(upload, 'desktop', 5, intake=uuid4())
    assert ads.tick(token, {}) == {}
    uploads.advance(upload, 'desktop', 6, storefront='https://example.test/products/fixture')
    staged = dict(stage='opening', prompt='Sports Cave automatic ad job ' + key, folder='/fixture')
    monkeypatch.setattr(ads, '_prepare', lambda *_: deepcopy(staged))
    with store() as conn, conn.cursor() as cur:
        cur.execute("UPDATE app_settings SET updated_at=now()-interval '2 days' WHERE key=%s",
                    (ads.PREFIX + key,))
    opening = ads.tick(token, {})['job']
    assert opening['project'] == ads.PROJECT
    assert opening['id'] == key
    assert ads.tick(token, {'id': str(uuid4()), 'state': 'submitted'})['job'] == opening

    request = SimpleNamespace(submission_id=ads._posting_id(key))
    artifacts = []
    monkeypatch.setattr(ads, '_post_request', lambda _: request if len(artifacts) == 4 else None)
    receipts = {'status': 'CREATING'}
    calls = []
    def submit(post):
        calls.append(post)
        return post.submission_id
    monkeypatch.setattr(meta_posting_jobs, 'JOBS', SimpleNamespace(submit=submit, snapshot=lambda _: receipts))
    monkeypatch.setattr(meta_posting_jobs, 'confirmed_ads', lambda row: (3, 3))
    assert ads.tick(token, {'id': key, 'state': 'submitted'})['job']['stage'] == 'generating'
    artifacts.extend(['copy', 'cover-one', 'cover-two'])
    assert ads.tick(token, {})['job']['stage'] == 'generating'
    assert not calls
    artifacts.append('cover-three')
    ads.tick(token, {})
    ads.tick(token, {})
    assert calls == [request]
    receipts['status'] = 'COMPLETE'
    ads.tick(token, {})
    done = uploads.list_jobs('staff')['jobs'][0]
    assert done['stage'] == 6 and done['percent'] == 100
    assert done['ad']['posting_id'] == request.submission_id
    assert not done['ad']['active']


def test_exact_primary_market_comes_from_matching_brief(store, monkeypatch):
    import morning_design_queue as morning
    from home_brief_calendar import HISTORY_PREFIX

    monkeypatch.setattr(ads, 'connect', store)
    with store() as conn, conn.cursor() as cur:
        cur.execute('CREATE TABLE morning_design_jobs (id uuid PRIMARY KEY, edition_date date, section text, title text, prompt text)')
        article = dict(title='Fixture leads the league', sport='Ice Hockey', markets=['CA', 'USA'],
                       primary_market='USA', recommendation='Fixture')
        day = '2026-11-17'
        morning.insert_suggestion(cur, day, 'recommendations', article)
        job = morning.identity(day, 'recommendations', article)
        cur.execute('SELECT prompt FROM morning_design_jobs WHERE id=%s', (job,))
        assert 'primary_market = "USA"' in cur.fetchone()['prompt']
        cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',
                    (HISTORY_PREFIX + day, json.dumps({'recommendations': [article]})))
    assert ads.primary_country({'morning_design_job_id': job, 'primary_market': 'CA'}) == 'USA'
    assert ads.primary_country({'primary_market': 'NZ'}) == 'New Zealand'
    assert ads.primary_country({}) == ''


@pytest.mark.parametrize('country,code', [('Australia', 'AUS'), ('Canada', 'CAN'), ('USA', 'USA')])
def test_post_request_imports_originals_in_route_order(country, code, monkeypatch):
    import ads_direct_post
    import product_upload_services
    import ads_posting_page

    folder = '/fixture'
    upload = str(uuid4())
    result, workflow = completed_ad('Instant Experience')
    result.update(country=country, category='Baseball', product_name='Forever a Brewer - Ken Sanders Wall Art')
    assets = {'ad_copy.csv': ads_page.build_instant_experience_copy_csv(result, workflow)}
    for position, name in enumerate(ads.COVERS.values(), 1):
        file = io.BytesIO()
        Image.new('RGB', (512, 512), (position * 40, 100, 150)).save(file, format='JPEG')
        assets[name] = file.getvalue()
    def info(path):
        name = path.rsplit('/', 1)[1]
        data = assets.get(name)
        if data:
            return dict(name=name, id='id:' + name, rev='1c0ffeebb', size=len(data),
                        content_hash=hashlib.sha256(data).hexdigest(), path_display=path)
    def download(token, file_id, rev):
        name = file_id.removeprefix('id:')
        return info(folder + '/' + name), SimpleNamespace(iter_content=lambda **_: [assets[name]], close=lambda: None)
    monkeypatch.setattr(product_upload_services, 'Dropbox', lambda: SimpleNamespace(
        token='fixture', metadata_if_present=info, api=SimpleNamespace(get_psd_file_response=download)))
    refs = dict(product_sets=[{'id': '20', 'name': 'Baseball Wall Art'},
                              {'id': '21', 'name': 'Baseball Popular Set'},
                              {'id': '22', 'name': 'NFL Popular Set'}],
                saved_audiences=[{'id': '23', 'name': 'Baseball Collectors'},
                                 {'id': '24', 'name': 'Baseball · Ken Sanders'}],
                catalog_resolution={'id': '25'}, dataset_resolution={'id': '26'}, page=True, instagram=True)
    monkeypatch.setattr(ads_direct_post, 'references', lambda *_args, **kwargs: refs)
    value = dict(result=result, folder=folder, handle='fixture-product', upload=upload)
    monkeypatch.setattr(ads, 'write', lambda *_: None)
    def membership_must_not_gate_targeting(*args, **kwargs):
        raise AssertionError('Queue targeting selects the canonical sport collection without a membership read.')
    monkeypatch.setattr(ads_posting_page, 'MetaPostingClient', lambda: SimpleNamespace(
        product_set_members=membership_must_not_gate_targeting))
    request = ads._post_request(value)
    assert request.country == code
    assert request.product_set_id == '20'
    assert request.audience_id == '24'
    assert request.submission_id == ads._posting_id(upload)
    assert tuple(creative.image_name for creative in request.creatives) == tuple(ads.COVERS.values())
    assert all(creative.primary_text and creative.headline for creative in request.creatives)
    assert ads._selected_product_set([refs['product_sets'][0]], 'Baseball') == '20'
    with pytest.raises(ValueError, match='No Baseball'):
        ads._selected_product_set([refs['product_sets'][2]], 'Baseball')
    assets.pop('man-cave.jpg')
    assert ads._post_request(value) is None


def test_handoff_pins_black_frame_and_existing_ad_prompt():
    saved = {'folder': '/upload', 'originals': {'black-frame': {'filename': 'original-black.webp',
             'file_id': 'id:exact', 'revision': 'abcd123456', 'size_bytes': 123, 'content_hash': 'hash-exact'}}}
    prompt = ads._prompt({'master_prompt': 'EXISTING APPROVED AD PROMPT'}, saved, '/approved/ads/fixture', 'job')
    assert prompt.startswith('Sports Cave automatic ad job job\n')
    assert all(term in prompt for term in ('/upload/original-black.webp', 'id:exact', 'abcd123456',
                                           'hash-exact', 'EXISTING APPROVED AD PROMPT'))
    assert all('/approved/ads/fixture/' + name in prompt for name in (*ads.COVERS.values(), 'ad_copy.csv'))




def test_ads_companion_heartbeat_pause_and_blocked_job_history(store, monkeypatch):
    import os_accounts

    monkeypatch.setattr(ads, 'connect', store)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda user, page: True)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda key, **kwargs: {'id': key})
    token = uploads.pair({'id': 'desktop'})
    actor = {'id': 'staff'}
    first, second = [
        uploads.enqueue(actor, {'id': 'id:' + title, 'rev': 'r1'}, title, 'Baseball', ad_country='USA')
        for title in ('First', 'Second')
    ]
    for key in (first, second):
        assert uploads.desktop_tick(token)['id'] == key
        uploads.advance(key, 'desktop', 6, allowed=[1])
    assert ads.dashboard()['online'] is False  # Upload polling alone does not mean the Ads worker is installed.
    assert ads.settings(False) == {'enabled': False}
    assert ads.tick(token, {}) == {}
    status = ads.dashboard()
    assert status['online'] and not status['enabled']
    assert [job['label'] for job in status['jobs']] == ['Ready · queue paused'] * 2

    monkeypatch.setattr(ads, '_prepare', lambda *_: {'stage': 'opening', 'prompt': 'Fixture prompt'})
    monkeypatch.setattr(ads, '_post_request', lambda _: None)
    ads.settings(True)
    assert ads.tick(token, {})['job']['id'] == str(first)
    ads.settings(False)
    # Pausing preserves the first job and never dispatches the second.
    chat = ads.PROJECT.removesuffix('/project') + '/c/' + str(uuid4())
    reply = ads.tick(token, {'id': str(first), 'state': 'submitted', 'chat_url': chat})
    assert reply['job']['stage'] == 'generating'
    assert ads.tick(token, {'id': str(first), 'state': 'blocked',
                            'reason': 'Dropbox did not return the reference.'}) == {}
    assert ads.tick(token, {}) == {}
    jobs = {job['title']: job for job in ads.dashboard()['jobs']}
    assert jobs['First']['stage'] == 'waiting' and jobs['First']['chat_url'] == chat
    assert jobs['First']['label'] == 'Automatic recovery scheduled'
    assert 'Dropbox did not return the reference.' in jobs['First']['detail']
    assert jobs['Second']['stage'] == 'waiting'
    ads.settings(True)
    assert ads.tick(token, {})['job']['id'] == str(second)


def test_companion_shows_selected_ads_queue(monkeypatch):
    # AppTest has no browser visibility; the real component is covered in Edge.
    monkeypatch.setattr('upload_companion_page.visible', lambda: True)
    monkeypatch.setattr('upload_companion_page.read_display', lambda name, loader: loader())
    import ads_companion_quick_add
    monkeypatch.setattr(ads_companion_quick_add,'catalog',lambda:dict(products=[]))
    from streamlit.testing.v1 import AppTest
    import os_accounts
    import upload_companion_page as page

    monkeypatch.setattr(os_accounts, 'can_access_page', lambda user, route: True)
    monkeypatch.setattr(page, 'render_design_queue', lambda *_: None)
    monkeypatch.setattr(page, 'render_queue', lambda *_: None)
    monkeypatch.setattr(ads, 'dashboard', lambda: {'online': True, 'enabled': False, 'jobs': [
        dict(stage='waiting', active=True, title='Fixture', country='USA', sport='Baseball',
             label='Ready · queue paused')
    ]})
    app = AppTest.from_string(
        "import upload_companion_page as page; page.render_page({'id': 'fixture'})"
    ).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ['Design queue', 'Upload queue', 'Ads queue', 'Orders queue']
    assert not app.button  # Hidden queues no longer execute.
    app.session_state['companion-queue-tabs'] = 'Ads queue'
    app.run()
    assert not app.exception
    assert [(button.label, button.disabled) for button in app.button] == [('Play', False), ('Pause', True)]
    assert any('Fixture' in text.value for text in app.markdown)


def test_catalog_backoff_keeps_other_ads_queued(store, monkeypatch):
    import os_accounts
    monkeypatch.setattr(ads, 'connect', store)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *args: True)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda key: {'id': key})
    token = uploads.pair({'id':'desktop'})
    waiting, ready = str(uuid4()), str(uuid4())
    with store() as conn, conn.cursor() as cur:
        for key, retry in ((waiting, {'next_at':ads.time.time()+900}), (ready, {})):
            value=dict(upload=key,source='new_ads',stage='generating' if retry else 'waiting',requester='staff',catalog_retry=retry)
            cur.execute('INSERT INTO app_settings(key,value) VALUES (%s,%s::jsonb)', (ads.PREFIX+key,json.dumps(value)))
    processed=[]
    monkeypatch.setattr(ads,'_step',lambda key,value,*args: processed.append(value['upload']) or {})
    ads.tick(token,{})
    assert processed==[waiting]
